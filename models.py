
from sqlalchemy import (
    Column, Integer, String, Text, Numeric, Boolean,
    DateTime, Date, ForeignKey, CheckConstraint,
    UniqueConstraint, Index, text, func
)
from database import Base


# ============================================================
# PRODUCT MANAGEMENT
# ============================================================

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(50), unique=True, nullable=False, index=True)
    barcode = Column(String(100), nullable=True)
    name = Column(String(200), nullable=False)
    brand = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    unit = Column(String(30), default="unit")
    purchase_price = Column(Numeric(12, 2), default=0, nullable=False)
    selling_price = Column(Numeric(12, 2), default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_archived = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )


# ============================================================
# INVENTORY MANAGEMENT
# ============================================================

class InventoryBatch(Base):
    __tablename__ = "inventory_batches"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False,
        index=True
    )

    purchase_item_id = Column(
        Integer, ForeignKey("purchase_items.id"), nullable=True, index=True
    )
    supplier_id = Column(
        Integer, ForeignKey("suppliers.id"), nullable=True, index=True
    )

    batch_number = Column(String(100), nullable=True)
    received_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=True)

    received_quantity = Column(Numeric(12, 3), nullable=False)
    remaining_quantity = Column(Numeric(12, 3), nullable=False)

    unit_cost = Column(Numeric(12, 2), nullable=False)
    supplier = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False,
        index=True
    )
    batch_id = Column(
        Integer,
        ForeignKey("inventory_batches.id"),
        nullable=True,
        index=True
    )

    movement_type = Column(String(50), nullable=False)
    quantity_change = Column(Numeric(12, 3), nullable=False)

    reference_type = Column(String(50), nullable=True)
    reference_id = Column(Integer, nullable=True)

    note = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


# ============================================================
# SUPPLIER MANAGEMENT
# ============================================================

class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    phone = Column(String(30), nullable=True)
    address = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


# ============================================================
# CUSTOMER MANAGEMENT
# ============================================================

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    customer_code = Column(
        String(50),
        unique=True,
        nullable=True,
        index=True
    )

    name = Column(String(200), nullable=False)
    phone = Column(String(30), nullable=True)
    email = Column(String(150), nullable=True)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)

    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, server_default=func.now())


# ============================================================
# PURCHASE MANAGEMENT
# ============================================================

class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(
        Integer,
        ForeignKey("suppliers.id"),
        nullable=False
    )

    invoice_number = Column(String(100), nullable=True)
    purchase_date = Column(Date, nullable=False)

    subtotal = Column(Numeric(12, 2), default=0, nullable=False)
    discount = Column(Numeric(12, 2), default=0, nullable=False)
    other_charges = Column(Numeric(12, 2), default=0, nullable=False)
    total_amount = Column(Numeric(12, 2), default=0, nullable=False)

    paid_amount = Column(Numeric(12, 2), default=0, nullable=False)
    balance_amount = Column(Numeric(12, 2), default=0, nullable=False)

    status = Column(String(30), default="received", nullable=False)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())


class PurchaseItem(Base):
    __tablename__ = "purchase_items"

    id = Column(Integer, primary_key=True, index=True)
    purchase_id = Column(
        Integer,
        ForeignKey("purchases.id"),
        nullable=False
    )
    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False
    )

    batch_number = Column(String(100), nullable=True)
    expiry_date = Column(Date, nullable=True)

    quantity = Column(Numeric(12, 3), nullable=False)
    unit_cost = Column(Numeric(12, 2), nullable=False)
    line_total = Column(Numeric(12, 2), nullable=False)


class SupplierPayment(Base):
    __tablename__ = "supplier_payments"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(
        Integer,
        ForeignKey("suppliers.id"),
        nullable=False
    )
    purchase_id = Column(
        Integer,
        ForeignKey("purchases.id"),
        nullable=True
    )

    payment_date = Column(Date, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    payment_method = Column(String(50), default="cash")
    reference_number = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())


# ============================================================
# ACCOUNTING FOUNDATION
# ============================================================

class AccountingPeriod(Base):
    __tablename__ = "accounting_periods"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    status = Column(String(20), default="open", nullable=False)

    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "end_date >= start_date",
            name="ck_accounting_period_dates"
        ),
    )


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)

    code = Column(String(30), nullable=False, unique=True, index=True)
    name = Column(String(200), nullable=False)

    account_type = Column(String(30), nullable=False)
    normal_balance = Column(String(10), nullable=False)

    parent_id = Column(
        Integer,
        ForeignKey("accounts.id"),
        nullable=True,
        index=True
    )

    description = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    is_system = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    __table_args__ = (
        Index(
            "ux_journal_entries_reversal_of_id",
            "reversal_of_id",
            unique=True,
            sqlite_where=text("reversal_of_id IS NOT NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    entry_number = Column(
        String(50),
        nullable=False,
        unique=True,
        index=True
    )

    entry_date = Column(Date, nullable=False)
    description = Column(Text, nullable=False)

    source_module = Column(String(50), nullable=True)
    reference_type = Column(String(50), nullable=True)
    reference_id = Column(Integer, nullable=True)

    accounting_period_id = Column(
        Integer,
        ForeignKey("accounting_periods.id"),
        nullable=True,
        index=True
    )

    idempotency_key = Column(
        String(150),
        nullable=True,
        unique=True
    )

    status = Column(String(20), default="draft", nullable=False)

    reversal_of_id = Column(
        Integer,
        ForeignKey("journal_entries.id"),
        nullable=True
    )

    created_by = Column(String(100), nullable=True)
    posted_by = Column(String(100), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    posted_at = Column(DateTime, nullable=True)


class JournalEntryLine(Base):
    __tablename__ = "journal_entry_lines"

    id = Column(Integer, primary_key=True, index=True)

    journal_entry_id = Column(
        Integer,
        ForeignKey("journal_entries.id"),
        nullable=False,
        index=True
    )

    account_id = Column(
        Integer,
        ForeignKey("accounts.id"),
        nullable=False,
        index=True
    )

    line_number = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)

    debit = Column(Numeric(14, 2), default=0, nullable=False)
    credit = Column(Numeric(14, 2), default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "journal_entry_id",
            "line_number",
            name="uq_journal_entry_line_number"
        ),
        CheckConstraint(
            "debit >= 0 AND credit >= 0",
            name="ck_journal_line_nonnegative"
        ),
        CheckConstraint(
            "(debit > 0 AND credit = 0) OR "
            "(credit > 0 AND debit = 0)",
            name="ck_journal_line_one_side"
        ),
    )


# ============================================================
# CENTRAL AUDIT LOG
# ============================================================

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    module = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)

    record_type = Column(String(100), nullable=True)
    record_id = Column(Integer, nullable=True)

    user_id = Column(Integer, nullable=True)
    username = Column(String(100), nullable=True)

    old_values = Column(Text, nullable=True)
    new_values = Column(Text, nullable=True)

    reason = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())

class OpeningBalance(Base):
    __tablename__ = "opening_balances"

    id = Column(Integer, primary_key=True, index=True)
    reference_number = Column(String(50), unique=True, nullable=False, index=True)
    opening_date = Column(Date, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="draft", nullable=False)
    total_debit = Column(Numeric(14, 2), default=0, nullable=False)
    total_credit = Column(Numeric(14, 2), default=0, nullable=False)
    journal_entry_id = Column(
        Integer,
        ForeignKey("journal_entries.id"),
        nullable=True
    )
    created_by = Column(String(100), nullable=False)
    posted_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    posted_at = Column(DateTime, nullable=True)


class OpeningBalanceLine(Base):
    __tablename__ = "opening_balance_lines"

    id = Column(Integer, primary_key=True, index=True)
    opening_balance_id = Column(
        Integer,
        ForeignKey("opening_balances.id"),
        nullable=False,
        index=True
    )
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    line_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    debit = Column(Numeric(14, 2), default=0, nullable=False)
    credit = Column(Numeric(14, 2), default=0, nullable=False)

    # Optional links to the underlying business records
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    batch_id = Column(Integer, ForeignKey("inventory_batches.id"), nullable=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)

    quantity = Column(Numeric(12, 3), nullable=True)
    unit_cost = Column(Numeric(12, 2), nullable=True)

    batch_number = Column(String(100), nullable=True)
    received_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)

    created_at = Column(DateTime, server_default=func.now())