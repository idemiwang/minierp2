import pytds
from flask import Blueprint, render_template, request, redirect, url_for, flash

import db
import id_generator

bp = Blueprint("customer", __name__)


@bp.route("/")
def list_view():
    customers = db.query("SELECT CustomerId, CustomerName, Phone FROM dbo.Customer ORDER BY CustomerId")
    return render_template("customer/list.html", customers=customers)


@bp.route("/new", methods=["GET", "POST"])
def create_view():
    if request.method == "POST":
        name = request.form.get("customer_name", "").strip()
        phone = request.form.get("phone", "").strip() or None
        if not name:
            flash("客戶名稱必填", "error")
            return render_template("customer/form.html", customer=None,
                                    form_values={"customer_name": name, "phone": phone or ""})

        def insert(new_id):
            db.execute(
                "INSERT INTO dbo.Customer (CustomerId, CustomerName, Phone) VALUES (%s, %s, %s)",
                (new_id, name, phone),
            )

        new_id = id_generator.generate_with_retry(id_generator.next_customer_id, insert)
        flash(f"已新增客戶 {new_id}", "success")
        return redirect(url_for("customer.list_view"))

    return render_template("customer/form.html", customer=None,
                            form_values={"customer_name": "", "phone": ""})


@bp.route("/<customer_id>/edit", methods=["GET", "POST"])
def edit_view(customer_id):
    customer = db.query_one("SELECT * FROM dbo.Customer WHERE CustomerId = %s", (customer_id,))
    if not customer:
        flash("找不到該客戶", "error")
        return redirect(url_for("customer.list_view"))

    if request.method == "POST":
        name = request.form.get("customer_name", "").strip()
        phone = request.form.get("phone", "").strip() or None
        if not name:
            flash("客戶名稱必填", "error")
            return render_template("customer/form.html", customer=customer,
                                    form_values={"customer_name": name, "phone": phone or ""})
        db.execute(
            "UPDATE dbo.Customer SET CustomerName = %s, Phone = %s WHERE CustomerId = %s",
            (name, phone, customer_id),
        )
        flash("已更新客戶", "success")
        return redirect(url_for("customer.list_view"))

    return render_template("customer/form.html", customer=customer,
                            form_values={"customer_name": customer["CustomerName"], "phone": customer["Phone"] or ""})


@bp.route("/<customer_id>/delete", methods=["POST"])
def delete_view(customer_id):
    in_use = db.query_one(
        "SELECT COUNT(*) AS c FROM dbo.OutboundHeader WHERE CustomerId = %s", (customer_id,)
    )["c"]
    if in_use > 0:
        flash("此客戶已有出庫單據使用,無法刪除", "error")
        return redirect(url_for("customer.list_view"))
    try:
        db.execute("DELETE FROM dbo.Customer WHERE CustomerId = %s", (customer_id,))
        flash("已刪除客戶", "success")
    except pytds.tds_base.IntegrityError:
        flash("此客戶已有關聯資料,無法刪除", "error")
    return redirect(url_for("customer.list_view"))
