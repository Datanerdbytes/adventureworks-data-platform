from dash import dcc, html
import dash_ag_grid as dag
from data import grid_options


def icon(name):
    return html.Img(src=f"/assets/icons/{name}.svg", className="icon", alt="")


def heading(title, subtitle, action=None):
    return html.Div(
        [html.Div([html.H1(title), html.P(subtitle, className="muted")]), action],
        className="page-heading",
    )


def card(title, children, extra=None):
    return html.Section(
        [html.Div([html.H2(title), extra], className="card-heading"), *children],
        className="card",
    )


def graph(identifier):
    return dcc.Loading(
        dcc.Graph(
            id=identifier,
            figure={"data": [], "layout": {"template": "plotly_white"}},
            config={"displayModeBar": False, "responsive": True},
            className="chart",
        ),
        type="circle",
    )


def grid(identifier):
    return dcc.Loading(
        dag.AgGrid(
            id=identifier,
            rowData=[],
            columnDefs=[],
            dashGridOptions=grid_options(),
            columnSize="responsiveSizeToFit",
            defaultColDef={
                "filter": True,
                "sortable": True,
                "resizable": True,
                "minWidth": 120,
            },
            className="ag-theme-balham data-grid",
        ),
        type="circle",
    )


def details():
    return html.Dl(
        [
            html.Div([html.Dt(k), html.Dd(v)], className="detail-row")
            for k, v in [
                ("Project", "AdventureWorks"),
                ("Environment", "Local demo"),
                ("Data source", "Synthetic fixtures"),
                ("Sample period", "September 2026"),
                ("Connection", "Offline"),
            ]
        ]
    )


def field(label, child):
    return html.Div([html.Label(label, htmlFor=child.id), child], className="field")


def metric(label, value, note):
    return html.Div(
        [html.Span(label, className="muted"), html.Strong(value), html.Small(note)],
        className="metric",
    )
