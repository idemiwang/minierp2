import pytds
from flask import Blueprint, render_template, request, redirect, url_for, flash

import db
import id_generator

bp = Blueprint("doctype", __name__)

DIRECTION_LABELS = {"IN": "入庫", "OUT": "出庫"}


def _in_use_count(doctype_id):
    return (
        db.query_one("SELECT COUNT(*) AS c FROM dbo.InboundHeader WHERE DocTypeId = %s", (doctype_id,))["c"]
        + db.query_one("SELECT COUNT(*) AS c FROM dbo.OutboundHeader WHERE DocTypeId = %s", (doctype_id,))["c"]
    )


@bp.route("/")
def list_view():
    doctypes = db.query("SELECT DocTypeId, DocTypeName, Direction FROM dbo.DocType ORDER BY Direction, DocTypeId")
    return render_template("doctype/list.html", doctypes=doctypes, direction_labels=DIRECTION_LABELS)


@bp.route("/new", methods=["GET", "POST"])
def create_view():
    if request.method == "POST":
        name = request.form.get("doctype_name", "").strip()
        direction = request.form.get("direction", "")
        if not name or direction not in DIRECTION_LABELS:
            flash("單別名稱與方向皆必填", "error")
            return render_template("doctype/form.html", doctype=None,
                                    form_values={"doctype_name": name, "direction": direction})

        def insert(new_id):
            db.execute(
                "INSERT INTO dbo.DocType (DocTypeId, DocTypeName, Direction) VALUES (%s, %s, %s)",
                (new_id, name, direction),
            )

        new_id = id_generator.generate_with_retry(id_generator.next_doctype_id, insert)
        flash(f"已新增單別 {new_id}", "success")
        return redirect(url_for("doctype.list_view"))

    return render_template("doctype/form.html", doctype=None,
                            form_values={"doctype_name": "", "direction": "IN"})


@bp.route("/<doctype_id>/edit", methods=["GET", "POST"])
def edit_view(doctype_id):
    doctype = db.query_one("SELECT * FROM dbo.DocType WHERE DocTypeId = %s", (doctype_id,))
    if not doctype:
        flash("找不到該單別", "error")
        return redirect(url_for("doctype.list_view"))

    if request.method == "POST":
        name = request.form.get("doctype_name", "").strip()
        direction = request.form.get("direction", "")
        if not name or direction not in DIRECTION_LABELS:
            flash("單別名稱與方向皆必填", "error")
            return render_template("doctype/form.html", doctype=doctype,
                                    form_values={"doctype_name": name, "direction": direction})
        db.execute(
            "UPDATE dbo.DocType SET DocTypeName = %s, Direction = %s WHERE DocTypeId = %s",
            (name, direction, doctype_id),
        )
        flash("已更新單別", "success")
        return redirect(url_for("doctype.list_view"))

    return render_template("doctype/form.html", doctype=doctype,
                            form_values={"doctype_name": doctype["DocTypeName"], "direction": doctype["Direction"]})


@bp.route("/<doctype_id>/delete", methods=["POST"])
def delete_view(doctype_id):
    if _in_use_count(doctype_id) > 0:
        flash("此單別已有入出庫單據使用,無法刪除", "error")
        return redirect(url_for("doctype.list_view"))
    try:
        db.execute("DELETE FROM dbo.DocType WHERE DocTypeId = %s", (doctype_id,))
        flash("已刪除單別", "success")
    except pytds.tds_base.IntegrityError:
        flash("此單別已有關聯資料,無法刪除", "error")
    return redirect(url_for("doctype.list_view"))
