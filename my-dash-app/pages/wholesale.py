import dash
from analytics import REPORTS, report_layout, register_report_callbacks

dash.register_page(
    __name__,
    path="/dashboard/wholesale",
    title=REPORTS["wholesale"][0] + " | AdventureWorks",
)


def layout():
    return report_layout("wholesale")


register_report_callbacks("wholesale")
