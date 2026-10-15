"""Opt-in deterministic customer-map characterization; no server or service clients."""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import platform
import tempfile
import statistics
import sys
import time
import tracemalloc
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "my-dash-app"))
# These modules read only bundled boundaries and visual tokens, never app.py/.env.
from customer_map import OVERVIEW, boundaries, normalized, revenue_map  # noqa: E402


def build_indexes(data: dict[str, Any]) -> tuple[dict, dict]:
    """Phase proxy mirroring revenue_map's current local index construction."""
    countries = {feature["id"]: feature for feature in data["countries"]}
    states = {}
    for feature in data["states"]:
        properties = feature["properties"]
        for name in [properties["name"], *properties["aliases"]]:
            for alias in name.split("|"):
                states[(properties["country"], normalized(alias))] = feature
    return countries, states


def aggregate_proxy(rows: list[dict], group: str, countries: dict, states: dict):
    """Matching/Decimal phase proxy; excludes geometry, labels and Plotly objects."""
    totals: dict[str, Decimal] = {}
    omitted = Decimal(0)
    for row in rows:
        territory = row["territory_group"] or "Unknown"
        if group != OVERVIEW and territory != group:
            continue
        value = Decimal(str(row["revenue"]))
        if group == OVERVIEW:
            if row["country"] not in countries:
                omitted += value
                continue
            key = territory
        else:
            feature = states.get((row["country"], normalized(row["state"])))
            if feature is None:
                omitted += value
                continue
            key = feature["id"]
        totals[key] = totals.get(key, Decimal(0)) + value
    return totals, omitted


def fixture(size: int, data: dict[str, Any]) -> list[dict]:
    """Unique country/state/territory groups, with controlled unmapped tail."""
    rows = []
    # Alternate names exercise accent folding, punctuation and boundary aliases.
    for index, feature in enumerate(data["states"][:size]):
        properties = feature["properties"]
        name = next(iter(properties["aliases"]), properties["name"]).split("|")[0]
        rows.append(
            dict(
                country=properties["country"],
                state=name,
                territory_group="Europe" if index % 2 == 0 else "Other",
                revenue=Decimal("100.01") + Decimal(index) / Decimal(100),
            )
        )
    # Explicit historical normalization aliases; retain distinct input groups.
    aliases = ["Garonne Haute", "Seine Paris", "Yveline"]
    for name in aliases:
        if len(rows) < size:
            rows.append(
                dict(
                    country="France",
                    state=name,
                    territory_group="Europe",
                    revenue=Decimal("0.10"),
                )
            )
    while len(rows) < size:
        index = len(rows)
        rows.append(
            dict(
                country="France" if index % 2 else "Unknown country",
                state=f"Unknown state {index}",
                territory_group="Europe",
                revenue=Decimal("0.10"),
            )
        )
    return rows


def measure(operation: Callable[[], Any], repetitions: int) -> dict:
    """Separate wall-clock and traced-allocation samples to avoid conflation."""
    elapsed = []
    for _ in range(repetitions):
        gc.collect()
        start = time.perf_counter_ns()
        result = operation()
        elapsed.append((time.perf_counter_ns() - start) / 1_000_000)
        del result
    gc.collect()
    tracemalloc.start()
    result = operation()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del result
    return dict(
        median_ms=round(statistics.median(elapsed), 4),
        min_ms=round(min(elapsed), 4),
        max_ms=round(max(elapsed), 4),
        python_peak_bytes=peak,
    )


def check_result(rows: list[dict], group: str, countries: dict, states: dict):
    totals, omitted = aggregate_proxy(rows, group, countries, states)
    figure, note = revenue_map(rows, group)
    if totals:
        trace = figure.data[0]
        actual = dict(zip(trace.locations, (item[1] for item in trace.customdata)))
        expected = {key: f"${value:,.2f}" for key, value in totals.items()}
        if actual != expected:
            raise AssertionError("Map currency totals differ from Decimal fixture")
    elif figure.data:
        raise AssertionError("Empty fixture unexpectedly produced a map trace")
    if omitted and f"${omitted:,.2f}" not in note:
        raise AssertionError("Missing unlocated revenue")
    return figure, totals, omitted


def run(sizes: list[int], repetitions: int) -> dict:
    # Warm Plotly's imports/templates once; boundary cold means its LRU only.
    revenue_map([])
    data = boundaries()
    countries, states = build_indexes(data)
    for alias, canonical in (
        ("Garonne Haute", "Haute Garonne"),
        ("Seine Paris", "Paris"),
        ("Yveline", "Yvelines"),
    ):
        if normalized(alias) != normalized(canonical):
            raise AssertionError("Historical alias contract changed")
        if ("France", normalized(alias)) not in states:
            raise AssertionError("Fixture alias does not resolve to a bundled state")
    precision_rows = [
        dict(
            country="France",
            state="Seine Paris",
            territory_group="Europe",
            revenue=Decimal("0.10"),
        ),
        dict(
            country="France",
            state="Paris",
            territory_group="Europe",
            revenue=Decimal("0.20"),
        ),
    ]
    precision_figure, _ = revenue_map(precision_rows, "Europe")
    if list(precision_figure.data[0].customdata)[0][1] != "$0.30":
        raise AssertionError("Decimal alias accumulation lost exact currency")
    check_result([], OVERVIEW, countries, states)
    check_result(
        [
            dict(
                country="Unknown",
                state=None,
                territory_group=None,
                revenue=Decimal("0.10"),
            )
        ],
        "Unknown",
        countries,
        states,
    )

    def cold_boundaries():
        boundaries.cache_clear()
        return boundaries()

    results = dict(
        boundary_lru_cold=measure(cold_boundaries, repetitions),
        boundary_lru_warm=measure(boundaries, repetitions),
        index_build_proxy=measure(lambda: build_indexes(data), repetitions),
    )
    cases = []
    for size in sizes:
        rows = fixture(size, data)
        for group in (OVERVIEW, "Europe"):
            figure, totals, omitted = check_result(rows, group, countries, states)
            cases.append(
                dict(
                    input_rows=len(rows),
                    group=group,
                    mapped_groups=len(totals),
                    mapped_revenue=str(sum(totals.values(), Decimal(0))),
                    unlocated_revenue=str(omitted),
                    aggregation_proxy=measure(
                        lambda: aggregate_proxy(rows, group, countries, states),
                        repetitions,
                    ),
                    figure_end_to_end_warm_boundary=measure(
                        lambda: revenue_map(rows, group), repetitions
                    ),
                    serialization=measure(figure.to_json, repetitions),
                    payload_utf8_bytes=len(figure.to_json().encode("utf-8")),
                )
            )
    boundary_path = ROOT / "my-dash-app/map_data/customer_boundaries.json"
    return dict(
        methodology="perf_counter_ns wall-clock samples; separate tracemalloc peak sample; see docs/performance-benchmark.md",
        python=platform.python_version(),
        platform=platform.platform(),
        versions={
            name: importlib.metadata.version(name)
            for name in ("plotly", "dash", "pyarrow")
        },
        boundary_sha256=hashlib.sha256(boundary_path.read_bytes()).hexdigest(),
        boundary_countries=len(data["countries"]),
        boundary_states=len(data["states"]),
        repetitions=repetitions,
        phases=results,
        cases=cases,
        checks="Decimal currency, historical aliases, empty/all-unlocated selections passed",
    )


def measure_elt(row_counts: list[int], batch_size: int, repetitions: int) -> dict:
    """Exercise the pure E helper only; never construct database/cloud clients."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    import elt_staging
    from elt_staging import validate_batch_size, write_parquet_batches

    validate_batch_size(batch_size)
    schema = pa.schema(
        [("id", pa.int64()), ("label", pa.string()), ("amount", pa.float64())]
    )

    class SyntheticResult:
        def __init__(self, count):
            self.remaining = count
            self.position = 0
            self.max_fetch = 0

        def fetchmany(self, requested):
            if requested > batch_size:
                raise AssertionError("Oversized extraction request")
            self.max_fetch = max(self.max_fetch, requested)
            end = self.position + min(requested, self.remaining)
            rows = [
                SimpleNamespace(
                    _mapping=dict(
                        id=index, label=f"row-{index:010d}", amount=Decimal("100.01")
                    )
                )
                for index in range(self.position, end)
            ]
            self.remaining -= len(rows)
            self.position = end
            return rows

    cases = []
    with tempfile.TemporaryDirectory(prefix="performance-offline-") as directory:
        path = Path(directory) / "spool.parquet"
        for count in row_counts:

            def stage():
                result = SyntheticResult(count)
                if write_parquet_batches(result, schema, path, batch_size) != count:
                    raise AssertionError("Staging lost source rows")
                metadata = pq.read_metadata(path)
                if metadata.num_rows != count:
                    raise AssertionError("Parquet metadata row count mismatch")

            metrics = measure(stage, repetitions)
            # tracemalloc cannot observe native Arrow buffers. Sample their own
            # allocator peak separately; this is still not whole-process RSS.
            previous_pool = pa.default_memory_pool()
            proxy_pool = pa.proxy_memory_pool(previous_pool)
            try:
                pa.set_memory_pool(proxy_pool)
                stage()
                arrow_peak = proxy_pool.max_memory()
            finally:
                pa.set_memory_pool(previous_pool)
            cases.append(
                dict(
                    rows=count,
                    batch_size=batch_size,
                    measurements=metrics,
                    arrow_allocator_peak_bytes=arrow_peak,
                    spool_bytes=path.stat().st_size,
                )
            )
    return dict(
        helper_sha256=hashlib.sha256(
            Path(elt_staging.__file__).read_bytes()
        ).hexdigest(),
        schema=str(schema),
        cases=cases,
        limitations="Synthetic fetchmany only; excludes PostgreSQL driver, SQL reflection, full RSS and BigQuery load; Parquet metadata grows with row-group count.",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[100, 500, 2000])
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument(
        "--elt-memory",
        action="store_true",
        help="also measure the pure elt_staging helper after track E is integrated",
    )
    parser.add_argument(
        "--elt-rows", type=int, nargs="+", default=[10000, 100000, 1000000]
    )
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()
    if not args.sizes or any(size < 1 or size > 2000 for size in args.sizes):
        parser.error("sizes must each be between 1 and the 2,000-group loader limit")
    if args.repetitions < 1 or args.repetitions > 100:
        parser.error("repetitions must be between 1 and 100")
    if any(count < 1 for count in args.elt_rows):
        parser.error("ELT row counts must be positive")
    result = run(args.sizes, args.repetitions)
    if args.elt_memory:
        result["elt_staging"] = measure_elt(
            args.elt_rows, args.batch_size, args.repetitions
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
