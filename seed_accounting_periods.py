
from datetime import date
from calendar import monthrange

from database import SessionLocal
from models import AccountingPeriod


# ============================================================
# PILLISTAN - FINANCIAL YEAR 2026-27
# July 2026 to June 2027
# ============================================================

FINANCIAL_YEAR_START = 2026
FINANCIAL_YEAR_END = 2027

MONTHS = [
    (7, 2026, "July"),
    (8, 2026, "August"),
    (9, 2026, "September"),
    (10, 2026, "October"),
    (11, 2026, "November"),
    (12, 2026, "December"),
    (1, 2027, "January"),
    (2, 2027, "February"),
    (3, 2027, "March"),
    (4, 2027, "April"),
    (5, 2027, "May"),
    (6, 2027, "June"),
]


def seed_accounting_periods():
    db = SessionLocal()

    created = 0
    skipped = 0

    try:
        for month, year, month_name in MONTHS:

            start_date = date(year, month, 1)

            last_day = monthrange(year, month)[1]
            end_date = date(year, month, last_day)

            period_name = (
                f"FY {FINANCIAL_YEAR_START}-"
                f"{str(FINANCIAL_YEAR_END)[-2:]} "
                f"- {month_name} {year}"
            )

            existing = db.query(AccountingPeriod).filter(
                AccountingPeriod.start_date == start_date,
                AccountingPeriod.end_date == end_date
            ).first()

            if existing:
                print(f"SKIPPED: {existing.name}")
                skipped += 1
                continue

            overlapping = db.query(AccountingPeriod).filter(
                AccountingPeriod.start_date <= end_date,
                AccountingPeriod.end_date >= start_date
            ).first()

            if overlapping:
                raise ValueError(
                    f"Date overlap with existing period: "
                    f"{overlapping.name}"
                )

            period = AccountingPeriod(
                name=period_name,
                start_date=start_date,
                end_date=end_date,
                status="open"
            )

            db.add(period)
            created += 1

        db.commit()

        print("\nAccounting period setup completed!")
        print(f"Periods created: {created}")
        print(f"Existing periods skipped: {skipped}")
        print(f"Total periods planned: {len(MONTHS)}")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed_accounting_periods()
