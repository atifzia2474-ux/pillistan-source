
from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtGui import QPixmap
from branding import get_logo_pixmap

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QLineEdit, QDateEdit,
    QTableWidget, QTableWidgetItem, QMessageBox, QDialog,
    QFormLayout, QHeaderView
)
from PySide6.QtCore import QDate, Qt

from database import SessionLocal
from models import (
    Product, Supplier, Purchase, PurchaseItem,
    SupplierPayment, InventoryBatch, StockMovement
)
from theme_manager import apply_theme


STYLE = """
QMainWindow, QWidget {
    background-color: #101827;
    color: #e5e7eb;
    font-family: Segoe UI;
    font-size: 10pt;
}
QLabel {
    color: #d1d5db;
}
QLineEdit, QComboBox, QDateEdit {
    background-color: #1e293b;
    color: white;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px;
    min-height: 22px;
}
QComboBox QAbstractItemView {
    background-color: #1e293b;
    color: white;
    selection-background-color: #047857;
}
QPushButton {
    background-color: #047857;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 9px 16px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #059669;
}
QPushButton#secondary {
    background-color: #334155;
}
QPushButton#danger {
    background-color: #991b1b;
}
QTableWidget {
    background-color: #1e293b;
    color: white;
    gridline-color: #334155;
    border: 1px solid #334155;
    border-radius: 6px;
}
QHeaderView::section {
    background-color: #263449;
    color: white;
    padding: 8px;
    border: none;
    font-weight: bold;
}
"""


def money(value):
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def quantity(value):
    return Decimal(str(value or "0")).quantize(Decimal("0.001"))


class AddSupplierDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add New Supplier")
        self.setMinimumWidth(380)

        layout = QFormLayout(self)

        self.name = QLineEdit()
        self.phone = QLineEdit()
        self.address = QLineEdit()
        self.notes = QLineEdit()

        layout.addRow("Supplier Name *", self.name)
        layout.addRow("Phone", self.phone)
        layout.addRow("Address", self.address)
        layout.addRow("Notes", self.notes)

        save_button = QPushButton("Save Supplier")
        save_button.clicked.connect(self.accept)
        layout.addRow(save_button)

    def supplier_data(self):
        return {
            "name": self.name.text().strip(),
            "phone": self.phone.text().strip(),
            "address": self.address.text().strip(),
            "notes": self.notes.text().strip()
        }


class PurchaseManager(QMainWindow):
    def __init__(self, user=None):
        super().__init__()
        self.user = user or {}

        self.setWindowTitle("Pillistan | Purchase Management")
        self.resize(1250, 820)
        self.setStyleSheet(STYLE)

        self.purchase_items = []

        central = QWidget()
        self.setCentralWidget(central)
        main = QVBoxLayout(central)

        header_row = QHBoxLayout()

        purchase_logo = QLabel()
        purchase_logo.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        purchase_logo.setPixmap(get_logo_pixmap(150, 85))
        header_row.addWidget(purchase_logo)

        heading = QLabel("PURCHASE MANAGEMENT")
        heading.setStyleSheet(
            "font-size: 22pt; font-weight: bold; color: #10b981;"
        )
        header_row.addWidget(heading)
        header_row.addStretch()
        main.addLayout(header_row)

        subtitle = QLabel(
            "Record supplier purchases and automatically receive stock"
        )
        main.addWidget(subtitle)

        supplier_payment_button = QPushButton("Record Later Supplier Payment")
        supplier_payment_button.setObjectName("secondary")
        supplier_payment_button.clicked.connect(self.record_supplier_payment_dialog)
        main.addWidget(supplier_payment_button)

        # Supplier and invoice section
        supplier_row = QHBoxLayout()

        self.supplier_combo = QComboBox()
        self.supplier_combo.setMinimumWidth(250)

        add_supplier_button = QPushButton("+ Add Supplier")
        add_supplier_button.setObjectName("secondary")
        add_supplier_button.clicked.connect(self.add_supplier)

        self.invoice_number = QLineEdit()
        self.invoice_number.setPlaceholderText("Supplier invoice number")

        self.purchase_date = QDateEdit()
        self.purchase_date.setCalendarPopup(True)
        self.purchase_date.setDisplayFormat("dd MMM yyyy")
        self.purchase_date.setDate(QDate.currentDate())

        supplier_row.addWidget(QLabel("Supplier"))
        supplier_row.addWidget(self.supplier_combo)
        supplier_row.addWidget(add_supplier_button)
        supplier_row.addWidget(QLabel("Invoice No."))
        supplier_row.addWidget(self.invoice_number)
        supplier_row.addWidget(QLabel("Date"))
        supplier_row.addWidget(self.purchase_date)

        main.addLayout(supplier_row)

        # Product entry section
        product_heading = QLabel("ADD PRODUCTS TO PURCHASE")
        product_heading.setStyleSheet(
            "font-size: 13pt; font-weight: bold; color: #10b981;"
        )
        main.addWidget(product_heading)

        product_row = QHBoxLayout()

        self.product_combo = QComboBox()
        self.product_combo.setMinimumWidth(220)

        self.batch_number = QLineEdit()
        self.batch_number.setPlaceholderText("Batch number")

        self.expiry_date = QDateEdit()
        self.expiry_date.setCalendarPopup(True)
        self.expiry_date.setDisplayFormat("dd MMM yyyy")
        self.expiry_date.setSpecialValueText("No expiry")
        self.expiry_date.setMinimumDate(QDate(2000, 1, 1))
        self.expiry_date.setDate(QDate(2000, 1, 1))

        self.qty_input = QLineEdit()
        self.qty_input.setPlaceholderText("Quantity")

        self.cost_input = QLineEdit()
        self.cost_input.setPlaceholderText("Unit cost (PKR)")

        add_item_button = QPushButton("+ Add Item")
        add_item_button.clicked.connect(self.add_item)

        product_row.addWidget(self.product_combo, 2)
        product_row.addWidget(self.batch_number, 1)
        product_row.addWidget(self.expiry_date, 1)
        product_row.addWidget(self.qty_input, 1)
        product_row.addWidget(self.cost_input, 1)
        product_row.addWidget(add_item_button)

        main.addLayout(product_row)

        # Purchase items table
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Product", "Batch", "Expiry", "Quantity",
            "Unit Cost", "Line Total", "Product ID"
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setColumnHidden(6, True)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        main.addWidget(self.table)

        remove_button = QPushButton("Remove Selected Item")
        remove_button.setObjectName("danger")
        remove_button.clicked.connect(self.remove_item)
        main.addWidget(remove_button)

        # Financial section
        finance_row = QHBoxLayout()

        self.discount_input = QLineEdit("0")
        self.discount_input.setPlaceholderText("Discount")

        self.charges_input = QLineEdit("0")
        self.charges_input.setPlaceholderText("Other charges")

        self.paid_input = QLineEdit("0")
        self.paid_input.setPlaceholderText("Amount paid")

        for field in (
            self.discount_input,
            self.charges_input,
            self.paid_input
        ):
            field.textChanged.connect(self.update_totals)

        finance_row.addWidget(QLabel("Discount (PKR)"))
        finance_row.addWidget(self.discount_input)
        finance_row.addWidget(QLabel("Other Charges (PKR)"))
        finance_row.addWidget(self.charges_input)
        finance_row.addWidget(QLabel("Paid Amount (PKR)"))
        finance_row.addWidget(self.paid_input)

        main.addLayout(finance_row)

        self.subtotal_label = QLabel("Subtotal: PKR 0.00")
        self.total_label = QLabel("Total: PKR 0.00")
        self.balance_label = QLabel("Outstanding: PKR 0.00")

        for label in (
            self.subtotal_label,
            self.total_label,
            self.balance_label
        ):
            label.setStyleSheet(
                "font-size: 12pt; font-weight: bold; color: #10b981;"
            )

        totals_row = QHBoxLayout()
        totals_row.addWidget(self.subtotal_label)
        totals_row.addWidget(self.total_label)
        totals_row.addWidget(self.balance_label)
        main.addLayout(totals_row)

        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("Purchase notes (optional)")
        main.addWidget(self.notes_input)

        save_button = QPushButton("SAVE PURCHASE & RECEIVE STOCK")
        save_button.setMinimumHeight(48)
        save_button.setStyleSheet(
            "font-size: 12pt; background-color: #059669;"
        )
        save_button.clicked.connect(self.save_purchase)
        main.addWidget(save_button)

        self.load_suppliers()
        self.load_products()
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self)

    def record_supplier_payment_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Record Supplier Payment")
        dialog.setMinimumWidth(520)
        form = QFormLayout(dialog)

        purchase_combo = QComboBox()
        amount_input = QLineEdit()
        amount_input.setPlaceholderText("Payment amount in PKR")
        method_combo = QComboBox()
        method_combo.addItem("Cash", "cash")
        method_combo.addItem("Bank Transfer", "bank transfer")
        reference_input = QLineEdit()
        reference_input.setPlaceholderText("Receipt / payment voucher reference (required)")
        payment_date = QDateEdit()
        payment_date.setCalendarPopup(True)
        payment_date.setDisplayFormat("dd MMM yyyy")
        payment_date.setDate(QDate.currentDate())
        notes_input = QLineEdit()
        notes_input.setPlaceholderText("Optional notes")

        session = SessionLocal()
        try:
            outstanding = (
                session.query(Purchase)
                .filter(Purchase.status == "received", Purchase.balance_amount > 0)
                .order_by(Purchase.purchase_date.desc(), Purchase.id.desc())
                .all()
            )
            for purchase in outstanding:
                supplier = session.get(Supplier, purchase.supplier_id)
                supplier_name = supplier.name if supplier else f"Supplier #{purchase.supplier_id}"
                purchase_combo.addItem(
                    f"Purchase #{purchase.id} | {supplier_name} | Outstanding PKR {money(purchase.balance_amount):,.2f}",
                    purchase.id,
                )
        finally:
            session.close()

        form.addRow("Purchase with outstanding balance", purchase_combo)
        form.addRow("Payment date", payment_date)
        form.addRow("Amount (PKR)", amount_input)
        form.addRow("Payment method", method_combo)
        form.addRow("Reference", reference_input)
        form.addRow("Notes", notes_input)

        save_button = QPushButton("Record Payment")
        save_button.clicked.connect(dialog.accept)
        form.addRow(save_button)

        if purchase_combo.count() == 0:
            QMessageBox.information(self, "No Outstanding Purchases",
                                    "There are no received purchases with an outstanding balance.")
            return
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        session = SessionLocal()
        try:
            from supplier_payment_service import record_supplier_payment
            username = str(self.user.get("username") or "").strip()
            if not username:
                raise ValueError("The authenticated username could not be identified. Please log in again.")
            record_supplier_payment(
                session,
                purchase_id=purchase_combo.currentData(),
                payment_date=date.fromisoformat(payment_date.date().toString("yyyy-MM-dd")),
                amount=amount_input.text().strip(),
                payment_method=method_combo.currentData(),
                reference_number=reference_input.text().strip(),
                notes=notes_input.text().strip(),
                username=username,
                changed_by_id=self.user.get("id"),
            )
            session.commit()
            QMessageBox.information(self, "Payment Recorded",
                                    "Supplier payment and accounting entry were recorded successfully.")
        except Exception as error:
            session.rollback()
            QMessageBox.critical(self, "Supplier Payment Failed", str(error))
        finally:
            session.close()

    def load_suppliers(self):
        self.supplier_combo.clear()

        db = SessionLocal()
        try:
            suppliers = (
                db.query(Supplier)
                .filter(Supplier.is_active == True)
                .order_by(Supplier.name)
                .all()
            )

            for supplier in suppliers:
                self.supplier_combo.addItem(
                    supplier.name, supplier.id
                )
        finally:
            db.close()

    def load_products(self):
        self.product_combo.clear()

        db = SessionLocal()
        try:
            products = (
                db.query(Product)
                .filter(
                    Product.is_active == True,
                    Product.is_archived == False
                )
                .order_by(Product.name)
                .all()
            )

            for product in products:
                self.product_combo.addItem(
                    f"{product.name} ({product.sku})",
                    product.id
                )
        finally:
            db.close()

    def add_supplier(self):
        dialog = AddSupplierDialog(self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.supplier_data()

        if not data["name"]:
            QMessageBox.warning(
                self, "Missing Information",
                "Please enter a supplier name."
            )
            return

        db = SessionLocal()
        try:
            supplier = Supplier(
                name=data["name"],
                phone=data["phone"] or None,
                address=data["address"] or None,
                notes=data["notes"] or None
            )
            db.add(supplier)
            db.commit()
            db.refresh(supplier)
            new_id = supplier.id

        except Exception as error:
            db.rollback()
            QMessageBox.critical(
                self, "Database Error", str(error)
            )
            return
        finally:
            db.close()

        self.load_suppliers()
        index = self.supplier_combo.findData(new_id)
        if index >= 0:
            self.supplier_combo.setCurrentIndex(index)

        QMessageBox.information(
            self, "Success", "Supplier added successfully."
        )

    def add_item(self):
        product_id = self.product_combo.currentData()

        if product_id is None:
            QMessageBox.warning(
                self, "No Product",
                "Please add a product in Product Management first."
            )
            return

        try:
            qty = quantity(self.qty_input.text())
            cost = money(self.cost_input.text())

            if qty <= 0:
                raise ValueError("Quantity must be greater than zero.")

            if cost < 0:
                raise ValueError("Unit cost cannot be negative.")

        except (InvalidOperation, ValueError) as error:
            QMessageBox.warning(
                self, "Invalid Entry", str(error)
            )
            return

        product_name = self.product_combo.currentText()
        batch = self.batch_number.text().strip()

        expiry = None
        if self.expiry_date.date() > QDate(2000, 1, 1):
            expiry = self.expiry_date.date().toString("yyyy-MM-dd")

        line_total = money(qty * cost)

        item = {
            "product_id": product_id,
            "product_name": product_name,
            "batch_number": batch or None,
            "expiry_date": expiry,
            "quantity": qty,
            "unit_cost": cost,
            "line_total": line_total
        }

        self.purchase_items.append(item)
        self.refresh_table()

        self.batch_number.clear()
        self.qty_input.clear()
        self.cost_input.clear()
        self.expiry_date.setDate(QDate(2000, 1, 1))

    def refresh_table(self):
        self.table.setRowCount(0)

        for item in self.purchase_items:
            row = self.table.rowCount()
            self.table.insertRow(row)

            values = [
                item["product_name"],
                item["batch_number"] or "-",
                item["expiry_date"] or "-",
                str(item["quantity"]),
                f"{item['unit_cost']:.2f}",
                f"{item['line_total']:.2f}",
                str(item["product_id"])
            ]

            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter
                )
                self.table.setItem(row, col, cell)

        self.update_totals()

    def remove_item(self):
        row = self.table.currentRow()

        if row < 0:
            QMessageBox.warning(
                self, "Select Item",
                "Please select a purchase item first."
            )
            return

        self.purchase_items.pop(row)
        self.refresh_table()

    def calculate_totals(self):
        subtotal = sum(
            (item["line_total"] for item in self.purchase_items),
            Decimal("0.00")
        )

        discount = money(self.discount_input.text() or "0")
        charges = money(self.charges_input.text() or "0")
        total = subtotal - discount + charges

        if discount < 0 or charges < 0:
            raise ValueError(
                "Discount and other charges cannot be negative."
            )

        if total < 0:
            raise ValueError(
                "Discount cannot exceed the purchase subtotal."
            )

        return subtotal, discount, charges, money(total)

    def update_totals(self):
        try:
            subtotal, discount, charges, total = (
                self.calculate_totals()
            )
            paid = money(self.paid_input.text() or "0")
            balance = total - paid

            self.subtotal_label.setText(
                f"Subtotal: PKR {subtotal:,.2f}"
            )
            self.total_label.setText(
                f"Total: PKR {total:,.2f}"
            )
            self.balance_label.setText(
                f"Outstanding: PKR {balance:,.2f}"
            )
        except (ValueError, InvalidOperation):
            self.subtotal_label.setText("Subtotal: PKR --")
            self.total_label.setText("Total: PKR --")
            self.balance_label.setText("Outstanding: PKR --")

    def save_purchase(self):
        if self.supplier_combo.currentData() is None:
            QMessageBox.warning(
                self, "Missing Supplier",
                "Please add or select a supplier."
            )
            return

        if not self.purchase_items:
            QMessageBox.warning(
                self, "No Items",
                "Please add at least one product."
            )
            return

        try:
            subtotal, discount, charges, total = self.calculate_totals()
            paid = money(self.paid_input.text() or "0")

            if paid < 0:
                raise ValueError("Paid amount cannot be negative.")
            if paid > total:
                raise ValueError("Paid amount cannot exceed the purchase total.")

            from inventory_purchase_service import create_purchase

            result = create_purchase(
                supplier_id=self.supplier_combo.currentData(),
                purchase_date=date.fromisoformat(
                    self.purchase_date.date().toString("yyyy-MM-dd")
                ),
                items=self.purchase_items,
                discount=discount,
                other_charges=charges,
                paid_amount=paid,
                invoice_number=self.invoice_number.text().strip(),
                notes=self.notes_input.text().strip(),
                payment_method="cash",
                username=str(self.user.get("username") or "").strip(),
                changed_by_id=self.user.get("id"),
            )

        except (ValueError, InvalidOperation) as error:
            QMessageBox.warning(self, "Purchase Not Saved", str(error))
            return
        except Exception as error:
            QMessageBox.critical(
                self,
                "Purchase Not Saved",
                "The purchase, inventory and accounting transaction "
                "could not be completed. The transaction was rolled back.\n\n"
                f"Reason: {error}"
            )
            return

        QMessageBox.information(
            self,
            "Purchase Saved",
            f"Purchase saved successfully!\n\n"
            f"Purchase ID: {result['purchase_id']}\n"
            f"Total: PKR {result['total']:,.2f}\n"
            f"Paid: PKR {result['paid']:,.2f}\n"
            f"Outstanding: PKR {result['balance']:,.2f}\n"
            f"Inventory batches created: {result['batch_count']}\n"
            "Accounting entries have been posted."
        )

        self.purchase_items.clear()
        self.refresh_table()
        self.invoice_number.clear()
        self.discount_input.setText("0")
        self.charges_input.setText("0")
        self.paid_input.setText("0")
        self.notes_input.clear()
        self.batch_number.clear()
        self.qty_input.clear()
        self.cost_input.clear()
        self.expiry_date.setDate(QDate(2000, 1, 1))

