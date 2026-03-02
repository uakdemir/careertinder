# Architectural Decision Records (ADRs) — JobHunter

This document captures the key architectural decisions made for the **JobHunter** platform — a local job search automation system that scrapes postings from four job sites, applies a three-tier filtering pipeline, evaluates matches against two resumes, generates application materials, and surfaces everything through a dashboard.

**Profile context:** Senior technology professional targeting remote positions from Turkey, minimum $90K compensation, maintaining two resumes (Leadership track and Architect/Developer track). The system runs locally on Windows.

---

## Summary

| ADR# | Title | Status | Date |
|------|-------|--------|------|
| ADR-001 | Python as Primary Language | Accepted | 2026-03-02 |
| ADR-002 | SQLite as Database | Accepted | 2026-03-02 |
| ADR-003 | Playwright for Web Scraping | Accepted | 2026-03-02 |
| ADR-004 | Apify for LinkedIn and Wellfound Scraping | Accepted | 2026-03-02 |
| ADR-005 | 3-Tier Filtering Architecture | Accepted | 2026-03-02 |
| ADR-006 | Dual AI Provider Strategy (Claude + OpenAI) | Accepted | 2026-03-02 |
| ADR-007 | Streamlit for Dashboard | Accepted | 2026-03-02 |
| ADR-008 | Job Fingerprinting for Deduplication | Accepted | 2026-03-02 |
| ADR-009 | config.yaml for Configuration | Accepted | 2026-03-02 |
| ADR-010 | SQLAlchemy ORM | Accepted | 2026-03-02 |
| ADR-011 | Content Versioning Strategy | Accepted | 2026-03-02 |
| ADR-012 | Windows Task Scheduler for Automation | Accepted | 2026-03-02 |
| ADR-013 | Resilient Scraper Design | Accepted | 2026-03-02 |
| ADR-014 | Token Cost Tracking | Accepted | 2026-03-02 |
| ADR-015 | Resume Text Extraction Strategy | Accepted | 2026-03-02 |
| ADR-016 | Logging Strategy | Accepted | 2026-03-02 |

---

## ADR-001: Python as Primary Language

**Status:** Accepted

### Context

JobHunter requires capabilities across several domains: web scraping with browser automation, AI/LLM integration via multiple provider SDKs, data processing and persistence, and a local dashboard UI. We need a language that has mature library support in all of these areas and allows rapid development for a single-developer project.

### Decision

Use **Python 3.12+** as the sole implementation language for all components of the platform.

Python provides the richest ecosystem for every pillar of this project:

- **Scraping:** Playwright (browser automation), BeautifulSoup (HTML parsing), httpx/requests (HTTP clients).
- **AI integration:** First-party SDKs from Anthropic (`anthropic`) and OpenAI (`openai`) with full feature parity.
- **Rapid prototyping:** Dynamic typing and concise syntax enable fast iteration on filtering logic and prompt engineering.
- **Dashboard:** Streamlit is Python-native, eliminating the need for a separate frontend stack.

### Consequences

- **Positive:** Single language across the entire stack reduces context-switching and simplifies dependency management. Vast ecosystem means most problems have well-tested library solutions. Type hints via `mypy` or `pyright` can be adopted incrementally for critical paths.
- **Negative:** Python is slower than compiled languages (Go, Rust, C#). This is irrelevant for our use case — the bottlenecks are network I/O (scraping) and API latency (AI calls), not CPU computation.
- **Risks:** None significant. Python is the dominant language for exactly this class of application.

---

## ADR-002: SQLite as Database

**Status:** Accepted

### Context

The platform needs persistent storage for job postings, evaluation results, generated materials, cost tracking, and run metadata. The system is a single-user local application running on one Windows machine.

### Decision

Use **SQLite** as the sole database engine.

SQLite provides zero-setup, single-file storage that is perfectly matched to the deployment model. There is no need for a separate database server process, network configuration, or authentication setup.

### Consequences

- **Positive:** Zero operational overhead — no database server to install, configure, or maintain. The entire database is a single portable file that can be backed up by copying. Excellent read performance for dashboard queries. Native Python support via the `sqlite3` standard library module. Full SQL support for complex queries.
- **Positive:** Schema migrations are handled via Alembic (see ADR-010), providing a controlled upgrade path.
- **Negative:** No concurrent write access — not an issue for a single-user system. Limited to a single machine — acceptable for the current scope.
- **Migration path:** If the project ever grows to multi-user or cloud deployment, the SQLAlchemy abstraction layer (ADR-010) allows migration to PostgreSQL with minimal code changes.

---

## ADR-003: Playwright for Web Scraping

**Status:** Accepted

### Context

JobHunter scrapes job postings from four sites: Remote.io, RemoteRocketship, Wellfound, and LinkedIn. Two of these (Remote.io, RemoteRocketship) rely on JavaScript rendering and dynamic content loading. The other two (LinkedIn, Wellfound) are accessed via Apify REST API (see ADR-004). For the Playwright-based scrapers, a simple HTTP client with HTML parsing (requests + BeautifulSoup) cannot reliably access the full page content.

### Decision

Use **Playwright** (via `playwright` Python package) as the web scraping engine for sites that require browser-level rendering (Remote.io, RemoteRocketship).

### Consequences

- **Positive:** Handles JavaScript-heavy pages where content is rendered client-side. Headless mode enables unattended automated runs via Task Scheduler (ADR-012). Built-in wait mechanisms handle dynamically loaded content gracefully.
- **Positive:** Playwright supports Chromium, Firefox, and WebKit — providing fallback options if a site blocks one browser fingerprint.
- **Negative:** Heavier dependency than `requests` + BeautifulSoup (requires browser binary downloads). Slower per-page than raw HTTP requests. Higher memory usage.
- **Mitigation:** Use `requests` + BeautifulSoup as a lightweight fallback for sites that serve static HTML, keeping Playwright for sites that genuinely require it.

---

## ADR-004: Apify for LinkedIn and Wellfound Scraping

**Status:** Accepted

### Context

LinkedIn is a critical job source but aggressively enforces anti-scraping measures. Direct scraping of LinkedIn — even with Playwright and careful rate limiting — carries a high risk of permanent account bans. A banned LinkedIn account would be a significant professional loss.

Wellfound (formerly AngelList Talent) is similarly challenging: the site is heavily JavaScript-rendered, requires authentication, and may enforce 2FA or CAPTCHA. Building and maintaining an authenticated Playwright scraper for Wellfound was identified as the #1 development risk (see `risky_components.md`).

Both sites have well-maintained Apify actors that provide the same data via a simple REST API, eliminating all browser automation complexity.

### Decision

Use **Apify actors** to collect job postings from both LinkedIn and Wellfound, accessed via Apify's REST API:

- **LinkedIn:** `apify/linkedin-jobs-scraper` (official Apify actor)
- **Wellfound:** `shahidirfan/wellfound-jobs-scraper` (community actor with good reviews and reasonable pricing)

### Consequences

- **Positive:** Eliminates all risk of personal LinkedIn account bans. Eliminates the entire Wellfound authentication flow (login, 2FA, session management, CAPTCHA detection) which was the highest-risk component. Apify handles proxy rotation, browser fingerprinting, and rate limiting through their infrastructure.
- **Positive:** Both integrations follow the same REST API pattern — a single HTTP call triggers a scrape run, and results are retrieved as JSON. This means C2c (Wellfound) and C2d (LinkedIn) share a common `ApifyBaseScraper` base class, reducing code duplication.
- **Positive:** Cost is manageable. For typical usage (a few hundred jobs per week across both sources), this falls well within Apify's free tier or low-cost paid tier.
- **Negative:** Introduces an external service dependency and associated cost for two sources instead of one. Apify actor availability and data format may change without notice. Community actors (Wellfound) have higher change risk than official actors (LinkedIn).
- **Mitigation:** Abstract the Apify integration behind the same scraper interface as other sources, so it can be replaced if needed. Cache results aggressively to avoid redundant API calls. Pin actor versions where possible.

---

## ADR-005: 3-Tier Filtering Architecture

**Status:** Accepted

### Context

The platform processes hundreds of job postings per run across four sources. Evaluating every posting with a powerful (and expensive) AI model would be wasteful — many postings are obviously irrelevant (wrong location policy, wrong seniority, wrong domain). We need a cost-effective filtering strategy that preserves evaluation quality for promising matches.

### Decision

Implement a **three-tier filtering pipeline** where each tier progressively increases in sophistication and cost:

| Tier | Method | Cost per Job | Purpose |
|------|--------|-------------|---------|
| **Tier 1** | Rule-based filters | Free | Eliminate obvious mismatches on salary, location, seniority, keywords |
| **Tier 2** | Cheap AI (Claude Haiku / GPT-4o-mini) | ~$0.001 | Evaluate ambiguous cases that pass rule-based filters |
| **Tier 3** | Deep AI (Claude Sonnet / GPT-4o) | ~$0.01–0.03 | Full evaluation with resume matching for promising candidates |

### Consequences

- **Positive:** Tier 1 eliminates an estimated **60–70%** of postings at zero cost. Tier 2 handles the ambiguous middle ground at negligible cost. Only the most promising 10–20% of original postings reach Tier 3. Expected total AI cost reduction: **80%+** compared to evaluating every posting at Tier 3.
- **Positive:** Each tier produces a structured verdict (PASS / FAIL / UNCERTAIN) with reasoning, enabling transparency in the dashboard about why a job was filtered or promoted.
- **Negative:** Adds pipeline complexity. Tier 1 rules must be carefully tuned to avoid false negatives (filtering out good jobs). Tier boundary thresholds require calibration.
- **Mitigation:** All tier decisions are logged and reviewable. A "show filtered jobs" mode in the dashboard allows manual inspection of Tier 1 and Tier 2 rejections to catch systematic errors.

---

## ADR-006: Dual AI Provider Strategy (Claude + OpenAI)

**Status:** Accepted

### Context

The platform depends heavily on LLM capabilities for job evaluation (Tiers 2 and 3), resume matching, cover letter generation, and "why this company" narrative generation. Relying on a single AI provider creates a single point of failure.

### Decision

Integrate **both Claude (Anthropic) and OpenAI (GPT)** as AI providers. Claude is the primary provider; OpenAI serves as the fallback.

- **Claude** (primary): Used for nuanced analysis — resume-to-job matching, cover letter generation, and contextual evaluation where understanding of subtle career narratives matters.
- **OpenAI** (fallback): Used for structured data extraction (parsing job postings into normalized fields) and as a redundancy layer when Claude's API is unavailable.
- **Cross-validation:** For borderline Tier 2/3 cases, both providers can evaluate the same job independently to increase confidence in the verdict.

### Consequences

- **Positive:** Redundancy ensures the pipeline does not stall if one provider has an outage. Cross-validation reduces false negatives on borderline matches. Each provider's strengths are leveraged where they matter most.
- **Negative:** Two sets of API keys, two SDK dependencies, two billing relationships. Prompt engineering must be maintained for two model families. Response format normalization adds code complexity.
- **Mitigation:** Abstract both providers behind a common `AIProvider` interface. Prompts are stored as templates with provider-specific formatting handled at the adapter layer.

---

## ADR-007: Streamlit for Dashboard

**Status:** Accepted

### Context

The platform needs a local user interface for reviewing evaluated jobs, comparing resume matches, viewing and regenerating cover letters, monitoring costs, and managing scraper runs. The development team is one person, and the UI is for single-user local use only.

### Decision

Use **Streamlit** as the dashboard framework.

### Consequences

- **Positive:** Fastest path from zero to a functional, interactive dashboard. Python-native — no need for a separate JavaScript frontend, REST API layer, or build toolchain. Rich built-in widgets for tables, filters, sorting, charts, and text display. Hot-reload during development.
- **Positive:** Streamlit's data-centric design aligns naturally with the use case: displaying tables of jobs, filtering by score/status, and showing detailed evaluation views.
- **Negative:** Limited customization compared to a React or Vue frontend. Non-standard layout model that can feel restrictive for complex UIs. Session state management can become awkward for multi-page workflows.
- **Tradeoff accepted:** The customization limitations are acceptable for a single-user tool. If the UI requirements grow significantly, Streamlit can be replaced with a proper frontend while keeping the Python backend and database unchanged.

---

## ADR-008: Job Fingerprinting for Deduplication

**Status:** Accepted

### Context

The same job posting frequently appears on multiple sites (e.g., a company posts on both LinkedIn and Wellfound). Across successive scraping runs, the same jobs will be encountered repeatedly. Without deduplication, the pipeline would waste AI tokens re-evaluating identical jobs and clutter the dashboard with duplicates.

### Decision

Generate a **fingerprint hash** for each job posting using the formula:

```
fingerprint = SHA256(normalize(company_name) + "|" + normalize(job_title))
```

Normalization rules:
- Convert to lowercase
- Strip leading/trailing whitespace
- Remove special characters (commas, periods, dashes, etc.)
- Collapse multiple spaces into one

The fingerprint is checked against the database before any processing. If a fingerprint already exists, the new source URL is appended to `DS11.source_urls` and `times_seen` is incremented — no duplicate job record is created.

### Consequences

- **Positive:** Prevents re-processing of jobs across runs, saving API costs and pipeline time. Handles cross-site duplicates natively — the same job posted on LinkedIn and Wellfound produces the same fingerprint because the formula uses only company name and job title, not the source URL.
- **Positive:** Fingerprint-based lookup is O(1) via database index on the fingerprint column.
- **Positive:** `DS11.source_urls` tracks all sources where a job was seen, enabling the dashboard to show "Found on: LinkedIn, Wellfound" for cross-posted jobs.
- **Negative:** Two genuinely different jobs at the same company with the same title will collide. This is rare and acceptable — a missed duplicate is cheaper than a false dedup.

---

## ADR-009: config.yaml for Configuration

**Status:** Accepted

### Context

The platform has numerous configurable parameters: API keys, filter rules (salary thresholds, required keywords, excluded terms), scraper schedules, model preferences, cost caps, logging levels, and file paths. These need to be easy to read, modify, and version-control.

### Decision

Use a single **`config.yaml`** file as the central configuration source for all platform settings.

Design principles:
- All non-secret parameters are stored directly in the YAML file.
- Sensitive values (API keys, credentials) are referenced via environment variable names: `api_key: ${ANTHROPIC_API_KEY}`. The configuration loader resolves these at runtime.
- The file is structured into logical sections: `scraping`, `filtering`, `ai`, `dashboard`, `logging`, `paths`.

### Consequences

- **Positive:** Human-readable and easy to edit with any text editor. YAML supports nested structures, comments, and lists naturally. Single source of truth for all configuration. Can be version-controlled (with secrets excluded via env var references).
- **Negative:** YAML has well-known pitfalls (implicit type coercion, indentation sensitivity). No schema validation out of the box.
- **Mitigation:** Use `pydantic` for configuration schema validation at load time. Invalid configuration fails fast with clear error messages. A `config.example.yaml` template is provided with documentation comments.

---

## ADR-010: SQLAlchemy ORM

**Status:** Accepted

### Context

The platform needs a data access layer for SQLite that supports: declarative model definitions, type-safe queries, schema migrations, and complex query construction for dashboard views (joins, aggregations, filtering).

### Decision

Use **SQLAlchemy 2.0+** as the ORM layer, paired with **Alembic** for schema migrations.

### Consequences

- **Positive:** Declarative model definitions serve as living documentation of the database schema. The query builder enables complex dashboard queries (e.g., "show all jobs scoring above 7, grouped by company, with cost statistics") without raw SQL string manipulation. Alembic provides versioned, reversible schema migrations.
- **Positive:** SQLAlchemy's dialect system means switching from SQLite to PostgreSQL (if ever needed) requires only a connection string change — no query rewrites.
- **Negative:** ORM overhead and learning curve. SQLAlchemy 2.0's new query style differs significantly from 1.x documentation that dominates search results.
- **Alternative considered:** Raw SQL with `sqlite3` — rejected due to poor maintainability as the schema grows and the risk of SQL injection in dynamically constructed dashboard queries.

---

## ADR-011: Content Versioning Strategy

**Status:** Accepted

### Context

The platform generates application materials — cover letters and "why this company" narratives — using AI. The quality of generated content varies based on the prompt, model, and job context. Users need the ability to iterate: regenerate with a different prompt, try a different model, or tweak the tone, then compare results and select the best version.

### Decision

Implement **content versioning** for all AI-generated application materials:

- Each generation produces a new version record linked to the job posting.
- Version records store: the generated text, the model used, the prompt template name, input/output token counts, estimated cost, and a timestamp.
- Users can view all versions side-by-side, mark a preferred version, or trigger regeneration with modified parameters.

### Consequences

- **Positive:** No generated content is ever lost. Users can freely experiment with different models and prompts without fear of overwriting a good result. Version history provides data on which model/prompt combinations produce the best outputs over time.
- **Positive:** Token and cost tracking per version (ties into ADR-014) gives visibility into the cost of regeneration.
- **Negative:** Storage grows with each regeneration. For a local SQLite database with text content, this is negligible (a few KB per version).
- **Implementation:** A `generated_content` table with columns: `id`, `job_id`, `content_type` (cover_letter | why_company), `version`, `text`, `model`, `prompt_template`, `input_tokens`, `output_tokens`, `cost_estimate`, `is_preferred`, `created_at`.

---

## ADR-012: Windows Task Scheduler for Automation

**Status:** Accepted

### Context

The scraping pipeline should run on a regular schedule (e.g., daily or twice daily) without requiring the user to manually trigger each run. The platform runs on a local Windows machine.

### Decision

Use **Windows Task Scheduler** to automate pipeline execution.

A scheduled task invokes a Python entry-point script (`run_pipeline.py`) at configured intervals. The script handles its own lifecycle: initialize logging, run scrapers, execute the filtering pipeline, and exit.

### Consequences

- **Positive:** Native to Windows — no additional dependencies to install. Runs independently of any active user session (can execute even when the user is not logged in, if configured). Reliable and well-understood scheduling mechanism.
- **Positive:** The pipeline script is also callable from the command line for manual/ad-hoc runs, preserving flexibility.
- **Negative:** Task Scheduler's UI is clunky and configuration is not version-controllable (though the task can be exported as XML).
- **Alternative rejected:** Python `schedule` library — requires a perpetually running Python process, which is fragile on a desktop machine (process gets killed on reboot, sleep, or crash). Task Scheduler is a fire-and-forget model that is strictly more reliable.
- **Fallback:** Manual runs via CLI remain fully supported for testing and on-demand use.

---

## ADR-013: Resilient Scraper Design

**Status:** Accepted

### Context

Web scraping is inherently fragile. Sites change their HTML structure, implement new anti-bot measures, experience downtime, or throttle requests. With four independent scraper targets, failures are not a question of "if" but "when."

### Decision

Design each scraper as an **independent, fault-isolated unit** with the following resilience patterns:

- **Independence:** Each scraper runs in its own execution context. One scraper's failure does not prevent others from completing.
- **Circuit breaker:** If a scraper fails N consecutive times (configurable, default: 3), it is automatically disabled for a cooldown period (configurable, default: 24 hours). This prevents wasting resources on a persistently broken scraper.
- **Retry with backoff:** Transient failures (network timeouts, HTTP 429/503) trigger automatic retries with exponential backoff (max 3 retries).
- **Detailed logging:** Each scraper run logs: start/end time, number of jobs found, number of new jobs (post-dedup), errors encountered, and final status. Logs are per-scraper for easy debugging.

### Consequences

- **Positive:** The pipeline degrades gracefully. If Wellfound changes its DOM structure, the other three scrapers continue operating normally. The circuit breaker prevents log spam and wasted compute on broken scrapers.
- **Positive:** Per-run logging enables rapid diagnosis when a scraper starts failing — the logs show exactly when it broke and what error occurred.
- **Negative:** Adds complexity to the scraper orchestration layer. Circuit breaker state must be persisted across runs (stored in the database).
- **Monitoring:** The dashboard displays scraper health status: last successful run, consecutive failures, circuit breaker state.

---

## ADR-014: Token Cost Tracking

**Status:** Accepted

### Context

AI API calls are the primary variable cost of operating the platform. Without tracking, costs can accumulate unnoticed — especially during development and prompt iteration. Budget control is essential for a self-funded personal project.

### Decision

Implement **comprehensive token cost tracking** for every AI API call:

- **Per-call logging:** Every API call records: model name, input tokens, output tokens, estimated cost (based on published pricing), timestamp, and the pipeline stage that triggered it.
- **Dashboard visibility:** A dedicated cost section in the dashboard shows: cumulative cost (daily, weekly, monthly), cost breakdown by model, cost breakdown by pipeline stage (Tier 2 vs. Tier 3 vs. generation).
- **Cost caps:** Configurable daily and monthly cost limits. When a cap is reached, the AI evaluation pipeline pauses and logs a warning. Scraping continues (it is free), but no new AI evaluations are triggered until the cap resets or is raised.

### Consequences

- **Positive:** Full visibility into where money is being spent. Cost caps prevent runaway spending during development or if a bug causes excessive API calls. Historical cost data informs optimization decisions (e.g., "Tier 2 is catching 90% of cases — can we tighten Tier 1 rules to reduce Tier 2 volume?").
- **Negative:** Cost estimates are approximations based on published pricing, which may lag behind actual billing. Token counts from streaming responses may differ slightly from billed amounts.
- **Mitigation:** Periodically reconcile tracked costs against actual API provider invoices. Use a conservative cost multiplier (e.g., 1.1x) for cap calculations.

---

## ADR-015: Resume Text Extraction Strategy

**Status:** Accepted

### Context

The two resumes (Leadership and Architect/Developer) are maintained as PDF files. AI evaluation at Tiers 2 and 3 requires the resume text as context in prompts. Extracting text from PDFs on every API call would be wasteful and slow.

### Decision

Extract resume text **once at setup time** (and on change) using **PyPDF2** or **pdfplumber**, then store the extracted text in the database for fast retrieval.

Process:
1. On first run or when a resume file is added/updated, compute the file's SHA-256 hash.
2. Compare the hash against the stored hash in the database.
3. If the hash differs (or no stored version exists), extract the full text from the PDF and store both the hash and extracted text.
4. All AI calls reference the stored text, never the PDF file directly.

### Consequences

- **Positive:** Resume text is available instantly for every AI call without file I/O or PDF parsing overhead. The hash-based change detection ensures the stored text is always current without unnecessary re-extraction.
- **Positive:** Storing extracted text in the database makes it available to the dashboard for display and to the configuration UI for verification ("does the extracted text look correct?").
- **Negative:** PDF text extraction is imperfect — formatting, tables, and columns may not extract cleanly. Complex resume layouts may produce garbled text.
- **Mitigation:** The dashboard includes a "review extracted text" view where the user can verify and manually correct the extracted text if needed. The corrected text is stored as an override.

---

## ADR-016: Logging Strategy

**Status:** Accepted

### Context

The platform runs unattended (via Task Scheduler) and includes multiple independent components (scrapers, filtering pipeline, AI calls, database operations). When something goes wrong, detailed logs are essential for diagnosis. When running interactively, real-time console output aids development and debugging.

### Decision

Implement structured logging using Python's built-in **`logging`** module with the following configuration:

- **Rotating file handler:** Daily log files stored in a `logs/` directory. Files are named `jobhunter_YYYY-MM-DD.log`. Retention: 30 days (configurable).
- **Separate loggers per component:** `jobhunter.scraper.linkedin`, `jobhunter.scraper.wellfound`, `jobhunter.filter.tier1`, `jobhunter.ai.claude`, etc. Each component's logs can be filtered independently.
- **File format:** Human-readable plain text (`%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`). JSON format is available as an optional configuration for machine parsing.
- **Console handler:** When running interactively (TTY detected), logs are also printed to the console in the same human-readable format.
- **Log levels:** `DEBUG` during development and testing. `INFO` for production (scheduled) runs. Configurable per component in `config.yaml`.

### Consequences

- **Positive:** Daily rotation keeps log files manageable and provides natural time-based partitioning for debugging ("what happened on Tuesday's run?"). Structured JSON format enables searching and filtering with standard tools (`jq`, Python scripts). Per-component loggers allow focused debugging without noise from other components.
- **Positive:** Console output during interactive runs provides immediate feedback during development without requiring log file inspection.
- **Negative:** JSON log format is less human-readable than plain text in log files. Logging configuration adds boilerplate to each component.
- **Mitigation:** The console handler uses a human-friendly format (not JSON). A simple log viewer utility or dashboard page can render JSON logs in a readable table format.
