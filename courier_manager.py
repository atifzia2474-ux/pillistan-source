from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTabWidget, QLineEdit, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QComboBox, QDoubleSpinBox, QInputDialog
)

from database import SessionLocal
from orders_models import (
    Courier, SalesOrder, DispatchParcel, StockReservation
)
from models import Product, InventoryBatch
from dispatch_service import hand_over_parcel


class CourierManager(QWidget):
    def __init__(self, session_factory=None, user=None):
        super().__init__()
        self.session_factory = session_factory or SessionLocal
        self.user = user or {}
        self.setStyleSheet("""
            QWidget {
                background: #f4f7f5;
                color: #24352c;
                font-family: Segoe UI;
                font-size: 13px;
            }
            QLineEdit, QComboBox, QDoubleSpinBox {
                background: white;
                border: 1px solid #d5ded8;
                border-radius: 5px;
                padding: 7px;
                min-height: 20px;
            }
            QPushButton {
                background: #164b37;
                color: white;
                padding: 9px 14px;
                border: none;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover { background: #28664d; }
            QTableWidget {
                background: white;
                alternate-background-color: #f4f7f5;
                gridline-color: #e5ebe7;
                border: 1px solid #d5ded8;
            }
            QHeaderView::section {
                background: #164b37;
                color: white;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
        """)
        self.build_interface()
        self.refresh_all()

    def build_interface(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        heading = QLabel("Courier Management")
        heading.setStyleSheet(
            "font-size:27px;font-weight:bold;color:#164b37;"
        )
        root.addWidget(heading)

        subtitle = QLabel(
            "Manage courier companies, prepare parcels and record physical handovers."
        )
        root.addWidget(subtitle)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        self.build_courier_tab()
        self.build_dispatch_tab()
        self.build_delivery_accounting_tab()

    def build_courier_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        form_box = QWidget()
        form = QFormLayout(form_box)

        self.courier_name = QLineEdit()
        self.courier_contact = QLineEdit()
        self.courier_phone = QLineEdit()
        self.courier_email = QLineEdit()
        self.courier_account = QLineEdit()
        self.courier_tracking_template = QLineEdit()
        self.courier_tracking_template.setPlaceholderText(
            "Optional tracking URL template"
        )

        form.addRow("Courier company *", self.courier_name)
        form.addRow("Contact person", self.courier_contact)
        form.addRow("Phone", self.courier_phone)
        form.addRow("Email", self.courier_email)
        form.addRow("Account reference", self.courier_account)
        form.addRow("Tracking URL template", self.courier_tracking_template)

        layout.addWidget(form_box)

        actions = QHBoxLayout()
        add_button = QPushButton("Add Courier")
        add_button.clicked.connect(self.add_courier)
        toggle_button = QPushButton("Activate / Deactivate Selected")
        toggle_button.clicked.connect(self.toggle_courier)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_couriers)

        actions.addWidget(add_button)
        actions.addWidget(toggle_button)
        actions.addWidget(refresh_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.courier_table = QTableWidget(0, 6)
        self.courier_table.setHorizontalHeaderLabels([
            "Company", "Contact", "Phone", "Email", "Account Ref.", "Status"
        ])
        self.courier_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.courier_table.setAlternatingRowColors(True)
        self.courier_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        layout.addWidget(self.courier_table)

        self.tabs.addTab(page, "Courier Companies")

    def build_dispatch_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        parcel_form = QFormLayout()

        self.order_selector = QComboBox()
        self.courier_selector = QComboBox()
        self.tracking_number = QLineEdit()
        self.tracking_number.setPlaceholderText(
            "Courier consignment / tracking number"
        )
        self.tracking_url = QLineEdit()
        self.tracking_url.setPlaceholderText("Optional tracking URL")

        parcel_form.addRow("Confirmed order", self.order_selector)
        parcel_form.addRow("Courier company", self.courier_selector)
        parcel_form.addRow("Tracking number", self.tracking_number)
        parcel_form.addRow("Tracking URL", self.tracking_url)
        layout.addLayout(parcel_form)

        create_button = QPushButton("Create Prepared Parcel")
        create_button.clicked.connect(self.create_parcel)
        layout.addWidget(create_button)

        layout.addWidget(QLabel("Parcels"))
        self.parcel_table = QTableWidget(0, 6)
        self.parcel_table.setHorizontalHeaderLabels([
            "Dispatch Ref.", "Order", "Parcel", "Courier",
            "Tracking Number", "Status"
        ])
        self.parcel_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.parcel_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.parcel_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        layout.addWidget(self.parcel_table)

        parcel_actions = QHBoxLayout()
        load_button = QPushButton("Load Selected Parcel Items")
        load_button.clicked.connect(self.load_selected_parcel_items)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_dispatch_data)
        parcel_actions.addWidget(load_button)
        parcel_actions.addWidget(refresh_button)
        parcel_actions.addStretch()
        layout.addLayout(parcel_actions)

        layout.addWidget(QLabel(
            "Enter the quantities physically placed in this parcel."
        ))
        self.reservation_table = QTableWidget(0, 6)
        self.reservation_table.setHorizontalHeaderLabels([
            "Product", "Batch", "Reserved", "Dispatched",
            "Remaining", "Quantity in Parcel"
        ])
        self.reservation_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.reservation_table)

        handover_button = QPushButton("Hand Over Parcel to Courier")
        handover_button.clicked.connect(self.handover_selected_parcel)
        layout.addWidget(handover_button)

        self.tabs.addTab(page, "Parcel Dispatch")

    def build_delivery_accounting_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        delivery_form = QFormLayout()
        self.delivery_parcel_selector = QComboBox()
        delivery_form.addRow("Parcel handed to courier", self.delivery_parcel_selector)
        layout.addLayout(delivery_form)

        confirm_delivery_button = QPushButton("Confirm Successful Delivery")
        confirm_delivery_button.clicked.connect(self.confirm_selected_delivery)
        layout.addWidget(confirm_delivery_button)
        returned_button = QPushButton("Record Parcel Physically Returned to Warehouse")
        returned_button.clicked.connect(self.record_selected_parcel_return)
        layout.addWidget(returned_button)

        layout.addWidget(QLabel("COD settlement received from courier"))
        settlement_form = QFormLayout()
        self.settlement_parcel_selector = QComboBox()
        self.cod_remitted_input = QLineEdit()
        self.cod_remitted_input.setPlaceholderText("Actual amount received in bank (PKR)")
        self.courier_fee_input = QLineEdit("0")
        self.courier_fee_input.setPlaceholderText("Courier fee deducted (PKR)")
        self.cod_reference_input = QLineEdit()
        self.cod_reference_input.setPlaceholderText("Courier settlement / bank reference")
        settlement_form.addRow("Delivered COD parcel", self.settlement_parcel_selector)
        settlement_form.addRow("Amount remitted (PKR)", self.cod_remitted_input)
        settlement_form.addRow("Courier fee (PKR)", self.courier_fee_input)
        settlement_form.addRow("Settlement reference", self.cod_reference_input)
        layout.addLayout(settlement_form)

        settle_button = QPushButton("Record COD Remittance")
        settle_button.clicked.connect(self.record_selected_cod_remittance)
        layout.addWidget(settle_button)
        refresh_button = QPushButton("Refresh Delivery & COD Records")
        refresh_button.clicked.connect(self.refresh_delivery_data)
        layout.addWidget(refresh_button)
        layout.addStretch()

        self.tabs.addTab(page, "Delivery & COD Accounting")

    def refresh_all(self):
        self.refresh_couriers()
        self.refresh_dispatch_data()
        self.refresh_delivery_data()

    def _authenticated_username(self):
        username = str(self.user.get("username") or "").strip()
        if not username:
            raise ValueError("The authenticated username could not be identified. Please log in again.")
        return username

    def refresh_delivery_data(self):
        session = self.session_factory()
        try:
            current_delivery = self.delivery_parcel_selector.currentData()
            current_settlement = self.settlement_parcel_selector.currentData()
            self.delivery_parcel_selector.clear()
            self.settlement_parcel_selector.clear()
            self.delivery_parcel_selector.addItem("Select handed-over COD parcel", None)
            self.settlement_parcel_selector.addItem("Select delivered COD parcel", None)

            parcels = (session.query(DispatchParcel)
                       .filter(DispatchParcel.parcel_status.in_(("handed_over", "delivered")))
                       .order_by(DispatchParcel.created_at.desc()).limit(500).all())
            for parcel in parcels:
                order = session.get(SalesOrder, parcel.order_id)
                if order is None or str(order.payment_method).lower() != "cod":
                    continue
                label = f"{parcel.dispatch_reference} | {order.order_number} | {order.customer_name}"
                if parcel.parcel_status == "handed_over":
                    self.delivery_parcel_selector.addItem(label, parcel.id)
                elif parcel.parcel_status == "delivered":
                    self.settlement_parcel_selector.addItem(label, parcel.id)

            if current_delivery is not None:
                idx = self.delivery_parcel_selector.findData(current_delivery)
                if idx >= 0:
                    self.delivery_parcel_selector.setCurrentIndex(idx)
            if current_settlement is not None:
                idx = self.settlement_parcel_selector.findData(current_settlement)
                if idx >= 0:
                    self.settlement_parcel_selector.setCurrentIndex(idx)
        except Exception as error:
            QMessageBox.warning(self, "Delivery Records", str(error))
        finally:
            session.close()

    def confirm_selected_delivery(self):
        parcel_id = self.delivery_parcel_selector.currentData()
        if parcel_id is None:
            QMessageBox.warning(self, "Select Parcel", "Select a handed-over parcel first.")
            return
        answer = QMessageBox.question(
            self, "Confirm Delivery",
            "Confirm that the customer has successfully received this parcel?\n\n"
            "This will recognize the sale, COD receivable and delivered stock cost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        session = self.session_factory()
        try:
            from delivery_accounting_service import confirm_parcel_delivery
            journal_id = confirm_parcel_delivery(
                session, parcel_id, username=self._authenticated_username(),
                changed_by_id=self.user.get("id"),
            )
            session.commit()
            self.refresh_delivery_data()
            self.refresh_dispatch_data()
            QMessageBox.information(self, "Delivery Confirmed",
                                    f"Delivery and accounting journal #{journal_id} were recorded.")
        except Exception as error:
            session.rollback()
            QMessageBox.critical(self, "Delivery Confirmation Failed", str(error))
        finally:
            session.close()

    def record_selected_parcel_return(self):
        parcel_id = self.delivery_parcel_selector.currentData()
        if parcel_id is None:
            QMessageBox.warning(self, "Select Parcel", "Select a handed-over parcel first.")
            return
        reason, ok = QInputDialog.getText(
            self, "Parcel Returned to Warehouse", "Reason for failed delivery / return:"
        )
        if not ok:
            return
        answer = QMessageBox.question(
            self, "Confirm Physical Return",
            "Confirm this parcel has physically arrived back at the warehouse?\n\n"
            "Stock quantities will be restored to their original batches.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        session = self.session_factory()
        try:
            from delivery_accounting_service import record_parcel_return_to_warehouse
            journal_id = record_parcel_return_to_warehouse(
                session, parcel_id, reason=reason,
                username=self._authenticated_username(),
                changed_by_id=self.user.get("id"),
            )
            session.commit()
            self.refresh_delivery_data()
            self.refresh_dispatch_data()
            QMessageBox.information(
                self, "Parcel Return Recorded",
                f"Parcel returned to warehouse. Accounting journal: {journal_id or 'No value (zero-cost stock)'}"
            )
        except Exception as error:
            session.rollback()
            QMessageBox.critical(self, "Parcel Return Failed", str(error))
        finally:
            session.close()

    def record_selected_cod_remittance(self):
        parcel_id = self.settlement_parcel_selector.currentData()
        if parcel_id is None:
            QMessageBox.warning(self, "Select Parcel", "Select a delivered COD parcel first.")
            return
        session = self.session_factory()
        try:
            from delivery_accounting_service import record_cod_remittance
            journal_id = record_cod_remittance(
                session, parcel_id,
                remitted_amount=self.cod_remitted_input.text().strip(),
                courier_fee=self.courier_fee_input.text().strip() or "0",
                transaction_reference=self.cod_reference_input.text().strip(),
                username=self._authenticated_username(),
                changed_by_id=self.user.get("id"),
            )
            session.commit()
            self.cod_remitted_input.clear()
            self.courier_fee_input.setText("0")
            self.cod_reference_input.clear()
            self.refresh_delivery_data()
            QMessageBox.information(self, "COD Remittance Recorded",
                                    f"Courier remittance and accounting journal #{journal_id} were recorded.")
        except Exception as error:
            session.rollback()
            QMessageBox.critical(self, "COD Settlement Failed", str(error))
        finally:
            session.close()

    def refresh_couriers(self):
        session = self.session_factory()
        try:
            couriers = session.query(Courier).order_by(Courier.name).all()

            self.courier_table.setRowCount(0)
            self.courier_selector.clear()
            self.courier_selector.addItem("Select courier", None)

            for courier in couriers:
                row = self.courier_table.rowCount()
                self.courier_table.insertRow(row)

                values = [
                    courier.name,
                    courier.contact_person or "",
                    courier.phone or "",
                    courier.email or "",
                    courier.account_reference or "",
                    "Active" if courier.is_active else "Inactive",
                ]

                for col, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if col == 0:
                        item.setData(Qt.ItemDataRole.UserRole, courier.id)
                    self.courier_table.setItem(row, col, item)

                if courier.is_active:
                    self.courier_selector.addItem(
                        courier.name, courier.id
                    )
        except Exception as error:
            QMessageBox.warning(
                self, "Courier Loading Error", str(error)
            )
        finally:
            session.close()

    def add_courier(self):
        name = self.courier_name.text().strip()
        if not name:
            QMessageBox.warning(
                self, "Courier Required",
                "Enter the courier company name."
            )
            return

        session = self.session_factory()
        try:
            existing = session.query(Courier).filter(
                Courier.name.ilike(name)
            ).first()
            if existing:
                QMessageBox.warning(
                    self, "Already Exists",
                    "A courier with this company name already exists."
                )
                return

            now = datetime.now()
            courier = Courier(
                name=name,
                contact_person=self.courier_contact.text().strip() or None,
                phone=self.courier_phone.text().strip() or None,
                email=self.courier_email.text().strip() or None,
                account_reference=self.courier_account.text().strip() or None,
                tracking_url_template=(
                    self.courier_tracking_template.text().strip() or None
                ),
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(courier)
            session.commit()

            for field in (
                self.courier_name,
                self.courier_contact,
                self.courier_phone,
                self.courier_email,
                self.courier_account,
                self.courier_tracking_template,
            ):
                field.clear()

            self.refresh_all()
            QMessageBox.information(
                self, "Courier Added",
                f"{name} has been added successfully."
            )
        except Exception as error:
            session.rollback()
            QMessageBox.critical(
                self, "Could Not Add Courier", str(error)
            )
        finally:
            session.close()

    def toggle_courier(self):
        row = self.courier_table.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, "Select Courier",
                "Select a courier company first."
            )
            return

        item = self.courier_table.item(row, 0)
        courier_id = item.data(Qt.ItemDataRole.UserRole)

        session = self.session_factory()
        try:
            courier = session.get(Courier, courier_id)
            if courier is None:
                raise ValueError("Courier record was not found.")

            courier.is_active = not courier.is_active
            courier.updated_at = datetime.now()
            session.commit()
            self.refresh_all()
        except Exception as error:
            session.rollback()
            QMessageBox.warning(
                self, "Courier Update Failed", str(error)
            )
        finally:
            session.close()

    def refresh_dispatch_data(self):
        session = self.session_factory()
        try:
            current_order_id = self.order_selector.currentData()
            self.order_selector.clear()
            self.order_selector.addItem("Select order", None)

            orders = (
                session.query(SalesOrder)
                .filter(
                    SalesOrder.order_status.in_(
                        ("confirmed", "partially_dispatched")
                    ),
                    SalesOrder.fulfilment_status.in_(
                        ("reserved", "partially_dispatched")
                    ),
                )
                .order_by(SalesOrder.created_at.desc())
                .all()
            )

            for order in orders:
                label = (
                    f"{order.order_number} | {order.customer_name} | "
                    f"{order.fulfilment_status.replace('_', ' ').title()}"
                )
                self.order_selector.addItem(label, order.id)

            if current_order_id is not None:
                index = self.order_selector.findData(current_order_id)
                if index >= 0:
                    self.order_selector.setCurrentIndex(index)

            parcels = (
                session.query(DispatchParcel)
                .order_by(DispatchParcel.created_at.desc())
                .limit(200)
                .all()
            )

            self.parcel_table.setRowCount(0)
            for parcel in parcels:
                order = session.get(SalesOrder, parcel.order_id)
                courier = (
                    session.get(Courier, parcel.courier_id)
                    if parcel.courier_id else None
                )

                row = self.parcel_table.rowCount()
                self.parcel_table.insertRow(row)
                values = [
                    parcel.dispatch_reference,
                    order.order_number if order else "",
                    f"{parcel.parcel_number}/{parcel.parcel_count}",
                    courier.name if courier else "",
                    parcel.courier_tracking_number or "",
                    parcel.parcel_status.replace("_", " ").title(),
                ]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if col == 0:
                        item.setData(Qt.ItemDataRole.UserRole, parcel.id)
                    self.parcel_table.setItem(row, col, item)
        except Exception as error:
            QMessageBox.warning(
                self, "Dispatch Loading Error", str(error)
            )
        finally:
            session.close()

    def create_parcel(self):
        order_id = self.order_selector.currentData()
        courier_id = self.courier_selector.currentData()

        if order_id is None:
            QMessageBox.warning(
                self, "Select Order", "Select an order first."
            )
            return
        if courier_id is None:
            QMessageBox.warning(
                self, "Select Courier", "Select a courier company first."
            )
            return

        session = self.session_factory()
        try:
            order = session.get(SalesOrder, order_id)
            if order is None:
                raise ValueError("Order was not found.")

            if order.order_status not in (
                "confirmed", "partially_dispatched"
            ):
                raise ValueError(
                    "Only confirmed orders can have dispatch parcels."
                )

            existing = (
                session.query(DispatchParcel)
                .filter(DispatchParcel.order_id == order.id)
                .all()
            )
            parcel_number = max(
                [p.parcel_number for p in existing], default=0
            ) + 1

            next_id = (
                session.query(DispatchParcel.id)
                .order_by(DispatchParcel.id.desc())
                .first()
            )
            sequence = (next_id[0] if next_id else 0) + 1
            now = datetime.now()
            reference = f"PIL-DSP-{now:%Y%m%d}-{sequence:06d}"

            courier = session.get(Courier, courier_id)
            tracking_url = self.tracking_url.text().strip() or None

            if not tracking_url and courier and courier.tracking_url_template:
                template = courier.tracking_url_template
                tracking_number = self.tracking_number.text().strip()
                tracking_url = template.replace(
                    "{tracking_number}", tracking_number
                )

            parcel = DispatchParcel(
                order_id=order.id,
                dispatch_reference=reference,
                parcel_number=parcel_number,
                parcel_count=parcel_number,
                courier_id=courier_id,
                courier_tracking_number=(
                    self.tracking_number.text().strip() or None
                ),
                tracking_url=tracking_url,
                parcel_status="prepared",
                created_at=now,
                updated_at=now,
            )
            session.add(parcel)
            session.commit()

            self.tracking_number.clear()
            self.tracking_url.clear()
            self.refresh_dispatch_data()

            QMessageBox.information(
                self, "Parcel Prepared",
                f"Parcel {reference} has been created.\n\n"
                "Load its reserved items, enter the quantities physically "
                "packed, and then record courier handover."
            )
        except Exception as error:
            session.rollback()
            QMessageBox.critical(
                self, "Parcel Could Not Be Created", str(error)
            )
        finally:
            session.close()

    def load_selected_parcel_items(self):
        row = self.parcel_table.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, "Select Parcel", "Select a parcel first."
            )
            return

        parcel_id = self.parcel_table.item(
            row, 0
        ).data(Qt.ItemDataRole.UserRole)

        session = self.session_factory()
        try:
            parcel = session.get(DispatchParcel, parcel_id)
            if parcel is None:
                raise ValueError("Parcel was not found.")

            if parcel.parcel_status != "prepared":
                raise ValueError(
                    "Only prepared parcels can be edited for handover."
                )

            reservations = (
                session.query(StockReservation)
                .filter(
                    StockReservation.order_id == parcel.order_id,
                    StockReservation.reservation_status.in_(
                        ("reserved", "partially_dispatched")
                    ),
                )
                .order_by(StockReservation.id)
                .all()
            )

            self.reservation_table.setRowCount(0)
            for reservation in reservations:
                remaining = (
                    Decimal(str(reservation.quantity_reserved or 0))
                    - Decimal(str(reservation.quantity_dispatched or 0))
                )
                if remaining <= 0:
                    continue

                product = session.get(Product, reservation.product_id)
                batch = session.get(InventoryBatch, reservation.batch_id)

                row = self.reservation_table.rowCount()
                self.reservation_table.insertRow(row)

                values = [
                    product.name if product else "",
                    batch.batch_number if batch else "",
                    str(reservation.quantity_reserved),
                    str(reservation.quantity_dispatched),
                    str(remaining),
                ]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if col == 0:
                        item.setData(
                            Qt.ItemDataRole.UserRole, reservation.id
                        )
                    self.reservation_table.setItem(row, col, item)

                quantity = QDoubleSpinBox()
                quantity.setDecimals(3)
                quantity.setRange(0, float(remaining))
                quantity.setSingleStep(1)
                quantity.setValue(0)
                self.reservation_table.setCellWidget(row, 5, quantity)

            if self.reservation_table.rowCount() == 0:
                QMessageBox.information(
                    self, "No Outstanding Stock",
                    "This order has no remaining reserved quantities."
                )
        except Exception as error:
            QMessageBox.warning(
                self, "Could Not Load Parcel Items", str(error)
            )
        finally:
            session.close()

    def handover_selected_parcel(self):
        row = self.parcel_table.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, "Select Parcel", "Select a parcel first."
            )
            return

        parcel_id = self.parcel_table.item(
            row, 0
        ).data(Qt.ItemDataRole.UserRole)

        dispatch_lines = []
        for row in range(self.reservation_table.rowCount()):
            reservation_item = self.reservation_table.item(row, 0)
            quantity_widget = self.reservation_table.cellWidget(row, 5)

            if reservation_item is None or quantity_widget is None:
                continue

            quantity = Decimal(str(quantity_widget.value()))
            if quantity > 0:
                dispatch_lines.append({
                    "reservation_id": reservation_item.data(
                        Qt.ItemDataRole.UserRole
                    ),
                    "quantity": str(quantity),
                })

        if not dispatch_lines:
            QMessageBox.warning(
                self, "No Dispatch Quantities",
                "Enter at least one quantity greater than zero."
            )
            return

        answer = QMessageBox.question(
            self,
            "Confirm Courier Handover",
            "Confirm that these quantities have physically been handed "
            "to the courier?\n\nStock will be deducted immediately.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        session = self.session_factory()
        try:
            hand_over_parcel(
                session,
                parcel_id,
                dispatch_lines,
                changed_by_id=self.user.get("id"),
                username=self._authenticated_username(),
            )
            session.commit()

            self.reservation_table.setRowCount(0)
            self.refresh_dispatch_data()
            self.refresh_delivery_data()

            QMessageBox.information(
                self, "Courier Handover Recorded",
                "The parcel has been handed over successfully.\n\n"
                "Dispatched quantities have been deducted from physical "
                "inventory and recorded in the stock movement history."
            )
        except Exception as error:
            session.rollback()
            QMessageBox.critical(
                self, "Handover Failed",
                f"No handover was committed.\n\n{error}"
            )
        finally:
            session.close()
