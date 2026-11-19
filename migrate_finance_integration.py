"""Safe schema/account migration for the Pillistan Finance integration upgrade.

Run only after setting PILLISTAN_DATABASE_URL to the development database.
This migration creates missing model tables and seeds missing chart accounts;
it does not rewrite existing journal entries or transaction history.
"""
import models  # noqa: F401 - register core tables
import orders_models  # noqa: F401 - register order/courier tables
import returns_module  # noqa: F401 - register return tables

from database import Base, engine, SessionLocal
from models import Account
from seed_chart_of_accounts import seed_chart_of_accounts


def migrate():
    database_name = engine.url.database
    if not database_name:
        raise RuntimeError("A file-backed SQLite development database is required.")

    Base.metadata.create_all(bind=engine)
    seed_chart_of_accounts()

    # A supplier payment receipt reference must be globally unique when present.
    with engine.begin() as connection:
        duplicates = connection.exec_driver_sql(
            """
            SELECT LOWER(TRIM(reference_number)) AS normalized_reference, COUNT(*) AS total
            FROM supplier_payments
            WHERE reference_number IS NOT NULL AND TRIM(reference_number) <> ''
            GROUP BY LOWER(TRIM(reference_number))
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        if duplicates:
            raise RuntimeError(
                "Duplicate supplier payment references already exist. "
                "Resolve these before applying the uniqueness index: "
                + ", ".join(str(row[0]) for row in duplicates[:10])
            )
        connection.exec_driver_sql(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_supplier_payments_reference_number_ci
            ON supplier_payments(LOWER(TRIM(reference_number)))
            WHERE reference_number IS NOT NULL AND TRIM(reference_number) <> ''
            """
        )

    db = SessionLocal()
    try:
        transit = db.query(Account).filter_by(code="1180").one_or_none()
        if transit is None:
            raise RuntimeError("Required account 1180 was not created.")
        parent = db.get(Account, transit.parent_id) if transit.parent_id else None
        if (transit.name != "Inventory in Transit"
                or transit.account_type != "asset"
                or transit.normal_balance != "debit"
                or parent is None or parent.code != "1100"
                or not transit.is_active):
            raise RuntimeError(
                "Account 1180 exists but does not match the required Inventory in Transit configuration. "
                "No existing account was overwritten."
            )
    finally:
        db.close()

    with engine.connect() as connection:
        integrity = connection.exec_driver_sql("PRAGMA integrity_check").scalar()
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if integrity != "ok" or foreign_keys:
        raise RuntimeError(
            f"Database validation failed: integrity={integrity}; foreign_key_violations={len(foreign_keys)}"
        )
    print(f"Finance integration migration: PASS ({database_name})")
    print("Inventory in Transit account 1180: verified")
    print("Existing journal history: preserved")
    print("SQLite integrity and foreign keys: PASS")


if __name__ == "__main__":
    migrate()
