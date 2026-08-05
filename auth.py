from functools import wraps

from flask import Blueprint, request, session, redirect, url_for, render_template, flash
from werkzeug.security import check_password_hash
from config import Config

bp = Blueprint("auth", __name__)

PUBLIC_ENDPOINTS = {"auth.login", "static"}

ROLE_ACCOUNTS = {
    "employee": (Config.EMPLOYEE_USERNAME, Config.EMPLOYEE_PASSWORD_HASH),
    "manager": (Config.MANAGER_USERNAME, Config.MANAGER_PASSWORD_HASH),
}


def enforce_login():
    """Called from app.before_request — blocks everything except /login and
    static assets until session["user"] is set."""
    if request.endpoint in PUBLIC_ENDPOINTS or request.endpoint is None:
        return None
    if not session.get("user"):
        return redirect(url_for("auth.login", next=request.path))
    return None


def manager_required(view):
    """Route-level enforcement for manager-only actions (approve/reject) —
    hiding the buttons in the template isn't real security on its own."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "manager":
            flash("只有主管才能執行此操作", "error")
            return redirect(request.referrer or url_for("dashboard.index_view"))
        return view(*args, **kwargs)
    return wrapped


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("dashboard.index_view"))
    next_url = request.values.get("next") or url_for("dashboard.index_view")
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        matched_role = None
        for role, (account_username, account_hash) in ROLE_ACCOUNTS.items():
            if username == account_username and check_password_hash(account_hash, password):
                matched_role = role
                break
        if matched_role:
            session["user"] = username
            session["role"] = matched_role
            return redirect(next_url)
        flash("帳號或密碼錯誤", "error")
    return render_template("login.html", next=next_url)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
