from flask import Blueprint, request, session, redirect, url_for, render_template, flash
from werkzeug.security import check_password_hash
from config import Config

bp = Blueprint("auth", __name__)

PUBLIC_ENDPOINTS = {"auth.login", "static"}


def enforce_login():
    """Called from app.before_request — blocks everything except /login and
    static assets until session["user"] is set."""
    if request.endpoint in PUBLIC_ENDPOINTS or request.endpoint is None:
        return None
    if not session.get("user"):
        return redirect(url_for("auth.login", next=request.path))
    return None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("dashboard"))
    next_url = request.values.get("next") or url_for("dashboard")
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == Config.APP_USERNAME and check_password_hash(Config.APP_PASSWORD_HASH, password):
            session["user"] = username
            return redirect(next_url)
        flash("帳號或密碼錯誤", "error")
    return render_template("login.html", next=next_url)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
