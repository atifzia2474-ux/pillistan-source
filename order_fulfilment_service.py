from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from models import InventoryBatch
from orders_models import (
    SalesOrder,
    SalesOrderItem,
    StockReservation,
    OrderStatusHistory,
)


ACTIVE_RESERVATION_STATUSES = ("reserved", "partially_dispatched")


def _decimal(value):
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def get_available_batch_quantity(session, batch):
    """
    Physical remaining quantity minus quantities still reserved
    for orders. This does not change physical inventory.
    """
    outstanding = Decimal("0")

    reservations = (
        session.query(StockReservation)
        .filter(
            StockReservation.batch_id == batch.id,
            StockReservation.reservation_status.in_(
                ACTIVE_RESERVATION_STATUSES
            ),
        )
        .all()
    )

    for reservation in reservations:
        outstanding += max(
            Decimal("0"),
            _decimal(reservation.quantity_reserved)
            - _decimal(reservation.quantity_dispatched),
        )

    return max(
        Decimal("0"),
        _decimal(batch.remaining_quantity) - outstanding,
    )


def confirm_order(
    session,
    order_id,
    approved_by_id=None,
    changed_by_id=None,
):
    """
    Confirm a draft order and reserve stock from eligible batches.

    Uses FEFO: earliest expiry date first; batches without an expiry
    date are considered after dated batches.

    Physical batch quantities are NOT reduced here.
    The caller is responsible for commit/rollback.
    """
    order = session.get(SalesOrder, order_id)

    if order is None:
        raise ValueError("Order was not found.")

    if order.order_status != "draft":
        raise ValueError(
            f"Only draft orders can be confirmed. Current status: "
            f"{order.order_status}."
        )

    items = (
        session.query(SalesOrderItem)
        .filter(SalesOrderItem.order_id == order.id)
        .order_by(SalesOrderItem.id)
        .all()
    )

    if not items:
        raise ValueError("This order has no items.")

    today = date.today()
    batch_cache = {}
    planned_allocations = []
    reserved_in_plan = {}

    # Validate and plan all reservations before creating any records.
    for item in items:
        required = _decimal(item.quantity_ordered)

        if required <= 0:
            raise ValueError(
                f"Invalid quantity for {item.product_name_snapshot}."
            )

        if item.quantity_reserved and _decimal(item.quantity_reserved) > 0:
            raise ValueError(
                f"{item.product_name_snapshot} already has a reservation."
            )

        if item.product_id not in batch_cache:
            batches = (
                session.query(InventoryBatch)
                .filter(
                    InventoryBatch.product_id == item.product_id,
                    InventoryBatch.is_active.is_(True),
                    InventoryBatch.remaining_quantity > 0,
                )
                .order_by(
                    InventoryBatch.expiry_date.is_(None),
                    InventoryBatch.expiry_date,
                    InventoryBatch.received_date,
                    InventoryBatch.id,
                )
                .all()
            )

            batch_cache[item.product_id] = [
                batch for batch in batches
                if batch.expiry_date is None or batch.expiry_date >= today
            ]

        remaining_needed = required

        for batch in batch_cache[item.product_id]:
            already_planned = reserved_in_plan.get(batch.id, Decimal("0"))
            available = (
                get_available_batch_quantity(session, batch)
                - already_planned
            )

            if available <= 0:
                continue

            allocation = min(remaining_needed, available)

            if allocation > 0:
                planned_allocations.append((item, batch, allocation))
                reserved_in_plan[batch.id] = already_planned + allocation
                remaining_needed -= allocation

            if remaining_needed <= 0:
                break

        if remaining_needed > 0:
            total_available = required - remaining_needed
            raise ValueError(
                f"Insufficient available stock for "
                f"'{item.product_name_snapshot}'. "
                f"Required: {required}; available: {total_available}."
            )

    now = datetime.now()
    item_reserved_totals = {}

    for item, batch, quantity in planned_allocations:
        reservation = StockReservation(
            order_id=order.id,
            order_item_id=item.id,
            product_id=item.product_id,
            batch_id=batch.id,
            quantity_reserved=quantity,
            quantity_dispatched=Decimal("0"),
            reservation_status="reserved",
            reserved_at=now,
            notes="Reserved when order was confirmed.",
        )
        session.add(reservation)

        item_reserved_totals[item.id] = (
            item_reserved_totals.get(item.id, Decimal("0")) + quantity
        )

    for item in items:
        item.quantity_reserved = item_reserved_totals.get(
            item.id, Decimal("0")
        )

    old_status = order.order_status
    order.order_status = "confirmed"
    order.fulfilment_status = "reserved"
    order.confirmed_at = now
    order.approved_by_id = approved_by_id
    order.updated_at = now

    session.add(OrderStatusHistory(
        order_id=order.id,
        status_type="order_status",
        old_status=old_status,
        new_status="confirmed",
        notes="Order confirmed and stock reserved.",
        changed_by_id=changed_by_id,
        changed_at=now,
    ))

    session.flush()
    return order
