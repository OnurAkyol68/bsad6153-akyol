# Implementation Brief: Kickbase Lineup Assistant (v1)

**Onur Akyol · 18 Nov 2026** · Living document, revised in later milestones.

## 1. My workflow
Before each Bundesliga matchday I decide which players to line up in my Kickbase team, and during the week which to buy or sell: about **10 decisions per week**. I do it by hand across three tools: predicted lineups on Ligainsider, news and social media for injuries, and market values and the transfer market in the Kickbase app. My [baseline log](baseline_log.md) (5 entries, reconstructed from memory) shows 5 to over 15 minutes per decision, **about 10 minutes on average, or about 100 minutes per week**, with confidence as low as 1 of 5.
**Frustrations:** jumping between three tools for the same player; not knowing whether a player will start or how good his form is; not knowing how strong the opponent is.

## 2. Should this use AI?
| Option | Solves | Costs | Could go wrong |
|---|---|---|---|
| **A. No new technology:** weekly routine and checklist | Fewer random decisions | Nothing | Still three tools and ~100 min/week; discipline fades |
| **B. Data without AI:** dashboard on my database (opponent rank, team form, recent scorers) | Form and opponent strength in one place | Free tiers; ~10–15 h of building | Goals-only data hides defenders; no lineups or injuries; stale if sync fails |
| **C. LLM chatbot and agent** (Milestones 5–6): agent proposes a lineup with reasons, I decide | One reasoned proposal from several views | ~$1–9/month API, build and test time | Invented facts; false certainty; API costs |

**What actually needs an LLM:** Goal counts, form tables, and opponent strength are plain SQL, so **most of the value comes from Option B**. The LLM handles only the narrow part: understanding my free-text questions and summarizing several query results. It never calculates numbers; it calls my SQL queries.

## 3. Value hypothesis
- **Time:** baseline ~10 min per decision (~100 min/week); **target under 4 min (~40 min/week)**.
- **Confidence:** baseline average **2.4 of 5** (log values 1, 3, 3, 4, 1); **target 3.5 or higher**.

**Measurement:** from Milestone 4 I log every real decision in [`usage_log.md`](usage_log.md) with a timer and the baseline columns, and compare averages after 10 entries. The baseline is reconstructed, so the comparison is rough. Kickbase points are not a target yet (too much luck).

## 4. Early cost estimate
**Assumptions:** 10 decisions/week × 3 questions ≈ 130 questions/month, plus ~100 eval questions and ~5 agent runs. One question ≈ 3 API calls, ~12,000 input and 1,200 output tokens.
**Prices** ([Anthropic](https://platform.claude.com/docs/en/about-claude/pricing), checked 18 Nov 2026): Claude Haiku 5.5 $0.10 / $0.50 per million input/output tokens; Claude Sonnet 5.5 $2 / $10. That is ~$0.002 (Haiku) or ~$0.04 (Sonnet) per question, so **under $1/month with Haiku, ~$9 with Sonnet**. I start with Haiku. Hosting: $0.
**Hard cap:** **$20 prepaid API credit, auto-reload off**; the chatbot is behind a password, max 30 questions/day.
**At the cap:** the API refuses the call and the app shows "Chatbot paused: budget reached. The data views still work." The dashboard needs no LLM, so the main value stays.

## 5. My stack
**Supabase** (database, free tier) · **GitHub Actions** (scheduled sync, free for public repos) · **Render** (website, free tier, sleeps when idle, ~1 min to wake, stated on the site) · **Anthropic API** ($20 prepaid; a Claude Pro subscription doesn't pay for API calls).

## 6. Risks and governance
- **If it is wrong:** I bench or sell the wrong player and lose points or budget; no real money is at stake, but confident wrong answers build false trust.
- **Who could be misled or harmed:** me; visitors to my public site who copy a recommendation (the site says the data covers goals only and is not advice); and the players, because goals-only data makes defenders, goalkeepers, and weak teams look "out of form" (Schalke 4 goal records vs. Bayern 27 this season).
- **Data about real people:** names and goal records of Bundesliga players, public data under ODbL. No user data and no Kickbase login.
- **The AI must never:** act in my Kickbase account; invent statistics not in my database; write to the database (read-only role); guess about a player's health or mental state beyond what is reported; give betting advice; or run without sign-in and spending cap.

## 7. Scorecard self-assessment (v1)
| # | Factor | Rating | Justification |
|---|---|---|---|
| 1 | Real user and workflow | 🟢 | I am the user; a logged decision, 10 times a week. |
| 2 | Data access | 🟡 | OpenLigaDB is free and legal but lacks lineups, injuries, market values. |
| 3 | Data understanding | 🟡 | My data dictionary and quality report document the gaps. |
| 4 | Freshness and monitoring | 🟡 | Staleness warning exists; the scheduled sync is still being built. |
| 5 | Grounding | 🟡 | Answers only from SQL tools is planned, not yet tested. |
| 6 | Bounded autonomy | 🟢 | The agent only proposes; I make every Kickbase change; read-only database role. |
| 7 | Evaluation | 🟡 | Golden questions are planned; "correct" is not measured yet. |
| 8 | Measured value and cost | 🔴 | Reconstructed baseline and estimated costs: no real evidence yet. |
| 9 | Adoption | 🟡 | Without lineups I may keep going back to Ligainsider out of habit. |
| 10 | Governance and accountability | 🟢 | I am responsible; spending cap, sign-in, disclaimer, "never" rules. |

**Plans for the two weakest:**
- **Measured value and cost (red):** this week I log at least 3 decisions with a real timer; from Milestone 4 I log every use, and from Milestone 5 the real token cost of every question.
- **Data access (yellow):** I check whether my backup source (football-data.org) has lineups or injuries. If not, the site links to Ligainsider next to each player and labels form values "goals only", so missing data is never read as bad form.
