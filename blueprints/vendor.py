import pytds
from flask import Blueprint, render_template, request, redirect, url_for, flash

import db
import id_generator

bp = Blueprint("vendor", __name__)


@bp.route("/")
def list_view():
    vendors = db.query("SELECT VendorId, VendorName, Phone FROM dbo.Vendor ORDER BY VendorId")
    return render_template("vendor/list.html", vendors=vendors)


@bp.route("/new", methods=["GET", "POST"])
def create_view():
    if request.method == "POST":
        name = request.form.get("vendor_name", "").strip()
        phone = request.form.get("phone", "").strip() or None
        if not name:
            flash("廠商名稱必填", "error")
            return render_template("vendor/form.html", vendor=None,
                                    form_values={"vendor_name": name, "phone": phone or ""})

        def insert(new_id):
            db.execute(
                "INSERT INTO dbo.Vendor (VendorId, VendorName, Phone) VALUES (%s, %s, %s)",
                (new_id, name, phone),
            )

        new_id = id_generator.generate_with_retry(id_generator.next_vendor_id, insert)
        flash(f"已新增廠商 {new_id}", "success")
        return redirect(url_for("vendor.list_view"))

    return render_template("vendor/form.html", vendor=None,
                            form_values={"vendor_name": "", "phone": ""})


@bp.route("/<vendor_id>/edit", methods=["GET", "POST"])
def edit_view(vendor_id):
    vendor = db.query_one("SELECT * FROM dbo.Vendor WHERE VendorId = %s", (vendor_id,))
    if not vendor:
        flash("找不到該廠商", "error")
        return redirect(url_for("vendor.list_view"))

    if request.method == "POST":
        name = request.form.get("vendor_name", "").strip()
        phone = request.form.get("phone", "").strip() or None
        if not name:
            flash("廠商名稱必填", "error")
            return render_template("vendor/form.html", vendor=vendor,
                                    form_values={"vendor_name": name, "phone": phone or ""})
        db.execute(
            "UPDATE dbo.Vendor SET VendorName = %s, Phone = %s WHERE VendorId = %s",
            (name, phone, vendor_id),
        )
        flash("已更新廠商", "success")
        return redirect(url_for("vendor.list_view"))

    return render_template("vendor/form.html", vendor=vendor,
                            form_values={"vendor_name": vendor["VendorName"], "phone": vendor["Phone"] or ""})


@bp.route("/<vendor_id>/delete", methods=["POST"])
def delete_view(vendor_id):
    in_use = db.query_one(
        "SELECT COUNT(*) AS c FROM dbo.InboundHeader WHERE VendorId = %s", (vendor_id,)
    )["c"]
    if in_use > 0:
        flash("此廠商已有入庫單據使用,無法刪除", "error")
        return redirect(url_for("vendor.list_view"))
    try:
        db.execute("DELETE FROM dbo.Vendor WHERE VendorId = %s", (vendor_id,))
        flash("已刪除廠商", "success")
    except pytds.tds_base.IntegrityError:
        flash("此廠商已有關聯資料,無法刪除", "error")
    return redirect(url_for("vendor.list_view"))
