import dash
from analytics import REPORTS, report_layout, register_report_callbacks

dash.register_page(
    __name__, path="/dashboard/growth", title=REPORTS["growth"][0] + " | AdventureWorks"
)


def layout():
    return report_layout("growth")


register_report_callbacks("growth")
