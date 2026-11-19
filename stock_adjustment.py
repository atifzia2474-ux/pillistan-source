import sys

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QDoubleSpinBox, QTextEdit,
    QMessageBox, QGroupBox, QFormLayout
)

from database import SessionLocal
from models import Product, InventoryBatch
from inventory_stock_service import (
    get_batch_stock_summary,
    adjust_stock,
)
from theme_manager import apply_theme


class StockAdjustmentWindow(QMainWindow):
    def __init__(self, user=None):
        super().__init__()
        self.user = user or {}
        self.setWindowTitle("Pillistan | Stock Adjustment")
        self.resize(900, 700)
        self.setMinimumSize(720, 570)

        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #101827;
                color: #e5e7eb;
                font-size: 14px;
            }
            QGroupBox {
                border: 1px solid #344256;
                border-radius: 10px;
                margin-top: 14px;
                padding: 16px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #34d399;
            }
            QComboBox, QDoubleSpinBox, QTextEdit {
                background: #1e293b;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 9px;
                color: white;
                min-height: 22px;
            }
            QPushButton {
                background: #059669;
                color: white;
                border: none;
                border-radius: 7px;
                padding: 12px 20px;
                font-weight: bold;
            }
            QPushButton:hover { background: #10b981; }
            QPushButton#secondary { background: #334155; }
            QLabel#heading {
                font-size: 25px;
                font-weight: bold;
                color: #34d399;
            }
            QLabel#stock {
                font-size: 16px;
                font-weight: bold;
                color: #34d399;
            }
        """)

        self.build_ui()
        self.load_products()

        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self)

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(18)

        heading = QLabel("Stock Adjustment")
        heading.setObjectName("heading")
        layout.addWidget(heading)

        subtitle = QLabel(
            "Adjust stock with reservation protection and a recorded reason."
        )
        subtitle.setStyleSheet("color: #94a3b8;")
        layout.addWidget(subtitle)

        group = QGroupBox("Adjustment Details")
        form = QFormLayout(group)
        form.setSpacing(15)

        self.product_combo = QComboBox()
        self.product_combo.currentIndexChanged.connect(self.load_batches)
        form.addRow("Product:", self.product_combo)

        self.batch_combo = QComboBox()
        self.batch_combo.currentIndexChanged.connect(self.show_quantity)
        form.addRow("Inventory Batch:", self.batch_combo)

        self.stock_label = QLabel("Physical: — | Reserved: — | Available: —")
        self.stock_label.setObjectName("stock")
        self.stock_label.setWordWrap(True)
        form.addRow("Stock Position:", self.stock_label)

        self.adjustment_combo = QComboBox()
        self.adjustment_combo.addItem("Decrease Stock", "decrease")
        self.adjustment_combo.addItem("Increase Stock", "increase")
        form.addRow("Adjustment Type:", self.adjustment_combo)

        self.reason_combo = QComboBox()
        self.reason_combo.addItems([
            "Damaged",
            "Expired",
            "Physical Stock Correction",
            "Other",
        ])
        form.addRow("Reason:", self.reason_combo)

        self.quantity_input = QDoubleSpinBox()
        self.quantity_input.setRange(0.001, 9999999)
        self.quantity_input.setDecimals(3)
        self.quantity_input.setValue(1)
        form.addRow("Adjustment Quantity:", self.quantity_input)

        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText(
            "Add details, especially for physical corrections or Other."
        )
        self.notes_input.setMaximumHeight(100)
        form.addRow("Notes:", self.notes_input)

        layout.addWidget(group)

        buttons = QHBoxLayout()
        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("secondary")
        refresh_button.clicked.connect(self.load_products)

        save_button = QPushButton("Save Adjustment")
        save_button.clicked.connect(self.save_adjustment)

        buttons.addWidget(refresh_button)
        buttons.addStretch()
        buttons.addWidget(save_button)
        layout.addLayout(buttons)
        layout.addStretch()

    def load_products(self):
        db = SessionLocal()
        self.product_combo.blockSignals(True)
        try:
            self.product_combo.clear()
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
                self.product_combo.addItem(product.name, product.id)
        finally:
            db.close()
            self.product_combo.blockSignals(False)

        self.load_batches()

    def load_batches(self):
        self.batch_combo.blockSignals(True)
        self.batch_combo.clear()
        product_id = self.product_combo.currentData()

        if product_id is None:
            self.batch_combo.blockSignals(False)
            self.stock_label.setText(
                "Physical: — | Reserved: — | Available: —"
            )
            return

        db = SessionLocal()
        try:
            batches = (
                db.query(InventoryBatch)
                .filter(
                    InventoryBatch.product_id == product_id,
                    InventoryBatch.is_active.is_(True),
                )
                .order_by(
                    InventoryBatch.expiry_date.is_(None),
                    InventoryBatch.expiry_date,
                )
                .all()
            )

            for batch in batches:
                summary = get_batch_stock_summary(db, batch)
                label = (
                    f"Batch: {batch.batch_number or 'N/A'} | "
                    f"Physical: {summary['physical']} | "
                    f"Available: {summary['available']}"
                )
                self.batch_combo.addItem(label, batch.id)
        finally:
            db.close()
            self.batch_combo.blockSignals(False)

        self.show_quantity()

    def show_quantity(self):
        batch_id = self.batch_combo.currentData()
        if batch_id is None:
            self.stock_label.setText(
                "Physical: — | Reserved: — | Available: —"
            )
            return

        username = str(self.user.get("username") or "").strip()
        if not username:
            QMessageBox.critical(self, "Authentication Required",
                                 "The authenticated user could not be identified. Please log in again.")
            return

        db = SessionLocal()
        try:
            batch = db.get(InventoryBatch, batch_id)
            if batch:
                summary = get_batch_stock_summary(db, batch)
                self.stock_label.setText(
                    f"Physical remaining: {summary['physical']}   |   "
                    f"Reserved: {summary['reserved']}   |   "
                    f"Unreserved available: {summary['available']}"
                )
            else:
                self.stock_label.setText("Selected batch not found.")
        finally:
            db.close()

    def save_adjustment(self):
        product_id = self.product_combo.currentData()
        batch_id = self.batch_combo.currentData()

        if product_id is None or batch_id is None:
            QMessageBox.warning(
                self, "Missing Information",
                "Please select a product and inventory batch."
            )
            return

        quantity = self.quantity_input.value()
        adjustment = self.adjustment_combo.currentData()
        reason = self.reason_combo.currentText()
        notes = self.notes_input.toPlainText().strip()

        if reason == "Other" and not notes:
            QMessageBox.warning(
                self, "Details Required",
                "Please explain the reason when selecting Other."
            )
            return

        db = SessionLocal()
        try:
            batch = db.get(InventoryBatch, batch_id)
            if not batch or batch.product_id != product_id:
                raise ValueError("The selected inventory batch was not found.")

            adjust_stock(
                session=db,
                batch_id=batch_id,
                adjustment=adjustment,
                quantity=quantity,
                reason=reason,
                notes=notes,
                username=username,
                changed_by_id=self.user.get("id"),
            )

            db.commit()
            QMessageBox.information(
                self, "Success",
                "Stock adjustment and audit record saved successfully."
            )
            self.notes_input.clear()
            self.load_batches()

        except Exception as error:
            db.rollback()
            QMessageBox.critical(
                self, "Adjustment Not Saved", str(error)
            )
        finally:
            db.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = StockAdjustmentWindow()
    window.show()
    sys.exit(app.exec())
