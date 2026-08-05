from datetime import date

from flask import Blueprint, render_template

import db

bp = Blueprint("dashboard", __name__)


def _sales_total(date_from, date_to):
    row = db.query_one("""
        SELECT ISNULL(SUM(od.Quantity * p.UnitPrice), 0) AS Total
        FROM dbo.OutboundHeader oh
        JOIN dbo.OutboundDetail od ON od.OutboundId = oh.OutboundId
        JOIN dbo.Product p ON p.ProductId = od.ProductId
        WHERE oh.OutboundDate >= %s AND oh.OutboundDate <= %s
    """, (date_from, date_to))
    return row["Total"]


@bp.route("/")
def index_view():
    today = date.today()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    counts = {
        "Product": db.query_one("SELECT COUNT(*) AS c FROM dbo.Product")["c"],
        "Employee": db.query_one("SELECT COUNT(*) AS c FROM dbo.Employee")["c"],
        "Customer": db.query_one("SELECT COUNT(*) AS c FROM dbo.Customer")["c"],
        "Vendor": db.query_one("SELECT COUNT(*) AS c FROM dbo.Vendor")["c"],
    }

    month_sales = _sales_total(month_start.isoformat(), today.isoformat())
    year_sales = _sales_total(year_start.isoformat(), today.isoformat())

    low_stock_count = db.query_one(
        "SELECT COUNT(*) AS c FROM dbo.Product WHERE StockBalance <= SafetyStock"
    )["c"]

    top_products = db.query("""
        SELECT TOP 5 p.ProductId, p.ProductName, SUM(od.Quantity) AS TotalQty
        FROM dbo.OutboundDetail od
        JOIN dbo.Product p ON p.ProductId = od.ProductId
        GROUP BY p.ProductId, p.ProductName
        ORDER BY TotalQty DESC
    """)

    return render_template(
        "dashboard/index.html",
        counts=counts,
        month_sales=month_sales,
        year_sales=year_sales,
        low_stock_count=low_stock_count,
        top_products=top_products,
    )
