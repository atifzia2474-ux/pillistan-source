import argparse
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, event
from database import Base
import models
import orders_models

NEW_MODELS = [
    orders_models.CustomerAddress,
    orders_models.CustomerLabel,
    orders_models.SalesOrder,
    orders_models.SalesOrderItem,
    orders_models.OrderPayment,
    orders_models.StockReservation,
    orders_models.Courier,
    orders_models.DispatchParcel,
    orders_models.OrderStatusHistory,
]

REQUIRED_EXISTING_TABLES = {
    "customers", "products", "inventory_batches", "accounts", "app_users"
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, help="Explicit SQLite database path")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.is_file():
        raise SystemExit(f"Database file not found: {db_path}")

    with sqlite3.connect(str(db_path)) as check_db:
        existing = {
            row[0] for row in check_db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        missing = REQUIRED_EXISTING_TABLES - existing
        if missing:
            raise SystemExit(f"Required existing tables missing: {sorted(missing)}")
        before_check = check_db.execute("PRAGMA integrity_check").fetchone()[0]
        if before_check != "ok":
            raise SystemExit(f"Database integrity check failed before migration: {before_check}")

    engine = create_engine("sqlite:///" + db_path.as_posix())

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    tables = [model.__table__ for model in NEW_MODELS]
    Base.metadata.create_all(bind=engine, tables=tables)

    with sqlite3.connect(str(db_path)) as check_db:
        after_check = check_db.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = check_db.execute("PRAGMA foreign_key_check").fetchall()
        created = {
            row[0] for row in check_db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        expected = {table.name for table in tables}
        missing_new = expected - created

        if after_check != "ok":
            raise SystemExit(f"Integrity check failed after migration: {after_check}")
        if foreign_keys:
            raise SystemExit(f"Foreign key check reported problems: {foreign_keys[:10]}")
        if missing_new:
            raise SystemExit(f"New tables missing: {sorted(missing_new)}")

        print("ISOLATED ORDERS SCHEMA MIGRATION PASSED")
        print(f"Database tested: {db_path}")
        print(f"New tables created/verified: {len(expected)}")
        for name in sorted(expected):
            print(f"  - {name}")
        print("SQLite integrity check: OK")
        print("Foreign key check: OK")
        print("No orders or stock records were inserted.")

    engine.dispose()

if __name__ == "__main__":
    main()
