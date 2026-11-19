import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QTabWidget, QComboBox, QSpinBox, QCheckBox, QGroupBox,
    QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QInputDialog, QScrollArea, QDialog, QDialogButtonBox, QPlainTextEdit
)

from auth_manager import DB_PATH, connect_db, hash_password, PERMISSIONS
from theme_manager import (
    THEMES, current_theme, save_theme, apply_theme
)


def app_settings():
    from PySide6.QtCore import QSettings
    return QSettings("ZAO Enterprises", "Pillistan")


class SettingsCentre(QWidget):
    """Unified settings workspace for Pillistan."""

    def __init__(self, app, main_window):
        super().__init__()
        self.app = app
        self.main_window = main_window
        self.settings = app_settings()
        self._build_ui()
        self._load_all()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        heading = QLabel("Settings Centre")
        heading.setStyleSheet("font-size: 26px; font-weight: bold;")
        root.addWidget(heading)

        intro = QLabel(
            "Manage company information, regional preferences, business defaults, "
            "users, appearance and database backups."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        self._build_general_tab()
        self._build_regional_tab()
        self._build_sales_tab()
        self._build_purchase_tab()
        self._build_inventory_tab()
        self._build_security_tab()
        self._build_appearance_tab()
        self._build_backup_tab()

        save_row = QHBoxLayout()
        save_row.addStretch()
        save_button = QPushButton("Save Settings")
        save_button.setMinimumWidth(150)
        save_button.clicked.connect(self.save_all)
        save_row.addWidget(save_button)
        root.addLayout(save_row)

    def _form_tab(self, title):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(form)
        layout.addStretch()
        self.tabs.addTab(page, title)
        return page, layout, form

    def _build_general_tab(self):
        self.general_page, _, form = self._form_tab("General")
        self.company_name = QLineEdit()
        self.company_phone = QLineEdit()
        self.company_email = QLineEdit()
        self.company_address = QPlainTextEdit()
        self.company_address.setMaximumHeight(85)
        self.logo_path = QLineEdit()
        self.logo_path.setReadOnly(True)
        logo_row = QHBoxLayout()
        logo_row.addWidget(self.logo_path)
        browse = QPushButton("Browse")
        browse.clicked.connect(self.choose_logo)
        logo_row.addWidget(browse)

        form.addRow("Company / Business Name:", self.company_name)
        form.addRow("Phone:", self.company_phone)
        form.addRow("Email:", self.company_email)
        form.addRow("Address:", self.company_address)
        form.addRow("Logo:", logo_row)

    def _build_regional_tab(self):
        self.regional_page, _, form = self._form_tab("Regional")
        self.currency = QComboBox()
        self.currency.addItems(["PKR - Pakistani Rupee"])
        self.date_format = QComboBox()
        self.date_format.addItems([
            "DD-MM-YYYY", "DD/MM/YYYY", "YYYY-MM-DD", "MM/DD/YYYY"
        ])
        self.number_format = QComboBox()
        self.number_format.addItems([
            "1,234.56", "1.234,56", "1 234.56"
        ])
        self.timezone = QComboBox()
        self.timezone.addItems(["Asia/Karachi"])
        form.addRow("Currency:", self.currency)
        form.addRow("Date Format:", self.date_format)
        form.addRow("Number Format:", self.number_format)
        form.addRow("Time Zone:", self.timezone)
        note = QLabel(
            "The available currency and time-zone defaults are configured for Pakistan."
        )
        note.setWordWrap(True)
        form.addRow("", note)

    def _build_sales_tab(self):
        self.sales_page, _, form = self._form_tab("Sales")
        self.sales_prefix = QLineEdit()
        self.sales_prefix.setMaxLength(12)
        self.sales_next = QSpinBox()
        self.sales_next.setRange(1, 999999999)
        self.sales_payment = QComboBox()
        self.sales_payment.addItems(["Cash", "Bank", "COD", "Other"])
        self.sales_notes = QLineEdit()
        form.addRow("Invoice Prefix:", self.sales_prefix)
        form.addRow("Next Invoice Number:", self.sales_next)
        form.addRow("Default Payment Method:", self.sales_payment)
        form.addRow("Default Notes:", self.sales_notes)
        note = QLabel(
            "These are saved as application preferences. Existing invoice numbering "
            "logic is not changed by this settings screen."
        )
        note.setWordWrap(True)
        form.addRow("", note)

    def _build_purchase_tab(self):
        self.purchase_page, _, form = self._form_tab("Purchases")
        self.purchase_prefix = QLineEdit()
        self.purchase_prefix.setMaxLength(12)
        self.purchase_next = QSpinBox()
        self.purchase_next.setRange(1, 999999999)
        self.purchase_payment = QComboBox()
        self.purchase_payment.addItems(["Cash", "Bank"])
        self.purchase_notes = QLineEdit()
        form.addRow("Purchase Prefix:", self.purchase_prefix)
        form.addRow("Next Purchase Number:", self.purchase_next)
        form.addRow("Default Payment Method:", self.purchase_payment)
        form.addRow("Default Notes:", self.purchase_notes)
        note = QLabel(
            "These preferences do not alter existing purchase records or accounting entries."
        )
        note.setWordWrap(True)
        form.addRow("", note)

    def _build_inventory_tab(self):
        self.inventory_page, _, form = self._form_tab("Inventory")
        self.low_stock_enabled = QCheckBox("Enable low-stock warning preference")
        self.low_stock_level = QSpinBox()
        self.low_stock_level.setRange(0, 100000000)
        self.expiry_enabled = QCheckBox("Enable expiry warning preference")
        self.expiry_days = QSpinBox()
        self.expiry_days.setRange(0, 3650)
        form.addRow("", self.low_stock_enabled)
        form.addRow("Low-stock threshold:", self.low_stock_level)
        form.addRow("", self.expiry_enabled)
        form.addRow("Expiry warning (days):", self.expiry_days)
        note = QLabel(
            "These values store alert preferences. They will take effect in inventory "
            "screens when their alert logic is connected."
        )
        note.setWordWrap(True)
        form.addRow("", note)

    def _build_security_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.security_tabs = QTabWidget()
        layout.addWidget(self.security_tabs)
        self.tabs.addTab(page, "Users & Security")

        users_page = QWidget()
        users_layout = QVBoxLayout(users_page)
        user_form_box = QGroupBox("Create User")
        user_form = QFormLayout(user_form_box)
        self.new_username = QLineEdit()
        self.new_full_name = QLineEdit()
        self.new_password = QLineEdit()
        self.new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_role = QComboBox()
        user_form.addRow("Username:", self.new_username)
        user_form.addRow("Full Name:", self.new_full_name)
        user_form.addRow("Temporary Password:", self.new_password)
        user_form.addRow("Role:", self.new_role)
        create_user_button = QPushButton("Create User")
        create_user_button.clicked.connect(self.create_user)
        user_form.addRow("", create_user_button)
        users_layout.addWidget(user_form_box)

        self.users_table = QTableWidget(0, 5)
        self.users_table.setHorizontalHeaderLabels(
            ["ID", "Username", "Full Name", "Status", "Roles"]
        )
        self.users_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.users_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.users_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        users_layout.addWidget(self.users_table)

        user_actions = QHBoxLayout()
        refresh_users = QPushButton("Refresh")
        refresh_users.clicked.connect(self.refresh_users)
        toggle_user = QPushButton("Activate / Deactivate Selected")
        toggle_user.clicked.connect(self.toggle_selected_user)
        reset_password = QPushButton("Reset Selected Password")
        reset_password.clicked.connect(self.reset_selected_password)
        user_actions.addWidget(refresh_users)
        user_actions.addWidget(toggle_user)
        user_actions.addWidget(reset_password)
        users_layout.addLayout(user_actions)
        self.security_tabs.addTab(users_page, "User Accounts")

        roles_page = QWidget()
        roles_layout = QVBoxLayout(roles_page)
        role_top = QHBoxLayout()
        self.roles_list = QComboBox()
        self.roles_list.currentIndexChanged.connect(self.load_role_permissions)
        role_top.addWidget(QLabel("Role:"))
        role_top.addWidget(self.roles_list, 1)
        new_role_button = QPushButton("Create Role")
        new_role_button.clicked.connect(self.create_role)
        role_top.addWidget(new_role_button)
        roles_layout.addLayout(role_top)

        self.permission_checks = {}
        scroll_content = QWidget()
        permissions_layout = QVBoxLayout(scroll_content)
        for key in PERMISSIONS:
            check = QCheckBox(key)
            self.permission_checks[key] = check
            permissions_layout.addWidget(check)
        permissions_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(scroll_content)
        roles_layout.addWidget(scroll)

        role_buttons = QHBoxLayout()
        save_role_button = QPushButton("Save Role Permissions")
        save_role_button.clicked.connect(self.save_role_permissions)
        role_buttons.addStretch()
        role_buttons.addWidget(save_role_button)
        roles_layout.addLayout(role_buttons)
        self.security_tabs.addTab(roles_page, "Roles & Permissions")

        security_note = QLabel(
            "Account and role records are stored in the existing authentication database. "
            "Permission assignments are configurable here; individual business modules "
            "must enforce those permissions separately."
        )
        security_note.setWordWrap(True)
        layout.addWidget(security_note)

    def _build_appearance_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.addWidget(QLabel("Choose a colour theme for your Pillistan workspace."))
        self.theme_selector = QComboBox()
        self.theme_selector.addItems(list(THEMES.keys()))
        self.theme_selector.setCurrentText(current_theme())
        self.theme_selector.currentTextChanged.connect(self.change_theme)
        layout.addWidget(QLabel("Colour Theme:"))
        layout.addWidget(self.theme_selector)

        self.theme_preview = QFrame()
        self.theme_preview.setMinimumHeight(150)
        preview_layout = QVBoxLayout(self.theme_preview)
        preview_title = QLabel("PILLISTAN")
        preview_title.setStyleSheet("font-size: 24px; font-weight: bold;")
        preview_layout.addWidget(preview_title)
        preview_layout.addWidget(QLabel("Nourish to Flourish"))
        preview_layout.addWidget(QPushButton("Sample Button"))
        preview_layout.addStretch()
        layout.addWidget(QLabel("Theme Preview:"))
        layout.addWidget(self.theme_preview)
        layout.addStretch()
        self.tabs.addTab(page, "Appearance")
        self.update_theme_preview(current_theme())

    def _build_backup_tab(self):
        page, layout, form = self._form_tab("Backup & Restore")
        self.backup_folder = QLineEdit()
        self.backup_folder.setReadOnly(True)
        self.backup_folder.setText(
            str(Path.home() / "PillistanBackups")
        )
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.backup_folder)
        browse = QPushButton("Choose")
        browse.clicked.connect(self.choose_backup_folder)
        folder_row.addWidget(browse)
        form.addRow("Backup Folder:", folder_row)

        backup_button = QPushButton("Create Database Backup Now")
        backup_button.clicked.connect(self.create_backup)
        restore_button = QPushButton("Restore Database Backup")
        restore_button.clicked.connect(self.restore_backup)
        layout.addWidget(backup_button)
        layout.addWidget(restore_button)
        warning = QLabel(
            "Restoring replaces the current database. Pillistan will first create a "
            "safety backup of the current database. Restart the application after restore."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)

    def _key(self, name):
        return f"business/{name}"

    def _load_all(self):
        s = self.settings
        self.company_name.setText(s.value(self._key("company_name"), ""))
        self.company_phone.setText(s.value(self._key("company_phone"), ""))
        self.company_email.setText(s.value(self._key("company_email"), ""))
        self.company_address.setPlainText(s.value(self._key("company_address"), ""))
        self.logo_path.setText(s.value(self._key("logo_path"), ""))

        self.date_format.setCurrentText(s.value(self._key("date_format"), "DD-MM-YYYY"))
        self.number_format.setCurrentText(s.value(self._key("number_format"), "1,234.56"))

        self.sales_prefix.setText(s.value(self._key("sales_prefix"), "INV-"))
        self.sales_next.setValue(int(s.value(self._key("sales_next"), 1)))
        self.sales_payment.setCurrentText(s.value(self._key("sales_payment"), "COD"))
        self.sales_notes.setText(s.value(self._key("sales_notes"), ""))

        self.purchase_prefix.setText(s.value(self._key("purchase_prefix"), "PUR-"))
        self.purchase_next.setValue(int(s.value(self._key("purchase_next"), 1)))
        self.purchase_payment.setCurrentText(s.value(self._key("purchase_payment"), "Cash"))
        self.purchase_notes.setText(s.value(self._key("purchase_notes"), ""))

        self.low_stock_enabled.setChecked(
            s.value(self._key("low_stock_enabled"), True, type=bool)
        )
        self.low_stock_level.setValue(int(s.value(self._key("low_stock_level"), 5)))
        self.expiry_enabled.setChecked(
            s.value(self._key("expiry_enabled"), True, type=bool)
        )
        self.expiry_days.setValue(int(s.value(self._key("expiry_days"), 90)))
        self.refresh_users()
        self.refresh_roles()

    def save_all(self):
        s = self.settings
        values = {
            "company_name": self.company_name.text().strip(),
            "company_phone": self.company_phone.text().strip(),
            "company_email": self.company_email.text().strip(),
            "company_address": self.company_address.toPlainText().strip(),
            "logo_path": self.logo_path.text().strip(),
            "date_format": self.date_format.currentText(),
            "number_format": self.number_format.currentText(),
            "sales_prefix": self.sales_prefix.text().strip(),
            "sales_next": self.sales_next.value(),
            "sales_payment": self.sales_payment.currentText(),
            "sales_notes": self.sales_notes.text().strip(),
            "purchase_prefix": self.purchase_prefix.text().strip(),
            "purchase_next": self.purchase_next.value(),
            "purchase_payment": self.purchase_payment.currentText(),
            "purchase_notes": self.purchase_notes.text().strip(),
            "low_stock_enabled": self.low_stock_enabled.isChecked(),
            "low_stock_level": self.low_stock_level.value(),
            "expiry_enabled": self.expiry_enabled.isChecked(),
            "expiry_days": self.expiry_days.value(),
        }
        for key, value in values.items():
            s.setValue(self._key(key), value)
        s.sync()
        QMessageBox.information(
            self, "Settings Saved",
            "Your settings have been saved successfully."
        )

    def choose_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Company Logo", "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if path:
            self.logo_path.setText(path)

    def change_theme(self, name):
        if not name:
            return
        save_theme(name)
        apply_theme(self.app, self.main_window, name)
        self.update_theme_preview(name)

    def update_theme_preview(self, name):
        colors = THEMES[name]
        self.theme_preview.setStyleSheet(
            f"background-color: {colors['surface']};"
            f"border: 1px solid {colors['border']};"
            "border-radius: 9px; padding: 12px;"
        )

    def refresh_users(self):
        with connect_db() as con:
            rows = con.execute("""
                SELECT u.id, u.username, u.full_name, u.is_active,
                       GROUP_CONCAT(r.name, ', ') AS roles
                FROM app_users u
                LEFT JOIN app_user_roles ur ON ur.user_id = u.id
                LEFT JOIN app_roles r ON r.id = ur.role_id
                GROUP BY u.id
                ORDER BY u.id
            """).fetchall()
        self.users_table.setRowCount(0)
        for row in rows:
            r = self.users_table.rowCount()
            self.users_table.insertRow(r)
            values = [
                row["id"], row["username"], row["full_name"],
                "Active" if row["is_active"] else "Inactive",
                row["roles"] or ""
            ]
            for c, value in enumerate(values):
                self.users_table.setItem(r, c, QTableWidgetItem(str(value)))
        self.new_role.clear()
        with connect_db() as con:
            roles = con.execute("SELECT id, name FROM app_roles ORDER BY name").fetchall()
        for role in roles:
            self.new_role.addItem(role["name"], role["id"])

    def _selected_user_id(self):
        row = self.users_table.currentRow()
        if row < 0:
            return None
        item = self.users_table.item(row, 0)
        return int(item.text()) if item else None

    def create_user(self):
        username = self.new_username.text().strip().lower()
        full_name = self.new_full_name.text().strip()
        password = self.new_password.text()
        role_id = self.new_role.currentData()
        import re
        if not re.fullmatch(r"[a-z0-9_.-]{3,40}", username):
            QMessageBox.warning(self, "Invalid Username",
                                "Username must be 3-40 characters using letters, numbers, dots, underscores or hyphens.")
            return
        if not full_name:
            QMessageBox.warning(self, "Missing Name", "Enter the user's full name.")
            return
        if len(password) < 12 or not any(ch.isdigit() for ch in password):
            QMessageBox.warning(self, "Weak Password",
                                "Use at least 12 characters and include at least one number.")
            return
        if role_id is None:
            QMessageBox.warning(self, "Missing Role", "Create or select a role first.")
            return
        salt, password_hash = hash_password(password)
        try:
            with connect_db() as con:
                cur = con.execute("""
                    INSERT INTO app_users (username, full_name, password_hash, password_salt)
                    VALUES (?, ?, ?, ?)
                """, (username, full_name, password_hash, salt))
                con.execute(
                    "INSERT INTO app_user_roles (user_id, role_id) VALUES (?, ?)",
                    (cur.lastrowid, role_id)
                )
            self.new_username.clear()
            self.new_full_name.clear()
            self.new_password.clear()
            self.refresh_users()
            QMessageBox.information(self, "User Created", "The user account was created.")
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "User Not Created", "That username already exists.")

    def toggle_selected_user(self):
        user_id = self._selected_user_id()
        if user_id is None:
            QMessageBox.warning(self, "Select User", "Select a user account first.")
            return
        current = getattr(self.main_window, "current_user", {}) or {}
        if user_id == current.get("id"):
            QMessageBox.warning(self, "Not Allowed", "You cannot deactivate your own logged-in account.")
            return
        with connect_db() as con:
            row = con.execute(
                "SELECT is_active FROM app_users WHERE id = ?", (user_id,)
            ).fetchone()
            if not row:
                return
            new_status = 0 if row["is_active"] else 1
            con.execute(
                "UPDATE app_users SET is_active = ? WHERE id = ?",
                (new_status, user_id)
            )
        self.refresh_users()

    def reset_selected_password(self):
        user_id = self._selected_user_id()
        if user_id is None:
            QMessageBox.warning(self, "Select User", "Select a user account first.")
            return
        password, ok = QInputDialog.getText(
            self, "Reset Password", "New password:",
            QLineEdit.EchoMode.Password
        )
        if not ok:
            return
        if len(password) < 12 or not any(ch.isdigit() for ch in password):
            QMessageBox.warning(self, "Weak Password",
                                "Use at least 12 characters and include at least one number.")
            return
        salt, password_hash = hash_password(password)
        with connect_db() as con:
            con.execute("""
                UPDATE app_users
                SET password_hash = ?, password_salt = ?,
                    failed_attempts = 0, locked_until = NULL
                WHERE id = ?
            """, (password_hash, salt, user_id))
        QMessageBox.information(self, "Password Reset", "The password has been reset.")

    def refresh_roles(self):
        self.roles_list.blockSignals(True)
        self.roles_list.clear()
        with connect_db() as con:
            rows = con.execute("SELECT id, name FROM app_roles ORDER BY name").fetchall()
        for row in rows:
            self.roles_list.addItem(row["name"], row["id"])
        self.roles_list.blockSignals(False)
        self.load_role_permissions()

    def create_role(self):
        name, ok = QInputDialog.getText(self, "Create Role", "Role name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        description, ok = QInputDialog.getText(
            self, "Role Description", "Description (optional):"
        )
        if not ok:
            description = ""
        try:
            with connect_db() as con:
                con.execute(
                    "INSERT INTO app_roles (name, description) VALUES (?, ?)",
                    (name, description.strip())
                )
            self.refresh_roles()
            self.refresh_users()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Role Exists", "A role with that name already exists.")

    def load_role_permissions(self, *_):
        role_id = self.roles_list.currentData()
        for check in self.permission_checks.values():
            check.setChecked(False)
        if role_id is None:
            return
        with connect_db() as con:
            rows = con.execute("""
                SELECT p.permission_key
                FROM app_role_permissions rp
                JOIN app_permissions p ON p.id = rp.permission_id
                WHERE rp.role_id = ?
            """, (role_id,)).fetchall()
        selected = {row["permission_key"] for row in rows}
        for key, check in self.permission_checks.items():
            check.setChecked(key in selected)

    def save_role_permissions(self):
        role_id = self.roles_list.currentData()
        if role_id is None:
            return
        selected = [
            key for key, check in self.permission_checks.items()
            if check.isChecked()
        ]
        with connect_db() as con:
            con.execute("DELETE FROM app_role_permissions WHERE role_id = ?", (role_id,))
            for key in selected:
                row = con.execute(
                    "SELECT id FROM app_permissions WHERE permission_key = ?", (key,)
                ).fetchone()
                if row:
                    con.execute(
                        "INSERT INTO app_role_permissions (role_id, permission_id) VALUES (?, ?)",
                        (role_id, row["id"])
                    )
        QMessageBox.information(self, "Permissions Saved", "Role permissions were saved.")

    def choose_backup_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Choose Backup Folder", self.backup_folder.text()
        )
        if folder:
            self.backup_folder.setText(folder)
            self.settings.setValue(self._key("backup_folder"), folder)
            self.settings.sync()

    def create_backup(self):
        folder = Path(self.backup_folder.text())
        try:
            folder.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_path = folder / f"pillistan_backup_{stamp}.db"
            source = sqlite3.connect(str(DB_PATH), timeout=30)
            target = sqlite3.connect(str(target_path), timeout=30)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
            QMessageBox.information(
                self, "Backup Successful",
                f"Database backup created successfully:\n{target_path}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Backup Failed", str(exc))

    def restore_backup(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Pillistan Database Backup", "",
            "SQLite Database (*.db *.sqlite *.sqlite3)"
        )
        if not path:
            return
        confirm = QMessageBox.question(
            self, "Confirm Database Restore",
            "This will replace the current database. A safety backup will be created first. "
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        source_path = Path(path)
        if source_path.resolve() == Path(DB_PATH).resolve():
            QMessageBox.warning(self, "Invalid Backup", "Select a separate backup file.")
            return

        try:
            check = sqlite3.connect(str(source_path), timeout=30)
            try:
                integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
                tables = {
                    row[0] for row in check.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                required = {"app_users", "app_roles", "products"}
                if integrity != "ok" or not required.issubset(tables):
                    raise ValueError(
                        "The selected file is not a valid Pillistan database backup."
                    )
            finally:
                check.close()

            backup_folder = Path(self.backup_folder.text())
            backup_folder.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safety_path = backup_folder / f"before_restore_{stamp}.db"

            current = sqlite3.connect(str(DB_PATH), timeout=30)
            safety = sqlite3.connect(str(safety_path), timeout=30)
            try:
                current.backup(safety)
            finally:
                safety.close()
                current.close()

            source = sqlite3.connect(str(source_path), timeout=30)
            destination = sqlite3.connect(str(DB_PATH), timeout=30)
            try:
                source.backup(destination)
            finally:
                destination.close()
                source.close()

            QMessageBox.information(
                self, "Restore Completed",
                "The database was restored successfully.\n"
                f"Safety backup: {safety_path}\n\n"
                "Close and restart Pillistan before continuing."
            )
        except Exception as exc:
            QMessageBox.critical(self, "Restore Failed", str(exc))
