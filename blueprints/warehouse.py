import pytds
from flask import Blueprint, render_template, request, redirect, url_for, flash

import db
import id_generator

bp = Blueprint("warehouse", __name__)


def _in_use_count(warehouse_id):
    return (
        db.query_one("SELECT COUNT(*) AS c FROM dbo.InboundHeader WHERE WarehouseId = %s", (warehouse_id,))["c"]
        + db.query_one("SELECT COUNT(*) AS c FROM dbo.OutboundHeader WHERE WarehouseId = %s", (warehouse_id,))["c"]
    )


@bp.route("/")
def list_view():
    warehouses = db.query("SELECT WarehouseId, WarehouseName FROM dbo.Warehouse ORDER BY WarehouseId")
    return render_template("warehouse/list.html", warehouses=warehouses)


@bp.route("/new", methods=["GET", "POST"])
def create_view():
    if request.method == "POST":
        name = request.form.get("warehouse_name", "").strip()
        if not name:
            flash("倉別名稱必填", "error")
            return render_template("warehouse/form.html", warehouse=None,
                                    form_values={"warehouse_name": name})

        def insert(new_id):
            db.execute(
                "INSERT INTO dbo.Warehouse (WarehouseId, WarehouseName) VALUES (%s, %s)",
                (new_id, name),
            )

        new_id = id_generator.generate_with_retry(id_generator.next_warehouse_id, insert)
        flash(f"已新增倉別 {new_id}", "success")
        return redirect(url_for("warehouse.list_view"))

    return render_template("warehouse/form.html", warehouse=None, form_values={"warehouse_name": ""})


@bp.route("/<warehouse_id>/edit", methods=["GET", "POST"])
def edit_view(warehouse_id):
    warehouse = db.query_one("SELECT * FROM dbo.Warehouse WHERE WarehouseId = %s", (warehouse_id,))
    if not warehouse:
        flash("找不到該倉別", "error")
        return redirect(url_for("warehouse.list_view"))

    if request.method == "POST":
        name = request.form.get("warehouse_name", "").strip()
        if not name:
            flash("倉別名稱必填", "error")
            return render_template("warehouse/form.html", warehouse=warehouse,
                                    form_values={"warehouse_name": name})
        db.execute("UPDATE dbo.Warehouse SET WarehouseName = %s WHERE WarehouseId = %s", (name, warehouse_id))
        flash("已更新倉別", "success")
        return redirect(url_for("warehouse.list_view"))

    return render_template("warehouse/form.html", warehouse=warehouse,
                            form_values={"warehouse_name": warehouse["WarehouseName"]})


@bp.route("/<warehouse_id>/delete", methods=["POST"])
def delete_view(warehouse_id):
    if _in_use_count(warehouse_id) > 0:
        flash("此倉別已有入出庫單據使用,無法刪除", "error")
        return redirect(url_for("warehouse.list_view"))
    try:
        db.execute("DELETE FROM dbo.Warehouse WHERE WarehouseId = %s", (warehouse_id,))
        flash("已刪除倉別", "success")
    except pytds.tds_base.IntegrityError:
        flash("此倉別已有關聯資料,無法刪除", "error")
    return redirect(url_for("warehouse.list_view"))
