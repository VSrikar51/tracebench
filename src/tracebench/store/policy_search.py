"""Load the store's policy documents into Postgres and search them."""

from pathlib import Path

from sqlalchemy import text

from tracebench.db import engine

POLICY_DIR = Path(__file__).parent / "policies"


def read_policies() -> list[dict]:
    """Read every policy file and split it into an id, a title, and a body."""
    policies = []
    for path in sorted(POLICY_DIR.glob("*.md")):
        content = path.read_text().strip()
        first_line, _, body = content.partition("\n")
        policies.append({
            "id": path.stem,
            "title": first_line.removeprefix("# ").strip(),
            "body": body.strip(),
        })
    return policies


def load_policies() -> int:
    """Replace the policies in the database with the ones in the files."""
    policies = read_policies()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM store.policies"))
        conn.execute(
            text("INSERT INTO store.policies (id, title, body) VALUES (:id, :title, :body)"),
            policies,
        )
    return len(policies)

def search_policies(query: str, limit: int = 3) -> list[dict]:
    """Find the policies that best match a question, best match first."""
    sql = text("""
        WITH q AS (
            SELECT replace(plainto_tsquery('english', :query)::text, '&', '|')::tsquery AS query
        )
        SELECT p.id, p.title, p.body, ts_rank(p.search_vector, q.query) AS score
        FROM store.policies AS p, q
        WHERE p.search_vector @@ q.query
        ORDER BY score DESC, p.id
        LIMIT :limit
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"query": query, "limit": limit}).mappings().all()
    return [dict(row) for row in rows]


if __name__ == "__main__":
    import sys

    question = " ".join(sys.argv[1:])
    for policy in search_policies(question):
        print(f"{policy['score']:.3f}  {policy['id']}")