from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import func

from models import Customer, Product
from orders_models import SalesOrder, SalesOrderItem


def normalize_phone(phone):
    """Normalize Pakistani mobile numbers in local and +92 formats."""
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())

    # Convert +92 3XX XXXXXXX to 03XX XXXXXXX
    if len(digits) == 12 and digits.startswith("92"):
        digits = "0" + digits[2:]

    # Accept a 10-digit mobile number without its leading zero
    elif len(digits) == 10 and digits.startswith("3"):
        digits = "0" + digits

    return digits


def find_customer_by_phone(session, phone):
    """Find an exact normalized phone match; never merge by name."""
    normalized = normalize_phone(phone)
    if not normalized:
        return None

    matches = [
        customer for customer in session.query(Customer).all()
        if normalize_phone(customer.phone) == normalized
    ]

    if len(matches) > 1:
        raise ValueError(
            "More than one customer has this phone number. "
            "Please resolve the duplicate customer records before proceeding."
        )

    return matches[0] if matches else None


def get_or_create_customer(
    session, name, phone, email=None, address=None, city=None, notes=None
):
    """Reuse an exact phone match; otherwise create a new customer."""
    name = str(name or "").strip()
    phone = str(phone or "").strip()

    if not name:
        raise ValueError("Customer name is required.")
    if not normalize_phone(phone):
        raise ValueError("A valid customer phone number is required.")

    existing = find_customer_by_phone(session, phone)
    if existing:
        return existing, False

    customer = Customer(
        name=name,
        phone=phone,
        email=email,
        address=address,
        city=city,
        notes=notes,
        is_active=True,
        created_at=datetime.now(),
    )
    session.add(customer)
    session.flush()

    if not customer.customer_code:
        customer.customer_code = f"CUS-{customer.id:06d}"
        session.flush()

    return customer, True


def next_order_number(session, year=None):
    """Generate the next yearly order number, e.g. PIL-2026-000001."""
    year = int(year or datetime.now().year)

    highest = (
        session.query(func.max(SalesOrder.order_sequence))
        .filter(SalesOrder.order_year == year)
        .scalar()
    ) or 0

    return f"PIL-{year}-{highest + 1:06d}", highest + 1


def find_possible_duplicate_orders(session, customer_id, hours=24):
    """Return recent non-cancelled orders for a duplicate-order warning."""
    cutoff = datetime.now() - timedelta(hours=hours)

    return (
        session.query(SalesOrder)
        .filter(
            SalesOrder.customer_id == customer_id,
            SalesOrder.created_at >= cutoff,
            SalesOrder.order_status != "cancelled",
        )
        .order_by(SalesOrder.created_at.desc())
        .all()
    )


def create_draft_order(
    session,
    customer,
    items,
    delivery_address,
    delivery_city=None,
    delivery_province=None,
    customer_whatsapp=None,
    delivery_instructions=None,
    payment_method="cod",
    delivery_charge=0,
    discount_amount=0,
    source="manual",
    notes=None,
    created_by_id=None,
):
    """
    Create a draft order and item snapshots.
    This function does not reserve or deduct stock and does not post accounting.
    The caller controls commit/rollback.
    """
    if not customer or not customer.id:
        raise ValueError("A saved customer record is required.")
    if not str(delivery_address or "").strip():
        raise ValueError("Delivery address is required.")
    if not items:
        raise ValueError("At least one order item is required.")

    allowed_payment_methods = {
        "cod", "cash", "bank_transfer", "easypaisa", "jazzcash", "other"
    }
    if payment_method not in allowed_payment_methods:
        raise ValueError("Unsupported payment method.")

    try:
        delivery_charge = Decimal(str(delivery_charge or 0))
        discount_amount = Decimal(str(discount_amount or 0))
    except InvalidOperation:
        raise ValueError("Delivery charge and discount must be valid amounts.")

    if delivery_charge < 0 or discount_amount < 0:
        raise ValueError("Delivery charge and discount cannot be negative.")

    prepared_items = []
    subtotal = Decimal("0.00")

    for item in items:
        product_id = item.get("product_id")
        try:
            quantity = Decimal(str(item.get("quantity", 0)))
        except InvalidOperation:
            raise ValueError("Item quantity must be a valid number.")

        if not product_id or quantity <= 0:
            raise ValueError("Every item needs a product and a quantity greater than zero.")

        product = session.get(Product, int(product_id))
        if not product:
            raise ValueError(f"Product ID {product_id} was not found.")
        if not product.is_active or getattr(product, "is_archived", False):
            raise ValueError(f"Product '{product.name}' is inactive or archived.")

        try:
            unit_price = Decimal(str(
                item.get("unit_price", product.selling_price)
            ))
        except InvalidOperation:
            raise ValueError(f"Invalid selling price for '{product.name}'.")

        if unit_price < 0:
            raise ValueError("Selling price cannot be negative.")

        line_total = quantity * unit_price
        subtotal += line_total

        prepared_items.append({
            "product": product,
            "quantity": quantity,
            "unit_price": unit_price,
            "line_total": line_total,
        })

    if discount_amount > subtotal:
        raise ValueError("Order discount cannot exceed the items subtotal.")

    total_amount = subtotal - discount_amount + delivery_charge
    now = datetime.now()
    order_year = now.year
    order_number, sequence = next_order_number(session, order_year)

    order = SalesOrder(
        order_number=order_number,
        order_year=order_year,
        order_sequence=sequence,
        customer_id=customer.id,
        order_date=now,
        order_status="draft",
        fulfilment_status="unfulfilled",
        payment_status="unpaid",
        payment_method=payment_method,
        customer_name=customer.name,
        customer_phone=customer.phone or "",
        customer_whatsapp=customer_whatsapp,
        delivery_province=delivery_province,
        delivery_city=delivery_city or customer.city,
        delivery_address=str(delivery_address).strip(),
        delivery_instructions=delivery_instructions,
        subtotal=subtotal,
        discount_amount=discount_amount,
        delivery_charge=delivery_charge,
        total_amount=total_amount,
        amount_paid=Decimal("0.00"),
        source=source,
        notes=notes,
        created_by_id=created_by_id,
        created_at=now,
        updated_at=now,
    )

    session.add(order)
    session.flush()

    for prepared in prepared_items:
        product = prepared["product"]
        session.add(SalesOrderItem(
            order_id=order.id,
            product_id=product.id,
            product_name_snapshot=product.name,
            sku_snapshot=product.sku,
            quantity_ordered=prepared["quantity"],
            quantity_reserved=Decimal("0"),
            quantity_dispatched=Decimal("0"),
            quantity_delivered=Decimal("0"),
            unit_price=prepared["unit_price"],
            discount_amount=Decimal("0.00"),
            line_total=prepared["line_total"],
            substitution_approved=False,
            created_at=now,
        ))

    session.flush()
    return order
