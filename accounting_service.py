
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4
import json

from sqlalchemy import func

from database import SessionLocal
from models import (
    Account,
    AccountingPeriod,
    JournalEntry,
    JournalEntryLine,
    AuditLog,
)


# ============================================================
# PILLISTAN ACCOUNTING SERVICE
# Journal Entry Engine
# ============================================================

CENT = Decimal("0.01")


def money(value):
    """Convert an amount safely to two-decimal Decimal."""

    try:
        amount = Decimal(str(value))

        if not amount.is_finite():
            raise ValueError("Amount must be a finite number.")

        rounded = amount.quantize(CENT)

        if amount != rounded:
            raise ValueError(
                "Amounts must not contain more than two decimal places."
            )

        return rounded

    except (InvalidOperation, TypeError):
        raise ValueError(f"Invalid monetary amount: {value}")


def generate_entry_number():
    """Generate a unique journal entry number."""

    return f"JV-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"


def write_audit_log(
    db,
    action,
    record_id,
    username,
    old_values=None,
    new_values=None,
    reason=None,
):
    """Record an accounting action in the central audit table."""

    log = AuditLog(
        module="accounting",
        action=action,
        record_type="JournalEntry",
        record_id=record_id,
        username=username,
        old_values=json.dumps(old_values) if old_values else None,
        new_values=json.dumps(new_values) if new_values else None,
        reason=reason,
    )

    db.add(log)


def find_account(db, account_code):
    """Find an account using its unique account code."""

    account = db.query(Account).filter_by(
        code=account_code
    ).first()

    if account is None:
        raise ValueError(
            f"Account code {account_code} does not exist."
        )

    if not account.is_active:
        raise ValueError(
            f"Account {account_code} is inactive."
        )

    # Prevent posting directly to parent/category accounts.
    has_children = db.query(Account.id).filter(
        Account.parent_id == account.id
    ).first()

    if has_children:
        raise ValueError(
            f"Account {account_code} is a parent account. "
            "Use a detailed child account instead."
        )

    return account


def validate_journal_lines(db, lines):
    """Validate accounts, amounts and debit/credit equality."""

    if not lines or len(lines) < 2:
        raise ValueError(
            "A journal entry must contain at least two lines."
        )

    validated_lines = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")

    for index, item in enumerate(lines, start=1):

        account = find_account(db, item["account_code"])

        debit = money(item.get("debit", 0))
        credit = money(item.get("credit", 0))

        if debit < 0 or credit < 0:
            raise ValueError("Negative amounts are not allowed.")

        # Exactly one side must contain a positive amount.
        if (debit > 0 and credit > 0) or (
            debit == 0 and credit == 0
        ):
            raise ValueError(
                f"Line {index}: Enter either a debit or a credit."
            )

        validated_lines.append({
            "account_id": account.id,
            "line_number": index,
            "description": item.get("description"),
            "debit": debit,
            "credit": credit,
        })

        total_debit += debit
        total_credit += credit

    if total_debit != total_credit:
        raise ValueError(
            f"Journal is not balanced. "
            f"Debits: {total_debit}, Credits: {total_credit}"
        )

    return validated_lines


def create_draft_entry(
    entry_date,
    description,
    lines,
    username="admin",
    source_module=None,
    reference_type=None,
    reference_id=None,
    idempotency_key=None,
    db=None,
):
    """
    Create a draft journal entry.

    Draft entries do not affect posted financial records.
    The caller is responsible for committing the database session.
    """

    owns_session = db is None
    if owns_session:
        db = SessionLocal()

    try:
        if not description or not description.strip():
            raise ValueError("Journal description is required.")

        if isinstance(entry_date, str):
            entry_date = datetime.strptime(
                entry_date, "%Y-%m-%d"
            ).date()

        if not isinstance(entry_date, datetime) and not hasattr(
            entry_date, "year"
        ):
            raise ValueError("A valid entry date is required.")

        if idempotency_key:
            existing = db.query(JournalEntry).filter_by(
                idempotency_key=idempotency_key
            ).first()

            if existing:
                raise ValueError(
                    "This transaction already has a journal entry."
                )

        validated_lines = validate_journal_lines(db, lines)

        entry = JournalEntry(
            entry_number=generate_entry_number(),
            entry_date=entry_date,
            description=description.strip(),
            source_module=source_module,
            reference_type=reference_type,
            reference_id=reference_id,
            idempotency_key=idempotency_key,
            status="draft",
            created_by=username,
        )

        db.add(entry)
        db.flush()

        for item in validated_lines:
            db.add(
                JournalEntryLine(
                    journal_entry_id=entry.id,
                    account_id=item["account_id"],
                    line_number=item["line_number"],
                    description=item["description"],
                    debit=item["debit"],
                    credit=item["credit"],
                )
            )

        write_audit_log(
            db,
            action="journal_draft_created",
            record_id=entry.id,
            username=username,
            new_values={
                "entry_number": entry.entry_number,
                "entry_date": str(entry_date),
                "status": "draft",
                "description": description,
            },
        )

        if owns_session:
            db.commit()
        else:
            db.flush()

        print("Draft journal entry created successfully.")
        print("Entry number:", entry.entry_number)
        print("Status:", entry.status)

        return entry.id

    except Exception:
        if owns_session:
            db.rollback()
        raise

    finally:
        if owns_session:
            db.close()


def post_journal_entry(entry_id, username="admin", db=None):
    """
    Post a draft journal entry after validating its accounts,
    accounting period and debit/credit balance.
    """

    if not isinstance(username, str):
        raise ValueError("Username must be a valid string.")

    username = username.strip()

    if not username:
        raise ValueError("Username cannot be blank.")

    if len(username) > 100:
        raise ValueError("Username cannot exceed 100 characters.")

    owns_session = db is None
    if owns_session:
        db = SessionLocal()

    try:
        entry = db.query(JournalEntry).filter_by(
            id=entry_id
        ).with_for_update().first()

        if entry is None:
            raise ValueError("Journal entry not found.")

        if entry.status != "draft":
            raise ValueError(
                "Only draft journal entries can be posted."
            )

        period = db.query(AccountingPeriod).filter(
            AccountingPeriod.start_date <= entry.entry_date,
            AccountingPeriod.end_date >= entry.entry_date,
        ).first()

        if period is None:
            raise ValueError(
                "No accounting period exists for this entry date."
            )

        if period.status != "open":
            raise ValueError(
                "This accounting period is closed."
            )

        original_lines = db.query(
            JournalEntryLine
        ).filter_by(
            journal_entry_id=entry.id
        ).order_by(
            JournalEntryLine.line_number
        ).all()

        lines = []

        for line in original_lines:
            account = db.query(Account).filter_by(
                id=line.account_id
            ).first()

            if account is None:
                raise ValueError("Journal account no longer exists.")

            lines.append({
                "account_code": account.code,
                "debit": line.debit,
                "credit": line.credit,
                "description": line.description,
            })

        validated_lines = validate_journal_lines(db, lines)

        total_debit = sum(
            (line["debit"] for line in validated_lines),
            Decimal("0.00"),
        )

        total_credit = sum(
            (line["credit"] for line in validated_lines),
            Decimal("0.00"),
        )

        entry.accounting_period_id = period.id
        entry.status = "posted"
        entry.posted_by = username
        entry.posted_at = datetime.now(timezone.utc).replace(
            tzinfo=None
        )

        write_audit_log(
            db,
            action="journal_entry_posted",
            record_id=entry.id,
            username=username,
            old_values={"status": "draft"},
            new_values={
                "status": "posted",
                "entry_number": entry.entry_number,
                "accounting_period_id": period.id,
                "accounting_period": period.name,
                "total_debit": str(total_debit),
                "total_credit": str(total_credit),
                "line_count": len(validated_lines),
            },
        )

        if owns_session:
            db.commit()
        else:
            db.flush()

        print("Journal entry posted successfully.")
        print("Entry number:", entry.entry_number)
        print("Accounting period:", period.name)
        print("Status:", entry.status)

    except Exception:
        if owns_session:
            db.rollback()
        raise

    finally:
        if owns_session:
            db.close()


def reverse_journal_entry(
    original_entry_id,
    reversal_date,
    reason,
    username="admin",
):
    """
    Create a posted reversal for an existing posted journal entry.

    The original entry remains unchanged. The reversal is a separate
    posted journal entry, with complete audit history.
    """

    from datetime import date, datetime

    if isinstance(reversal_date, str):
        try:
            reversal_date = date.fromisoformat(reversal_date)
        except ValueError:
            raise ValueError("Reversal date must use YYYY-MM-DD format.")

    if (
        not isinstance(reversal_date, date)
        or isinstance(reversal_date, datetime)
    ):
        raise ValueError("A valid reversal date is required.")

    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("A reversal reason is required.")

    if not isinstance(username, str) or not username.strip():
        raise ValueError("A valid username is required.")
    db = SessionLocal()

    try:
        original = (
            db.query(JournalEntry)
            .filter_by(id=original_entry_id)
            .with_for_update()
            .first()
        )

        if original is None:
            raise ValueError("Original journal entry not found.")

        if original.status != "posted":
            raise ValueError("Only a posted journal entry can be reversed.")

        existing_reversal = (
            db.query(JournalEntry)
            .filter_by(reversal_of_id=original.id)
            .first()
        )

        if existing_reversal:
            raise ValueError("This journal entry has already been reversed.")

        period = (
            db.query(AccountingPeriod)
            .filter(
                AccountingPeriod.start_date <= reversal_date,
                AccountingPeriod.end_date >= reversal_date,
            )
            .first()
        )

        if period is None:
            raise ValueError("No accounting period covers the reversal date.")

        if period.status != "open":
            raise ValueError(
                "The accounting period is closed. The reversal cannot be posted."
            )

        original_lines = (
            db.query(JournalEntryLine)
            .filter_by(journal_entry_id=original.id)
            .order_by(JournalEntryLine.line_number)
            .all()
        )

        if len(original_lines) < 2:
            raise ValueError("Original journal entry has invalid lines.")

        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")
        reversal_lines = []

        for line in original_lines:
            account = db.query(Account).filter_by(
                id=line.account_id
            ).first()

            if account is None:
                raise ValueError(
                    f"Account ID {line.account_id} no longer exists."
                )

            debit = money(line.credit)
            credit = money(line.debit)

            total_debit += debit
            total_credit += credit

            reversal_lines.append({
                "account_id": line.account_id,
                "description": (
                    f"Reversal: {line.description or original.description}"
                ),
                "debit": debit,
                "credit": credit,
            })

        if total_debit <= Decimal("0.00"):
            raise ValueError("Reversal must contain a positive debit amount.")

        if total_debit != total_credit:
            raise ValueError("Original journal entry is not balanced.")

        reversal_number = (
            f"JV-{reversal_date.strftime('%Y%m%d')}-"
            f"{uuid4().hex[:8].upper()}"
        )

        reversal = JournalEntry(
            entry_number=reversal_number,
            entry_date=reversal_date,
            description=(
                f"Reversal of {original.entry_number}: {reason.strip()}"
            ),
            source_module="accounting_reversal",
            reference_type="journal_entry",
            reference_id=original.id,
            accounting_period_id=period.id,
            idempotency_key=f"REVERSAL-{original.id}",
            status="draft",
            reversal_of_id=original.id,
            created_by=username.strip(),
        )

        db.add(reversal)
        db.flush()

        for index, line in enumerate(reversal_lines, start=1):
            db.add(
                JournalEntryLine(
                    journal_entry_id=reversal.id,
                    account_id=line["account_id"],
                    line_number=index,
                    description=line["description"],
                    debit=line["debit"],
                    credit=line["credit"],
                )
            )

        # Flush all reversal lines while the journal is still a draft.
        db.flush()

        # Post only after all lines have been inserted successfully.
        reversal.status = "posted"
        reversal.posted_by = username.strip()
        reversal.posted_at = datetime.now(timezone.utc).replace(
            tzinfo=None
        )
        db.flush()

        # Preserve the existing audit convention: the reversal's ID
        # is the record ID, and old_values identify the original entry.
        write_audit_log(
            db,
            action="reverse",
            record_id=reversal.id,
            username=username.strip(),
            old_values={
                "original_entry_id": original.id,
                "original_entry_number": original.entry_number,
            },
            new_values={
                "reversal_entry_number": reversal_number,
                "reversal_date": str(reversal_date),
                "reason": reason.strip(),
            },
            reason=reason.strip(),
        )

        # Add a second audit record linked to the original entry.
        write_audit_log(
            db,
            action="reversal_created",
            record_id=original.id,
            username=username.strip(),
            old_values={"status": "posted"},
            new_values={
                "reversal_entry_id": reversal.id,
                "reversal_entry_number": reversal_number,
                "reversal_status": "posted",
            },
            reason=reason.strip(),
        )

        db.commit()

        print("Journal entry reversed successfully.")
        print("Original entry:", original.entry_number)
        print("Reversal entry:", reversal_number)
        print("Reversal ID:", reversal.id)

        return reversal.id

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


