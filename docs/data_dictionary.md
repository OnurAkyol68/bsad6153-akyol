# Data Dictionary (Week 1)

## Source

| | |
|---|---|
| **API** | OpenLigaDB (free, community-run football data) |
| **Base URL** | `https://api.openligadb.de` |
| **Documentation** | https://api.openligadb.de/index.html (Swagger page; the rules are in the description at the top) |
| **Terms of service** | Linked from the documentation as https://www.openligadb.de/nutzungsbedingungen |
| **Data license** | Open Database License (ODbL 1.0), linked as https://www.openligadb.de/lizenz |
| **Authentication** | None. No account, no API key, no login. |
| **Rate limit** | 60 requests per minute per IP. The providers ask users to fetch sparingly. |
| **League / seasons** | 1. Bundesliga (`bl1`), seasons 2025 (= 2025/26, finished) and 2026 (= 2026/27, running) |

Endpoints used by `ingest/fetch.py`:

| Endpoint | Returns | Requests per season |
|---|---|---|
| `/getavailableteams/bl1/{season}` | the 18 teams of the season | 1 |
| `/getmatchdata/bl1/{season}/{matchday}` | the 9 matches of one matchday, each with its results and goals | 34 |
| `/getbltable/bl1/{season}` | the current league table | 1 |

Records from the last run (2026-11-01): **612 matches**, **1,246 goals**, 36 team rows (18 per season), 36 table rows.

## What one record means

- **Match:** One record is one scheduled Bundesliga match between a home team (`team1`) and an away team (`team2`) on one matchday of one season. It exists before kickoff; results and goals fill in once it is played.
- **Goal:** One record is one goal scored in a match, with the score right after the goal, the minute, and the player who scored it. Goals are nested inside their match.
- **Team:** One record is one club taking part in a season of the league.
- **Table row:** One record is one team's standing (points, wins, goals) in a season, as of the moment the table was fetched.
- **Match result:** One record is one score snapshot of a match: half-time or final score (after 90 minutes). Nested inside the match.

## Fields

| Field | Type | Example | Meaning | Can be missing? |
|---|---|---|---|---|
| `matchID` | integer | `83161` | Unique ID of the match | No |
| `leagueSeason` | integer | `2026` | Year the season started (2026 = 2026/27) | No |
| `group.groupOrderID` | integer | `1` | Matchday number, 1&ndash;34 | No |
| `matchDateTimeUTC` | text (ISO date-time, UTC) | `2026-08-29T13:30:00Z` | Kickoff time in UTC | No |
| `matchDateTime` | text (ISO date-time, no zone) | `2026-08-29T15:30:00` | Kickoff in German local time | No |
| `team1.teamId` / `team2.teamId` | integer | `40` | Home team / away team ID | No |
| `team1.teamName` | text | `FC Bayern München` | Full club name | No |
| `matchIsFinished` | boolean | `true` | Whether the match has been played | No |
| `lastUpdateDateTime` | text (date-time, no zone) | `2026-08-29T17:31:02.12` | When OpenLigaDB last changed this match | No |
| `matchResults[].resultTypeID` | integer | `2` | 1 = half-time, 2 = final score after 90 min | Empty list before kickoff |
| `matchResults[].pointsTeam1` / `pointsTeam2` | integer | `2` | Goals of home / away team in that result | Empty list before kickoff |
| `goals[].goalID` | integer | `130535` | Unique ID of the goal | No |
| `goals[].matchMinute` | integer | `27` | Minute of the goal | **Yes** (4 goals) |
| `goals[].goalGetterID` | integer | `23135` | ID of the scoring player | **Yes**, `0`/empty in 5 goals |
| `goals[].goalGetterName` | text | `M. Olise` | Short name of the scorer | **Yes**, empty string in 5 goals |
| `goals[].scoringTeamId` | integer | `40` | Team the goal counts for | **Yes** (6 goals) |
| `goals[].isPenalty` / `isOwnGoal` | boolean | `false` | Penalty goal / own goal | No |
| `table[].teamInfoId` | integer | `40` | Team ID in the table (same values as `teamId`) | No |
| `table[].points` | integer | `18` | League points so far | No |
| `timeZoneID` | text | `W. Europe Standard Time` | Time zone of `matchDateTime` | **Yes** (333 of 612 matches) |

## Identifiers and relationships

- **Match** is identified by `matchID`. **Goal** by `goalID`. **Team** by `teamId`. **Match result** by `resultID`.
- A **goal belongs to one match** (it is nested in the match; in the database it gets a `match_id` foreign key).
- A **goal belongs to one team** through `scoringTeamId` &rarr; `teamId`, and to one **player** through `goalGetterID`. Player is not its own endpoint: the only player data is the ID and short name on goals.
- A **match refers to two teams**: `team1.teamId` (home) and `team2.teamId` (away).
- A **table row refers to a team** through `teamInfoId`, which holds the same number as `teamId` in the other endpoints.
- A **team plays in many seasons**, so a season's team list is a team&ndash;season relationship (teams get promoted and relegated: 21 different teams across the two seasons).

## Update behavior

- New data appears on every matchday weekend (and on midweek matchdays): unfinished matches get results and goals, and the table changes.
- Old records do change: future matches are created months ahead and get updated when kickoff times are fixed and when they are played. A finished match can still change afterwards (each change moves its `lastUpdateDateTime`); I have not yet seen how often this happens and will check it in Week 3.
- Finished seasons no longer change, according to the documentation.
- **How to detect what's new:** compare each match's `lastUpdateDateTime` with the time of the last sync. The API also has `/getlastchangedate/bl1/{season}/{matchday}`, a cheap call that says when a matchday last changed, so a sync can skip matchdays that have not changed.

## Surprises

1. **Missing scorers.** 5 goals have `goalGetterID` = 0 and an empty `goalGetterName`, and they are not own goals. 4 goals have no `matchMinute`, and 6 have no `scoringTeamId`.
2. **Goals don't always add up.** In 4 finished matches, the number of goal records does not match the final score, so goals cannot be counted to get the result.
3. **Inconsistent time zone field.** `timeZoneID` is `null` for most finished matches but filled for future ones, and `matchDateTime` has no time zone at all. Only `matchDateTimeUTC` is safe to use.
4. **Inconsistent labels.** The half-time result is called `Halbzeitergebnis` in season 2024 but `Halbzeit` in later seasons, so code must use `resultTypeID`, not the name.
5. **Different names for the same ID.** The table calls the team ID `teamInfoId`, while matches and teams call it `teamId`.
6. **Always-empty fields.** `location`, `numberOfViewers`, and `tla` (three-letter team code) are `null` in every record.
7. **No Kickbase data.** There are no Kickbase points, market values, injuries, or lineups. The system can only use form data (goals, results, table, fixtures).

## Data-use ethics check


- **Terms of service: allowed and forbidden?** The documentation says the data is under the ODbL 1.0 license: storing, showing it publicly, and commercial use are allowed if we credit OpenLigaDB (and the ODbL contributors) and share any changed database under the same license. The linked terms page did not show its text when I checked it, so I will confirm the details with OpenLigaDB or the instructor.
- **Real, identifiable people?** Yes: goal scorers are real players, named by short name and ID. This is public match information that is reported in the media anyway, and players expect it to be published. My system only uses it for fantasy-football decisions.
- **Worst realistic harm if leaked or misread?** A leak would reveal nothing private, because the data is already public. The bigger risk is misreading: a wrong or missing scorer could make me sell or bench the wrong player in Kickbase, which costs me points or virtual money.
- **Who may read or change the records?** Anyone may read them on the public website (with attribution). Only the sync pipeline may write or change them; the website, chatbot, and agent get read-only access.
