"""Consistent accessible chart feedback without additional data requests."""

from functools import wraps
from html import unescape
import re

from dash import html
import plotly.graph_objects as go


def status(identifier):
    return html.P(
        id=identifier,
        role="status",
        className="muted chart-status",
        **{"aria-live": "polite", "aria-atomic": "true"},
    )


def feedback(figure, note=""):
    """Promote empty/error plot annotations to the card's accessible status."""
    payload = figure.to_plotly_json() if hasattr(figure, "to_plotly_json") else figure
    payload = payload or {}
    traces = payload.get("data", [])
    has_points = any(
        len(trace.get(key, [])) > 0
        for trace in traces
        for key in ("x", "y", "z", "values", "locations", "lat")
        if trace.get(key) is not None
    )
    if has_points:
        return figure, note or ""
    annotations = payload.get("layout", {}).get("annotations", [])
    annotation = " ".join(
        unescape(re.sub(r"<[^>]+>", " ", item.get("text", ""))).strip()
        for item in annotations
    )
    # Empty states take priority over ordinary interpretation captions.
    state_note = re.search(
        r"^(no |unable|unavailable|waiting|limit:|too many)", note or "", re.I
    )
    message = (note if state_note else annotation) or "No data matches these filters."
    blank = go.Figure(figure or {})
    blank.layout.annotations = ()
    blank.update_layout(xaxis_visible=False, yaxis_visible=False)
    return blank, message


def with_feedback(figure_index, status_index):
    """Normalize callback feedback while preserving titles and other outputs."""

    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            result = list(function(*args, **kwargs))
            result[figure_index], result[status_index] = feedback(
                result[figure_index], result[status_index]
            )
            return tuple(result)

        return wrapped

    return decorate
