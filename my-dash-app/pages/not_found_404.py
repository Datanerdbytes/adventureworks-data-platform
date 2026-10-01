import dash
from dash import dcc, html

dash.register_page(__name__, title="Page not found | AdventureWorks")


def layout():
    return html.Div(
        [
            html.P("404", className="eyebrow"),
            html.H1("Page not found"),
            html.P("This page is not part of the demo workspace."),
            dcc.Link(
                "Return to dashboard →", href="/dashboard", className="button primary"
            ),
        ],
        className="card",
    )
