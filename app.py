from flask import Flask, redirect, url_for

import auth
import db
from config import Config
from blueprints import product, employee, inbound, outbound, reports, warehouse, doctype, customer, vendor

MENU = [
    {
        "title": "🧸 主數據",
        "links": [
            {"title": "🐻 物料管理", "endpoint": "product.list_view"},
            {"title": "🎀 員工管理", "endpoint": "employee.list_view"},
        ],
    },
    {
        "title": "📦 交易數據",
        "links": [
            {"title": "🚚 入庫管理", "endpoint": "inbound.list_view"},
            {"title": "🚛 出庫管理", "endpoint": "outbound.list_view"},
        ],
    },
    {
        "title": "🏢 往來與設定",
        "links": [
            {"title": "🏬 倉別管理", "endpoint": "warehouse.list_view"},
            {"title": "🏷️ 單別管理", "endpoint": "doctype.list_view"},
            {"title": "🧑‍🤝‍🧑 客戶管理", "endpoint": "customer.list_view"},
            {"title": "📦 廠商管理", "endpoint": "vendor.list_view"},
        ],
    },
    {
        "title": "🍡 報表查詢",
        "links": [
            {"title": "📋 入出單據", "endpoint": "reports.header_view"},
            {"title": "📝 入出明細", "endpoint": "reports.detail_view"},
            {"title": "🌸 日結餘額表", "endpoint": "reports.closing_view"},
            {"title": "💾 資料備份", "endpoint": "reports.backup_view"},
        ],
    },
]


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = Config.SECRET_KEY

    app.teardown_appcontext(db.close_connection)
    app.before_request(auth.enforce_login)

    app.register_blueprint(auth.bp)
    app.register_blueprint(product.bp, url_prefix="/products")
    app.register_blueprint(employee.bp, url_prefix="/employees")
    app.register_blueprint(inbound.bp, url_prefix="/inbound")
    app.register_blueprint(outbound.bp, url_prefix="/outbound")
    app.register_blueprint(reports.bp, url_prefix="/reports")
    app.register_blueprint(warehouse.bp, url_prefix="/warehouses")
    app.register_blueprint(doctype.bp, url_prefix="/doctypes")
    app.register_blueprint(customer.bp, url_prefix="/customers")
    app.register_blueprint(vendor.bp, url_prefix="/vendors")

    @app.context_processor
    def inject_menu():
        return {"menu": MENU}

    @app.route("/")
    def dashboard():
        return redirect(url_for("product.list_view"))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5050)
