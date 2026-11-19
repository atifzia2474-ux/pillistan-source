from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from database import SessionLocal
from models import (
    Product, Supplier, Purchase, PurchaseItem, SupplierPayment,
    InventoryBatch, StockMovement, AuditLog
)
from accounting_service import create_draft_entry, post_journal_entry


CENT = Decimal("0.01")
THREE = Decimal("0.001")


def _money(value):
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _quantity(value):
    return Decimal(str(value or 0)).quantize(THREE, rounding=ROUND_HALF_UP)


def _post_entry(db, entry_date, description, lines, username,
                reference_type, reference_id, idempotency_key):
    entry_id = create_draft_entry(
        entry_date=entry_date,
        description=description,
        lines=lines,
        username=username,
        source_module="purchases",
        reference_type=reference_type,
        reference_id=reference_id,
        idempotency_key=idempotency_key,
        db=db,
    )
    post_journal_entry(entry_id, username=username, db=db)
    return entry_id


def create_purchase(
    supplier_id,
    purchase_date,
    items,
    discount=0,
    other_charges=0,
    paid_amount=0,
    invoice_number=None,
    notes=None,
    payment_method="cash",
    username="admin",
    changed_by_id=None,
):
    """
    Save a received purchase, stock batches, stock movements,
    supplier payment and accounting journals in one DB transaction.
    The caller must not separately receive this purchase's stock.
    """
    username = str(username or "").strip()
    if not username:
        raise ValueError("Authenticated username is required to record a purchase.")
    if not isinstance(purchase_date, date):
        raise ValueError("A valid purchase date is required.")
    if not items:
        raise ValueError("At least one purchase item is required.")

    discount = _money(discount)
    charges = _money(other_charges)
    paid = _money(paid_amount)

    if discount < 0 or charges < 0 or paid < 0:
        raise ValueError("Discount, charges and payment cannot be negative.")

    prepared = []
    subtotal = Decimal("0.00")

    db = SessionLocal()
    try:
        supplier = db.get(Supplier, supplier_id)
        if supplier is None or not supplier.is_active:
            raise ValueError("The selected supplier is unavailable.")

        for raw in items:
            product = db.get(Product, raw["product_id"])
            if product is None or not product.is_active or product.is_archived:
                raise ValueError("A selected product is unavailable.")

            qty = _quantity(raw["quantity"])
            unit_cost = _money(raw["unit_cost"])
            line_total = _money(qty * unit_cost)

            if qty <= 0:
                raise ValueError(f"Quantity must be positive for {product.name}.")
            if unit_cost < 0:
                raise ValueError(f"Unit cost cannot be negative for {product.name}.")

            expiry = raw.get("expiry_date")
            if isinstance(expiry, str) and expiry.strip():
                expiry = date.fromisoformat(expiry)
            elif not expiry:
                expiry = None

            prepared.append({
                "product": product,
                "quantity": qty,
                "unit_cost": unit_cost,
                "line_total": line_total,
                "batch_number": raw.get("batch_number"),
                "expiry_date": expiry,
            })
            subtotal += line_total

        subtotal = _money(subtotal)
        total = _money(subtotal - discount + charges)

        if total < 0:
            raise ValueError("Discount cannot exceed the purchase subtotal.")
        if paid > total:
            raise ValueError("Payment cannot exceed the purchase total.")

        balance = _money(total - paid)

        purchase = Purchase(
            supplier_id=supplier.id,
            invoice_number=(invoice_number or "").strip() or None,
            purchase_date=purchase_date,
            subtotal=subtotal,
            discount=discount,
            other_charges=charges,
            total_amount=total,
            paid_amount=paid,
            balance_amount=balance,
            status="received",
            notes=(notes or "").strip() or None,
        )
        db.add(purchase)
        db.flush()

        # Allocate discount and additional charges proportionally
        # so batch cost reflects the purchase's landed cost.
        total_qty = sum((x["quantity"] for x in prepared), Decimal("0"))
        allocated_total = Decimal("0.00")

        for index, item in enumerate(prepared):
            if index == len(prepared) - 1:
                allocated_value = _money(total - allocated_total)
            elif subtotal > 0:
                allocated_value = _money(
                    total * item["line_total"] / subtotal
                )
                allocated_total += allocated_value
            elif total_qty > 0:
                allocated_value = _money(
                    total * item["quantity"] / total_qty
                )
                allocated_total += allocated_value
            else:
                allocated_value = Decimal("0.00")

            landed_unit_cost = (
                _money(allocated_value / item["quantity"])
                if item["quantity"] > 0 else item["unit_cost"]
            )

            purchase_item = PurchaseItem(
                purchase_id=purchase.id,
                product_id=item["product"].id,
                batch_number=item["batch_number"],
                expiry_date=item["expiry_date"],
                quantity=item["quantity"],
                unit_cost=item["unit_cost"],
                line_total=item["line_total"],
            )
            db.add(purchase_item)
            db.flush()

            batch = InventoryBatch(
                product_id=item["product"].id,
                purchase_item_id=purchase_item.id,
                supplier_id=supplier.id,
                batch_number=item["batch_number"],
                received_date=purchase_date,
                expiry_date=item["expiry_date"],
                received_quantity=item["quantity"],
                remaining_quantity=item["quantity"],
                unit_cost=landed_unit_cost,
                supplier=supplier.name,
                notes=f"Purchase ID: {purchase.id}; Purchase item ID: {purchase_item.id}",
            )
            db.add(batch)
            db.flush()

            db.add(StockMovement(
                product_id=item["product"].id,
                batch_id=batch.id,
                movement_type="purchase_received",
                quantity_change=item["quantity"],
                reference_type="purchase",
                reference_id=purchase.id,
                note=f"Received from {supplier.name}; purchase item {purchase_item.id}",
            ))

        # Record and post the full purchase liability.
        if total > 0:
            _post_entry(
                db,
                purchase_date,
                f"Inventory received from {supplier.name}",
                [
                    {
                        "account_code": "1150",
                        "debit": total,
                        "credit": 0,
                        "description": "Inventory received",
                    },
                    {
                        "account_code": "2110",
                        "debit": 0,
                        "credit": total,
                        "description": "Supplier payable",
                    },
                ],
                username,
                "purchase",
                purchase.id,
                f"PURCHASE-{purchase.id}",
            )

        # Initial payment is a separate accounting transaction.
        if paid > 0:
            payment = SupplierPayment(
                supplier_id=supplier.id,
                purchase_id=purchase.id,
                payment_date=purchase_date,
                amount=paid,
                payment_method=payment_method,
                notes="Initial payment against purchase",
            )
            db.add(payment)
            db.flush()

            cash_account = "1120" if payment_method.lower() in (
                "bank", "bank transfer", "online transfer"
            ) else "1110"

            _post_entry(
                db,
                purchase_date,
                f"Initial supplier payment to {supplier.name}",
                [
                    {
                        "account_code": "2110",
                        "debit": paid,
                        "credit": 0,
                        "description": "Reduce supplier payable",
                    },
                    {
                        "account_code": cash_account,
                        "debit": 0,
                        "credit": paid,
                        "description": "Payment from business funds",
                    },
                ],
                username,
                "supplier_payment",
                payment.id,
                f"SUPPLIER-PAYMENT-{payment.id}",
            )

        db.add(AuditLog(
            module="purchases",
            action="purchase_received",
            record_type="Purchase",
            record_id=purchase.id,
            user_id=changed_by_id,
            username=username,
            new_values=(
                f'{{"supplier_id": {supplier.id}, "total": "{total}", '
                f'"paid": "{paid}", "balance": "{balance}"}}'
            ),
            reason="Purchase and inventory received",
        ))

        db.commit()

        return {
            "purchase_id": purchase.id,
            "subtotal": subtotal,
            "total": total,
            "paid": paid,
            "balance": balance,
            "batch_count": len(prepared),
        }

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
