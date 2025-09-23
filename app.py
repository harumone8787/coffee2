# app.py
import os
from flask import Flask, redirect, url_for
from extensions import db, login_manager, mail

def create_app():
    app = Flask(__name__)

    # ---- 基本設定 ----
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    app.config["SECURITY_PASSWORD_SALT"] = os.environ.get("SECURITY_PASSWORD_SALT", "dev-reset-salt")

    # DB（ローカルはSQLite、本番はDATABASE_URLで上書き可）
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///app.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # ---- メール設定（環境変数で切替）----
    # SMTP(Gmail等) 例：
    app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER")            # 例: smtp.gmail.com
    app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", "587"))    # 587(TLS) or 465(SSL)
    app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    app.config["MAIL_USE_SSL"] = os.environ.get("MAIL_USE_SSL", "false").lower() == "true"
    app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")        # 送信元アカウント
    app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")        # （Gmailはアプリパス）
    app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER")  # 例: "no-reply@example.com"

    # ---- 拡張初期化 ----
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    mail.init_app(app)

    # ---- Blueprint ----
    from auth import auth_bp
    from inventory import inventory_bp, ensure_admin, ensure_columns
    app.register_blueprint(auth_bp)
    app.register_blueprint(inventory_bp)

    # ---- 初期セットアップ ----
    with app.app_context():
        from models import User  # noqa
        db.create_all()
        ensure_columns(db)
        ensure_admin(app)

    @app.route("/")
    def index():
        return redirect(url_for("inventory.dashboard"))

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
