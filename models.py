# models.py
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from extensions import db, login_manager

class User(UserMixin, db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)

    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    # Flask-Login が参照するプロパティ（UserMixin でデフォルト実装あり）
    # def get_id(self): return str(self.id)


@login_manager.user_loader
def load_user(user_id: str):
    """
    セッション内の user_id からユーザーを復元。
    Flask-Login が current_user を作るときに呼ばれる。
    """
    try:
        return User.query.get(int(user_id))
    except Exception:
        return None


class Product(db.Model):
    __tablename__ = "product"
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(120), unique=True, nullable=False)
    unit = db.Column(db.String(40), nullable=False)
    min_stock = db.Column(db.Integer, default=0, nullable=False)
    supplier = db.Column(db.String(120))
    current_stock = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Movement(db.Model):
    __tablename__ = "movement"
    id = db.Column(db.Integer, primary_key=True)

    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    qty = db.Column(db.Integer, nullable=False)  # 入庫は+、出庫は- を保存
    kind = db.Column(db.String(8), nullable=False)  # 'IN' or 'OUT'
    note = db.Column(db.String(255))

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    product = db.relationship("Product", backref="movements")
    user = db.relationship("User", backref="movements")
