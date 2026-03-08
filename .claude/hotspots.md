# Hotspots

## 1) Repo Overview
- Python 3.12+ project: job search automation platform (JobHunter).
- Backend stack: SQLAlchemy 2.0 + Alembic (PostgreSQL), Pydantic (config/validation), asyncio.
- Scraping stack: Playwright (Remote.io, RemoteRocketship), httpx (Apify REST API for LinkedIn + Wellfound).
- AI stack: Anthropic SDK (primary), OpenAI SDK (fallback), 3-tier filtering pipeline.
- Dashboard: Streamlit multi-page app.
- Primary entrypoints: `run.py` (CLI), `jobhunter/dashboard/app.py` (Streamlit).
- DB schema lives in `jobhunter/db/models.py`, migrations in `alembic/versions/`.
- Config loaded from `config.yaml` + `.env` via `jobhunter/config/loader.py`.
- Pipeline orchestration in `jobhunter/scheduler/runner.py`.

## 2) Hotspot Map

| Area | Start here (entry points) | High-change files/dirs | Config/secrets | Notes |
|---|---|---|---|---|
| CLI / Pipeline | `run.py`, `jobhunter/scheduler/runner.py` | `jobhunter/scheduler/`, `jobhunter/scrapers/`, `jobhunter/filters/`, `jobhunter/ai/` | `config.yaml`, `.env` | `run.py` dispatches to pipeline stages via CLI args. |
| Scrapers | `jobhunter/scrapers/orchestrator.py`, `jobhunter/scrapers/base.py` | `jobhunter/scrapers/remote_io.py`, `jobhunter/scrapers/remoterocketship.py`, `jobhunter/scrapers/apify_base.py`, `jobhunter/scrapers/wellfound_apify.py`, `jobhunter/scrapers/linkedin_apify.py` | `config.yaml` (scraping section), `.env` (APIFY_API_TOKEN) | Playwright scrapers (C2a, C2b) implement `BaseScraper`. Apify scrapers (C2c, C2d) share `ApifyBaseScraper`. Orchestrator runs all with failure isolation. |
| Filtering | `jobhunter/filters/rule_engine.py`, `jobhunter/filters/salary_parser.py` | `jobhunter/filters/` | `config.yaml` (filtering section) | Tier 1 is free/local. Configurable rules via YAML. |
| AI Evaluation | `jobhunter/ai/claude_client.py`, `jobhunter/ai/openai_client.py`, `jobhunter/ai/evaluator.py` | `jobhunter/ai/`, `jobhunter/ai/prompts/` | `.env` (ANTHROPIC_API_KEY, OPENAI_API_KEY), `config.yaml` (ai_models section) | Tier 2 (cheap) + Tier 3 (deep). Cost tracking on every call. |
| Content Gen | `jobhunter/generation/cover_letter.py`, `jobhunter/generation/why_company.py` | `jobhunter/generation/` | `config.yaml` (ai_models.content_gen) | Generates personalized materials for shortlisted jobs. |
| Database | `jobhunter/db/models.py`, `jobhunter/db/session.py`, `alembic/env.py` | `jobhunter/db/`, `alembic/versions/` | `config.yaml` (database section) | SQLAlchemy 2.0 declarative models. DS1-DS11 all in models.py. |
| Dashboard | `jobhunter/dashboard/app.py`, `jobhunter/dashboard/pages/` | `jobhunter/dashboard/` | `config.yaml` (dashboard section) | Streamlit multi-page. Session state for filters/selections. |
| Resume Mgmt | `jobhunter/resume/manager.py`, `jobhunter/resume/extractor.py` | `jobhunter/resume/` | `data/resumes/` | PDF text extraction + key skills extraction. Multi-profile resume model. |

## 3) Commands (copy/paste)

### Find entrypoints
```bash
rg -n "def main|if __name__|click.command|typer.command|st.set_page_config" jobhunter/ run.py -g"*.py"
```

### Find models / schema
```bash
rg -n "class.*Base\)|class.*Model|Column\(|mapped_column\(" jobhunter/db/ -g"*.py"
```

### Find config references
```bash
rg -n "config\.|AppConfig|load_config|settings\." jobhunter/ -g"*.py"
rg -n "os.environ|dotenv|getenv|ANTHROPIC_API_KEY|OPENAI_API_KEY|APIFY_API_TOKEN" jobhunter/ -g"*.py"
```

### Find AI prompts
```bash
rg --files jobhunter/ai/prompts/
rg -n "system_prompt|user_prompt|messages\.append" jobhunter/ai/ -g"*.py"
```

### Find tests
```bash
rg --files tests/ | rg "test_.*\.py$"
```

### Build / lint / test commands
```bash
ruff check .                     # lint
ruff format --check .            # format check
mypy .                           # type check
pytest -v                        # run tests
pytest -v -k "test_salary"      # specific tests
alembic upgrade head             # apply migrations
streamlit run jobhunter/dashboard/app.py  # launch dashboard
```

## 4) Dependency / Integration Touchpoints
- Config boundary: `jobhunter/config/loader.py` loads `config.yaml` + `.env` → `AppConfig` Pydantic model
- DB boundary: `jobhunter/db/session.py` provides `get_session()` context manager; all components use it
- Scraper → DB: `jobhunter/scrapers/orchestrator.py` writes DS1 (RawJobPosting) + DS9 (ScraperRun)
- Filter → DB: `jobhunter/filters/rule_engine.py` writes DS3 (ProcessedJob) + DS10 (FilterResult)
- AI → DB: `jobhunter/ai/evaluator.py` writes DS4 (MatchEvaluation), checks cost caps via DS11
- Content → DB: `jobhunter/generation/` writes DS5 (CoverLetter) + DS6 (WhyCompany)
- Dashboard → DB: read-only queries + DS7 (ApplicationStatus) writes on user actions
- Resume → DB: `jobhunter/resume/manager.py` writes DS8 (ResumeProfile)
- Dedup boundary: `jobhunter/scrapers/orchestrator.py` checks DS11 (JobFingerprint) at ingestion
- Secrets boundary: `.env` file (gitignored), loaded via `python-dotenv`, never logged
