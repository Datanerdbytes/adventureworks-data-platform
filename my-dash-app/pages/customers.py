import dash
from analytics import REPORTS, report_layout, register_report_callbacks

dash.register_page(
    __name__,
    path="/dashboard/customers",
    title=REPORTS["customers"][0] + " | AdventureWorks",
)


def layout():
    return report_layout("customers")


register_report_callbacks("customers")
