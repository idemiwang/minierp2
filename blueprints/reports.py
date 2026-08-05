from flask import Blueprint, render_template, request, send_file

import db
from excel.exporters import export_table, export_workbook

bp = Blueprint("reports", __name__)


def _header_rows(args):
    conditions, params = [], []
    if args.get("date_from"):
        conditions.append("InboundDate >= %s")
        params.append(args["date_from"])
    if args.get("date_to"):
        conditions.append("InboundDate <= %s")
        params.append(args["date_to"])
    if args.get("employee_id"):
        conditions.append("EmployeeId = %s")
        params.append(args["employee_id"])
    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return db.query(
        f"SELECT * FROM dbo.v_inoutheader {where_clause} ORDER BY InboundDate DESC",
        tuple(params),
    )


def _detail_rows(args):
    conditions, params = [], []
    if args.get("product_id"):
        conditions.append("ProductId = %s")
        params.append(args["product_id"])
    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return db.query(
        f"SELECT * FROM dbo.v_inoutdetail {where_clause} ORDER BY InboundId, LineNum",
        tuple(params),
    )


def _closing_rows(args):
    conditions, params = [], []
    if args.get("product_id"):
        conditions.append("c.ProductId = %s")
        params.append(args["product_id"])
    if args.get("date_from"):
        conditions.append("c.ClosingDate >= %s")
        params.append(args["date_from"])
    if args.get("date_to"):
        conditions.append("c.ClosingDate <= %s")
        params.append(args["date_to"])
    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return db.query(f"""
        SELECT c.ClosingDate, c.ProductId, p.ProductName,
               c.OpeningQuantity, c.InboundQuantity, c.OutboundQuantity, c.ClosingQuantity
        FROM dbo.InventoryDailyClosing c
        JOIN dbo.Product p ON p.ProductId = c.ProductId
        {where_clause}
        ORDER BY c.ProductId, c.ClosingDate
    """, tuple(params))


@bp.route("/header")
def header_view():
    filters = {
        "date_from": request.args.get("date_from", ""),
        "date_to": request.args.get("date_to", ""),
        "employee_id": request.args.get("employee_id", ""),
    }
    rows = _header_rows(filters)
    employees = db.query("SELECT EmployeeId, EmployeeName FROM dbo.Employee ORDER BY EmployeeId")
    return render_template("reports/header.html", rows=rows, employees=employees, filters=filters)


@bp.route("/header/export")
def header_export():
    filters = {
        "date_from": request.args.get("date_from", ""),
        "date_to": request.args.get("date_to", ""),
        "employee_id": request.args.get("employee_id", ""),
    }
    rows = _header_rows(filters)
    buf = export_table(
        title="入出單據查詢結果",
        columns=[("單據編號", "InboundId"), ("日期", "InboundDate"), ("員工編號", "EmployeeId")],
        rows=rows,
    )
    return send_file(buf, as_attachment=True, download_name="inout_header.xlsx",
                      mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@bp.route("/detail")
def detail_view():
    filters = {"product_id": request.args.get("product_id", "")}
    rows = _detail_rows(filters)
    products = db.query("SELECT ProductId, ProductName FROM dbo.Product ORDER BY ProductId")
    return render_template("reports/detail.html", rows=rows, products=products, filters=filters)


@bp.route("/detail/export")
def detail_export():
    filters = {"product_id": request.args.get("product_id", "")}
    rows = _detail_rows(filters)
    buf = export_table(
        title="入出明細查詢結果",
        columns=[("單據編號", "InboundId"), ("行號", "LineNum"), ("物料編號", "ProductId"),
                  ("物料名稱", "ProductName"), ("數量", "Quantity")],
        rows=rows,
    )
    return send_file(buf, as_attachment=True, download_name="inout_detail.xlsx",
                      mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@bp.route("/closing")
def closing_view():
    filters = {
        "product_id": request.args.get("product_id", ""),
        "date_from": request.args.get("date_from", ""),
        "date_to": request.args.get("date_to", ""),
    }
    rows = _closing_rows(filters)
    products = db.query("SELECT ProductId, ProductName FROM dbo.Product ORDER BY ProductId")
    return render_template("reports/closing.html", rows=rows, products=products, filters=filters)


@bp.route("/closing/export")
def closing_export():
    filters = {
        "product_id": request.args.get("product_id", ""),
        "date_from": request.args.get("date_from", ""),
        "date_to": request.args.get("date_to", ""),
    }
    rows = _closing_rows(filters)
    buf = export_table(
        title="日結餘額表",
        columns=[("日期", "ClosingDate"), ("物料編號", "ProductId"), ("物料名稱", "ProductName"),
                  ("期初數量", "OpeningQuantity"), ("入庫數量", "InboundQuantity"),
                  ("出庫數量", "OutboundQuantity"), ("期末數量", "ClosingQuantity")],
        rows=rows,
    )
    return send_file(buf, as_attachment=True, download_name="inventory_daily_closing.xlsx",
                      mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@bp.route("/backup")
def backup_view():
    counts = {
        "Product": db.query_one("SELECT COUNT(*) AS c FROM dbo.Product")["c"],
        "Employee": db.query_one("SELECT COUNT(*) AS c FROM dbo.Employee")["c"],
        "InboundHeader": db.query_one("SELECT COUNT(*) AS c FROM dbo.InboundHeader")["c"],
        "OutboundHeader": db.query_one("SELECT COUNT(*) AS c FROM dbo.OutboundHeader")["c"],
        "InventoryDailyClosing": db.query_one("SELECT COUNT(*) AS c FROM dbo.InventoryDailyClosing")["c"],
    }
    return render_template("reports/backup.html", counts=counts)


@bp.route("/backup/export")
def backup_export():
    sheets = [
        ("Product",
         [("物料編號", "ProductId"), ("物料名稱", "ProductName"), ("庫存餘額", "StockBalance")],
         db.query("SELECT * FROM dbo.Product ORDER BY ProductId")),
        ("Employee",
         [("員工編號", "EmployeeId"), ("姓名", "EmployeeName"), ("Email", "Email")],
         db.query("SELECT * FROM dbo.Employee ORDER BY EmployeeId")),
        ("InboundHeader",
         [("入庫單號", "InboundId"), ("日期", "InboundDate"), ("員工編號", "EmployeeId")],
         db.query("SELECT * FROM dbo.InboundHeader ORDER BY InboundId")),
        ("InboundDetail",
         [("入庫單號", "InboundId"), ("行號", "LineNum"), ("物料編號", "ProductId"),
          ("物料名稱", "ProductName"), ("數量", "Quantity")],
         db.query("SELECT * FROM dbo.InboundDetail ORDER BY InboundId, LineNum")),
        ("OutboundHeader",
         [("出庫單號", "OutboundId"), ("日期", "OutboundDate"), ("員工編號", "EmployeeId")],
         db.query("SELECT * FROM dbo.OutboundHeader ORDER BY OutboundId")),
        ("OutboundDetail",
         [("出庫單號", "OutboundId"), ("行號", "LineNum"), ("物料編號", "ProductId"),
          ("物料名稱", "ProductName"), ("數量", "Quantity")],
         db.query("SELECT * FROM dbo.OutboundDetail ORDER BY OutboundId, LineNum")),
        ("InventoryDailyClosing",
         [("日期", "ClosingDate"), ("物料編號", "ProductId"), ("期初數量", "OpeningQuantity"),
          ("入庫數量", "InboundQuantity"), ("出庫數量", "OutboundQuantity"), ("期末數量", "ClosingQuantity")],
         db.query("SELECT * FROM dbo.InventoryDailyClosing ORDER BY ProductId, ClosingDate")),
    ]
    buf = export_workbook(sheets)
    return send_file(buf, as_attachment=True, download_name="minierp2_backup.xlsx",
                      mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
