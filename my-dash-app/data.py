"""Small deterministic fixtures. No credentials, I/O, or production connections."""

from datetime import datetime, timedelta
import pandas as pd

PIPELINES = ("Postgres ingestion", "dbt transformation", "Quality checks")


def runs(pipeline="All pipelines", days=7):
    days = int(days) if str(days) in {"1", "7", "30"} else 7
    rows = []
    for day in range(days):
        for index, name in enumerate(PIPELINES):
            if pipeline not in ("All pipelines", name):
                continue
            stamp = datetime(2026, 9, 30, 8 + index) - timedelta(days=day)
            rows.append(
                {
                    "Run": f"RUN-{1042-day*3-index}",
                    "Pipeline": name,
                    "Started": stamp.strftime("%Y-%m-%d %H:%M"),
                    "Duration (s)": 38 + index * 21 + (day * 13 % 43),
                    "Status": "Warning" if day % 9 == 4 and index == 2 else "Success",
                }
            )
    return rows


def activity():
    return pd.DataFrame(
        [
            {
                "Hour": f"{hour:02d}:00",
                "Pipeline": name,
                "Rows processed": 1600
                + (hour * 173 + i * 823) % 2700
                + (3200 if hour in (8, 12, 16) else 0),
            }
            for hour in range(24)
            for i, name in enumerate(PIPELINES[:2])
        ]
    )


def table_rows(name):
    if name == "Products":
        return [
            {
                "Product ID": 100 + i,
                "Product": f"{['Road Bike', 'Mountain Bike', 'Touring Helmet', 'Cycling Jersey'][i % 4]} {i+1}",
                "Category": ["Bikes", "Bikes", "Accessories", "Clothing"][i % 4],
                "Unit price": round(49.5 + (i * 137) % 2200, 2),
                "Available": i % 7 != 0,
            }
            for i in range(48)
        ]
    if name == "Customers":
        return [
            {
                "Customer ID": 1000 + i,
                "Customer": f"Sample customer {i+1:02}",
                "Territory": ["North America", "Europe", "Pacific"][i % 3],
                "Orders": 2 + i % 19,
            }
            for i in range(36)
        ]
    if name == "Sales":
        return [
            {
                "Order ID": f"SO-{5000+i}",
                "Date": f"2026-09-{i % 28+1:02}",
                "Channel": ["Internet", "Reseller"][i % 2],
                "Revenue": round(180 + i * 37.25, 2),
            }
            for i in range(64)
        ]
    return []


def grid_options(page_size=10, search=""):
    size = page_size if page_size in (10, 20, 50) else 10
    return {
        "theme": "themeBalham",
        "animateRows": True,
        "pagination": True,
        "paginationPageSize": size,
        "paginationPageSizeSelector": False,
        "quickFilterText": search or "",
        "domLayout": "normal",
        "rowHeight": 44,
    }
