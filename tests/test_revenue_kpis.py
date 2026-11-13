import sys
import unittest
import multiprocessing
import tempfile
import threading
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from app import app
from pages.executive import (
    layout,
    monthly_figure,
    populate_report,
    normalize_filters,
)
from revenue_kpis import kpi_cards, kpi_sql


class RevenueKpiTests(unittest.TestCase):
    def test_concurrent_worker_cache_misses_submit_one_load(self):
        from flask import Flask
        from revenue_kpis import cache, load_executive_report

        context = multiprocessing.get_context("fork")
        count = context.Value("i", 0)
        barrier = context.Barrier(3)
        results = context.Queue()
        server = Flask("coalescing-test")
        with tempfile.TemporaryDirectory() as directory:
            cache.init_app(
                server, config={"CACHE_TYPE": "FileSystemCache", "CACHE_DIR": directory}
            )
            lock_dir = Path(directory) / "locks"
            lock_dir.mkdir()
            server.extensions["executive_query_lock_dir"] = lock_dir

            def query_rows_mock(*args, **kwargs):
                with count.get_lock():
                    count.value += 1
                threading.Event().wait(0.1)
                # Financials, orders, monthly, then detail — in loader order.
                return [
                    [
                        {
                            "gross_revenue_amount": 100,
                            "gross_profit_amount": 10,
                            "source_rows": 42,
                            "gross_profit_margin_percentage": 10.0,
                        }
                    ],
                    [{"total_orders_count": 5}],
                    [],
                    [],
                ][(count.value - 1) % 4]

            def fetch():
                try:
                    barrier.wait(timeout=5)
                    with server.app_context():
                        results.put(
                            load_executive_report("test-project", "test_dataset")[
                                "source_rows"
                            ]
                        )
                except Exception as error:
                    results.put(type(error).__name__)

            with patch("revenue_kpis.query_rows", side_effect=query_rows_mock):
                workers = [context.Process(target=fetch) for _ in range(3)]
                try:
                    for worker in workers:
                        worker.start()
                    for worker in workers:
                        worker.join(timeout=10)
                        self.assertEqual(worker.exitcode, 0)
                    self.assertEqual(
                        [results.get(timeout=1) for _ in workers], [42, 42, 42]
                    )
                    # One cold load runs the four report SQL reads exactly once.
                    self.assertEqual(count.value, 4)
                finally:
                    for worker in workers:
                        if worker.is_alive():
                            worker.terminate()
                            worker.join()
                    results.close()

    def test_chart_menus_only_trigger_their_own_chart_and_title(self):
        callbacks = app.callback_map
        for menu, expected in (
            (
                "executive-chart-type",
                {
                    "executive-primary.figure",
                    "executive-primary-status.children",
                    "executive-chart-title.children",
                },
            ),
            (
                "executive-breakdown-type",
                {
                    "executive-secondary.figure",
                    "executive-secondary-status.children",
                    "executive-breakdown-title.children",
                },
            ),
            (
                "executive-monthly-granularity",
                {
                    "executive-primary.figure",
                    "executive-primary-status.children",
                    "executive-chart-title.children",
                },
            ),
        ):
            triggered = {
                part
                for output, metadata in callbacks.items()
                for part in output.strip(".").split("...")
                if any(item["id"] == menu for item in metadata["inputs"])
            }
            self.assertEqual(triggered, expected)
        for output in ("executive-primary.figure", "executive-secondary.figure"):
            self.assertTrue(
                {
                    f"executive-{name}"
                    for name in (
                        "year",
                        "quarter",
                        "channel",
                        "category",
                        "subcategory",
                    )
                }
                <= {
                    item["id"]
                    for item in next(
                        metadata for key, metadata in callbacks.items() if output in key
                    )["inputs"]
                }
            )

    def test_each_kpi_has_its_own_loading_target(self):
        from dash import dcc
        from revenue_kpis import KPI_FIELDS
        from pages.executive import update_report

        def walk(component):
            yield component
            children = getattr(component, "children", [])
            for child in children if isinstance(children, list) else [children]:
                if child is not None:
                    yield from walk(child)

        nodes = list(walk(layout()))
        for key, _, _ in KPI_FIELDS:
            spinner = next(
                n
                for n in nodes
                if getattr(n, "id", None) == f"executive-kpi-loading-{key}"
            )
            self.assertIsInstance(spinner, dcc.Loading)
            self.assertEqual(spinner.children.id, f"executive-kpi-slot-{key}")
        result = update_report(None, *["__all__"] * 5, {})
        self.assertEqual(len(result), 10)
        self.assertEqual(
            [card.id for card in result[:5]],
            [f"executive-kpi-{key}" for key, _, _ in KPI_FIELDS],
        )
        # The ranked top-categories card fills the slot right after the KPIs.
        self.assertIn("No ranked results", str(result[5]))

    def test_five_cards_and_percentage_units(self):
        cards = kpi_cards(
            {
                "gross_revenue_amount": Decimal("1234567.89"),
                "gross_profit_amount": Decimal("250000.00"),
                "gross_profit_margin_percentage": Decimal("20.25"),
                "total_orders_count": 12000,
                "average_order_value_aov": Decimal("102.88"),
            }
        )
        self.assertEqual(len(cards), 5)
        self.assertEqual(
            [c.children[1].children for c in cards],
            ["$1.23M", "$250K", "20.25%", "12K", "$102.88"],
        )
        self.assertEqual(len({c.id for c in cards}), 5)

    def test_null_and_zero_are_distinct(self):
        cards = kpi_cards({"gross_revenue_amount": 0, "total_orders_count": 0})
        self.assertEqual(cards[0].children[1].children, "$0.00")
        self.assertEqual(cards[2].children[1].children, "—")
        self.assertEqual(cards[3].children[1].children, "0")

    def test_layout_does_not_query(self):
        with patch("pages.executive.load_executive_report") as query:
            layout()
            query.assert_not_called()

    def test_empty_and_error_preserve_five_cards(self):
        catalog = [
            {
                "calendar_year": 2013,
                "calendar_quarter_name": "Q1",
                "sales_channel": "Internet",
                "product_category": "Bikes",
                "product_subcategory": "Road Bikes",
            }
        ]
        empty = {
            "monthly": [],
            "detail": [],
            "gross_revenue_amount": 0,
            "total_orders_count": 0,
        }
        with patch("pages.executive.load_executive_report", return_value=empty):
            result = populate_report(
                catalog, "__all__", "__all__", "__all__", "__all__", "__all__", {}
            )
            self.assertEqual(len(result[0]), 5)
            self.assertIn("No warehouse sales", result[-1])
        with patch(
            "pages.executive.load_executive_report",
            side_effect=RuntimeError("private diagnostic"),
        ):
            result = populate_report(
                catalog, "__all__", "__all__", "__all__", "__all__", "__all__", {}
            )
            self.assertEqual(len(result[0]), 5)
            self.assertIn("Unable", result[-1])
            self.assertNotIn("private diagnostic", result[-1])

    def test_filter_validation(self):
        import dash

        catalog = [
            {
                "calendar_year": 2013,
                "calendar_quarter_name": "Q1",
                "sales_channel": "Internet",
                "product_category": "Bikes",
                "product_subcategory": "Road Bikes",
            },
            {
                "calendar_year": 2013,
                "calendar_quarter_name": "Q1",
                "sales_channel": "Reseller",
                "product_category": "Clothing",
                "product_subcategory": "Jerseys",
            },
        ]
        self.assertEqual(
            normalize_filters(
                catalog, "__all__", "__all__", "Internet", "Bikes", "Road Bikes"
            ),
            [None, None, "Internet", "Bikes", "Road Bikes"],
        )
        with self.assertRaises(dash.exceptions.PreventUpdate):
            normalize_filters(catalog, 2013, "Q1", "Internet", "Bikes", "Jerseys")
        with self.assertRaises(ValueError):
            normalize_filters(catalog, 2099, "Q1", "Internet", "Bikes", "Road Bikes")

    def test_rollup_uses_distinct_baskets_and_weighted_ratios(self):
        query = kpi_sql("test-project", "gold_adventureworks")
        self.assertIn("SELECT DISTINCT s.sales_channel, s.sales_order_number", query)
        self.assertNotIn("SUM(product_purchasing_orders_count)", query)
        self.assertIn("gross_profit_amount / gross_revenue_amount", query)
        self.assertIn("gross_revenue_amount / total_orders_count", query)
        self.assertIn("THEN NULL", query)


class MonthlyComboChartTests(unittest.TestCase):
    def test_weighted_margin_axes_and_zero_revenue(self):
        values = {
            "monthly": [
                {
                    "calendar_year": 2024,
                    "month_name": "February",
                    "sales_channel": "Internet",
                    "revenue": 0,
                    "profit": -10,
                },
                {
                    "calendar_year": 2024,
                    "month_name": "January",
                    "sales_channel": "Internet",
                    "revenue": 100,
                    "profit": 50,
                },
                {
                    "calendar_year": 2024,
                    "month_name": "January",
                    "sales_channel": "Reseller",
                    "revenue": 900,
                    "profit": 90,
                },
                {
                    "calendar_year": 2024,
                    "month_name": "March",
                    "sales_channel": "Internet",
                    "revenue": 200,
                    "profit": -20,
                },
            ],
            "detail": [],
            "fetched_at": "12:00 UTC",
        }
        chart = monthly_figure(values, "dual")
        original = monthly_figure(values)
        self.assertEqual(len(original.data), 1)
        self.assertEqual(original.data[0].type, "scatter")
        self.assertEqual(list(original.data[0].y), [1000, 0, 200])
        bars, line = chart.data
        self.assertEqual(bars.type, "bar")
        self.assertEqual(list(bars.y), [1000, 0, 200])
        self.assertEqual(line.type, "scatter")
        self.assertAlmostEqual(line.y[0], 14)
        self.assertIsNone(line.y[1])
        self.assertAlmostEqual(line.y[2], -10)
        self.assertEqual(line.yaxis, "y2")
        self.assertFalse(line.connectgaps)
        self.assertEqual(chart.layout.yaxis2.ticksuffix, "%")


class RevenueBreakdownTests(unittest.TestCase):
    def test_channel_shares_and_product_hierarchy(self):
        import pandas as pd
        from pages.executive import revenue_breakdown

        channels = pd.DataFrame(
            {"sales_channel": ["Internet", "Reseller"], "revenue": [100, 300]}
        )
        bars = revenue_breakdown(channels, [])
        self.assertTrue(all(trace.type == "bar" for trace in bars.data))
        self.assertEqual(sum(sum(trace.y) for trace in bars.data), 400)
        donut = revenue_breakdown(channels, [], "donut")
        self.assertEqual(list(donut.data[0].labels), ["B2C Internet", "B2B Reseller"])
        self.assertEqual(list(donut.data[0].values), [100, 300])
        self.assertEqual(donut.data[0].hole, 0.62)
        self.assertIn("$400.00", donut.layout.annotations[0].text)
        single = revenue_breakdown(channels.iloc[:1], [], "donut")
        self.assertIn("$100.00", single.layout.annotations[0].text)
        detail = [
            {
                "product_category": "Bikes",
                "product_subcategory": "Road",
                "revenue": 100,
            },
            {
                "product_category": "Bikes",
                "product_subcategory": "Road",
                "revenue": 200,
            },
            {
                "product_category": "Clothing",
                "product_subcategory": "Jerseys",
                "revenue": 100,
            },
        ]
        tree = revenue_breakdown(channels, detail, "treemap").data[0]
        totals = dict(zip(tree.ids, tree.values))
        self.assertEqual(totals["All products/Bikes/Road"], 300)
        self.assertEqual(totals["All products"], 400)
        empty = revenue_breakdown(channels, [], "treemap")
        self.assertEqual(len(empty.data), 0)
        self.assertIn("No positive revenue", empty.layout.annotations[0].text)


class YoyBadgeTests(unittest.TestCase):
    def test_ratios_margin_points_and_zero_baseline(self):
        from revenue_kpis import yoy_badge
        import dash_bootstrap_components as dbc

        values = {
            "revenue": 120,
            "margin": 12,
            "yoy": {
                "period": "2024 vs 2023",
                "previous": {"revenue": 100, "margin": 10},
            },
        }
        self.assertIsInstance(yoy_badge("revenue", "currency", values), dbc.Badge)
        self.assertEqual(
            yoy_badge("revenue", "currency", values).children, "↑ 20.0% YoY"
        )
        self.assertEqual(yoy_badge("margin", "percent", values).children, "↑ 2.0pp YoY")
        values["yoy"]["previous"]["revenue"] = 0
        self.assertEqual(yoy_badge("revenue", "currency", values).children, "YoY N/A")
        values["yoy"]["previous"]["revenue"] = 200
        self.assertEqual(
            yoy_badge("revenue", "currency", values).children, "↓ 40.0% YoY"
        )

    def test_comparison_keeps_filters_and_does_not_mutate_cached_result(self):
        from revenue_kpis import add_yoy_comparison

        current = {"source_rows": 1}
        with patch(
            "revenue_kpis.load_executive_report", return_value={"source_rows": 2}
        ) as query:
            result = add_yoy_comparison(
                current,
                "project",
                "dataset",
                2024,
                "Q2",
                "Internet",
                "Bikes",
                "Road Bikes",
            )
            query.assert_called_once_with(
                "project", "dataset", 2023, "Q2", "Internet", "Bikes", "Road Bikes"
            )
            self.assertIn("previous", result["yoy"])
            self.assertNotIn("yoy", current)
        with patch("revenue_kpis.load_executive_report") as query:
            result = add_yoy_comparison(
                current, "project", "dataset", None, None, None, None, None
            )
            query.assert_not_called()
            self.assertEqual(result["yoy"]["reason"], "Select year for YoY")
        with patch(
            "revenue_kpis.load_executive_report", return_value={"source_rows": 0}
        ):
            result = add_yoy_comparison(
                current, "project", "dataset", 2024, None, None, None, None
            )
            self.assertEqual(result["yoy"]["reason"], "No prior-year data")
        with patch(
            "revenue_kpis.load_executive_report", side_effect=RuntimeError("private")
        ):
            result = add_yoy_comparison(
                current, "project", "dataset", 2024, None, None, None, None
            )
            self.assertEqual(result["yoy"]["reason"], "YoY unavailable")


MONTHLY_FIXTURE = [
    {
        "calendar_year": 2024,
        "month_name": "January",
        "sales_channel": "Internet",
        "revenue": 100,
        "profit": 50,
    },
    {
        "calendar_year": 2024,
        "month_name": "January",
        "sales_channel": "Reseller",
        "revenue": 900,
        "profit": 90,
    },
    {
        "calendar_year": 2024,
        "month_name": "February",
        "sales_channel": "Internet",
        "revenue": 0,
        "profit": -10,
    },
    {
        "calendar_year": 2024,
        "month_name": "March",
        "sales_channel": "Internet",
        "revenue": 200,
        "profit": -20,
    },
]


class KpiSparklineTests(unittest.TestCase):
    def test_series_kpis_get_sparklines_and_scalars_do_not(self):
        from dash import dcc

        values = {
            "gross_revenue_amount": 1200,
            "gross_profit_amount": 120,
            "gross_profit_margin_percentage": 10.0,
            "total_orders_count": 5,
            "average_order_value_aov": 240.0,
        }
        cards = kpi_cards(values, note=None, monthly=MONTHLY_FIXTURE)
        by_key = {card.id: card for card in cards}
        for key in (
            "gross_revenue_amount",
            "gross_profit_amount",
            "gross_profit_margin_percentage",
        ):
            spark = by_key[f"executive-kpi-{key}"].children[-2]
            self.assertIsInstance(spark, dcc.Graph)
            self.assertEqual(len(spark.figure.data[0].x), 3)
        for key in ("total_orders_count", "average_order_value_aov"):
            card_children = by_key[f"executive-kpi-{key}"].children
            self.assertFalse(
                any(isinstance(child, dcc.Graph) for child in card_children)
            )
        # The YoY badge stays the last child on every card.
        from dash import html

        import dash_bootstrap_components as dbc

        for card in cards:
            self.assertNotIsInstance(card.children[-1], dcc.Graph)
            self.assertIsInstance(card.children[-1], (html.Div, dbc.Badge))

    def test_margin_sparkline_gaps_zero_revenue_months(self):
        figure = (
            kpi_cards(
                {"gross_profit_margin_percentage": 10.0},
                note=None,
                monthly=MONTHLY_FIXTURE,
            )[2]
            .children[-2]
            .figure
        )
        self.assertEqual(len(figure.data[0].x), 3)
        self.assertAlmostEqual(figure.data[0].y[0], 14.0)
        self.assertIsNone(figure.data[0].y[1])
        self.assertFalse(figure.data[0].connectgaps)

    def test_without_monthly_rows_cards_stay_plain(self):
        cards = kpi_cards({"gross_revenue_amount": 1200}, note=None)
        self.assertEqual(len(cards[0].children), 3)  # label, value, badge


class QuarterlyGranularityTests(unittest.TestCase):
    def test_quarters_sum_monthly_rows_and_recompute_margin(self):
        values = {
            "monthly": MONTHLY_FIXTURE,
            "detail": [],
            "fetched_at": "12:00 UTC",
        }
        line = monthly_figure(values, granularity="quarter")
        self.assertEqual(len(line.data[0].x), 1)
        self.assertEqual([round(value) for value in line.data[0].y], [1200])
        dual = monthly_figure(values, "dual", granularity="quarter")
        bars, margin_line = dual.data
        self.assertEqual([round(value) for value in bars.y], [1200])
        # Quarter margin = summed profit / summed revenue (110/1200), not an
        # average of the monthly margins.
        self.assertAlmostEqual(margin_line.y[0], 9.1666667, places=6)

    def test_monthly_remainder_and_titles_track_granularity(self):
        values = {
            "monthly": MONTHLY_FIXTURE,
            "detail": [],
            "fetched_at": "12:00 UTC",
        }
        monthly_line = monthly_figure(values, granularity="month")
        self.assertEqual(len(monthly_line.data[0].x), 3)
        callbacks = app.callback_map
        title_metadata = next(
            metadata
            for key, metadata in callbacks.items()
            if "executive-chart-title.children" in key
        )
        self.assertTrue(
            {
                "executive-chart-type",
                "executive-monthly-granularity",
            }
            <= {item["id"] for item in title_metadata["inputs"]}
        )


class AdaptedComponentTests(unittest.TestCase):
    def test_metric_without_sparkline_keeps_original_children(self):
        from components import metric

        card = metric("Label", "12", "note")
        self.assertEqual(len(card.children), 3)
        self.assertEqual(card.children[0].children, "Label")
        self.assertEqual(card.children[1].children, "12")

    def test_metric_appends_sparkline_last(self):
        from components import metric
        import plotly.graph_objects as go

        card = metric("Label", "12", "note", sparkline=go.Figure())
        self.assertEqual(len(card.children), 4)
        self.assertEqual(card.children[-1].className, "metric-sparkline")

    def test_ranked_list_orders_rows_and_clamps_shares(self):
        from components import ranked_list

        rows = [
            {"name": "Bikes · Road", "value": "$300.00", "share": 0.5},
            {"name": "Clothing · Jerseys", "value": "$100.00", "share": 1.4},
            {"name": "Accessories · Pumps", "value": "$0.00", "share": None},
        ]
        rendered = ranked_list(rows)
        self.assertEqual(rendered.className, "ranked-list")
        self.assertEqual(
            [item.children[0].children for item in rendered.children], ["1", "2", "3"]
        )
        bars = [item.children[1].children[1].children for item in rendered.children]
        self.assertEqual([bar.style["width"] for bar in bars], ["50%", "100%", "0%"])
        values = [item.children[-1].children for item in rendered.children]
        self.assertEqual(values, ["$300.00", "$100.00", "$0.00"])

    def test_ranked_list_empty_state(self):
        from components import ranked_list

        rendered = ranked_list([])
        self.assertIn("No ranked results", rendered.children)

    def test_top_category_rows_share_of_positive_revenue(self):
        from pages.executive import top_category_rows

        detail = [
            {
                "product_category": "Bikes",
                "product_subcategory": "Road",
                "revenue": 300,
            },
            {
                "product_category": "Bikes",
                "product_subcategory": "Mountain",
                "revenue": -50,
            },
            {"product_category": None, "product_subcategory": None, "revenue": 100},
        ]
        rows = top_category_rows(detail, limit=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Bikes · Road")
        self.assertEqual(rows[0]["value"], "$300.00")
        self.assertAlmostEqual(rows[0]["share"], 300 / 400)
        self.assertEqual(top_category_rows([]), [])
        negative_only = top_category_rows(
            [
                {
                    "product_category": "Bikes",
                    "product_subcategory": "Road",
                    "revenue": -1,
                }
            ]
        )
        self.assertEqual(negative_only, [])
