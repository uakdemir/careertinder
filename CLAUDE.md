# Claude Project Instructions

## Session Bootstrap (do this first)

1. Read `.claude/hotspots.md` for entrypoints, boundaries, and key file locations.
2. Check `tmp/ai_communications/implementation_plans/` for an active plan and continue from the next unchecked item.
3. Keep `## Project Status` (below) up to date at the end of a session.

## Hotspots

Canonical map: `.claude/hotspots.md`. Main entry: `run.py`. Dashboard entry: `src/dashboard/app.py`.

## Review Fixes Workflow

Use `/review-fix [review_file] [response_file]` (see `.claude/skills/review-fix/SKILL.md`).
Review files should be grouped by file with P0/P1/P2 priorities. Apply fixes file-by-file, run type-check + lint + tests once at the end, write response.md with Applied / Pushed back / Deferred per item.

## Continuation Context

```text
I'm continuing from a previous session. Current status: <one-liner>. Pick up where we left off: <next action>.
```

## Implementation Plans

Store short, active plans in `tmp/ai_communications/implementation_plans/` as checkbox lists. Delete/archive when done.

## Project Status

- Current milestone: M0 (Foundation & Project Setup) — analysis complete, awaiting implementation
- Completed: all architecture docs (components, ADRs, roadmap, user stories, risk analysis), M0 detailed analysis reviewed and fixed (2 rounds of Codex review)
- Next action: implement M0 per `tmp/ai/temp/hobby/resume_matcher/analysis/r1/m0.md`

---

## Coding Guidelines

1. Treat this repository as the source of truth: follow existing architecture, folder structure, conventions, and ADRs exactly.
2. Before writing code, restate the key requirements you are implementing and list any missing details that would materially affect correctness, maintainability, security, performance, or UI/UX.
3. Do not make assumptions that change architecture or behavior; if something important is unclear, ask concise clarifying questions first and wait for answers.
4. Keep output token-aware: be brief, avoid repetition, and prefer small, high-signal diffs over long narratives.
5. Produce production-quality code: readable naming, clear boundaries, dependency injection where appropriate, and minimal global state.
6. Prefer simple, standard solutions over cleverness; optimize for maintainability and future onboarding.
7. Follow "tests first where it helps": add focused unit tests and a small number of smoke/integration tests only where they materially reduce risk.
8. Tests must be deterministic, non-brittle, and intention-revealing (clear arrange/act/assert), avoiding over-mocking and over-specification.
9. When modifying code, refactor nearby smells only if it reduces complexity without expanding scope; otherwise keep changes localized.
10. Validate edge cases and error handling for user-facing flows and external integrations (timeouts, retries, input validation), but do not invent features. After multi-file changes, run `ruff check` and `mypy` and report errors before considering the task complete.
11. Prefer explicit types: use type hints on all function signatures and public interfaces. Avoid `Any` unless explicitly requested. Use `pydantic` models for external data boundaries.
12. When asked for explanations, provide short tradeoffs and the recommended choice; expand only if requested.
13. If you detect conflicting requirements, call them out clearly and propose a minimal resolution path before coding.
14. When changing/updating analysis documents that are already done always keep the changes surgical unless otherwise told. Do not change grammatical minor fixes for better looks — I want to be able to identify and confirm surgical changes quickly via diff rather than spending much time to identify the changes that matter due to grammatical punctuation fixes.

### Python-Specific Guidelines

15. Use `async/await` for I/O-bound operations (scraping, AI API calls). Use `asyncio.gather` with semaphores for controlled concurrency.
16. Use `pydantic` for config validation and structured AI response parsing. Use `dataclasses` for internal value objects.
17. Use `SQLAlchemy 2.0` style (declarative, type-annotated models). Always use explicit sessions with context managers.
18. Handle secrets via `.env` + `python-dotenv`. Never hardcode API keys or credentials. Never log secrets.
19. Use `logging` module with named loggers per module (`logging.getLogger(__name__)`). Never use `print()` for operational output.
20. Scrapers must respect rate limits, implement retry with backoff, and catch `playwright.TimeoutError` explicitly.
21. All AI API calls must log model, token counts, and estimated cost. Enforce cost caps before making calls.

---

## Project: JobHunter

### What This Is

Job Search Automation Platform that scrapes postings from 4 job sites, filters them with a 3-tier approach (rule-based → cheap AI → deep AI), evaluates matches against 2 resumes, generates personalized application materials, and presents everything through a local Streamlit dashboard.

Target profile: senior tech professional, remote positions from Turkey, $90K+ salary, two resumes (Leadership/Management and Architect/Developer).

### Tech Stack (see ADRs in docs/architecture/adrs.md)

- **Language:** Python 3.12+ (ADR-001)
- **Database:** SQLite + SQLAlchemy 2.0 ORM + Alembic (ADR-002, ADR-010)
- **Scraping:** Playwright for 2 sites (ADR-003), Apify REST API for LinkedIn + Wellfound (ADR-004)
- **AI Primary:** Anthropic Claude SDK — Haiku for Tier 2, Sonnet for Tier 3 (ADR-005, ADR-006)
- **AI Fallback:** OpenAI SDK — GPT-4o-mini for Tier 2, GPT-4o for Tier 3 (ADR-006)
- **Dashboard:** Streamlit (ADR-007)
- **Config:** YAML + Pydantic validation (ADR-009)
- **Scheduling:** Windows Task Scheduler (ADR-012)
- **Logging:** Python `logging` module, rotating JSON file handler (ADR-016)
- **Testing:** pytest

### Architecture References

- `docs/architecture/components_r1.md` — Components (C0–C11) and Data Structures (DS1–DS11)
- `docs/architecture/adrs.md` — All architectural decision records (ADR-001–ADR-016)
- `docs/project_management/r1/release_roadmap.md` — Milestones M0–M7
- `tmp/ai/temp/hobby/resume_matcher/analysis/r1/user_stories.md` — User stories by epic

### Project Structure (target)

```
jobhunter/                  # main package
  config/                   # C0: config loader, Pydantic models
  scrapers/                 # C1+C2: orchestrator + 4 scraper implementations
  filters/                  # C3: rule-based Tier 1 filter engine
  ai/                       # C4+C5: AI client wrappers, Tier 2+3 evaluators
  generation/               # C6: cover letter + why-company generators
  resume/                   # C7: resume manager, PDF extraction
  db/                       # C8: SQLAlchemy models, session management
  dashboard/                # C9: Streamlit multi-page app
  scheduler/                # C10: pipeline orchestrator
  utils/                    # shared utilities (logging setup, cost tracking)
tests/                      # pytest test suite
alembic/                    # database migrations
data/                       # SQLite DB file, resume PDFs, backups
logs/                       # rotating log files
config.yaml                 # runtime configuration
run.py                      # CLI entry point
```

### Development Environment

- **Windows 11** (native, not WSL)
- **VS Code** with Python + Pylance + SQLite Viewer extensions
- **Claude Code CLI** as primary development tool
- **Virtual environment** via `python -m venv .venv`
- No Docker required (SQLite is file-based)

### Workflow Convention

- Analysis-first: for each milestone, clarify requirements → approve → implement
- Claude Code handles implementation; user reviews in VS Code
- Analysis documents stored in `tmp/ai/temp/hobby/resume_matcher/analysis/r1/`
- All code changes go through git; CLAUDE.md is the persistent context carrier across sessions

### Workflow Style

- Analysis-first: for each milestone, clarify requirements → approve folder structure → implement
- Prompt templates for review workflows stored in `tmp/ai_communications/prompts/`
- Build verification: `ruff check .` + `mypy .` + `pytest` after each implementation task
