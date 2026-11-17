import sqlite3
from pathlib import Path

from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    database = g.pop("db", None)
    if database is not None:
        database.close()


def init_db():
    database = get_db()
    schema_path = Path(current_app.root_path) / "database" / "schema.sql"
    database.executescript(schema_path.read_text(encoding="utf-8"))
    food_columns = {
        row["name"] for row in database.execute("PRAGMA table_info(food_items)")
    }
    if "stock_quantity" not in food_columns:
        database.execute(
            "ALTER TABLE food_items ADD COLUMN stock_quantity "
            "INTEGER NOT NULL DEFAULT 100 CHECK (stock_quantity >= 0)"
        )
    order_columns = {
        row["name"] for row in database.execute("PRAGMA table_info(orders)")
    }
    new_order_columns = {
        "subtotal": "INTEGER NOT NULL DEFAULT 0 CHECK (subtotal >= 0)",
        "delivery_fee": "INTEGER NOT NULL DEFAULT 0 CHECK (delivery_fee >= 0)",
        "delivery_address": "TEXT NOT NULL DEFAULT ''",
        "delivery_phone": "TEXT NOT NULL DEFAULT ''",
        "assigned_to": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
        "demo_auto_progress": (
            "INTEGER NOT NULL DEFAULT 0 CHECK (demo_auto_progress IN (0, 1))"
        ),
        "tracking_status": (
            "TEXT NOT NULL DEFAULT 'Order Accepted' CHECK (tracking_status IN "
            "('Order Accepted', 'Preparing', 'Ready for Pickup', "
            "'Out for Delivery', 'Delivered', 'Cancelled'))"
        ),
    }
    for column, definition in new_order_columns.items():
        if column not in order_columns:
            database.execute(f"ALTER TABLE orders ADD COLUMN {column} {definition}")
    if "tracking_status" not in order_columns:
        database.execute(
            """
            UPDATE orders
            SET tracking_status = CASE status
                WHEN 'Preparing' THEN 'Preparing'
                WHEN 'Out for delivery' THEN 'Out for Delivery'
                WHEN 'Delivered' THEN 'Delivered'
                WHEN 'Cancelled' THEN 'Cancelled'
                ELSE 'Order Accepted'
            END
            """
        )
    database.execute(
        """
        UPDATE orders
        SET subtotal = total
        WHERE subtotal = 0 AND total > 0
          AND delivery_address = '' AND delivery_phone = ''
        """
    )
    database.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
