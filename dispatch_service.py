from datetime import datetime
from decimal import Decimal
from decimal import Decimal, InvalidOperation

from models import InventoryBatch, StockMovement
from accounting_service import create_draft_entry, post_journal_entry
from orders_models import (
    SalesOrder,
    SalesOrderItem,
    StockReservation,
    DispatchParcel,
    DispatchParcelItem,
    OrderStatusHistory,
)

ACTIVE_RESERVATION_STATUSES = ("reserved", "partially_dispatched")


def _decimal(value):
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def hand_over_parcel(
    session,
    parcel_id,
    dispatch_lines,
    changed_by_id=None,
    username="admin",
):
    """
    Hand a prepared parcel to its courier and deduct only the quantities
    physically handed over.

    dispatch_lines format:
        [
            {"reservation_id": 12, "quantity": "2"},
            {"reservation_id": 13, "quantity": "1.5"},
        ]

    The caller controls commit/rollback. All stock, reservation,
    parcel and order updates must be committed together.
    """
    parcel = session.get(DispatchParcel, parcel_id)

    if parcel is None:
        raise ValueError("Dispatch parcel was not found.")

    if parcel.parcel_status != "prepared" or parcel.handed_to_courier_at:
        raise ValueError(
            "This parcel is not in the prepared state. "
            "It may already have been handed to the courier."
        )

    if parcel.courier_id is None:
        raise ValueError("Assign a courier before handing over the parcel.")

    order = session.get(SalesOrder, parcel.order_id)

    if order is None:
        raise ValueError("The parcel's sales order was not found.")

    if order.order_status not in ("confirmed", "partially_dispatched"):
        raise ValueError(
            f"This order cannot be dispatched. "
            f"Current order status: {order.order_status}."
        )

    if order.fulfilment_status not in ("reserved", "partially_dispatched"):
        raise ValueError(
            f"This order has no dispatchable reserved stock. "
            f"Current fulfilment status: {order.fulfilment_status}."
        )

    if not dispatch_lines:
        raise ValueError("Add at least one product quantity to this parcel.")

    # Validate every line before changing any inventory.
    planned = []
    seen_reservations = set()

    for line in dispatch_lines:
        reservation_id = line.get("reservation_id")
        quantity = _decimal(line.get("quantity"))

        if reservation_id is None:
            raise ValueError("A reservation ID is missing from a dispatch line.")

        if reservation_id in seen_reservations:
            raise ValueError(
                "A reservation appears more than once in this parcel."
            )
        seen_reservations.add(reservation_id)

        if quantity <= 0:
            raise ValueError("Dispatch quantities must be greater than zero.")

        reservation = session.get(StockReservation, reservation_id)

        if reservation is None or reservation.order_id != order.id:
            raise ValueError(
                f"Reservation {reservation_id} does not belong to this order."
            )

        if reservation.reservation_status not in ACTIVE_RESERVATION_STATUSES:
            raise ValueError(
                f"Reservation {reservation_id} is not available for dispatch."
            )

        outstanding = max(
            Decimal("0"),
            _decimal(reservation.quantity_reserved)
            - _decimal(reservation.quantity_dispatched),
        )

        if quantity > outstanding:
            raise ValueError(
                f"Dispatch quantity exceeds the outstanding reservation "
                f"for reservation {reservation_id}. "
                f"Outstanding: {outstanding}; requested: {quantity}."
            )

        batch = session.get(InventoryBatch, reservation.batch_id)

        if batch is None or not batch.is_active:
            raise ValueError(
                f"The inventory batch for reservation {reservation_id} "
                f"is missing or inactive."
            )

        physical_quantity = _decimal(batch.remaining_quantity)

        if quantity > physical_quantity:
            raise ValueError(
                f"Insufficient physical batch quantity for reservation "
                f"{reservation_id}. Available: {physical_quantity}."
            )

        item = session.get(SalesOrderItem, reservation.order_item_id)

        if item is None or item.order_id != order.id:
            raise ValueError(
                f"The order item for reservation {reservation_id} was not found."
            )

        planned.append((reservation, batch, item, quantity))

    now = datetime.now()
    affected_item_ids = set()

    # Apply all validated dispatch lines.
    # Physical stock leaves the warehouse here. Move its carrying value from
    # Inventory to Inventory in Transit; revenue/COGS are recognized only
    # after confirmed delivery.
    transit_value = Decimal("0.00")
    for reservation, batch, item, quantity in planned:
        transit_value += (quantity * _decimal(batch.unit_cost))
        reservation.quantity_dispatched = (
            _decimal(reservation.quantity_dispatched) + quantity
        )

        if (
            _decimal(reservation.quantity_dispatched)
            >= _decimal(reservation.quantity_reserved)
        ):
            reservation.reservation_status = "dispatched"
        else:
            reservation.reservation_status = "partially_dispatched"

        # This is the point at which physical stock is deducted.
        batch.remaining_quantity = (
            _decimal(batch.remaining_quantity) - quantity
        )

        session.add(DispatchParcelItem(
            parcel_id=parcel.id,
            reservation_id=reservation.id,
            order_item_id=item.id,
            product_id=item.product_id,
            quantity_dispatched=quantity,
            created_at=now,
        ))

        session.add(StockMovement(
            product_id=item.product_id,
            batch_id=batch.id,
            movement_type="sale_dispatch",
            quantity_change=-quantity,
            reference_type="dispatch_parcel",
            reference_id=parcel.id,
            note=(
                f"Courier handover for order {order.order_number}; "
                f"reservation {reservation.id}."
            ),
        ))

        affected_item_ids.add(item.id)

    # Refresh cumulative dispatched quantities on the order items.
    for item_id in affected_item_ids:
        item = session.get(SalesOrderItem, item_id)
        reservations = (
            session.query(StockReservation)
            .filter(StockReservation.order_item_id == item_id)
            .all()
        )
        item.quantity_dispatched = sum(
            (_decimal(r.quantity_dispatched) for r in reservations),
            Decimal("0"),
        )

    old_fulfilment_status = order.fulfilment_status

    all_items = (
        session.query(SalesOrderItem)
        .filter(SalesOrderItem.order_id == order.id)
        .all()
    )

    fully_dispatched = bool(all_items) and all(
        _decimal(item.quantity_dispatched)
        >= _decimal(item.quantity_ordered)
        for item in all_items
    )

    parcel.parcel_status = "handed_over"
    parcel.handed_to_courier_at = now
    parcel.updated_at = now

    order.dispatched_at = order.dispatched_at or now
    order.updated_at = now

    if fully_dispatched:
        order.fulfilment_status = "dispatched"
        order.order_status = "dispatched"
    else:
        order.fulfilment_status = "partially_dispatched"

    transit_value = transit_value.quantize(Decimal("0.01"))
    if transit_value > 0:
        journal_id = create_draft_entry(
            entry_date=now.date(),
            description=f"Inventory transferred to courier: {parcel.dispatch_reference}",
            lines=[
                {"account_code": "1180", "debit": transit_value, "credit": 0,
                 "description": "Inventory in transit"},
                {"account_code": "1150", "debit": 0, "credit": transit_value,
                 "description": "Warehouse inventory dispatched"},
            ],
            username=str(username or "admin"),
            source_module="dispatch",
            reference_type="dispatch_parcel",
            reference_id=parcel.id,
            idempotency_key=f"PARCEL-HANDOVER-{parcel.id}",
            db=session,
        )
        post_journal_entry(journal_id, username=str(username or "admin"), db=session)

    session.add(OrderStatusHistory(
        order_id=order.id,
        parcel_id=parcel.id,
        status_type="fulfilment_status",
        old_status=old_fulfilment_status,
        new_status=order.fulfilment_status,
        notes=(
            f"Parcel {parcel.dispatch_reference} handed to courier. "
            f"Physical stock deducted for {len(planned)} reservation line(s)."
        ),
        changed_by_id=changed_by_id,
        changed_at=now,
    ))

    session.flush()
    return parcel
