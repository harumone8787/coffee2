from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, abort
from flask_login import login_required, current_user
from sqlalchemy import text, or_
from extensions import db
from models import Product, Movement, User

inventory_bp = Blueprint("inventory", __name__, url_prefix="")

# --------- 起動時の初期化系 ---------
def ensure_admin(app):
    """初期管理者の投入"""
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username="admin").first():
            admin = User(username="admin", email="admin@example.com", is_admin=True, is_active=True)
            admin.set_password("admin0123")
            db.session.add(admin)
            db.session.commit()
            app.logger.info("Created default admin (admin/admin0123).")

def ensure_columns(db):
    """既存DBに is_active カラムが無ければ追加（SQLite想定）"""
    try:
        # Users
        res = db.session.execute(text("PRAGMA table_info(user);")).mappings().all()
        cols = {r["name"] for r in res}
        if "is_active" not in cols:
            db.session.execute(text("ALTER TABLE user ADD COLUMN is_active BOOLEAN DEFAULT 1;"))
            db.session.commit()
        # Products
        res = db.session.execute(text("PRAGMA table_info(product);")).mappings().all()
        cols = {r["name"] for r in res}
        if "is_active" not in cols:
            db.session.execute(text("ALTER TABLE product ADD COLUMN is_active BOOLEAN DEFAULT 1;"))
            db.session.commit()
    except Exception as e:
        current_app.logger.warning(f"ensure_columns skipped/failed: {e}")

def require_admin():
    if not current_user.is_admin:
        abort(403)

# --------- ダッシュボード（在庫一覧＋最新履歴10件） ---------
@inventory_bp.route("/dashboard")
@login_required
def dashboard():
    # 商品検索（名前/仕入れ先）
    q = (request.args.get("q") or "").strip()
    prod_q = Product.query.filter_by(is_active=True)
    if q:
        like = f"%{q}%"
        # SQLiteは ilike が like と同等でもOK（case-insensitive想定）
        try:
            prod_q = prod_q.filter(or_(Product.name.ilike(like), Product.supplier.ilike(like)))
        except Exception:
            prod_q = prod_q.filter(or_(Product.name.like(like), Product.supplier.like(like)))
    products = prod_q.order_by(Product.name.asc()).all()

    # 履歴フィルタ（区分/商品）
    kind = (request.args.get("kind") or "").upper()  # IN / OUT / ''
    prod_id = request.args.get("prod")
    mov_q = Movement.query.order_by(Movement.created_at.desc())
    if kind in {"IN", "OUT"}:
        mov_q = mov_q.filter(Movement.kind == kind)
    if prod_id and prod_id.isdigit():
        mov_q = mov_q.filter(Movement.product_id == int(prod_id))
    recent10 = mov_q.limit(10).all()

    # フィルタUI用：商品一覧（アクティブ）
    filter_products = Product.query.filter_by(is_active=True).order_by(Product.name.asc()).all()

    return render_template(
        "dashboard.html",
        products=products,
        recent10=recent10,
        q=q, kind=kind, prod_selected=int(prod_id) if prod_id and prod_id.isdigit() else None,
        filter_products=filter_products
    )

# --------- 商品（一覧・登録・編集・削除=ソフト削除） ---------
@inventory_bp.route("/products", methods=["GET", "POST"])
@login_required
def products():
    # 登録は管理者のみ
    if request.method == "POST":
        if not current_user.is_admin:
            abort(403)
        name = request.form.get("name", "").strip()
        unit = request.form.get("unit", "").strip()
        min_stock = int(request.form.get("min_stock", "0") or 0)
        supplier = request.form.get("supplier", "").strip()
        if not name or not unit:
            flash("商品名と単位は必須です。", "danger")
            return redirect(url_for("inventory.products"))
        if Product.query.filter_by(name=name).first():
            flash("同名の商品が既に存在します。", "warning")
            return redirect(url_for("inventory.products"))
        p = Product(name=name, unit=unit, min_stock=min_stock, supplier=supplier, is_active=True)
        db.session.add(p)
        db.session.commit()
        flash("商品を登録しました。", "success")
        return redirect(url_for("inventory.products"))

    # 一覧はアクティブのみ
    products = Product.query.filter_by(is_active=True).order_by(Product.created_at.desc()).all()
    return render_template("products.html", products=products)

@inventory_bp.route("/products/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def product_edit(pid):
    require_admin()
    p = Product.query.get_or_404(pid)
    if request.method == "POST":
        p.name = request.form.get("name", "").strip()
        p.unit = request.form.get("unit", "").strip()
        p.min_stock = int(request.form.get("min_stock", "0") or 0)
        p.supplier = request.form.get("supplier", "").strip()
        if not p.name or not p.unit:
            flash("商品名と単位は必須です。", "danger")
            return redirect(url_for("inventory.product_edit", pid=pid))
        db.session.commit()
        flash("商品を更新しました。", "success")
        return redirect(url_for("inventory.products"))
    return render_template("product_edit.html", p=p)

@inventory_bp.route("/products/<int:pid>/delete", methods=["POST"])
@login_required
def product_delete(pid):
    require_admin()
    p = Product.query.get_or_404(pid)
    p.is_active = False  # ソフト削除
    db.session.commit()
    flash("商品を削除（非表示）にしました。履歴は維持されます。", "warning")
    return redirect(url_for("inventory.products"))

# --------- 入出庫（登録・履歴50件表示） ---------
@inventory_bp.route("/movements", methods=["GET", "POST"])
@login_required
def movements():
    products = Product.query.filter_by(is_active=True).order_by(Product.name.asc()).all()
    if request.method == "POST":
        product_id = int(request.form.get("product_id"))
        kind = request.form.get("kind")  # 'IN' or 'OUT'
        qty = int(request.form.get("qty", "0") or 0)
        note = request.form.get("note", "").strip()
        product = Product.query.get_or_404(product_id)
        if not product.is_active:
            flash("無効化された商品です。入出庫できません。", "danger")
            return redirect(url_for("inventory.movements"))
        if kind not in {"IN", "OUT"}:
            flash("入出庫区分が不正です。", "danger")
            return redirect(url_for("inventory.movements"))
        signed_qty = qty if kind == "IN" else -qty
        if product.current_stock + signed_qty < 0:
            flash("在庫が不足しています。", "danger")
            return redirect(url_for("inventory.movements"))
        m = Movement(product_id=product.id, user_id=current_user.id, qty=signed_qty, kind=kind, note=note)
        product.current_stock += signed_qty
        db.session.add(m)
        db.session.commit()
        flash("在庫を更新しました。", "success")
        return redirect(url_for("inventory.movements"))
    recent = Movement.query.order_by(Movement.created_at.desc()).limit(50).all()
    return render_template("movements.html", products=products, recent=recent)

# --------- スタッフ管理（一覧・追加・編集・停止） ---------
@inventory_bp.route("/admin/users", methods=["GET", "POST"])
@login_required
def admin_users():
    require_admin()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        if not username or not email or not password:
            flash("全ての項目を入力してください。", "danger")
            return redirect(url_for("inventory.admin_users"))
        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash("そのユーザー名またはメールは既に使われています。", "danger")
            return redirect(url_for("inventory.admin_users"))
        user = User(username=username, email=email, is_admin=False, is_active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("スタッフを追加しました。", "success")
        return redirect(url_for("inventory.admin_users"))
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin_users.html", users=users)

@inventory_bp.route("/admin/users/<int:uid>/edit", methods=["GET", "POST"])
@login_required
def admin_user_edit(uid):
    """★ 今回のエラーの原因：このルートが欠けていたので復活させました。"""
    require_admin()
    u = User.query.get_or_404(uid)
    if request.method == "POST":
        u.username = request.form.get("username", "").strip()
        u.email = request.form.get("email", "").strip()
        u.is_admin = (request.form.get("is_admin") == "on")
        u.is_active = (request.form.get("is_active") == "on")
        if not u.username or not u.email:
            flash("ユーザー名とメールは必須です。", "danger")
            return redirect(url_for("inventory.admin_user_edit", uid=uid))
        db.session.commit()
        flash("ユーザー情報を更新しました。", "success")
        return redirect(url_for("inventory.admin_users"))
    return render_template("admin_user_edit.html", u=u)

@inventory_bp.route("/admin/users/<int:uid>/delete", methods=["POST"])
@login_required
def admin_user_delete(uid):
    """物理削除ではなく停止（ソフト削除）"""
    require_admin()
    u = User.query.get_or_404(uid)
    u.is_active = False
    db.session.commit()
    flash("ユーザーを停止しました（履歴は維持）。", "warning")
    return redirect(url_for("inventory.admin_users"))
