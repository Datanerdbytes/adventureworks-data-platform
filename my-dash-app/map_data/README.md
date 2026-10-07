# Customer map boundaries

`customer_boundaries.json` is a simplified subset of Natural Earth admin-0
countries and admin-1 states/provinces, covering the six customer countries.
England combines Natural Earth's constituent features identified by geonunit.
France uses departments, matching the warehouse's legacy state/province field.
Name matching is country-qualified, accent/punctuation-insensitive, with explicit
aliases for Garonne (Haute), Seine (Paris), and Yveline. Unmatched revenue is
reported rather than assigned to an invented location.

Source: https://github.com/nvkelso/natural-earth-vector/tree/master/geojson
Files: ne_110m_admin_0_countries.geojson, ne_10m_admin_1_states_provinces.geojson
Retrieved: 2026-10-07. Natural Earth data is public domain:
https://www.naturalearthdata.com/about/terms-of-use/
Rebuild using scripts/build_customer_boundaries.py and downloaded source files.

The bundled assets/geo/world_110m.json comes from
https://cdn.plot.ly/world_110m.json (Plotly's Natural Earth-derived base geography).
It is served locally to avoid runtime external map requests.
