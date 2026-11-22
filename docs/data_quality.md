# Data-Quality Report (Week 3)

Every number below comes from a query in [`db/quality_checks.sql`](../db/quality_checks.sql); the label
(QC01, QC02, ...) names the query. My data now changes every 6 hours, so **each number has the date it was
measured**. All numbers were measured on **2026-11-22 at about 21:10 UTC**, right after sync run 2 (season
2025 complete, season 2026 through matchday 10).

## 1. Row counts (QC01, 2026-11-22)

| Table | Rows | Note |
|---|---|---|
| `teams` | 21 | 18 per season, 21 different clubs across 2025 and 2026 |
| `team_seasons` | 36 | 18 per season |
| `players` | 394 | only goal scorers (OpenLigaDB has no player endpoint) |
| `matches` | 612 | 306 per season; 396 finished, 216 not yet played |
| `goals` | 1,299 | up from 1,276 before the first sync: matchday 10 added 23 goals |
| `standings` | 36 | 18 per season, as of the last sync |
| `sync_runs` | 2 | both manual test runs |

## 2. Null rates (QC02, QC03, 2026-11-22)

| Field | Missing | Rate |
|---|---|---|
| `goals.player_id` (scorer) | 5 of 1,299 | 0.38 % |
| `goals.minute` | 4 of 1,299 | 0.31 % |
| `goals.scoring_team_id` | 6 of 1,299 | 0.46 % |
| `matches.home_goals` for finished matches | 0 of 396 | 0 % |
| `matches.home_goals` for unplayed matches | 216 of 216 | 100 %, as it must be (CHECK constraint) |

## 3. Duplicates (QC04–QC07, 2026-11-22)

- **By natural ID (QC04):** 0 duplicates in `matches`, `goals`, `players`, `teams`. The natural IDs are the
  primary keys, so the database cannot store a duplicate, and the upsert updates instead of inserting twice.
- **Same pairing twice in a season (QC05):** 0. Every home/away pairing appears exactly once per season.
- **Same goal twice with different IDs (QC07):** 0.
- **Same player, different IDs (QC06): 5 short names have two IDs**, for example `J. Musiala` (18700, 20736)
  and `Justin Njinmah` (19557, 24729). OpenLigaDB sometimes creates a new scorer ID instead of reusing the old
  one. A query that groups by `player_id` splits such a player's goals in two.

## 4. Out-of-range and inconsistent values (QC08–QC12, 2026-11-22)

| Check | Result |
|---|---|
| Goal records don't add up to the final score (QC08) | **4 matches**, all season 2025, each with 2 goal records for a 1-goal result |
| Placeholder goals with score 0:0 after the goal (QC09) | **5 goals**; they are the extra records in QC08 |
| Matches still "unfinished" 3 hours after kickoff (QC10) | 0 |
| Finished match last updated before its kickoff (QC11), i.e. a time-zone error | 0 |
| Stored table points differ from points computed from our own matches, 2026 (QC12) | 0 teams |
| Negative scores, minutes outside 1–130, half-time > full-time | impossible: CHECK constraints in `db/schema.sql` |

Time zones: `kickoff_at` comes from `matchDateTimeUTC`; `source_updated_at` is German local time in the source
and is converted with `Europe/Berlin` (including summer time). QC11 confirms the conversion: no finished match
was "updated" before it kicked off.

## 5. Orphans (QC13, QC14, 2026-11-22)

- Goals without a match, player, or team: **0 / 0 / 0**. Foreign keys make orphans impossible: the sync always
  writes parents first (teams, team_seasons, players, then matches, then goals), and a goal pointing to a
  missing parent would make the whole transaction fail and roll back.
- A goal with an **unknown scorer** is not an orphan: `player_id` is NULL on purpose (5 goals).
- Players without goals: 0 (players only exist because they scored). Teams without a season: 0.
- **Goals deleted at the source:** when OpenLigaDB removes a goal from a match, the sync deletes it too
  (`records_deleted` in `sync_runs`), so our goals never point to a goal that no longer exists. So far: 0.

## 6. Decisions

| What | Decision | Why |
|---|---|---|
| 5 goals with no scorer | **kept**, `player_id` NULL | the goal still counts for the score; queries about players skip it |
| 5 placeholder goals with 0:0 after the goal | **kept**, flagged by QC09 | they are in the source; deleting them would make my data differ from OpenLigaDB. Goal counts per match use `matches.home_goals`, not goal records |
| 5 players with two IDs | **left alone** | I can't prove two IDs are the same person (two players can share a short name). Documented as a should_decline risk in the golden questions |
| Always-empty fields (`location`, `numberOfViewers`) | **not modeled** | still in `matches.raw` if they ever fill in |
| `timeZoneID`, `matchDateTime` | **rejected** | inconsistent; only `matchDateTimeUTC` is used |
| Unknown result-type names | **cleaned** by using `resultTypeID` | names changed between seasons |
| Goals removed at the source | **deleted** in our table | otherwise counts would include goals that no longer exist |

## 7. Fairness check (QC15–QC17, 2026-11-22)

**Yes, gaps in this data could mislead my chatbot.** Two concrete examples:

1. **Promoted clubs have far less history.** Elversberg, Paderborn and Schalke have **10 finished matches** in my
   database, while 15 other clubs have **44** (QC17), 4.4 times as much evidence. A question like "How strong is
   Elversberg?" rests on 10 games, and a question that compares "the last two seasons" silently compares a club
   with only one. The chatbot must say how many matches an answer is based on.
2. **Goals are the only player data, so most players look bad.** Of 147 players who scored in 2026, **73 (50 %)
   have exactly one goal** (QC15), and the top 10 % of scorers have 30.2 % of all goals (QC16). Defenders and
   goalkeepers who never score are not in the database at all. If I ask "Who is in good form?", the system can
   only rank strikers; it would unfairly suggest selling a defender who plays well but doesn't score. This is
   one of my should_decline golden questions (Q17).

## 8. Change log (Week 3)

What the first sync runs taught me about my data (2026-11-22):

- **Finished matches do change afterwards.** One match of matchday 9 (played 6–8 Nov) was updated again on
  10 Nov. So the sync can't stop looking at a matchday once it is finished. The watermark handles this: it
  refetches any matchday whose `getlastchangedate` is newer than what we stored.
- **Future matches change too.** 17 matches of matchdays 11 and 12 (not yet played) were updated on 20 Nov,
  when the exact kickoff times were fixed. `kickoff_at` is therefore not final until about 2 weeks before a
  match.
- **The first sync caught up 12 days.** My Milestone 2 load was from 10 Nov; the first sync found 4 changed
  matchdays (9–12) and inserted 23 goals and 5 new scorers, and updated 27 matches and all 18 table rows.
- **Table positions swap.** Updating the table row by row broke the `unique (season, position)` constraint
  when two clubs swap places. I made that constraint `deferrable initially deferred`, so it is checked at the
  end of the transaction.

## 9. Freshness and ownership

See [`data_dictionary.md`](data_dictionary.md#lineage-and-freshness-week-3) for the lineage, the freshness
guarantee, and who owns the pipeline.
