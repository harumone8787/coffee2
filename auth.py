from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask_mail import Message
from extensions import db, mail
from models import User
import re

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# ===== ユーティリティ =====
def _get_serializer():
    secret_key = current_app.config.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY が設定されていません。")
    salt = current_app.config.get("SECURITY_PASSWORD_SALT", "default-reset-salt")
    return URLSafeTimedSerializer(secret_key, salt=salt)

def _valid_email(s: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", s or "", flags=re.I))

def _send_reset_link(email: str, link: str):
    """
    本番: Flask-Mail で送信
    開発: MAIL_SERVER 等が未設定ならコンソールへ出力
    """
    if current_app.config.get("MAIL_SERVER") and current_app.config.get("MAIL_DEFAULT_SENDER"):
        subj = "【在庫管理】パスワード再設定リンク"
        body = f"以下のリンクから1時間以内にパスワードを再設定してください。\n\n{link}\n\n※心当たりがない場合はこのメールを破棄してください。"
        try:
            msg = Message(subject=subj, recipients=[email], body=body)
            mail.send(msg)
            current_app.logger.info(f"[MAIL] Sent reset link to {email}")
        except Exception as e:
            current_app.logger.error(f"[MAIL] send failed: {e}")
            # フォールバック（失敗時はコンソールにも表示）
            print(f"[DEV-FALLBACK] Password reset link for {email}: {link}")
    else:
        # 開発時: コンソール出力
        current_app.logger.info(f"[DEV] Password reset link for {email}: {link}")
        print(f"[DEV] Password reset link for {email}: {link}")

# ===== 認証 =====
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ident = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not ident or not password:
            flash("ユーザー名（またはメール）とパスワードを入力してください。", "danger")
            return render_template("login.html")

        user = User.query.filter((User.username == ident) | (User.email == ident)).first()
        if not user or not user.is_active:
            flash("ユーザーが見つからないか、無効化されています。", "danger")
            return render_template("login.html")

        if not user.check_password(password):
            flash("パスワードが違います。", "danger")
            return render_template("login.html")

        login_user(user)
        flash("ログインしました。", "success")
        return redirect(url_for("inventory.dashboard"))
    return render_template("login.html")

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("ログアウトしました。", "success")
    return redirect(url_for("auth.login"))

@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not current_user.check_password(current_password):
            flash("現在のパスワードが違います。", "danger")
            return render_template("change_password.html")

        if not new_password or new_password != confirm_password:
            flash("新しいパスワードが未入力、または一致しません。", "danger")
            return render_template("change_password.html")

        current_user.set_password(new_password)
        db.session.commit()
        flash("パスワードを変更しました。", "success")
        return redirect(url_for("inventory.dashboard"))
    return render_template("change_password.html")

# ===== パスワード再設定フロー =====
@auth_bp.route("/request-reset", methods=["GET", "POST"])
def request_reset():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        if not _valid_email(email):
            flash("メールアドレスの形式が不正です。", "danger")
            return render_template("request_reset.html")

        s = _get_serializer()
        token = s.dumps(email)
        reset_link = url_for("auth.reset_with_token", token=token, _external=True)

        _send_reset_link(email, reset_link)

        flash("パスワード再設定用のリンクを送信しました。（登録がある場合）", "success")
        return redirect(url_for("auth.login"))

    return render_template("request_reset.html")

@auth_bp.route("/reset/<token>", methods=["GET", "POST"])
def reset_with_token(token):
    s = _get_serializer()
    try:
        email = s.loads(token, max_age=3600)  # 1時間有効
    except SignatureExpired:
        flash("リンクの有効期限が切れています。もう一度発行してください。", "danger")
        return redirect(url_for("auth.request_reset"))
    except BadSignature:
        flash("リンクが不正です。", "danger")
        return redirect(url_for("auth.request_reset"))

    if request.method == "GET":
        return render_template("reset_password.html")

    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")
    if not new_password or new_password != confirm_password:
        flash("新しいパスワードが未入力、または一致しません。", "danger")
        return render_template("reset_password.html")

    user = User.query.filter_by(email=email).first()

    if not user or not user.is_active:
        flash("パスワードを更新しました。（登録がある場合）", "success")
        return redirect(url_for("auth.login"))

    user.set_password(new_password)
    db.session.commit()
    flash("パスワードを更新しました。ログインしてください。", "success")
    return redirect(url_for("auth.login"))
