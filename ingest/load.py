"""Week 2: load the raw OpenLigaDB JSON from data/raw/ into the database.

Run it from the project folder, after ingest/fetch.py:

    python ingest/load.py              # load all seasons found in data/raw/
    python ingest/load.py --schema     # first create the tables from db/schema.sql

It connects as the database owner (DATABASE_URL in .env) and never prints the
connection string.

How it works:
  * Parents before children, so every foreign key already exists:
    teams -> team_seasons -> players -> matches -> goals -> standings.
  * Every value goes in through psycopg placeholders (%s). SQL is never built
    by gluing strings together, which is how SQL injection happens.
  * Every INSERT ends with ON CONFLICT DO NOTHING, so running the load twice
    adds no duplicate rows. (Week 3 upgrades this to real updates.)
  * Everything runs in one transaction: if one row fails, nothing is saved.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
SCHEMA_FILE = ROOT / "db" / "schema.sql"
GERMAN_TIME = ZoneInfo("Europe/Berlin")   # lastUpdateDateTime has no time zone

HALFTIME, FINAL = 1, 2                    # resultTypeID values (names change between seasons)
TABLES = ["teams", "team_seasons", "players", "matches", "goals", "standings"]


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_utc(text):
    """'2026-08-28T18:30:00Z' -> aware datetime in UTC."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def parse_german(text):
    """'2026-09-02T15:36:25.313' (German local time, no zone) -> aware datetime."""
    return datetime.fromisoformat(text).replace(tzinfo=GERMAN_TIME)


def score(match, result_type):
    """Return (home, away) goals for one result type, or (None, None) if missing."""
    for result in match["matchResults"]:
        if result["resultTypeID"] == result_type:
            return result["pointsTeam1"], result["pointsTeam2"]
    return None, None


def count_rows(cur):
    counts = {}
    for table in TABLES:
        # Table names come from the fixed list above, never from outside input.
        cur.execute(f"select count(*) from {table}")
        counts[table] = cur.fetchone()[0]
    return counts


def insert_rows(cur, table, sql, rows, inserted):
    """Run one parameterized INSERT for many rows in a single round trip (executemany).

    cur.rowcount is the total number of rows actually inserted, so rows skipped by
    ON CONFLICT DO NOTHING are not counted.
    """
    if rows:
        cur.executemany(sql, rows)
        inserted[table] += cur.rowcount


def load_season(cur, season_dir, inserted):
    season = int(season_dir.name)
    matches = [m for f in sorted(season_dir.glob("matchday_*.json")) for m in read_json(f)]

    # 1. Teams and team_seasons. Teams also appear inside matches, so collect them there too.
    teams = {t["teamId"]: t for t in read_json(season_dir / "teams.json")}
    for m in matches:
        for side in ("team1", "team2"):
            teams.setdefault(m[side]["teamId"], m[side])
    insert_rows(cur, "teams",
        """insert into teams (team_id, name, short_name, icon_url)
           values (%s, %s, %s, %s)
           on conflict (team_id) do nothing""",
        [(t["teamId"], t["teamName"], t["shortName"], t.get("teamIconUrl")) for t in teams.values()],
        inserted)
    insert_rows(cur, "team_seasons",
        """insert into team_seasons (team_id, season) values (%s, %s)
           on conflict (team_id, season) do nothing""",
        [(team_id, season) for team_id in teams],
        inserted)

    # 2. Players: only goals with a real scorer (goalGetterID 0 or empty name = unknown).
    players = {}
    for m in matches:
        for g in m["goals"]:
            if g.get("goalGetterID") and g.get("goalGetterName"):
                players.setdefault(g["goalGetterID"], g["goalGetterName"].strip())
    insert_rows(cur, "players",
        """insert into players (player_id, short_name) values (%s, %s)
           on conflict (player_id) do nothing""",
        list(players.items()),
        inserted)

    # 3. Matches (parents of goals).
    match_rows = []
    for m in matches:
        ht_home, ht_away = score(m, HALFTIME)
        ft_home, ft_away = score(m, FINAL)
        match_rows.append(
            (m["matchID"], m["leagueSeason"], m["group"]["groupOrderID"],
             parse_utc(m["matchDateTimeUTC"]),
             m["team1"]["teamId"], m["team2"]["teamId"], m["matchIsFinished"],
             ht_home, ht_away, ft_home, ft_away,
             parse_german(m["lastUpdateDateTime"]), Jsonb(m)))
    insert_rows(cur, "matches",
        """insert into matches (match_id, season, matchday, kickoff_at,
               home_team_id, away_team_id, is_finished,
               home_goals_halftime, away_goals_halftime, home_goals, away_goals,
               source_updated_at, raw)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           on conflict (match_id) do nothing""",
        match_rows, inserted)

    # 4. Goals (children of matches, teams and players).
    goal_rows = []
    for m in matches:
        for g in m["goals"]:
            player_id = g["goalGetterID"] if g.get("goalGetterID") and g.get("goalGetterName") else None
            goal_rows.append(
                (g["goalID"], m["matchID"], g.get("scoringTeamId") or None, player_id,
                 g.get("matchMinute"), g["scoreTeam1"], g["scoreTeam2"],
                 bool(g.get("isPenalty")), bool(g.get("isOwnGoal")), bool(g.get("isOvertime"))))
    insert_rows(cur, "goals",
        """insert into goals (goal_id, match_id, scoring_team_id, player_id, minute,
               home_score_after, away_score_after, is_penalty, is_own_goal, is_overtime)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           on conflict (goal_id) do nothing""",
        goal_rows, inserted)

    # 5. Standings: the API returns the table already sorted, so the list order is the position.
    table_file = season_dir / "table.json"
    if table_file.exists():
        insert_rows(cur, "standings",
            """insert into standings (team_id, season, position, matches_played,
                   won, draw, lost, goals_for, goals_against, points)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               on conflict (team_id, season) do nothing""",
            [(row["teamInfoId"], season, position, row["matches"], row["won"], row["draw"],
              row["lost"], row["goals"], row["opponentGoals"], row["points"])
             for position, row in enumerate(read_json(table_file), start=1)],
            inserted)

    print(f"  season {season}: read {len(teams)} teams, {len(matches)} matches, "
          f"{sum(len(m['goals']) for m in matches)} goals")


def main():
    parser = argparse.ArgumentParser(description="Load raw OpenLigaDB JSON into the database.")
    parser.add_argument("--schema", action="store_true", help="create the tables from db/schema.sql first")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("[FAIL] DATABASE_URL is not set. Add it to your .env file (see .env.example).")

    season_dirs = sorted(d for d in RAW_DIR.iterdir() if d.is_dir() and d.name.isdigit())
    if not season_dirs:
        sys.exit("[FAIL] No raw data in data/raw/. Run python ingest/fetch.py first.")

    inserted = {table: 0 for table in TABLES}
    with psycopg.connect(url, connect_timeout=10) as conn:   # one transaction, committed at the end
        with conn.cursor() as cur:
            if args.schema:
                cur.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
                print("[ok] Tables created from db/schema.sql (existing tables are kept)")
            before = count_rows(cur)
            for season_dir in season_dirs:
                load_season(cur, season_dir, inserted)
            after = count_rows(cur)

    print()
    print(f"{'table':<14}{'before':>8}{'inserted':>10}{'after':>8}")
    for table in TABLES:
        print(f"{table:<14}{before[table]:>8}{inserted[table]:>10}{after[table]:>8}")
    if sum(inserted.values()) == 0:
        print("\nNo new rows: everything was already loaded (no duplicates created).")


if __name__ == "__main__":
    main()
