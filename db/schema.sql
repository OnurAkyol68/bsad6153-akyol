-- db/schema.sql: database design for the Kickbase Lineup Assistant (Week 2).
--
-- Source: OpenLigaDB, 1. Bundesliga, seasons 2025 and 2026 (see docs/data_dictionary.md).
-- Tables: teams, team_seasons, players, matches (main table), goals, standings.
--
-- Design rules:
--   * Primary keys: where OpenLigaDB has its own ID (team, player, match, goal) we use
--     that natural ID as the primary key, so it is unique automatically.
--     Where it has none (team_seasons, standings) we create an identity ID and add
--     a UNIQUE constraint on the columns that identify a row.
--   * Foreign keys for every relationship.
--   * Real data types: integer, boolean, timestamptz, text, jsonb.
--   * NOT NULL and CHECK constraints encode what the Week 1 data showed.
--   * Audit columns first_seen_at and last_updated_at on every table.
--
-- Running this file again is safe: tables are only created if they are missing.
-- Week 3 adds sync_runs. Week 6 adds agent_runs and agent_proposals.

-- One club. A club keeps the same OpenLigaDB team ID across seasons.
create table if not exists teams (
    team_id          integer primary key check (team_id > 0),   -- OpenLigaDB teamId / teamInfoId
    name             text not null check (name <> ''),          -- e.g. 'FC Bayern München'
    short_name       text not null check (short_name <> ''),    -- e.g. 'Bayern'
    icon_url         text,                                      -- logo link, can be missing
    first_seen_at    timestamptz not null default now(),
    last_updated_at  timestamptz not null default now()
);

-- Which club plays in which season (clubs are promoted and relegated).
create table if not exists team_seasons (
    team_season_id   integer generated always as identity primary key,
    team_id          integer not null references teams (team_id),
    season           integer not null check (season between 2000 and 2100),  -- 2026 = 2026/27
    first_seen_at    timestamptz not null default now(),
    last_updated_at  timestamptz not null default now(),
    unique (team_id, season)
);

-- A goal scorer. The API has no player endpoint: only an ID and a short name on each goal.
create table if not exists players (
    player_id        integer primary key check (player_id > 0),   -- OpenLigaDB goalGetterID
    short_name       text not null check (short_name <> ''),      -- e.g. 'M. Olise'
    first_seen_at    timestamptz not null default now(),
    last_updated_at  timestamptz not null default now()
);

-- One scheduled Bundesliga match (main table). It exists before kickoff;
-- the scores fill in once it is played.
create table if not exists matches (
    match_id             integer primary key check (match_id > 0),   -- OpenLigaDB matchID
    season               integer not null check (season between 2000 and 2100),
    matchday             integer not null check (matchday between 1 and 34),
    kickoff_at           timestamptz not null,   -- from matchDateTimeUTC, the only safe time field
    home_team_id         integer not null references teams (team_id),
    away_team_id         integer not null references teams (team_id),
    is_finished          boolean not null default false,
    -- Scores come from matchResults by resultTypeID (1 = half-time, 2 = after 90 minutes),
    -- never by name, because the name changed between seasons.
    home_goals_halftime  integer check (home_goals_halftime >= 0),
    away_goals_halftime  integer check (away_goals_halftime >= 0),
    home_goals           integer check (home_goals >= 0),
    away_goals           integer check (away_goals >= 0),
    source_updated_at    timestamptz not null,   -- lastUpdateDateTime (German local time, converted)
    raw                  jsonb not null,         -- original API record, for fields not modeled yet
    first_seen_at        timestamptz not null default now(),
    last_updated_at      timestamptz not null default now(),
    check (home_team_id <> away_team_id),
    -- A finished match has a final score; an unplayed match has none.
    check ((is_finished and home_goals is not null and away_goals is not null)
        or (not is_finished and home_goals is null and away_goals is null)),
    -- Half-time goals can never be more than full-time goals.
    check (home_goals_halftime is null or home_goals is null or home_goals_halftime <= home_goals),
    check (away_goals_halftime is null or away_goals is null or away_goals_halftime <= away_goals)
);

create index if not exists matches_season_matchday_idx on matches (season, matchday);
create index if not exists matches_home_team_idx on matches (home_team_id);
create index if not exists matches_away_team_idx on matches (away_team_id);

-- One goal in a match. Scorer, minute and team are missing for a few goals in the
-- source (Week 1 surprise 1), so those columns allow NULL.
create table if not exists goals (
    goal_id           integer primary key check (goal_id > 0),   -- OpenLigaDB goalID
    match_id          integer not null references matches (match_id),
    scoring_team_id   integer references teams (team_id),        -- team the goal counts for
    player_id         integer references players (player_id),    -- NULL when the scorer is unknown
    minute            integer check (minute between 1 and 130),  -- includes stoppage time
    home_score_after  integer not null check (home_score_after >= 0),
    away_score_after  integer not null check (away_score_after >= 0),
    is_penalty        boolean not null default false,
    is_own_goal       boolean not null default false,
    is_overtime       boolean not null default false,
    first_seen_at     timestamptz not null default now(),
    last_updated_at   timestamptz not null default now()
    -- No check "home_score_after + away_score_after > 0": I planned one, but 5 goals in
    -- season 2025 have the score 0:0 after the goal and no scoring team. They look like
    -- placeholder records in the source, so I keep them and flag them in queries instead.
);

create index if not exists goals_match_idx on goals (match_id);
create index if not exists goals_player_idx on goals (player_id);

-- One club's row in the league table of a season, as of the last fetch.
create table if not exists standings (
    standing_id      integer generated always as identity primary key,
    team_id          integer not null references teams (team_id),
    season           integer not null check (season between 2000 and 2100),
    position         integer not null check (position between 1 and 18),
    matches_played   integer not null check (matches_played between 0 and 34),
    won              integer not null check (won >= 0),
    draw             integer not null check (draw >= 0),
    lost             integer not null check (lost >= 0),
    goals_for        integer not null check (goals_for >= 0),
    goals_against    integer not null check (goals_against >= 0),
    points           integer not null check (points >= 0),
    first_seen_at    timestamptz not null default now(),
    last_updated_at  timestamptz not null default now(),
    unique (team_id, season),
    unique (season, position),
    check (won + draw + lost = matches_played),
    check (points = 3 * won + draw)   -- Bundesliga: 3 points for a win, 1 for a draw
);
