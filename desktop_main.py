import sys

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QStackedWidget,
    QComboBox,
    QDialog,
)
from PySide6.QtCore import Qt

from finance_manager import FinanceManager
from settings_centre import SettingsCentre
from auth_manager import initialize_auth, has_users, FirstAdminSetupDialog, LoginDialog
from theme_manager import (
    THEMES,
    current_theme,
    save_theme,
    apply_theme,
)

from database import SessionLocal
from product_manager import ProductManager
from inventory_manager import InventoryWindow
from customer_manager import CustomerManager
from purchase_manager import PurchaseManager
from orders_manager import OrdersManager
from courier_manager import CourierManager
from returns_module import ReturnsManager


class AppearancePage(QWidget):

    def __init__(self, app, main_window):
        super().__init__()
        self.app = app
        self.main_window = main_window

        layout = QVBoxLayout(self)
        layout.setContentsMargins(35, 30, 35, 30)
        layout.setSpacing(16)

        heading = QLabel("Appearance Settings")
        heading.setStyleSheet(
            "font-size: 27px; font-weight: bold;"
        )
        layout.addWidget(heading)

        description = QLabel(
            "Choose a colour theme for your Pillistan workspace. "
            "Your selection is saved automatically."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self.theme_selector = QComboBox()
        self.theme_selector.addItems(list(THEMES.keys()))
        self.theme_selector.setCurrentText(current_theme())
        self.theme_selector.setMinimumWidth(260)
        self.theme_selector.currentTextChanged.connect(
            self.change_theme
        )

        layout.addWidget(QLabel("Color Theme"))
        layout.addWidget(self.theme_selector)

        self.preview = QFrame()
        self.preview.setMinimumHeight(170)

        preview_layout = QVBoxLayout(self.preview)

        self.preview_title = QLabel("PILLISTAN")
        self.preview_title.setStyleSheet(
            "font-size: 23px; font-weight: bold;"
        )

        self.preview_subtitle = QLabel("Nourish to Flourish")
        self.preview_button = QPushButton("Sample Button")

        preview_layout.addWidget(self.preview_title)
        preview_layout.addWidget(self.preview_subtitle)
        preview_layout.addWidget(self.preview_button)
        preview_layout.addStretch()

        layout.addSpacing(12)
        layout.addWidget(QLabel("Theme Preview"))
        layout.addWidget(self.preview)
        layout.addStretch()

        self.update_preview(current_theme())

    def change_theme(self, name):
        if not name:
            return

        save_theme(name)
        apply_theme(self.app, self.main_window, name)
        self.update_preview(name)

    def update_preview(self, name):
        colors = THEMES[name]

        self.preview.setStyleSheet(
            f"background-color: {colors['surface']};"
            f"border: 1px solid {colors['border']};"
            "border-radius: 10px; padding: 12px;"
        )
        self.preview_title.setStyleSheet(
            f"color: {colors['primary']};"
            "font-size: 23px; font-weight: bold;"
        )
        self.preview_subtitle.setStyleSheet(
            f"color: {colors['muted']};"
        )
        self.preview_button.setStyleSheet(
            f"background-color: {colors['primary']};"
            "color: white; padding: 9px 16px;"
            "border-radius: 5px;"
        )


class PillistanApp(QMainWindow):

    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user or {}

        self.setWindowTitle("Pillistan Business Management")
        self.resize(1250, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(230)
        self.sidebar.setStyleSheet(
            "background-color: #164b37;"
        )

        sidebar_layout = QVBoxLayout(self.sidebar)

        logo = QLabel("PILLISTAN")
        logo.setStyleSheet(
            "color: white; font-size: 25px; font-weight: bold;"
        )
        sidebar_layout.addWidget(logo)

        slogan = QLabel("Nourish to Flourish")
        slogan.setStyleSheet("color: #d5e9dc;")
        sidebar_layout.addWidget(slogan)

        sidebar_layout.addSpacing(30)

        self.pages = QStackedWidget()

        # Core pages available immediately.
        self.dashboard_page = self._create_dashboard()
        self.finance_page = FinanceManager(user=self.current_user)
        self.settings_page = SettingsCentre(
            QApplication.instance(), self
        )

        self.pages.addWidget(self.dashboard_page)
        self.pages.addWidget(self.finance_page)
        self.pages.addWidget(self.settings_page)

        # Other modules are loaded only when first opened.
        self.module_factories = {
            "Products": lambda: ProductManager(),
            "Inventory": lambda: InventoryWindow(user=self.current_user),
            "Customers": lambda: CustomerManager(SessionLocal),
            "Purchases": lambda: PurchaseManager(user=self.current_user),
            "Orders": lambda: OrdersManager(SessionLocal),
            "Couriers": lambda: CourierManager(SessionLocal, self.current_user),
            "Returns": lambda: ReturnsManager(SessionLocal, self.current_user),
            "Reports": lambda: self._create_placeholder_page(
                "Reports",
                "Business reports will be implemented in a later development step."
            ),
        }

        self.module_pages = {}

        menu_items = [
            "Dashboard",
            "Products",
            "Inventory",
            "Customers",
            "Purchases",
            "Orders",
            "Couriers",
            "Returns",
            "Finance",
            "Reports",
            "Settings",
        ]

        for item in menu_items:
            button = QPushButton(item)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet("""
                QPushButton {
                    color: white;
                    background-color: transparent;
                    border: none;
                    padding: 12px;
                    text-align: left;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #28664d;
                }
            """)

            button.clicked.connect(
                lambda checked=False, page_name=item:
                    self.open_page(page_name)
            )

            sidebar_layout.addWidget(button)

        sidebar_layout.addStretch()

        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.pages)

        apply_theme(
            QApplication.instance(),
            self,
            current_theme()
        )

    def _create_dashboard(self):
        content = QWidget()
        content.setStyleSheet("background-color: #f4f7f5;")

        layout = QVBoxLayout(content)
        layout.setContentsMargins(35, 30, 35, 30)

        heading = QLabel("Business Dashboard")
        heading.setStyleSheet(
            "font-size: 28px; font-weight: bold; color: #24352c;"
        )
        layout.addWidget(heading)

        subtitle = QLabel(
            "Welcome to your Pillistan management workspace."
        )
        subtitle.setStyleSheet(
            "font-size: 14px; color: #718078;"
        )
        layout.addWidget(subtitle)

        layout.addSpacing(25)

        cards_layout = QHBoxLayout()

        card_data = [
            ("Total Orders", "0"),
            ("Products", "0"),
            ("Customers", "0"),
            ("Pending COD", "PKR 0"),
        ]

        for title, value in card_data:
            card = QFrame()
            card.setStyleSheet("""
                QFrame {
                    background-color: white;
                    border-radius: 10px;
                    padding: 15px;
                }
            """)

            card_layout = QVBoxLayout(card)

            title_label = QLabel(title)
            title_label.setStyleSheet(
                "font-size: 13px; color: #718078;"
            )

            value_label = QLabel(value)
            value_label.setStyleSheet("""
                font-size: 25px;
                font-weight: bold;
                color: #164b37;
            """)

            card_layout.addWidget(title_label)
            card_layout.addWidget(value_label)
            cards_layout.addWidget(card)

        layout.addLayout(cards_layout)
        layout.addSpacing(25)

        welcome = QLabel(
            "Your business, organised.\n\n"
            "Manage products, inventory, customers, orders, "
            "couriers, returns and financial records from one place."
        )
        welcome.setStyleSheet("""
            background-color: white;
            color: #24352c;
            font-size: 16px;
            padding: 25px;
            border-radius: 10px;
        """)
        welcome.setMinimumHeight(130)

        layout.addWidget(welcome)
        layout.addStretch()

        return content

    def _create_placeholder_page(self, title, description):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(35, 30, 35, 30)

        heading = QLabel(title)
        heading.setStyleSheet(
            "font-size: 26px; font-weight: bold; color: #24352c;"
        )

        message = QLabel(description)
        message.setWordWrap(True)
        message.setStyleSheet("font-size: 14px; color: #718078;")

        layout.addWidget(heading)
        layout.addSpacing(12)
        layout.addWidget(message)
        layout.addStretch()

        return page

    def open_page(self, page_name):
        if page_name == "Dashboard":
            page = self.dashboard_page

        elif page_name == "Finance":
            page = self.finance_page
            page.refresh_all()

        elif page_name == "Settings":
            page = self.settings_page

        else:
            page = self.module_pages.get(page_name)

            if page is None:
                factory = self.module_factories.get(page_name)

                if factory is None:
                    return

                page = factory()
                self.module_pages[page_name] = page
                self.pages.addWidget(page)

            # Refresh the selected module when it opens.
            if page_name == "Products":
                page.load_products()

            elif page_name == "Inventory":
                page.load_inventory()

            elif page_name == "Customers":
                page.load_customers()

            elif page_name == "Purchases":
                page.load_suppliers()
                page.load_products()

            elif page_name == "Orders":
                page.refresh_orders()

            elif page_name == "Couriers":
                page.refresh_all()

        self.pages.setCurrentWidget(page)

    def open_finance(self):
        self.open_page("Finance")


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Initialize authentication tables.
    initialize_auth()

    # Create the first administrator if no user exists.
    if not has_users():
        setup_dialog = FirstAdminSetupDialog()
        if setup_dialog.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)

    # Require login before opening the main application.
    login_dialog = LoginDialog()
    if login_dialog.exec() != QDialog.DialogCode.Accepted:
        sys.exit(0)

    # Open the application after successful authentication.
    window = PillistanApp(current_user=login_dialog.authenticated_user)
    window.setWindowTitle(
        f"Pillistan - {login_dialog.authenticated_user['username']}"
    )
    window.show()

    sys.exit(app.exec())
