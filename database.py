import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

# Local Pillistan database
DATABASE_URL = os.environ.get("PILLISTAN_DATABASE_URL", "sqlite:///./pk_skincare_ops.db")

# Create database connection
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    """Enable SQLite foreign-key enforcement on every new connection."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()

# Create database sessions
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for all database models
Base = declarative_base()


def install_journal_immutability_triggers(connection):
    """
    Install SQLite-level accounting protections.

    New journals must begin as drafts. A journal can become posted
    only when its lines balance and its accounting period is open.
    Posted journals and their lines cannot subsequently be changed.
    """

    statements = [
        """
        CREATE TRIGGER IF NOT EXISTS trg_journal_insert_draft_only
        BEFORE INSERT ON journal_entries
        WHEN NEW.status <> 'draft'
        BEGIN
            SELECT RAISE(
                ABORT,
                'New journal entries must begin as drafts.'
            );
        END
        """,

        """
        CREATE TRIGGER IF NOT EXISTS trg_journal_posted_immutable
        BEFORE UPDATE ON journal_entries
        WHEN OLD.status = 'posted'
        BEGIN
            SELECT RAISE(
                ABORT,
                'Posted journal entries are immutable. Use a reversal or adjustment.'
            );
        END
        """,

        """
        CREATE TRIGGER IF NOT EXISTS trg_journal_posted_delete
        BEFORE DELETE ON journal_entries
        WHEN OLD.status = 'posted'
        BEGIN
            SELECT RAISE(
                ABORT,
                'Posted journal entries cannot be deleted.'
            );
        END
        """,

        """
        CREATE TRIGGER IF NOT EXISTS trg_journal_valid_status
        BEFORE UPDATE OF status ON journal_entries
        WHEN OLD.status <> 'draft'
             OR NEW.status NOT IN ('draft', 'posted')
        BEGIN
            SELECT RAISE(
                ABORT,
                'Invalid journal status transition.'
            );
        END
        """,

        """
        CREATE TRIGGER IF NOT EXISTS trg_journal_validate_posting
        BEFORE UPDATE OF status ON journal_entries
        WHEN OLD.status = 'draft' AND NEW.status = 'posted'
        BEGIN
            SELECT CASE
                WHEN NEW.accounting_period_id IS NULL
                OR NOT EXISTS (
                    SELECT 1
                    FROM accounting_periods p
                    WHERE p.id = NEW.accounting_period_id
                      AND p.status = 'open'
                      AND p.start_date <= NEW.entry_date
                      AND p.end_date >= NEW.entry_date
                )
                THEN RAISE(
                    ABORT,
                    'Journal requires a valid open accounting period.'
                )
            END;

            SELECT CASE
                WHEN (
                    SELECT COUNT(*)
                    FROM journal_entry_lines l
                    WHERE l.journal_entry_id = NEW.id
                ) < 2
                THEN RAISE(
                    ABORT,
                    'A journal requires at least two lines.'
                )
            END;

            SELECT CASE
                WHEN (
                    SELECT COALESCE(SUM(l.debit), 0)
                    FROM journal_entry_lines l
                    WHERE l.journal_entry_id = NEW.id
                ) <= 0
                OR (
                    SELECT COALESCE(SUM(l.debit), 0)
                    FROM journal_entry_lines l
                    WHERE l.journal_entry_id = NEW.id
                ) <> (
                    SELECT COALESCE(SUM(l.credit), 0)
                    FROM journal_entry_lines l
                    WHERE l.journal_entry_id = NEW.id
                )
                THEN RAISE(
                    ABORT,
                    'Journal debit and credit totals must be equal and positive.'
                )
            END;

            SELECT CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM journal_entry_lines l
                    JOIN accounts a ON a.id = l.account_id
                    WHERE l.journal_entry_id = NEW.id
                      AND (
                          a.is_active <> 1
                          OR EXISTS (
                              SELECT 1
                              FROM accounts child
                              WHERE child.parent_id = a.id
                          )
                      )
                )
                THEN RAISE(
                    ABORT,
                    'Journal contains an inactive or parent account.'
                )
            END;
        END
        """,

        """
        CREATE TRIGGER IF NOT EXISTS trg_journal_line_insert_draft
        BEFORE INSERT ON journal_entry_lines
        WHEN COALESCE(
            (
                SELECT status
                FROM journal_entries
                WHERE id = NEW.journal_entry_id
            ),
            ''
        ) <> 'draft'
        BEGIN
            SELECT RAISE(
                ABORT,
                'Journal lines can only be added to draft entries.'
            );
        END
        """,

        """
        CREATE TRIGGER IF NOT EXISTS trg_journal_line_update_draft
        BEFORE UPDATE ON journal_entry_lines
        WHEN COALESCE(
            (
                SELECT status
                FROM journal_entries
                WHERE id = OLD.journal_entry_id
            ),
            ''
        ) <> 'draft'
        OR COALESCE(
            (
                SELECT status
                FROM journal_entries
                WHERE id = NEW.journal_entry_id
            ),
            ''
        ) <> 'draft'
        BEGIN
            SELECT RAISE(
                ABORT,
                'Lines belonging to posted journals cannot be changed.'
            );
        END
        """,

        """
        CREATE TRIGGER IF NOT EXISTS trg_journal_line_delete_draft
        BEFORE DELETE ON journal_entry_lines
        WHEN COALESCE(
            (
                SELECT status
                FROM journal_entries
                WHERE id = OLD.journal_entry_id
            ),
            ''
        ) <> 'draft'
        BEGIN
            SELECT RAISE(
                ABORT,
                'Lines belonging to posted journals cannot be deleted.'
            );
        END
        """,
    ]

    cursor = connection.cursor()
    try:
        for statement in statements:
            cursor.execute(statement)
    finally:
        cursor.close()




def install_accounting_period_triggers(connection):
    """
    SQLite-level safeguards for accounting period integrity.
    Status changes require a matching audit event in the same transaction.
    """

    statements = [
        """
        CREATE TRIGGER IF NOT EXISTS trg_period_valid_insert
        BEFORE INSERT ON accounting_periods
        WHEN NEW.status NOT IN ('open', 'closed')
        BEGIN
            SELECT RAISE(ABORT, 'Invalid accounting period status.');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_period_valid_update
        BEFORE UPDATE OF status ON accounting_periods
        WHEN NEW.status NOT IN ('open', 'closed')
        BEGIN
            SELECT RAISE(ABORT, 'Invalid accounting period status.');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_period_no_overlap_insert
        BEFORE INSERT ON accounting_periods
        WHEN EXISTS (
            SELECT 1
            FROM accounting_periods p
            WHERE NEW.start_date <= p.end_date
              AND NEW.end_date >= p.start_date
        )
        BEGIN
            SELECT RAISE(ABORT, 'Accounting period date range overlaps another period.');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_period_no_overlap_update
        BEFORE UPDATE OF start_date, end_date ON accounting_periods
        WHEN EXISTS (
            SELECT 1
            FROM accounting_periods p
            WHERE p.id <> OLD.id
              AND NEW.start_date <= p.end_date
              AND NEW.end_date >= p.start_date
        )
        BEGIN
            SELECT RAISE(ABORT, 'Accounting period date range overlaps another period.');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_period_dates_immutable
        BEFORE UPDATE OF start_date, end_date ON accounting_periods
        WHEN EXISTS (
            SELECT 1
            FROM journal_entries j
            WHERE j.accounting_period_id = OLD.id
              AND j.status = 'posted'
        )
        AND (
            NEW.start_date <> OLD.start_date
            OR NEW.end_date <> OLD.end_date
        )
        BEGIN
            SELECT RAISE(ABORT, 'Period dates cannot change after posted journals reference the period.');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_period_close_guards
        BEFORE UPDATE OF status ON accounting_periods
        WHEN OLD.status = 'open' AND NEW.status = 'closed'
        BEGIN
            SELECT CASE
                WHEN NEW.end_date >= date('now', 'localtime')
                THEN RAISE(ABORT, 'An accounting period can only close after its end date.')
            END;

            SELECT CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM journal_entries j
                    WHERE j.status = 'draft'
                      AND (
                          j.accounting_period_id = OLD.id
                          OR (
                              j.entry_date >= OLD.start_date
                              AND j.entry_date <= OLD.end_date
                          )
                      )
                )
                THEN RAISE(ABORT, 'Cannot close period while draft journals remain.')
            END;

            SELECT CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM opening_balances ob
                    WHERE ob.status = 'draft'
                      AND ob.opening_date >= OLD.start_date
                      AND ob.opening_date <= OLD.end_date
                )
                THEN RAISE(ABORT, 'Cannot close period while draft opening balances remain.')
            END;

            SELECT CASE
                WHEN NOT EXISTS (
                    SELECT 1
                    FROM audit_logs a
                    WHERE a.module = 'accounting_periods'
                      AND a.action = 'accounting_period_closed'
                      AND a.record_type = 'AccountingPeriod'
                      AND a.record_id = OLD.id
                      AND a.username IS NOT NULL
                      AND length(trim(a.username)) > 0
                      AND a.reason IS NOT NULL
                      AND length(trim(a.reason)) > 0
                      AND a.old_values LIKE '%"status": "open"%'
                      AND a.new_values LIKE '%"status": "closed"%'
                )
                THEN RAISE(ABORT, 'A valid closure audit event with username and reason is required.')
            END;
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_period_reopen_audit
        BEFORE UPDATE OF status ON accounting_periods
        WHEN OLD.status = 'closed' AND NEW.status = 'open'
        BEGIN
            SELECT CASE
                WHEN NOT EXISTS (
                    SELECT 1
                    FROM audit_logs a
                    WHERE a.module = 'accounting_periods'
                      AND a.action = 'accounting_period_reopened'
                      AND a.record_type = 'AccountingPeriod'
                      AND a.record_id = OLD.id
                      AND a.username IS NOT NULL
                      AND length(trim(a.username)) > 0
                      AND a.reason IS NOT NULL
                      AND length(trim(a.reason)) > 0
                      AND a.old_values LIKE '%"status": "closed"%'
                      AND a.new_values LIKE '%"status": "open"%'
                )
                THEN RAISE(ABORT, 'A valid reopening audit event with username and reason is required.')
            END;
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_period_delete_protection
        BEFORE DELETE ON accounting_periods
        WHEN EXISTS (
            SELECT 1 FROM journal_entries j
            WHERE j.accounting_period_id = OLD.id
        )
        OR EXISTS (
            SELECT 1 FROM audit_logs a
            WHERE a.record_type = 'AccountingPeriod'
              AND a.record_id = OLD.id
        )
        BEGIN
            SELECT RAISE(ABORT, 'Accounting periods with journal or audit history cannot be deleted.');
        END
        """,
    ]

    cursor = connection.cursor()
    try:
        for statement in statements:
            cursor.execute(statement)
    finally:
        cursor.close()


@event.listens_for(engine, "checkout")
def protect_journal_entries(
    dbapi_connection,
    connection_record,
    connection_proxy,
):
    """
    Check and install protections whenever a connection is checked
    out, including after tables are created on a reused connection.
    """

    cursor = dbapi_connection.cursor()
    try:
        existing = {
            row[0]
            for row in cursor.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        }
    finally:
        cursor.close()

    required = {
        "journal_entries",
        "journal_entry_lines",
        "accounting_periods",
        "accounts",
    }

    if required.issubset(existing):
        install_journal_immutability_triggers(dbapi_connection)

    period_required = {
        "accounting_periods",
        "journal_entries",
        "opening_balances",
        "audit_logs",
    }

    if period_required.issubset(existing):
        install_accounting_period_triggers(dbapi_connection)


# Database connection function
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
