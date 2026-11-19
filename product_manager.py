from decimal import Decimal

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QTableWidget,
    QTableWidgetItem, QDialog, QFormLayout, QDoubleSpinBox,
    QComboBox, QMessageBox, QHeaderView, QCheckBox,
    QPlainTextEdit
)
from PySide6.QtCore import Qt

from database import SessionLocal
from models import Product
from theme_manager import apply_theme


class ProductForm(QDialog):
    def __init__(self, product=None, parent=None, categories=None):
        super().__init__(parent)

        self.product = product
        self.setWindowTitle("Edit Product" if product else "Add New Product")
        self.setMinimumWidth(520)
        self.setMinimumHeight(570)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self.sku = QLineEdit()
        self.sku.setPlaceholderText("Enter a unique product SKU")

        self.name = QLineEdit()
        self.name.setPlaceholderText("Enter product name")

        self.brand = QLineEdit()
        self.brand.setPlaceholderText("Brand or manufacturer")

        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.category.setPlaceholderText("Select or enter a category")
        self.category.addItems(sorted(set(categories or []), key=str.lower))

        self.barcode = QLineEdit()
        self.barcode.setPlaceholderText("Enter product barcode (optional)")

        self.unit = QComboBox()
        self.unit.setEditable(True)
        self.unit.addItems([
            "unit", "box", "bottle", "pack", "piece",
            "kg", "gram", "ml", "litre", "tablet", "capsule", "sachet"
        ])

        self.purchase_price = QDoubleSpinBox()
        self.purchase_price.setRange(0, 999999999)
        self.purchase_price.setDecimals(2)
        self.purchase_price.setPrefix("PKR ")

        self.selling_price = QDoubleSpinBox()
        self.selling_price.setRange(0, 999999999)
        self.selling_price.setDecimals(2)
        self.selling_price.setPrefix("PKR ")

        self.description = QPlainTextEdit()
        self.description.setPlaceholderText(
            "Optional product details, ingredients, size or other notes..."
        )
        self.description.setMaximumHeight(100)

        form.addRow("SKU *", self.sku)
        form.addRow("Product Name *", self.name)
        form.addRow("Brand", self.brand)
        form.addRow("Category", self.category)
        form.addRow("Barcode", self.barcode)
        form.addRow("Unit", self.unit)
        form.addRow("Purchase Price", self.purchase_price)
        form.addRow("Selling Price", self.selling_price)
        form.addRow("Description", self.description)

        layout.addLayout(form)

        buttons = QHBoxLayout()
        save_button = QPushButton("Save Product")
        save_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(save_button)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)

        if product:
            self.sku.setText(product.sku or "")
            self.name.setText(product.name or "")
            self.brand.setText(product.brand or "")
            self.category.setCurrentText(product.category or "")
            self.barcode.setText(product.barcode or "")

            current_unit = product.unit or "unit"
            if self.unit.findText(current_unit) < 0:
                self.unit.addItem(current_unit)
            self.unit.setCurrentText(current_unit)

            self.purchase_price.setValue(float(product.purchase_price or 0))
            self.selling_price.setValue(float(product.selling_price or 0))
            self.description.setPlainText(product.description or "")

    def get_data(self):
        return {
            "sku": self.sku.text().strip().upper(),
            "name": self.name.text().strip(),
            "brand": self.brand.text().strip() or None,
            "category": self.category.currentText().strip() or None,
            "barcode": self.barcode.text().strip() or None,
            "unit": self.unit.currentText().strip() or "unit",
            "purchase_price": Decimal(str(self.purchase_price.value())),
            "selling_price": Decimal(str(self.selling_price.value())),
            "description": self.description.toPlainText().strip() or None,
        }


class ProductManager(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Pillistan - Product Management")
        self.resize(1250, 720)

        self.setStyleSheet("""
            QWidget {
                background-color: #f4f7f5;
                color: #24352c;
                font-family: Arial;
                font-size: 13px;
            }
            QLineEdit, QComboBox, QDoubleSpinBox, QPlainTextEdit {
                background: white;
                padding: 7px;
                border: 1px solid #d5ded8;
                border-radius: 5px;
            }
            QPushButton {
                background-color: #164b37;
                color: white;
                padding: 9px 14px;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #28664d;
            }
            QTableWidget {
                background: white;
                gridline-color: #e5ebe7;
                border: 1px solid #d5ded8;
            }
            QHeaderView::section {
                background: #164b37;
                color: white;
                padding: 8px;
                border: none;
            }
        """)

        self.build_interface()
        self.load_categories()
        self.load_products()

        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self)

    def build_interface(self):
        main = QVBoxLayout(self)

        heading = QLabel("Product Management")
        heading.setStyleSheet(
            "font-size: 25px; font-weight: bold; color: #164b37;"
        )
        main.addWidget(heading)

        main.addWidget(QLabel(
            "Manage your Pillistan product catalogue, pricing and product details."
        ))

        filters = QHBoxLayout()

        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Search by product name, SKU, brand, barcode or category..."
        )
        self.search.textChanged.connect(self.load_products)
        filters.addWidget(self.search, 3)

        self.category_filter = QComboBox()
        self.category_filter.addItem("All Categories", None)
        self.category_filter.currentIndexChanged.connect(self.load_products)
        filters.addWidget(self.category_filter, 1)

        self.status_filter = QComboBox()
        self.status_filter.addItem("All Statuses", "all")
        self.status_filter.addItem("Active", "active")
        self.status_filter.addItem("Inactive", "inactive")
        self.status_filter.addItem("Archived", "archived")
        self.status_filter.currentIndexChanged.connect(self.load_products)
        filters.addWidget(self.status_filter, 1)

        main.addLayout(filters)

        actions = QHBoxLayout()

        add_button = QPushButton("Add Product")
        add_button.clicked.connect(self.add_product)
        actions.addWidget(add_button)

        edit_button = QPushButton("Edit Selected")
        edit_button.clicked.connect(self.edit_product)
        actions.addWidget(edit_button)

        self.status_button = QPushButton("Activate / Deactivate")
        self.status_button.clicked.connect(self.toggle_active)
        actions.addWidget(self.status_button)

        self.archive_button = QPushButton("Archive / Restore")
        self.archive_button.clicked.connect(self.toggle_archive)
        actions.addWidget(self.archive_button)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_all)
        actions.addWidget(refresh_button)

        main.addLayout(actions)

        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "SKU", "Product Name", "Brand", "Category", "Barcode",
            "Unit", "Purchase Price", "Selling Price", "Status"
        ])
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        main.addWidget(self.table)

        self.status = QLabel("Ready")
        main.addWidget(self.status)

    def load_categories(self):
        current = self.category_filter.currentData()

        with SessionLocal() as db:
            categories = (
                db.query(Product.category)
                .filter(Product.category.isnot(None), Product.category != "")
                .distinct()
                .order_by(Product.category)
                .all()
            )

        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("All Categories", None)

        for row in categories:
            self.category_filter.addItem(row[0], row[0])

        index = self.category_filter.findData(current)
        if index >= 0:
            self.category_filter.setCurrentIndex(index)

        self.category_filter.blockSignals(False)

    def refresh_all(self):
        self.load_categories()
        self.load_products()

    def product_status(self, product):
        if product.is_archived:
            return "Archived"
        if not product.is_active:
            return "Inactive"
        return "Active"

    def load_products(self):
        search_text = self.search.text().strip()
        selected_category = self.category_filter.currentData()
        selected_status = self.status_filter.currentData()

        with SessionLocal() as db:
            query = db.query(Product)

            if selected_status == "active":
                query = query.filter(
                    Product.is_active == True,
                    Product.is_archived == False
                )
            elif selected_status == "inactive":
                query = query.filter(
                    Product.is_active == False,
                    Product.is_archived == False
                )
            elif selected_status == "archived":
                query = query.filter(Product.is_archived == True)

            if selected_category:
                query = query.filter(Product.category == selected_category)

            if search_text:
                pattern = f"%{search_text}%"
                query = query.filter(
                    Product.name.ilike(pattern)
                    | Product.sku.ilike(pattern)
                    | Product.brand.ilike(pattern)
                    | Product.barcode.ilike(pattern)
                    | Product.category.ilike(pattern)
                )

            products = query.order_by(Product.name).all()

            self.table.setRowCount(len(products))

            for row, product in enumerate(products):
                values = [
                    product.sku or "",
                    product.name or "",
                    product.brand or "",
                    product.category or "",
                    product.barcode or "",
                    product.unit or "",
                    f"PKR {product.purchase_price or 0:,.2f}",
                    f"PKR {product.selling_price or 0:,.2f}",
                    self.product_status(product),
                ]

                for col, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignVCenter
                        | Qt.AlignmentFlag.AlignLeft
                    )
                    self.table.setItem(row, col, item)

                self.table.item(row, 0).setData(
                    Qt.ItemDataRole.UserRole, product.id
                )

            self.status.setText(
                f"Products displayed: {len(products)}"
            )

    def selected_product_id(self):
        row = self.table.currentRow()

        if row < 0:
            QMessageBox.warning(
                self, "No Selection", "Please select a product first."
            )
            return None

        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def get_categories(self):
        with SessionLocal() as db:
            return [
                row[0] for row in db.query(Product.category)
                .filter(Product.category.isnot(None), Product.category != "")
                .distinct()
                .all()
            ]

    def validate_unique_fields(self, db, data, product_id=None):
        sku_query = db.query(Product).filter(Product.sku == data["sku"])
        if product_id is not None:
            sku_query = sku_query.filter(Product.id != product_id)

        if sku_query.first():
            QMessageBox.warning(
                self, "Duplicate SKU",
                "This SKU is already assigned to another product."
            )
            return False

        if data["barcode"]:
            barcode_query = db.query(Product).filter(
                Product.barcode == data["barcode"]
            )
            if product_id is not None:
                barcode_query = barcode_query.filter(
                    Product.id != product_id
                )

            if barcode_query.first():
                QMessageBox.warning(
                    self, "Duplicate Barcode",
                    "This barcode is already assigned to another product."
                )
                return False

        return True

    def add_product(self):
        dialog = ProductForm(parent=self, categories=self.get_categories())

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.get_data()

        if not data["sku"] or not data["name"]:
            QMessageBox.warning(
                self, "Missing Information",
                "SKU and Product Name are required."
            )
            return

        try:
            with SessionLocal() as db:
                if not self.validate_unique_fields(db, data):
                    return

                db.add(Product(**data))
                db.commit()

            self.refresh_all()
            QMessageBox.information(
                self, "Success", "Product added successfully."
            )

        except Exception as error:
            QMessageBox.critical(
                self, "Database Error",
                f"The product could not be saved.\n\n{error}"
            )

    def edit_product(self):
        product_id = self.selected_product_id()
        if product_id is None:
            return

        try:
            with SessionLocal() as db:
                product = db.get(Product, product_id)

                if not product:
                    QMessageBox.warning(
                        self, "Not Found", "Product no longer exists."
                    )
                    return

                dialog = ProductForm(
                    product, self, categories=self.get_categories()
                )

                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return

                data = dialog.get_data()

                if not data["sku"] or not data["name"]:
                    QMessageBox.warning(
                        self, "Missing Information",
                        "SKU and Product Name are required."
                    )
                    return

                if not self.validate_unique_fields(db, data, product_id):
                    return

                for key, value in data.items():
                    setattr(product, key, value)

                db.commit()

            self.refresh_all()
            QMessageBox.information(
                self, "Success", "Product updated successfully."
            )

        except Exception as error:
            QMessageBox.critical(
                self, "Database Error",
                f"The product could not be updated.\n\n{error}"
            )

    def toggle_active(self):
        product_id = self.selected_product_id()
        if product_id is None:
            return

        try:
            with SessionLocal() as db:
                product = db.get(Product, product_id)

                if not product:
                    QMessageBox.warning(
                        self, "Not Found", "Product no longer exists."
                    )
                    return

                if product.is_archived:
                    QMessageBox.warning(
                        self, "Archived Product",
                        "Restore this product before activating it."
                    )
                    return

                new_status = not product.is_active
                action = "activate" if new_status else "deactivate"

                answer = QMessageBox.question(
                    self, "Confirm Status Change",
                    f"Are you sure you want to {action} "
                    f"'{product.name}'?"
                )

                if answer != QMessageBox.StandardButton.Yes:
                    return

                product.is_active = new_status
                db.commit()

            self.load_products()
            QMessageBox.information(
                self, "Success", f"Product {action}d successfully."
            )

        except Exception as error:
            QMessageBox.critical(
                self, "Database Error",
                f"Status could not be changed.\n\n{error}"
            )

    def toggle_archive(self):
        product_id = self.selected_product_id()
        if product_id is None:
            return

        try:
            with SessionLocal() as db:
                product = db.get(Product, product_id)

                if not product:
                    QMessageBox.warning(
                        self, "Not Found", "Product no longer exists."
                    )
                    return

                restoring = bool(product.is_archived)
                action = "restore" if restoring else "archive"

                answer = QMessageBox.question(
                    self, "Confirm Action",
                    f"Are you sure you want to {action} "
                    f"'{product.name}'?"
                )

                if answer != QMessageBox.StandardButton.Yes:
                    return

                if restoring:
                    product.is_archived = False
                    product.is_active = True
                else:
                    product.is_archived = True
                    product.is_active = False

                db.commit()

            self.refresh_all()
            QMessageBox.information(
                self, "Success",
                f"Product {action}d successfully."
            )

        except Exception as error:
            QMessageBox.critical(
                self, "Database Error",
                f"Archive status could not be changed.\n\n{error}"
            )
