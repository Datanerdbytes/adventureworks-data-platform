"""Territory-to-state revenue choropleth with bundled geographic boundaries."""

import json
import re
import unicodedata
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
import plotly.graph_objects as go
from theme import TOKENS, style_figure

OVERVIEW = "__overview__"
ALIASES = {"garonnehaute": "hautegaronne", "seineparis": "paris", "yveline": "yvelines"}


def normalized(value):
    value = "".join(
        c
        for c in unicodedata.normalize("NFKD", value or "")
        if not unicodedata.combining(c)
    )
    key = re.sub("[^a-z0-9]", "", value.lower())
    return ALIASES.get(key, key)


@lru_cache(maxsize=1)
def boundaries():
    return json.loads(
        (Path(__file__).parent / "map_data/customer_boundaries.json").read_text()
    )


def revenue_map(rows, group=OVERVIEW):
    data = boundaries()
    countries = {f["id"]: f for f in data["countries"]}
    states = {}
    for feature in data["states"]:
        p = feature["properties"]
        for name in [p["name"], *p["aliases"]]:
            for alias in name.split("|"):
                states[(p["country"], normalized(alias))] = feature
    features, totals, labels = {}, {}, {}
    omitted = Decimal(0)
    seen_countries = set()
    for row in rows:
        territory = row["territory_group"] or "Unknown"
        if group != OVERVIEW and territory != group:
            continue
        value = Decimal(str(row["revenue"]))
        if group == OVERVIEW:
            country = row["country"]
            if country not in countries:
                omitted += value
                continue
            if territory not in features:
                features[territory] = dict(
                    type="Feature",
                    id=territory,
                    properties={},
                    geometry=dict(type="MultiPolygon", coordinates=[]),
                )
            if (territory, country) not in seen_countries:
                features[territory]["geometry"]["coordinates"].extend(
                    countries[country]["geometry"]["coordinates"]
                )
                seen_countries.add((territory, country))
            key = territory
            labels[key] = territory
        else:
            feature = states.get((row["country"], normalized(row["state"])))
            if feature is None:
                omitted += value
                continue
            key = feature["id"]
            features[key] = feature
            labels[key] = f"{row['state']}, {row['country']}"
        totals[key] = totals.get(key, Decimal(0)) + value
    figure = style_figure(go.Figure())
    if not totals:
        figure.add_annotation(
            text="No mapped revenue matches this selection.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
        )
        return (
            figure,
            f"Unlocated revenue: ${omitted:,.2f}. Reseller and unknown states cannot be placed on the state map.",
        )
    keys = sorted(totals)
    figure.add_trace(
        go.Choropleth(
            geojson=dict(type="FeatureCollection", features=list(features.values())),
            locations=keys,
            z=[float(totals[k]) for k in keys],
            customdata=[
                [labels[k], f"${totals[k]:,.2f}", k if group == OVERVIEW else ""]
                for k in keys
            ],
            colorscale=[[0, "#e7f1f8"], [1, TOKENS["primary"]]],
            marker_line_color=TOKENS["surface"],
            marker_line_width=0.5,
            colorbar=dict(
                title=dict(text="Revenue (USD)", side="top"),
                orientation="h",
                x=0.5,
                xanchor="center",
                y=-0.05,
                yanchor="top",
                len=0.8,
                thickness=12,
                tickprefix="$",
                tickformat="~s",
            ),
            hovertemplate="%{customdata[0]}<br>Revenue: %{customdata[1]}<extra></extra>",
        )
    )
    figure.update_geos(
        visible=False, fitbounds="locations", projection_type="equirectangular"
    )
    if group == OVERVIEW:
        figure.update_geos(
            fitbounds=False, lonaxis_range=[-170, 180], lataxis_range=[-50, 85]
        )
    figure.update_layout(
        autosize=True, margin=dict(l=10, r=10, t=10, b=70), clickmode="event+select"
    )
    top = max(keys, key=lambda k: totals[k])
    note = (
        f"Top territory: {labels[top]} · ${totals[top]:,.2f}"
        if group == OVERVIEW
        else f"Top mapped state/province: {labels[top]} · ${totals[top]:,.2f}"
    )
    if omitted:
        note += f" Unlocated revenue: ${omitted:,.2f} · Included in territory totals."
    return figure, note
