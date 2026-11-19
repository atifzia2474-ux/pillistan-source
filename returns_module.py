from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.orm import Session

from database import Base
from models import Customer, InventoryBatch, StockMovement, AuditLog, JournalEntry
from orders_models import SalesOrder, SalesOrderItem, StockReservation, DispatchParcelItem


def _decimal(value):
    try:
        result = Decimal(str(value if value is not None else "0"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Enter a valid number.")
    if not result.is_finite():
        raise ValueError("Enter a valid number.")
    return result


def _qty(value):
    result = _decimal(value)
    if result < 0:
        raise ValueError("Quantity cannot be negative.")
    return result


def _money(value):
    result = _decimal(value).quantize(Decimal("0.01"))
    if result < 0:
        raise ValueError("Amount cannot be negative.")
    return result


class ReturnRequest(Base):
    __tablename__ = "return_requests"
    id = Column(Integer, primary_key=True)
    return_number = Column(String(40), unique=True, nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("sales_orders.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    status = Column(String(24), nullable=False, default="pending", index=True)
    reason = Column(String(500), nullable=False)
    notes = Column(Text)
    requested_at = Column(DateTime, nullable=False, default=datetime.now)
    created_by = Column(String(100), nullable=False, default="admin")
    approved_by = Column(String(100))
    approved_at = Column(DateTime)
    received_at = Column(DateTime)
    inspected_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)


class ReturnItem(Base):
    __tablename__ = "return_items"
    id = Column(Integer, primary_key=True)
    return_id = Column(Integer, ForeignKey("return_requests.id"), nullable=False, index=True)
    order_item_id = Column(Integer, ForeignKey("sales_order_items.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    product_name_snapshot = Column(String(255), nullable=False)
    sku_snapshot = Column(String(100))
    quantity_requested = Column(Numeric(14, 3), nullable=False)
    quantity_approved = Column(Numeric(14, 3), nullable=False, default=0)
    quantity_received = Column(Numeric(14, 3), nullable=False, default=0)
    quantity_resellable = Column(Numeric(14, 3), nullable=False, default=0)
    quantity_damaged = Column(Numeric(14, 3), nullable=False, default=0)
    quantity_expired = Column(Numeric(14, 3), nullable=False, default=0)
    quantity_rejected = Column(Numeric(14, 3), nullable=False, default=0)
    inspected = Column(Integer, nullable=False, default=0)
    notes = Column(Text)


class ReturnInspection(Base):
    __tablename__ = "return_inspections"
    id = Column(Integer, primary_key=True)
    return_item_id = Column(Integer, ForeignKey("return_items.id"), nullable=False, index=True)
    source_batch_id = Column(Integer, ForeignKey("inventory_batches.id"), nullable=False, index=True)
    quantity_resellable = Column(Numeric(14, 3), nullable=False, default=0)
    quantity_damaged = Column(Numeric(14, 3), nullable=False, default=0)
    quantity_expired = Column(Numeric(14, 3), nullable=False, default=0)
    quantity_rejected = Column(Numeric(14, 3), nullable=False, default=0)
    inspected_by = Column(String(100), nullable=False)
    inspected_at = Column(DateTime, nullable=False, default=datetime.now)
    notes = Column(Text)


class ReturnRefund(Base):
    __tablename__ = "return_refunds"
    id = Column(Integer, primary_key=True)
    return_id = Column(Integer, ForeignKey("return_requests.id"), nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    payment_method = Column(String(20), nullable=False)
    account_code = Column(String(10), nullable=False)
    payment_reference = Column(String(120))
    status = Column(String(20), nullable=False, default="paid")
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False)
    idempotency_key = Column(String(100), unique=True, nullable=False)
    paid_by = Column(String(100), nullable=False)
    paid_at = Column(DateTime, nullable=False, default=datetime.now)
    notes = Column(Text)


def _audit(db, action, record_type, record_id, username, old=None, new=None, reason=None, user_id=None):
    import json
    db.add(AuditLog(
        module="returns", action=action, record_type=record_type,
        record_id=record_id, user_id=user_id, username=username,
        old_values=json.dumps(old, default=str) if old is not None else None,
        new_values=json.dumps(new, default=str) if new is not None else None,
        reason=reason
    ))


def _items(db, return_id):
    return db.query(ReturnItem).filter(
        ReturnItem.return_id == return_id
    ).order_by(ReturnItem.id).all()


def _already_requested(db, order_item_id):
    rows = (
        db.query(ReturnItem, ReturnRequest)
        .join(ReturnRequest, ReturnRequest.id == ReturnItem.return_id)
        .filter(
            ReturnItem.order_item_id == order_item_id,
            ReturnRequest.status != "rejected"
        ).all()
    )
    return sum((_qty(item.quantity_requested) for item, _ in rows), Decimal("0"))


def create_return_request(db: Session, order_id, items, reason, username="admin", notes=None, changed_by_id=None):
    order = db.get(SalesOrder, int(order_id))
    if order is None:
        raise ValueError("Sales order was not found.")
    if order.order_status in ("draft", "cancelled"):
        raise ValueError("A return requires a confirmed, partially dispatched or delivered order.")
    if not str(reason or "").strip():
        raise ValueError("A return reason is required.")
    if not items:
        raise ValueError("Add at least one item.")

    validated = []
    seen = set()
    for line in items:
        item_id = int(line["order_item_id"])
        if item_id in seen:
            raise ValueError("The same order item cannot be added twice.")
        seen.add(item_id)
        order_item = db.get(SalesOrderItem, item_id)
        if order_item is None or order_item.order_id != order.id:
            raise ValueError("An item does not belong to the selected order.")
        quantity = _qty(line["quantity"])
        if quantity <= 0:
            raise ValueError("Return quantity must be greater than zero.")
        dispatched = _qty(order_item.quantity_dispatched)
        remaining = max(Decimal("0"), dispatched - _already_requested(db, item_id))
        if quantity > remaining:
            raise ValueError(
                f"{order_item.product_name_snapshot}: only {remaining} dispatched units "
                "remain eligible for return."
            )
        validated.append((order_item, quantity))

    now = datetime.now()
    request = ReturnRequest(
        return_number=f"RET-{now:%Y%m%d}-{uuid4().hex[:6].upper()}",
        order_id=order.id, customer_id=order.customer_id,
        status="pending", reason=str(reason).strip(), notes=notes,
        requested_at=now, created_by=username, created_at=now, updated_at=now
    )
    db.add(request)
    db.flush()
    for order_item, quantity in validated:
        db.add(ReturnItem(
            return_id=request.id, order_item_id=order_item.id,
            product_id=order_item.product_id,
            product_name_snapshot=order_item.product_name_snapshot,
            sku_snapshot=order_item.sku_snapshot,
            quantity_requested=quantity, quantity_approved=Decimal("0")
        ))
    _audit(db, "return_requested", "ReturnRequest", request.id, username,
           new={"return_number": request.return_number, "order_id": order.id,
                "reason": reason,
                "items": [{"order_item_id": x.id, "quantity": str(q)} for x, q in validated]},
           user_id=changed_by_id)
    db.flush()
    return request


def approve_return(db: Session, return_id, approved, username="admin", reason=None, changed_by_id=None):
    request = db.get(ReturnRequest, int(return_id))
    if request is None or request.status != "pending":
        raise ValueError("Only a pending return can be approved or rejected.")
    old_status = request.status
    if not approved:
        request.status = "rejected"
        request.updated_at = datetime.now()
        _audit(db, "return_rejected", "ReturnRequest", request.id, username,
               old={"status": old_status}, new={"status": "rejected"},
               reason=reason or "Rejected by manager", user_id=changed_by_id)
        db.flush()
        return request

    for item in _items(db, request.id):
        item.quantity_approved = item.quantity_requested
    request.status = "approved"
    request.approved_by = username
    request.approved_at = datetime.now()
    request.updated_at = datetime.now()
    _audit(db, "return_approved", "ReturnRequest", request.id, username,
           old={"status": old_status}, new={"status": "approved"}, user_id=changed_by_id)
    db.flush()
    return request


def receive_return(db: Session, return_id, username="admin", notes=None, changed_by_id=None):
    request = db.get(ReturnRequest, int(return_id))
    if request is None or request.status != "approved":
        raise ValueError("Only an approved return can be marked physically received.")
    request.status = "received"
    request.received_at = datetime.now()
    request.updated_at = datetime.now()
    if notes:
        request.notes = (request.notes + "\n" if request.notes else "") + notes
    _audit(db, "return_physically_received", "ReturnRequest", request.id, username,
           old={"status": "approved"}, new={"status": "received"}, user_id=changed_by_id)
    db.flush()
    return request


def _batch_capacities(db, order_item_id):
    rows = (
        db.query(DispatchParcelItem, StockReservation)
        .join(StockReservation, StockReservation.id == DispatchParcelItem.reservation_id)
        .filter(DispatchParcelItem.order_item_id == order_item_id)
        .all()
    )
    capacities = {}
    for parcel_item, reservation in rows:
        batch_id = reservation.batch_id
        capacities[batch_id] = capacities.get(batch_id, Decimal("0")) + _qty(
            parcel_item.quantity_dispatched
        )

    inspections = (
        db.query(ReturnInspection, ReturnItem)
        .join(ReturnItem, ReturnItem.id == ReturnInspection.return_item_id)
        .filter(ReturnItem.order_item_id == order_item_id).all()
    )
    already_by_batch = {}
    for inspection, _item in inspections:
        already_by_batch[inspection.source_batch_id] = (
            already_by_batch.get(inspection.source_batch_id, Decimal("0"))
            + _qty(inspection.quantity_resellable)
            + _qty(inspection.quantity_damaged)
            + _qty(inspection.quantity_expired)
            + _qty(inspection.quantity_rejected)
        )
    return {
        batch_id: max(Decimal("0"), capacity - already_by_batch.get(batch_id, Decimal("0")))
        for batch_id, capacity in capacities.items()
        if capacity - already_by_batch.get(batch_id, Decimal("0")) > 0
    }


def inspect_return_item(db: Session, return_id, return_item_id, resellable, damaged,
                        expired, rejected=0, username="admin", notes=None, changed_by_id=None):
    request = db.get(ReturnRequest, int(return_id))
    item = db.get(ReturnItem, int(return_item_id))
    if request is None or request.status != "received":
        raise ValueError("The return must be physically received before inspection.")
    if item is None or item.return_id != request.id:
        raise ValueError("Return item was not found.")
    if item.inspected:
        raise ValueError("This item has already been inspected.")

    amounts = {
        "resellable": _qty(resellable), "damaged": _qty(damaged),
        "expired": _qty(expired), "rejected": _qty(rejected)
    }
    total = sum(amounts.values(), Decimal("0"))
    expected = _qty(item.quantity_approved)
    if total != expected:
        raise ValueError(f"Inspection quantities must total exactly {expected}; entered {total}.")

    capacities = _batch_capacities(db, item.order_item_id)
    if sum(capacities.values(), Decimal("0")) < expected:
        raise ValueError("Returned quantities could not be matched to the original dispatched batches.")

    remaining = dict(amounts)
    allocations = []
    for batch_id in sorted(capacities):
        capacity = capacities[batch_id]
        allocation = {"batch_id": batch_id}
        for key in ("resellable", "damaged", "expired", "rejected"):
            take = min(remaining[key], capacity)
            allocation[key] = take
            remaining[key] -= take
            capacity -= take
        if sum((allocation[k] for k in amounts), Decimal("0")) > 0:
            allocations.append(allocation)

    now = datetime.now()
    for allocation in allocations:
        batch = db.get(InventoryBatch, allocation["batch_id"])
        if batch is None:
            raise ValueError("An original inventory batch no longer exists.")
        resellable_qty = allocation["resellable"]
        if resellable_qty > 0 and batch.expiry_date and batch.expiry_date < date.today():
            raise ValueError(
                f"Original batch {batch.batch_number or batch.id} is expired. "
                "Classify those units as expired, not resellable."
            )
        db.add(ReturnInspection(
            return_item_id=item.id, source_batch_id=batch.id,
            quantity_resellable=resellable_qty,
            quantity_damaged=allocation["damaged"],
            quantity_expired=allocation["expired"],
            quantity_rejected=allocation["rejected"],
            inspected_by=username, inspected_at=now, notes=notes
        ))
        if resellable_qty > 0:
            batch.remaining_quantity = _qty(batch.remaining_quantity) + resellable_qty
            db.add(StockMovement(
                product_id=item.product_id, batch_id=batch.id,
                movement_type="customer_return_resellable",
                quantity_change=resellable_qty,
                reference_type="return_request", reference_id=request.id,
                note=f"Resellable return {request.return_number}; inspected by {username}."
            ))

    # Restore resellable returned goods to perpetual inventory and reverse
    # the corresponding portion of COGS in the same transaction.
    restock_value = Decimal("0.00")
    for allocation in allocations:
        qty = allocation["resellable"]
        if qty > 0:
            batch = db.get(InventoryBatch, allocation["batch_id"])
            restock_value += qty * _decimal(batch.unit_cost)
    restock_value = restock_value.quantize(Decimal("0.01"))
    if restock_value > 0:
        from accounting_service import create_draft_entry, post_journal_entry
        journal_key = f"RETURN-RESTOCK-{item.id}"
        existing_restock = db.query(JournalEntry).filter_by(
            idempotency_key=journal_key
        ).first()
        if existing_restock is None:
            journal_id = create_draft_entry(
                entry_date=date.today(),
                description=f"Resellable returned inventory: {request.return_number}",
                lines=[
                    {"account_code": "1150", "debit": restock_value, "credit": 0,
                     "description": "Restore resellable returned stock"},
                    {"account_code": "5100", "debit": 0, "credit": restock_value,
                     "description": "Reverse cost of resellable returned goods"},
                ],
                username=username, source_module="returns",
                reference_type="return_item", reference_id=item.id,
                idempotency_key=journal_key, db=db,
            )
            post_journal_entry(journal_id, username=username, db=db)
        elif existing_restock.status != "posted":
            raise ValueError("An unfinished inventory-restock journal exists for this return item.")

    item.quantity_received = expected
    item.quantity_resellable = amounts["resellable"]
    item.quantity_damaged = amounts["damaged"]
    item.quantity_expired = amounts["expired"]
    item.quantity_rejected = amounts["rejected"]
    item.inspected = 1
    item.notes = notes
    all_items = _items(db, request.id)
    if all(x.inspected for x in all_items):
        request.status = "inspected"
        request.inspected_at = now
    request.updated_at = now
    _audit(db, "return_item_inspected", "ReturnItem", item.id, username,
           new={key: str(value) for key, value in amounts.items()}, reason=notes,
           user_id=changed_by_id)
    db.flush()
    return request


def refund_return(db: Session, return_id, amount, payment_method, username="admin",
                  payment_reference=None, notes=None, changed_by_id=None):
    from accounting_service import create_draft_entry, post_journal_entry

    request = db.get(ReturnRequest, int(return_id))
    if request is None or request.status not in ("inspected", "closed"):
        raise ValueError("The return must be fully inspected before a refund can be paid.")
    amount = _money(amount).quantize(Decimal("0.01"))
    if amount <= 0:
        raise ValueError("Refund amount must be greater than zero.")
    method = str(payment_method or "").strip().lower()
    account_code = {"cash": "1110", "bank": "1120"}.get(method)
    if account_code is None:
        raise ValueError("Refund method must be Cash or Bank.")

    # Resolve a repeated payment reference before calculating remaining refund
    # capacity, otherwise a legitimate retry would appear to exceed the cap.
    if not payment_reference or not str(payment_reference).strip():
        raise ValueError("A payment / cash voucher reference is required to prevent duplicate refunds.")
    from hashlib import sha256
    reference = str(payment_reference).strip()
    if len(reference) > 120:
        raise ValueError("Refund reference cannot exceed 120 characters.")
    reference_hash = sha256(reference.casefold().encode("utf-8")).hexdigest()[:24]
    idempotency_key = f"return-refund-ref-{reference_hash}"
    existing_refund = db.query(ReturnRefund).filter_by(
        idempotency_key=idempotency_key
    ).first()
    if existing_refund:
        if (existing_refund.status == "paid"
                and _money(existing_refund.amount) == amount
                and existing_refund.payment_method == method):
            return existing_refund
        raise ValueError("This refund reference was already used with different payment details.")

    eligible = Decimal("0.00")
    for item in _items(db, request.id):
        accepted_qty = (
            _qty(item.quantity_resellable) + _qty(item.quantity_damaged)
            + _qty(item.quantity_expired)
        )
        order_item = db.get(SalesOrderItem, item.order_item_id)
        ordered_qty = _qty(order_item.quantity_ordered)
        if ordered_qty > 0:
            eligible += _money(order_item.line_total) * accepted_qty / ordered_qty
    eligible = eligible.quantize(Decimal("0.01"))

    prior_refunds = db.query(ReturnRefund).filter(
        ReturnRefund.return_id == request.id, ReturnRefund.status == "paid"
    ).all()
    already_refunded = sum((_money(x.amount) for x in prior_refunds), Decimal("0.00"))
    order = db.get(SalesOrder, request.order_id)
    order_paid = _money(order.amount_paid)
    all_order_refunds = sum((
        _money(x.amount) for x in db.query(ReturnRefund).join(
            ReturnRequest, ReturnRequest.id == ReturnRefund.return_id
        ).filter(ReturnRequest.order_id == order.id, ReturnRefund.status == "paid").all()
    ), Decimal("0.00"))
    cap = min(max(Decimal("0"), eligible - already_refunded),
              max(Decimal("0"), order_paid - all_order_refunds))
    if amount > cap:
        raise ValueError(f"Refund exceeds the permitted amount. Maximum now: PKR {cap:.2f}.")

    journal_id = create_draft_entry(
        entry_date=date.today(),
        description=f"Customer refund for {request.return_number}",
        lines=[
            {"account_code": "4300", "debit": amount, "credit": 0,
             "description": f"Sales return {request.return_number}"},
            {"account_code": account_code, "debit": 0, "credit": amount,
             "description": f"{method.title()} refund payment"},
        ],
        username=username, source_module="returns",
        reference_type="return_request", reference_id=request.id,
        idempotency_key=idempotency_key, db=db
    )
    post_journal_entry(journal_id, username=username, db=db)
    refund = ReturnRefund(
        return_id=request.id, amount=amount, payment_method=method,
        account_code=account_code, payment_reference=payment_reference,
        status="paid", journal_entry_id=journal_id,
        idempotency_key=idempotency_key, paid_by=username,
        paid_at=datetime.now(), notes=notes
    )
    db.add(refund)
    request.updated_at = datetime.now()
    _audit(db, "customer_refund_paid", "ReturnRequest", request.id, username,
           new={"amount": str(amount), "method": method, "journal_entry_id": journal_id},
           user_id=changed_by_id)
    db.flush()
    return refund


from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QInputDialog, QHeaderView, QDialog,
    QDialogButtonBox, QFormLayout, QComboBox, QDoubleSpinBox, QLineEdit
)


class ReturnsManager(QWidget):
    def __init__(self, session_factory, user=None):
        super().__init__()
        self.session_factory = session_factory
        self.user = user or {}
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Return No.", "Order", "Customer", "Items", "Status", "Reason", "Date"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout = QVBoxLayout(self)
        heading = QLabel("Returns & Refunds")
        heading.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(heading)
        actions = QHBoxLayout()
        for label, callback in [
            ("New Return", self.new_return), ("Approve", self.approve),
            ("Reject", self.reject), ("Mark Received", self.receive),
            ("Inspect", self.inspect), ("Pay Refund", self.refund),
            ("Refresh", self.refresh)
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        layout.addWidget(self.table)
        self.refresh()

    def _authenticated_username(self):
        username = str(self.user.get("username") or "").strip()
        if not username:
            raise ValueError("The authenticated username could not be identified. Please log in again.")
        return username

    def _selected_id(self):
        row = self.table.currentRow()
        if row < 0:
            raise ValueError("Select a return first.")
        return int(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))

    def _show_error(self, title, exc):
        QMessageBox.warning(self, title, str(exc))

    def _run(self, action, message):
        db = self.session_factory()
        try:
            action(db)
            db.commit()
            self.refresh()
            QMessageBox.information(self, "Returns", message)
        except Exception as exc:
            db.rollback()
            self._show_error("Returns", exc)
        finally:
            db.close()

    def refresh(self):
        db = self.session_factory()
        try:
            requests = db.query(ReturnRequest).order_by(
                ReturnRequest.created_at.desc()
            ).limit(500).all()
            self.table.setRowCount(0)
            for request in requests:
                order = db.get(SalesOrder, request.order_id)
                customer = db.get(Customer, request.customer_id) if request.customer_id else None
                item_text = ", ".join(
                    f"{x.product_name_snapshot} × {x.quantity_requested}"
                    for x in _items(db, request.id)
                )
                values = [
                    request.return_number, order.order_number if order else "",
                    customer.name if customer else (order.customer_name if order else ""),
                    item_text, request.status.title(), request.reason,
                    request.requested_at.strftime("%Y-%m-%d") if request.requested_at else ""
                ]
                row = self.table.rowCount()
                self.table.insertRow(row)
                for col, value in enumerate(values):
                    cell = QTableWidgetItem(str(value))
                    if col == 0:
                        cell.setData(Qt.ItemDataRole.UserRole, request.id)
                    self.table.setItem(row, col, cell)
        finally:
            db.close()

    def new_return(self):
        db = self.session_factory()
        try:
            orders = db.query(SalesOrder).filter(
                SalesOrder.order_status.notin_(("draft", "cancelled"))
            ).order_by(SalesOrder.created_at.desc()).limit(300).all()
            if not orders:
                raise ValueError("No eligible orders were found.")
            labels = [f"{o.order_number} — {o.customer_name}" for o in orders]
            selected, ok = QInputDialog.getItem(self, "New Return", "Select order:", labels, 0, False)
            if not ok:
                return
            order = orders[labels.index(selected)]
            order_items = db.query(SalesOrderItem).filter(
                SalesOrderItem.order_id == order.id,
                SalesOrderItem.quantity_dispatched > 0
            ).all()
            if not order_items:
                raise ValueError("This order has no dispatched items.")
            item_labels = [f"{x.product_name_snapshot} | dispatched {x.quantity_dispatched}" for x in order_items]
            selected_item, ok = QInputDialog.getItem(self, "New Return", "Select item:", item_labels, 0, False)
            if not ok:
                return
            item = order_items[item_labels.index(selected_item)]
            maximum = max(Decimal("0"), _qty(item.quantity_dispatched) - _already_requested(db, item.id))
            quantity, ok = QInputDialog.getText(self, "Return Quantity", f"Quantity (max {maximum}):")
            if not ok:
                return
            reason, ok = QInputDialog.getText(self, "Return Reason", "Reason:")
            if not ok:
                return
            request = create_return_request(
                db, order.id, [{"order_item_id": item.id, "quantity": quantity}], reason,
                username=self._authenticated_username(), changed_by_id=self.user.get("id")
            )
            db.commit()
            self.refresh()
            QMessageBox.information(self, "Return Created", f"{request.return_number} is pending approval.")
        except Exception as exc:
            db.rollback()
            self._show_error("New Return", exc)
        finally:
            db.close()

    def _approval(self, yes):
        try:
            rid = self._selected_id()
        except Exception as exc:
            self._show_error("Returns", exc)
            return
        self._run(lambda db: approve_return(
                      db, rid, yes, username=self._authenticated_username(),
                      changed_by_id=self.user.get("id")),
                  "Return approved." if yes else "Return rejected.")

    def approve(self):
        self._approval(True)

    def reject(self):
        self._approval(False)

    def receive(self):
        try:
            rid = self._selected_id()
        except Exception as exc:
            self._show_error("Returns", exc)
            return
        self._run(lambda db: receive_return(
                      db, rid, username=self._authenticated_username(),
                      changed_by_id=self.user.get("id")),
                  "Physical receipt recorded. Inspect the items next.")

    def inspect(self):
        try:
            rid = self._selected_id()
            db = self.session_factory()
            request = db.get(ReturnRequest, rid)
            if request is None or request.status != "received":
                raise ValueError("Mark the return as received before inspection.")
            pending = [x for x in _items(db, rid) if not x.inspected]
            if not pending:
                raise ValueError("There are no uninspected items.")
            item = pending[0]
            total = _qty(item.quantity_approved)
        except Exception as exc:
            try:
                db.close()
            except Exception:
                pass
            self._show_error("Inspect Return", exc)
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Inspect: {item.product_name_snapshot}")
        form = QFormLayout(dialog)
        fields = {}
        for key, label in [
            ("resellable", "Resellable"), ("damaged", "Damaged"),
            ("expired", "Expired"), ("rejected", "Rejected")
        ]:
            spin = QDoubleSpinBox()
            spin.setRange(0, float(total))
            spin.setDecimals(3)
            spin.setMaximumWidth(180)
            fields[key] = spin
            form.addRow(label, spin)
        note = QLineEdit()
        form.addRow("Inspection notes", note)
        form.addRow(QLabel(f"Total quantities must equal: {total}"))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            db.close()
            return
        try:
            inspect_return_item(
                db, rid, item.id,
                fields["resellable"].value(), fields["damaged"].value(),
                fields["expired"].value(), fields["rejected"].value(),
                notes=note.text(), username=self._authenticated_username(),
                changed_by_id=self.user.get("id")
            )
            db.commit()
            self.refresh()
            QMessageBox.information(self, "Inspection", "Inspection saved. Resellable units were returned to their original batches.")
        except Exception as exc:
            db.rollback()
            self._show_error("Inspect Return", exc)
        finally:
            db.close()

    def refund(self):
        try:
            rid = self._selected_id()
        except Exception as exc:
            self._show_error("Returns", exc)
            return
        amount, ok = QInputDialog.getText(self, "Pay Refund", "Refund amount (PKR):")
        if not ok:
            return
        method, ok = QInputDialog.getItem(self, "Refund Method", "Payment method:", ["Cash", "Bank"], 0, False)
        if not ok:
            return
        reference, ok = QInputDialog.getText(self, "Payment Reference", "Payment / cash voucher reference (required):")
        if not ok:
            return
        if not reference.strip():
            QMessageBox.warning(self, "Reference Required", "Enter a unique payment or cash voucher reference.")
            return
        self._run(
            lambda db: refund_return(
                db, rid, amount, method, username=self._authenticated_username(),
                payment_reference=reference, changed_by_id=self.user.get("id")),
            "Refund recorded and its accounting journal posted."
        )
