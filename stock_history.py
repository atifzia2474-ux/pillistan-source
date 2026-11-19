
import sys

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTableWidget, QTableWidgetItem, QMessageBox,
    QHeaderView
)
from PySide6.QtCore import Qt

from database import SessionLocal
from models import Product, InventoryBatch, StockMovement
from theme_manager import apply_theme


class StockHistoryWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Pillistan | Stock Movement History")
        self.resize(1150, 700)
        self.setMinimumSize(850, 550)

        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #101827;
                color: #e5e7eb;
                font-size: 13px;
            }
            QLabel#heading {
                color: #34d399;
                font-size: 25px;
                font-weight: bold;
            }
            QLineEdit {
                background: #1e293b;
                border: 1px solid #475569;
                border-radius: 7px;
                padding: 10px;
                color: white;
            }
            QPushButton {
                background: #059669;
                color: white;
                border: none;
                border-radius: 7px;
                padding: 10px 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #10b981;
            }
            QTableWidget {
                background: #172235;
                alternate-background-color: #1e293b;
                border: 1px solid #344256;
                gridline-color: #344256;
                color: #e5e7eb;
                selection-background-color: #065f46;
            }
            QHeaderView::section {
                background: #263449;
                color: #34d399;
                padding: 10px;
                border: none;
                font-weight: bold;
            }
        """)

        self.build_ui()
        self.load_movements()
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self)

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(16)

        heading = QLabel("Stock Movement History")
        heading.setObjectName("heading")
        layout.addWidget(heading)

        subtitle = QLabel(
            "Review stock receipts, adjustments and inventory transactions."
        )
        subtitle.setStyleSheet("color: #94a3b8;")
        layout.addWidget(subtitle)

        search_row = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Search by product, SKU, batch or movement type..."
        )
        self.search_input.textChanged.connect(self.filter_table)

        refresh_button = QPushButton("Refresh History")
        refresh_button.clicked.connect(self.load_movements)

        search_row.addWidget(self.search_input)
        search_row.addWidget(refresh_button)

        layout.addLayout(search_row)

        self.summary_label = QLabel("Total records: 0")
        self.summary_label.setStyleSheet(
            "color: #34d399; font-weight: bold;"
        )
        layout.addWidget(self.summary_label)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Date",
            "Product",
            "SKU",
            "Batch",
            "Movement Type",
            "Quantity Change",
            "Reference",
            "Notes"
        ])

        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(self.table)

        self.all_rows = []

    def load_movements(self):
        db = SessionLocal()

        try:
            records = (
                db.query(StockMovement, Product, InventoryBatch)
                .join(
                    Product,
                    StockMovement.product_id == Product.id
                )
                .outerjoin(
                    InventoryBatch,
                    StockMovement.batch_id == InventoryBatch.id
                )
                .order_by(StockMovement.id.desc())
                .all()
            )

            self.all_rows = []

            for movement, product, batch in records:
                date_value = (
                    movement.created_at.strftime("%Y-%m-%d %H:%M")
                    if movement.created_at else ""
                )

                batch_number = (
                    batch.batch_number if batch else "—"
                )

                self.all_rows.append([
                    date_value,
                    product.name,
                    product.sku,
                    batch_number or "—",
                    movement.movement_type,
                    str(movement.quantity_change),
                    (
                        f"{movement.reference_type or ''} "
                        f"{movement.reference_id or ''}"
                    ).strip(),
                    movement.note or ""
                ])

            self.populate_table(self.all_rows)

        except Exception as error:
            QMessageBox.critical(
                self,
                "Database Error",
                str(error)
            )

        finally:
            db.close()

    def populate_table(self, rows):
        self.table.setRowCount(len(rows))

        for row_index, row_data in enumerate(rows):
            for column_index, value in enumerate(row_data):
                item = QTableWidgetItem(str(value))
                item.setFlags(
                    item.flags()
                    & ~Qt.ItemFlag.ItemIsEditable
                )

                if column_index == 5:
                    if str(value).startswith("-"):
                        item.setForeground(
                            Qt.GlobalColor.red
                        )
                    else:
                        item.setForeground(
                            Qt.GlobalColor.green
                        )

                self.table.setItem(
                    row_index,
                    column_index,
                    item
                )

        self.summary_label.setText(
            f"Total records: {len(rows)}"
        )

    def filter_table(self):
        search = self.search_input.text().strip().lower()

        if not search:
            self.populate_table(self.all_rows)
            return

        filtered = [
            row for row in self.all_rows
            if any(search in str(value).lower() for value in row)
        ]

        self.populate_table(filtered)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = StockHistoryWindow()
    window.show()
    sys.exit(app.exec())
