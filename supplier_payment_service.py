"""Transaction-safe supplier settlement accounting.

The caller owns the SQLAlchemy session and must commit or roll it back.
"""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from models import Purchase, SupplierPayment, AuditLog
from sqlalchemy import func
from accounting_service import create_draft_entry, post_journal_entry

CENT = Decimal("0.01")


def record_supplier_payment(session, purchase_id, payment_date, amount,
                            payment_method="cash", reference_number=None,
                            notes=None, username="admin", changed_by_id=None):
    """Record a later payment against one purchase and post its journal."""
    if isinstance(payment_date, str):
        payment_date = date.fromisoformat(payment_date)
    if not isinstance(payment_date, date):
        raise ValueError("A valid payment date is required.")
    try:
        value = Decimal(str(amount)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Enter a valid payment amount.")
    if not value.is_finite() or value <= 0:
        raise ValueError("Payment amount must be greater than zero.")
    if not username or not str(username).strip():
        raise ValueError("The authenticated username is required.")
    reference_value = (reference_number or "").strip()
    if not reference_value:
        raise ValueError("A supplier receipt / payment voucher reference is required to prevent duplicate payments.")
    if len(reference_value) > 100:
        raise ValueError("Supplier payment reference cannot exceed 100 characters.")

    purchase = session.get(Purchase, purchase_id)
    if purchase is None or purchase.status != "received":
        raise ValueError("Only an existing received purchase can be paid.")
    existing_payment = session.query(SupplierPayment).filter(
        func.lower(func.trim(SupplierPayment.reference_number)) == reference_value.casefold()
    ).first()
    if existing_payment:
        same_details = (
            existing_payment.purchase_id == purchase.id
            and Decimal(str(existing_payment.amount)).quantize(CENT) == value
            and str(existing_payment.payment_method or "").strip().lower()
                == str(payment_method or "cash").strip().lower()
        )
        if same_details:
            return existing_payment
        raise ValueError("This supplier payment reference has already been used with different details.")

    outstanding = Decimal(str(purchase.balance_amount or 0)).quantize(CENT)
    if value > outstanding:
        raise ValueError(
            f"Payment exceeds the outstanding purchase balance ({outstanding})."
        )
    method = (payment_method or "cash").strip().lower()
    if method in ("bank", "bank transfer", "online transfer"):
        cash_account = "1120"
    elif method in ("cash", "cash in hand"):
        cash_account = "1110"
    else:
        raise ValueError("Payment method must be cash or bank transfer.")

    payment = SupplierPayment(
        supplier_id=purchase.supplier_id, purchase_id=purchase.id,
        payment_date=payment_date, amount=value, payment_method=method,
        reference_number=reference_value,
        notes=(notes or "").strip() or None,
    )
    session.add(payment)
    session.flush()

    new_paid = (Decimal(str(purchase.paid_amount or 0)) + value).quantize(CENT)
    new_balance = (outstanding - value).quantize(CENT)
    purchase.paid_amount = new_paid
    purchase.balance_amount = new_balance

    journal_id = create_draft_entry(
        entry_date=payment_date,
        description=f"Supplier payment for purchase {purchase.id}",
        lines=[
            {"account_code": "2110", "debit": value, "credit": 0,
             "description": "Reduce supplier payable"},
            {"account_code": cash_account, "debit": 0, "credit": value,
             "description": "Supplier payment"},
        ],
        username=str(username).strip(), source_module="supplier_payments",
        reference_type="supplier_payment", reference_id=payment.id,
        idempotency_key=f"SUPPLIER-PAYMENT-{payment.id}", db=session,
    )
    post_journal_entry(journal_id, username=str(username).strip(), db=session)
    session.add(AuditLog(
        module="purchases", action="supplier_payment_recorded",
        record_type="SupplierPayment", record_id=payment.id,
        user_id=changed_by_id, username=str(username).strip(),
        old_values=f'{{"paid_amount":"{new_paid - value}","balance_amount":"{outstanding}"}}',
        new_values=f'{{"paid_amount":"{new_paid}","balance_amount":"{new_balance}","journal_entry_id":{journal_id}}}',
        reason="Subsequent supplier payment",
    ))
    session.flush()
    return payment
