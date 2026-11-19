from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QTabWidget, QMessageBox, QInputDialog
)
from PySide6.QtCore import Qt

from database import SessionLocal
from models import Product, ProductCategory, ProductBrand


DEFAULT_CATEGORIES = [
    "Vitamins & Minerals",
    "Herbal & Botanical",
    "Omega & Essential Fatty Acids",
    "Protein & Sports Nutrition",
    "Probiotics & Digestive Health",
    "Joint & Bone Health",
    "Immunity & General Wellness",
    "Women's Health",
    "Men's Health",
    "Children's Health",
    "Skin, Hair & Nails",
    "Other",
]


class CatalogueManager(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Product Categories & Companies / Brands")
        self.resize(760, 540)

        self._seed_existing_values()

        layout = QVBoxLayout(self)
        heading = QLabel("Product Catalogue Settings")
        heading.setStyleSheet("font-size: 21px; font-weight: 700;")
        layout.addWidget(heading)

        subtitle = QLabel(
            "Maintain the product categories and associated companies / brands."
        )
        layout.addWidget(subtitle)

        tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        self.category_list = self._build_tab(
            tabs, "Categories", ProductCategory, "category"
        )
        self.brand_list = self._build_tab(
            tabs, "Companies / Brands", ProductBrand, "company / brand"
        )

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

    def _seed_existing_values(self):
        with SessionLocal() as db:
            category_names = set(DEFAULT_CATEGORIES)
            category_names.update(
                (value or "").strip()
                for value, in db.query(Product.category).all()
                if value and value.strip()
            )

            brand_names = {
                value.strip()
                for value, in db.query(Product.brand).all()
                if value and value.strip()
            }

            for model, names in (
                (ProductCategory, category_names),
                (ProductBrand, brand_names),
            ):
                existing = {
                    item.name.casefold()
                    for item in db.query(model).all()
                }
                for name in sorted(names, key=str.casefold):
                    if name.casefold() not in existing:
                        db.add(model(name=name, is_active=True))
                        existing.add(name.casefold())
            db.commit()

    def _build_tab(self, tabs, title, model, kind):
        page = QDialog()
        layout = QVBoxLayout(page)

        description = QLabel(
            f"Select a {kind} to rename, deactivate or reactivate it."
        )
        layout.addWidget(description)

        item_list = QListWidget()
        item_list.setMinimumHeight(300)
        layout.addWidget(item_list, 1)

        buttons = QHBoxLayout()
        add_button = QPushButton(f"Add {kind.title()}")
        rename_button = QPushButton("Rename Selected")
        toggle_button = QPushButton("Deactivate / Activate")
        refresh_button = QPushButton("Refresh")

        buttons.addWidget(add_button)
        buttons.addWidget(rename_button)
        buttons.addWidget(toggle_button)
        buttons.addWidget(refresh_button)
        layout.addLayout(buttons)

        tabs.addTab(page, title)

        add_button.clicked.connect(lambda: self._add(model, kind, item_list))
        rename_button.clicked.connect(
            lambda: self._rename(model, kind, item_list)
        )
        toggle_button.clicked.connect(
            lambda: self._toggle(model, item_list)
        )
        refresh_button.clicked.connect(
            lambda: self._load(model, item_list)
        )

        self._load(model, item_list)
        return item_list

    def _load(self, model, item_list):
        item_list.clear()
        with SessionLocal() as db:
            records = db.query(model).order_by(model.name).all()
            for record in records:
                suffix = "" if record.is_active else "  [INACTIVE]"
                item = QListWidgetItem(record.name + suffix)
                item.setData(Qt.ItemDataRole.UserRole, record.id)
                item.setData(Qt.ItemDataRole.UserRole + 1, record.name)
                item_list.addItem(item)

    def _selected_id(self, item_list):
        item = item_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _add(self, model, kind, item_list):
        name, accepted = QInputDialog.getText(
            self, f"Add {kind.title()}", f"Enter {kind} name:"
        )
        name = name.strip()
        if not accepted or not name:
            return

        with SessionLocal() as db:
            existing = db.query(model).all()
            if any(item.name.casefold() == name.casefold() for item in existing):
                QMessageBox.warning(
                    self, "Already Exists",
                    f"This {kind} name already exists."
                )
                return
            db.add(model(name=name, is_active=True))
            db.commit()

        self._load(model, item_list)

    def _rename(self, model, kind, item_list):
        record_id = self._selected_id(item_list)
        if record_id is None:
            QMessageBox.information(self, "Select an Item", f"Select a {kind} first.")
            return

        old_name = item_list.currentItem().data(Qt.ItemDataRole.UserRole + 1)
        new_name, accepted = QInputDialog.getText(
            self, f"Rename {kind.title()}", f"New {kind} name:",
            text=old_name
        )
        new_name = new_name.strip()
        if not accepted or not new_name or new_name == old_name:
            return

        with SessionLocal() as db:
            duplicate = db.query(model).all()
            if any(
                item.id != record_id and item.name.casefold() == new_name.casefold()
                for item in duplicate
            ):
                QMessageBox.warning(
                    self, "Already Exists",
                    f"Another {kind} already uses that name."
                )
                return

            record = db.get(model, record_id)
            if not record:
                return

            if model is ProductCategory:
                db.query(Product).filter(
                    Product.category == old_name
                ).update(
                    {Product.category: new_name},
                    synchronize_session=False
                )
            else:
                db.query(Product).filter(
                    Product.brand == old_name
                ).update(
                    {Product.brand: new_name},
                    synchronize_session=False
                )

            record.name = new_name
            db.commit()

        self._load(model, item_list)

    def _toggle(self, model, item_list):
        record_id = self._selected_id(item_list)
        if record_id is None:
            QMessageBox.information(
                self, "Select an Item", "Select a category or company / brand first."
            )
            return

        with SessionLocal() as db:
            record = db.get(model, record_id)
            if not record:
                return
            record.is_active = not record.is_active
            db.commit()

        self._load(model, item_list)
