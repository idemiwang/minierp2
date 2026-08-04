import pytds
from flask import Blueprint, render_template, request, redirect, url_for, flash

import db
import id_generator

bp = Blueprint("product", __name__)


@bp.route("/")
def list_view():
    products = db.query("SELECT ProductId, ProductName, StockBalance FROM dbo.Product ORDER BY ProductId")
    return render_template("product/list.html", products=products)


@bp.route("/new", methods=["GET", "POST"])
def create_view():
    if request.method == "POST":
        name = request.form.get("product_name", "").strip()
        stock = request.form.get("stock_balance") or "0"
        if not name:
            flash("物料名稱必填", "error")
            return render_template("product/form.html", product=None,
                                    form_values={"product_name": name, "stock_balance": stock})

        def insert(new_id):
            db.execute(
                "INSERT INTO dbo.Product (ProductId, ProductName, StockBalance) VALUES (%s, %s, %s)",
                (new_id, name, stock),
            )

        new_id = id_generator.generate_with_retry(id_generator.next_product_id, insert)
        flash(f"已新增物料 {new_id}", "success")
        return redirect(url_for("product.list_view"))

    return render_template("product/form.html", product=None,
                            form_values={"product_name": "", "stock_balance": "0"})


@bp.route("/<product_id>/edit", methods=["GET", "POST"])
def edit_view(product_id):
    product = db.query_one("SELECT * FROM dbo.Product WHERE ProductId = %s", (product_id,))
    if not product:
        flash("找不到該物料", "error")
        return redirect(url_for("product.list_view"))

    if request.method == "POST":
        name = request.form.get("product_name", "").strip()
        stock = request.form.get("stock_balance") or "0"
        if not name:
            flash("物料名稱必填", "error")
            return render_template("product/form.html", product=product,
                                    form_values={"product_name": name, "stock_balance": stock})
        db.execute(
            "UPDATE dbo.Product SET ProductName = %s, StockBalance = %s WHERE ProductId = %s",
            (name, stock, product_id),
        )
        flash("已更新物料", "success")
        return redirect(url_for("product.list_view"))

    return render_template("product/form.html", product=product,
                            form_values={"product_name": product["ProductName"],
                                         "stock_balance": product["StockBalance"]})


@bp.route("/<product_id>/delete", methods=["POST"])
def delete_view(product_id):
    detail_count = db.query_one(
        "SELECT COUNT(*) AS c FROM dbo.v_inoutdetail WHERE ProductId = %s", (product_id,)
    )["c"]
    if detail_count > 0:
        flash("此物料已有入出庫明細,無法刪除", "error")
        return redirect(url_for("product.list_view"))

    try:
        db.execute("DELETE FROM dbo.Product WHERE ProductId = %s", (product_id,))
        flash("已刪除物料", "success")
    except pytds.tds_base.IntegrityError:
        flash("此物料已有關聯資料,無法刪除", "error")
    return redirect(url_for("product.list_view"))


@bp.route("/<product_id>")
def detail_view(product_id):
    product = db.query_one("SELECT * FROM dbo.Product WHERE ProductId = %s", (product_id,))
    if not product:
        flash("找不到該物料", "error")
        return redirect(url_for("product.list_view"))
    details = db.query(
        "SELECT * FROM dbo.v_inoutdetail WHERE ProductId = %s ORDER BY InboundId, LineNum",
        (product_id,),
    )
    return render_template("product/detail.html", product=product, details=details)
