# inventory.py
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func, case
from sqlalchemy.orm import selectinload

from extensions import db
from models import User, Product, Movement

inventory_bp = Blueprint("inventory", __name__)

# --- Postgres では列点検は何もしない（SQLite 専用の PRAGMA は使わない） ---
def ensure_columns(db_):
    """
    以前は SQLite の PRAGMA を使ってカラム確認していましたが、
    本番は Postgres のため、ここでは何もしません。（安全のため no-op）
    """
    return

# デフォルト管理者を作成
def ensure_admin(app):
    with app.app_context():
        if not User.query.filter_by(username="admin").first():
            u = User(username="admin", email="admin@example.com", is_admin=True)
            u.set_password("admin0123")
            db.session.add(u)
            db.session.commit()
            app.logger.info("[INIT] created default admin")


# ====== ページ ======

@inventory_bp.route("/dashboard")
@login_required
def dashboard():
    # 検索フィルタ（商品名）
    q = request.args.get("q", "").strip()
    product_query = Product.query
    if q:
        product_query = product_query.filter(Product.name.ilike(f"%{q}%"))

    products = product_query.order_by(Product.name.asc()).all()

    # 在庫数 = 入庫 - 出庫（Movement 集計）
    agg = (
        db.session.query(
            Product.id.label("pid"),
            func.coalesce(
                func.sum(
                    case(
                        (Movement.movement_type == "in", Movement.quantity),
                        else_=-Movement.quantity,
                    )
                ),
                0,
            ).label("qty"),
        )
        .select_from(Product)
        .outerjoin(Movement, Movement.product_id == Product.id)
        .group_by(Product.id)
        .all()
    )
    qty_map = {row.pid: int(row.qty or 0) for row in agg}

    # 最新10件（関連は事前ロード）
    recent_movements = (
        Movement.query.options(
            selectinload(Movement.product),
            selectinload(Movement.user),
        )
        .order_by(Movement.created_at.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "dashboard.html",
        products=products,
        qty_map=qty_map,
        recent_movements=recent_movements,
        filter_products=q,
    )


# ========== 商品 ==========
@inventory_bp.route("/products", methods=["GET", "POST"])
@login_required
def products():
    if not current_user.is_admin:
        flash("商品登録は管理者のみ可能です。", "warning")
        return redirect(url_for("inventory.dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        unit = request.form.get("unit", "").strip()
        min_stock = request.form.get("min_stock", "").strip()
        supplier = request.form.get("supplier", "").strip()

        if not name:
            flash("商品名は必須です。", "danger")
        else:
            try:
                p = Product(
                    name=name,
                    unit=unit or None,
                    min_stock=int(min_stock) if min_stock else None,
                    supplier=supplier or None,
                    created_at=datetime.utcnow(),
                )
                db.session.add(p)
                db.session.commit()
                flash("商品を登録しました。", "success")
                return redirect(url_for("inventory.products"))
            except Exception as e:
                db.session.rollback()
                flash(f"商品登録に失敗しました: {e}", "danger")

    items = Product.query.order_by(Product.created_at.desc()).all()
    return render_template("products.html", products=items)


@inventory_bp.route("/product/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def product_edit(pid):
    if not current_user.is_admin:
        flash("商品編集は管理者のみ可能です。", "warning")
        return redirect(url_for("inventory.dashboard"))

    p = Product.query.get_or_404(pid)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        unit = request.form.get("unit", "").strip()
        min_stock = request.form.get("min_stock", "").strip()
        supplier = request.form.get("supplier", "").strip()

        try:
            p.name = name or p.name
            p.unit = unit or None
            p.min_stock = int(min_stock) if min_stock else None
            p.supplier = supplier or None
            db.session.commit()
            flash("商品情報を更新しました。", "success")
            return redirect(url_for("inventory.products"))
        except Exception as e:
            db.session.rollback()
            flash(f"更新に失敗しました: {e}", "danger")

    return render_template("product_edit.html", p=p)


@inventory_bp.route("/product/<int:pid>/delete", methods=["POST"])
@login_required
def product_delete(pid):
    if not current_user.is_admin:
        flash("商品削除は管理者のみ可能です。", "warning")
        return redirect(url_for("inventory.dashboard"))

    p = Product.query.get_or_404(pid)
    try:
        db.session.delete(p)
        db.session.commit()
        flash("商品を削除しました。", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"削除に失敗しました: {e}", "danger")
    return redirect(url_for("inventory.products"))


# ========== 入出庫 ==========
@inventory_bp.route("/movements", methods=["GET", "POST"])
@login_required
def movements():
    if request.method == "POST":
        product_id = request.form.get("product_id")
        movement_type = request.form.get("movement_type")  # 'in' or 'out'
        quantity = request.form.get("quantity")

        if not product_id or not movement_type or not quantity:
            flash("必要項目が不足しています。", "danger")
            return redirect(url_for("inventory.movements"))

        try:
            mv = Movement(
                product_id=int(product_id),
                movement_type=movement_type,
                quantity=int(quantity),
                user_id=current_user.id,
                created_at=datetime.utcnow(),
            )
            db.session.add(mv)
            db.session.commit()
            flash("入出庫を記録しました。", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"記録に失敗しました: {e}", "danger")
        return redirect(url_for("inventory.movements"))

    items = Product.query.order_by(Product.name.asc()).all()

    logs = (
        Movement.query.options(
            selectinload(Movement.product),
            selectinload(Movement.user),
        )
        .order_by(Movement.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template("movements.html", products=items, movements=logs)


# ========== スタッフ管理 ==========
@inventory_bp.route("/admin/users")
@login_required
def admin_users():
    if not current_user.is_admin:
        flash("管理者のみアクセス可能です。", "warning")
        return redirect(url_for("inventory.dashboard"))

    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin_users.html", users=users)


@inventory_bp.route("/admin/users/<int:uid>/edit", methods=["GET", "POST"])
@login_required
def admin_user_edit(uid):
    if not current_user.is_admin:
        flash("管理者のみアクセス可能です。", "warning")
        return redirect(url_for("inventory.dashboard"))

    u = User.query.get_or_404(uid)

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        is_admin = True if request.form.get("is_admin") == "on" else False

        try:
            if username:
                u.username = username
            u.email = email or None
            u.is_admin = is_admin
            db.session.commit()
            flash("ユーザー情報を更新しました。", "success")
            return redirect(url_for("inventory.admin_users"))
        except Exception as e:
            db.session.rollback()
            flash(f"更新に失敗しました: {e}", "danger")

    return render_template("admin_user_edit.html", u=u)


@inventory_bp.route("/admin/users/<int:uid>/delete", methods=["POST"])
@login_required
def admin_user_delete(uid):
    if not current_user.is_admin:
        flash("管理者のみアクセス可能です。", "warning")
        return redirect(url_for("inventory.dashboard"))

    u = User.query.get_or_404(uid)
    if u.id == current_user.id:
        flash("自分自身は削除できません。", "warning")
        return redirect(url_for("inventory.admin_users"))

    try:
        db.session.delete(u)
        db.session.commit()
        flash("ユーザーを削除しました。", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"削除に失敗しました: {e}", "danger")
    return redirect(url_for("inventory.admin_users"))
