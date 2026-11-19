

from datetime import date, datetime, timezone

from decimal import Decimal, InvalidOperation

from uuid import uuid4

import json



from sqlalchemy import func



from database import SessionLocal

from models import (

    Account,

    AuditLog,

    Customer,

    OpeningBalance,

    OpeningBalanceLine,

    Product,

    Supplier,

)





# ============================================================

# PILLISTAN OPENING BALANCE SERVICE

# Draft Creation and Validation

# ============================================================



CENT = Decimal("0.01")

THREE_PLACES = Decimal("0.001")





# ------------------------------------------------------------

# MONEY VALIDATION

# ------------------------------------------------------------



def money(value):

    try:

        amount = Decimal(str(value))



        if not amount.is_finite():

            raise ValueError("Amount must be finite.")



        rounded = amount.quantize(CENT)



        if amount != rounded:

            raise ValueError(

                "Amounts cannot contain more than two decimal places."

            )



        return rounded



    except (InvalidOperation, TypeError):

        raise ValueError(f"Invalid monetary amount: {value}")





def quantity_value(value):

    try:

        amount = Decimal(str(value))



        if not amount.is_finite():

            raise ValueError("Quantity must be finite.")



        rounded = amount.quantize(THREE_PLACES)



        if amount != rounded:

            raise ValueError(

                "Quantity cannot contain more than three decimal places."

            )



        return rounded



    except (InvalidOperation, TypeError):

        raise ValueError(f"Invalid quantity: {value}")





def parse_date(value):

    if isinstance(value, datetime):

        return value.date()



    if isinstance(value, date):

        return value



    if isinstance(value, str):

        try:

            return date.fromisoformat(value)

        except ValueError:

            raise ValueError(

                f"Invalid date: {value}. Use YYYY-MM-DD."

            )



    raise ValueError("A valid date is required.")





# ------------------------------------------------------------

# ACCOUNT VALIDATION

# ------------------------------------------------------------



def find_account(db, account_code):



    if not account_code:

        raise ValueError("Account code is required.")



    account = db.query(Account).filter_by(

        code=str(account_code).strip()

    ).first()



    if account is None:

        raise ValueError(

            f"Account {account_code} does not exist."

        )



    if not account.is_active:

        raise ValueError(

            f"Account {account_code} is inactive."

        )



    has_children = db.query(Account.id).filter(

        Account.parent_id == account.id

    ).first()



    if has_children:

        raise ValueError(

            f"Account {account_code} is a parent account. "

            "Select a detailed account."

        )



    return account





# ------------------------------------------------------------

# AUDIT LOG

# ------------------------------------------------------------



def write_audit_log(

    db,

    action,

    record_id,

    username,

    old_values=None,

    new_values=None,

    reason=None,

):



    db.add(

        AuditLog(

            module="opening_balances",

            action=action,

            record_type="OpeningBalance",

            record_id=record_id,

            username=username,

            old_values=(

                json.dumps(old_values, default=str)

                if old_values else None

            ),

            new_values=(

                json.dumps(new_values, default=str)

                if new_values else None

            ),

            reason=reason,

        )

    )





# ------------------------------------------------------------

# OPENING BALANCE LINE VALIDATION

# ------------------------------------------------------------



def validate_opening_balance_line(db, item):



    account = find_account(

        db,

        item.get("account_code")

    )



    line_type = str(

        item.get("line_type", "general")

    ).strip().lower()



    if not line_type:

        raise ValueError("Line type is required.")



    debit = money(item.get("debit", 0))

    credit = money(item.get("credit", 0))



    if debit < 0 or credit < 0:

        raise ValueError("Negative amounts are not allowed.")



    if (debit > 0 and credit > 0) or (

        debit == 0 and credit == 0

    ):

        raise ValueError(

            "Each line must contain either a debit or a credit."

        )



    validated = {

        "account_id": account.id,

        "line_type": line_type,

        "description": item.get("description"),

        "debit": debit,

        "credit": credit,

        "product_id": None,

        "batch_id": None,

        "supplier_id": None,

        "customer_id": None,

        "quantity": None,

        "unit_cost": None,

        "batch_number": None,

        "received_date": None,

        "expiry_date": None,

    }



    # Inventory-specific validation.

    if line_type == "inventory":



        product_id = item.get("product_id")



        if product_id is None:

            raise ValueError(

                "Inventory lines require a product ID."

            )



        product = db.query(Product).filter_by(

            id=product_id

        ).first()



        if product is None:

            raise ValueError(

                f"Product ID {product_id} does not exist."

            )



        if not product.is_active or product.is_archived:

            raise ValueError(

                "Archived or inactive products cannot receive "

                "opening inventory."

            )



        quantity = quantity_value(item.get("quantity", 0))

        unit_cost = money(item.get("unit_cost", 0))



        if quantity <= 0:

            raise ValueError(

                "Inventory quantity must be greater than zero."

            )



        if unit_cost < 0:

            raise ValueError("Unit cost cannot be negative.")



        expected_value = money(quantity * unit_cost)



        if debit <= 0 or credit != 0:

            raise ValueError(

                "Opening inventory must be recorded as a debit."

            )



        if debit != expected_value:

            raise ValueError(

                f"Inventory value mismatch. "

                f"Expected {expected_value}, entered {debit}."

            )



        validated.update({

            "product_id": product.id,

            "quantity": quantity,

            "unit_cost": unit_cost,

            "batch_number": item.get("batch_number"),

            "received_date": (

                parse_date(item["received_date"])

                if item.get("received_date")

                else None

            ),

            "expiry_date": (

                parse_date(item["expiry_date"])

                if item.get("expiry_date")

                else None

            ),

        })



        if (

            validated["received_date"]

            and validated["expiry_date"]

            and validated["expiry_date"] < validated["received_date"]

        ):

            raise ValueError(

                "Expiry date cannot precede the received date."

            )



    # Supplier-specific validation.

    supplier_id = item.get("supplier_id")

    if line_type == "supplier" and supplier_id is None:
        raise ValueError(
            "Supplier opening balances require a supplier ID."
        )

    # Inventory lines may optionally identify their supplier.
    # Preserve the supplier ID for the inventory batch.
    if line_type in ("supplier", "inventory") and supplier_id is not None:

        supplier = db.query(Supplier).filter_by(
            id=supplier_id
        ).first()

        if supplier is None:
            raise ValueError("Supplier does not exist.")

        validated["supplier_id"] = supplier.id


    # Customer-specific validation.

    if line_type == "customer":



        customer_id = item.get("customer_id")



        if customer_id is None:

            raise ValueError(

                "Customer opening balances require a customer ID."

            )



        customer = db.query(Customer).filter_by(

            id=customer_id

        ).first()



        if customer is None:

            raise ValueError("Customer does not exist.")



        validated["customer_id"] = customer.id



    # Optional existing inventory batch reference.

    if item.get("batch_id") is not None:



        from models import InventoryBatch



        batch = db.query(InventoryBatch).filter_by(

            id=item["batch_id"]

        ).first()



        if batch is None:

            raise ValueError("Inventory batch does not exist.")



        if (

            validated["product_id"] is not None

            and batch.product_id != validated["product_id"]

        ):

            raise ValueError(

                "The selected batch belongs to another product."

            )



        validated["batch_id"] = batch.id



    return validated







def check_duplicate_inventory_batches(db, lines):
    """
    Return informational warnings for repeated product/batch combinations.

    Checks:
    1. Existing inventory batches for the same product and batch number.
    2. Repeated product/batch combinations within the supplied draft lines.
    3. Differences in expiry dates.

    This function never blocks entries or changes inventory records.
    """

    from models import InventoryBatch

    warnings = []
    seen = {}

    for index, item in enumerate(lines, start=1):

        if str(item.get("line_type", "general")).strip().lower() != "inventory":
            continue

        product_id = item.get("product_id")
        batch_number = str(item.get("batch_number") or "").strip()

        # Blank batch numbers are intentionally not compared.
        if product_id is None or not batch_number:
            continue

        expiry_date = item.get("expiry_date")

        if isinstance(expiry_date, str):
            expiry_date = parse_date(expiry_date) if expiry_date else None

        key = (product_id, batch_number.casefold())

        existing_batches = (
            db.query(InventoryBatch)
            .filter(
                InventoryBatch.product_id == product_id,
                func.lower(InventoryBatch.batch_number) == batch_number.lower(),
            )
            .all()
        )

        for batch in existing_batches:
            warnings.append({
                "type": (
                    "expiry_mismatch"
                    if batch.expiry_date != expiry_date
                    else "existing_batch"
                ),
                "line_number": index,
                "product_id": product_id,
                "batch_number": batch_number,
                "existing_batch_id": batch.id,
                "existing_expiry_date": batch.expiry_date,
                "new_expiry_date": expiry_date,
                "message": (
                    f"Line {index}: Product {product_id} already has "
                    f"batch {batch_number!r}. "
                    + (
                        "The expiry date differs; please review."
                        if batch.expiry_date != expiry_date
                        else "A separate receipt will be preserved."
                    )
                ),
            })

        if key in seen:
            previous = seen[key]
            expiry_differs = previous["expiry_date"] != expiry_date

            warnings.append({
                "type": (
                    "draft_expiry_mismatch"
                    if expiry_differs
                    else "draft_duplicate"
                ),
                "line_number": index,
                "previous_line_number": previous["line_number"],
                "product_id": product_id,
                "batch_number": batch_number,
                "existing_expiry_date": previous["expiry_date"],
                "new_expiry_date": expiry_date,
                "message": (
                    f"Line {index}: This product and batch number also "
                    f"appear on line {previous['line_number']}. "
                    + (
                        "The expiry dates differ; please review."
                        if expiry_differs
                        else "Both lines will remain separate."
                    )
                ),
            })
        else:
            seen[key] = {
                "line_number": index,
                "expiry_date": expiry_date,
            }

    return warnings


# ------------------------------------------------------------

# CREATE OPENING BALANCE DRAFT

# ------------------------------------------------------------



def create_opening_balance_draft(

    opening_date,

    description,

    lines,

    username="admin",

):

    """

    Create an opening balance draft.



    Drafts do not affect posted financial records.



    Incomplete or unbalanced drafts can be saved.

    Posting will require a balanced entry.

    """



    db = SessionLocal()



    try:



        opening_date = parse_date(opening_date)



        if not username or not username.strip():

            raise ValueError("Username is required.")



        if not lines:

            raise ValueError(

                "At least one opening balance line is required."

            )



        reference_number = (

            f"OB-{datetime.now().strftime('%Y%m%d')}-"

            f"{uuid4().hex[:8].upper()}"

        )



        opening_balance = OpeningBalance(

            reference_number=reference_number,

            opening_date=opening_date,

            description=description,

            status="draft",

            total_debit=Decimal("0.00"),

            total_credit=Decimal("0.00"),

            created_by=username,

        )



        db.add(opening_balance)

        db.flush()



        total_debit = Decimal("0.00")

        total_credit = Decimal("0.00")



        for index, item in enumerate(lines, start=1):



            validated = validate_opening_balance_line(

                db,

                item

            )



            db.add(

                OpeningBalanceLine(

                    opening_balance_id=opening_balance.id,

                    **validated,

                )

            )



            total_debit += validated["debit"]

            total_credit += validated["credit"]



        opening_balance.total_debit = total_debit

        opening_balance.total_credit = total_credit



        write_audit_log(

            db,

            action="opening_balance_draft_created",

            record_id=opening_balance.id,

            username=username,

            new_values={

                "reference_number": reference_number,

                "opening_date": opening_date.isoformat(),

                "status": "draft",

                "total_debit": str(total_debit),

                "total_credit": str(total_credit),

                "line_count": len(lines),

            },

        )



        db.commit()



        print("Opening balance draft created successfully.")

        print("Reference:", reference_number)

        print("Status: draft")

        print("Total debit:", total_debit)

        print("Total credit:", total_credit)



        return opening_balance.id



    except Exception:

        db.rollback()

        raise



    finally:

        db.close()





# ------------------------------------------------------------

# VALIDATE OPENING BALANCE

# ------------------------------------------------------------



def validate_opening_balance(opening_balance_id):



    db = SessionLocal()



    try:



        opening_balance = db.query(

            OpeningBalance

        ).filter_by(

            id=opening_balance_id

        ).first()



        if opening_balance is None:

            raise ValueError(

                "Opening balance record not found."

            )



        if opening_balance.status != "draft":

            raise ValueError(

                "Only draft opening balances can be validated."

            )



        lines = db.query(

            OpeningBalanceLine

        ).filter_by(

            opening_balance_id=opening_balance.id

        ).order_by(

            OpeningBalanceLine.id

        ).all()



        if len(lines) < 2:

            raise ValueError(

                "At least two opening balance lines are required."

            )



        total_debit = Decimal("0.00")

        total_credit = Decimal("0.00")



        for line in lines:



            account = db.query(Account).filter_by(

                id=line.account_id

            ).first()



            if account is None or not account.is_active:

                raise ValueError(

                    f"Account ID {line.account_id} is missing or inactive."

                )



            debit = money(line.debit)

            credit = money(line.credit)



            if debit < 0 or credit < 0:

                raise ValueError(

                    "Negative amounts are not allowed."

                )



            if (debit > 0 and credit > 0) or (

                debit == 0 and credit == 0

            ):

                raise ValueError(

                    f"Invalid debit/credit values on line {line.id}."

                )



            total_debit += debit

            total_credit += credit



        if total_debit != total_credit:

            raise ValueError(

                f"Opening balance is not balanced. "

                f"Debits: {total_debit}, Credits: {total_credit}."

            )



        print("Opening balance validation PASSED.")

        print("Reference:", opening_balance.reference_number)

        print("Lines:", len(lines))

        print("Total debit:", total_debit)

        print("Total credit:", total_credit)

        print("Difference:", total_debit - total_credit)



        return True



    finally:

        db.close()


# ------------------------------------------------------------
# POST OPENING BALANCE — ATOMIC TRANSACTION
# ------------------------------------------------------------

def post_opening_balance(opening_balance_id, username="admin"):
    """
    Post an opening balance atomically.

    Creates:
    - Posted journal entry and journal lines
    - Inventory batches and stock movements
    - Opening balance and journal audit records

    All changes are committed in one transaction.
    Returns the journal entry ID.
    """

    from models import (
        AccountingPeriod,
        JournalEntry,
        JournalEntryLine,
        InventoryBatch,
        StockMovement,
    )

    from accounting_service import (
        validate_journal_lines,
        generate_entry_number,
    )

    if not username or not username.strip():
        raise ValueError("Username is required.")

    db = SessionLocal()

    try:
        # 1. Lock and retrieve the opening balance.
        opening_balance = (
            db.query(OpeningBalance)
            .filter_by(id=opening_balance_id)
            .with_for_update()
            .first()
        )

        if opening_balance is None:
            raise ValueError("Opening balance record not found.")

        if opening_balance.status != "draft":
            raise ValueError(
                "Only draft opening balances can be posted."
            )

        # 2. Prevent duplicate journal creation.
        idempotency_key = (
            f"OPENING-BALANCE-{opening_balance.id}"
        )

        existing_entry = db.query(JournalEntry).filter_by(
            idempotency_key=idempotency_key
        ).first()

        if existing_entry is not None:
            raise ValueError(
                "A journal entry already exists for this "
                "opening balance. Manual review is required."
            )

        # 3. Find the accounting period.
        period = db.query(AccountingPeriod).filter(
            AccountingPeriod.start_date <= opening_balance.opening_date,
            AccountingPeriod.end_date >= opening_balance.opening_date,
        ).with_for_update().first()

        if period is None:
            raise ValueError(
                "No accounting period covers the opening balance date."
            )

        if period.status != "open":
            raise ValueError(
                "The accounting period is closed."
            )

        # 4. Retrieve and validate the opening balance lines.
        opening_lines = (
            db.query(OpeningBalanceLine)
            .filter_by(opening_balance_id=opening_balance.id)
            .order_by(OpeningBalanceLine.id)
            .all()
        )

        if len(opening_lines) < 2:
            raise ValueError(
                "At least two opening balance lines are required."
            )

        journal_input = []
        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")
        validated_details = []

        for line in opening_lines:

            account = db.query(Account).filter_by(
                id=line.account_id
            ).first()

            if account is None:
                raise ValueError(
                    f"Account ID {line.account_id} no longer exists."
                )

            # Revalidate the business-specific information.
            item = {
                "account_code": account.code,
                "line_type": line.line_type,
                "description": line.description,
                "debit": line.debit,
                "credit": line.credit,
                "product_id": line.product_id,
                "supplier_id": line.supplier_id,
                "customer_id": line.customer_id,
                "quantity": line.quantity,
                "unit_cost": line.unit_cost,
                "batch_number": line.batch_number,
                "received_date": line.received_date,
                "expiry_date": line.expiry_date,
            }

            validated = validate_opening_balance_line(db, item)

            # Existing batches must not be modified by an
            # opening-balance transaction.
            if (
                line.line_type == "inventory"
                and line.batch_id is not None
            ):
                raise ValueError(
                    f"Inventory line {line.id} already references "
                    "an existing batch. Opening inventory posting "
                    "must create a new batch."
                )

            journal_input.append({
                "account_code": account.code,
                "description": line.description,
                "debit": validated["debit"],
                "credit": validated["credit"],
            })

            total_debit += validated["debit"]
            total_credit += validated["credit"]

            validated_details.append((line, validated))

        if total_debit != total_credit:
            raise ValueError(
                f"Opening balance is not balanced. "
                f"Debits: {total_debit}; Credits: {total_credit}."
            )

        if (
            money(opening_balance.total_debit) != total_debit
            or money(opening_balance.total_credit) != total_credit
        ):
            raise ValueError(
                "Stored opening balance totals do not match "
                "the opening balance lines."
            )

        # Check for duplicate inventory batches before creating new batches.
        inventory_warning_items = [
            {
                "line_type": line.line_type,
                "product_id": validated["product_id"],
                "batch_number": validated["batch_number"],
                "expiry_date": validated["expiry_date"],
            }
            for line, validated in validated_details
            if line.line_type == "inventory"
        ]

        duplicate_batch_warnings = check_duplicate_inventory_batches(
            db,
            inventory_warning_items,
        )

        # 5. Validate the journal lines using the accounting engine.
        validated_journal_lines = validate_journal_lines(
            db,
            journal_input
        )

        # 6. Create the journal entry directly in this session.
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        journal_entry = JournalEntry(
            entry_number=generate_entry_number(),
            entry_date=opening_balance.opening_date,
            description=(
                opening_balance.description
                or f"Opening balance {opening_balance.reference_number}"
            ),
            source_module="opening_balances",
            reference_type="OpeningBalance",
            reference_id=opening_balance.id,
            accounting_period_id=period.id,
            idempotency_key=idempotency_key,
            status="draft",
            created_by=username,
        )

        db.add(journal_entry)
        db.flush()

        for item in validated_journal_lines:
            db.add(
                JournalEntryLine(
                    journal_entry_id=journal_entry.id,
                    account_id=item["account_id"],
                    line_number=item["line_number"],
                    description=item["description"],
                    debit=item["debit"],
                    credit=item["credit"],
                )
            )

        # Ensure all journal lines are inserted while the journal
        # is still a draft.
        db.flush()

        # 7. Create inventory batches and stock movements.
        inventory_batch_count = 0

        for line, validated in validated_details:

            if line.line_type != "inventory":
                continue

            supplier_name = None

            if validated["supplier_id"] is not None:
                supplier = db.query(Supplier).filter_by(
                    id=validated["supplier_id"]
                ).first()

                if supplier is None:
                    raise ValueError(
                        f"Supplier ID {validated['supplier_id']} "
                        "no longer exists."
                    )

                supplier_name = supplier.name

            received_date = (
                validated["received_date"]
                or opening_balance.opening_date
            )

            batch = InventoryBatch(
                product_id=validated["product_id"],
                batch_number=validated["batch_number"],
                received_date=received_date,
                expiry_date=validated["expiry_date"],
                received_quantity=validated["quantity"],
                remaining_quantity=validated["quantity"],
                unit_cost=validated["unit_cost"],
                supplier=supplier_name,
                notes=(
                    f"Opening balance: "
                    f"{opening_balance.reference_number}"
                ),
                is_active=True,
            )

            db.add(batch)
            db.flush()

            # Link the new batch to its opening balance line.
            line.batch_id = batch.id

            db.add(
                StockMovement(
                    product_id=validated["product_id"],
                    batch_id=batch.id,
                    movement_type="opening_balance",
                    quantity_change=validated["quantity"],
                    reference_type="OpeningBalance",
                    reference_id=opening_balance.id,
                    note=(
                        f"Opening inventory for "
                        f"{opening_balance.reference_number}"
                    ),
                )
            )

            inventory_batch_count += 1

        # 8. Post the journal after all journal lines and related
        # inventory records have been prepared in this transaction.
        journal_entry.status = "posted"
        journal_entry.posted_by = username
        journal_entry.posted_at = now
        db.flush()

        # Mark the opening balance as posted.
        opening_balance.status = "posted"
        opening_balance.journal_entry_id = journal_entry.id
        opening_balance.posted_by = username
        opening_balance.posted_at = now

        # 9. Record opening balance audit history.
        write_audit_log(
            db,
            action="opening_balance_posted",
            record_id=opening_balance.id,
            username=username,
            old_values={"status": "draft"},
            new_values={
                "status": "posted",
                "journal_entry_id": journal_entry.id,
                "journal_entry_number": journal_entry.entry_number,
                "accounting_period": period.name,
                "total_debit": str(total_debit),
                "total_credit": str(total_credit),
                "inventory_batches_created": inventory_batch_count,
                "inventory_batch_warnings": duplicate_batch_warnings,
            },
        )

        # 10. Record journal audit history.
        db.add(
            AuditLog(
                module="accounting",
                action="journal_entry_posted",
                record_type="JournalEntry",
                record_id=journal_entry.id,
                username=username,
                old_values=json.dumps({"status": "draft"}),
                new_values=json.dumps({
                    "status": "posted",
                    "source_module": "opening_balances",
                    "opening_balance_id": opening_balance.id,
                    "entry_number": journal_entry.entry_number,
                    "accounting_period": period.name,
                    "total_debit": str(total_debit),
                    "total_credit": str(total_credit),
                }),
            )
        )

        # 11. One commit for every change.
        db.commit()

        print("Opening balance posted successfully.")
        print("Opening balance:", opening_balance.reference_number)
        print("Journal entry:", journal_entry.entry_number)
        print("Journal entry ID:", journal_entry.id)
        print("Accounting period:", period.name)
        print("Inventory batches created:", inventory_batch_count)
        print("Total debit:", total_debit)
        print("Total credit:", total_credit)
        print("Status: posted")

        return journal_entry.id

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


