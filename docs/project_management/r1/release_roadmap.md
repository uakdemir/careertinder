# JobHunter - Release Roadmap (R1)

> **Project:** Job Search Automation Platform (JobHunter)
> **Version:** R1 (Initial Release)
> **Last Updated:** 2026-03-03
> **Target Platform:** Windows (local execution)

## Overview

JobHunter is a locally-run job search automation platform that scrapes postings from four job sites, applies a three-tier AI filtering approach (rule-based, cheap-model triage, strong-model deep evaluation), generates personalized application materials, and presents everything through a Streamlit dashboard. The system is designed to run unattended via Windows Task Scheduler, minimizing manual effort while keeping the human in the loop for final application decisions.

### Technology Stack

| Component            | Technology                              |
| -------------------- | --------------------------------------- |
| Language             | Python 3.12+                            |
| Browser Automation   | Playwright                              |
| External Scraping    | Apify API (LinkedIn + Wellfound)        |
| Database             | SQLite + SQLAlchemy ORM + Alembic       |
| AI - Primary         | Claude SDK (Anthropic)                  |
| AI - Fallback        | OpenAI SDK                              |
| Dashboard            | Streamlit                               |
| Scheduling           | Windows Task Scheduler                  |
| Config               | YAML (config.yaml)                      |
| Testing              | pytest                                  |

---

## Summary Timeline

> **Development model:** Claude Opus generates all code; user provides async review, live testing, and credentials. Estimates below reflect this AI-assisted workflow, not solo human development.

| Milestone | Name                          | Complexity | Est. Duration | Depends On | Cumulative |
| --------- | ----------------------------- | ---------- | ------------- | ---------- | ---------- |
| M0        | Foundation & Project Setup    | S          | 2-3 hours     | --         | Day 1      |
| M1        | Scraper Infrastructure        | L          | 2-3 days      | M0         | Day 4      |
| M1.5      | Dashboard Companion (Early UI)| M          | 4-6 hours     | M0, M1     | Day 5      |
| M2        | Tier 1 Rule-Based Filtering   | S          | 2-4 hours     | M1         | Day 5      |
| M3        | AI Evaluation Pipeline        | M          | 3-5 hours     | M2         | Day 6      |
| M4        | Content Generation            | S          | 2-3 hours     | M3         | Day 6      |
| M5        | Dashboard Review Workflow     | M          | 3-4 hours     | M4, M1.5   | Day 7      |
| M6        | Automation & Scheduling       | S          | 1-2 hours     | M5         | Day 7      |
| M7        | Integration Testing & Fixes   | M          | 1-2 days      | M6         | Day 8-9    |

**Total estimated duration: 7-10 days (1-1.5 weeks)**

### Why this is achievable

- M0, M2, M3, M4, M6 are **deterministic code** — Claude Opus writes ORM models, rule engines, API wrappers, prompt templates, and Streamlit pages in single sessions with no ambiguity.
- **M1.5 introduces the dashboard early** — the UI grows incrementally alongside the backend rather than being a monolithic M5 build. Each backend milestone extends the existing dashboard with new pages.
- M5 (Dashboard Review Workflow) is now **reduced in scope** — it only adds the job review, approve/reject, and ready-to-apply views on top of the existing M1.5 dashboard shell.
- **M1 (Scrapers) is the bottleneck** — the only milestone requiring iterative live testing against real websites. See `risky_components.md` for mitigation.
- M7 absorbs scraper fixes, integration issues, and prompt tuning discovered during real use.

### Parallel UI Philosophy

**Every backend milestone gets a corresponding UI surface immediately.** The dashboard is not a deferred monolith — it grows incrementally:

| Backend Milestone | UI Surface Added |
|---|---|
| M0 | Resume upload, DB status (via M1.5) |
| M1 | Raw job browser, scraper runs, scraper config, trigger scrape (via M1.5) |
| M2 | Filter results view, rule config editor (M2 extends dashboard) |
| M3 | Evaluation results, cost tracker (M3 extends dashboard) |
| M4 | Cover letter viewer, "why company" viewer (M4 extends dashboard) |
| M5 | Job review workflow, approve/reject, ready-to-apply (extends dashboard) |
| M6 | Pipeline status, scheduling config (extends dashboard) |

### MVP Scope Cuts (deferred to post-MVP)

| Feature | Originally in | Deferred to |
|---|---|---|
| OpenAI fallback provider | M3 | Post-MVP (Claude-only is sufficient) |
| Content versioning (multiple versions per job) | M4 | Post-MVP (single version is fine) |
| Circuit breaker pattern | M1 | Post-MVP (simple try/except for MVP) |
| Dashboard analytics/charts | M5 | Post-MVP |
| Daily summary reports | M6 | Post-MVP |
| Desktop notifications | M6 | Post-MVP |
| Data export (CSV/Excel) | M7 | Post-MVP |
| Company research enrichment | M4 | Post-MVP |

---

## Dependency Graph

```
M0 (Foundation)
 |
 +---> M1 (Scrapers) ---> M2 (Rule Filtering) ---> M3 (AI Evaluation)
 |         |                                             |
 |         v                                             v
 |     M1.5 (Early UI) --------+               M4 (Content Generation)
 |                              |                        |
 |                              v                        v
 |                          M5 (Review Workflow) <-------+
 |                              |
 |                              v
 |                          M6 (Automation)
 |                              |
 |                              v
 |                          M7 (Polish)
```

The backend pipeline (M1→M2→M3→M4) is linear. M1.5 branches off after M1 to provide early UI, then M5 merges both tracks (M4 backend + M1.5 dashboard shell). The primary constraint is **user availability for live testing** (scrapers, credentials, API keys).

---

## Critical Path Analysis

With AI-assisted development, the bottleneck shifts from "writing code" to "testing against live systems." The single critical path risk is:

1. **M1 (Scraper Infrastructure)** -- The ONLY milestone requiring iterative live testing. For the 2 Playwright scrapers (Remote.io, RemoteRocketship), site HTML structures must be inspected in real-time and selectors verified. The 2 Apify scrapers (LinkedIn, Wellfound) are REST API integrations with deterministic JSON output. Claude generates all scraper code, but the user must run Playwright scrapers and report results. **Mitigation:** Start with Apify scrapers first (LinkedIn + Wellfound in ~1 hour), then iterate on Playwright scrapers.

2. **M3 (AI Evaluation Pipeline)** -- Low risk. Prompt engineering is fast when Claude writes the prompts and the user reviews AI output quality on a handful of real jobs. Structured JSON output with response validation catches format issues immediately.

3. **M5 (Dashboard)** -- Low risk for MVP. A minimal Streamlit table with filters is a few hours of work. The risk is scope creep — resist adding charts, analytics, and fancy layouts until the pipeline is proven.

**Buffer:** M7 (1-2 days) exists specifically to absorb scraper failures, prompt tuning, and integration issues found during first real pipeline runs.

---

## Cost Estimation (API Costs by Milestone)

| Milestone | API Costs | Notes |
| --------- | --------- | ----- |
| M0        | $0        | No external API calls. |
| M1        | ~$5-15/mo | Apify free tier may suffice for LinkedIn; paid tier ~$49/mo if volume is high. Playwright scrapers are free. |
| M2        | $0        | Purely local rule-based filtering. No API calls. |
| M3        | ~$10-30/mo | Tier 2 (Haiku/4o-mini): ~$0.001-0.005 per job evaluation. Tier 3 (Sonnet/4o): ~$0.02-0.08 per deep evaluation. At 200 jobs/week with 30% reaching Tier 3: roughly $8-25/month. |
| M4        | ~$5-15/mo | Cover letter + "Why this company" generation for shortlisted jobs. At ~20 jobs/week reaching generation: ~$4-12/month. |
| M5        | $0        | Dashboard is local Streamlit; no API costs. |
| M6        | $0 incremental | Costs already accounted for in M3/M4 running on schedule. |
| M7        | $0 incremental | Optimization may reduce M3/M4 costs. |

**Estimated monthly running cost (steady state): $15-60/month** depending on volume and how aggressively Tier 1 filters.

---

## Milestones

---

### M0 -- Foundation & Project Setup

**Complexity: S (Small)**

#### Description

Establish the complete project skeleton including build configuration, virtual environment, database schema, and all core data structures. This milestone produces no user-facing functionality but ensures every subsequent milestone has solid infrastructure to build on. By the end of M0 the database is created, resumes are loadable, and the test harness is operational.

#### Dependencies

None.

#### Task List

- [ ] Initialize Python project with `pyproject.toml` (project metadata, dependencies, scripts entry point)
- [ ] Create virtual environment and pin all initial dependencies
- [ ] Establish folder structure:
  ```
  jobhunter/
    config/
    scrapers/
    filters/
    ai/
    generation/
    dashboard/
    models/
    utils/
  tests/
  alembic/
  data/
  docs/
  ```
- [ ] Create `config.yaml` with all parameter definitions:
  - [ ] Scraper settings (URLs, selectors, rate limits, credentials reference)
  - [ ] Filter rules (salary range, title patterns, keywords, blacklists)
  - [ ] AI settings (model names, temperature, max tokens, cost caps)
  - [ ] Dashboard settings (port, page size)
  - [ ] Scheduling settings (cron expression, retry policy)
- [ ] Config loader module with validation and defaults
- [ ] Set up SQLite database with SQLAlchemy engine and session management
- [ ] Implement all ORM models (DS1-DS11):
  - [ ] DS1: `RawJobPosting` (raw scraped data before processing)
  - [ ] DS2: `Company` (company metadata)
  - [ ] DS3: `ProcessedJob` (normalized job data, canonical record)
  - [ ] DS4: `MatchEvaluation` (AI scoring results)
  - [ ] DS5: `CoverLetter` (generated cover letters with versioning)
  - [ ] DS6: `WhyCompany` (generated "why this company" answers)
  - [ ] DS7: `ApplicationStatus` (status tracking state machine)
  - [ ] DS8: `ResumeProfile` (resume metadata and extracted text)
  - [ ] DS9: `ScraperRun` (per-run scraper audit records)
  - [ ] DS10: `FilterResult` (filter decision trail)
  - [ ] DS11: `JobFingerprint` (deduplication tracking)
- [ ] Set up Alembic for database migrations with initial migration
- [ ] Resume text extraction pipeline (PDF to plain text using `pdfplumber` or `PyMuPDF`)
- [ ] Store extracted resume text in DS8 (ResumeProfile) with metadata (filename, extraction date, hash)
- [ ] Basic CLI entry point (`run.py`) with argument parsing (--scrape, --filter, --evaluate, --generate, --all)
- [ ] Logging infrastructure (rotating file handler, console handler, configurable log level)
- [ ] pytest setup with fixtures for in-memory SQLite database
- [ ] Write unit tests for config loader, ORM models, and resume extraction
- [ ] `.gitignore` configured for Python, SQLite, virtual env, IDE files

#### Key Risks and Mitigations

| Risk | Impact | Mitigation |
| ---- | ------ | ---------- |
| Data model changes later in the project | Medium | Use Alembic migrations from day one so schema changes are manageable. Keep models normalized but not over-engineered. |
| Config schema becomes unwieldy | Low | Use a structured config with clear sections and defaults. Validate on load. |
| PDF extraction quality varies across resume formats | Medium | Support multiple extraction backends; store raw text and allow manual correction. |

#### Acceptance Criteria

1. `python run.py --help` prints usage information and exits cleanly.
2. Running the project creates the SQLite database with all tables matching the ORM models.
3. A PDF resume placed in the designated folder is extracted to text and stored in the database.
4. `alembic upgrade head` and `alembic downgrade -1` both succeed.
5. `pytest` runs and all tests pass with zero external dependencies.
6. `config.yaml` is loaded and validated; missing required fields produce clear error messages.

---

### M1 -- Scraper Infrastructure

**Complexity: L (Large)**

#### Description

Build the complete scraping layer with implementations for all four job sources: Remote.io, RemoteRocketship, Wellfound, and LinkedIn (via Apify). Each scraper conforms to an abstract base class, enabling uniform orchestration. The milestone also delivers deduplication, audit logging, and resilience patterns (rate limiting, circuit breakers, retries).

#### Dependencies

M0 (database, ORM models, config, logging).

#### Task List

- [ ] Design and implement abstract `BaseScraper` class:
  - [ ] Common interface: `scrape() -> list[RawJob]`, `validate()`, `health_check()`
  - [ ] Built-in retry decorator with exponential backoff
  - [ ] Built-in rate limiter (configurable requests-per-minute)
  - [ ] Session/context management for Playwright browser lifecycle
- [ ] **Remote.io scraper** (Playwright):
  - [ ] Navigate to job listing pages with pagination
  - [ ] Extract job title, company, description, salary (if present), URL, posted date
  - [ ] Handle dynamic page loading (wait for selectors, scroll-based loading)
  - [ ] Map extracted data to `Job` ORM model
  - [ ] Unit/integration tests with saved HTML fixtures
- [ ] **RemoteRocketship scraper** (Playwright):
  - [ ] Navigate to job listing pages with pagination
  - [ ] Extract structured job data (title, company, description, tags, salary, URL)
  - [ ] Handle any required search filters or category navigation
  - [ ] Map extracted data to `Job` ORM model
  - [ ] Unit/integration tests with saved HTML fixtures
- [ ] **Wellfound scraper** (Apify REST API):
  - [ ] Apify API client using shared `ApifyBaseScraper` base class (same as LinkedIn)
  - [ ] Configure Wellfound scraper actor (`shahidirfan/wellfound-jobs-scraper`) with search parameters from config
  - [ ] Poll for actor run completion and retrieve results
  - [ ] Parse Apify output format into `Job` ORM model (includes equity range, company stage, team size)
  - [ ] Handle Apify rate limits and billing tier constraints
  - [ ] Unit tests with mocked API responses
- [ ] **LinkedIn scraper** (Apify REST API):
  - [ ] Apify API client wrapper (API key management, request/response handling)
  - [ ] Configure LinkedIn scraper actor with search parameters from config
  - [ ] Poll for actor run completion and retrieve results
  - [ ] Parse Apify output format into `Job` ORM model
  - [ ] Handle Apify rate limits and billing tier constraints
  - [ ] Unit tests with mocked API responses
- [ ] **Scraper orchestrator**:
  - [ ] Run all scrapers sequentially or in parallel (configurable)
  - [ ] Aggregate results from all sources
  - [ ] Per-scraper enable/disable toggle in config
  - [ ] Timeout handling per scraper (kill long-running scrapes)
- [ ] **Job fingerprinting and deduplication**:
  - [ ] Generate fingerprint: `SHA-256(normalize(company) + "|" + normalize(title))` per ADR-008
  - [ ] On fingerprint match: append source URL to `DS11.source_urls`, increment `times_seen` — no duplicate record
  - [ ] Cross-source deduplication is automatic (fingerprint excludes URL domain)
  - [ ] Same-source re-scraping deduplication is automatic (same fingerprint, same source)
- [ ] **Per-run audit logging** (DS9):
  - [ ] Record: scraper name, start time, end time, jobs found, jobs new, jobs duplicate, errors
  - [ ] Store full error tracebacks for failed runs
- [ ] **Rate limiting and politeness**:
  - [ ] Configurable delay between requests per scraper
  - [ ] Respect `robots.txt` where applicable
  - [ ] Randomized delay jitter to reduce detection risk
- [ ] **Error handling**:
  - [ ] Graceful degradation: one scraper failing does not block others (try/except per scraper)
  - [ ] Log errors and continue to next scraper
  - [ ] *(Post-MVP)* Circuit breaker: after N consecutive failures, disable scraper for configurable cooldown

#### Key Risks and Mitigations

| Risk | Impact | Mitigation |
| ---- | ------ | ---------- |
| Site layout changes break scrapers | High | Use saved HTML fixtures for tests; structure selectors in config for easy updates; build a health-check command. |
| Anti-bot detection blocks Playwright scrapers | High | Use stealth mode (playwright-stealth), rotate user agents, add human-like delays, consider headed mode for debugging. |
| Wellfound Apify actor format changes | Low | Pin actor version; abstract behind common scraper interface. Community actor has higher change risk than official actors. |
| Apify pricing exceeds expectations | Medium | Monitor Apify usage; set monthly caps in config; fall back to reduced frequency if budget is hit. |
| Playwright installs browsers, increasing setup complexity | Low | Document browser install step; pin Playwright version; include in setup script. |

#### Acceptance Criteria

1. Each of the four scrapers successfully retrieves at least one page of job listings when run individually.
2. `python run.py --scrape` runs all enabled scrapers and stores results in the database.
3. Running the scraper twice on the same data produces no duplicate `Job` records.
4. Audit log (DS9) contains accurate records for each scraper run, including job counts and timing.
5. A deliberately failed scraper (e.g., invalid URL) is handled gracefully; other scrapers still complete.
6. Rate limiting is observable in logs (delays between requests).

---

### M1.5 -- Dashboard Companion (Early UI)

**Complexity: M (Medium)**

#### Description

Deliver a minimal but functional Streamlit dashboard that provides immediate visibility into M0 and M1 outputs. This includes resume management (upload/view/delete), scraper configuration editing, raw job browsing, scraper run audit viewing, and the ability to trigger scrapes from the UI. The dashboard shell and navigation established here will be extended by every subsequent milestone.

#### Dependencies

M0 (database, ORM models, config), M1 (scrapers, raw_job_postings, scraper_runs tables).

#### Task List

- [ ] **App scaffold + DB settings model (D1)**:
  - [ ] Streamlit multi-page app structure under `jobhunter/dashboard/`
  - [ ] DB-backed settings model (`DS12 SettingsEntry`) with JSON fields for scraping, filtering, scheduling, notifications
  - [ ] Alembic migration: create `settings` table, seed defaults from Pydantic models
  - [ ] Hybrid config loading: `config.yaml` for ai_models/database/dashboard, SQLite for operational settings
- [ ] **Resume management page (D2)**:
  - [ ] Upload PDF resumes, extract text via existing M0 pipeline, persist to DS8
  - [ ] List stored resumes with metadata (filename, upload date, word count)
  - [ ] View extracted text and delete resumes
- [ ] **Scraper config page — DB-backed (D3)**:
  - [ ] Load scraping config from `settings` table into structured form
  - [ ] Per-scraper enable/disable toggles, URL/keyword/filter editing
  - [ ] Save changes to SQLite with Pydantic validation
- [ ] **Raw jobs browser (D4)**:
  - [ ] Paginated table of raw_job_postings with source filter, date range, search
  - [ ] Expandable row detail showing full description and raw HTML
  - [ ] Basic stats: total by source, recent counts
- [ ] **Scraper runs page (D5)**:
  - [ ] Table of scraper_runs with status badges (success/failed/timeout/running)
  - [ ] Expandable error details for failed runs
  - [ ] Duration and job count columns
- [ ] **Trigger scrape — async job (D6)**:
  - [ ] Background thread execution with status polling
  - [ ] Duplicate-run prevention per scraper (check for `status='running'`)
  - [ ] Stale-job detection for orphaned `running` records
- [ ] **Navigation shell (D7)**:
  - [ ] Sidebar navigation with page links
  - [ ] Placeholder pages for future milestones (Filters, Evaluations, Applications)
  - [ ] DB connection status indicator

#### Key Risks and Mitigations

| Risk | Impact | Mitigation |
| ---- | ------ | ---------- |
| Config editing introduces invalid YAML | Medium | Validate with Pydantic before saving; show validation errors in UI; keep backup of previous config. |
| Streamlit subprocess for scrape triggering is fragile | Medium | Use `subprocess.run` with timeout; capture stdout/stderr; show errors clearly. |
| Scraper runs table grows large | Low | Default to last 50 runs; add date filter and pagination. |

#### Acceptance Criteria

1. `streamlit run jobhunter/dashboard/app.py` launches without errors and shows sidebar navigation.
2. A PDF resume can be uploaded, its text viewed, and the resume deleted — all from the UI.
3. Scraper config edits made in the UI are persisted to the SQLite `settings` table and validated.
4. Raw jobs browser shows all scraped jobs with working source filter and search.
5. Scraper runs page shows run history with correct status and error details.
6. Triggering a scrape from the UI starts a background job; status is polled; duplicate runs are prevented.

---

### M2 -- Tier 1 Rule-Based Filtering

**Complexity: S (Small)**

#### Description

Implement a configurable, zero-API-cost rule engine that filters out obvious mismatches before any AI evaluation. Rules cover salary, location, title patterns, company lists, and keywords. Every filter decision is audited for transparency. The goal is to eliminate 60-70% of irrelevant jobs locally, dramatically reducing downstream AI costs.

#### Dependencies

M1 (scraped jobs in database).

#### Task List

- [ ] Design rule engine architecture:
  - [ ] `RuleEngine` class that loads rules from config and applies them in sequence
  - [ ] Each rule is a composable `FilterRule` with `evaluate(job) -> FilterResult(pass/fail/ambiguous, reason)`
  - [ ] Support for AND/OR composition of rules
  - [ ] Configurable rule ordering and short-circuit evaluation
- [ ] **Salary extraction and normalization**:
  - [ ] Parse salary strings: "$90K", "$90,000", "$90,000/yr", "$7,500/mo", "90k-120k", "USD 90,000 - 120,000"
  - [ ] Normalize to annual USD amount (or configured currency)
  - [ ] Handle missing salary (configurable: pass-through or flag as ambiguous)
  - [ ] Min/max salary thresholds from config
  - [ ] Unit tests with comprehensive salary format corpus
- [ ] **Location/remote policy detection**:
  - [ ] Parse location strings for remote indicators: "remote", "remote worldwide", "work from anywhere"
  - [ ] Detect geo-restrictions: "US only", "EU timezone", "Turkey allowed/not allowed"
  - [ ] Configurable allowed regions/countries list
  - [ ] Handle ambiguous location descriptions (pass to Tier 2)
  - [ ] Unit tests with real-world location string samples
- [ ] **Title matching**:
  - [ ] Positive title patterns list (e.g., "engineering manager", "staff engineer", "senior backend")
  - [ ] Negative title patterns list (e.g., "intern", "junior", "co-op", "associate")
  - [ ] Fuzzy matching support (handle variations like "Sr." vs "Senior", "Eng." vs "Engineer")
  - [ ] Configurable match threshold
- [ ] **Company blacklist/whitelist**:
  - [ ] Blacklist: companies to always reject (e.g., known bad employers, already applied)
  - [ ] Whitelist: companies to always pass through (e.g., dream companies)
  - [ ] Case-insensitive matching with normalization
- [ ] **Keyword inclusion/exclusion**:
  - [ ] Required keywords (job must contain at least one): e.g., "Python", "distributed systems"
  - [ ] Excluded keywords (job is rejected if found): e.g., "clearance required", "on-site only"
  - [ ] Search in both title and description
  - [ ] Configurable keyword weighting (optional)
- [ ] **Filter audit trail** (DS10):
  - [ ] For every job: record which rules fired, pass/fail/ambiguous result, reason string
  - [ ] Aggregate stats: total processed, passed, failed, ambiguous per run
  - [ ] Enable debugging "why was this job filtered out?" queries
- [ ] **Integration with pipeline**:
  - [ ] CLI flag: `python run.py --filter`
  - [ ] Process only unfiltered jobs (incremental)
  - [ ] Mark jobs with filter result status: `passed_tier1`, `failed_tier1`, `ambiguous_tier1`
- [ ] Write unit tests for each rule type with edge cases
- [ ] Write integration test: run full filter pipeline on sample job set

#### Key Risks and Mitigations

| Risk | Impact | Mitigation |
| ---- | ------ | ---------- |
| Salary parsing fails on unexpected formats | Medium | Build extensive test corpus from real data; log unparseable formats for iterative improvement; treat parse failures as ambiguous (not reject). |
| Over-aggressive filtering removes good matches | High | Default to "ambiguous" (pass to Tier 2) rather than "reject" when uncertain. Track false-negative rate in M7 polish phase. |
| Rule configuration becomes complex | Low | Provide well-documented config.yaml examples; validate rules on load. |

#### Acceptance Criteria

1. Running Tier 1 filtering on a batch of scraped jobs produces pass/fail/ambiguous decisions for every job.
2. Salary strings in at least 10 different formats are correctly parsed and normalized (verified by tests).
3. Filter audit log (DS10) records the specific rule(s) and reason for every decision.
4. Jobs matching the company whitelist always pass regardless of other rules.
5. Jobs matching the company blacklist always fail regardless of other rules.
6. Ambiguous jobs (rules cannot decide) are flagged for Tier 2 evaluation, not rejected.
7. At least 60% of a representative sample of irrelevant jobs are correctly filtered out.

---

### M3 -- AI Evaluation Pipeline

**Complexity: M (Medium)**

#### Description

Build the two-tier AI evaluation system that assesses ambiguous and promising jobs against the user's resume. Tier 2 uses cheap models (Claude Haiku / GPT-4o-mini) for quick triage of Tier 1 ambiguous results. Tier 3 uses strong models (Claude Sonnet / GPT-4o) for deep evaluation of promising candidates. All calls are tracked for cost, and the system enforces spending caps.

#### Dependencies

M2 (filtered jobs with tier 1 results, stored resumes).

#### Task List

- [ ] **Claude client wrapper** (anthropic SDK):
  - [ ] API key management (environment variable)
  - [ ] Message construction with system prompts, user prompts, structured output
  - [ ] Retry with exponential backoff on rate limits (429) and transient errors (500, 503)
  - [ ] Response parsing and validation
  - [ ] Token counting (input + output) per call
  - [ ] Unit tests with mocked API responses
- [ ] *(Post-MVP)* **OpenAI client wrapper** (openai SDK): same pattern as Claude wrapper, adds fallback provider
- [ ] *(Post-MVP)* **Model fallback logic**: Claude primary, OpenAI fallback on failure
- [ ] **Tier 2: Quick AI filter** (cheap models):
  - [ ] Prompt template: concise job summary + resume summary -> quick relevance score (1-10) + brief reason
  - [ ] Model: Claude Haiku or GPT-4o-mini (configurable)
  - [ ] Input: jobs marked `ambiguous_tier1` from M2
  - [ ] Output: `passed_tier2` (score >= threshold) or `failed_tier2`
  - [ ] Threshold configurable in config.yaml
  - [ ] Batch processing with configurable concurrency
- [ ] **Tier 3: Deep AI evaluation** (strong models):
  - [ ] Prompt template: full job description + full resume text -> detailed evaluation
  - [ ] Model: Claude Sonnet or GPT-4o (configurable)
  - [ ] Input: jobs marked `passed_tier1` + `passed_tier2`
  - [ ] Evaluation dimensions:
    - [ ] Skills match score (0-100)
    - [ ] Experience level match (0-100)
    - [ ] Culture/values alignment (0-100)
    - [ ] Overall match score (weighted composite)
    - [ ] Key strengths (bullet list)
    - [ ] Key gaps (bullet list)
    - [ ] Recommendation: strong_match / good_match / weak_match / no_match
  - [ ] Structured output parsing (JSON mode or structured extraction)
- [ ] **Resume recommendation**:
  - [ ] Compare job against both stored resumes
  - [ ] Recommend which resume is the better fit with brief justification
  - [ ] Store recommendation in DS4
- [ ] **Match evaluation storage** (DS4):
  - [ ] Store all scoring dimensions, raw AI response, model used, provider used
  - [ ] Link to job and resume records
  - [ ] Support multiple evaluations per job (re-evaluation)
- [ ] **Token tracking and cost estimation** (stored in DS4 per evaluation):
  - [ ] Record input tokens, output tokens, model name, estimated cost per call
  - [ ] Aggregate by day, by tier, by provider
  - [ ] Cost estimation using published pricing (configurable rates in config.yaml)
- [ ] **Cost caps**:
  - [ ] Daily spending limit (configurable)
  - [ ] Monthly spending limit (configurable)
  - [ ] Check cap before each API call; skip evaluation if cap reached
  - [ ] Log warning when approaching cap (80% threshold)
  - [ ] Hard stop when cap is reached; mark remaining jobs as `deferred_cost_cap`
- [ ] **Prompt templates**:
  - [ ] Store prompts as separate text files or in config for easy iteration
  - [ ] Variable substitution: {job_title}, {job_description}, {resume_text}, {company_name}
  - [ ] Version tracking for prompts (which prompt version produced which evaluation)
- [ ] CLI integration: `python run.py --evaluate`
- [ ] Write unit tests with mocked AI responses for both tiers
- [ ] Write integration test: full pipeline from filtered jobs through scoring

#### Key Risks and Mitigations

| Risk | Impact | Mitigation |
| ---- | ------ | ---------- |
| AI scoring is inconsistent across runs | High | Use low temperature (0.1-0.3), structured output format, and explicit scoring rubric in prompts. Log all responses for analysis. |
| API costs exceed expectations | High | Cost caps are mandatory. Start with conservative Tier 2 threshold to limit Tier 3 volume. Monitor daily. |
| Claude API outages | Medium | Retry with backoff. Deferred evaluation queue for retry on next run. *(Post-MVP: OpenAI fallback)* |
| Prompt engineering takes many iterations | Medium | Design prompts as external templates for rapid iteration without code changes. Track prompt versions. |
| Structured output parsing fails on unexpected AI responses | Medium | Validate AI response structure; fall back to regex extraction; log malformed responses for debugging. |

#### Acceptance Criteria

1. Tier 2 evaluation runs on ambiguous jobs and produces a numeric score and pass/fail decision for each.
2. Tier 3 evaluation runs on passed jobs and produces a multi-dimensional evaluation with overall recommendation.
3. Resume recommendation selects the better-fit resume with justification for each evaluated job.
4. All API calls are logged with token counts and estimated costs in DS4.
5. When daily cost cap is reached, the pipeline halts AI evaluation and logs the reason; no cap overruns.
6. Evaluation results are stored in DS4 and retrievable by job ID.

---

### M4 -- Content Generation

**Complexity: S (Small)**

#### Description

Generate personalized application materials for jobs that pass AI evaluation. This includes cover letters tailored to specific job requirements, "Why this company?" answers enriched with company research, and a versioning system that supports regeneration with different prompts or models. The output is the raw material the user needs to apply.

#### Dependencies

M3 (evaluated and scored jobs, resume recommendation, AI client wrappers).

#### Task List

- [ ] **Cover letter generator**:
  - [ ] Prompt template: job description + resume + evaluation highlights -> personalized cover letter
  - [ ] Map user's specific achievements to job requirements (use Tier 3 evaluation data)
  - [ ] Configurable tone (professional, conversational, technical)
  - [ ] Configurable length (short/medium/long)
  - [ ] Generate using recommended resume (from M3)
  - [ ] Store in DS5 with metadata: model used, prompt version, generation timestamp
- [ ] *(Post-MVP)* **Company research enrichment**: scrape company websites, extract mission/product/tech stack, store in DS2
- [ ] **"Why this company?" answer generator**:
  - [ ] Prompt template: company research + job description + resume -> personalized "why" answer
  - [ ] Reference specific company attributes (mission, product, culture)
  - [ ] Connect company attributes to user's experience and values
  - [ ] Store in DS6 with metadata
- [ ] *(Post-MVP)* **Content versioning**: multiple versions per job, regeneration support, version comparison
- [ ] **Application package assembly** (DS7):
  - [ ] Bundle: job link, recommended resume, best cover letter version, best "why" answer version
  - [ ] Mark package as ready for review
- [ ] CLI integration: `python run.py --generate`
- [ ] Write unit tests with mocked AI responses
- [ ] Write integration test: generate materials for a sample evaluated job

#### Key Risks and Mitigations

| Risk | Impact | Mitigation |
| ---- | ------ | ---------- |
| Generated cover letters are generic or low quality | Medium | Include specific evaluation data (strengths, gaps) in prompt context. Iterate on prompts in M7. |
| "Why this company?" answer is too generic without company research | Medium | Use job description details as context. *(Post-MVP: add company research enrichment)* |
| Generated content sounds AI-written | Medium | Prompt engineering: include user's writing style examples; instruct natural tone; plan for human editing. |
| Token costs for long cover letters | Low | Use strong model only; content gen is low volume (only shortlisted jobs). |

#### Acceptance Criteria

1. A personalized cover letter is generated for each job with `strong_match` or `good_match` recommendation.
2. Cover letter references specific job requirements and maps them to resume achievements.
3. "Why this company?" answer is generated using job description and resume context.
4. Generated content is stored in DS5 (cover letter) and DS6 (why-company) with model/cost metadata.
5. Application status (DS7) is updated to `ready_to_apply` for jobs with generated materials.

---

### M5 -- Dashboard Review Workflow

**Complexity: M (Medium)**

#### Description

Extend the M1.5 dashboard shell with the job review workflow: evaluated job listing with AI scores, detailed evaluation views, approve/reject/shortlist actions, "Ready to Apply" view with generated materials, and application status tracking. The app scaffold, DB connection, session state, resume pages, scraper config, and raw job browser already exist from M1.5.

#### Dependencies

M4 (evaluated jobs, generated content, application packages), M1.5 (existing dashboard shell and navigation).

#### Task List

- [ ] **Evaluated job listing view** (extends M1.5 raw jobs browser):
  - [ ] Paginated table of processed jobs with AI scores
  - [ ] Filters: match score range, source site, date range, status, salary range, recommendation level
  - [ ] Sortable columns: score, date posted, salary, company
  - [ ] Color coding by recommendation (strong=green, good=blue, weak=yellow, no_match=red)
  - [ ] Quick-action buttons: approve, reject, shortlist
  - [ ] Bulk actions: select multiple jobs and change status
- [ ] **Job detail view**:
  - [ ] Full job description (rendered HTML or clean text)
  - [ ] Tier 1 filter results with reasons
  - [ ] Tier 2 quick score (if applicable)
  - [ ] Tier 3 deep evaluation: all scoring dimensions, strengths, gaps, recommendation
  - [ ] Source URL link (open in browser)
  - [ ] Company research data (if available)
- [ ] **Side-by-side comparison view**:
  - [ ] Left panel: job requirements (extracted key points)
  - [ ] Right panel: resume highlights (matching experience/skills)
  - [ ] Visual match indicators
- [ ] **Approve/reject/shortlist workflow**:
  - [ ] Status buttons on job detail and job list views
  - [ ] Confirmation dialog for reject (prevent accidental rejection)
  - [ ] Batch status updates
  - [ ] Status filter presets: "Needs Review", "Shortlisted", "Ready to Apply"
- [ ] **"Ready to Apply" view**:
  - [ ] List of jobs with status `ready_to_apply`
  - [ ] For each job display: job link, recommended resume, cover letter, "why this company?" answer
  - [ ] Copy-to-clipboard buttons for generated text
  - [ ] Mark as "Applied" button with optional notes field
- [ ] **Application status tracking pipeline** (DS7):
  - [ ] State machine: `new` -> `reviewed` -> `shortlisted` -> `applying` -> `applied` -> `interviewing` -> `offer`/`rejected`/`withdrawn`
  - [ ] Status change history with timestamps
  - [ ] Dashboard view: Kanban-style or pipeline funnel visualization
  - [ ] Stats: conversion rates between stages
- [ ] *(Post-MVP)* **Cost dashboard**: token usage charts, tier/provider breakdown, budget tracking
- [ ] **General UI enhancements**:
  - [ ] Loading indicators for database queries
  - [ ] Error handling with user-friendly messages
- [ ] Write integration tests for review workflow data queries

#### Key Risks and Mitigations

| Risk | Impact | Mitigation |
| ---- | ------ | ---------- |
| Streamlit performance with large datasets | Medium | Paginate all list views; use database-level filtering (not Python-side); cache expensive queries. |
| Scope creep from UX feature requests | Medium | Stick to defined task list for M5; defer enhancements to M7. |
| Streamlit limitations for complex layouts | Low | Use st.columns, st.tabs, st.expander for layout; accept Streamlit conventions rather than fighting them. |

#### Acceptance Criteria

1. Evaluated job listing view displays all processed jobs with working filters (score, source, date, status, salary).
2. Job detail view shows full evaluation data including all scoring dimensions.
3. Clicking "Approve" or "Reject" updates job status in the database and reflects immediately in the UI.
4. "Ready to Apply" view shows complete application package (link, resume, cover letter, "why" answer).
5. Application status can be updated (shortlist, apply, reject) from the dashboard.
6. Navigation integrates seamlessly with existing M1.5 pages.

---

### M6 -- Automation & Scheduling

**Complexity: S (Small)**

#### Description

Wire the full pipeline into an automated workflow that runs on a schedule via Windows Task Scheduler. The pipeline executes the complete sequence -- scrape, filter, deduplicate, evaluate, generate -- processing only new or updated jobs incrementally. Error recovery and retry logic ensure the system runs reliably without daily supervision.

#### Dependencies

M5 (complete pipeline and dashboard).

#### Task List

- [ ] **Full pipeline orchestrator**:
  - [ ] Single entry point: `python run.py --all` runs the complete pipeline in order
  - [ ] Pipeline stages: scrape -> deduplicate -> tier1 filter -> tier2 evaluate -> tier3 evaluate -> generate -> report
  - [ ] Stage-level error handling: failure in one stage logs error and continues to next where possible
  - [ ] Pipeline lock file to prevent concurrent runs
  - [ ] Pipeline run record: start time, end time, jobs processed per stage, errors, cost
- [ ] **Incremental processing**:
  - [ ] Track last-processed timestamp per stage
  - [ ] Only scrape jobs newer than last successful scrape
  - [ ] Only filter jobs not yet filtered
  - [ ] Only evaluate jobs not yet evaluated
  - [ ] Only generate materials for newly-qualified jobs
  - [ ] Force-reprocess flag: `--force` to reprocess all jobs
- [ ] **Windows Task Scheduler integration**:
  - [ ] PowerShell/batch script to invoke `python run.py --all` with correct venv activation
  - [ ] Setup script that creates the scheduled task (configurable time, e.g., daily at 7 AM)
  - [ ] Removal script to unregister the scheduled task
  - [ ] Documentation for manual Task Scheduler configuration
- [ ] **Error recovery and retry logic**:
  - [ ] Retry failed scraper runs (configurable max retries)
  - [ ] Retry failed AI evaluations (transient API errors)
  - [ ] Dead-letter queue: jobs that fail N times are flagged for manual review
  - [ ] Pipeline resumes from last successful stage on restart
- [ ] *(Post-MVP)* **Daily summary report**: generate after pipeline run, save to file
- [ ] *(Post-MVP)* **Desktop notification**: Windows toast for high-scoring matches
- [ ] Write integration test: run full pipeline end-to-end in test mode

#### Key Risks and Mitigations

| Risk | Impact | Mitigation |
| ---- | ------ | ---------- |
| Scheduled task fails silently | High | Log all pipeline output to file; summary report flags errors; consider email notification for failures. |
| Concurrent pipeline runs corrupt data | Medium | Lock file mechanism prevents concurrent execution. |
| Windows Task Scheduler permission issues | Low | Document required permissions; provide troubleshooting guide. |
| Pipeline takes too long and overlaps next scheduled run | Medium | Lock file prevents overlap; log warning if run duration exceeds threshold. |

#### Acceptance Criteria

1. `python run.py --all` executes the complete pipeline: scrape through generate.
2. Running the pipeline twice processes only new/unprocessed jobs on the second run.
3. The Windows Task Scheduler setup script creates a working scheduled task.
4. A pipeline run failure in the scraping stage does not prevent filtering of previously-scraped jobs.
5. Daily summary report is generated with accurate counts and cost data.
6. Lock file prevents a second pipeline instance from starting while one is running.
7. Desktop notification fires when a high-scoring job is found (if enabled).

---

### M7 -- Polish & Optimization

**Complexity: M (Medium)**

#### Description

Refine the system based on real-world usage. Optimize database query performance for growing job databases, tune AI prompts using actual evaluation feedback, improve the dashboard UX, and add data export capabilities. This milestone also delivers documentation and the final setup guide, making the tool ready for long-term personal use.

#### Dependencies

M6 (complete automated system running for at least 1-2 weeks).

#### Task List

- [ ] **Performance optimization**:
  - [ ] Add database indexes on frequently-queried columns (score, status, date, source)
  - [ ] Optimize dashboard list queries (pagination, selective column loading)
  - [ ] Profile and fix slow dashboard pages
  - [ ] Database vacuum and maintenance script
  - [ ] Archive old/rejected jobs to reduce active dataset size
- [ ] **Prompt tuning**:
  - [ ] Review Tier 2 and Tier 3 evaluation accuracy against manual review decisions
  - [ ] Identify false positives and false negatives
  - [ ] Iterate on prompt templates to improve precision
  - [ ] A/B test prompt variants (track prompt version in DS4)
  - [ ] Tune scoring thresholds based on observed distribution
- [ ] **Dashboard UX improvements**:
  - [ ] Address usability issues discovered during usage
  - [ ] Add keyboard shortcuts for common actions
  - [ ] Improve mobile/narrow-screen layout (if applicable)
  - [ ] Add "quick reject" reasons (dropdown: wrong level, wrong domain, bad location, etc.)
  - [ ] Saved filter presets
- [ ] **Cost optimization**:
  - [ ] Analyze token usage patterns; identify wasted tokens (overly long prompts, unnecessary context)
  - [ ] Optimize prompt length without sacrificing quality
  - [ ] Adjust Tier 1 rules to catch more obvious rejects (reduce Tier 2 volume)
  - [ ] Consider caching AI evaluations for similar job descriptions
- [ ] **Documentation and setup guide**:
  - [ ] Installation guide (Python, Playwright browsers, API keys, config)
  - [ ] Configuration reference (all config.yaml fields documented)
  - [ ] Architecture overview
  - [ ] Troubleshooting guide (common errors and fixes)
- [ ] **Data export**:
  - [ ] Export matched jobs to CSV (configurable columns)
  - [ ] Export matched jobs to Excel with formatting
  - [ ] Export application status pipeline as CSV
  - [ ] Export from dashboard UI (download button)
- [ ] **General cleanup**:
  - [ ] Remove dead code and unused dependencies
  - [ ] Ensure all log messages are clear and actionable
  - [ ] Final pass on error messages and user-facing text
  - [ ] Ensure all tests pass and coverage is adequate

#### Key Risks and Mitigations

| Risk | Impact | Mitigation |
| ---- | ------ | ---------- |
| Prompt tuning is unbounded | Low | Time-box to 2-3 iterations; accept "good enough" and iterate post-R1. |
| Scope creep from accumulated feature requests | Medium | Strictly prioritize: performance and accuracy fixes first, UX polish second, new features deferred to R2. |
| Documentation becomes outdated | Low | Generate config reference from code/schema where possible. |

#### Acceptance Criteria

1. Dashboard loads job list in under 2 seconds with 5,000+ jobs in the database.
2. At least one round of prompt tuning is completed with before/after accuracy comparison.
3. Data export produces valid CSV and Excel files downloadable from the dashboard.
4. Setup guide enables a fresh install from zero to working pipeline (tested on a clean environment).
5. All tests pass. No known critical bugs.
6. Daily pipeline run completes within a reasonable time window (configurable target, e.g., under 30 minutes).

---

## Appendix: Data Structures Reference

| ID   | Name                 | Purpose                                         |
| ---- | -------------------- | ----------------------------------------------- |
| DS1  | RawJobPosting        | Raw scraped data before processing (source, URL, title, company, salary_raw, description) |
| DS2  | Company              | Company metadata and research data              |
| DS3  | ProcessedJob         | Normalized job data after Tier 1 filtering (canonical job record) |
| DS4  | MatchEvaluation      | AI scoring results (all dimensions, recommendation) |
| DS5  | CoverLetter          | Generated cover letters with version tracking   |
| DS6  | WhyCompany           | Generated "why this company" answers            |
| DS7  | ApplicationStatus    | Status tracking state machine with history      |
| DS8  | ResumeProfile        | Resume metadata, extracted text, key skills      |
| DS9  | ScraperRun           | Per-run scraper audit records                   |
| DS10 | FilterResult         | Filter decision trail with reasons              |
| DS11 | JobFingerprint       | Deduplication tracking (hash, source URLs, times seen) |
