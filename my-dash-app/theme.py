"""Shared visual tokens for CSS and Plotly."""

TOKENS = {
    "background": "#F5F7FA",
    "surface": "#FFFFFF",
    "text": "#243B45",
    "muted": "#596B78",
    "primary": "#2274B5",
    "teal": "#138579",
    "border": "#DFE6ED",
    "font": "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
    "space": "8px",
    "radius": "8px",
}


def css_tokens():
    return (
        ":root{" + ";".join(f"--{key}:{value}" for key, value in TOKENS.items()) + "}"
    )


def style_figure(figure):
    figure.update_layout(
        template="plotly_white",
        paper_bgcolor=TOKENS["surface"],
        plot_bgcolor=TOKENS["surface"],
        font={"family": TOKENS["font"], "color": TOKENS["muted"]},
        margin={"l": 40, "r": 20, "t": 25, "b": 40},
        legend={"orientation": "h", "y": 1.15, "title": None},
        hovermode="x unified",
        autosize=True,
    )
    figure.update_xaxes(gridcolor=TOKENS["border"], title=None)
    figure.update_yaxes(gridcolor=TOKENS["border"])
    return figure
