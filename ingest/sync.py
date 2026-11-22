"""Week 3: keep the database in sync with OpenLigaDB. One entry point for fetch + load.

Run it from the project folder:

    python ingest/sync.py              # normal run: only matchdays that changed
    python ingest/sync.py --full       # ignore the watermark, refetch every matchday
    python ingest/sync.py --seasons 2025 2026

GitHub Actions runs it on a schedule (.github/workflows/sync.yml). It connects as the
database owner (DATABASE_URL) and never prints the connection string.

How it works:
  1. Watermark. For every matchday of the season, OpenLigaDB tells us when anything in
     it last changed (/getlastchangedate/bl1/{season}/{matchday}). We compare that with
     the newest source_updated_at we already stored for that matchday. Only matchdays
     that are newer at the source (or missing in our database) are downloaded again.
     So the watermark lives in the database itself, in matches.source_updated_at.
  2. Upsert. Every row goes in with INSERT ... ON CONFLICT (natural id) DO UPDATE SET ...
     WHERE the new values are DISTINCT FROM the stored ones. So a row that did not
     change is not touched, and last_updated_at moves only when something really changed.
     RETURNING (xmax = 0) tells us whether Postgres inserted or updated the row.
  3. Idempotent. Run it twice in a row: the second run finds no changed matchdays
     (or only unchanged rows) and reports 0 inserted, 0 updated.
  4. Retries. 429 and 5xx answers, timeouts, and cut-off JSON are retried with growing
     waits (2, 4, 8 s). After MAX_RETRIES attempts the request fails cleanly.
  5. One transaction. All data changes of a run are committed together at the end.
     If anything fails halfway, everything is rolled back, so no half-written data.
  6. sync_runs. Every run, successful or not, writes one row to sync_runs in its own
     transaction afterwards. A failed run exits with code 1, so GitHub shows a red X.
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
import requests
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_FILE = ROOT / "db" / "schema.sql"

BASE_URL = "https://api.openligadb.de"
LEAGUE = "bl1"
MATCHDAYS = range(1, 35)
DEFAULT_SEASONS = [2026]        # the running season; 2025/26 is finished and already loaded
GERMAN_TIME = ZoneInfo("Europe/Berlin")
HALFTIME, FINAL = 1, 2          # resultTypeID values

REQUEST_DELAY = 1.1             # seconds between requests: under the 60 per minute limit
TIMEOUT = 30
MAX_RETRIES = 4
HEADERS = {"User-Agent": "BSAD6153 student project (Kickbase Lineup Assistant)"}


class FetchError(Exception):
    """A request that still failed after all retries."""


# ---------------------------------------------------------------- API

def get_json(path):
    """GET one endpoint. Retries 429, 5xx, timeouts and bad JSON; raises FetchError at the end."""
    url = f"{BASE_URL}{path}"
    last_problem = ""
    for attempt in range(1, MAX_RETRIES + 1):
        time.sleep(REQUEST_DELAY)
        wait = 2 ** attempt
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        except (requests.Timeout, requests.ConnectionError) as error:
            last_problem = type(error).__name__
        else:
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError:
                    last_problem = "response was not valid JSON"
            elif response.status_code == 429:
                last_problem = "429 Too Many Requests"
                retry_after = response.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    wait = int(retry_after)
            elif response.status_code >= 500:
                last_problem = f"server error {response.status_code}"
            else:
                # 4xx other than 429: asking again gives the same answer.
                raise FetchError(f"{path}: HTTP {response.status_code}")
        if attempt < MAX_RETRIES:
            print(f"  [retry] {path}: {last_problem} (attempt {attempt}/{MAX_RETRIES}), waiting {wait} s")
            time.sleep(wait)
    raise FetchError(f"{path}: gave up after {MAX_RETRIES} attempts ({last_problem})")


def parse_utc(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def parse_german(text):
    """OpenLigaDB's lastUpdateDateTime / lastchangedate: German local time without a zone."""
    return datetime.fromisoformat(text).replace(tzinfo=GERMAN_TIME)


def score(match, result_type):
    for result in match["matchResults"]:
        if result["resultTypeID"] == result_type:
            return result["pointsTeam1"], result["pointsTeam2"]
    return None, None


# ---------------------------------------------------------------- upserts

class Counter:
    def __init__(self):
        self.fetched = self.inserted = self.updated = self.deleted = 0
        self.per_table = {}

    def add(self, table, inserted):
        ins, upd = self.per_table.get(table, (0, 0))
        if inserted:
            self.inserted += 1
            self.per_table[table] = (ins + 1, upd)
        else:
            self.updated += 1
            self.per_table[table] = (ins, upd + 1)


def upsert(cur, counter, table, key_cols, data_cols, values):
    """INSERT one row, or UPDATE it if the natural key exists and a value really changed.

    The SQL is built only from the fixed column names in this file; the values always
    go in through %s placeholders.
    """
    cols = key_cols + data_cols
    sql = (
        f"insert into {table} ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))}) "
        f"on conflict ({', '.join(key_cols)}) do update set "
        + ", ".join(f"{c} = excluded.{c}" for c in data_cols)
        + ", last_updated_at = now() "
        f"where ({', '.join(f'{table}.{c}' for c in data_cols)}) "
        f"is distinct from ({', '.join(f'excluded.{c}' for c in data_cols)}) "
        "returning (xmax = 0) as inserted"
    )
    cur.execute(sql, values)
    row = cur.fetchone()          # None: the row existed and nothing changed
    if row is not None:
        counter.add(table, row[0])


def sync_matchday(cur, counter, season, matches):
    # Teams and team_seasons first (parents of matches).
    for m in matches:
        for side in ("team1", "team2"):
            t = m[side]
            upsert(cur, counter, "teams", ["team_id"], ["name", "short_name", "icon_url"],
                   (t["teamId"], t["teamName"], t["shortName"], t.get("teamIconUrl")))
            cur.execute("""insert into team_seasons (team_id, season) values (%s, %s)
                           on conflict (team_id, season) do nothing returning team_season_id""",
                        (t["teamId"], season))
            if cur.fetchone():
                counter.add("team_seasons", True)

    # Players: only goals with a real scorer.
    for m in matches:
        for g in m["goals"]:
            if g.get("goalGetterID") and g.get("goalGetterName"):
                upsert(cur, counter, "players", ["player_id"], ["short_name"],
                       (g["goalGetterID"], g["goalGetterName"].strip()))

    # Matches.
    for m in matches:
        ht_home, ht_away = score(m, HALFTIME)
        ft_home, ft_away = score(m, FINAL)
        upsert(cur, counter, "matches", ["match_id"],
               ["season", "matchday", "kickoff_at", "home_team_id", "away_team_id", "is_finished",
                "home_goals_halftime", "away_goals_halftime", "home_goals", "away_goals",
                "source_updated_at", "raw"],
               (m["matchID"], m["leagueSeason"], m["group"]["groupOrderID"],
                parse_utc(m["matchDateTimeUTC"]), m["team1"]["teamId"], m["team2"]["teamId"],
                m["matchIsFinished"], ht_home, ht_away, ft_home, ft_away,
                parse_german(m["lastUpdateDateTime"]), Jsonb(m)))

    # Goals, plus goals that disappeared at the source (corrected by OpenLigaDB).
    for m in matches:
        source_ids = []
        for g in m["goals"]:
            source_ids.append(g["goalID"])
            player_id = g["goalGetterID"] if g.get("goalGetterID") and g.get("goalGetterName") else None
            upsert(cur, counter, "goals", ["goal_id"],
                   ["match_id", "scoring_team_id", "player_id", "minute", "home_score_after",
                    "away_score_after", "is_penalty", "is_own_goal", "is_overtime"],
                   (g["goalID"], m["matchID"], g.get("scoringTeamId") or None, player_id,
                    g.get("matchMinute"), g["scoreTeam1"], g["scoreTeam2"],
                    bool(g.get("isPenalty")), bool(g.get("isOwnGoal")), bool(g.get("isOvertime"))))
        cur.execute("delete from goals where match_id = %s and not (goal_id = any(%s))",
                    (m["matchID"], source_ids))
        counter.deleted += cur.rowcount


def sync_standings(cur, counter, season, table):
    for position, row in enumerate(table, start=1):
        upsert(cur, counter, "standings", ["team_id", "season"],
               ["position", "matches_played", "won", "draw", "lost",
                "goals_for", "goals_against", "points"],
               (row["teamInfoId"], season, position, row["matches"], row["won"], row["draw"],
                row["lost"], row["goals"], row["opponentGoals"], row["points"]))


def stored_watermarks(cur, season):
    """Newest source_updated_at we have per matchday: the watermark."""
    cur.execute("""select matchday, max(source_updated_at) from matches
                   where season = %s group by matchday""", (season,))
    return dict(cur.fetchall())


# ---------------------------------------------------------------- one run

def run_sync(conn, seasons, full, counter, synced, problems, crash_after=None):
    """All data changes in ONE transaction. Raises on a fatal error (then nothing is saved)."""
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(SCHEMA_FILE.read_text(encoding="utf-8"))   # create missing tables
            for season in seasons:
                watermarks = {} if full else stored_watermarks(cur, season)
                done = []
                for matchday in MATCHDAYS:
                    try:
                        changed_at = parse_german(get_json(f"/getlastchangedate/{LEAGUE}/{season}/{matchday}"))
                        stored = watermarks.get(matchday)
                        if stored is not None and changed_at <= stored:
                            continue            # nothing new at the source
                        matches = get_json(f"/getmatchdata/{LEAGUE}/{season}/{matchday}")
                    except FetchError as error:
                        problems.append(str(error))   # skip this matchday, keep going
                        continue
                    counter.fetched += len(matches)
                    sync_matchday(cur, counter, season, matches)
                    done.append(matchday)
                    print(f"  {season} matchday {matchday:2d}: {len(matches)} matches synced")
                    if crash_after is not None and len(done) >= crash_after:
                        raise RuntimeError(f"simulated crash after {crash_after} matchday(s) (--crash-after)")
                if done:
                    synced.append(f"{season}: {', '.join(map(str, done))}")
                try:
                    table = get_json(f"/getbltable/{LEAGUE}/{season}")
                except FetchError as error:
                    problems.append(str(error))
                else:
                    counter.fetched += len(table)
                    sync_standings(cur, counter, season, table)


def record_run(url, started, status, trigger, counter, synced, error_message):
    """Write the sync_runs row in its own transaction, so it survives a rolled-back sync."""
    with psycopg.connect(url, connect_timeout=10) as conn:
        conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
        row = conn.execute(
            """insert into sync_runs (started_at, finished_at, status, trigger, records_fetched,
                   records_inserted, records_updated, records_deleted, matchdays_synced, error_message)
               values (%s, now(), %s, %s, %s, %s, %s, %s, %s, %s) returning run_id""",
            (started, status, trigger, counter.fetched, counter.inserted, counter.updated,
             counter.deleted, "; ".join(synced) or None, error_message)).fetchone()
    return row[0]


def safe_error(error, url):
    """First line of the error, with the connection string removed just in case."""
    text = (str(error).strip().splitlines() or [type(error).__name__])[0]
    if url:
        text = text.replace(url, "<DATABASE_URL>")
    return f"{type(error).__name__}: {text}"[:500]


def main():
    parser = argparse.ArgumentParser(description="Sync OpenLigaDB into the database.")
    parser.add_argument("--seasons", type=int, nargs="+", default=DEFAULT_SEASONS)
    parser.add_argument("--full", action="store_true", help="ignore the watermark, refetch all matchdays")
    parser.add_argument("--crash-after", type=int, metavar="N",
                        help="break-it test: crash on purpose after N synced matchdays")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("[FAIL] DATABASE_URL is not set (.env locally, an Actions secret on GitHub).")
    # GitHub sets GITHUB_EVENT_NAME; anything that is not the cron schedule counts as manual.
    trigger = "schedule" if os.environ.get("GITHUB_EVENT_NAME") == "schedule" else "manual"

    started = datetime.now(timezone.utc)
    counter, synced, problems = Counter(), [], []
    print(f"Sync started {started:%Y-%m-%d %H:%M} UTC, trigger={trigger}, seasons={args.seasons}"
          f"{', FULL' if args.full else ''}")
    try:
        with psycopg.connect(url, connect_timeout=10) as conn:
            run_sync(conn, args.seasons, args.full, counter, synced, problems, args.crash_after)
        status = "partial" if problems else "success"
        error_message = "; ".join(problems)[:500] or None
    except Exception as error:   # anything fatal: the transaction was rolled back
        status = "failed"
        error_message = safe_error(error, url)
        # Nothing was committed, so report 0 changes but keep what was fetched.
        counter.inserted = counter.updated = counter.deleted = 0
        counter.per_table = {}
        synced = []

    try:
        run_id = record_run(url, started, status, trigger, counter, synced, error_message)
    except Exception as error:
        print(f"[FAIL] could not write sync_runs: {safe_error(error, url)}")
        sys.exit(1)

    print()
    print(f"run_id {run_id}: {status}")
    print(f"  fetched {counter.fetched}, inserted {counter.inserted}, "
          f"updated {counter.updated}, deleted {counter.deleted}")
    for table, (ins, upd) in sorted(counter.per_table.items()):
        print(f"    {table:<13} +{ins} inserted, {upd} updated")
    print(f"  matchdays synced: {'; '.join(synced) or 'none (nothing changed at the source)'}")
    if error_message:
        print(f"  error: {error_message}")
    # partial and failed both exit 1, so GitHub shows a red X and sends an email.
    sys.exit(0 if status == "success" else 1)


if __name__ == "__main__":
    main()
