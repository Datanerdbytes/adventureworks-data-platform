"""Shared visual tokens for CSS and Plotly."""

from pathlib import Path

TOKENS = {
    "background": "#F5F7FA",
    "surface": "#FFFFFF",
    "text": "#243B45",
    "muted": "#596B78",
    "primary": "#2274B5",
    "teal": "#138579",
    "border": "#DFE6ED",
    "surface-raised": "#FFFFFF",
    "surface-overlay": "#FFFFFF",
    "control-border": "#8193a1",
    "on-primary": "#FFFFFF",
    "font": "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
    "space": "8px",
    "radius": "8px",
}

DARK_TOKENS = {
    "background": "#0c1222",
    "surface": "#121a2e",
    "text": "#f1f5f9",
    "muted": "#94a3b8",
    "primary": "#60a5fa",
    "teal": "#2dd4bf",
    "border": "#334155",
    "surface-raised": "#192339",
    "surface-overlay": "#22304a",
    "control-border": "#71839b",
    "on-primary": "#0c1222",
    "font": "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
    "space": "8px",
    "radius": "8px",
}


def css_tokens():
    light = (
        ":root{" + ";".join(f"--{key}:{value}" for key, value in TOKENS.items()) + "}"
    )
    dark = (
        ":root.theme-dark{"
        + ";".join(f"--{key}:{value}" for key, value in DARK_TOKENS.items())
        + "}"
    )
    return light + dark + ":root{color-scheme:light}:root.theme-dark{color-scheme:dark}"


def theme_script():
    """Share the pre-paint preference script with Flask templates and Dash."""
    return (Path(__file__).parent / "templates" / "theme-script.html").read_text()


def style_figure(figure, dark=False):
    tokens = DARK_TOKENS if dark else TOKENS
    figure.update_layout(
        template="plotly_white" if not dark else "plotly_dark",
        paper_bgcolor=tokens["surface"],
        plot_bgcolor=tokens["surface"],
        font={"family": tokens["font"], "color": tokens["muted"]},
        margin={"l": 40, "r": 20, "t": 25, "b": 40},
        legend={"orientation": "h", "y": 1.15, "title": None},
        hovermode="x unified",
        autosize=True,
    )
    figure.update_xaxes(gridcolor=tokens["border"], title=None)
    figure.update_yaxes(gridcolor=tokens["border"])
    return figure
