# JobHunter - How to Start (Developer Quickstart)

> Personal roadmap for getting this project off the ground fast with Claude Code doing the heavy lifting.

## Prerequisites Checklist

- [ ] **Python 3.12+** installed on Windows ([python.org](https://www.python.org/downloads/))
  - During install: check "Add to PATH"
  - Verify: `python --version`
- [ ] **Git** installed ([git-scm.com](https://git-scm.com/))
- [ ] **VS Code** with these extensions:
  - Python (ms-python.python) -- intellisense, debugging, venv activation
  - Pylance (ms-python.vscode-pylance) -- type checking
  - SQLite Viewer (alexcvzz.vscode-sqlite) -- browse the DB directly in VS Code
  - Python Environment Manager (optional, for switching venvs)
- [ ] **Claude Code CLI** installed and working
- [ ] **API Keys** obtained:
  - [ ] Anthropic API key: [console.anthropic.com](https://console.anthropic.com/)
  - [ ] OpenAI API key: [platform.openai.com](https://platform.openai.com/)
  - [ ] Apify API token: [console.apify.com](https://console.apify.com/) (free tier is fine to start)
  - (Wellfound is scraped via Apify — no separate credentials needed, just the Apify token above)
- [ ] **Two resume PDFs** ready (Leadership and Architect/Developer versions)

## Do I Need PyCharm?

**No.** VS Code + Claude Code is the optimal setup for this project. Here's why:

| Capability | VS Code | PyCharm |
|---|---|---|
| Python intellisense / autocomplete | Pylance (excellent) | Built-in (excellent) |
| Debugging | Built-in Python debugger | Built-in debugger |
| Virtual env management | Auto-detects venvs | Auto-detects venvs |
| SQLite browsing | SQLite Viewer extension | Database tool (Pro only) |
| Git integration | Built-in + GitLens | Built-in |
| Claude Code integration | Native terminal | Terminal works, but no native support |
| Weight / startup time | Lightweight (~200MB) | Heavy (~1GB+, slower startup) |
| Cost | Free | Community: free, Pro: $249/yr |

**Bottom line:** Claude Code writes the code, VS Code provides intellisense for reading/reviewing it, and the SQLite Viewer extension lets you inspect the database. PyCharm's refactoring power is less relevant when Claude handles the implementation. Save PyCharm for when you're deeply debugging a complex issue -- but even then, VS Code's debugger will suffice for this project.

## Step 0: Create the Project (5 minutes)

```powershell
# Navigate to your projects folder
cd "D:\01 Projects\01 Interview\01HobbyProjects"

# Create the project directory
mkdir job-hunter
cd job-hunter

# Initialize git
git init

# Create virtual environment
python -m venv .venv

# Activate it (PowerShell)
.\.venv\Scripts\Activate.ps1

# Verify
python --version   # should be 3.12+
pip --version
```

## Step 1: Bootstrap with Claude Code (10 minutes)

Open the project in Claude Code and ask it to scaffold M0. Give it this context:

```
Read the analysis docs for the JobHunter project:
- docs/architecture/components_r1.md
- docs/architecture/adrs.md
- docs/project_management/r1/release_roadmap.md

Then implement M0 (Foundation & Project Setup):
1. Create pyproject.toml with all dependencies
2. Create the folder structure per the components doc
3. Create all SQLAlchemy ORM models (DS1-DS11) per components_r1.md
4. Set up Alembic for migrations
5. Create config.yaml with all sections from C0
6. Create the config loader with Pydantic validation
7. Set up logging infrastructure
8. Create run.py CLI entry point
9. Set up pytest with in-memory SQLite fixtures
10. Create .gitignore
```

Claude Code will generate the entire foundation. Review each file in VS Code as it's created.

## Step 2: Set Up Environment Variables

Create a `.env` file in the project root (it's gitignored):

```ini
# .env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
APIFY_API_TOKEN=apify_api_...  # used for both LinkedIn and Wellfound scrapers
```

## Step 3: Install Dependencies & Verify

```powershell
# Install project in editable mode
pip install -e ".[dev]"

# Install Playwright browsers (needed for scraping)
playwright install chromium

# Run the initial migration
alembic upgrade head

# Verify everything works
python run.py --help
pytest
```

## Step 4: Add Your Resumes

```powershell
# Create the resumes directory
New-Item -ItemType Directory -Path data\resumes -Force

# Copy your resume PDFs
Copy-Item "C:\path\to\leadership_resume.pdf" "data\resumes\resume_leadership.pdf"
Copy-Item "C:\path\to\architect_resume.pdf" "data\resumes\resume_architect.pdf"

# Extract and store resume text
python run.py --ingest-resumes
```

## Milestone-by-Milestone Development Flow

For each milestone (M1 through M7), follow this pattern:

### 1. Give Claude Code the context

```
Read the roadmap at docs/project_management/r1/release_roadmap.md
and the components doc at docs/architecture/components_r1.md.

Implement M{N} - {Milestone Name}. Follow the task list exactly.
Refer to the component specs and data structures for implementation details.
```

### 2. Review in VS Code
- Read through generated code for correctness
- Check the SQLite database with SQLite Viewer
- Run tests: `pytest -v`
- Run the specific pipeline step: `python run.py --{stage}`

### 3. Test manually
- For scrapers: `python run.py --scrape` (check DB for results)
- For filters: `python run.py --filter` (check filter audit logs)
- For AI: `python run.py --evaluate` (check scores, watch cost)
- For dashboard: `streamlit run src/dashboard/app.py`

### 4. Commit and move on
```powershell
git add -A
git commit -m "Implement M{N}: {milestone name}"
```

## Recommended Development Order

This is the critical path -- follow it sequentially:

```
Day 1:   M0 Foundation        -- Get the skeleton running
Day 1-3: M1 Scrapers          -- Start collecting real data (Apify first, Playwright second)
Day 3-4: M2 Rule Filtering    -- Filter the noise for free
Day 4-5: M3 AI Evaluation     -- Score what survived
Day 5:   M4 Content Gen       -- Generate application materials
Day 6:   M5 Dashboard         -- See everything in a UI
Day 6:   M6 Automation        -- Set it and forget it
Day 7-10: M7 Polish           -- Tune and optimize
```

**Tip:** You can start using the system productively after M3. At that point you'll have scraped jobs, filtered and scored by AI, and you can review them in the database directly or with a simple script while the dashboard is being built.

## Key Files to Understand

These are the files you'll interact with most:

| File | Purpose | When you touch it |
|---|---|---|
| `config.yaml` | All settings | Tuning filters, thresholds, models |
| `run.py` | CLI entry point | Running pipeline stages |
| `src/ai/prompts.py` | AI prompt templates | Tuning evaluation quality |
| `data/jobhunter.db` | SQLite database | Browsing with SQLite Viewer |
| `logs/` | Pipeline logs | Debugging scraper/AI issues |
| `.env` | API keys | Initial setup only |

## Cost Management Tips

1. **Start with Tier 1 only** (M2) -- free, filters 60-70% of noise
2. **Set low cost caps initially** -- `daily_cap: 1.00` until you trust the filtering
3. **Use Haiku/4o-mini for Tier 2** -- $0.001/job, negligible cost
4. **Monitor Tier 3 volume** -- this is where cost lives (~$0.02-0.08/job)
5. **Expected steady-state: $15-60/month** depending on volume

## Troubleshooting Quick Reference

| Problem | Solution |
|---|---|
| `playwright install` fails | Run as admin, or install manually: `playwright install --with-deps chromium` |
| SQLite database locked | Stop the dashboard before running pipeline, or enable WAL mode |
| Wellfound Apify actor fails | Check actor status at apify.com/shahidirfan/wellfound-jobs-scraper, verify APIFY_API_TOKEN |
| AI evaluation returns garbage | Lower temperature to 0.1, check prompt templates |
| Apify quota exhausted | Reduce `max_results`, check billing at console.apify.com |
| Import errors after `pip install -e .` | Reactivate venv: `.\.venv\Scripts\Activate.ps1` |

## Quick Reference Commands

```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Run full pipeline
python run.py --all

# Run individual stages
python run.py --scrape
python run.py --filter
python run.py --evaluate
python run.py --generate

# Launch dashboard
streamlit run src/dashboard/app.py

# Run tests
pytest -v
pytest -v -k "test_salary"  # specific tests

# Database migration
alembic upgrade head
alembic revision --autogenerate -m "description"

# Check database (use Python if sqlite3 CLI is not installed)
python -c "import sqlite3; conn = sqlite3.connect('data/jobhunter.db'); print(conn.execute('SELECT count(*) FROM processed_jobs').fetchone())"
```
