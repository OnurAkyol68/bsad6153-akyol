# Sync Tests: Break It on Purpose (Week 3)

All tests ran on **2026-11-22** (times in UTC) against my Supabase database, with `python ingest/sync.py`
started by hand (`trigger = manual`). Following "predict, then check", the prediction was written down before
each run and compared with the `sync_runs` row afterwards.

OpenLigaDB needs no API key, so the "bad credentials" test does not apply to my project. I ran the other
three tests plus the required golden-question check.

## Test 0: First sync after the Milestone 2 load (runs 1 and 2)

**Prediction:** my Milestone 2 data was loaded on 10 Nov. Since then only matchday 10 (20–22 Nov) was played,
so I expected **1 matchday** refetched: 9 matches updated, about 25 new goals, a few new scorers, and all 18
table rows of 2026 updated.

**Result (run 1):** `success`, fetched 54, **inserted 28** (23 goals, 5 players), **updated 45** (27 matches,
18 standings), matchdays **9, 10, 11, 12**.

**Prediction vs. result: they disagreed, and my understanding was wrong, not the code.** The goals, players
and standings matched my prediction, but 4 matchdays changed instead of 1:
- matchday 9 (already played on 6–8 Nov): 1 match was changed again on 10 Nov, after my load;
- matchdays 11 and 12 (not yet played): 17 matches were changed on 20 Nov, because OpenLigaDB fixed their
  exact kickoff times.

So finished matches and future matches both change at the source. I added this to the change log in
`docs/data_quality.md` and `docs/data_dictionary.md`.

## Test 1: Rerun (runs 1 → 2, and 6 → 7)

**What I did:** ran the sync twice back to back.
**Prediction:** second run: 0 matchdays refetched, 0 inserted, 0 updated.
**Result:** both times the second run reported `success, inserted 0, updated 0`. It still fetched 18 records:
these are the 18 rows of the league table, which is read on every run (one request) and compared row by row;
none changed, so nothing was written. The watermark check skipped all 34 matchdays.

| run_id | started | status | fetched | inserted | updated | matchdays_synced |
|---|---|---|---|---|---|---|
| 1 | 21:04:12 | success | 54 | 28 | 45 | 2026: 9, 10, 11, 12 |
| 2 | 21:05:37 | success | 18 | 0 | 0 | – |
| 6 | 21:13:06 | success | 27 | 0 | 9 | 2026: 10 |
| 7 | 21:14:08 | success | 18 | 0 | 0 | – |

## Test 2: Source change (simulated) + interrupted run (runs 5 and 6)

**What I did:** I simulated a record that is out of date compared with the source:
1. Changed match 83237 (Bayern – Köln, matchday 10, really 1:1) in my database to **4:1**.
2. Moved `source_updated_at` of all 9 matchday-10 matches back by 30 days, so the watermark says "matchday 10
   is older in my database than at OpenLigaDB" (exactly what happens when the source changes a match).
3. **Interrupted run:** started the sync with `--crash-after 1`, which raises an error right after the first
   refetched matchday has been written, but before the commit.
4. Started a normal sync.

**Prediction for step 3:** status `failed`, exit code 1, nothing saved: match 83237 still shows 4:1, row counts
unchanged.
**Result for step 3 (run 5):** `failed`, `error_message = RuntimeError: simulated crash after 1 matchday(s)
(--crash-after)`, exit code 1. Match 83237 was still 4:1 with the old `last_updated_at`, and all row counts
were unchanged (612 matches, 1,299 goals). The 9 matches written before the crash were rolled back.

**Prediction for step 4:** matchday 10 is refetched, **9 matches updated** (all 9 get their real
`source_updated_at` back, one of them also its score), 0 inserted, 0 duplicates.
**Result for step 4 (run 6):** `success`, fetched 27, inserted 0, **updated 9**, matchdays `2026: 10`.
Match 83237 is back to **1:1**, `source_updated_at` back to 2026-11-21 17:21, `last_updated_at` moved to the
run time. Row counts unchanged, so no duplicates. Run 7 afterwards: 0 / 0.

| run_id | started | status | fetched | inserted | updated | error_message |
|---|---|---|---|---|---|---|
| 5 | 21:12:42 | failed | 9 | 0 | 0 | RuntimeError: simulated crash after 1 matchday(s) (--crash-after) |
| 6 | 21:13:06 | success | 27 | 0 | 9 | – |

I also ran a crash during a `--full` run (run 3, crash after matchday 2) followed by a normal run (run 4): same
behaviour, `failed` with nothing written, then `success` with 0 / 0.

## Golden-question check

The reference queries in `evals/golden_questions.csv` are run with `python evals/check_reference.py`, which
connects as `app_reader`.

**Baseline run (2026-11-22, 21:45 UTC, after sync run 8):** all 14 reference queries run as `app_reader` and
return rows; the 5 should_decline questions have no SQL. Saved as `evals/reference_runs/2026-11-22_2145.json`.

```
$ python evals/check_reference.py
Connected as app_reader, 2026-11-22 21:45 UTC

Q01  ok    15 rows   player=Romulo, team=Leipzig, goals=5, penalties=0
Q02  ok    18 rows   team=Leipzig, played=4, points=12, goals_for=16, goals_against=3
Q03  ok     9 rows   matchday=11, kickoff_german_time=2026-11-27 20:30:00, home_team=Bremen, home_position=6, h
Q04  ok    18 rows   player=A. Caci, matchday=5, match=Mainz - Leverkusen, minute=42, is_penalty=False
Q05  ok     6 rows   position=18, team=Gladbach, matches_played=10, won=1, draw=1, lost=8, goals=12:26, points=
Q06  ok     8 rows   minute_block=01-15, goals=153, percent_of_all_goals=11.8
Q07  ok     1 rows   matchday=11, kickoff_german_time=2026-11-27 20:30:00, home_team=Bremen, away_team=Gladbach
Q08  ok     2 rows   season=2025, goals=13, matches_with_goal=9
Q09  ok     5 rows   matchday=10, match=Bayern - Köln, bayern_goals=1
Q10  skip  (should_decline: no reference SQL)
Q11  skip  (should_decline: no reference SQL)
Q12  ok     5 rows   position=1, team=Dortmund, matches_played=10, points=24, goals=17:7
Q13  ok     3 rows   season=2025, matchday=7, match=Bayern - Dortmund, result=2:1
Q14  ok     7 rows   player=N. Füllkrug, team=Bremen, penalties=3
Q15  ok     1 rows   last_successful_sync=2026-11-22 21:41:39.447416+00:00, age=0:03:53.224494
Q16  skip  (should_decline: no reference SQL)
Q17  skip  (should_decline: no reference SQL)
Q18  skip  (should_decline: no reference SQL)
Q19  ok     1 rows   finished_matches=90, pct_home_wins=50.0, pct_draws=21.1, pct_away_wins=28.9

14 of 14 reference queries OK; saved to evals/reference_runs/2026-11-22_2145.json
```

**Second run (2026-11-22, 21:51 UTC, after sync run 9).** Honest limitation: the assignment asks for this
run after at least two more *scheduled* syncs. My schedule only started today at 21:40 UTC (PR 1 was merged
on the deadline day), so the first scheduled run is at about 00:17 UTC on 23 Nov. Between the baseline and this
run there were only manual syncs (the GitHub Actions run 8 and the local run 9), and neither found new data.

```
$ python evals/check_reference.py --compare
Connected as app_reader, 2026-11-22 21:51 UTC

Q01  ok    15 rows  same   player=Romulo, team=Leipzig, goals=5, penalties=0
Q02  ok    18 rows  same   team=Leipzig, played=4, points=12, goals_for=16, goals_against=3
Q03  ok     9 rows  same   matchday=11, kickoff_german_time=2026-11-27 20:30:00, home_team=Bremen, home_position=6, h
Q04  ok    18 rows  same   player=A. Caci, matchday=5, match=Mainz - Leverkusen, minute=42, is_penalty=False
Q05  ok     6 rows  same   position=18, team=Gladbach, matches_played=10, won=1, draw=1, lost=8, goals=12:26, points=
Q06  ok     8 rows  same   minute_block=01-15, goals=153, percent_of_all_goals=11.8
Q07  ok     1 rows  same   matchday=11, kickoff_german_time=2026-11-27 20:30:00, home_team=Bremen, away_team=Gladbach
Q08  ok     2 rows  same   season=2025, goals=13, matches_with_goal=9
Q09  ok     5 rows  same   matchday=10, match=Bayern - Köln, bayern_goals=1
Q10  skip  (should_decline: no reference SQL)
Q11  skip  (should_decline: no reference SQL)
Q12  ok     5 rows  same   position=1, team=Dortmund, matches_played=10, points=24, goals=17:7
Q13  ok     3 rows  same   season=2025, matchday=7, match=Bayern - Dortmund, result=2:1
Q14  ok     7 rows  same   player=N. Füllkrug, team=Bremen, penalties=3
Q15  ok     1 rows  CHANGED   last_successful_sync=2026-11-22 21:51:50.168695+00:00, age=0:00:02.459886
Q16  skip  (should_decline: no reference SQL)
Q17  skip  (should_decline: no reference SQL)
Q18  skip  (should_decline: no reference SQL)
Q19  ok     1 rows  same   finished_matches=90, pct_home_wins=50.0, pct_draws=21.1, pct_away_wins=28.9

14 of 14 reference queries OK; saved to evals/reference_runs/2026-11-22_2151.json
Compared with run of 2026-11-22T21:45 UTC: 1 answers changed (Q15)
```

**Which answers changed:** only **Q15** (age of the last sync), which changes on every run by design. All 14
reference queries still run as `app_reader` and return rows.

**Why the others didn't change:** no match was played between the two checks. Matchday 10 ended today at 18:30
UTC and was already synced in run 1; matchday 11 starts on 27 Nov. So identical answers are what a correct sync
should produce here, not a sign that it is stuck. The sync does bring in new data when the source changes:
run 1 (before the baseline) took the database from 1,276 to 1,299 goals and updated all 18 table rows after
matchday 10, which changed the answers to Q01, Q02, Q05, Q09, Q12 and Q19 compared with the Milestone 2 data
(for example Q19 went from 81 to 90 finished matches of 2026/27).

**Follow-up:** after matchday 11 (27–29 Nov) I will run `python evals/check_reference.py --compare` again;
then Q01, Q02, Q03, Q05, Q07, Q09, Q12 and Q19 must change.
