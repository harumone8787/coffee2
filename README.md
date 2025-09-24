# Coffee2 在庫管理アプリ

Flask + SQLAlchemy + Render(PostgreSQL) を使ったシンプルで拡張可能な在庫管理アプリです。  
管理者とスタッフの権限を分け、商品管理・入出庫管理・履歴表示・パスワードリセット機能を備えています。  
レスポンシブ対応済みで、スマートフォンからも快適に利用可能です。

---

## 🚀 主な機能

- **ログイン / ログアウト**
  - Flask-Login を利用したユーザー認証
- **ユーザー管理**
  - 管理者のみがスタッフを追加・編集・削除可能
- **商品管理**
  - 商品の登録 / 編集 / 削除（管理者のみ）
  - 最低在庫数の設定
- **入出庫管理**
  - 入庫 / 出庫の記録
  - 在庫数の自動更新
- **履歴管理**
  - 最新10件の入出庫履歴を一覧表示
  - PCは表形式、スマホはカード形式で見やすく表示
- **パスワードリセット**
  - メール経由でパスワード再設定リンクを送信
- **UI**
  - レスポンシブ対応
  - 管理者とスタッフ、入庫と出庫で色分けされたアイコン表示

---

## 🛠 技術スタック

- **言語 / フレームワーク**
  - Python 3.13
  - Flask 3.x
- **ライブラリ**
  - Flask-Login
  - Flask-SQLAlchemy
  - Flask-Mail
- **DB**
  - PostgreSQL（本番環境）
  - SQLite（ローカル開発用）
- **本番サーバ**
  - Gunicorn
  - Render（デプロイ先）

---

## 📦 セットアップ方法（ローカル）

```bash
# リポジトリをクローン
git clone https://github.com/harumone8787/coffee2.git
cd coffee2

# 仮想環境作成＆有効化
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 必要なパッケージをインストール
pip install -r requirements.txt

# アプリを起動
python app.py
