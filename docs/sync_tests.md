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

**Baseline run:** _to do after `APP_DATABASE_URL` is set_ (paste output here).

**Second run, after at least two more scheduled syncs:** _to do_ (run with `--compare`, paste output, list
which answers changed).

Expected changes: Q15 (age of the last sync) changes on every run. The first time a new matchday is played
(matchday 11 on 27–29 Nov), Q01, Q02, Q03, Q05, Q07, Q09, Q12 and Q19 should change too. If they don't, the
sync is not bringing in new data.
