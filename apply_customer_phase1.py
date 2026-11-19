from pathlib import Path
from datetime import datetime
import re
import shutil
import py_compile

ROOT = Path.cwd()
MAIN = ROOT / "desktop_main.py"
NEW_MODULE = ROOT / "customer_manager.py"

if not MAIN.exists():
    raise SystemExit("ERROR: Run this script from the Pillistan project folder containing desktop_main.py.")

main_text = MAIN.read_text(encoding="utf-8-sig")

# Confirm the expected source version before making any changes.
required = [
    "class PillistanApp(QMainWindow):",
    "self.customers_page = self._create_customers_page()",
    'elif name == "Customers":\n                self._refresh_customers()',
    "def _create_customers_page(self):",
]
missing = [item for item in required if item not in main_text]
if missing:
    raise SystemExit(
        "SAFETY STOP: desktop_main.py does not match the inspected source. "
        "No files were changed. Missing expected section(s): " + repr(missing)
    )

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_dir = ROOT / "backups" / f"customer_phase1_before_{stamp}"
backup_dir.mkdir(parents=True, exist_ok=False)
shutil.copy2(MAIN, backup_dir / "desktop_main.py")
if NEW_MODULE.exists():
    shutil.copy2(NEW_MODULE, backup_dir / "customer_manager.py")

module_source = r'''from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QDialog, QDialogButtonBox,
    QLabel, QPushButton, QLineEdit, QTextEdit, QComboBox, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QTabWidget, QMessageBox, QInputDialog, QGroupBox
)
from sqlalchemy import or_, func

from database import SessionLocal
from models import Customer
from orders_models import CustomerAddress, CustomerLabel, SalesOrder, OrderPayment
from orders_service import normalize_phone


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
    return table


class CustomerManager(QWidget):
    """Customer directory and customer records for the Pillistan desktop app."""

    def __init__(self, session_factory=None):
        super().__init__()
        self.session_factory = session_factory or SessionLocal
        self._build_ui()
        self.load_customers()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(13)

        heading = QLabel("Customers & Parties")
        heading.setStyleSheet("font-size:26px;font-weight:700;color:#26352e;")
        layout.addWidget(heading)

        description = QLabel(
            "Manage customer contact details, delivery addresses, labels, orders and payments."
        )
        description.setStyleSheet("color:#718078;font-size:13px;")
        layout.addWidget(description)

        toolbar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search name, phone, customer code, email or city...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.load_customers)
        toolbar.addWidget(self.search_input, 1)

        self.status_filter = QComboBox()
        self.status_filter.addItems(["All customers", "Active", "Inactive"])
        self.status_filter.currentIndexChanged.connect(self.load_customers)
        self.status_filter.setMinimumWidth(145)
        toolbar.addWidget(self.status_filter)

        add_button = QPushButton("+ Add Customer")
        add_button.clicked.connect(self.add_customer)
        toolbar.addWidget(add_button)

        edit_button = QPushButton("View / Edit")
        edit_button.clicked.connect(self.edit_selected_customer)
        toolbar.addWidget(edit_button)

        self.toggle_button = QPushButton("Deactivate")
        self.toggle_button.clicked.connect(self.toggle_selected_customer)
        toolbar.addWidget(self.toggle_button)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.load_customers)
        toolbar.addWidget(refresh_button)
        layout.addLayout(toolbar)

        self.summary = QLabel("Loading customers...")
        self.summary.setStyleSheet(
            "background:#f3f6f4;color:#405249;padding:10px;border-radius:6px;"
        )
        layout.addWidget(self.summary)

        self.customer_table = _table(self, [
            "Customer Code", "Customer Name", "Mobile Number", "Email",
            "City", "Orders", "Outstanding (PKR)", "Status"
        ])
        self.customer_table.doubleClicked.connect(self.edit_selected_customer)
        self.customer_table.itemSelectionChanged.connect(self._update_toggle_button)
        self.customer_table.setMinimumHeight(350)
        layout.addWidget(self.customer_table, 1)

        note = QLabel(
            "Outstanding is calculated from non-cancelled orders (total less recorded payments). "
            "Refund adjustments will be integrated with the Returns workflow."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#718078;font-size:11px;")
        layout.addWidget(note)

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
            status = self.status_filter.currentText() if hasattr(self, "status_filter") else "All customers"
            if status == "Active":
                query = query.filter(Customer.is_active.is_(True))
            elif status == "Inactive":
                query = query.filter(Customer.is_active.is_(False))

            term = self.search_input.text().strip() if hasattr(self, "search_input") else ""
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
            stats_rows = (
                session.query(
                    SalesOrder.customer_id,
                    func.count(SalesOrder.id),
                    func.coalesce(func.sum(SalesOrder.total_amount - SalesOrder.amount_paid), 0),
                )
                .filter(SalesOrder.order_status != "cancelled")
                .group_by(SalesOrder.customer_id)
                .all()
            )
            stats = {cid: (count, max(Decimal("0"), Decimal(str(balance or 0))))
                     for cid, count, balance in stats_rows}

            self.customer_table.setRowCount(len(customers))
            for row, customer in enumerate(customers):
                order_count, balance = stats.get(customer.id, (0, Decimal("0")))
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
                        item.setData(Qt.ItemDataRole.UserRole, customer.id)
                    if col in (5, 6):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.customer_table.setItem(row, col, item)

            active_count = sum(1 for c in customers if c.is_active)
            self.summary.setText(
                f"Showing {len(customers):,} customer(s)  |  "
                f"Active in current results: {active_count:,}  |  "
                f"Double-click a customer to view or edit the record."
            )
        except Exception as error:
            QMessageBox.warning(self, "Customer Loading Error", str(error))
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


class CustomerDialog(QDialog):
    def __init__(self, parent=None, customer_id=None, session_factory=None):
        super().__init__(parent)
        self.session_factory = session_factory or SessionLocal
        self.customer_id = customer_id
        self.saved_customer_id = customer_id
        self.setWindowTitle("Customer Details" if customer_id else "Add Customer")
        self.resize(900, 680)
        self.setMinimumSize(760, 560)
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
            count = session.query(SalesOrder).filter(SalesOrder.customer_id == self.customer_id, SalesOrder.order_status != "cancelled").count()
            if count == 0:
                automatic = "New Customer"
            elif count < 5:
                automatic = "Repeat Customer" if count >= 2 else "First Order"
            else:
                automatic = "Loyal Customer"
            self.auto_label.setText(f"Automatic category (based on order history): {automatic} — {count} non-cancelled order(s)")
            labels = session.query(CustomerLabel).filter(CustomerLabel.customer_id == self.customer_id).order_by(CustomerLabel.label.asc()).all()
            self.labels_table.setRowCount(len(labels))
            for row, label in enumerate(labels):
                values = [label.label, label.label_type, label.created_at.strftime("%d %b %Y") if label.created_at else ""]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(str(value or ""))
                    if col == 0:
                        item.setData(Qt.ItemDataRole.UserRole, label.id)
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

    def _load_order_history(self):
        session = self.session_factory()
        try:
            orders = session.query(SalesOrder).filter(SalesOrder.customer_id == self.customer_id).order_by(SalesOrder.order_date.desc()).all()
            self.orders_table.setRowCount(len(orders))
            total_sales = Decimal("0")
            outstanding = Decimal("0")
            for row, order in enumerate(orders):
                total = Decimal(str(order.total_amount or 0))
                paid = Decimal(str(order.amount_paid or 0))
                balance = max(Decimal("0"), total - paid) if order.order_status != "cancelled" else Decimal("0")
                if order.order_status != "cancelled":
                    total_sales += total
                    outstanding += balance
                values = [order.order_number, order.order_date.strftime("%d %b %Y") if order.order_date else "", order.order_status, order.payment_status, f"{total:,.2f}", f"{paid:,.2f}", f"{balance:,.2f}"]
                for col, value in enumerate(values):
                    self.orders_table.setItem(row, col, QTableWidgetItem(str(value)))
            self.order_summary.setText(f"Orders: {len(orders)}  |  Non-cancelled sales: {_money(total_sales)}  |  Outstanding: {_money(outstanding)}")
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
'''

# Remove both duplicated legacy customer page implementations.
for method in ("_create_customers_page", "_refresh_customers"):
    pattern = rf"^    def {method}\(self\):\n.*?(?=^    def |^class |\Z)"
    main_text, count = re.subn(pattern, "", main_text, flags=re.MULTILINE | re.DOTALL)
    if count != 2:
        raise SystemExit(
            f"SAFETY STOP: expected to remove exactly 2 duplicate {method} methods, found {count}. "
            "Only backups may have been created; source files were not patched."
        )

main_text = main_text.replace(
    "from purchase_manager import PurchaseManager\n",
    "from purchase_manager import PurchaseManager\nfrom customer_manager import CustomerManager\n",
    1,
)
main_text = main_text.replace(
    "self.customers_page = self._create_customers_page()",
    "self.customers_page = CustomerManager()",
    1,
)
main_text = main_text.replace(
    'elif name == "Customers":\n                self._refresh_customers()',
    'elif name == "Customers":\n                self.customers_page.load_customers()',
    1,
)

# Write new module and patched main, then syntax-check both.
NEW_MODULE.write_text(module_source, encoding="utf-8")
MAIN.write_text(main_text, encoding="utf-8")

try:
    py_compile.compile(str(NEW_MODULE), doraise=True)
    py_compile.compile(str(MAIN), doraise=True)
except Exception as error:
    # Restore the original main file if syntax validation fails.
    shutil.copy2(backup_dir / "desktop_main.py", MAIN)
    if (backup_dir / "customer_manager.py").exists():
        shutil.copy2(backup_dir / "customer_manager.py", NEW_MODULE)
    else:
        NEW_MODULE.unlink(missing_ok=True)
    raise SystemExit(f"SYNTAX CHECK FAILED. Original source restored. Details: {error}")

print("CUSTOMER MANAGEMENT PHASE 1 PATCH APPLIED")
print(f"Backup folder: {backup_dir}")
print("Created: customer_manager.py")
print("Updated: desktop_main.py")
print("Removed: 2 duplicate customer page methods and 2 duplicate refresh methods")
print("Syntax check: PASSED for both changed Python files")
print("Database: NOT modified")
print("Next: launch the app and test Customers > Add Customer, edit, addresses, labels, order history and payments.")
