"""Week 3: run every reference query in evals/golden_questions.csv and check that it works.

    python evals/check_reference.py                  # run all, save the answers
    python evals/check_reference.py --compare        # also compare with the previous saved run

It connects as the read-only role app_reader (APP_DATABASE_URL), and on top of that runs
every query in a READ ONLY transaction, so a reference query can never change data.

For each question with reference SQL it checks: the query succeeds and returns at least
one row. should_decline questions have no SQL and are skipped. The answers are saved to
evals/reference_runs/<UTC time>.json, so a later run can show which answers changed.
Exit code 1 if any query fails or returns nothing.
"""

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "evals" / "golden_questions.csv"
RUNS_DIR = ROOT / "evals" / "reference_runs"


def fingerprint(rows):
    return hashlib.sha256(json.dumps(rows, default=str).encode()).hexdigest()[:12]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare", action="store_true", help="compare with the previous saved run")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    url = os.environ.get("APP_DATABASE_URL")
    if not url:
        sys.exit("[FAIL] APP_DATABASE_URL is not set in .env (the read-only app_reader role).")

    with open(QUESTIONS, encoding="utf-8", newline="") as f:
        questions = list(csv.DictReader(f))

    previous = None
    old_runs = sorted(RUNS_DIR.glob("*.json"))
    if args.compare and old_runs:
        previous = json.loads(old_runs[-1].read_text(encoding="utf-8"))

    now = datetime.now(timezone.utc)
    results, failures = {}, 0
    with psycopg.connect(url, connect_timeout=10) as conn:
        user = conn.execute("select current_user").fetchone()[0]
        conn.rollback()
        print(f"Connected as {user}, {now:%Y-%m-%d %H:%M} UTC\n")
        conn.read_only = True   # every transaction is READ ONLY
        for q in questions:
            qid, sql = q["id"], q["reference_sql"].strip()
            if not sql:
                print(f"{qid}  skip  ({q['category']}: no reference SQL)")
                continue
            try:
                with conn.transaction():
                    cur = conn.execute(sql)
                    rows = [list(r) for r in cur.fetchall()]
                    columns = [d.name for d in cur.description]
            except psycopg.Error as error:
                failures += 1
                print(f"{qid}  FAIL  {str(error).strip().splitlines()[0]}")
                continue
            status = "ok  " if rows else "EMPTY"
            if not rows:
                failures += 1
            results[qid] = {"question": q["question"], "columns": columns,
                            "rows": json.loads(json.dumps(rows, default=str)),
                            "row_count": len(rows), "fingerprint": fingerprint(rows)}
            change = ""
            if previous is not None:
                old = previous["results"].get(qid)
                change = "  (new)" if old is None else (
                    "  CHANGED" if old["fingerprint"] != results[qid]["fingerprint"] else "  same")
            first = ", ".join(f"{c}={v}" for c, v in zip(columns, rows[0]))[:90] if rows else ""
            print(f"{qid}  {status} {len(rows):>3} rows{change}   {first}")

    RUNS_DIR.mkdir(exist_ok=True)
    out = RUNS_DIR / f"{now:%Y-%m-%d_%H%M}.json"
    out.write_text(json.dumps({"run_at": now.isoformat(), "user": user, "results": results},
                              indent=2, ensure_ascii=False), encoding="utf-8")

    ok = sum(1 for v in results.values() if v["row_count"])
    print(f"\n{ok} of "
          f"{sum(1 for q in questions if q['reference_sql'].strip())} reference queries OK; "
          f"saved to {out.relative_to(ROOT)}")
    if previous is not None:
        changed = [k for k, v in results.items()
                   if k in previous["results"] and previous["results"][k]["fingerprint"] != v["fingerprint"]]
        print(f"Compared with run of {previous['run_at'][:16]} UTC: "
              f"{len(changed)} answers changed ({', '.join(changed) or 'none'})")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
