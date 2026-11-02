# BSAD 6153 Project: Kickbase Lineup Assistant

**Student:** Onur Akyol
**My decision:** Which Bundesliga players to line up, buy, and sell in my Kickbase team before each matchday.
**Website:** &lt;your domain, from Week 4&gt;

This repository is one complete AI system, built over eight weeks: a real API, synced on a schedule into a
PostgreSQL database, shown on a public website, with a chatbot and an agent that answer and act from your
own data. You build it with an AI coding agent, and you read and verify everything it writes.

---

## Setting up your computer (Week 1 Setup)

You need a **Windows 10/11 or macOS computer where you can install software**, Git, Python 3.12, and your AI
coding agent (Claude Code, Codex, Antigravity, or Copilot). Let your agent help with the installs, but read
every command before you approve it, and keep auto-approve off.

1. **Clone this repository** into a short folder path that isn't synced by OneDrive or Dropbox, for example
   `C:\dev\bsad6153` on Windows or `~/dev/bsad6153` on macOS.
2. **Create and activate a virtual environment** from the project folder:

   | | Windows (PowerShell) | macOS (Terminal) |
   |---|---|---|
   | Create | `py -3.12 -m venv .venv` | `python3.12 -m venv .venv` |
   | Activate | `.venv\Scripts\Activate.ps1` | `source .venv/bin/activate` |

   You'll see `(.venv)` at the start of your prompt when it's active. Activate it every time you open a new terminal.
3. **Install the packages:** `pip install -r requirements.txt`
4. **Create your secrets file:** copy `.env.example` to `.env`, and put a fake value on the `TEST_SECRET=` line.
5. **Check everything:** `python scripts/check_setup.py` should end with `Setup OK`.
6. **Try the website:** `streamlit run app/streamlit_app.py` opens it in your browser. Press Ctrl+C to stop it.

### Working with your AI agent

- **You approve every command.** Read it first, and if you don't understand it, ask the agent what it does.
- **Ask for a plan before code:** "Before writing anything, tell me your plan."
- **Never paste a real key into the chat,** and never ask the agent to print your `.env` file.
- **The agent never gets the owner database password or deploy tokens.** That's how agents delete databases.
- **Record what you directed, read, verified, and decided** in each pull request's AI review log.

---

## Project layout

| Folder | What goes there | When |
|---|---|---|
| `ingest/` | Fetch, load, and sync code | Weeks 1&ndash;3 |
| `db/` | `schema.sql`, `roles.sql`, `queries.sql` | Weeks 2&ndash;6 |
| `docs/` | Data dictionary, logs, reports (see `docs/README.md`) | Every week |
| `evals/` | Golden questions and evaluation runs | Weeks 3&ndash;7 |
| `app/` | Your website (Streamlit) | Weeks 4&ndash;6 |
| `examples/` | A reference tool-using chatbot loop | Week 5 |
| `scripts/` | Setup and database checks | Weeks 0&ndash;2 |
| `data/sample/` | A small sample of raw API data (large downloads go in `data/raw/`, which Git ignores) | Week 1 |

## Secrets: where each one lives

| Secret | On your computer | On Render (website) | In GitHub Actions (sync) |
|---|---|---|---|
| `DATABASE_URL` (owner) | `.env` | **never** | Actions secret |
| `APP_DATABASE_URL` (read-only) | `.env` | environment setting | if your checks need it |
| `AGENT_DATABASE_URL` | `.env` | environment setting | no |
| LLM key, `APP_PASSWORD` | `.env` | environment setting | no |
| Data API key | `.env` | no | Actions secret |

`.env.example` lists the names only. If a secret ever leaks, revoke or rotate it first, then tell the instructor.

---

## Deploying on Render (Week 4)

1. Claim your free domain through the GitHub Student Developer Pack.
2. In Render, choose **New &gt; Blueprint**, pick this repository, and enter each secret when asked.
   (`render.yaml` describes the service.) Or create a **Web Service** by hand with:
   - Build command: `pip install -r requirements.txt`
   - Start command: `streamlit run app/streamlit_app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true`
   - Environment variables: `PYTHON_VERSION=3.12.4`, `APP_DATABASE_URL`, and later your LLM key and `APP_PASSWORD`
3. Under **Settings &gt; Custom Domains**, add your domain, then add the DNS records Render shows you at your
   registrar. Ask your agent to explain each record before you add it. HTTPS turns on automatically.
4. Free services sleep when idle and take about a minute to wake. Say so on your site.

---

## Troubleshooting

- **`pip install` fails with "No such file or directory" on Windows:** the folder path is too long. Move the
  project to a short path such as `C:\dev\bsad6153` and recreate `.venv`.
- **PowerShell says running scripts is disabled when you activate:** use Command Prompt instead and run
  `.venv\Scripts\activate.bat`, or ask the instructor. Don't change system security settings without asking.
- **`python` opens the Microsoft Store or isn't found:** use `py -3.12` on Windows or `python3.12` on macOS.
- **The database check can't connect:** use Supabase's Session pooler string, check the password, and check
  that your Supabase project isn't paused.

---

## Project proposal (Week 1)

**Data source and backup.** My main source is [OpenLigaDB](https://api.openligadb.de/index.html), a free,
community-run API for German football. It needs no key and allows 60 requests per minute. I use Bundesliga
matches (with results and goals), teams, and the league table for the finished 2025/26 season and the running
2026/27 season. The data is under the ODbL 1.0 license. OpenLigaDB is not on the course menu, so **I ask the
instructor to approve it**. My backup is [football-data.org](https://www.football-data.org) (free key, also
covers the Bundesliga). The official Kickbase API is not public and needs my personal login, so I do not use it.

**My decision and workflow.** Before each Bundesliga matchday I decide which players to line up in my Kickbase
team, and during the week which players to buy or sell.
Today I make this decision mainly with Ligainsider and the Kickbase app. One lineup decision takes me about 12 minutes. The hardest part is knowing whether the predicted lineups are really correct, and how the players are doing mentally, because a player who does not start or is out of form earns me no points.
My system should bring the information I need into one place, so I decide faster and with more confidence.

**Agent idea (first draft).** Before each matchday, an agent checks the upcoming fixtures, each team's recent
results, and which players have been scoring. It then proposes a lineup and a short list of players to buy
or sell, with a reason for each. I review the proposal and make the final change in Kickbase myself; the agent
never acts in my Kickbase account.

**Risks.**
- *Rate limits:* 60 requests per minute. My script waits 1.2 seconds between requests and backs off on 429.
- *Access:* OpenLigaDB is run privately by volunteers and could be slow or go offline; then I switch to the backup.
- *Data quality:* some goals have no scorer or minute, and Kickbase points and market values are not in the data.
- *Data volume:* small (about 70 requests and a few MB per sync), so this is low risk.
- *Terms of service:* ODbL requires attribution and sharing a changed database under the same license; I credit
  OpenLigaDB on my website.

## How to run this project

From the project folder, with the virtual environment active (`source .venv/bin/activate`):

```
python ingest/fetch.py                  # fetch seasons 2025 and 2026 into data/raw/ (about 3 minutes)
python ingest/fetch.py --seasons 2026   # fetch only the running season
```

The script needs no API key. It prints a summary of requests, records, missing fields, and failures.
Raw files go to `data/raw/` (not in Git); a small sample is in `data/sample/`.

## Credits

Football data from [OpenLigaDB](https://www.openligadb.de), licensed under the
[Open Database License (ODbL 1.0)](https://opendatacommons.org/licenses/odbl/1-0/).
