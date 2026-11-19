"""Transaction-safe delivery and courier COD accounting for Pillistan.

All functions accept the caller's SQLAlchemy session and deliberately do not
commit. The caller must commit or roll back the complete business operation.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

from models import (
    Account,
    AuditLog,
    InventoryBatch,
    JournalEntry,
    JournalEntryLine,
    StockMovement,
)
from orders_models import (
    DispatchParcel,
    DispatchParcelItem,
    OrderPayment,
    OrderStatusHistory,
    SalesOrder,
    SalesOrderItem,
    StockReservation,
)
from accounting_service import create_draft_entry, post_journal_entry

CENT = Decimal("0.01")


def _decimal(value, label):
    try:
        result = Decimal(str(value if value is not None else 0))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a valid number.")
    if not result.is_finite():
        raise ValueError(f"{label} must be a finite number.")
    return result


def _money(value):
    return _decimal(value, "Amount").quantize(CENT, rounding=ROUND_HALF_UP)


def _account_id(session, code):
    account = session.query(Account).filter_by(code=str(code)).first()
    if account is None or not account.is_active:
        raise ValueError(f"Required active account {code} is missing.")
    return account.id


def _post_journal_once(session, *, key, entry_date, description, lines,
                       username, source_module, reference_type, reference_id):
    existing = session.query(JournalEntry).filter_by(idempotency_key=key).first()
    if existing:
        if existing.status == "posted":
            return existing.id
        raise ValueError(
            f"An unfinished journal already exists for {key}. "
            "Resolve it before retrying the business action."
        )
    entry_id = create_draft_entry(
        entry_date=entry_date,
        description=description,
        lines=lines,
        username=username,
        source_module=source_module,
        reference_type=reference_type,
        reference_id=reference_id,
        idempotency_key=key,
        db=session,
    )
    post_journal_entry(entry_id, username=username, db=session)
    return entry_id


def _parcel_delivery_values(session, parcel, delivery_charge_override=None):
    rows = (
        session.query(DispatchParcelItem, SalesOrderItem, StockReservation,
                      InventoryBatch)
        .join(SalesOrderItem,
              SalesOrderItem.id == DispatchParcelItem.order_item_id)
        .join(StockReservation,
              StockReservation.id == DispatchParcelItem.reservation_id)
        .join(InventoryBatch, InventoryBatch.id == StockReservation.batch_id)
        .filter(DispatchParcelItem.parcel_id == parcel.id)
        .all()
    )
    if not rows:
        raise ValueError("This parcel has no dispatched item lines.")

    gross_goods = Decimal("0")
    cost_goods = Decimal("0")
    quantities_by_item = {}
    for parcel_item, order_item, reservation, batch in rows:
        qty = _decimal(parcel_item.quantity_dispatched, "Dispatched quantity")
        if qty <= 0:
            raise ValueError("A parcel contains a non-positive dispatched quantity.")
        gross_goods += qty * _decimal(order_item.unit_price, "Unit price")
        cost_goods += qty * _decimal(batch.unit_cost, "Batch unit cost")
        quantities_by_item[order_item.id] = (
            quantities_by_item.get(order_item.id, Decimal("0")) + qty
        )

    order = session.get(SalesOrder, parcel.order_id)
    if order is None:
        raise ValueError("The parcel's sales order was not found.")
    subtotal = _decimal(order.subtotal, "Order subtotal")
    discount = _decimal(order.discount_amount, "Order discount")
    if subtotal < 0 or discount < 0 or discount > subtotal:
        raise ValueError("The order's subtotal or discount is invalid.")

    # Allocate the order-level discount proportionally across delivered goods.
    allocated_discount = (
        (discount * gross_goods / subtotal).quantize(CENT, rounding=ROUND_HALF_UP)
        if subtotal > 0 else Decimal("0.00")
    )
    net_goods = _money(gross_goods - allocated_discount)
    delivery_charge = _money(
        parcel.customer_delivery_charge if delivery_charge_override is None
        else delivery_charge_override
    )
    if net_goods < 0 or delivery_charge < 0:
        raise ValueError("Calculated delivery amounts cannot be negative.")

    return order, rows, quantities_by_item, net_goods, delivery_charge, _money(cost_goods)


def confirm_parcel_delivery(session, parcel_id, *, username, changed_by_id=None,
                            recipient_name=None, proof_of_delivery_path=None,
                            delivered_at=None):
    """Confirm a delivered COD parcel and recognize its sales and COGS.

    This intentionally handles COD orders only. Non-COD receipts require their
    own verified-payment workflow and must not be treated as courier receivable.
    Caller owns commit/rollback.
    """
    username = str(username or "").strip()
    if not username:
        raise ValueError("Authenticated username is required.")
    parcel = session.get(DispatchParcel, parcel_id)
    if parcel is None:
        raise ValueError("Dispatch parcel was not found.")
    if parcel.parcel_status == "delivered":
        key = f"PARCEL-DELIVERY-{parcel.id}"
        existing = session.query(JournalEntry).filter_by(idempotency_key=key).first()
        if existing and existing.status == "posted":
            return existing.id
        raise ValueError("Parcel is marked delivered but its posted journal is missing.")
    if parcel.parcel_status != "handed_over" or not parcel.handed_to_courier_at:
        raise ValueError("Only a parcel handed to the courier can be delivered.")

    # Allocate the order's delivery charge only when this parcel completes
    # delivery of every ordered item. This avoids charging the full delivery
    # fee on each partial parcel and still works if an earlier parcel fails.
    order = session.get(SalesOrder, parcel.order_id)
    if order is None:
        raise ValueError("The parcel's sales order was not found.")
    parcel_rows = (
        session.query(DispatchParcelItem, SalesOrderItem)
        .join(SalesOrderItem, SalesOrderItem.id == DispatchParcelItem.order_item_id)
        .filter(DispatchParcelItem.parcel_id == parcel.id)
        .all()
    )
    if not parcel_rows:
        raise ValueError("This parcel has no dispatched item lines.")
    current_quantities = {}
    for parcel_item, order_item in parcel_rows:
        qty = _decimal(parcel_item.quantity_dispatched, "Dispatched quantity")
        current_quantities[order_item.id] = current_quantities.get(
            order_item.id, Decimal("0")
        ) + qty
        if _decimal(order_item.quantity_delivered, "Delivered quantity") + current_quantities[order_item.id] > _decimal(
            order_item.quantity_ordered, "Ordered quantity"
        ):
            raise ValueError("This delivery would exceed the ordered quantity.")
    all_order_items = session.query(SalesOrderItem).filter_by(order_id=order.id).all()
    order_fully_delivered = bool(all_order_items) and all(
        _decimal(item.quantity_delivered, "Delivered quantity")
        + current_quantities.get(item.id, Decimal("0"))
        >= _decimal(item.quantity_ordered, "Ordered quantity")
        for item in all_order_items
    )
    delivery_charge_for_this_parcel = (
        _money(order.delivery_charge) if order_fully_delivered else Decimal("0.00")
    )
    parcel.customer_delivery_charge = delivery_charge_for_this_parcel
    order, rows, quantities, goods_revenue, delivery_revenue, cogs = \
        _parcel_delivery_values(
            session, parcel,
            delivery_charge_override=delivery_charge_for_this_parcel,
        )
    if str(order.payment_method).lower() != "cod":
        raise ValueError(
            "This delivery service currently handles COD orders only. "
            "Use the verified-payment workflow for prepaid orders."
        )
    receivable = _money(goods_revenue + delivery_revenue)
    if receivable <= 0:
        raise ValueError("The parcel has no positive COD amount to recognize.")

    lines = [{
        "account_code": "1130", "debit": receivable, "credit": 0,
        "description": "COD receivable from courier for delivered parcel",
    }]
    if goods_revenue > 0:
        lines.append({
            "account_code": "4100", "debit": 0, "credit": goods_revenue,
            "description": "Delivered product sales, net of allocated discount",
        })
    if delivery_revenue > 0:
        lines.append({
            "account_code": "4200", "debit": 0, "credit": delivery_revenue,
            "description": "Customer delivery charge",
        })
    if cogs > 0:
        lines.extend([
            {"account_code": "5100", "debit": cogs, "credit": 0,
             "description": "Cost of delivered products"},
            {"account_code": "1180", "debit": 0, "credit": cogs,
             "description": "Release delivered goods from inventory in transit"},
        ])

    now = delivered_at or datetime.now()
    journal_id = _post_journal_once(
        session,
        key=f"PARCEL-DELIVERY-{parcel.id}",
        entry_date=now.date(),
        description=f"COD delivery recognized: {parcel.dispatch_reference}",
        lines=lines,
        username=username,
        source_module="delivery",
        reference_type="dispatch_parcel",
        reference_id=parcel.id,
    )

    old_status = parcel.parcel_status
    parcel.parcel_status = "delivered"
    parcel.delivered_at = now
    parcel.delivery_outcome = "delivered"
    if recipient_name:
        parcel.recipient_name = str(recipient_name).strip()[:150]
    if proof_of_delivery_path:
        parcel.proof_of_delivery_path = str(proof_of_delivery_path)
    parcel.updated_at = now

    for item_id, qty in quantities.items():
        item = session.get(SalesOrderItem, item_id)
        item.quantity_delivered = (
            _decimal(item.quantity_delivered, "Previously delivered quantity") + qty
        )

    # The customer has paid the courier at successful COD delivery. This
    # updates customer payment status now; the separate COD remittance event
    # later clears the courier receivable when money reaches the business.
    collected_payment = session.query(OrderPayment).filter_by(
        transaction_reference=f"PARCEL:{parcel.id}:DELIVERY"
    ).first()
    if collected_payment is None:
        session.add(OrderPayment(
            order_id=order.id,
            payment_method="courier_cod_collection",
            amount=receivable,
            payment_status="verified",
            payment_date=now,
            transaction_reference=f"PARCEL:{parcel.id}:DELIVERY",
            account_id=_account_id(session, "1130"),
            verified_by_id=changed_by_id,
            notes=f"Customer COD collected by courier; journal_entry_id={journal_id}",
            created_at=now,
        ))
        order.amount_paid = _money(_decimal(order.amount_paid, "Amount paid") + receivable)
        order.payment_status = (
            "paid" if _decimal(order.amount_paid, "Amount paid") >= _decimal(order.total_amount, "Order total")
            else "partially_paid"
        )

    order_items = session.query(SalesOrderItem).filter_by(order_id=order.id).all()
    all_delivered = bool(order_items) and all(
        _decimal(item.quantity_delivered, "Delivered quantity")
        >= _decimal(item.quantity_ordered, "Ordered quantity")
        for item in order_items
    )
    any_delivered = any(
        _decimal(item.quantity_delivered, "Delivered quantity") > 0
        for item in order_items
    )
    if all_delivered:
        order.order_status = "delivered"
        order.fulfilment_status = "delivered"
        order.delivered_at = now
    elif any_delivered:
        order.order_status = "partially_delivered"
        order.fulfilment_status = "partially_delivered"
    order.updated_at = now

    session.add(OrderStatusHistory(
        order_id=order.id,
        parcel_id=parcel.id,
        status_type="delivery_status",
        old_status=old_status,
        new_status="delivered",
        notes=f"Delivery confirmed; accounting journal {journal_id} posted.",
        changed_by_id=changed_by_id,
        changed_at=now,
    ))
    session.add(AuditLog(
        module="delivery", action="parcel_delivered",
        record_type="DispatchParcel", record_id=parcel.id,
        user_id=changed_by_id, username=username,
        new_values=(
            f'{{"journal_entry_id": {journal_id}, '
            f'"cod_amount": "{receivable}", "cogs": "{cogs}"}}'
        ),
        reason="Courier delivery confirmed",
    ))
    session.flush()
    return journal_id


def record_cod_remittance(session, parcel_id, *, remitted_amount,
                          courier_fee=0, transaction_reference,
                          username, changed_by_id=None, received_at=None):
    """Record a courier's COD remittance, allowing genuine partial settlements.

    Debit Bank for cash received and courier fee expense for a documented
    deduction; credit COD Receivable for their combined gross settlement.
    Caller owns commit/rollback.
    """
    username = str(username or "").strip()
    reference = str(transaction_reference or "").strip()
    if not username:
        raise ValueError("Authenticated username is required.")
    if not reference:
        raise ValueError("Courier settlement reference is required.")
    if len(reference) > 100:
        raise ValueError("Courier settlement reference cannot exceed 100 characters.")

    parcel = session.get(DispatchParcel, parcel_id)
    if parcel is None or parcel.parcel_status != "delivered":
        raise ValueError("COD can only be settled for a delivered parcel.")
    order = session.get(SalesOrder, parcel.order_id)
    if order is None or str(order.payment_method).lower() != "cod":
        raise ValueError("This parcel is not linked to a COD order.")
    delivery_key = f"PARCEL-DELIVERY-{parcel.id}"
    delivery_entry = session.query(JournalEntry).filter_by(
        idempotency_key=delivery_key, status="posted"
    ).first()
    if delivery_entry is None:
        raise ValueError("The parcel's delivery accounting must be posted first.")

    remitted = _money(remitted_amount)
    fee = _money(courier_fee)
    gross_settlement = _money(remitted + fee)
    if remitted <= 0 or fee < 0 or gross_settlement <= 0:
        raise ValueError("Remittance must be positive and courier fee cannot be negative.")

    token = re.sub(r"[^A-Za-z0-9_-]+", "-", reference.casefold()).strip("-")[:60]
    if not token:
        raise ValueError("Settlement reference must contain letters or numbers.")
    key = f"COD-REMIT-{token}"
    existing = session.query(JournalEntry).filter_by(idempotency_key=key).first()
    if existing:
        if existing.status != "posted":
            raise ValueError("An unfinished journal exists for this settlement reference.")
        existing_payment = session.query(OrderPayment).filter_by(
            transaction_reference=f"PARCEL:{parcel.id}:{reference}"
        ).first()
        if existing_payment is None:
            raise ValueError("The existing settlement journal has no matching payment record.")
        existing_fee = Decimal("0.00")
        if existing_payment.notes and "fee=" in existing_payment.notes:
            existing_fee = _money(existing_payment.notes.split("fee=", 1)[1])
        if (_money(existing_payment.amount) == remitted and existing_fee == fee):
            return existing.id
        raise ValueError("This settlement reference was already used with different amounts.")

    # Prevent aggregate settlements from exceeding the parcel's recognized COD.
    _, _, _, goods_revenue, delivery_revenue, _ = _parcel_delivery_values(session, parcel)
    total_due = _money(goods_revenue + delivery_revenue)
    prior_payments = session.query(OrderPayment).filter(
        OrderPayment.order_id == order.id,
        OrderPayment.payment_method == "courier_cod_remittance",
        OrderPayment.payment_status == "verified",
        OrderPayment.transaction_reference.like(f"PARCEL:{parcel.id}:%"),
    ).all()
    already_settled = sum(
        (_money(payment.amount) + _money(payment.notes.split("fee=", 1)[1])
         if payment.notes and "fee=" in payment.notes
         else _money(payment.amount) for payment in prior_payments),
        Decimal("0.00"),
    )
    if already_settled + gross_settlement > total_due:
        raise ValueError(
            f"Settlement exceeds outstanding COD. Outstanding: "
            f"{_money(total_due - already_settled)}."
        )

    now = received_at or datetime.now()
    bank_account_id = _account_id(session, "1120")
    lines = [{
        "account_code": "1120", "debit": remitted, "credit": 0,
        "description": "COD remittance received in bank",
    }]
    if fee > 0:
        lines.append({
            "account_code": "6100", "debit": fee, "credit": 0,
            "description": "Courier fee deducted from COD remittance",
        })
    lines.append({
        "account_code": "1130", "debit": 0, "credit": gross_settlement,
        "description": "Clear COD receivable for courier settlement",
    })
    journal_id = _post_journal_once(
        session,
        key=key,
        entry_date=now.date(),
        description=f"Courier COD remittance: {parcel.dispatch_reference} / {reference}",
        lines=lines,
        username=username,
        source_module="cod_settlement",
        reference_type="dispatch_parcel",
        reference_id=parcel.id,
    )

    session.add(OrderPayment(
        order_id=order.id,
        payment_method="courier_cod_remittance",
        amount=remitted,
        payment_status="verified",
        payment_date=now,
        transaction_reference=f"PARCEL:{parcel.id}:{reference}",
        account_id=bank_account_id,
        verified_by_id=changed_by_id,
        notes=f"journal_entry_id={journal_id};fee={fee}",
        created_at=now,
    ))
    session.add(AuditLog(
        module="cod_settlement", action="cod_remittance_recorded",
        record_type="DispatchParcel", record_id=parcel.id,
        user_id=changed_by_id, username=username,
        new_values=(
            f'{{"journal_entry_id": {journal_id}, '
            f'"remitted_amount": "{remitted}", "courier_fee": "{fee}"}}'
        ),
        reason=f"Courier settlement reference: {reference}",
    ))
    session.flush()
    return journal_id


def record_parcel_return_to_warehouse(session, parcel_id, *, reason, username,
                                      changed_by_id=None, received_at=None):
    """Record a failed parcel physically returned to the warehouse.

    Restores the original batches and reservations and transfers inventory
    value from Inventory in Transit back to Inventory. The caller owns the
    transaction and must commit or roll back all changes together.
    """
    username = str(username or "").strip()
    reason = str(reason or "").strip()
    if not username:
        raise ValueError("Authenticated username is required.")
    if not reason:
        raise ValueError("A reason for the returned parcel is required.")

    parcel = session.get(DispatchParcel, parcel_id)
    if parcel is None:
        raise ValueError("Dispatch parcel was not found.")
    key = f"PARCEL-RETURN-{parcel.id}"
    existing = session.query(JournalEntry).filter_by(idempotency_key=key).first()
    if parcel.parcel_status == "returned_to_warehouse":
        if existing and existing.status == "posted":
            return existing.id
        if existing is None:
            # Zero-cost parcels legitimately have no journal; their final
            # status and movement history are the durable event marker.
            return None
        raise ValueError("Parcel is marked returned but its accounting journal is not posted.")
    if existing is not None:
        raise ValueError("A return journal already exists while the parcel is not marked returned. Manual review is required.")
    if parcel.parcel_status != "handed_over" or not parcel.handed_to_courier_at:
        raise ValueError("Only a parcel handed to the courier and not delivered can be returned.")

    rows = (
        session.query(DispatchParcelItem, StockReservation, InventoryBatch, SalesOrderItem)
        .join(StockReservation, StockReservation.id == DispatchParcelItem.reservation_id)
        .join(InventoryBatch, InventoryBatch.id == StockReservation.batch_id)
        .join(SalesOrderItem, SalesOrderItem.id == DispatchParcelItem.order_item_id)
        .filter(DispatchParcelItem.parcel_id == parcel.id)
        .all()
    )
    if not rows:
        raise ValueError("This parcel has no dispatched item lines.")

    total_value = Decimal("0.00")
    now = received_at or datetime.now()
    affected_item_ids = set()
    for parcel_item, reservation, batch, order_item in rows:
        qty = _decimal(parcel_item.quantity_dispatched, "Returned quantity")
        if qty <= 0:
            raise ValueError("A parcel contains an invalid dispatched quantity.")
        dispatched = _decimal(reservation.quantity_dispatched, "Reservation dispatched quantity")
        if qty > dispatched:
            raise ValueError("Returned parcel quantity exceeds the reservation's dispatched quantity.")
        reservation.quantity_dispatched = dispatched - qty
        reservation.reservation_status = (
            "reserved" if reservation.quantity_dispatched <= 0 else "partially_dispatched"
        )
        batch.remaining_quantity = _decimal(batch.remaining_quantity, "Batch quantity") + qty
        total_value += qty * _decimal(batch.unit_cost, "Batch unit cost")
        session.add(StockMovement(
            product_id=order_item.product_id, batch_id=batch.id,
            movement_type="courier_return_received", quantity_change=qty,
            reference_type="dispatch_parcel", reference_id=parcel.id,
            note=f"Parcel returned to warehouse: {reason}",
        ))
        affected_item_ids.add(order_item.id)

    for item_id in affected_item_ids:
        item = session.get(SalesOrderItem, item_id)
        reservations = session.query(StockReservation).filter_by(order_item_id=item_id).all()
        item.quantity_dispatched = sum(
            (_decimal(r.quantity_dispatched, "Dispatched quantity") for r in reservations),
            Decimal("0"),
        )

    total_value = total_value.quantize(CENT, rounding=ROUND_HALF_UP)
    journal_id = None
    if total_value > 0:
        journal_id = _post_journal_once(
            session, key=key, entry_date=now.date(),
            description=f"Courier parcel returned to warehouse: {parcel.dispatch_reference}",
            lines=[
                {"account_code": "1150", "debit": total_value, "credit": 0,
                 "description": "Restore returned goods to warehouse inventory"},
                {"account_code": "1180", "debit": 0, "credit": total_value,
                 "description": "Release returned goods from inventory in transit"},
            ], username=username, source_module="delivery",
            reference_type="dispatch_parcel", reference_id=parcel.id,
        )
    else:
        # A zero-cost parcel still needs a durable event marker to prevent
        # repeated physical stock restoration. Zero-value journals are invalid,
        # so the parcel state and stock movement references provide idempotency.
        journal_id = None

    old_status = parcel.parcel_status
    parcel.parcel_status = "returned_to_warehouse"
    parcel.delivery_outcome = "returned_to_warehouse"
    parcel.updated_at = now

    order = session.get(SalesOrder, parcel.order_id)
    items = session.query(SalesOrderItem).filter_by(order_id=order.id).all()
    any_delivered = any(_decimal(x.quantity_delivered, "Delivered quantity") > 0 for x in items)
    all_dispatched = bool(items) and all(
        _decimal(x.quantity_dispatched, "Dispatched quantity") >= _decimal(x.quantity_ordered, "Ordered quantity")
        for x in items
    )
    any_dispatched = any(_decimal(x.quantity_dispatched, "Dispatched quantity") > 0 for x in items)
    if any_delivered:
        order.order_status = "partially_delivered"
        order.fulfilment_status = "partially_delivered"
    elif all_dispatched:
        order.order_status = "dispatched"
        order.fulfilment_status = "dispatched"
    elif any_dispatched:
        order.order_status = "partially_dispatched"
        order.fulfilment_status = "partially_dispatched"
    else:
        order.order_status = "confirmed"
        order.fulfilment_status = "reserved"
    order.updated_at = now

    session.add(OrderStatusHistory(
        order_id=order.id, parcel_id=parcel.id,
        status_type="delivery_status", old_status=old_status,
        new_status="returned_to_warehouse",
        notes=f"Physical parcel return recorded. Reason: {reason}. Journal: {journal_id or 'zero-cost'}.",
        changed_by_id=changed_by_id, changed_at=now,
    ))
    session.add(AuditLog(
        module="delivery", action="parcel_returned_to_warehouse",
        record_type="DispatchParcel", record_id=parcel.id,
        user_id=changed_by_id, username=username,
        new_values=(f'{{"journal_entry_id": {journal_id}, "inventory_value": "{total_value}"}}'),
        reason=reason,
    ))
    session.flush()
    return journal_id
