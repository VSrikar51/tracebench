"""Fill the pet store with fake data.

Running this wipes the store tables and refills them. The same seed number
always produces exactly the same data, so eval answers never change.
"""

import random
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import text

from tracebench.config import settings
from tracebench.db import engine

SEED = 42

# (sku, name, category, price_cents, stock, restock_date, requires_prescription)
PRODUCTS = [
    ("DOG-KIBBLE-15LB", "Chicken & Rice Dog Kibble, 15 lb", "dog_food", 3499, 40, None, False),
    ("DOG-KIBBLE-30LB", "Chicken & Rice Dog Kibble, 30 lb", "dog_food", 5999, 0, date(2026, 10, 14), False),
    ("DOG-TREATS-SALMON", "Salmon Jerky Dog Treats", "dog_treats", 1299, 85, None, False),
    ("CAT-FOOD-WET-24", "Tuna Pate Wet Cat Food, 24 pack", "cat_food", 3299, 25, None, False),
    ("CAT-FOOD-DRY-7LB", "Indoor Formula Dry Cat Food, 7 lb", "cat_food", 2499, 0, date(2026, 10, 9), False),
    ("CAT-LITTER-25LB", "Clumping Cat Litter, 25 lb", "litter", 1899, 60, None, False),
    ("DOG-TOY-ROPE", "Braided Rope Tug Toy", "toys", 999, 120, None, False),
    ("CAT-TOY-WAND", "Feather Wand Cat Toy", "toys", 799, 0, None, False),
    ("DOG-BED-LARGE", "Orthopedic Dog Bed, Large", "beds", 8999, 8, None, False),
    ("CAT-TREE-5FT", "5 ft Cat Tree with Scratching Posts", "furniture", 12999, 3, None, False),
    ("DOG-LEASH-6FT", "Reflective Dog Leash, 6 ft", "accessories", 1599, 45, None, False),
    ("FISH-TANK-20G", "20 Gallon Aquarium Kit", "aquatics", 14999, 5, None, False),
    ("FLEA-TICK-DOG-6", "Flea & Tick Chews for Dogs, 6 count", "health", 6499, 30, None, False),
    ("RX-DOG-RENAL-8LB", "Prescription Renal Care Dog Food, 8 lb", "prescription_food", 7299, 15, None, True),
    ("RX-CAT-URINARY-6LB", "Prescription Urinary Care Cat Food, 6 lb", "prescription_food", 5899, 0, date(2026, 10, 20), True),
]

PRODUCT_COLUMNS = [
    "sku", "name", "category", "price_cents", "stock", "restock_date", "requires_prescription",
]

FIRST_NAMES = [
    "Ava", "Liam", "Maya", "Noah", "Priya", "Ethan", "Sofia", "Lucas",
    "Aisha", "Mateo", "Chloe", "Arjun", "Emma", "Diego", "Hannah",
]

LAST_NAMES = [
    "Patel", "Garcia", "Nguyen", "Smith", "Kim", "Rossi", "Okafor",
    "Johnson", "Chen", "Lopez", "Reddy", "Brown", "Silva", "Walker", "Haddad",
]


def at(day: date, rng: random.Random) -> datetime:
    """Turn a calendar day into an exact moment, at a random hour of the day."""
    return datetime.combine(day, time(hour=rng.randint(8, 20)), tzinfo=UTC)


def make_customers(rng: random.Random) -> list[dict]:
    today = settings.store_today
    customers = []
    for i in range(1, 31):
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        customers.append({
            "id": i,
            "email": f"{first.lower()}.{last.lower()}{i}@example.com",
            "name": f"{first} {last}",
            "loyalty_tier": "gold" if rng.random() < 0.25 else "standard",
            "created_at": at(today - timedelta(days=rng.randint(100, 700)), rng),
        })
    return customers


def make_orders(rng: random.Random, customers: list[dict]) -> tuple[list[dict], list[dict]]:
    today = settings.store_today
    orders, items = [], []
    order_id = 1001

    for customer in customers:
        for _ in range(rng.randint(1, 4)):
            ordered_on = today - timedelta(days=rng.randint(0, 90))
            age_in_days = (today - ordered_on).days

            if rng.random() < 0.05:
                status = "cancelled"
            elif age_in_days < 2:
                status = "processing"
            elif age_in_days < 5:
                status = "shipped"
            else:
                status = "delivered"

            shipped = status in ("shipped", "delivered")
            delivered = status == "delivered"

            total_cents = 0
            for product in rng.sample(PRODUCTS, k=rng.randint(1, 3)):
                sku, price_cents = product[0], product[3]
                quantity = rng.randint(1, 2)
                total_cents += price_cents * quantity
                items.append({
                    "order_id": order_id,
                    "sku": sku,
                    "quantity": quantity,
                    "unit_price_cents": price_cents,
                })

            orders.append({
                "id": order_id,
                "customer_id": customer["id"],
                "status": status,
                "ordered_at": at(ordered_on, rng),
                "shipped_at": at(ordered_on + timedelta(days=1), rng) if shipped else None,
                "delivered_at": at(ordered_on + timedelta(days=4), rng) if delivered else None,
                "total_cents": total_cents,
            })
            order_id += 1

    return orders, items


def seed() -> None:
    rng = random.Random(SEED)
    products = [dict(zip(PRODUCT_COLUMNS, row)) for row in PRODUCTS]
    customers = make_customers(rng)
    orders, items = make_orders(rng, customers)

    with engine.begin() as conn:
        conn.execute(text("""
            TRUNCATE store.escalations, store.refunds, store.order_items,
                     store.orders, store.products, store.customers
            RESTART IDENTITY
        """))

        conn.execute(text("""
            INSERT INTO store.products
                (sku, name, category, price_cents, stock, restock_date, requires_prescription)
            VALUES
                (:sku, :name, :category, :price_cents, :stock, :restock_date, :requires_prescription)
        """), products)

        conn.execute(text("""
            INSERT INTO store.customers (id, email, name, loyalty_tier, created_at)
            VALUES (:id, :email, :name, :loyalty_tier, :created_at)
        """), customers)

        conn.execute(text("""
            INSERT INTO store.orders
                (id, customer_id, status, ordered_at, shipped_at, delivered_at, total_cents)
            VALUES
                (:id, :customer_id, :status, :ordered_at, :shipped_at, :delivered_at, :total_cents)
        """), orders)

        conn.execute(text("""
            INSERT INTO store.order_items (order_id, sku, quantity, unit_price_cents)
            VALUES (:order_id, :sku, :quantity, :unit_price_cents)
        """), items)

        for table in ("customers", "orders"):
            conn.execute(text(f"""
                SELECT setval(
                    pg_get_serial_sequence('store.{table}', 'id'),
                    (SELECT max(id) FROM store.{table})
                )
            """))

    print(
        f"Seeded {len(customers)} customers, {len(products)} products, "
        f"{len(orders)} orders and {len(items)} order items."
    )


if __name__ == "__main__":
    seed()