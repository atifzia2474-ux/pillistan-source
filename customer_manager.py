from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QDialog, QDialogButtonBox,
    QLabel, QPushButton, QLineEdit, QTextEdit, QComboBox, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QTabWidget, QMessageBox, QInputDialog, QGroupBox,
    QFrame, QGridLayout
)
from sqlalchemy import or_, func

from database import SessionLocal
from models import Customer
from orders_models import CustomerAddress, CustomerLabel, SalesOrder, OrderPayment
from orders_service import normalize_phone
from theme_manager import THEMES, current_theme


def _money(value):
    try:
        return f"PKR {Decimal(str(value or 0)):,.2f}"
    except Exception:
        return "PKR 0.00"


def _table(parent, headers):
    table = QTableWidget(0, len(headers), parent)
    table.setHorizontalHeaderLabels(headers)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(38)
    table.horizontalHeader().setMinimumHeight(42)
    table.setShowGrid(False)
    return table


class CustomerManager(QWidget):
    """Customer directory and customer records for the Pillistan desktop app."""

    def __init__(self, session_factory=None):
        super().__init__()
        self.session_factory = session_factory or SessionLocal
        self._build_ui()
        self.load_customers()

    def _build_ui(self):
        # PILLISTAN_CUSTOMER_VISUAL_REDESIGN_V1
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # Page heading and primary action.
        header_layout = QHBoxLayout()
        heading_column = QVBoxLayout()
        heading_column.setSpacing(4)

        heading = QLabel("Customers")
        heading.setObjectName("customerPageTitle")
        heading_column.addWidget(heading)

        description = QLabel(
            "Manage customer profiles, delivery addresses, orders and payments."
        )
        description.setObjectName("customerPageDescription")
        description.setWordWrap(True)
        heading_column.addWidget(description)

        header_layout.addLayout(heading_column, 1)

        add_button = QPushButton("+ Add Customer")
        add_button.setObjectName("customerPrimaryButton")
        add_button.setMinimumHeight(42)
        add_button.clicked.connect(self.add_customer)
        header_layout.addWidget(add_button, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(header_layout)

        # Four live summary cards.
        metrics_layout = QGridLayout()
        metrics_layout.setSpacing(12)

        def make_metric_card(title):
            card = QFrame()
            card.setObjectName("customerSummaryCard")

            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(17, 13, 17, 14)
            card_layout.setSpacing(7)

            title_label = QLabel(title)
            title_label.setObjectName("customerMetricTitle")
            card_layout.addWidget(title_label)

            value_label = QLabel("?")
            value_label.setObjectName("customerMetricValue")
            value_label.setMinimumHeight(32)
            card_layout.addWidget(value_label)

            return card, value_label

        card, self.metric_total_value = make_metric_card("CUSTOMERS IN VIEW")
        metrics_layout.addWidget(card, 0, 0)

        card, self.metric_active_value = make_metric_card("ACTIVE CUSTOMERS")
        metrics_layout.addWidget(card, 0, 1)

        card, self.metric_inactive_value = make_metric_card("INACTIVE CUSTOMERS")
        metrics_layout.addWidget(card, 0, 2)

        card, self.metric_outstanding_value = make_metric_card("OUTSTANDING BALANCE")
        metrics_layout.addWidget(card, 0, 3)

        for column in range(4):
            metrics_layout.setColumnStretch(column, 1)

        layout.addLayout(metrics_layout)

        # Search, filter and secondary actions.
        toolbar = QHBoxLayout()
        toolbar.setSpacing(9)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Search by name, phone, code, email or city..."
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumHeight(40)
        self.search_input.textChanged.connect(self.load_customers)
        toolbar.addWidget(self.search_input, 1)

        self.status_filter = QComboBox()
        self.status_filter.addItems(["All customers", "Active", "Inactive"])
        self.status_filter.currentIndexChanged.connect(self.load_customers)
        self.status_filter.setMinimumWidth(150)
        self.status_filter.setMinimumHeight(40)
        toolbar.addWidget(self.status_filter)

        edit_button = QPushButton("View / Edit")
        edit_button.setObjectName("customerSecondaryButton")
        edit_button.setMinimumHeight(40)
        edit_button.clicked.connect(self.edit_selected_customer)
        toolbar.addWidget(edit_button)

        self.toggle_button = QPushButton("Deactivate")
        self.toggle_button.setObjectName("customerSecondaryButton")
        self.toggle_button.setMinimumHeight(40)
        self.toggle_button.clicked.connect(self.toggle_selected_customer)
        toolbar.addWidget(self.toggle_button)

        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("customerSecondaryButton")
        refresh_button.setMinimumHeight(40)
        refresh_button.clicked.connect(self.load_customers)
        toolbar.addWidget(refresh_button)

        layout.addLayout(toolbar)

        # Customer directory panel.
        table_panel = QFrame()
        table_panel.setObjectName("customerTablePanel")
        panel_layout = QVBoxLayout(table_panel)
        panel_layout.setContentsMargins(15, 13, 15, 15)
        panel_layout.setSpacing(10)

        panel_header = QHBoxLayout()

        section_title = QLabel("Customer Directory")
        section_title.setObjectName("customerSectionTitle")
        panel_header.addWidget(section_title)

        panel_header.addStretch(1)

        self.result_count_label = QLabel("0 records")
        self.result_count_label.setObjectName("customerResultCount")
        panel_header.addWidget(self.result_count_label)

        panel_layout.addLayout(panel_header)

        self.customer_table = _table(table_panel, [
            "Customer Code", "Customer Name", "Mobile Number", "Email",
            "City", "Orders", "Outstanding (PKR)", "Status"
        ])

        self.customer_table.doubleClicked.connect(self.edit_selected_customer)
        self.customer_table.itemSelectionChanged.connect(self._update_toggle_button)
        self.customer_table.setMinimumHeight(350)

        header = self.customer_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(65)

        customer_column_widths = {
            0: 115,
            1: 175,
            2: 135,
            3: 165,
            4: 105,
            5: 75,
            6: 165,
            7: 95,
        }

        for column, width in customer_column_widths.items():
            self.customer_table.setColumnWidth(column, width)

        self.customer_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        panel_layout.addWidget(self.customer_table, 1)
        layout.addWidget(table_panel, 1)

        self.summary = QLabel("Loading customer records...")
        self.summary.setWordWrap(True)
        self.summary.setObjectName("customerSummaryText")
        layout.addWidget(self.summary)

        note = QLabel(
            "Outstanding balances are calculated from non-cancelled orders "
            "less recorded payments. Refund adjustments will be integrated "
            "with the Returns workflow."
        )
        note.setWordWrap(True)
        note.setObjectName("customerFootnote")
        layout.addWidget(note)

    def _apply_visual_theme(self):
        colors = THEMES[current_theme()]

        self.setStyleSheet(f"""
            QLabel#customerPageTitle {{
                color: {colors['text']};
                font-size: 27px;
                font-weight: 700;
            }}
            QLabel#customerPageDescription {{
                color: {colors['muted']};
                font-size: 13px;
            }}
            QFrame#customerSummaryCard {{
                background-color: {colors['surface_alt']};
                border: 1px solid {colors['border']};
                border-radius: 9px;
            }}
            QLabel#customerMetricTitle {{
                color: {colors['muted']};
                font-size: 10px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}
            QLabel#customerMetricValue {{
                color: {colors['primary']};
                font-size: 21px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}
            QFrame#customerTablePanel {{
                background-color: {colors['surface']};
                border: 1px solid {colors['border']};
                border-radius: 9px;
            }}
            QLabel#customerSectionTitle {{
                color: {colors['text']};
                font-size: 16px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}
            QLabel#customerResultCount {{
                color: {colors['muted']};
                font-size: 12px;
                background: transparent;
                border: none;
            }}
            QLabel#customerSummaryText {{
                color: {colors['text']};
                background-color: {colors['notice_bg']};
                border: 1px solid {colors['border']};
                border-radius: 6px;
                padding: 9px 12px;
            }}
            QLabel#customerFootnote {{
                color: {colors['muted']};
                font-size: 11px;
                background: transparent;
                border: none;
            }}
            QPushButton#customerPrimaryButton {{
                background-color: {colors['primary']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 9px 17px;
                font-weight: 700;
            }}
            QPushButton#customerPrimaryButton:hover {{
                background-color: {colors['primary_hover']};
            }}
            QPushButton#customerSecondaryButton {{
                background-color: {colors['surface_alt']};
                color: {colors['text']};
                border: 1px solid {colors['border']};
                border-radius: 6px;
                padding: 8px 12px;
                font-weight: 600;
            }}
            QPushButton#customerSecondaryButton:hover {{
                background-color: {colors['selection']};
            }}
        """)

    def showEvent(self, event):
        self._apply_visual_theme()
        super().showEvent(event)

    def _selected_customer_id(self):
        row = self.customer_table.currentRow()
        if row < 0:
            return None
        item = self.customer_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _update_toggle_button(self):
        customer_id = self._selected_customer_id()
        if not customer_id:
            self.toggle_button.setText("Deactivate")
            return
        session = self.session_factory()
        try:
            customer = session.get(Customer, customer_id)
            self.toggle_button.setText("Deactivate" if customer and customer.is_active else "Reactivate")
        finally:
            session.close()

    def load_customers(self, *_):
        session = self.session_factory()
        try:
            query = session.query(Customer)

            status = (
                self.status_filter.currentText()
                if hasattr(self, "status_filter")
                else "All customers"
            )

            if status == "Active":
                query = query.filter(Customer.is_active.is_(True))
            elif status == "Inactive":
                query = query.filter(Customer.is_active.is_(False))

            term = (
                self.search_input.text().strip()
                if hasattr(self, "search_input")
                else ""
            )

            if term:
                pattern = f"%{term}%"
                query = query.filter(or_(
                    Customer.customer_code.ilike(pattern),
                    Customer.name.ilike(pattern),
                    Customer.phone.ilike(pattern),
                    Customer.email.ilike(pattern),
                    Customer.city.ilike(pattern),
                ))

            customers = query.order_by(Customer.name.asc()).all()

            # Draft orders are not confirmed sales.
            # Cancelled orders must not contribute to customer balances.
            valid_sale_statuses = ("draft", "cancelled")

            stats_rows = (
                session.query(
                    SalesOrder.customer_id,
                    func.count(SalesOrder.id),
                    func.coalesce(
                        func.sum(
                            SalesOrder.total_amount - SalesOrder.amount_paid
                        ),
                        0,
                    ),
                )
                .filter(
                    SalesOrder.order_status.notin_(valid_sale_statuses)
                )
                .group_by(SalesOrder.customer_id)
                .all()
            )

            stats = {
                cid: (
                    count,
                    max(
                        Decimal("0"),
                        Decimal(str(balance or 0)),
                    ),
                )
                for cid, count, balance in stats_rows
            }

            self.customer_table.setRowCount(len(customers))

            for row, customer in enumerate(customers):
                order_count, balance = stats.get(
                    customer.id,
                    (0, Decimal("0")),
                )

                values = [
                    customer.customer_code or f"CUS-{customer.id:06d}",
                    customer.name or "",
                    customer.phone or "",
                    customer.email or "",
                    customer.city or "",
                    str(order_count),
                    f"{balance:,.2f}",
                    "Active" if customer.is_active else "Inactive",
                ]

                for col, value in enumerate(values):
                    item = QTableWidgetItem(str(value))

                    if col == 0:
                        item.setData(
                            Qt.ItemDataRole.UserRole,
                            customer.id,
                        )

                    if col in (5, 6):
                        item.setTextAlignment(
                            Qt.AlignmentFlag.AlignRight
                            | Qt.AlignmentFlag.AlignVCenter
                        )

                    self.customer_table.setItem(row, col, item)

            active_count = sum(1 for c in customers if c.is_active)
            inactive_count = len(customers) - active_count

            total_outstanding = sum(
                (
                    stats.get(c.id, (0, Decimal("0")))[1]
                    for c in customers
                ),
                Decimal("0"),
            )

            self.metric_total_value.setText(f"{len(customers):,}")
            self.metric_active_value.setText(f"{active_count:,}")
            self.metric_inactive_value.setText(f"{inactive_count:,}")
            self.metric_outstanding_value.setText(
                _money(total_outstanding)
            )
            self.result_count_label.setText(
                f"{len(customers):,} records"
            )

            self.summary.setText(
                "Customer figures reflect the current search and status "
                "filter. Order counts and outstanding balances exclude "
                "draft and cancelled orders. Refund adjustments will be "
                "integrated with the Returns workflow. Double-click a "
                "customer to open the full record."
            )

        except Exception as error:
            QMessageBox.warning(
                self,
                "Customer Loading Error",
                str(error),
            )
        finally:
            session.close()

        def add_customer(self):
            dialog = CustomerDialog(self, session_factory=self.session_factory)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.load_customers()
                if dialog.saved_customer_id:
                    self._open_customer(dialog.saved_customer_id)

        def edit_selected_customer(self, *_):
            customer_id = self._selected_customer_id()
            if not customer_id:
                QMessageBox.information(self, "Select Customer", "Please select a customer first.")
                return
            self._open_customer(customer_id)

        def _open_customer(self, customer_id):
            dialog = CustomerDialog(self, customer_id=customer_id, session_factory=self.session_factory)
            dialog.exec()
            self.load_customers()

        def toggle_selected_customer(self):
            customer_id = self._selected_customer_id()
            if not customer_id:
                QMessageBox.information(self, "Select Customer", "Please select a customer first.")
                return
            session = self.session_factory()
            try:
                customer = session.get(Customer, customer_id)
                if not customer:
                    return
                action = "deactivate" if customer.is_active else "reactivate"
                answer = QMessageBox.question(
                    self, "Confirm Customer Status",
                    f"Are you sure you want to {action} {customer.name}?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
                customer.is_active = not customer.is_active
                session.commit()
            except Exception as error:
                session.rollback()
                QMessageBox.warning(self, "Customer Update Error", str(error))
            finally:
                session.close()
            self.load_customers()

    def add_customer(self):
        dialog = CustomerDialog(self, session_factory=self.session_factory)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_customers()
            if dialog.saved_customer_id:
                self._open_customer(dialog.saved_customer_id)

    def edit_selected_customer(self, *_):
        customer_id = self._selected_customer_id()
        if not customer_id:
            QMessageBox.information(self, "Select Customer", "Please select a customer first.")
            return
        self._open_customer(customer_id)

    def _open_customer(self, customer_id):
        dialog = CustomerDialog(self, customer_id=customer_id, session_factory=self.session_factory)
        dialog.exec()
        self.load_customers()

    def toggle_selected_customer(self):
        customer_id = self._selected_customer_id()
        if not customer_id:
            QMessageBox.information(self, "Select Customer", "Please select a customer first.")
            return
        session = self.session_factory()
        try:
            customer = session.get(Customer, customer_id)
            if not customer:
                return
            action = "deactivate" if customer.is_active else "reactivate"
            answer = QMessageBox.question(
                self, "Confirm Customer Status",
                f"Are you sure you want to {action} {customer.name}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            customer.is_active = not customer.is_active
            session.commit()
        except Exception as error:
            session.rollback()
            QMessageBox.warning(self, "Customer Update Error", str(error))
        finally:
            session.close()
        self.load_customers()


class CustomerDialog(QDialog):
    def __init__(self, parent=None, customer_id=None, session_factory=None):
        super().__init__(parent)
        self.session_factory = session_factory or SessionLocal
        self.customer_id = customer_id
        self.saved_customer_id = customer_id
        self.setWindowTitle("Customer Details" if customer_id else "Add Customer")
        self.resize(960, 720)
        self.setMinimumSize(800, 600)
        self._build_ui()
        if customer_id:
            self._load_customer()
        else:
            self.address_tab.setEnabled(False)
            self.labels_tab.setEnabled(False)
            self.orders_tab.setEnabled(False)
            self.payments_tab.setEnabled(False)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(False)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(self.tabs, 1)

        details = QWidget()
        form = QFormLayout(details)
        form.setContentsMargins(20, 20, 20, 20)
        form.setVerticalSpacing(13)
        self.name_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("03XXXXXXXXX or +92 3XX XXXXXXX")
        self.email_input = QLineEdit()
        self.city_input = QLineEdit()
        self.address_input = QTextEdit()
        self.address_input.setMaximumHeight(85)
        self.notes_input = QTextEdit()
        self.notes_input.setMaximumHeight(100)
        self.active_check = QCheckBox("Customer is active")
        self.active_check.setChecked(True)
        form.addRow("Customer name *", self.name_input)
        form.addRow("Mobile number *", self.phone_input)
        form.addRow("Email address", self.email_input)
        form.addRow("City", self.city_input)
        form.addRow("Default / primary address", self.address_input)
        form.addRow("Notes", self.notes_input)
        form.addRow("Status", self.active_check)
        self.tabs.addTab(details, "Customer Details")

        self.address_tab = QWidget()
        address_layout = QVBoxLayout(self.address_tab)
        address_layout.addWidget(QLabel("Save multiple delivery addresses for this customer."))
        self.address_table = _table(self.address_tab, ["Label", "City", "Province", "Address", "Default", "Status"])
        address_layout.addWidget(self.address_table, 1)
        address_buttons = QHBoxLayout()
        for label, callback in [
            ("+ Add Address", self.add_address),
            ("Edit Address", self.edit_address),
            ("Set Default", self.set_default_address),
            ("Deactivate Address", self.deactivate_address),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            address_buttons.addWidget(button)
        address_layout.addLayout(address_buttons)
        self.tabs.addTab(self.address_tab, "Delivery Addresses")

        self.labels_tab = QWidget()
        labels_layout = QVBoxLayout(self.labels_tab)
        self.auto_label = QLabel("Automatic category: —")
        self.auto_label.setStyleSheet("background:#f3f6f4;padding:10px;border-radius:5px;")
        labels_layout.addWidget(self.auto_label)
        labels_layout.addWidget(QLabel("Manual customer labels"))
        self.labels_table = _table(self.labels_tab, ["Label", "Type", "Added"])
        labels_layout.addWidget(self.labels_table, 1)
        label_buttons = QHBoxLayout()
        add_label = QPushButton("+ Add Label")
        add_label.clicked.connect(self.add_label)
        remove_label = QPushButton("Remove Selected Label")
        remove_label.clicked.connect(self.remove_label)
        label_buttons.addWidget(add_label)
        label_buttons.addWidget(remove_label)
        labels_layout.addLayout(label_buttons)
        self.tabs.addTab(self.labels_tab, "Labels")

        self.orders_tab = QWidget()
        orders_layout = QVBoxLayout(self.orders_tab)
        self.order_summary = QLabel("Order summary")
        orders_layout.addWidget(self.order_summary)
        self.orders_table = _table(self.orders_tab, ["Order Number", "Date", "Status", "Payment", "Total (PKR)", "Paid (PKR)", "Balance (PKR)"])
        orders_layout.addWidget(self.orders_table, 1)
        self.tabs.addTab(self.orders_tab, "Order History")

        self.payments_tab = QWidget()
        payments_layout = QVBoxLayout(self.payments_tab)
        payments_layout.addWidget(QLabel("Recorded payments against this customer's orders."))
        self.payments_table = _table(self.payments_tab, ["Date", "Order", "Method", "Amount (PKR)", "Status", "Reference"])
        payments_layout.addWidget(self.payments_table, 1)
        self.tabs.addTab(self.payments_tab, "Payment History")

        buttons = QDialogButtonBox()
        self.save_button = buttons.addButton("Save Customer", QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_button = buttons.addButton("Close", QDialogButtonBox.ButtonRole.RejectRole)
        self.save_button.clicked.connect(self.save_customer)
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def _load_customer(self):
        session = self.session_factory()
        try:
            customer = session.get(Customer, self.customer_id)
            if not customer:
                QMessageBox.warning(self, "Customer Not Found", "This customer record no longer exists.")
                self.reject()
                return
            self.name_input.setText(customer.name or "")
            self.phone_input.setText(customer.phone or "")
            self.email_input.setText(customer.email or "")
            self.city_input.setText(customer.city or "")
            self.address_input.setPlainText(customer.address or "")
            self.notes_input.setPlainText(customer.notes or "")
            self.active_check.setChecked(bool(customer.is_active))
        finally:
            session.close()
        self._load_addresses()
        self._load_labels()
        self._load_order_history()
        self._load_payment_history()

    def save_customer(self):
        name = self.name_input.text().strip()
        phone = self.phone_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Name Required", "Please enter the customer's name.")
            return
        normalized = normalize_phone(phone)
        if len(normalized) != 11 or not normalized.startswith("03"):
            QMessageBox.warning(self, "Valid Mobile Required", "Enter a Pakistani mobile number, for example 03XXXXXXXXX or +92 3XX XXXXXXX.")
            return

        session = self.session_factory()
        try:
            duplicates = session.query(Customer).all()
            for other in duplicates:
                if other.id != self.customer_id and normalize_phone(other.phone) == normalized:
                    QMessageBox.warning(self, "Duplicate Mobile Number", f"This mobile number already belongs to {other.name} ({other.customer_code or other.id}). Customer records are not merged automatically.")
                    return

            customer = session.get(Customer, self.customer_id) if self.customer_id else Customer()
            if customer is None:
                raise ValueError("Customer record was not found.")
            customer.name = name
            customer.phone = phone
            customer.email = self.email_input.text().strip() or None
            customer.city = self.city_input.text().strip() or None
            customer.address = self.address_input.toPlainText().strip() or None
            customer.notes = self.notes_input.toPlainText().strip() or None
            customer.is_active = self.active_check.isChecked()
            if not self.customer_id:
                customer.created_at = datetime.now()
                session.add(customer)
                session.flush()
                customer.customer_code = f"CUS-{customer.id:06d}"
                self.customer_id = customer.id
                self.saved_customer_id = customer.id
            session.commit()
        except Exception as error:
            session.rollback()
            QMessageBox.warning(self, "Customer Save Error", str(error))
            return
        finally:
            session.close()
        self.accept()

    def _selected_row_id(self, table, column=0):
        row = table.currentRow()
        if row < 0:
            return None
        item = table.item(row, column)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _load_addresses(self):
        session = self.session_factory()
        try:
            addresses = session.query(CustomerAddress).filter(
                CustomerAddress.customer_id == self.customer_id,
                CustomerAddress.is_active.is_(True),
            ).order_by(CustomerAddress.is_default.desc(), CustomerAddress.id.asc()).all()
            self.address_table.setRowCount(len(addresses))
            for row, address in enumerate(addresses):
                values = [address.label or "", address.city or "", address.province or "", address.address or "", "Yes" if address.is_default else "No", "Active" if address.is_active else "Inactive"]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if col == 0:
                        item.setData(Qt.ItemDataRole.UserRole, address.id)
                    self.address_table.setItem(row, col, item)
        finally:
            session.close()

    def _address_dialog(self, address=None):
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Delivery Address" if address else "Add Delivery Address")
        dialog.resize(520, 420)
        form = QFormLayout(dialog)
        label = QLineEdit(address.label or "" if address else "")
        province = QLineEdit(address.province or "" if address else "")
        city = QLineEdit(address.city or "" if address else "")
        text = QTextEdit(address.address or "" if address else "")
        instructions = QTextEdit(address.delivery_instructions or "" if address else "")
        text.setMaximumHeight(90)
        instructions.setMaximumHeight(70)
        default = QCheckBox("Set as default delivery address")
        default.setChecked(bool(address.is_default) if address else False)
        form.addRow("Address label", label)
        form.addRow("Province", province)
        form.addRow("City", city)
        form.addRow("Full address *", text)
        form.addRow("Delivery instructions", instructions)
        form.addRow("Default", default)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        address_text = text.toPlainText().strip()
        if not address_text:
            QMessageBox.warning(self, "Address Required", "Please enter the full delivery address.")
            return
        session = self.session_factory()
        try:
            if default.isChecked():
                session.query(CustomerAddress).filter(CustomerAddress.customer_id == self.customer_id).update({CustomerAddress.is_default: False})
            record = session.get(CustomerAddress, address.id) if address else CustomerAddress(customer_id=self.customer_id, created_at=datetime.now(), is_active=True)
            record.label = label.text().strip() or "Delivery Address"
            record.province = province.text().strip() or None
            record.city = city.text().strip() or None
            record.address = address_text
            record.delivery_instructions = instructions.toPlainText().strip() or None
            record.is_default = default.isChecked() or not session.query(CustomerAddress).filter(CustomerAddress.customer_id == self.customer_id, CustomerAddress.is_active.is_(True), CustomerAddress.is_default.is_(True)).first()
            record.is_active = True
            if not address:
                session.add(record)
            if record.is_default:
                customer = session.get(Customer, self.customer_id)
                customer.address = record.address
                customer.city = record.city or customer.city
            session.commit()
        except Exception as error:
            session.rollback()
            QMessageBox.warning(self, "Address Save Error", str(error))
        finally:
            session.close()
        self._load_addresses()

    def add_address(self):
        self._address_dialog()

    def edit_address(self):
        address_id = self._selected_row_id(self.address_table)
        if not address_id:
            QMessageBox.information(self, "Select Address", "Please select an address first.")
            return
        session = self.session_factory()
        try:
            address = session.get(CustomerAddress, address_id)
            if address:
                # Detach a small value snapshot before closing the session.
                class Snapshot: pass
                snapshot = Snapshot()
                for field in ("id", "label", "province", "city", "address", "delivery_instructions", "is_default"):
                    setattr(snapshot, field, getattr(address, field))
            else:
                snapshot = None
        finally:
            session.close()
        if snapshot:
            self._address_dialog(snapshot)

    def set_default_address(self):
        address_id = self._selected_row_id(self.address_table)
        if not address_id:
            QMessageBox.information(self, "Select Address", "Please select an address first.")
            return
        session = self.session_factory()
        try:
            session.query(CustomerAddress).filter(CustomerAddress.customer_id == self.customer_id).update({CustomerAddress.is_default: False})
            address = session.get(CustomerAddress, address_id)
            if address:
                address.is_default = True
                customer = session.get(Customer, self.customer_id)
                customer.address = address.address
                customer.city = address.city or customer.city
            session.commit()
        except Exception as error:
            session.rollback()
            QMessageBox.warning(self, "Default Address Error", str(error))
        finally:
            session.close()
        self._load_addresses()

    def deactivate_address(self):
        address_id = self._selected_row_id(self.address_table)
        if not address_id:
            QMessageBox.information(self, "Select Address", "Please select an address first.")
            return
        answer = QMessageBox.question(self, "Deactivate Address", "Deactivate the selected delivery address?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        session = self.session_factory()
        try:
            address = session.get(CustomerAddress, address_id)
            if address:
                was_default = address.is_default
                address.is_active = False
                address.is_default = False
                if was_default:
                    customer = session.get(Customer, self.customer_id)
                    customer.address = None
                session.commit()
        except Exception as error:
            session.rollback()
            QMessageBox.warning(self, "Address Update Error", str(error))
        finally:
            session.close()
        self._load_addresses()

    def _load_labels(self):
        session = self.session_factory()
        try:
            count = (
                session.query(SalesOrder)
                .filter(
                    SalesOrder.customer_id == self.customer_id,
                    SalesOrder.order_status.notin_(
                        ("draft", "cancelled")
                    ),
                )
                .count()
            )

            if count == 0:
                automatic = "New Customer"
            elif count == 1:
                automatic = "First Order"
            elif count < 5:
                automatic = "Repeat Customer"
            else:
                automatic = "Loyal Customer"

            self.auto_label.setText(
                f"Automatic category (based on confirmed order history): "
                f"{automatic} ? {count} confirmed order(s)"
            )

            labels = (
                session.query(CustomerLabel)
                .filter(
                    CustomerLabel.customer_id == self.customer_id
                )
                .order_by(CustomerLabel.label.asc())
                .all()
            )

            self.labels_table.setRowCount(len(labels))

            for row, label in enumerate(labels):
                values = [
                    label.label,
                    label.label_type,
                    (
                        label.created_at.strftime("%d %b %Y")
                        if label.created_at
                        else ""
                    ),
                ]

                for col, value in enumerate(values):
                    item = QTableWidgetItem(str(value or ""))

                    if col == 0:
                        item.setData(
                            Qt.ItemDataRole.UserRole,
                            label.id,
                        )

                    self.labels_table.setItem(row, col, item)

        finally:
            session.close()

        def add_label(self):
            value, accepted = QInputDialog.getText(self, "Add Customer Label", "Enter a label (e.g. VIP, Frequent Buyer, WhatsApp):")
            value = value.strip() if accepted else ""
            if not value:
                return
            session = self.session_factory()
            try:
                exists = session.query(CustomerLabel).filter(CustomerLabel.customer_id == self.customer_id, func.lower(CustomerLabel.label) == value.lower()).first()
                if exists:
                    QMessageBox.information(self, "Label Exists", "This label is already assigned to the customer.")
                    return
                session.add(CustomerLabel(customer_id=self.customer_id, label=value, label_type="manual", created_at=datetime.now()))
                session.commit()
            except Exception as error:
                session.rollback()
                QMessageBox.warning(self, "Label Save Error", str(error))
            finally:
                session.close()
            self._load_labels()

        def remove_label(self):
            label_id = self._selected_row_id(self.labels_table)
            if not label_id:
                QMessageBox.information(self, "Select Label", "Please select a manual label first.")
                return
            session = self.session_factory()
            try:
                label = session.get(CustomerLabel, label_id)
                if label and label.label_type == "manual":
                    session.delete(label)
                    session.commit()
                elif label:
                    QMessageBox.information(self, "Automatic Label", "Automatic categories are calculated from order history and cannot be removed manually.")
            except Exception as error:
                session.rollback()
                QMessageBox.warning(self, "Label Update Error", str(error))
            finally:
                session.close()
            self._load_labels()

    def add_label(self):
        value, accepted = QInputDialog.getText(self, "Add Customer Label", "Enter a label (e.g. VIP, Frequent Buyer, WhatsApp):")
        value = value.strip() if accepted else ""
        if not value:
            return
        session = self.session_factory()
        try:
            exists = session.query(CustomerLabel).filter(CustomerLabel.customer_id == self.customer_id, func.lower(CustomerLabel.label) == value.lower()).first()
            if exists:
                QMessageBox.information(self, "Label Exists", "This label is already assigned to the customer.")
                return
            session.add(CustomerLabel(customer_id=self.customer_id, label=value, label_type="manual", created_at=datetime.now()))
            session.commit()
        except Exception as error:
            session.rollback()
            QMessageBox.warning(self, "Label Save Error", str(error))
        finally:
            session.close()
        self._load_labels()

    def remove_label(self):
        label_id = self._selected_row_id(self.labels_table)
        if not label_id:
            QMessageBox.information(self, "Select Label", "Please select a manual label first.")
            return
        session = self.session_factory()
        try:
            label = session.get(CustomerLabel, label_id)
            if label and label.label_type == "manual":
                session.delete(label)
                session.commit()
            elif label:
                QMessageBox.information(self, "Automatic Label", "Automatic categories are calculated from order history and cannot be removed manually.")
        except Exception as error:
            session.rollback()
            QMessageBox.warning(self, "Label Update Error", str(error))
        finally:
            session.close()
        self._load_labels()

    def _load_order_history(self):
        session = self.session_factory()
        try:
            orders = (
                session.query(SalesOrder)
                .filter(
                    SalesOrder.customer_id == self.customer_id
                )
                .order_by(SalesOrder.order_date.desc())
                .all()
            )

            self.orders_table.setRowCount(len(orders))

            total_sales = Decimal("0.00")
            outstanding = Decimal("0.00")

            for row, order in enumerate(orders):
                total = Decimal(str(order.total_amount or 0))
                paid = Decimal(str(order.amount_paid or 0))

                is_valid_sale = (
                    (order.order_status or "").lower()
                    not in ("draft", "cancelled")
                )

                # Draft and cancelled orders remain visible in history,
                # but they do not create customer debt or sales totals.
                balance = (
                    max(Decimal("0.00"), total - paid)
                    if is_valid_sale
                    else Decimal("0.00")
                )

                if is_valid_sale:
                    total_sales += total
                    outstanding += balance

                values = [
                    order.order_number,
                    (
                        order.order_date.strftime("%d %b %Y")
                        if order.order_date
                        else ""
                    ),
                    order.order_status,
                    order.payment_status,
                    f"{total:,.2f}",
                    f"{paid:,.2f}",
                    f"{balance:,.2f}",
                ]

                for col, value in enumerate(values):
                    self.orders_table.setItem(
                        row,
                        col,
                        QTableWidgetItem(str(value or "")),
                    )

            self.order_summary.setText(
                f"Orders: {len(orders)}  |  "
                f"Confirmed sales: {_money(total_sales)}  |  "
                f"Outstanding: {_money(outstanding)}"
            )

        finally:
            session.close()

        def _load_payment_history(self):
            session = self.session_factory()
            try:
                payments = (
                    session.query(OrderPayment, SalesOrder)
                    .join(SalesOrder, OrderPayment.order_id == SalesOrder.id)
                    .filter(SalesOrder.customer_id == self.customer_id)
                    .order_by(OrderPayment.created_at.desc())
                    .all()
                )
                self.payments_table.setRowCount(len(payments))
                for row, (payment, order) in enumerate(payments):
                    values = [
                        payment.payment_date.strftime("%d %b %Y") if payment.payment_date else (payment.created_at.strftime("%d %b %Y") if payment.created_at else ""),
                        order.order_number,
                        payment.payment_method,
                        f"{Decimal(str(payment.amount or 0)):,.2f}",
                        payment.payment_status,
                        payment.transaction_reference or "",
                    ]
                    for col, value in enumerate(values):
                        self.payments_table.setItem(row, col, QTableWidgetItem(str(value or "")))
            finally:
                session.close()

    def _load_payment_history(self):
        session = self.session_factory()
        try:
            payments = (
                session.query(OrderPayment, SalesOrder)
                .join(SalesOrder, OrderPayment.order_id == SalesOrder.id)
                .filter(SalesOrder.customer_id == self.customer_id)
                .order_by(OrderPayment.created_at.desc())
                .all()
            )
            self.payments_table.setRowCount(len(payments))
            for row, (payment, order) in enumerate(payments):
                values = [
                    payment.payment_date.strftime("%d %b %Y") if payment.payment_date else (payment.created_at.strftime("%d %b %Y") if payment.created_at else ""),
                    order.order_number,
                    payment.payment_method,
                    f"{Decimal(str(payment.amount or 0)):,.2f}",
                    payment.payment_status,
                    payment.transaction_reference or "",
                ]
                for col, value in enumerate(values):
                    self.payments_table.setItem(row, col, QTableWidgetItem(str(value or "")))
        finally:
            session.close()
