"""Database connection for tracebench."""

from sqlalchemy import create_engine, text

from tracebench.config import settings

engine = create_engine(settings.database_url)


def check_connection() -> str:
    """Ask the database for its version, to prove we can talk to it."""
    with engine.connect() as conn:
        return conn.execute(text("SELECT version()")).scalar_one()


if __name__ == "__main__":
    print(check_connection())