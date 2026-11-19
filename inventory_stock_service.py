import json
from decimal import Decimal, InvalidOperation

from models import InventoryBatch, StockMovement, AuditLog
from order_fulfilment_service import get_available_batch_quantity
from accounting_service import create_draft_entry, post_journal_entry


def decimal_value(value):
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def get_batch_stock_summary(session, batch):
    physical = decimal_value(batch.remaining_quantity)
    available = decimal_value(
        get_available_batch_quantity(session, batch)
    )
    reserved = max(Decimal("0"), physical - available)

    return {
        "physical": physical,
        "reserved": reserved,
        "available": available,
    }


def write_inventory_audit(
    session,
    action,
    record_type,
    record_id,
    old_values,
    new_values,
    reason,
    username="admin",
    user_id=None,
):
    audit = AuditLog(
        module="inventory",
        action=action,
        record_type=record_type,
        record_id=record_id,
        user_id=user_id,
        username=username,
        old_values=json.dumps(old_values, default=str),
        new_values=json.dumps(new_values, default=str),
        reason=reason,
    )
    session.add(audit)


def adjust_stock(
    session,
    batch_id,
    adjustment,
    quantity,
    reason,
    notes="",
    username="admin",
    changed_by_id=None,
):
    quantity = decimal_value(quantity)

    if quantity <= 0:
        raise ValueError("Adjustment quantity must be greater than zero.")

    if adjustment not in ("increase", "decrease"):
        raise ValueError("Invalid stock adjustment type.")

    batch = session.get(InventoryBatch, batch_id)

    if batch is None or not batch.is_active:
        raise ValueError("The selected inventory batch is unavailable.")

    current = decimal_value(batch.remaining_quantity)

    if adjustment == "decrease":
        available = decimal_value(
            get_available_batch_quantity(session, batch)
        )

        if quantity > available:
            raise ValueError(
                "This adjustment would reduce stock reserved for customer "
                f"orders. Physical stock: {current}; unreserved stock: "
                f"{available}; requested reduction: {quantity}."
            )
        change = -quantity
    else:
        change = quantity

    old_quantity = current
    new_quantity = current + change
    batch.remaining_quantity = new_quantity

    description = f"{reason}. {notes}".strip()

    movement = StockMovement(
        product_id=batch.product_id,
        batch_id=batch.id,
        movement_type=f"adjustment_{adjustment}",
        quantity_change=change,
        reference_type="stock_adjustment",
        note=description,
    )
    session.add(movement)
    session.flush()

    # Keep the perpetual inventory ledger in step with the physical batch.
    # The batch's recorded landed unit cost is the valuation basis.
    adjustment_value = (quantity * decimal_value(batch.unit_cost)).quantize(
        Decimal("0.01")
    )
    if adjustment_value > 0:
        if adjustment == "decrease":
            debit_account, credit_account = "5200", "1150"
            description = "Inventory write-off / stock decrease"
        else:
            debit_account, credit_account = "1150", "4200"
            description = "Inventory increase adjustment"

        journal_id = create_draft_entry(
            entry_date=__import__("datetime").date.today(),
            description=f"{description}: batch {batch.id}",
            lines=[
                {"account_code": debit_account, "debit": adjustment_value,
                 "credit": 0, "description": description},
                {"account_code": credit_account, "debit": 0,
                 "credit": adjustment_value, "description": description},
            ],
            username=username,
            source_module="inventory",
            reference_type="stock_movement",
            reference_id=movement.id,
            idempotency_key=f"STOCK-ADJUSTMENT-{movement.id}",
            db=session,
        )
        post_journal_entry(journal_id, username=username, db=session)

    write_inventory_audit(
        session,
        action=f"stock_adjustment_{adjustment}",
        record_type="InventoryBatch",
        record_id=batch.id,
        old_values={"remaining_quantity": str(old_quantity)},
        new_values={
            "remaining_quantity": str(new_quantity),
            "quantity_change": str(change),
            "reason": reason,
            "movement_id": movement.id,
        },
        reason=description,
        username=username,
        user_id=changed_by_id,
    )

    return batch
