import dash
from analytics import REPORTS, report_layout, register_report_callbacks

dash.register_page(
    __name__,
    path="/dashboard/executive",
    title=REPORTS["executive"][0] + " | AdventureWorks",
)


def layout():
    return report_layout("executive")


register_report_callbacks("executive")
