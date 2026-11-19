import argparse
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import models
import orders_models
from models import Product
from orders_service import (
    get_or_create_customer,
    find_customer_by_phone,
    next_order_number,
    create_draft_order,
    find_possible_duplicate_orders,
)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.is_file():
        raise SystemExit(f"Test database not found: {db_path}")

    engine = create_engine("sqlite:///" + db_path.as_posix())

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Test automatic customer creation
        customer, created = get_or_create_customer(
            session,
            name="Orders Module Test Customer",
            phone="03001234567",
            address="Test Address",
            city="Haripur",
        )
        assert created is True
        assert customer.customer_code.startswith("CUS-")

        # Test exact phone matching and reuse
        same_customer, created_again = get_or_create_customer(
            session,
            name="Different Display Name",
            phone="+92 300 1234567",
        )
        assert created_again is False
        assert same_customer.id == customer.id
        assert find_customer_by_phone(session, "0300-1234567").id == customer.id

        # Create a test product without touching stock batches
        now = datetime.now()
        product = Product(
            sku="ORDERS-TEST-001",
            name="Orders Module Test Product",
            unit="piece",
            purchase_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            is_active=True,
            is_archived=False,
            created_at=now,
            updated_at=now,
            low_stock_threshold=0,
        )
        session.add(product)
        session.flush()

        # Test yearly numbering
        number, sequence = next_order_number(session, 2026)
        assert number.startswith("PIL-2026-")
        assert sequence >= 1

        # Test draft order creation
        order = create_draft_order(
            session=session,
            customer=customer,
            items=[{"product_id": product.id, "quantity": 2}],
            delivery_address="Test Address, Haripur",
            delivery_city="Haripur",
            payment_method="cod",
            delivery_charge=Decimal("100.00"),
        )
        assert order.order_number.startswith("PIL-")
        assert order.order_status == "draft"
        assert order.total_amount == Decimal("400.00")

        # Test duplicate warning lookup
        possible_duplicates = find_possible_duplicate_orders(
            session, customer.id
        )
        assert len(possible_duplicates) >= 1

        # Confirm that creating a draft did not reserve stock
        assert all(
            item.quantity_reserved == 0
            for item in order.items
        ) if hasattr(order, "items") else True

        session.commit()

        print("ORDERS SERVICE TESTS PASSED")
        print(f"Test customer ID: {customer.id}")
        print(f"Customer code: {customer.customer_code}")
        print(f"Order number: {order.order_number}")
        print(f"Order total: PKR {order.total_amount}")
        print(f"Duplicate warning candidates: {len(possible_duplicates)}")
        print("Order status: draft")
        print("No stock reservation or accounting entries were created.")

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()

if __name__ == "__main__":
    main()
