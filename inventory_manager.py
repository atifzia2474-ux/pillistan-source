import sys
from datetime import date, timedelta
from decimal import Decimal

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QLineEdit, QComboBox, QDateEdit, QDoubleSpinBox,
    QFormLayout, QDialog, QMessageBox, QHeaderView, QCheckBox
)
from PySide6.QtCore import Qt, QDate

from database import SessionLocal
from models import Product, InventoryBatch, StockMovement
from inventory_stock_service import (
    get_batch_stock_summary,
    write_inventory_audit,
)
from theme_manager import apply_theme


STYLE = """
QMainWindow, QWidget {
    background-color: #101b2a;
    color: #e8f0f7;
    font-family: Segoe UI;
    font-size: 10pt;
}
QLabel#title {
    font-size: 22pt;
    font-weight: bold;
    color: #ffffff;
}
QLabel#subtitle {
    color: #9aafc3;
}
QPushButton {
    background-color: #087f5b;
    color: white;
    border: none;
    border-radius: 7px;
    padding: 10px 16px;
    font-weight: bold;
}
QPushButton:hover { background-color: #099268; }
QLineEdit, QComboBox, QDateEdit, QDoubleSpinBox {
    background-color: #1c2b3d;
    color: white;
    border: 1px solid #34465c;
    border-radius: 6px;
    padding: 7px;
}
QTableWidget {
    background-color: #172538;
    alternate-background-color: #1c2b3d;
    gridline-color: #34465c;
    border: 1px solid #34465c;
    border-radius: 8px;
}
QHeaderView::section {
    background-color: #20344a;
    color: #b9d4e8;
    padding: 9px;
    border: none;
    font-weight: bold;
}
"""


class ReceiveStockDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Record Opening / Manual Stock")
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.product = QComboBox()
        self.batch_number = QLineEdit()
        self.batch_number.setPlaceholderText("Batch number, if available")

        self.received_date = QDateEdit()
        self.received_date.setCalendarPopup(True)
        self.received_date.setDate(QDate.currentDate())

        self.has_expiry = QCheckBox("This batch has an expiry date")
        self.has_expiry.setChecked(True)

        self.expiry_date = QDateEdit()
        self.expiry_date.setCalendarPopup(True)
        self.expiry_date.setDate(QDate.currentDate().addYears(1))
        self.has_expiry.toggled.connect(self.expiry_date.setEnabled)

        self.quantity = QDoubleSpinBox()
        self.quantity.setRange(0.001, 999999999)
        self.quantity.setDecimals(3)
        self.quantity.setValue(1)

        self.unit_cost = QDoubleSpinBox()
        self.unit_cost.setRange(0, 999999999)
        self.unit_cost.setDecimals(2)

        self.supplier = QLineEdit()
        self.supplier.setPlaceholderText("Optional source / supplier")

        self.reason = QLineEdit()
        self.reason.setPlaceholderText(
            "Required: opening balance, migration, physical count, etc."
        )

        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Optional additional notes")

        form.addRow("Product:", self.product)
        form.addRow("Batch number:", self.batch_number)
        form.addRow("Received date:", self.received_date)
        form.addRow("", self.has_expiry)
        form.addRow("Expiry date:", self.expiry_date)
        form.addRow("Quantity:", self.quantity)
        form.addRow("Unit cost (PKR):", self.unit_cost)
        form.addRow("Source / supplier:", self.supplier)
        form.addRow("Reason:", self.reason)
        form.addRow("Notes:", self.notes)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        save_button = QPushButton("Save Opening Stock")
        cancel_button = QPushButton("Cancel")
        save_button.clicked.connect(self.validate_and_accept)
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)
        buttons.addWidget(save_button)
        layout.addLayout(buttons)

        self.load_products()

    def load_products(self):
        db = SessionLocal()
        try:
            products = (
                db.query(Product)
                .filter(
                    Product.is_active.is_(True),
                    Product.is_archived.is_(False),
                )
                .order_by(Product.name)
                .all()
            )
            for product in products:
                self.product.addItem(
                    f"{product.name} ({product.sku})", product.id
                )
        finally:
            db.close()

    def validate_and_accept(self):
        if self.product.currentData() is None:
            QMessageBox.warning(self, "Product Required", "Select a product.")
            return
        if not self.reason.text().strip():
            QMessageBox.warning(
                self, "Reason Required",
                "Please enter why this opening/manual stock is being recorded."
            )
            return

        received = self.received_date.date().toPython()
        expiry = (
            self.expiry_date.date().toPython()
            if self.has_expiry.isChecked() else None
        )
        if expiry and expiry < received:
            QMessageBox.warning(
                self, "Invalid Expiry",
                "Expiry date cannot be earlier than received date."
            )
            return
        self.accept()

    def get_data(self):
        return {
            "product_id": self.product.currentData(),
            "batch_number": self.batch_number.text().strip() or None,
            "received_date": self.received_date.date().toPython(),
            "expiry_date": (
                self.expiry_date.date().toPython()
                if self.has_expiry.isChecked() else None
            ),
            "quantity": Decimal(str(self.quantity.value())),
            "unit_cost": Decimal(str(self.unit_cost.value())),
            "supplier": self.supplier.text().strip() or None,
            "reason": self.reason.text().strip(),
            "notes": self.notes.text().strip() or None,
        }


class InventoryWindow(QMainWindow):
    def __init__(self, user=None):
        super().__init__()
        self.user = user or {}
        self.setWindowTitle("Pillistan | Inventory Management")
        self.resize(1450, 780)
        self.setMinimumSize(1050, 600)
        self.setStyleSheet(STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(13)

        header = QHBoxLayout()
        title_area = QVBoxLayout()

        title = QLabel("Inventory Management")
        title.setObjectName("title")
        subtitle = QLabel(
            "Monitor physical stock, reservations, availability and expiry."
        )
        subtitle.setObjectName("subtitle")
        title_area.addWidget(title)
        title_area.addWidget(subtitle)
        header.addLayout(title_area)
        header.addStretch()

        receive_button = QPushButton("+ Opening / Manual Stock")
        receive_button.clicked.connect(self.receive_stock)
        header.addWidget(receive_button)

        adjust_button = QPushButton("Adjust Stock")
        adjust_button.clicked.connect(self.open_stock_adjustment)
        header.addWidget(adjust_button)
        layout.addLayout(header)

        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Search product, SKU, batch number or supplier..."
        )
        self.search.textChanged.connect(self.load_inventory)
        layout.addWidget(self.search)

        self.table = QTableWidget()
        self.table.setColumnCount(12)
        self.table.setHorizontalHeaderLabels([
            "Product", "SKU", "Batch", "Received", "Expiry",
            "Received Qty", "Physical Remaining", "Reserved",
            "Available", "Expiry Status", "Unit Cost (PKR)", "Source"
        ])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        self.status = QLabel("Loading inventory...")
        self.status.setObjectName("subtitle")
        layout.addWidget(self.status)

        self.load_inventory()
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self)

    @staticmethod
    def expiry_status(expiry):
        if expiry is None:
            return "No expiry date"
        today = date.today()
        if expiry < today:
            return "EXPIRED"
        if expiry <= today + timedelta(days=30):
            return "Expiring soon"
        return "Healthy"

    def load_inventory(self):
        search_text = self.search.text().strip().lower()
        db = SessionLocal()
        try:
            records = (
                db.query(InventoryBatch, Product)
                .join(Product, InventoryBatch.product_id == Product.id)
                .filter(InventoryBatch.is_active.is_(True))
                .order_by(
                    InventoryBatch.expiry_date.is_(None),
                    InventoryBatch.expiry_date,
                    InventoryBatch.received_date,
                    InventoryBatch.id,
                )
                .all()
            )

            if search_text:
                records = [
                    (batch, product)
                    for batch, product in records
                    if search_text in (product.name or "").lower()
                    or search_text in (product.sku or "").lower()
                    or search_text in (batch.batch_number or "").lower()
                    or search_text in (batch.supplier or "").lower()
                ]

            self.table.setRowCount(len(records))
            total_physical = Decimal("0")
            total_reserved = Decimal("0")
            total_available = Decimal("0")

            for row, (batch, product) in enumerate(records):
                summary = get_batch_stock_summary(db, batch)
                physical = summary["physical"]
                reserved = summary["reserved"]
                available = summary["available"]
                status = self.expiry_status(batch.expiry_date)

                # Expired stock must not be presented as available for sale.
                if status == "EXPIRED":
                    available_for_sale = Decimal("0")
                else:
                    available_for_sale = available

                total_physical += physical
                total_reserved += reserved
                total_available += available_for_sale

                values = [
                    product.name or "",
                    product.sku or "",
                    batch.batch_number or "—",
                    str(batch.received_date or "—"),
                    str(batch.expiry_date or "Not specified"),
                    str(batch.received_quantity or 0),
                    str(physical),
                    str(reserved),
                    str(available_for_sale),
                    status,
                    f"{Decimal(str(batch.unit_cost or 0)):.2f}",
                    batch.supplier or "—",
                ]

                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                    if column == 9 and status == "EXPIRED":
                        item.setForeground(Qt.GlobalColor.red)
                    elif column == 9 and status == "Expiring soon":
                        item.setForeground(Qt.GlobalColor.yellow)
                    elif column == 8:
                        item.setForeground(Qt.GlobalColor.green)

                    self.table.setItem(row, column, item)

            self.status.setText(
                f"Active batches: {len(records)}   |   "
                f"Physical remaining: {total_physical}   |   "
                f"Reserved: {total_reserved}   |   "
                f"Available for sale: {total_available}"
            )
        except Exception as error:
            QMessageBox.critical(self, "Inventory Error", str(error))
        finally:
            db.close()

    def open_stock_adjustment(self):
        from stock_adjustment import StockAdjustmentWindow
        self.stock_adjustment_window = StockAdjustmentWindow(user=self.user)
        self.stock_adjustment_window.show()

    def receive_stock(self):
        dialog = ReceiveStockDialog(self)
        if dialog.product.count() == 0:
            QMessageBox.warning(
                self, "No Products",
                "Add an active product before recording opening stock."
            )
            return

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.get_data()
        db = SessionLocal()
        try:
            batch = InventoryBatch(
                product_id=data["product_id"],
                batch_number=data["batch_number"],
                received_date=data["received_date"],
                expiry_date=data["expiry_date"],
                received_quantity=data["quantity"],
                remaining_quantity=data["quantity"],
                unit_cost=data["unit_cost"],
                supplier=data["supplier"],
                notes=data["notes"],
            )
            db.add(batch)
            db.flush()

            movement = StockMovement(
                product_id=data["product_id"],
                batch_id=batch.id,
                movement_type="opening_stock",
                quantity_change=data["quantity"],
                reference_type="opening_stock",
                reference_id=batch.id,
                note=(
                    f"Opening/manual stock: {data['reason']}. "
                    f"{data['notes'] or ''}"
                ).strip(),
            )
            db.add(movement)
            db.flush()

            write_inventory_audit(
                db,
                action="opening_stock_received",
                record_type="InventoryBatch",
                record_id=batch.id,
                old_values={},
                new_values={
                    "product_id": data["product_id"],
                    "batch_number": data["batch_number"],
                    "quantity": str(data["quantity"]),
                    "unit_cost": str(data["unit_cost"]),
                    "expiry_date": str(data["expiry_date"]),
                    "reason": data["reason"],
                    "movement_id": movement.id,
                },
                reason=data["reason"],
            )

            db.commit()
            QMessageBox.information(
                self, "Success",
                "Opening/manual stock recorded successfully."
            )
            self.load_inventory()
        except Exception as error:
            db.rollback()
            QMessageBox.critical(self, "Save Error", str(error))
        finally:
            db.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = InventoryWindow()
    window.show()
    sys.exit(app.exec())
