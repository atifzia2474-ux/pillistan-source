
from database import SessionLocal
from models import Account


# ============================================================
# PILLISTAN - STARTER CHART OF ACCOUNTS
# ============================================================

# Format:
# Code, Name, Account Type, Normal Balance, Parent Code

ACCOUNTS = [
    # ASSETS
    ("1000", "Assets", "asset", "debit", None),
    ("1100", "Current Assets", "asset", "debit", "1000"),
    ("1110", "Cash in Hand", "asset", "debit", "1100"),
    ("1120", "Bank Accounts", "asset", "debit", "1100"),
    ("1130", "COD Receivable", "asset", "debit", "1100"),
    ("1140", "Customer Receivables", "asset", "debit", "1100"),
    ("1150", "Inventory", "asset", "debit", "1100"),
    ("1160", "Input Tax Receivable", "asset", "debit", "1100"),
    ("1170", "Prepaid Expenses", "asset", "debit", "1100"),
    ("1180", "Inventory in Transit", "asset", "debit", "1100"),

    # LIABILITIES
    ("2000", "Liabilities", "liability", "credit", None),
    ("2100", "Current Liabilities", "liability", "credit", "2000"),
    ("2110", "Supplier Payables", "liability", "credit", "2100"),
    ("2120", "COD Payable", "liability", "credit", "2100"),
    ("2130", "Tax Payable", "liability", "credit", "2100"),
    ("2140", "Other Payables", "liability", "credit", "2100"),
    ("2200", "Long-Term Liabilities", "liability", "credit", "2000"),
    ("2210", "Business Loans Payable", "liability", "credit", "2200"),

    # EQUITY
    ("3000", "Equity", "equity", "credit", None),
    ("3100", "Opening Balance Equity", "equity", "credit", "3000"),
    ("3200", "Retained Earnings", "equity", "credit", "3000"),

    # REVENUE
    ("4000", "Revenue", "revenue", "credit", None),
    ("4100", "Product Sales", "revenue", "credit", "4000"),
    ("4200", "Other Operating Income", "revenue", "credit", "4000"),
    ("4300", "Sales Returns and Allowances", "revenue", "debit", "4000"),

    # COST OF GOODS SOLD
    ("5000", "Cost of Goods Sold", "expense", "debit", None),
    ("5100", "Product Cost", "expense", "debit", "5000"),
    ("5200", "Inventory Write-Offs", "expense", "debit", "5000"),

    # OPERATING EXPENSES
    ("6000", "Operating Expenses", "expense", "debit", None),
    ("6100", "Delivery and Courier Expense", "expense", "debit", "6000"),
    ("6200", "Packaging Expense", "expense", "debit", "6000"),
    ("6300", "Marketing and Advertising", "expense", "debit", "6000"),
    ("6400", "Salaries and Wages", "expense", "debit", "6000"),
    ("6500", "Rent Expense", "expense", "debit", "6000"),
    ("6600", "Utilities Expense", "expense", "debit", "6000"),
    ("6700", "Bank Charges", "expense", "debit", "6000"),
    ("6800", "Interest Expense", "expense", "debit", "6000"),
    ("6900", "Other Operating Expenses", "expense", "debit", "6000"),
]


def seed_chart_of_accounts():
    db = SessionLocal()

    created = 0
    skipped = 0

    try:
        # First, identify existing account codes.
        existing_accounts = {
            account.code: account
            for account in db.query(Account).all()
        }

        for code, name, account_type, normal_balance, parent_code in ACCOUNTS:

            # Never overwrite an existing account.
            if code in existing_accounts:
                print(f"SKIPPED (already exists): {code} - {name}")
                skipped += 1
                continue

            parent_id = None

            if parent_code:
                parent = (
                    existing_accounts.get(parent_code)
                    or db.query(Account).filter_by(
                        code=parent_code
                    ).first()
                )

                if parent is None:
                    raise ValueError(
                        f"Parent account {parent_code} not found "
                        f"for account {code}."
                    )

                parent_id = parent.id

            account = Account(
                code=code,
                name=name,
                account_type=account_type,
                normal_balance=normal_balance,
                parent_id=parent_id,
                is_active=True,
                is_system=True,
            )

            db.add(account)
            db.flush()

            existing_accounts[code] = account
            created += 1

        db.commit()

        print("\nChart of Accounts setup completed!")
        print(f"Accounts created: {created}")
        print(f"Existing accounts skipped: {skipped}")
        print(f"Total starter accounts: {len(ACCOUNTS)}")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed_chart_of_accounts()
