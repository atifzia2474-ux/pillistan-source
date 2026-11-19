from decimal import Decimal
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QDoubleSpinBox,
    QTableWidget, QTableWidgetItem, QMessageBox, QGroupBox,
    QHeaderView, QAbstractItemView, QScrollArea
)
from PySide6.QtCore import Qt

from database import SessionLocal
from models import Product, Customer
from orders_models import SalesOrder, SalesOrderItem
from order_fulfilment_service import confirm_order
from orders_service import (
    get_or_create_customer,
    find_customer_by_phone,
    find_possible_duplicate_orders,
    create_draft_order,
)


class OrdersManager(QWidget):
    def __init__(self, session_factory=None):
        super().__init__()
        self.session_factory = session_factory or SessionLocal
        self.cart = []
        self.products = []

        self.setStyleSheet("""
            QWidget {
                background-color: #f4f7f5;
                color: #24352c;
                font-family: Segoe UI;
                font-size: 13px;
            }

            QLabel {
                background: transparent;
                color: #24352c;
            }

            QGroupBox {
                background-color: white;
                color: #24352c;
                border: 1px solid #d5ded8;
                border-radius: 7px;
                margin-top: 14px;
                padding: 14px 10px 10px 10px;
                font-weight: bold;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 2px 7px;
                color: #164b37;
                background-color: white;
            }

            QLineEdit, QComboBox, QDoubleSpinBox {
                background-color: white;
                color: #24352c;
                selection-background-color: #dcebe1;
                selection-color: #24352c;
                border: 1px solid #d5ded8;
                border-radius: 5px;
                padding: 7px;
                min-height: 20px;
            }

            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {
                border: 2px solid #164b37;
            }

            QLineEdit:disabled, QComboBox:disabled,
            QDoubleSpinBox:disabled {
                background-color: #eaf0ec;
                color: #718078;
            }

            QComboBox QAbstractItemView {
                background-color: white;
                color: #24352c;
                selection-background-color: #dcebe1;
                selection-color: #24352c;
                border: 1px solid #d5ded8;
                outline: none;
            }

            QPushButton {
                background-color: #164b37;
                color: white;
                padding: 9px 14px;
                border: none;
                border-radius: 5px;
                font-weight: bold;
            }

            QPushButton:hover {
                background-color: #28664d;
                color: white;
            }

            QPushButton:pressed {
                background-color: #21664b;
                color: white;
            }

            QPushButton:disabled {
                background-color: #d5ded8;
                color: #718078;
            }

            QTableWidget {
                background-color: white;
                color: #24352c;
                alternate-background-color: #f4f7f5;
                selection-background-color: #dcebe1;
                selection-color: #24352c;
                gridline-color: #e5ebe7;
                border: 1px solid #d5ded8;
                border-radius: 5px;
            }

            QTableWidget::item {
                color: #24352c;
                padding: 5px;
            }

            QTableWidget::item:selected {
                background-color: #dcebe1;
                color: #24352c;
            }

            QHeaderView::section {
                background-color: #164b37;
                color: white;
                padding: 8px;
                border: none;
                font-weight: bold;
            }

            QScrollBar:vertical, QScrollBar:horizontal {
                background-color: #f4f7f5;
                border: none;
            }

            QToolTip {
                background-color: white;
                color: #24352c;
                border: 1px solid #d5ded8;
                padding: 4px;
            }
        """)

        self.build_interface()
        self.refresh_products()
        self.refresh_orders()

    def build_interface(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setMinimumWidth(760)
        root = QVBoxLayout(content)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(18)

        heading = QLabel("Orders Management")
        heading.setStyleSheet(
            "font-size: 27px; font-weight: bold; color: #164b37;"
        )
        root.addWidget(heading)

        subtitle = QLabel(
            "Create customer orders, select products and prepare order confirmations."
        )
        root.addWidget(subtitle)

        main_row = QHBoxLayout()
        main_row.setSpacing(22)

        # Customer and delivery information
        left = QVBoxLayout()
        left.setSpacing(15)

        customer_group = QGroupBox("Customer Information")
        customer_form = QFormLayout(customer_group)
        customer_form.setRowWrapPolicy(
            QFormLayout.RowWrapPolicy.WrapLongRows
        )
        customer_form.setHorizontalSpacing(12)
        customer_form.setVerticalSpacing(12)
        customer_group.setMinimumHeight(175)

        self.customer_name = QLineEdit()
        self.customer_name.setPlaceholderText("Customer full name")

        self.customer_phone = QLineEdit()
        self.customer_phone.setPlaceholderText("03XXXXXXXXX")

        self.customer_whatsapp = QLineEdit()
        self.customer_whatsapp.setPlaceholderText("Optional WhatsApp number")

        self.customer_status = QLabel("Enter a phone number to check existing customers.")
        self.customer_status.setWordWrap(True)
        self.customer_status.setStyleSheet("color: #718078;")

        self.customer_phone.editingFinished.connect(self.check_customer)

        customer_form.addRow("Customer name *", self.customer_name)
        customer_form.addRow("Mobile number *", self.customer_phone)
        customer_form.addRow("WhatsApp number", self.customer_whatsapp)
        customer_form.addRow("Customer match", self.customer_status)

        left.addWidget(customer_group)

        delivery_group = QGroupBox("Delivery Information")
        delivery_form = QFormLayout(delivery_group)
        delivery_form.setRowWrapPolicy(
            QFormLayout.RowWrapPolicy.WrapLongRows
        )
        delivery_form.setHorizontalSpacing(12)
        delivery_form.setVerticalSpacing(12)
        delivery_group.setMinimumHeight(175)

        self.province = QComboBox()
        self.province.addItems([
            "", "Punjab", "Sindh", "Khyber Pakhtunkhwa",
            "Balochistan", "Islamabad Capital Territory",
            "Azad Jammu and Kashmir", "Gilgit-Baltistan"
        ])

        self.city = QLineEdit()
        self.city.setPlaceholderText("City")

        self.address = QLineEdit()
        self.address.setPlaceholderText("Complete delivery address")

        self.instructions = QLineEdit()
        self.instructions.setPlaceholderText("Optional delivery instructions")

        delivery_form.addRow("Province", self.province)
        delivery_form.addRow("City", self.city)
        delivery_form.addRow("Address *", self.address)
        delivery_form.addRow("Instructions", self.instructions)

        left.addWidget(delivery_group)

        payment_group = QGroupBox("Payment and Charges")
        payment_form = QFormLayout(payment_group)
        payment_form.setRowWrapPolicy(
            QFormLayout.RowWrapPolicy.WrapLongRows
        )
        payment_form.setHorizontalSpacing(12)
        payment_form.setVerticalSpacing(12)
        payment_group.setMinimumHeight(150)

        self.payment_method = QComboBox()
        self.payment_method.addItem("Cash on Delivery (COD)", "cod")
        self.payment_method.addItem("Cash", "cash")
        self.payment_method.addItem("Bank Transfer", "bank_transfer")
        self.payment_method.addItem("Easypaisa", "easypaisa")
        self.payment_method.addItem("JazzCash", "jazzcash")
        self.payment_method.addItem("Other", "other")

        self.delivery_charge = QDoubleSpinBox()
        self.delivery_charge.setRange(0, 999999999)
        self.delivery_charge.setDecimals(2)
        self.delivery_charge.setPrefix("PKR ")

        self.discount = QDoubleSpinBox()
        self.discount.setRange(0, 999999999)
        self.discount.setDecimals(2)
        self.discount.setPrefix("PKR ")

        payment_form.addRow("Payment method", self.payment_method)
        payment_form.addRow("Customer delivery charge", self.delivery_charge)
        payment_form.addRow("Order discount", self.discount)

        left.addWidget(payment_group)
        left.addStretch()

        # Product selection and order items
        right = QVBoxLayout()
        right.setSpacing(15)

        product_group = QGroupBox("Add Products")
        product_layout = QGridLayout(product_group)
        product_group.setMinimumHeight(125)
        product_layout.setHorizontalSpacing(12)
        product_layout.setVerticalSpacing(12)

        self.product_selector = QComboBox()
        self.product_selector.setMinimumWidth(220)

        self.quantity = QDoubleSpinBox()
        self.quantity.setRange(0.001, 1000000)
        self.quantity.setDecimals(3)
        self.quantity.setValue(1)

        self.add_item_button = QPushButton("Add Product")
        self.add_item_button.clicked.connect(self.add_product)

        product_layout.addWidget(QLabel("Product"), 0, 0)
        product_layout.addWidget(self.product_selector, 0, 1)
        product_layout.addWidget(QLabel("Quantity"), 1, 0)
        product_layout.addWidget(self.quantity, 1, 1)
        product_layout.addWidget(self.add_item_button, 2, 0, 1, 2)

        right.addWidget(product_group)

        self.cart_table = QTableWidget(0, 5)
        self.cart_table.setMinimumHeight(155)
        self.cart_table.setHorizontalHeaderLabels([
            "Product", "SKU", "Quantity", "Unit Price", "Line Total"
        ])
        cart_header = self.cart_table.horizontalHeader()
        cart_header.setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        cart_header.setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for column, width in {
            1: 95, 2: 95, 3: 115, 4: 125
        }.items():
            self.cart_table.setColumnWidth(column, width)
        self.cart_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.cart_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        right.addWidget(self.cart_table, 1)

        cart_actions = QHBoxLayout()
        self.remove_item_button = QPushButton("Remove Selected")
        self.remove_item_button.clicked.connect(self.remove_selected_item)
        cart_actions.addWidget(self.remove_item_button)
        cart_actions.addStretch()
        right.addLayout(cart_actions)

        self.subtotal_label = QLabel("Subtotal: PKR 0.00")
        self.discount_label = QLabel("Discount: PKR 0.00")
        self.delivery_label = QLabel("Delivery: PKR 0.00")
        self.total_label = QLabel("Order Total: PKR 0.00")
        self.total_label.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #164b37;"
        )

        right.addWidget(self.subtotal_label)
        right.addWidget(self.discount_label)
        right.addWidget(self.delivery_label)
        right.addWidget(self.total_label)

        self.delivery_charge.valueChanged.connect(self.update_totals)
        self.discount.valueChanged.connect(self.update_totals)

        main_row.addLayout(left, 1)
        main_row.addLayout(right, 1)
        root.addLayout(main_row, 1)

        action_row = QHBoxLayout()
        action_row.addStretch()

        self.save_button = QPushButton("Save Draft Order")
        self.save_button.setMinimumWidth(180)
        self.save_button.clicked.connect(self.save_order)
        action_row.addWidget(self.save_button)

        root.addLayout(action_row)

        recent_heading = QLabel("Recent Orders")
        recent_heading.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #164b37;"
        )
        root.addWidget(recent_heading)

        self.orders_table = QTableWidget(0, 5)
        self.orders_table.setHorizontalHeaderLabels([
            "Order Number", "Customer", "Date", "Status", "Total (PKR)"
        ])
        orders_header = self.orders_table.horizontalHeader()
        orders_header.setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        orders_header.setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        for column, width in {
            0: 155, 2: 110, 3: 105, 4: 130
        }.items():
            self.orders_table.setColumnWidth(column, width)
        self.orders_table.setMinimumHeight(140)
        self.orders_table.setMaximumHeight(220)
        self.orders_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.orders_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )

        root.addWidget(self.orders_table)

        order_actions = QHBoxLayout()
        self.confirm_order_button = QPushButton("Confirm Selected Order")
        self.confirm_order_button.clicked.connect(
            self.confirm_selected_order
        )
        self.refresh_orders_button = QPushButton("Refresh Orders")
        self.refresh_orders_button.clicked.connect(self.refresh_orders)

        order_actions.addWidget(self.confirm_order_button)
        order_actions.addWidget(self.refresh_orders_button)
        order_actions.addStretch()
        root.addLayout(order_actions)

        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

    def refresh_products(self):
        session = self.session_factory()
        try:
            self.products = (
                session.query(Product)
                .filter(
                    Product.is_active.is_(True),
                    Product.is_archived.is_(False)
                )
                .order_by(Product.name)
                .all()
            )

            self.product_selector.clear()
            for product in self.products:
                label = f"{product.name} | {product.sku} | PKR {product.selling_price}"
                self.product_selector.addItem(label, product.id)

            if not self.products:
                self.product_selector.addItem("No active products available", None)
        except Exception as error:
            QMessageBox.warning(
                self, "Products Could Not Load",
                f"Unable to load the product catalogue.\n\n{error}"
            )
        finally:
            session.close()

    def refresh_orders(self):
        session = self.session_factory()
        try:
            orders = (
                session.query(SalesOrder)
                .order_by(SalesOrder.created_at.desc())
                .limit(100)
                .all()
            )

            self.orders_table.setRowCount(0)
            for order in orders:
                row = self.orders_table.rowCount()
                self.orders_table.insertRow(row)
                values = [
                    order.order_number,
                    order.customer_name,
                    order.order_date.strftime("%d-%m-%Y") if order.order_date else "",
                    order.order_status,
                    f"{order.total_amount:,.2f}",
                ]
                for column, value in enumerate(values):
                    cell = QTableWidgetItem(str(value))
                    if column == 0:
                        cell.setData(Qt.ItemDataRole.UserRole, order.id)
                    self.orders_table.setItem(row, column, cell)
        except Exception as error:
            QMessageBox.warning(
                self, "Orders Could Not Load",
                f"Unable to load recent orders.\n\n{error}"
            )
        finally:
            session.close()


    def confirm_selected_order(self):
        row = self.orders_table.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, "Select Order",
                "Select a draft order from the table first."
            )
            return

        first_cell = self.orders_table.item(row, 0)
        order_id = (
            first_cell.data(Qt.ItemDataRole.UserRole)
            if first_cell else None
        )
        if order_id is None:
            QMessageBox.warning(
                self, "Order Not Found",
                "The selected order could not be identified."
            )
            return

        answer = QMessageBox.question(
            self,
            "Confirm Order and Reserve Stock",
            "Confirm this order?\n\n"
            "Pillistan will reserve eligible stock using FEFO "
            "(earliest expiry first). Physical stock will NOT be "
            "deducted until courier handover.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        session = self.session_factory()
        try:
            order = confirm_order(session, order_id)
            order_number = order.order_number
            session.commit()

            self.refresh_orders()
            QMessageBox.information(
                self,
                "Order Confirmed",
                f"Order {order_number} has been confirmed and stock reserved.\n\n"
                "Physical inventory remains unchanged until the parcel "
                "is handed to the courier."
            )
        except Exception as error:
            session.rollback()
            QMessageBox.critical(
                self,
                "Order Confirmation Failed",
                f"The order was not confirmed.\n\n{error}"
            )
        finally:
            session.close()

    def check_customer(self):
        phone = self.customer_phone.text().strip()
        if not phone:
            return

        session = self.session_factory()
        try:
            customer = find_customer_by_phone(session, phone)
            if customer:
                self.customer_status.setText(
                    f"Existing customer: {customer.customer_code or customer.id} — "
                    f"{customer.name}"
                )
                self.customer_status.setStyleSheet("color: #164b37; font-weight: bold;")

                if not self.customer_name.text().strip():
                    self.customer_name.setText(customer.name)
                if not self.city.text().strip() and customer.city:
                    self.city.setText(customer.city)
                if not self.address.text().strip() and customer.address:
                    self.address.setText(customer.address)
                if not self.customer_whatsapp.text().strip():
                    self.customer_whatsapp.setText(customer.phone or "")
            else:
                self.customer_status.setText(
                    "No exact phone match. A new customer record will be created when saved."
                )
                self.customer_status.setStyleSheet("color: #718078;")
        except Exception as error:
            self.customer_status.setText(str(error))
            self.customer_status.setStyleSheet("color: #a33;")
        finally:
            session.close()

    def add_product(self):
        product_id = self.product_selector.currentData()
        if product_id is None:
            QMessageBox.information(
                self, "No Products", "Add an active product before creating an order."
            )
            return

        session = self.session_factory()
        try:
            product = session.get(Product, int(product_id))
            if not product or not product.is_active or product.is_archived:
                QMessageBox.warning(
                    self, "Product Unavailable",
                    "This product is no longer active. Refresh the product list."
                )
                self.refresh_products()
                return

            quantity = Decimal(str(self.quantity.value()))
            unit_price = Decimal(str(product.selling_price or 0))

            existing = next(
                (item for item in self.cart if item["product_id"] == product.id),
                None
            )
            if existing:
                existing["quantity"] += quantity
            else:
                self.cart.append({
                    "product_id": product.id,
                    "name": product.name,
                    "sku": product.sku or "",
                    "quantity": quantity,
                    "unit_price": unit_price,
                })

            self.refresh_cart()
        finally:
            session.close()

    def refresh_cart(self):
        self.cart_table.setRowCount(0)

        for item in self.cart:
            row = self.cart_table.rowCount()
            self.cart_table.insertRow(row)
            line_total = item["quantity"] * item["unit_price"]
            values = [
                item["name"],
                item["sku"],
                f'{item["quantity"]:,.3f}'.rstrip("0").rstrip("."),
                f'{item["unit_price"]:,.2f}',
                f'{line_total:,.2f}',
            ]
            for column, value in enumerate(values):
                self.cart_table.setItem(
                    row, column, QTableWidgetItem(str(value))
                )

        self.update_totals()

    def remove_selected_item(self):
        row = self.cart_table.currentRow()
        if row < 0 or row >= len(self.cart):
            return
        self.cart.pop(row)
        self.refresh_cart()

    def update_totals(self):
        subtotal = sum(
            (item["quantity"] * item["unit_price"] for item in self.cart),
            Decimal("0.00")
        )
        discount = Decimal(str(self.discount.value()))
        delivery = Decimal(str(self.delivery_charge.value()))
        total = subtotal - discount + delivery

        self.subtotal_label.setText(f"Subtotal: PKR {subtotal:,.2f}")
        self.discount_label.setText(f"Discount: PKR {discount:,.2f}")
        self.delivery_label.setText(f"Delivery: PKR {delivery:,.2f}")
        self.total_label.setText(f"Order Total: PKR {total:,.2f}")

    def save_order(self):
        if not self.cart:
            QMessageBox.warning(
                self, "No Products", "Please add at least one product."
            )
            return

        if not self.customer_name.text().strip():
            QMessageBox.warning(
                self, "Customer Required", "Please enter the customer's name."
            )
            return

        if not self.customer_phone.text().strip():
            QMessageBox.warning(
                self, "Phone Required", "Please enter the customer's mobile number."
            )
            return

        if not self.address.text().strip():
            QMessageBox.warning(
                self, "Address Required", "Please enter the delivery address."
            )
            return

        if self.discount.value() > float(
            sum(
                item["quantity"] * item["unit_price"] for item in self.cart
            )
        ):
            QMessageBox.warning(
                self, "Invalid Discount",
                "The discount cannot exceed the products subtotal."
            )
            return

        session = self.session_factory()
        try:
            customer, created = get_or_create_customer(
                session,
                name=self.customer_name.text().strip(),
                phone=self.customer_phone.text().strip(),
            )

            duplicates = find_possible_duplicate_orders(session, customer.id)
            if duplicates:
                latest = duplicates[0]
                answer = QMessageBox.warning(
                    self,
                    "Possible Duplicate Order",
                    f"This customer has a recent order:\n\n"
                    f"{latest.order_number} — {latest.order_status}\n\n"
                    "Do you still want to proceed?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    session.rollback()
                    return

            items = [
                {
                    "product_id": item["product_id"],
                    "quantity": item["quantity"],
                    "unit_price": item["unit_price"],
                }
                for item in self.cart
            ]

            order = create_draft_order(
                session=session,
                customer=customer,
                items=items,
                delivery_address=self.address.text().strip(),
                delivery_city=self.city.text().strip() or None,
                delivery_province=self.province.currentText() or None,
                customer_whatsapp=self.customer_whatsapp.text().strip() or None,
                delivery_instructions=self.instructions.text().strip() or None,
                payment_method=self.payment_method.currentData(),
                delivery_charge=Decimal(str(self.delivery_charge.value())),
                discount_amount=Decimal(str(self.discount.value())),
                source="manual",
            )

            order_number = order.order_number
            order_total = order.total_amount
            session.commit()

            QMessageBox.information(
                self,
                "Draft Order Saved",
                f"Order {order_number} has been saved successfully.\n\n"
                f"Total: PKR {order_total:,.2f}\n"
                "The order is still a draft. No stock has been reserved or deducted."
            )

            self.cart.clear()
            self.cart_table.setRowCount(0)
            self.delivery_charge.setValue(0)
            self.discount.setValue(0)
            self.update_totals()
            self.refresh_orders()

        except Exception as error:
            session.rollback()
            QMessageBox.critical(
                self, "Order Could Not Be Saved",
                f"No order was saved.\n\n{error}"
            )
        finally:
            session.close()
