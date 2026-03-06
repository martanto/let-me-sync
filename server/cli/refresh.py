"""
Refresh script for local development only.
Drops all tables, deletes all uploaded files, recreates the schema, and re-runs seed.

Only runs when DEBUG=true and APP_ENV != production in .env.

Usage:
    uv run server:refresh
"""

import shutil
import subprocess

from server.config import APP_ENV, DATA_ROOT, DEBUG
from server.database.connection import SessionLocal, check_db_connection

from .seed import seed


def refresh() -> None:
    check_db_connection()

    print("=== Refresh: dropping and recreating schema via Alembic ===")
    subprocess.run(["uv", "run", "alembic", "downgrade", "base"], check=True)
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    print("Schema recreated.")

    if DATA_ROOT.exists():
        shutil.rmtree(DATA_ROOT)
        DATA_ROOT.mkdir(parents=True)
        print("Uploads directory cleared.")

    print("\n=== Re-running seed ===")
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()

    print("\nRefresh complete.")


if __name__ == "__main__":
    if not DEBUG:
        print("Refresh is disabled. Set DEBUG=true in .env to enable.")
        raise SystemExit(0)
    if APP_ENV == "production":
        print("Refresh is not allowed when APP_ENV=production.")
        raise SystemExit(0)
    refresh()
