# app.py
import os
from flask import Flask, redirect, url_for
from extensions import db, login_manager, mail

def create_app():
    app = Flask(__name__)

    # ---- 基本設定 ----
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    app.config["SECURITY_PASSWORD_SALT"] = os.environ.get("SECURITY_PASSWORD_SALT", "dev-reset-salt")

    # DB（本番は DATABASE_URL で上書き推奨。SQLite を永続化するなら Persistent Disk を使い sqlite:////data/app.db）
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///app.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # ---- メール設定 ----
    app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER")            # 例: smtp.gmail.com
    app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", "587"))    # 587(TLS) or 465(SSL)
    app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    app.config["MAIL_USE_SSL"] = os.environ.get("MAIL_USE_SSL", "false").lower() == "true"
    app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")
    app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER")

    # ---- 拡張初期化 ----
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    mail.init_app(app)

    # ---- Blueprints ----
    from auth import auth_bp
    from inventory import inventory_bp  # ensure_* は後で安全に import
    app.register_blueprint(auth_bp)
    app.register_blueprint(inventory_bp)

    # ---- 起動時初期化（安全版）----
    with app.app_context():
        try:
            from models import User  # noqa
            db.create_all()
        except Exception as e:
            app.logger.error(f"[INIT] db.create_all failed: {e}")

        # ある場合だけ呼ぶ（無ければスキップ）
        try:
            from inventory import ensure_columns  # type: ignore
            ensure_columns(db)
        except Exception as e:
            app.logger.warning(f"[INIT] ensure_columns skipped or failed: {e}")

        try:
            from inventory import ensure_admin  # type: ignore
            ensure_admin(app)
        except Exception as e:
            app.logger.warning(f"[INIT] ensure_admin skipped or failed: {e}")

    # ---- ルーティング ----
    @app.route("/")
    def index():
        return redirect(url_for("inventory.dashboard"))

    @app.route("/health")
    def health():
        return "ok", 200

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)

@app.route("/health")
def health():
    return "ok", 200
