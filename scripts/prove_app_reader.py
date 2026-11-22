"""Week 3: prove that app_reader can read but not change data.

    python scripts/prove_app_reader.py

Connects with APP_DATABASE_URL, runs one SELECT, one DELETE and one INSERT, and prints
what happened. Nothing can change: app_reader has no write rights, and every statement
is rolled back anyway.
"""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TESTS = [
    "select current_user, count(*) as matches from matches",
    "delete from matches where match_id = 83237",
    "insert into sync_runs (started_at, finished_at, status, trigger) values (now(), now(), 'success', 'manual')",
]

with psycopg.connect(os.environ["APP_DATABASE_URL"], connect_timeout=10) as conn:
    for sql in TESTS:
        print(f"> {sql}")
        try:
            rows = conn.execute(sql).fetchall()
            print(f"  OK: {rows}")
        except psycopg.Error as error:
            print(f"  ERROR: {str(error).strip().splitlines()[0]}")
        conn.rollback()
