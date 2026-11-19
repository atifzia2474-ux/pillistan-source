import models
import orders_models
import returns_module
from database import Base, engine

Base.metadata.create_all(bind=engine)

with engine.connect() as connection:
    integrity = connection.exec_driver_sql("PRAGMA integrity_check").scalar()
    foreign_keys = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    print("Database:", engine.url.database)
    print("Integrity check:", integrity)
    print("Foreign-key violations:", len(foreign_keys))
    for table in ("return_requests", "return_items", "return_inspections", "return_refunds"):
        exists = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        ).scalar()
        print(f"{table}: {'OK' if exists else 'MISSING'}")

if integrity != "ok" or foreign_keys:
    raise SystemExit("Returns migration validation failed.")
print("Returns schema migration: PASS")
