# inventory.py
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from sqlalchemy import func, case, or_
from sqlalchemy.orm import selectinload

from extensions import db
from models import User, Product, Movement

inventory_bp = Blueprint("inventory", __name__)

# --- Postgres/SQLite どちらでも安全に起動できるように、ここでは no-op ---
def ensure_columns(db_):
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
        else:
            app.logger.info("[INIT] admin already exists")


# ====== 在庫一覧（ダッシュボード） ======
@inventory_bp.route("/dashboard")
@login_required
def dashboard():
    # --- クエリパラメータ（テンプレが期待する名前） ---
    q = request.args.get("q", "").strip()
    kind = (request.args.get("kind") or "").upper()  # '', 'IN', 'OUT'
    prod_selected_raw = request.args.get("prod", "").strip()
    prod_selected = None
    if prod_selected_raw.isdigit():
        prod_selected = int(prod_selected_raw)

    # --- 商品一覧（表の左側）: 商品名 or 仕入れ先 でフィルタ ---
    product_query = Product.query
    if q:
        like = f"%{q}%"
        product_query = product_query.filter(
            or_(Product.name.ilike(like), Product.supplier.ilike(like))
        )
    products = product_query.order_by(Product.name.asc()).all()

    # --- 在庫集計 qty_map[product_id] = 入庫合計 - 出庫合計 ---
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

    # --- 履歴候補（最新から）: optional フィルタ kind/prod/q で絞り込み、上位10件 ---
    mv_q = (
        Movement.query.options(
            selectinload(Movement.product),
            selectinload(Movement.user),
        )
        .order_by(Movement.created_at.desc())
    )

    if kind in ("IN", "OUT"):
        mv_q = mv_q.filter(Movement.movement_type == ("in" if kind == "IN" else "out"))

    if prod_selected:
        mv_q = mv_q.filter(Movement.product_id == prod_selected)

    # 「q」が指定されているとき、履歴側も商品名 or 仕入れ先にかかるように（任意）
    if q:
        like = f"%{q}%"
        mv_q = mv_q.join(Product, Movement.product_id == Product.id).filter(
            or_(Product.name.ilike(like), Product.supplier.ilike(like))
        )

    recent10 = mv_q.limit(10).all()

    # 履歴フィルタ用の「商品セレクト」候補（全部）
    filter_products = Product.query.order_by(Product.name.asc()).all()

    return render_template(
        "dashboard.html",
        # テンプレが期待する変数
        q=q,
        kind=kind,
        filter_products=filter_products,
        prod_selected=prod_selected,
        recent10=recent10,
        # 表示用
        products=products,
        qty_map=qty_map,
    )


# ====== 商品 ======
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

        if not name or not unit:
            flash("商品名と単位は必須です。", "danger")
        else:
            try:
                p = Product(
                    name=name,
                    unit=unit,
                    min_stock=int(min_stock) if min_stock else 0,
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
            if name:
                p.name = name
            if unit:
                p.unit = unit
            p.min_stock = int(min_stock) if min_stock else p.min_stock
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


# ====== 入出庫 ======
@inventory_bp.route("/movements", methods=["GET", "POST"])
@login_required
def movements():
    if request.method == "POST":
        raw_product_id = request.form.get("product_id")
        raw_mtype = request.form.get("movement_type")
        raw_qty = request.form.get("quantity")
        note = request.form.get("note", "").strip()

        current_app.logger.info(
            f"[POST /movements] product_id={raw_product_id}, movement_type={raw_mtype}, quantity={raw_qty}, note={note}"
        )

        errors = []
        try:
            product_id = int(raw_product_id) if raw_product_id is not None else 0
            if product_id <= 0:
                errors.append("商品が選択されていません。")
        except Exception:
            errors.append("商品IDが不正です。")

        movement_type = (raw_mtype or "").strip().lower()
        if movement_type not in ("in", "out"):
            errors.append("区分は「入庫(in) / 出庫(out)」から選択してください。")

        try:
            qty = int(raw_qty) if raw_qty is not None else 0
            if qty <= 0:
                errors.append("数量は1以上の整数で入力してください。")
        except Exception:
            errors.append("数量は整数で入力してください。")

        if errors:
            for m in errors:
                flash(m, "danger")
            return redirect(url_for("inventory.movements"))

        try:
            mv = Movement(
                product_id=product_id,
                movement_type=movement_type,
                quantity=qty,
                note=note or None,
                user_id=current_user.id,
                created_at=datetime.utcnow(),
            )
            db.session.add(mv)
            db.session.commit()
            flash("入出庫を記録しました。", "success")
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("[POST /movements] DB error")
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


# ====== スタッフ管理 ======
@inventory_bp.route("/admin/users")
@login_required
def admin_users():
    if not current_user.is_admin:
        flash("管理者のみアクセス可能です。", "warning")
        return redirect(url_for("inventory.dashboard"))

    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin_users.html", users=users)


@inventory_bp.route("/admin/users/add", methods=["GET", "POST"])
@login_required
def admin_user_add():
    if not current_user.is_admin:
        flash("管理者のみアクセス可能です。", "warning")
        return redirect(url_for("inventory.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        is_admin = True if request.form.get("is_admin") == "on" else False

        if not username or not email or not password:
            flash("ユーザー名・メール・パスワードは必須です。", "danger")
            return redirect(url_for("inventory.admin_user_add"))

        if User.query.filter_by(username=username).first():
            flash("そのユーザー名は既に存在します。", "danger")
            return redirect(url_for("inventory.admin_user_add"))
        if User.query.filter_by(email=email).first():
            flash("そのメールアドレスは既に登録済みです。", "danger")
            return redirect(url_for("inventory.admin_user_add"))

        try:
            u = User(username=username, email=email, is_admin=is_admin)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            flash("スタッフを追加しました。", "success")
            return redirect(url_for("inventory.admin_users"))
        except Exception as e:
            db.session.rollback()
            flash(f"追加に失敗しました: {e}", "danger")
            return redirect(url_for("inventory.admin_user_add"))

    return render_template("admin_user_add.html")


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