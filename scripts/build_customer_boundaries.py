"""Build compact public-domain Natural Earth boundaries from downloaded GeoJSON.
Usage: python scripts/build_customer_boundaries.py admin0.geojson admin1.geojson
Source: https://github.com/nvkelso/natural-earth-vector/tree/master/geojson
"""

import json
import sys
from pathlib import Path

COUNTRIES = {
    "US": "United States",
    "CA": "Canada",
    "AU": "Australia",
    "GB": "United Kingdom",
    "DE": "Germany",
    "FR": "France",
}


def simplify(points, tolerance=0.025):
    if len(points) < 4:
        return points
    start, end = points[0], points[-1]
    dx, dy = end[0] - start[0], end[1] - start[1]
    norm = dx * dx + dy * dy

    def distance(p):
        t = (
            max(0, min(1, ((p[0] - start[0]) * dx + (p[1] - start[1]) * dy) / norm))
            if norm
            else 0
        )
        return (p[0] - start[0] - t * dx) ** 2 + (p[1] - start[1] - t * dy) ** 2

    index = max(range(1, len(points) - 1), key=lambda i: distance(points[i]))
    if distance(points[index]) > tolerance * tolerance:
        return simplify(points[: index + 1], tolerance)[:-1] + simplify(
            points[index:], tolerance
        )
    return [start, end]


def polygons(geometry):
    return (
        geometry["coordinates"]
        if geometry["type"] == "MultiPolygon"
        else [geometry["coordinates"]]
    )


def compact(geometry):
    result = []
    for poly in polygons(geometry):
        rings = []
        for ring in poly:
            reduced = simplify(ring)
            if len(reduced) < 4:
                reduced = ring
            rings.append([[round(x, 3), round(y, 3)] for x, y, *_ in reduced])
        result.append(rings)
    return {"type": "MultiPolygon", "coordinates": result}


def build(admin0, admin1):
    countries = []
    for f in admin0["features"]:
        p = f["properties"]
        code = p.get("ISO_A2_EH") or p.get("ISO_A2")
        if code in COUNTRIES:
            countries.append(
                dict(
                    type="Feature",
                    id=COUNTRIES[code],
                    properties={},
                    geometry=compact(f["geometry"]),
                )
            )
    states = []
    england = []
    for f in admin1["features"]:
        p = f["properties"]
        code = p["iso_a2"]
        if code not in COUNTRIES:
            continue
        if code == "GB":
            if p["geonunit"] == "England":
                england.extend(compact(f["geometry"])["coordinates"])
            continue
        states.append(
            dict(
                type="Feature",
                id=code + ":" + p["name"],
                properties=dict(
                    country=COUNTRIES[code],
                    name=p["name"],
                    aliases=[v for v in [p.get("name_en"), p.get("name_alt")] if v],
                ),
                geometry=compact(f["geometry"]),
            )
        )
    states.append(
        dict(
            type="Feature",
            id="GB:England",
            properties=dict(country="United Kingdom", name="England", aliases=[]),
            geometry=dict(type="MultiPolygon", coordinates=england),
        )
    )
    return dict(countries=countries, states=states)


if __name__ == "__main__":
    result = build(*(json.loads(Path(p).read_text()) for p in sys.argv[1:]))
    target = (
        Path(__file__).resolve().parents[1]
        / "my-dash-app/map_data/customer_boundaries.json"
    )
    target.write_text(json.dumps(result, separators=(",", ":"), ensure_ascii=False))
    print(len(result["countries"]), len(result["states"]), target.stat().st_size)
