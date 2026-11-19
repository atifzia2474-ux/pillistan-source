"""One-time, backup-first migration for per-product stock thresholds."""
import sqlite3
from pathlib import Path

from auth_manager import DB_PATH
from backup_service import create_verified_backup, verify_database


def migrate():
    database_path = Path(DB_PATH).resolve()
    if not database_path.exists():
        raise FileNotFoundError(f"Pillistan database not found: {database_path}")

    check = sqlite3.connect(str(database_path), timeout=30)
    try:
        columns = {
            row[1] for row in check.execute("PRAGMA table_info(products)")
        }
    finally:
        check.close()

    if "low_stock_threshold" in columns:
        print("PASS: products.low_stock_threshold already exists. No migration needed.")
        return

    backup_folder = Path.home() / "PillistanBackups"
    backup_path = create_verified_backup(
        database_path, backup_folder, prefix="before_threshold_migration"
    )
    print(f"Verified pre-migration backup: {backup_path}")

    connection = sqlite3.connect(str(database_path), timeout=30)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """ALTER TABLE products
               ADD COLUMN low_stock_threshold INTEGER
               CHECK (low_stock_threshold IS NULL OR low_stock_threshold >= 0)"""
        )
        connection.commit()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"Post-migration integrity check failed: {integrity}")
    except Exception:
        connection.rollback()
        connection.close()

        # Restore the verified pre-migration database if the migration fails.
        source = sqlite3.connect(str(backup_path), timeout=30)
        destination = sqlite3.connect(str(database_path), timeout=30)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        verify_database(database_path)
        raise
    else:
        connection.close()

    verify_database(database_path)
    print("PASS: products.low_stock_threshold added.")
    print("PASS: live database integrity check is OK.")
    print("Migration completed. Your existing product records are preserved.")


if __name__ == "__main__":
    migrate()
