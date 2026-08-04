import pytds
from flask import Blueprint, render_template, request, redirect, url_for, flash

import db
import id_generator

bp = Blueprint("employee", __name__)


@bp.route("/")
def list_view():
    employees = db.query("SELECT EmployeeId, EmployeeName, Email FROM dbo.Employee ORDER BY EmployeeId")
    return render_template("employee/list.html", employees=employees)


@bp.route("/new", methods=["GET", "POST"])
def create_view():
    if request.method == "POST":
        name = request.form.get("employee_name", "").strip()
        email = request.form.get("email", "").strip() or None
        if not name:
            flash("員工姓名必填", "error")
            return render_template("employee/form.html", employee=None,
                                    form_values={"employee_name": name, "email": email or ""})

        def insert(new_id):
            db.execute(
                "INSERT INTO dbo.Employee (EmployeeId, EmployeeName, Email) VALUES (%s, %s, %s)",
                (new_id, name, email),
            )

        new_id = id_generator.generate_with_retry(id_generator.next_employee_id, insert)
        flash(f"已新增員工 {new_id}", "success")
        return redirect(url_for("employee.list_view"))

    return render_template("employee/form.html", employee=None,
                            form_values={"employee_name": "", "email": ""})


@bp.route("/<employee_id>/edit", methods=["GET", "POST"])
def edit_view(employee_id):
    employee = db.query_one("SELECT * FROM dbo.Employee WHERE EmployeeId = %s", (employee_id,))
    if not employee:
        flash("找不到該員工", "error")
        return redirect(url_for("employee.list_view"))

    if request.method == "POST":
        name = request.form.get("employee_name", "").strip()
        email = request.form.get("email", "").strip() or None
        if not name:
            flash("員工姓名必填", "error")
            return render_template("employee/form.html", employee=employee,
                                    form_values={"employee_name": name, "email": email or ""})
        db.execute(
            "UPDATE dbo.Employee SET EmployeeName = %s, Email = %s WHERE EmployeeId = %s",
            (name, email, employee_id),
        )
        flash("已更新員工", "success")
        return redirect(url_for("employee.list_view"))

    return render_template("employee/form.html", employee=employee,
                            form_values={"employee_name": employee["EmployeeName"],
                                         "email": employee["Email"] or ""})


@bp.route("/<employee_id>/delete", methods=["POST"])
def delete_view(employee_id):
    detail_count = db.query_one(
        "SELECT COUNT(*) AS c FROM dbo.v_inoutheader WHERE EmployeeId = %s", (employee_id,)
    )["c"]
    if detail_count > 0:
        flash("此員工已有入出庫紀錄,無法刪除", "error")
        return redirect(url_for("employee.list_view"))

    try:
        db.execute("DELETE FROM dbo.Employee WHERE EmployeeId = %s", (employee_id,))
        flash("已刪除員工", "success")
    except pytds.tds_base.IntegrityError:
        flash("此員工已有關聯資料,無法刪除", "error")
    return redirect(url_for("employee.list_view"))


@bp.route("/<employee_id>")
def detail_view(employee_id):
    employee = db.query_one("SELECT * FROM dbo.Employee WHERE EmployeeId = %s", (employee_id,))
    if not employee:
        flash("找不到該員工", "error")
        return redirect(url_for("employee.list_view"))
    headers = db.query(
        "SELECT * FROM dbo.v_inoutheader WHERE EmployeeId = %s ORDER BY InboundDate DESC",
        (employee_id,),
    )
    return render_template("employee/detail.html", employee=employee, headers=headers)
