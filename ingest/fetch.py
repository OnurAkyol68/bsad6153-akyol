"""Week 1: fetch Bundesliga data from OpenLigaDB and save the raw JSON.

Run it from the project folder:

    python ingest/fetch.py                     # seasons 2024 and 2025 (default)
    python ingest/fetch.py --seasons 2025      # just one season

API docs:  https://api.openligadb.de/index.html
Terms:     https://www.openligadb.de/nutzungsbedingungen
License:   ODbL 1.0, https://www.openligadb.de/lizenz

What it fetches, per season:
  * teams:   /getavailableteams/bl1/{season}         (one request)
  * matches: /getmatchdata/bl1/{season}/{matchday}   (one request per matchday, 1-34)
             Each match includes its goals, so goals come along for free.
  * table:   /getbltable/bl1/{season}                 (one request)

Authentication: none. OpenLigaDB needs no login and no API key, so this script
reads nothing from .env.

Pagination: OpenLigaDB has no page numbers. Data is split by season and matchday
("groupOrderId"), so we loop over matchdays 1 to 34.

Rate limit: the docs allow 60 requests per minute per IP and ask us to fetch
sparingly. We wait REQUEST_DELAY seconds between requests (about 50 per minute),
and on a 429 we wait and retry instead of crashing.

Raw files go to data/raw/ (ignored by Git). Running the script again simply
overwrites them with fresh copies, so reruns never create duplicates.
"""

import argparse
import json
import logging
import time
from pathlib import Path

import requests

BASE_URL = "https://api.openligadb.de"
LEAGUE = "bl1"                  # 1. Bundesliga
MATCHDAYS = range(1, 35)        # 18 teams -> 34 matchdays per season
DEFAULT_SEASONS = [2024, 2025]  # season 2025 = 2025/26

REQUEST_DELAY = 1.2             # seconds between requests: stays under 60 per minute
TIMEOUT = 30                    # seconds before we give up waiting for one response
MAX_RETRIES = 4                 # attempts per request on 429, 5xx, or timeout
HEADERS = {"User-Agent": "BSAD6153 student project (Kickbase Lineup Assistant)"}

# Fields we expect on every match. A match missing one of these is reported.
MATCH_FIELDS = ["matchID", "matchDateTimeUTC", "group", "team1", "team2",
                "matchIsFinished", "matchResults", "goals", "lastUpdateDateTime"]

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

log = logging.getLogger("fetch")

# Counts for the summary at the end.
stats = {"requests": 0, "retries": 0, "failed": [], "teams": 0, "matches": 0,
         "goals": 0, "table_rows": 0, "missing_fields": []}


def get_json(path):
    """GET one endpoint and return the parsed JSON, or None if it keeps failing.

    Retries with growing waits (2, 4, 8, 16 s) on timeouts, connection errors,
    429 Too Many Requests, and 5xx server errors. Other errors (like 404) are
    not retried, because asking again would give the same answer.
    """
    url = f"{BASE_URL}{path}"
    for attempt in range(1, MAX_RETRIES + 1):
        time.sleep(REQUEST_DELAY)  # be polite: never fire requests back to back
        stats["requests"] += 1
        wait = 2 ** attempt
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        except (requests.Timeout, requests.ConnectionError) as error:
            log.warning("%s: %s (attempt %d/%d), waiting %d s",
                        path, type(error).__name__, attempt, MAX_RETRIES, wait)
        else:
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError:
                    # Large responses sometimes arrive cut off; treat like a server error.
                    log.warning("%s: response was not valid JSON (attempt %d/%d), waiting %d s",
                                path, attempt, MAX_RETRIES, wait)
            elif response.status_code == 429:
                # Too many requests: use the server's Retry-After if it sends one.
                retry_after = response.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    wait = int(retry_after)
                log.warning("%s: 429 Too Many Requests (attempt %d/%d), waiting %d s",
                            path, attempt, MAX_RETRIES, wait)
            elif response.status_code >= 500:
                log.warning("%s: server error %d (attempt %d/%d), waiting %d s",
                            path, response.status_code, attempt, MAX_RETRIES, wait)
            else:
                log.error("%s: HTTP %d, skipping (not retried)", path, response.status_code)
                stats["failed"].append(path)
                return None
        if attempt < MAX_RETRIES:
            stats["retries"] += 1
            time.sleep(wait)
    log.error("%s: gave up after %d attempts, skipping", path, MAX_RETRIES)
    stats["failed"].append(path)
    return None


def save(data, relative_path):
    """Write data as pretty JSON under data/raw/, replacing any older copy."""
    target = RAW_DIR / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def check_match(match):
    """Record any expected field that is missing or empty on one match."""
    for field in MATCH_FIELDS:
        if match.get(field) is None:
            stats["missing_fields"].append(f"match {match.get('matchID', '?')}: {field}")


def fetch_season(season):
    log.info("Season %d/%d", season, (season + 1) % 100)

    teams = get_json(f"/getavailableteams/{LEAGUE}/{season}")
    if teams is not None:
        save(teams, f"{season}/teams.json")
        stats["teams"] += len(teams)

    for matchday in MATCHDAYS:
        matches = get_json(f"/getmatchdata/{LEAGUE}/{season}/{matchday}")
        if matches is None:
            continue
        save(matches, f"{season}/matchday_{matchday:02d}.json")
        for match in matches:
            check_match(match)
            stats["goals"] += len(match.get("goals") or [])
        stats["matches"] += len(matches)
        log.info("  matchday %2d: %d matches", matchday, len(matches))

    table = get_json(f"/getbltable/{LEAGUE}/{season}")
    if table is not None:
        save(table, f"{season}/table.json")
        stats["table_rows"] += len(table)


def main():
    parser = argparse.ArgumentParser(description="Fetch Bundesliga data from OpenLigaDB.")
    parser.add_argument("--seasons", type=int, nargs="+", default=DEFAULT_SEASONS,
                        help="season start years, e.g. 2024 2025")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    started = time.time()
    for season in args.seasons:
        fetch_season(season)

    print()
    print("Summary")
    print(f"  requests sent:   {stats['requests']} ({stats['retries']} retries)")
    print(f"  teams:           {stats['teams']}")
    print(f"  matches:         {stats['matches']}")
    print(f"  goals:           {stats['goals']}")
    print(f"  table rows:      {stats['table_rows']}")
    print(f"  missing fields:  {len(stats['missing_fields'])}")
    for item in stats["missing_fields"][:10]:
        print(f"    - {item}")
    print(f"  failed requests: {len(stats['failed'])}")
    for path in stats["failed"]:
        print(f"    - {path}")
    print(f"  saved to:        {RAW_DIR.relative_to(ROOT)}/")
    print(f"  time:            {time.time() - started:.0f} s")


if __name__ == "__main__":
    main()
