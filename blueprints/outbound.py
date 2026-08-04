from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file

import db
import id_generator
from excel.exporters import export_document

bp = Blueprint("outbound", __name__)


def _products():
    return db.query("SELECT ProductId, ProductName FROM dbo.Product ORDER BY ProductId")


def _employees():
    return db.query("SELECT EmployeeId, EmployeeName FROM dbo.Employee ORDER BY EmployeeId")


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


@bp.route("/")
def list_view():
    headers = db.query("""
        SELECT h.OutboundId, h.OutboundDate, h.EmployeeId, e.EmployeeName,
               (SELECT COUNT(*) FROM dbo.OutboundDetail d WHERE d.OutboundId = h.OutboundId) AS LineCount
        FROM dbo.OutboundHeader h
        JOIN dbo.Employee e ON e.EmployeeId = h.EmployeeId
        ORDER BY h.OutboundDate DESC, h.OutboundId DESC
    """)
    return render_template("outbound/list.html", headers=headers)


@bp.route("/new", methods=["GET", "POST"])
def create_view():
    products = _products()
    employees = _employees()
    product_map = {p["ProductId"]: p["ProductName"] for p in products}

    if request.method == "POST":
        outbound_date = request.form.get("outbound_date") or date.today().isoformat()
        employee_id = request.form.get("employee_id", "")
        lines = _parse_lines(request.form, product_map)

        if not employee_id or not lines:
            flash("請選擇員工,且至少需要一筆明細(數量需大於 0)", "error")
            return render_template("outbound/form.html", header=None, lines=[],
                                    products=products, employees=employees,
                                    form_values={"outbound_date": outbound_date, "employee_id": employee_id})

        def insert(new_id):
            with db.transaction() as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO dbo.OutboundHeader (OutboundId, OutboundDate, EmployeeId) VALUES (%s, %s, %s)",
                    (new_id, outbound_date, employee_id),
                )
                for line_num, (pid, pname, qty) in enumerate(lines, start=1):
                    cur.execute(
                        "INSERT INTO dbo.OutboundDetail (OutboundId, LineNum, ProductId, ProductName, Quantity) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (new_id, line_num, pid, pname, qty),
                    )

        new_id = id_generator.generate_with_retry(id_generator.next_outbound_id, insert)
        flash(f"已新增出庫單 {new_id}", "success")
        return redirect(url_for("outbound.detail_view", outbound_id=new_id))

    return render_template("outbound/form.html", header=None, lines=[],
                            products=products, employees=employees,
                            form_values={"outbound_date": date.today().isoformat(), "employee_id": ""})


@bp.route("/<outbound_id>/edit", methods=["GET", "POST"])
def edit_view(outbound_id):
    header = db.query_one("SELECT * FROM dbo.OutboundHeader WHERE OutboundId = %s", (outbound_id,))
    if not header:
        flash("找不到該出庫單", "error")
        return redirect(url_for("outbound.list_view"))

    products = _products()
    employees = _employees()
    product_map = {p["ProductId"]: p["ProductName"] for p in products}

    if request.method == "POST":
        outbound_date = request.form.get("outbound_date") or header["OutboundDate"]
        employee_id = request.form.get("employee_id", "")
        lines = _parse_lines(request.form, product_map)

        if not employee_id or not lines:
            flash("請選擇員工,且至少需要一筆明細(數量需大於 0)", "error")
            return render_template("outbound/form.html", header=header,
                                    lines=[{"ProductId": p, "Quantity": q} for p, q in
                                           zip(request.form.getlist("product_id[]"), request.form.getlist("quantity[]"))],
                                    products=products, employees=employees,
                                    form_values={"outbound_date": outbound_date, "employee_id": employee_id})

        with db.transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE dbo.OutboundHeader SET OutboundDate = %s, EmployeeId = %s WHERE OutboundId = %s",
                (outbound_date, employee_id, outbound_id),
            )
            cur.execute("DELETE FROM dbo.OutboundDetail WHERE OutboundId = %s", (outbound_id,))
            for line_num, (pid, pname, qty) in enumerate(lines, start=1):
                cur.execute(
                    "INSERT INTO dbo.OutboundDetail (OutboundId, LineNum, ProductId, ProductName, Quantity) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (outbound_id, line_num, pid, pname, qty),
                )
        flash("已更新出庫單", "success")
        return redirect(url_for("outbound.detail_view", outbound_id=outbound_id))

    lines = db.query(
        "SELECT * FROM dbo.OutboundDetail WHERE OutboundId = %s ORDER BY LineNum", (outbound_id,)
    )
    return render_template("outbound/form.html", header=header, lines=lines,
                            products=products, employees=employees,
                            form_values={"outbound_date": str(header["OutboundDate"]), "employee_id": header["EmployeeId"]})


@bp.route("/<outbound_id>/delete", methods=["POST"])
def delete_view(outbound_id):
    with db.transaction() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.OutboundDetail WHERE OutboundId = %s", (outbound_id,))
        cur.execute("DELETE FROM dbo.OutboundHeader WHERE OutboundId = %s", (outbound_id,))
    flash("已刪除出庫單", "success")
    return redirect(url_for("outbound.list_view"))


@bp.route("/<outbound_id>")
def detail_view(outbound_id):
    header = db.query_one("""
        SELECT h.*, e.EmployeeName FROM dbo.OutboundHeader h
        JOIN dbo.Employee e ON e.EmployeeId = h.EmployeeId
        WHERE h.OutboundId = %s
    """, (outbound_id,))
    if not header:
        flash("找不到該出庫單", "error")
        return redirect(url_for("outbound.list_view"))
    lines = db.query(
        "SELECT * FROM dbo.OutboundDetail WHERE OutboundId = %s ORDER BY LineNum", (outbound_id,)
    )
    return render_template("outbound/detail.html", header=header, lines=lines)


@bp.route("/<outbound_id>/export")
def export_view(outbound_id):
    header = db.query_one("""
        SELECT h.*, e.EmployeeName FROM dbo.OutboundHeader h
        JOIN dbo.Employee e ON e.EmployeeId = h.EmployeeId
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
                        ("經手員工", "EmployeeName")],
        header_data=header,
        line_columns=[("行號", "LineNum"), ("物料編號", "ProductId"),
                       ("物料名稱", "ProductName"), ("數量", "Quantity")],
        lines=lines,
    )
    return send_file(buf, as_attachment=True, download_name=f"{outbound_id}.xlsx",
                      mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
