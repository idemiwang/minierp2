from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file

import db
import id_generator
import inventory_closing
from excel.exporters import export_document

bp = Blueprint("inbound", __name__)


def _products():
    return db.query("SELECT ProductId, ProductName FROM dbo.Product ORDER BY ProductId")


def _employees():
    return db.query("SELECT EmployeeId, EmployeeName FROM dbo.Employee ORDER BY EmployeeId")


def _parse_lines(form, product_map):
    """Build validated (product_id, product_name, quantity) tuples from the
    posted product_id[]/quantity[] arrays. Rows with an unknown product or a
    non-positive quantity are dropped rather than raising, so a stray blank
    row from the client-side grid doesn't block the whole save."""
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
        SELECT h.InboundId, h.InboundDate, h.EmployeeId, e.EmployeeName,
               (SELECT COUNT(*) FROM dbo.InboundDetail d WHERE d.InboundId = h.InboundId) AS LineCount
        FROM dbo.InboundHeader h
        JOIN dbo.Employee e ON e.EmployeeId = h.EmployeeId
        ORDER BY h.InboundDate DESC, h.InboundId DESC
    """)
    return render_template("inbound/list.html", headers=headers)


@bp.route("/new", methods=["GET", "POST"])
def create_view():
    products = _products()
    employees = _employees()
    product_map = {p["ProductId"]: p["ProductName"] for p in products}

    if request.method == "POST":
        inbound_date = request.form.get("inbound_date") or date.today().isoformat()
        employee_id = request.form.get("employee_id", "")
        lines = _parse_lines(request.form, product_map)

        if not employee_id:
            flash("請選擇員工", "error")
            return render_template("inbound/form.html", header=None, lines=[],
                                    products=products, employees=employees,
                                    form_values={"inbound_date": inbound_date, "employee_id": employee_id})
        if not lines:
            flash("至少需要一筆明細,且數量需大於 0", "error")
            return render_template("inbound/form.html", header=None, lines=[],
                                    products=products, employees=employees,
                                    form_values={"inbound_date": inbound_date, "employee_id": employee_id})

        def insert(new_id):
            with db.transaction() as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO dbo.InboundHeader (InboundId, InboundDate, EmployeeId) VALUES (%s, %s, %s)",
                    (new_id, inbound_date, employee_id),
                )
                for line_num, (pid, pname, qty) in enumerate(lines, start=1):
                    cur.execute(
                        "INSERT INTO dbo.InboundDetail (InboundId, LineNum, ProductId, ProductName, Quantity) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (new_id, line_num, pid, pname, qty),
                    )
                for pid in {pid for pid, _, _ in lines}:
                    inventory_closing.recalculate(pid)

        new_id = id_generator.generate_with_retry(id_generator.next_inbound_id, insert)
        flash(f"已新增入庫單 {new_id}", "success")
        return redirect(url_for("inbound.detail_view", inbound_id=new_id))

    return render_template("inbound/form.html", header=None, lines=[],
                            products=products, employees=employees,
                            form_values={"inbound_date": date.today().isoformat(), "employee_id": ""})


@bp.route("/<inbound_id>/edit", methods=["GET", "POST"])
def edit_view(inbound_id):
    header = db.query_one("SELECT * FROM dbo.InboundHeader WHERE InboundId = %s", (inbound_id,))
    if not header:
        flash("找不到該入庫單", "error")
        return redirect(url_for("inbound.list_view"))

    products = _products()
    employees = _employees()
    product_map = {p["ProductId"]: p["ProductName"] for p in products}

    if request.method == "POST":
        inbound_date = request.form.get("inbound_date") or header["InboundDate"]
        employee_id = request.form.get("employee_id", "")
        lines = _parse_lines(request.form, product_map)
        existing_lines = db.query(
            "SELECT ProductId, Quantity FROM dbo.InboundDetail WHERE InboundId = %s ORDER BY LineNum",
            (inbound_id,),
        )

        if not employee_id or not lines:
            flash("請選擇員工,且至少需要一筆明細(數量需大於 0)", "error")
            return render_template("inbound/form.html", header=header,
                                    lines=[{"ProductId": p, "Quantity": q} for p, q in
                                           zip(request.form.getlist("product_id[]"), request.form.getlist("quantity[]"))],
                                    products=products, employees=employees,
                                    form_values={"inbound_date": inbound_date, "employee_id": employee_id})

        with db.transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE dbo.InboundHeader SET InboundDate = %s, EmployeeId = %s WHERE InboundId = %s",
                (inbound_date, employee_id, inbound_id),
            )
            cur.execute("DELETE FROM dbo.InboundDetail WHERE InboundId = %s", (inbound_id,))
            for line_num, (pid, pname, qty) in enumerate(lines, start=1):
                cur.execute(
                    "INSERT INTO dbo.InboundDetail (InboundId, LineNum, ProductId, ProductName, Quantity) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (inbound_id, line_num, pid, pname, qty),
                )
            affected = {r["ProductId"] for r in existing_lines} | {pid for pid, _, _ in lines}
            for pid in affected:
                inventory_closing.recalculate(pid)
        flash("已更新入庫單", "success")
        return redirect(url_for("inbound.detail_view", inbound_id=inbound_id))

    lines = db.query(
        "SELECT * FROM dbo.InboundDetail WHERE InboundId = %s ORDER BY LineNum", (inbound_id,)
    )
    return render_template("inbound/form.html", header=header, lines=lines,
                            products=products, employees=employees,
                            form_values={"inbound_date": str(header["InboundDate"]), "employee_id": header["EmployeeId"]})


@bp.route("/<inbound_id>/delete", methods=["POST"])
def delete_view(inbound_id):
    affected = {r["ProductId"] for r in db.query(
        "SELECT DISTINCT ProductId FROM dbo.InboundDetail WHERE InboundId = %s", (inbound_id,)
    )}
    with db.transaction() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.InboundDetail WHERE InboundId = %s", (inbound_id,))
        cur.execute("DELETE FROM dbo.InboundHeader WHERE InboundId = %s", (inbound_id,))
        for pid in affected:
            inventory_closing.recalculate(pid)
    flash("已刪除入庫單", "success")
    return redirect(url_for("inbound.list_view"))


@bp.route("/<inbound_id>")
def detail_view(inbound_id):
    header = db.query_one("""
        SELECT h.*, e.EmployeeName FROM dbo.InboundHeader h
        JOIN dbo.Employee e ON e.EmployeeId = h.EmployeeId
        WHERE h.InboundId = %s
    """, (inbound_id,))
    if not header:
        flash("找不到該入庫單", "error")
        return redirect(url_for("inbound.list_view"))
    lines = db.query(
        "SELECT * FROM dbo.InboundDetail WHERE InboundId = %s ORDER BY LineNum", (inbound_id,)
    )
    return render_template("inbound/detail.html", header=header, lines=lines)


@bp.route("/<inbound_id>/export")
def export_view(inbound_id):
    header = db.query_one("""
        SELECT h.*, e.EmployeeName FROM dbo.InboundHeader h
        JOIN dbo.Employee e ON e.EmployeeId = h.EmployeeId
        WHERE h.InboundId = %s
    """, (inbound_id,))
    if not header:
        flash("找不到該入庫單", "error")
        return redirect(url_for("inbound.list_view"))
    lines = db.query(
        "SELECT * FROM dbo.InboundDetail WHERE InboundId = %s ORDER BY LineNum", (inbound_id,)
    )
    buf = export_document(
        title=f"入庫單 {inbound_id}",
        header_fields=[("入庫單號", "InboundId"), ("入庫日期", "InboundDate"),
                        ("經手員工", "EmployeeName")],
        header_data=header,
        line_columns=[("行號", "LineNum"), ("物料編號", "ProductId"),
                       ("物料名稱", "ProductName"), ("數量", "Quantity")],
        lines=lines,
    )
    return send_file(buf, as_attachment=True, download_name=f"{inbound_id}.xlsx",
                      mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
