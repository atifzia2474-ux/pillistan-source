import json
from datetime import date, datetime

from database import SessionLocal
from models import AccountingPeriod, JournalEntry, OpeningBalance, AuditLog


def _validate_username(username):
    if not isinstance(username, str):
        raise ValueError("A valid username is required.")

    username = username.strip()

    if not username or len(username) > 100:
        raise ValueError("Username must contain 1 to 100 characters.")

    return username


def _validate_reason(reason):
    if not isinstance(reason, str):
        raise ValueError("A reason is required.")

    reason = reason.strip()

    if not reason or len(reason) > 2000:
        raise ValueError("Reason must contain 1 to 2000 characters.")

    return reason


def _validate_date(value, field_name):
    if type(value) is not date:
        raise ValueError(f"{field_name} must be a date object.")


def _period_values(period):
    return {
        "period_id": period.id,
        "name": period.name,
        "start_date": period.start_date.isoformat(),
        "end_date": period.end_date.isoformat(),
        "status": period.status,
    }


def _write_period_audit(
    db, period, action, username, old_values, new_values, reason
):
    db.add(
        AuditLog(
            module="accounting_periods",
            action=action,
            record_type="AccountingPeriod",
            record_id=period.id,
            username=username,
            old_values=(
                json.dumps(old_values, sort_keys=True)
                if old_values is not None else None
            ),
            new_values=json.dumps(new_values, sort_keys=True),
            reason=reason,
        )
    )


def create_accounting_period(
    name, start_date, end_date, username, reason
):
    username = _validate_username(username)
    reason = _validate_reason(reason)

    if not isinstance(name, str):
        raise ValueError("Period name is required.")

    name = name.strip()

    if not name or len(name) > 100:
        raise ValueError("Period name must contain 1 to 100 characters.")

    _validate_date(start_date, "Start date")
    _validate_date(end_date, "End date")

    if end_date < start_date:
        raise ValueError("End date cannot precede start date.")

    db = SessionLocal()

    try:
        duplicate_name = db.query(AccountingPeriod).filter(
            AccountingPeriod.name == name
        ).first()

        if duplicate_name:
            raise ValueError("An accounting period with this name already exists.")

        overlap = db.query(AccountingPeriod).filter(
            AccountingPeriod.start_date <= end_date,
            AccountingPeriod.end_date >= start_date,
        ).first()

        if overlap:
            raise ValueError(
                f"Date range overlaps existing period: {overlap.name}."
            )

        period = AccountingPeriod(
            name=name,
            start_date=start_date,
            end_date=end_date,
            status="open",
        )

        db.add(period)
        db.flush()

        _write_period_audit(
            db,
            period,
            "accounting_period_created",
            username,
            None,
            _period_values(period),
            reason,
        )

        db.commit()
        return period.id

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def close_accounting_period(period_id, username, reason):
    username = _validate_username(username)
    reason = _validate_reason(reason)

    db = SessionLocal()

    try:
        period = db.query(AccountingPeriod).filter_by(
            id=period_id
        ).first()

        if period is None:
            raise ValueError("Accounting period not found.")

        if period.status != "open":
            raise ValueError("Only open accounting periods can be closed.")

        if period.end_date >= date.today():
            raise ValueError(
                "A period can only be closed after its end date."
            )

        draft_journals = db.query(JournalEntry).filter(
            JournalEntry.status == "draft",
        ).filter(
            (JournalEntry.accounting_period_id == period.id)
            | (
                (JournalEntry.entry_date >= period.start_date)
                & (JournalEntry.entry_date <= period.end_date)
            )
        ).count()

        if draft_journals:
            raise ValueError(
                f"Cannot close period: {draft_journals} draft journal(s) "
                "are linked to or dated within this period."
            )

        draft_openings = db.query(OpeningBalance).filter(
            OpeningBalance.opening_date >= period.start_date,
            OpeningBalance.opening_date <= period.end_date,
            OpeningBalance.status == "draft",
        ).count()

        if draft_openings:
            raise ValueError(
                f"Cannot close period: {draft_openings} draft opening "
                "balance(s) remain within its date range."
            )

        old_values = _period_values(period)
        new_values = dict(old_values)
        new_values["status"] = "closed"

        _write_period_audit(
            db,
            period,
            "accounting_period_closed",
            username,
            old_values,
            new_values,
            reason,
        )
        db.flush()

        period.status = "closed"
        db.commit()
        return True

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def reopen_accounting_period(period_id, username, reason):
    username = _validate_username(username)
    reason = _validate_reason(reason)

    db = SessionLocal()

    try:
        period = db.query(AccountingPeriod).filter_by(
            id=period_id
        ).first()

        if period is None:
            raise ValueError("Accounting period not found.")

        if period.status != "closed":
            raise ValueError("Only closed accounting periods can be reopened.")

        old_values = _period_values(period)
        new_values = dict(old_values)
        new_values["status"] = "open"

        _write_period_audit(
            db,
            period,
            "accounting_period_reopened",
            username,
            old_values,
            new_values,
            reason,
        )
        db.flush()

        period.status = "open"
        db.commit()
        return True

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
