"""Week 3: when was my data last updated, and what changed in the last 7 days?

    python scripts/status.py          # as the read-only role (APP_DATABASE_URL)
    python scripts/status.py --owner  # as the owner (DATABASE_URL), e.g. before app_reader exists

Milestone 4 shows the same numbers in the app; Milestone 5's chatbot uses them to warn
when the data is stale.
"""

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

LAST_SUCCESS = """
select finished_at, now() - finished_at as age, trigger
from sync_runs where status = 'success'
order by finished_at desc limit 1
"""

LAST_7_DAYS = """
select count(*)                                    as runs,
       count(*) filter (where status = 'success') as success,
       count(*) filter (where status = 'partial') as partial,
       count(*) filter (where status = 'failed')  as failed,
       coalesce(sum(records_inserted), 0)         as inserted,
       coalesce(sum(records_updated), 0)          as updated,
       coalesce(sum(records_deleted), 0)          as deleted
from sync_runs where started_at > now() - interval '7 days'
"""

RECENT_RUNS = """
select run_id, started_at, status, trigger, records_fetched, records_inserted,
       records_updated, coalesce(matchdays_synced, '-'), coalesce(error_message, '')
from sync_runs order by started_at desc limit 10
"""

CHANGED_ROWS = """
select 'matches' as tbl, count(*) filter (where first_seen_at > now() - interval '7 days'),
       count(*) filter (where last_updated_at > now() - interval '7 days'
                          and first_seen_at <= now() - interval '7 days') from matches
union all
select 'goals', count(*) filter (where first_seen_at > now() - interval '7 days'),
       count(*) filter (where last_updated_at > now() - interval '7 days'
                          and first_seen_at <= now() - interval '7 days') from goals
union all
select 'players', count(*) filter (where first_seen_at > now() - interval '7 days'),
       count(*) filter (where last_updated_at > now() - interval '7 days'
                          and first_seen_at <= now() - interval '7 days') from players
union all
select 'standings', count(*) filter (where first_seen_at > now() - interval '7 days'),
       count(*) filter (where last_updated_at > now() - interval '7 days'
                          and first_seen_at <= now() - interval '7 days') from standings
"""


def main():
    load_dotenv(ROOT / ".env")
    variable = "DATABASE_URL" if "--owner" in sys.argv else "APP_DATABASE_URL"
    url = os.environ.get(variable)
    if not url:
        sys.exit(f"[FAIL] {variable} is not set in .env")
    with psycopg.connect(url, connect_timeout=10) as conn:
        last = conn.execute(LAST_SUCCESS).fetchone()
        week = conn.execute(LAST_7_DAYS).fetchone()
        runs = conn.execute(RECENT_RUNS).fetchall()
        changed = conn.execute(CHANGED_ROWS).fetchall()

    if last:
        hours = last[1].total_seconds() / 3600
        print(f"Last successful sync: {last[0]:%Y-%m-%d %H:%M} UTC ({hours:.1f} hours ago, {last[2]})")
        if hours > 24:
            print("  WARNING: data is more than 24 hours old, check the GitHub Actions runs.")
    else:
        print("Last successful sync: never")

    print(f"\nLast 7 days: {week[0]} runs ({week[1]} success, {week[2]} partial, {week[3]} failed), "
          f"{week[4]} rows inserted, {week[5]} updated, {week[6]} deleted")
    print(f"\n{'table':<11}{'new':>6}{'changed':>9}   (rows, last 7 days)")
    for table, new, upd in changed:
        print(f"{table:<11}{new:>6}{upd:>9}")

    print(f"\n{'run':>4}  {'started (UTC)':<17} {'status':<8} {'trigger':<9}"
          f"{'fetched':>8}{'ins':>6}{'upd':>6}  matchdays / error")
    for r in runs:
        print(f"{r[0]:>4}  {r[1]:%Y-%m-%d %H:%M}  {r[2]:<8} {r[3]:<9}{r[4]:>8}{r[5]:>6}{r[6]:>6}  {r[7]} {r[8]}")


if __name__ == "__main__":
    main()
