from datetime import date, datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, session

import auth
import db
import id_generator
import inventory_closing
from excel.exporters import export_document

bp = Blueprint("outbound", __name__)

STATUS_LABELS = {"PENDING": "🟡 待審核", "APPROVED": "🟢 已核准", "REJECTED": "🔴 已拒絕"}


def _products():
    return db.query("SELECT ProductId, ProductName FROM dbo.Product ORDER BY ProductId")


def _employees():
    return db.query("SELECT EmployeeId, EmployeeName FROM dbo.Employee ORDER BY EmployeeId")


def _warehouses():
    return db.query("SELECT WarehouseId, WarehouseName FROM dbo.Warehouse ORDER BY WarehouseId")


def _doctypes():
    return db.query("SELECT DocTypeId, DocTypeName FROM dbo.DocType WHERE Direction = 'OUT' ORDER BY DocTypeId")


def _customers():
    return db.query("SELECT CustomerId, CustomerName FROM dbo.Customer ORDER BY CustomerId")


def _parse_lines(form, product_map):
    lines = []
    for pid, qty in zip(form.getlist("product_id[]"), form.getlist("quantity[]")):
        pid = (pid or "").strip()
        if not pid or pid not in product_map:
            continue
        try:
            qty_val = float(qty)
        except (TypeError, ValueError):
            continue
        if qty_val <= 0:
            continue
        lines.append((pid, product_map[pid], qty_val))
    return lines


def _stock_shortfall_warnings(lines, warehouse_id):
    """Non-blocking check against the warehouse's *current* (pre-save)
    balance — an advisory warning, not an enforced rule (backorders are
    tolerated), so it doesn't try to net out an edit's own prior line."""
    warnings = []
    for pid, pname, qty in lines:
        row = db.query_one(
            "SELECT StockBalance FROM dbo.ProductWarehouseStock WHERE ProductId = %s AND WarehouseId = %s",
            (pid, warehouse_id),
        )
        available = float(row["StockBalance"]) if row else 0.0
        if qty > available:
            warnings.append(f"{pname}(需求 {qty:g},現有庫存 {available:g})")
    return warnings


@bp.route("/")
def list_view():
    headers = db.query("""
        SELECT h.OutboundId, h.OutboundDate, h.EmployeeId, e.EmployeeName,
               w.WarehouseName, dt.DocTypeName, c.CustomerName, h.Status,
               (SELECT COUNT(*) FROM dbo.OutboundDetail d WHERE d.OutboundId = h.OutboundId) AS LineCount
        FROM dbo.OutboundHeader h
        JOIN dbo.Employee e ON e.EmployeeId = h.EmployeeId
        JOIN dbo.Warehouse w ON w.WarehouseId = h.WarehouseId
        JOIN dbo.DocType dt ON dt.DocTypeId = h.DocTypeId
        LEFT JOIN dbo.Customer c ON c.CustomerId = h.CustomerId
        ORDER BY h.OutboundDate DESC, h.OutboundId DESC
    """)
    return render_template("outbound/list.html", headers=headers, status_labels=STATUS_LABELS)


@bp.route("/pending")
def pending_view():
    headers = db.query("""
        SELECT h.OutboundId, h.OutboundDate, h.EmployeeId, e.EmployeeName,
               w.WarehouseName, dt.DocTypeName, c.CustomerName,
               (SELECT COUNT(*) FROM dbo.OutboundDetail d WHERE d.OutboundId = h.OutboundId) AS LineCount
        FROM dbo.OutboundHeader h
        JOIN dbo.Employee e ON e.EmployeeId = h.EmployeeId
        JOIN dbo.Warehouse w ON w.WarehouseId = h.WarehouseId
        JOIN dbo.DocType dt ON dt.DocTypeId = h.DocTypeId
        LEFT JOIN dbo.Customer c ON c.CustomerId = h.CustomerId
        WHERE h.Status = 'PENDING'
        ORDER BY h.OutboundDate, h.OutboundId
    """)
    return render_template("outbound/pending.html", headers=headers)


@bp.route("/new", methods=["GET", "POST"])
def create_view():
    products = _products()
    employees = _employees()
    warehouses = _warehouses()
    doctypes = _doctypes()
    customers = _customers()
    product_map = {p["ProductId"]: p["ProductName"] for p in products}

    if request.method == "POST":
        outbound_date = request.form.get("outbound_date") or date.today().isoformat()
        employee_id = request.form.get("employee_id", "")
        warehouse_id = request.form.get("warehouse_id", "")
        doctype_id = request.form.get("doctype_id", "")
        customer_id = request.form.get("customer_id") or None
        lines = _parse_lines(request.form, product_map)
        form_values = {"outbound_date": outbound_date, "employee_id": employee_id,
                       "warehouse_id": warehouse_id, "doctype_id": doctype_id, "customer_id": customer_id or ""}

        if not employee_id or not warehouse_id or not doctype_id or not lines:
            flash("請選擇員工、倉別與單別,且至少需要一筆明細(數量需大於 0)", "error")
            return render_template("outbound/form.html", header=None, lines=[],
                                    products=products, employees=employees,
                                    warehouses=warehouses, doctypes=doctypes, customers=customers,
                                    form_values=form_values)

        stock_warnings = _stock_shortfall_warnings(lines, warehouse_id)

        def insert(new_id):
            with db.transaction() as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO dbo.OutboundHeader "
                    "(OutboundId, OutboundDate, EmployeeId, WarehouseId, DocTypeId, CustomerId, Status) "
                    "VALUES (%s, %s, %s, %s, %s, %s, 'PENDING')",
                    (new_id, outbound_date, employee_id, warehouse_id, doctype_id, customer_id),
                )
                for line_num, (pid, pname, qty) in enumerate(lines, start=1):
                    cur.execute(
                        "INSERT INTO dbo.OutboundDetail (OutboundId, LineNum, ProductId, ProductName, Quantity) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (new_id, line_num, pid, pname, qty),
                    )
                for pid in {pid for pid, _, _ in lines}:
                    inventory_closing.recalculate(pid, warehouse_id)

        new_id = id_generator.generate_with_retry(id_generator.next_outbound_id, insert)
        flash(f"已新增出庫單 {new_id},狀態為「待審核」,主管核准後才會影響庫存", "success")
        if stock_warnings:
            flash("⚠️ 核准時若庫存不足會超賣:" + "、".join(stock_warnings), "warning")
        return redirect(url_for("outbound.detail_view", outbound_id=new_id))

    return render_template("outbound/form.html", header=None, lines=[],
                            products=products, employees=employees,
                            warehouses=warehouses, doctypes=doctypes, customers=customers,
                            form_values={"outbound_date": date.today().isoformat(), "employee_id": "",
                                         "warehouse_id": "", "doctype_id": "", "customer_id": ""})


@bp.route("/<outbound_id>/edit", methods=["GET", "POST"])
def edit_view(outbound_id):
    header = db.query_one("SELECT * FROM dbo.OutboundHeader WHERE OutboundId = %s", (outbound_id,))
    if not header:
        flash("找不到該出庫單", "error")
        return redirect(url_for("outbound.list_view"))

    products = _products()
    employees = _employees()
    warehouses = _warehouses()
    doctypes = _doctypes()
    customers = _customers()
    product_map = {p["ProductId"]: p["ProductName"] for p in products}

    if request.method == "POST":
        outbound_date = request.form.get("outbound_date") or header["OutboundDate"]
        employee_id = request.form.get("employee_id", "")
        warehouse_id = request.form.get("warehouse_id", "")
        doctype_id = request.form.get("doctype_id", "")
        customer_id = request.form.get("customer_id") or None
        lines = _parse_lines(request.form, product_map)
        existing_lines = db.query(
            "SELECT ProductId, Quantity FROM dbo.OutboundDetail WHERE OutboundId = %s ORDER BY LineNum",
            (outbound_id,),
        )
        old_warehouse_id = header["WarehouseId"]
        form_values = {"outbound_date": outbound_date, "employee_id": employee_id,
                       "warehouse_id": warehouse_id, "doctype_id": doctype_id, "customer_id": customer_id or ""}

        if not employee_id or not warehouse_id or not doctype_id or not lines:
            flash("請選擇員工、倉別與單別,且至少需要一筆明細(數量需大於 0)", "error")
            return render_template("outbound/form.html", header=header,
                                    lines=[{"ProductId": p, "Quantity": q} for p, q in
                                           zip(request.form.getlist("product_id[]"), request.form.getlist("quantity[]"))],
                                    products=products, employees=employees,
                                    warehouses=warehouses, doctypes=doctypes, customers=customers,
                                    form_values=form_values)

        stock_warnings = _stock_shortfall_warnings(lines, warehouse_id)
        was_approved = header["Status"] == "APPROVED"

        with db.transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE dbo.OutboundHeader SET OutboundDate = %s, EmployeeId = %s, WarehouseId = %s, "
                "DocTypeId = %s, CustomerId = %s, Status = 'PENDING', ApprovedBy = NULL, ApprovedAt = NULL "
                "WHERE OutboundId = %s",
                (outbound_date, employee_id, warehouse_id, doctype_id, customer_id, outbound_id),
            )
            cur.execute("DELETE FROM dbo.OutboundDetail WHERE OutboundId = %s", (outbound_id,))
            for line_num, (pid, pname, qty) in enumerate(lines, start=1):
                cur.execute(
                    "INSERT INTO dbo.OutboundDetail (OutboundId, LineNum, ProductId, ProductName, Quantity) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (outbound_id, line_num, pid, pname, qty),
                )
            affected_products = {r["ProductId"] for r in existing_lines} | {pid for pid, _, _ in lines}
            affected_warehouses = {old_warehouse_id, warehouse_id}
            for pid in affected_products:
                for wid in affected_warehouses:
                    inventory_closing.recalculate(pid, wid)
        if was_approved:
            flash("已更新出庫單 — 原本已核准,修改後打回「待審核」,庫存已還原,需重新審核", "success")
        else:
            flash("已更新出庫單", "success")
        if stock_warnings:
            flash("⚠️ 核准時若庫存不足會超賣:" + "、".join(stock_warnings), "warning")
        return redirect(url_for("outbound.detail_view", outbound_id=outbound_id))

    lines = db.query(
        "SELECT * FROM dbo.OutboundDetail WHERE OutboundId = %s ORDER BY LineNum", (outbound_id,)
    )
    return render_template("outbound/form.html", header=header, lines=lines,
                            products=products, employees=employees,
                            warehouses=warehouses, doctypes=doctypes, customers=customers,
                            form_values={"outbound_date": str(header["OutboundDate"]), "employee_id": header["EmployeeId"],
                                         "warehouse_id": header["WarehouseId"], "doctype_id": header["DocTypeId"],
                                         "customer_id": header["CustomerId"] or ""})


@bp.route("/<outbound_id>/delete", methods=["POST"])
def delete_view(outbound_id):
    header = db.query_one("SELECT WarehouseId FROM dbo.OutboundHeader WHERE OutboundId = %s", (outbound_id,))
    affected_products = {r["ProductId"] for r in db.query(
        "SELECT DISTINCT ProductId FROM dbo.OutboundDetail WHERE OutboundId = %s", (outbound_id,)
    )}
    with db.transaction() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.OutboundDetail WHERE OutboundId = %s", (outbound_id,))
        cur.execute("DELETE FROM dbo.OutboundHeader WHERE OutboundId = %s", (outbound_id,))
        if header:
            for pid in affected_products:
                inventory_closing.recalculate(pid, header["WarehouseId"])
    flash("已刪除出庫單", "success")
    return redirect(url_for("outbound.list_view"))


@bp.route("/<outbound_id>/approve", methods=["POST"])
@auth.manager_required
def approve_view(outbound_id):
    header = db.query_one("SELECT * FROM dbo.OutboundHeader WHERE OutboundId = %s", (outbound_id,))
    if not header:
        flash("找不到該出庫單", "error")
        return redirect(url_for("outbound.pending_view"))

    lines = db.query(
        "SELECT ProductId, ProductName, Quantity FROM dbo.OutboundDetail WHERE OutboundId = %s",
        (outbound_id,),
    )
    stock_warnings = _stock_shortfall_warnings(
        [(r["ProductId"], r["ProductName"], float(r["Quantity"])) for r in lines],
        header["WarehouseId"],
    )

    with db.transaction() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.OutboundHeader SET Status = 'APPROVED', ApprovedBy = %s, ApprovedAt = %s "
            "WHERE OutboundId = %s",
            (session["user"], datetime.now(), outbound_id),
        )
        for r in lines:
            inventory_closing.recalculate(r["ProductId"], header["WarehouseId"])

    flash(f"已核准出庫單 {outbound_id},庫存已更新", "success")
    if stock_warnings:
        flash("⚠️ 庫存不足,已超賣:" + "、".join(stock_warnings), "warning")
    return redirect(url_for("outbound.pending_view"))


@bp.route("/<outbound_id>/reject", methods=["POST"])
@auth.manager_required
def reject_view(outbound_id):
    header = db.query_one("SELECT WarehouseId FROM dbo.OutboundHeader WHERE OutboundId = %s", (outbound_id,))
    if not header:
        flash("找不到該出庫單", "error")
        return redirect(url_for("outbound.pending_view"))

    affected_products = {r["ProductId"] for r in db.query(
        "SELECT DISTINCT ProductId FROM dbo.OutboundDetail WHERE OutboundId = %s", (outbound_id,)
    )}
    with db.transaction() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.OutboundHeader SET Status = 'REJECTED', ApprovedBy = %s, ApprovedAt = %s "
            "WHERE OutboundId = %s",
            (session["user"], datetime.now(), outbound_id),
        )
        for pid in affected_products:
            inventory_closing.recalculate(pid, header["WarehouseId"])

    flash(f"已拒絕出庫單 {outbound_id}(單據保留供之後編輯重新送審)", "success")
    return redirect(url_for("outbound.pending_view"))


@bp.route("/<outbound_id>")
def detail_view(outbound_id):
    header = db.query_one("""
        SELECT h.*, e.EmployeeName, w.WarehouseName, dt.DocTypeName, c.CustomerName
        FROM dbo.OutboundHeader h
        JOIN dbo.Employee e ON e.EmployeeId = h.EmployeeId
        JOIN dbo.Warehouse w ON w.WarehouseId = h.WarehouseId
        JOIN dbo.DocType dt ON dt.DocTypeId = h.DocTypeId
        LEFT JOIN dbo.Customer c ON c.CustomerId = h.CustomerId
        WHERE h.OutboundId = %s
    """, (outbound_id,))
    if not header:
        flash("找不到該出庫單", "error")
        return redirect(url_for("outbound.list_view"))
    lines = db.query(
        "SELECT * FROM dbo.OutboundDetail WHERE OutboundId = %s ORDER BY LineNum", (outbound_id,)
    )
    return render_template("outbound/detail.html", header=header, lines=lines, status_labels=STATUS_LABELS)


@bp.route("/<outbound_id>/export")
def export_view(outbound_id):
    header = db.query_one("""
        SELECT h.*, e.EmployeeName, w.WarehouseName, dt.DocTypeName, c.CustomerName
        FROM dbo.OutboundHeader h
        JOIN dbo.Employee e ON e.EmployeeId = h.EmployeeId
        JOIN dbo.Warehouse w ON w.WarehouseId = h.WarehouseId
        JOIN dbo.DocType dt ON dt.DocTypeId = h.DocTypeId
        LEFT JOIN dbo.Customer c ON c.CustomerId = h.CustomerId
        WHERE h.OutboundId = %s
    """, (outbound_id,))
    if not header:
        flash("找不到該出庫單", "error")
        return redirect(url_for("outbound.list_view"))
    lines = db.query(
        "SELECT * FROM dbo.OutboundDetail WHERE OutboundId = %s ORDER BY LineNum", (outbound_id,)
    )
    buf = export_document(
        title=f"出庫單 {outbound_id}",
        header_fields=[("出庫單號", "OutboundId"), ("出庫日期", "OutboundDate"),
                        ("經手員工", "EmployeeName"), ("倉別", "WarehouseName"),
                        ("單別", "DocTypeName"), ("客戶", "CustomerName")],
        header_data=header,
        line_columns=[("行號", "LineNum"), ("物料編號", "ProductId"),
                       ("物料名稱", "ProductName"), ("數量", "Quantity")],
        lines=lines,
    )
    return send_file(buf, as_attachment=True, download_name=f"{outbound_id}.xlsx",
                      mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
