"""The agent's tools: the actions it can take in the pet store.

Each tool returns a plain dictionary. When something goes wrong, the tool
returns {"error": "..."} instead of crashing, so the agent can read the
problem and try something else.
"""

from datetime import date, datetime

from sqlalchemy import text

from tracebench.db import engine
from tracebench.store.policy_search import search_policies as find_policies


def usd(cents: int) -> float:
    """Turn cents into dollars, e.g. 3499 -> 34.99."""
    return round(cents / 100, 2)


def day(moment: date | datetime | None) -> str | None:
    """Turn a date or an exact moment into a plain date like '2026-09-28'."""
    if moment is None:
        return None
    if isinstance(moment, datetime):
        moment = moment.date()
    return moment.isoformat()


def get_customer(email: str) -> dict:
    """Look up a customer by email, with a summary of their orders."""
    with engine.connect() as conn:
        customer = conn.execute(text("""
            SELECT id, email, name, loyalty_tier
            FROM store.customers
            WHERE lower(email) = lower(:email)
        """), {"email": email.strip()}).mappings().first()

        if customer is None:
            return {"error": f"No customer found with email {email}."}

        orders = conn.execute(text("""
            SELECT id, status, ordered_at, total_cents
            FROM store.orders
            WHERE customer_id = :customer_id
            ORDER BY ordered_at DESC
        """), {"customer_id": customer["id"]}).mappings().all()

    return {
        "name": customer["name"],
        "email": customer["email"],
        "loyalty_tier": customer["loyalty_tier"],
        "orders": [
            {
                "order_id": order["id"],
                "status": order["status"],
                "ordered_on": day(order["ordered_at"]),
                "total_usd": usd(order["total_cents"]),
            }
            for order in orders
        ],
    }


def get_order(order_id: int, customer_email: str) -> dict:
    """Look up one order, but only if it belongs to the customer asking."""
    with engine.connect() as conn:
        order = conn.execute(text("""
            SELECT o.id, o.status, o.ordered_at, o.shipped_at, o.delivered_at,
                   o.total_cents, c.email,
                   COALESCE(
                       (SELECT sum(r.amount_cents)
                        FROM store.refunds AS r
                        WHERE r.order_id = o.id),
                       0
                   ) AS refunded_cents
            FROM store.orders AS o
            JOIN store.customers AS c ON c.id = o.customer_id
            WHERE o.id = :order_id
        """), {"order_id": order_id}).mappings().first()

        if order is None or order["email"].lower() != customer_email.strip().lower():
            return {"error": f"No order {order_id} found for {customer_email}."}

        items = conn.execute(text("""
            SELECT i.sku, p.name, p.category, p.requires_prescription,
                   i.quantity, i.unit_price_cents
            FROM store.order_items AS i
            JOIN store.products AS p ON p.sku = i.sku
            WHERE i.order_id = :order_id
            ORDER BY i.id
        """), {"order_id": order_id}).mappings().all()

    return {
        "order_id": order["id"],
        "status": order["status"],
        "ordered_on": day(order["ordered_at"]),
        "shipped_on": day(order["shipped_at"]),
        "delivered_on": day(order["delivered_at"]),
        "total_usd": usd(order["total_cents"]),
        "refunded_so_far_usd": usd(order["refunded_cents"]),
        "items": [
            {
                "sku": item["sku"],
                "name": item["name"],
                "category": item["category"],
                "requires_prescription": item["requires_prescription"],
                "quantity": item["quantity"],
                "unit_price_usd": usd(item["unit_price_cents"]),
            }
            for item in items
        ],
    }


def check_inventory(product: str) -> dict:
    """Find products by SKU or by words in their name, with stock levels."""
    words = product.lower().replace(",", " ").split()
    if not words:
        return {"error": "Please give a product name or SKU."}

    conditions = " AND ".join(f"lower(name) LIKE :word{i}" for i in range(len(words)))
    params = {f"word{i}": f"%{word}%" for i, word in enumerate(words)}
    params["sku"] = product.strip().upper()

    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT sku, name, price_cents, stock, restock_date, requires_prescription
            FROM store.products
            WHERE sku = :sku OR ({conditions})
            ORDER BY sku
            LIMIT 5
        """), params).mappings().all()

    if not rows:
        return {"error": f"No products found matching '{product}'."}

    return {
        "products": [
            {
                "sku": row["sku"],
                "name": row["name"],
                "price_usd": usd(row["price_cents"]),
                "in_stock": row["stock"] > 0,
                "stock": row["stock"],
                "restock_date": day(row["restock_date"]),
                "requires_prescription": row["requires_prescription"],
            }
            for row in rows
        ],
    }


def search_policies(query: str) -> dict:
    """Find the store policies most relevant to a question."""
    results = find_policies(query, limit=3)
    if not results:
        return {"error": f"No policies matched '{query}'. Try different words."}

    return {
        "policies": [
            {"policy_id": policy["id"], "title": policy["title"], "text": policy["body"]}
            for policy in results
        ],
    }

AGENT_REFUND_LIMIT_CENTS = 10_000


def issue_refund(order_id: int, customer_email: str, amount_usd: float, reason: str) -> dict:
    """Refund money on a delivered order, within the store's hard limits."""
    amount_cents = round(amount_usd * 100)
    if amount_cents <= 0:
        return {"error": "The refund amount must be more than $0.00."}
    if not reason.strip():
        return {"error": "Every refund needs a reason."}

    with engine.begin() as conn:
        order = conn.execute(text("""
            SELECT o.id, o.status, o.total_cents, c.email
            FROM store.orders AS o
            JOIN store.customers AS c ON c.id = o.customer_id
            WHERE o.id = :order_id
            FOR UPDATE OF o
        """), {"order_id": order_id}).mappings().first()

        if order is None or order["email"].lower() != customer_email.strip().lower():
            return {"error": f"No order {order_id} found for {customer_email}."}

        if order["status"] != "delivered":
            return {
                "error": f"Order {order_id} is '{order['status']}'. "
                "Only delivered orders can be refunded."
            }

        refunded_cents = conn.execute(text("""
            SELECT COALESCE(sum(amount_cents), 0)
            FROM store.refunds
            WHERE order_id = :order_id
        """), {"order_id": order_id}).scalar_one()

        after_refund = refunded_cents + amount_cents
        if after_refund > order["total_cents"]:
            left = usd(order["total_cents"] - refunded_cents)
            return {"error": f"Refund too large: only ${left:.2f} is left to refund on order {order_id}."}
        if after_refund > AGENT_REFUND_LIMIT_CENTS:
            return {
                "error": "This refund would bring the total refunded on this order over "
                "$100.00. Escalate it to a human instead."
            }

        refund_id = conn.execute(text("""
            INSERT INTO store.refunds (order_id, amount_cents, reason)
            VALUES (:order_id, :amount_cents, :reason)
            RETURNING id
        """), {
            "order_id": order_id,
            "amount_cents": amount_cents,
            "reason": reason.strip(),
        }).scalar_one()

    return {
        "refund_id": refund_id,
        "order_id": order_id,
        "amount_usd": usd(amount_cents),
        "total_refunded_on_order_usd": usd(after_refund),
        "message": "Refund issued. It will reach the original payment method within 5–7 business days.",
    }


def escalate_to_human(
    reason: str,
    customer_email: str | None = None,
    order_id: int | None = None,
) -> dict:
    """Hand the case to a human specialist."""
    if not reason.strip():
        return {"error": "Every escalation needs a reason."}

    with engine.begin() as conn:
        customer_id = None
        if customer_email:
            customer_id = conn.execute(text("""
                SELECT id FROM store.customers WHERE lower(email) = lower(:email)
            """), {"email": customer_email.strip()}).scalar_one_or_none()

        if order_id is not None:
            exists = conn.execute(
                text("SELECT 1 FROM store.orders WHERE id = :order_id"),
                {"order_id": order_id},
            ).first()
            if exists is None:
                return {"error": f"No order {order_id} exists. Check the number, or escalate without it."}

        escalation_id = conn.execute(text("""
            INSERT INTO store.escalations (customer_id, order_id, reason)
            VALUES (:customer_id, :order_id, :reason)
            RETURNING id
        """), {
            "customer_id": customer_id,
            "order_id": order_id,
            "reason": reason.strip(),
        }).scalar_one()

    return {
        "escalation_id": escalation_id,
        "message": "Escalated. A specialist will reply within 1 business day.",
    }


if __name__ == "__main__":
    import json

    from tracebench.store.seed import seed

    with engine.connect() as conn:
        email = conn.execute(text("SELECT email FROM store.customers WHERE id = 1")).scalar_one()
        shipped_order, shipped_email = conn.execute(text("""
            SELECT o.id, c.email
            FROM store.orders AS o
            JOIN store.customers AS c ON c.id = o.customer_id
            WHERE o.status = 'shipped'
            ORDER BY o.id
            LIMIT 1
        """)).one()

    customer = get_customer(email)
    first_order = customer["orders"][0]["order_id"]

    examples = {
        "get_customer": customer,
        "get_order (right email)": get_order(first_order, email),
        "get_order (wrong email)": get_order(first_order, "someone.else@example.com"),
        "check_inventory('30 lb kibble')": check_inventory("30 lb kibble"),
        "check_inventory('feather wand')": check_inventory("feather wand"),
        "search_policies('damaged refund')": search_policies("damaged refund"),
        "issue_refund $24.99 (allowed)": issue_refund(
            first_order, email, 24.99, "Cat food bag arrived torn"
        ),
        "issue_refund $80.00 more (over the $100 limit)": issue_refund(
            first_order, email, 80.00, "Customer changed their mind"
        ),
        "issue_refund (wrong email)": issue_refund(
            first_order, "someone.else@example.com", 10.00, "Test"
        ),
        "issue_refund (order not delivered yet)": issue_refund(
            shipped_order, shipped_email, 10.00, "Test"
        ),
        "escalate_to_human": escalate_to_human(
            "Customer wants a refund over $100", email, first_order
        ),
    }
    for title, result in examples.items():
        print(f"\n=== {title} ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))

    print("\nResetting the store...")
    seed()