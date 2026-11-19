import hashlib
import hmac
import os
import re
import sqlite3
import time
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QHBoxLayout
)

DB_PATH = Path(
    os.environ.get(
        "PILLISTAN_DB_PATH",
        str(Path(__file__).resolve().parent / "pk_skincare_ops.db")
    )
)

PBKDF2_ITERATIONS = 310000
LOCKOUT_SECONDS = 300

PERMISSIONS = [
    "dashboard.view",
    "products.view", "products.manage",
    "inventory.view", "inventory.manage",
    "customers.view", "customers.manage",
    "sales.view", "sales.manage",
    "purchases.view", "purchases.manage",
    "couriers.view", "couriers.manage",
    "returns.view", "returns.manage",
    "finance.view", "finance.manage",
    "reports.view", "reports.export",
    "settings.view", "settings.manage",
    "users.view", "users.manage",
    "backup.manage",
]


def connect_db():
    connection = sqlite3.connect(str(DB_PATH), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def initialize_auth():
    with connect_db() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS app_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS app_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                permission_key TEXT NOT NULL UNIQUE,
                description TEXT
            );

            CREATE TABLE IF NOT EXISTS app_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until REAL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_login TEXT
            );

            CREATE TABLE IF NOT EXISTS app_user_roles (
                user_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, role_id),
                FOREIGN KEY (user_id) REFERENCES app_users(id),
                FOREIGN KEY (role_id) REFERENCES app_roles(id)
            );

            CREATE TABLE IF NOT EXISTS app_role_permissions (
                role_id INTEGER NOT NULL,
                permission_id INTEGER NOT NULL,
                PRIMARY KEY (role_id, permission_id),
                FOREIGN KEY (role_id) REFERENCES app_roles(id),
                FOREIGN KEY (permission_id)
                    REFERENCES app_permissions(id)
            );
        """)

        connection.execute(
            """
            INSERT OR IGNORE INTO app_roles (name, description)
            VALUES (?, ?)
            """,
            ("Administrator", "Full system access")
        )

        for permission in PERMISSIONS:
            connection.execute(
                """
                INSERT OR IGNORE INTO app_permissions
                (permission_key, description)
                VALUES (?, ?)
                """,
                (permission, permission.replace(".", " ").title())
            )

        role = connection.execute(
            "SELECT id FROM app_roles WHERE name = ?",
            ("Administrator",)
        ).fetchone()

        for permission in connection.execute(
            "SELECT id FROM app_permissions"
        ).fetchall():
            connection.execute(
                """
                INSERT OR IGNORE INTO app_role_permissions
                (role_id, permission_id)
                VALUES (?, ?)
                """,
                (role["id"], permission["id"])
            )


def has_users():
    with connect_db() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS total FROM app_users"
        ).fetchone()
        return row["total"] > 0


def hash_password(password, salt=None):
    salt_bytes = (
        bytes.fromhex(salt)
        if salt else os.urandom(32)
    )
    result = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        PBKDF2_ITERATIONS
    )
    return salt_bytes.hex(), result.hex()


def create_initial_admin(username, full_name, password):
    username = username.strip().lower()
    full_name = full_name.strip()

    if not re.fullmatch(r"[a-z0-9_.-]{3,40}", username):
        raise ValueError(
            "Username must be 3-40 characters and use letters, "
            "numbers, dots, underscores or hyphens."
        )

    if not full_name:
        raise ValueError("Please enter the administrator's full name.")

    if len(password) < 12 or not any(c.isdigit() for c in password):
        raise ValueError(
            "Password must contain at least 12 characters "
            "and at least one number."
        )

    salt, password_hash = hash_password(password)

    with connect_db() as connection:
        total = connection.execute(
            "SELECT COUNT(*) AS total FROM app_users"
        ).fetchone()["total"]

        if total:
            raise ValueError(
                "An administrator account already exists. "
                "Initial setup is no longer available."
            )

        role = connection.execute(
            "SELECT id FROM app_roles WHERE name = ?",
            ("Administrator",)
        ).fetchone()

        cursor = connection.execute(
            """
            INSERT INTO app_users
            (username, full_name, password_hash, password_salt)
            VALUES (?, ?, ?, ?)
            """,
            (username, full_name, password_hash, salt)
        )

        connection.execute(
            """
            INSERT INTO app_user_roles (user_id, role_id)
            VALUES (?, ?)
            """,
            (cursor.lastrowid, role["id"])
        )


def authenticate_user(username, password):
    username = username.strip()

    with connect_db() as connection:
        user = connection.execute(
            """
            SELECT * FROM app_users
            WHERE username = ? COLLATE NOCASE
            """,
            (username,)
        ).fetchone()

        if not user or not user["is_active"]:
            return None

        now = time.time()

        if user["locked_until"] and user["locked_until"] > now:
            return None

        _, candidate = hash_password(
            password,
            user["password_salt"]
        )

        if not hmac.compare_digest(
            candidate, user["password_hash"]
        ):
            attempts = user["failed_attempts"] + 1
            locked_until = (
                now + LOCKOUT_SECONDS if attempts >= 5 else None
            )

            connection.execute(
                """
                UPDATE app_users
                SET failed_attempts = ?, locked_until = ?
                WHERE id = ?
                """,
                (attempts, locked_until, user["id"])
            )
            return None

        connection.execute(
            """
            UPDATE app_users
            SET failed_attempts = 0,
                locked_until = NULL,
                last_login = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (user["id"],)
        )

        roles = connection.execute(
            """
            SELECT r.name
            FROM app_user_roles ur
            JOIN app_roles r ON r.id = ur.role_id
            WHERE ur.user_id = ?
            """,
            (user["id"],)
        ).fetchall()

        permissions = connection.execute(
            """
            SELECT DISTINCT p.permission_key
            FROM app_user_roles ur
            JOIN app_role_permissions rp ON rp.role_id = ur.role_id
            JOIN app_permissions p ON p.id = rp.permission_id
            WHERE ur.user_id = ?
            """,
            (user["id"],)
        ).fetchall()

        return {
            "id": user["id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "roles": [row["name"] for row in roles],
            "permissions": [row["permission_key"] for row in permissions],
        }


class FirstAdminSetupDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pillistan - Initial Administrator Setup")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)

        heading = QLabel("Create Your Administrator Account")
        heading.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(heading)

        description = QLabel(
            "This is the first account for your Pillistan system. "
            "Keep your password private and secure."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        form = QFormLayout()

        self.full_name = QLineEdit()
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.confirm_password = QLineEdit()

        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password.setEchoMode(QLineEdit.EchoMode.Password)

        self.username.setPlaceholderText("e.g. administrator")
        self.password.setPlaceholderText("At least 12 characters and one number")

        form.addRow("Full name:", self.full_name)
        form.addRow("Username:", self.username)
        form.addRow("Password:", self.password)
        form.addRow("Confirm password:", self.confirm_password)

        layout.addLayout(form)

        button = QPushButton("Create Administrator Account")
        button.clicked.connect(self.create_account)
        layout.addWidget(button)

    def create_account(self):
        if self.password.text() != self.confirm_password.text():
            QMessageBox.warning(
                self, "Password mismatch",
                "The two passwords do not match."
            )
            return

        try:
            create_initial_admin(
                self.username.text(),
                self.full_name.text(),
                self.password.text()
            )
            QMessageBox.information(
                self, "Administrator Created",
                "Your administrator account has been created. "
                "Please log in."
            )
            self.accept()
        except (ValueError, sqlite3.IntegrityError) as error:
            QMessageBox.warning(self, "Setup Error", str(error))


class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pillistan - Login")
        self.setMinimumWidth(400)
        self.authenticated_user = None

        layout = QVBoxLayout(self)

        heading = QLabel("PILLISTAN")
        heading.setStyleSheet("font-size: 25px; font-weight: bold;")
        layout.addWidget(heading)

        subtitle = QLabel("Nourish to Flourish")
        layout.addWidget(subtitle)

        form = QFormLayout()

        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)

        self.username.setPlaceholderText("Username")
        self.password.setPlaceholderText("Password")

        form.addRow("Username:", self.username)
        form.addRow("Password:", self.password)
        layout.addLayout(form)

        buttons = QHBoxLayout()

        login_button = QPushButton("Login")
        cancel_button = QPushButton("Exit")

        login_button.clicked.connect(self.login)
        cancel_button.clicked.connect(self.reject)

        buttons.addWidget(login_button)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)

        self.password.returnPressed.connect(self.login)

    def login(self):
        user = authenticate_user(
            self.username.text(),
            self.password.text()
        )

        if not user:
            QMessageBox.warning(
                self,
                "Login Failed",
                "Login unsuccessful. Check your credentials, "
                "account status or temporary lockout."
            )
            self.password.clear()
            self.password.setFocus()
            return

        self.authenticated_user = user
        self.accept()