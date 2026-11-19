from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date,
    Numeric, ForeignKey, Index, UniqueConstraint
)
from database import Base


class CustomerAddress(Base):
    __tablename__ = "customer_addresses"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    label = Column(String(80))
    province = Column(String(80))
    city = Column(String(100))
    address = Column(Text, nullable=False)
    delivery_instructions = Column(Text)
    is_default = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False)


class CustomerLabel(Base):
    __tablename__ = "customer_labels"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    label = Column(String(100), nullable=False)
    label_type = Column(String(20), nullable=False, default="manual")
    created_at = Column(DateTime, nullable=False)


class SalesOrder(Base):
    __tablename__ = "sales_orders"

    id = Column(Integer, primary_key=True)
    order_number = Column(String(30), nullable=False, unique=True, index=True)
    order_year = Column(Integer, nullable=False, index=True)
    order_sequence = Column(Integer, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    order_date = Column(DateTime, nullable=False)
    order_status = Column(String(30), nullable=False, default="draft")
    fulfilment_status = Column(String(30), nullable=False, default="unfulfilled")
    payment_status = Column(String(30), nullable=False, default="unpaid")

    payment_method = Column(String(30), nullable=False, default="cod")
    customer_name = Column(String(200), nullable=False)
    customer_phone = Column(String(50), nullable=False)
    customer_whatsapp = Column(String(50))
    delivery_province = Column(String(80))
    delivery_city = Column(String(100))
    delivery_address = Column(Text, nullable=False)
    delivery_instructions = Column(Text)
    preferred_delivery_date = Column(Date)
    preferred_delivery_time = Column(String(80))

    subtotal = Column(Numeric(14, 2), nullable=False, default=0)
    discount_amount = Column(Numeric(14, 2), nullable=False, default=0)
    delivery_charge = Column(Numeric(14, 2), nullable=False, default=0)
    total_amount = Column(Numeric(14, 2), nullable=False, default=0)
    amount_paid = Column(Numeric(14, 2), nullable=False, default=0)

    source = Column(String(30), nullable=False, default="manual")
    notes = Column(Text)
    cancellation_reason = Column(Text)
    created_by_id = Column(Integer)
    approved_by_id = Column(Integer)
    confirmed_at = Column(DateTime)
    cancelled_at = Column(DateTime)
    dispatched_at = Column(DateTime)
    delivered_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime)


class SalesOrderItem(Base):
    __tablename__ = "sales_order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("sales_orders.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    product_name_snapshot = Column(String(250), nullable=False)
    sku_snapshot = Column(String(100))
    quantity_ordered = Column(Numeric(14, 3), nullable=False)
    quantity_reserved = Column(Numeric(14, 3), nullable=False, default=0)
    quantity_dispatched = Column(Numeric(14, 3), nullable=False, default=0)
    quantity_delivered = Column(Numeric(14, 3), nullable=False, default=0)
    unit_price = Column(Numeric(14, 2), nullable=False)
    discount_amount = Column(Numeric(14, 2), nullable=False, default=0)
    line_total = Column(Numeric(14, 2), nullable=False)
    replacement_product_id = Column(Integer, ForeignKey("products.id"))
    substitution_approved = Column(Boolean, nullable=False, default=False)
    notes = Column(Text)
    created_at = Column(DateTime, nullable=False)


class OrderPayment(Base):
    __tablename__ = "order_payments"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("sales_orders.id"), nullable=False, index=True)
    payment_method = Column(String(30), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    payment_status = Column(String(30), nullable=False, default="pending")
    payment_date = Column(DateTime)
    transaction_reference = Column(String(150))
    account_id = Column(Integer, ForeignKey("accounts.id"))
    verified_by_id = Column(Integer)
    notes = Column(Text)
    created_at = Column(DateTime, nullable=False)


class StockReservation(Base):
    __tablename__ = "stock_reservations"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("sales_orders.id"), nullable=False, index=True)
    order_item_id = Column(Integer, ForeignKey("sales_order_items.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("inventory_batches.id"), nullable=False, index=True)
    quantity_reserved = Column(Numeric(14, 3), nullable=False)
    quantity_dispatched = Column(Numeric(14, 3), nullable=False, default=0)
    reservation_status = Column(String(30), nullable=False, default="reserved")
    reserved_at = Column(DateTime, nullable=False)
    released_at = Column(DateTime)
    notes = Column(Text)


class Courier(Base):
    __tablename__ = "couriers"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False, unique=True)
    contact_person = Column(String(150))
    phone = Column(String(50))
    email = Column(String(150))
    account_reference = Column(String(150))
    tracking_url_template = Column(Text)
    service_types = Column(Text)
    notes = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime)


class DispatchParcel(Base):
    __tablename__ = "dispatch_parcels"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("sales_orders.id"), nullable=False, index=True)
    dispatch_reference = Column(String(40), nullable=False, unique=True, index=True)
    parcel_number = Column(Integer, nullable=False, default=1)
    parcel_count = Column(Integer, nullable=False, default=1)

    courier_id = Column(Integer, ForeignKey("couriers.id"))
    courier_tracking_number = Column(String(120), index=True)
    tracking_url = Column(Text)
    parcel_status = Column(String(40), nullable=False, default="prepared")

    weight = Column(Numeric(12, 3))
    weight_unit = Column(String(10), default="kg")
    length = Column(Numeric(12, 2))
    width = Column(Numeric(12, 2))
    height = Column(Numeric(12, 2))
    dimension_unit = Column(String(10), default="cm")

    customer_delivery_charge = Column(Numeric(14, 2), nullable=False, default=0)
    actual_courier_cost = Column(Numeric(14, 2), nullable=False, default=0)
    packaging_cost = Column(Numeric(14, 2), nullable=False, default=0)

    handed_to_courier_at = Column(DateTime)
    delivered_at = Column(DateTime)
    recipient_name = Column(String(150))
    delivery_outcome = Column(String(50))
    proof_of_delivery_path = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint("order_id", "parcel_number", name="uq_order_parcel_number"),
    )


class DispatchParcelItem(Base):
    """
    Records the exact reserved stock quantities handed to a courier
    in a particular parcel.
    """
    __tablename__ = "dispatch_parcel_items"

    id = Column(Integer, primary_key=True)
    parcel_id = Column(
        Integer,
        ForeignKey("dispatch_parcels.id"),
        nullable=False,
        index=True
    )
    reservation_id = Column(
        Integer,
        ForeignKey("stock_reservations.id"),
        nullable=False,
        index=True
    )
    order_item_id = Column(
        Integer,
        ForeignKey("sales_order_items.id"),
        nullable=False,
        index=True
    )
    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False,
        index=True
    )
    quantity_dispatched = Column(Numeric(14, 3), nullable=False)
    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "parcel_id",
            "reservation_id",
            name="uq_parcel_reservation"
        ),
    )


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("sales_orders.id"), nullable=False, index=True)
    parcel_id = Column(Integer, ForeignKey("dispatch_parcels.id"), index=True)
    status_type = Column(String(30), nullable=False)
    old_status = Column(String(40))
    new_status = Column(String(40), nullable=False)
    notes = Column(Text)
    changed_by_id = Column(Integer)
    changed_at = Column(DateTime, nullable=False)


Index("ix_order_year_sequence", SalesOrder.order_year, SalesOrder.order_sequence)
