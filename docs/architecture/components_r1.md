# JobHunter -- Architecture Components Document (R1)

| Field          | Value                                      |
| -------------- | ------------------------------------------ |
| Code Name      | **JobHunter**                              |
| Revision       | R1                                         |
| Date           | 2026-03-02                                 |
| Status         | Draft                                      |
| Stack          | Python 3.12+, Playwright, Apify, SQLite, Anthropic Claude SDK, OpenAI SDK, Streamlit |
| Target OS      | Windows 11 (Windows Task Scheduler)        |

---

## Table of Contents

1. [Overview](#1-overview)
2. [Component Interaction Diagram](#2-component-interaction-diagram)
3. [Components](#3-components)
   - [C0 -- Configuration Manager](#c0--configuration-manager)
   - [C1 -- Scraper Orchestrator](#c1--scraper-orchestrator)
   - [C2 -- Site Scrapers](#c2--site-scrapers)
   - [C3 -- Tier 1 Rule-Based Filter](#c3--tier-1-rule-based-filter)
   - [C4 -- Tier 2 Quick AI Filter](#c4--tier-2-quick-ai-filter)
   - [C5 -- Tier 3 Deep AI Evaluator](#c5--tier-3-deep-ai-evaluator)
   - [C6 -- Content Generator](#c6--content-generator)
   - [C7 -- Resume Manager](#c7--resume-manager)
   - [C8 -- Database Layer](#c8--database-layer)
   - [C9 -- Dashboard (Streamlit)](#c9--dashboard-streamlit)
   - [C10 -- Scheduler](#c10--scheduler)
   - [C11 -- Notification Service](#c11--notification-service-optionalfuture)
4. [Data Structures](#4-data-structures)
   - [DS1 -- RawJobPosting](#ds1--rawjobposting)
   - [DS2 -- Company](#ds2--company)
   - [DS3 -- ProcessedJob](#ds3--processedjob)
   - [DS4 -- MatchEvaluation](#ds4--matchevaluation)
   - [DS5 -- CoverLetter](#ds5--coverletter)
   - [DS6 -- WhyCompany](#ds6--whycompany)
   - [DS7 -- ApplicationStatus](#ds7--applicationstatus)
   - [DS8 -- ResumeProfile](#ds8--resumeprofile)
   - [DS9 -- ScraperRun](#ds9--scraperrun)
   - [DS10 -- FilterResult](#ds10--filterresult)
   - [DS11 -- JobFingerprint](#ds11--jobfingerprint)
5. [Cross-Cutting Concerns](#5-cross-cutting-concerns)

---

## 1. Overview

JobHunter is a local-first job-search automation platform built for job seekers who want automated scraping, AI-powered filtering, and personalized application material generation. The system supports **multiple resume profiles** (e.g., a Leadership/Management resume and an Architect/Developer resume) and evaluates every discovered job against all registered profiles to recommend the best-fit resume.

The platform follows a linear pipeline architecture:

```
Scrape --> Ingest --> Filter (rule-based) --> Filter (cheap AI) --> Evaluate (strong AI) --> Generate --> Review
```

All data resides in a local SQLite database. There are no cloud services beyond the AI model APIs and the Apify scraping API. The Streamlit dashboard is the sole user interface.

---

## 2. Component Interaction Diagram

```
+----------------------------------------------------------+
|                     C10  SCHEDULER                       |
|        (Windows Task Scheduler / cron trigger)           |
+----+-----------------------------------------------------+
     |  triggers
     v
+----+-----------------------------------------------------+
|                  C0  CONFIGURATION MANAGER                |
|          config.yaml, .env, API keys, thresholds          |
+----+-----------------------------------------------------+
     |  provides config to all components
     v
+----+-----------------------------------------------------+
|                  C1  SCRAPER ORCHESTRATOR                 |
|       parallel dispatch, retry, dedup at ingestion        |
+--+-------+-------+-------+------------------------------+
   |       |       |       |
   v       v       v       v
+------+ +------+ +------+ +------+
| C2a  | | C2b  | | C2c  | | C2d  |    <-- C2 Site Scrapers
|Remote| |Remote| |Well- | |Linke-|
| .io  | |Rocket| |found | | dIn  |
|      | | ship | |(Apify| |(Apify|
+--+---+ +--+---+ +--+---+ +--+---+
   |       |       |       |
   +---+---+---+---+---+---+
       |               |
       v               v
   DS1 RawJobPosting   DS9 ScraperRun
       |
       v
+------+-----------------------------------------------+
|              C3  TIER 1 RULE-BASED FILTER            |
|  salary gate, location keywords, title match,        |
|  blacklist / whitelist -- ZERO API cost              |
+------+-----------------------------------------------+
       |                          |
       v                          v
   DS3 ProcessedJob           DS10 FilterResult
   (status = "tier1_pass")    (audit log)
       |
       v
+------+-----------------------------------------------+
|              C4  TIER 2 QUICK AI FILTER              |
|  Claude Haiku / GPT-4o-mini -- cheap triage          |
|  yes / no / maybe with brief reasoning               |
+------+-----------------------------------------------+
       |                          |
       v                          v
   DS3 ProcessedJob           DS4 MatchEvaluation
   (status = "tier2_pass")    (tier = 2)
       |
       v
+------+-----------------------------------------------+
|            C5  TIER 3 DEEP AI EVALUATOR              |
|  Claude Sonnet / GPT-4o -- full resume matching      |
|  scores, fit analysis, resume recommendation         |
+------+-----------------------------------------------+
       |                          |
       v                          v
   DS3 ProcessedJob           DS4 MatchEvaluation
   (status = "evaluated")     (tier = 3)
       |
       v
+------+-----------------------------------------------+
|              C6  CONTENT GENERATOR                   |
|  cover letters, "Why this company?" answers          |
|  maps achievements to requirements                   |
+------+-----------------------------------------------+
       |               |
       v               v
   DS5 CoverLetter  DS6 WhyCompany
       |
       v
+------+-----------------------------------------------+
|            C9  DASHBOARD  (Streamlit)                |
|  review, approve/reject, "Ready to Apply" view,     |
|  status pipeline, filtering & sorting               |
+------+-----------------------------------------------+
       |
       v
   DS7 ApplicationStatus

       +-----------------------------------------------+
       |  C7  RESUME MANAGER   (serves all resume profiles) |
       |  C8  DATABASE LAYER   (SQLite + SQLAlchemy)    |
       |  C11 NOTIFICATION SVC (future / optional)      |
       +-----------------------------------------------+
              ^  shared services used by all above
```

**Condensed data-flow summary:**

```
Scrapers --(DS1)--> Tier1 Filter --(DS3)--> Tier2 AI --(DS4)--> Tier3 AI --(DS4)--> Content Gen --(DS5,DS6)--> Dashboard --(DS7)-->
```

---

## 3. Components

---

### C0 -- Configuration Manager

| Attribute            | Detail |
| -------------------- | ------ |
| **Purpose**          | Single source of truth for all runtime parameters. Loads infrastructure settings from `config.yaml`, operational settings from the SQLite `settings` table, and secrets from environment variables. Validates all via Pydantic and exposes typed configuration objects to every other component. See ADR-009 (amended). |
| **Inputs**           | `config.yaml` (infrastructure: `ai_models`, `database`, `dashboard`), SQLite `settings` table (operational: `scraping`, `filtering`, `scheduling`, `notifications`), `.env` (secrets), CLI overrides (optional). |
| **Outputs**          | Frozen `AppConfig` for infrastructure settings; category-specific Pydantic models (e.g., `ScrapingConfig`) read from DB on demand. |
| **Dependencies**     | `pyyaml`, `python-dotenv`, `pydantic` (for validation). No dependency on other JobHunter components. |
| **Error Handling**   | Fail-fast on startup. If `config.yaml` is missing or malformed, or if required API keys are absent, raise `ConfigurationError` with a human-readable message and halt the pipeline before any work begins. Log the exact missing/invalid fields. |
| **Implementation Notes** | |

- **Infrastructure settings** (`config.yaml`): `ai_models`, `database`, `dashboard`. Read at startup. Rarely change.
- **Operational settings** (SQLite `settings` table): `scraping`, `filtering`, `scheduling`, `notifications`. Read on demand via CRUD helpers. Editable from the dashboard UI. Stored as JSON per category, validated by Pydantic.
- API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `APIFY_API_TOKEN`) are **never** stored in `config.yaml` or the database. They live in `.env` or system environment variables and are merged at load time.
- Operational settings are hot-reloadable: the dashboard writes to the `settings` table, and pipeline components read from it at the start of each run.
- Schema example (`config.yaml` — infrastructure only after M1.5):

```yaml
# config.yaml (abbreviated)
scraping:
  remote_io:
    enabled: true
    base_url: "https://remote.io/remote-jobs"
    max_pages: 10
    delay_seconds: 2
  remote_rocketship:
    enabled: true
    base_url: "https://www.remoterocketship.com"
    max_pages: 10
    delay_seconds: 2
  wellfound:
    enabled: true
    apify_actor_id: "shahidirfan/wellfound-jobs-scraper"
    max_results: 100
  linkedin:
    enabled: true
    apify_actor_id: "apify/linkedin-jobs-scraper"
    max_results: 100

filtering:
  salary_min_usd: 90000
  location_keywords:
    include: ["remote", "worldwide", "anywhere", "turkey", "europe", "emea"]
    exclude: ["us only", "us-based only", "must be in us"]
  title_whitelist: ["architect", "principal", "staff", "lead", "director", "vp", "head of", "manager"]
  title_blacklist: ["intern", "junior", "entry level"]
  company_whitelist: []
  company_blacklist: []
  required_keywords: ["python", "golang", "distributed systems", "kubernetes"]
  excluded_keywords: ["clearance required", "must relocate"]

ai_models:
  tier2:
    provider: "anthropic"            # or "openai"
    model: "claude-3-5-haiku-latest" # or "gpt-4o-mini"
    max_tokens: 300
    temperature: 0.1
  tier3:
    provider: "anthropic"
    model: "claude-sonnet-4-20250514"
    max_tokens: 2000
    temperature: 0.3
  content_gen:
    provider: "openai"
    model: "gpt-4o"
    max_tokens: 2000
    temperature: 0.5

database:
  path: "data/jobhunter.db"
  echo_sql: false

scheduling:
  run_interval_hours: 12
  retry_failed_scrapers: true
  max_retries: 2

notifications:
  enabled: false
  method: "email"   # or "desktop"
  min_score_to_notify: 80
```

---

### C1 -- Scraper Orchestrator

| Attribute            | Detail |
| -------------------- | ------ |
| **Purpose**          | Coordinates the execution of all four site scrapers (C2a-C2d). Manages scheduling order, parallelism, per-scraper timeouts, and failure isolation. Performs deduplication at the ingestion boundary so duplicate postings from different sources are caught before they enter the database. |
| **Inputs**           | `AppConfig` (from C0), trigger signal (from C10 Scheduler or manual invocation). |
| **Outputs**          | List of `DS1 RawJobPosting` records written to the database. One `DS9 ScraperRun` audit record per scraper invocation. |
| **Dependencies**     | C0 (config), C2a-C2d (scrapers), C8 (database layer). |
| **Error Handling**   | **Isolation-first**: each scraper runs in its own try/except block. If C2a (Remote.io) throws an unrecoverable error, the orchestrator logs it, writes a failed `DS9` record, and proceeds to C2b, C2c, C2d. After all scrapers complete, it returns a summary indicating which succeeded and which failed. Retries are configurable (`max_retries` in config). A scraper that exceeds its timeout is forcibly cancelled. |
| **Implementation Notes** | |

- Scrapers run sequentially by default (to avoid IP-based rate limiting), but the orchestrator supports an `asyncio.gather` parallel mode when scrapers target different domains.
- Deduplication at ingestion uses `DS11 JobFingerprint`. The fingerprint is `SHA-256(normalize(company_name) + "|" + normalize(title))`. If a fingerprint already exists, the orchestrator appends the new source URL to `source_urls`, updates `last_seen` and increments `times_seen` — no duplicate job record is created. This handles both same-source re-scraping and cross-source deduplication.
- Each run generates a `DS9 ScraperRun` record capturing timing, counts, and errors for observability in the dashboard.
- The orchestrator exposes a `run_all()` entry point for the scheduler and individual `run_scraper(name)` for manual/dashboard-triggered runs.

---

### C2 -- Site Scrapers

All scrapers implement a common `BaseScraper` abstract class:

```python
class BaseScraper(ABC):
    @abstractmethod
    async def scrape(self, config: ScraperConfig) -> list[RawJobPosting]: ...

    @abstractmethod
    async def health_check(self) -> bool: ...
```

---

#### C2a -- Remote.io Scraper

| Attribute            | Detail |
| -------------------- | ------ |
| **Purpose**          | Scrapes job listings from Remote.io, a site that aggregates remote-friendly positions. |
| **Inputs**           | `ScraperConfig` (base URL, max pages, delay). |
| **Outputs**          | `list[DS1 RawJobPosting]`. |
| **Dependencies**     | `playwright` (Chromium), `beautifulsoup4` (HTML parsing), C0, C8. |
| **Error Handling**   | Catches `playwright.TimeoutError` per page load; retries the page up to 2 times with exponential backoff. If the site structure changes (CSS selectors return zero results), raises `ScraperStructureError` so the orchestrator knows this is not a transient failure but a schema change requiring developer attention. Logs the raw HTML of the failing page to `logs/scraper_debug/` for offline analysis. |
| **Implementation Notes** | |

- Navigates paginated listing pages. Extracts job cards via CSS selectors targeting title, company, location, salary (when present), and detail-page URL.
- For each job card, follows the detail-page link to extract the full description and requirements.
- Implements polite scraping: respects `delay_seconds` between requests, sets a realistic User-Agent header, and honors `robots.txt` directives.
- Salary data on this site is often missing; the `salary_raw` field may be `None`.

---

#### C2b -- RemoteRocketship Scraper

| Attribute            | Detail |
| -------------------- | ------ |
| **Purpose**          | Scrapes job listings from RemoteRocketship, which tends to have better salary transparency and remote-policy metadata. |
| **Inputs**           | `ScraperConfig` (base URL, max pages, delay). |
| **Outputs**          | `list[DS1 RawJobPosting]`. |
| **Dependencies**     | `playwright` (Chromium), `beautifulsoup4`, C0, C8. |
| **Error Handling**   | Same pattern as C2a. Additional handling for RemoteRocketship's occasional anti-bot interstitial: if detected (by checking for a known challenge element), waits and retries once before marking the run as blocked. |
| **Implementation Notes** | |

- RemoteRocketship has structured salary ranges and explicit remote-region tags, which improves Tier 1 filter accuracy.
- Listing pages use a load-more/infinite-scroll pattern; the scraper scrolls to the bottom of the page and waits for new content until `max_pages` equivalent of items are collected or no new items appear.
- Extracts: title, company, salary range, remote regions, tags, description, and application URL.

---

#### C2c -- Wellfound Scraper (Apify)

| Attribute            | Detail |
| -------------------- | ------ |
| **Purpose**          | Retrieves startup-focused job listings from Wellfound (formerly AngelList Talent) via the Apify REST API, avoiding the complexity of authenticated browser scraping. Targets senior and leadership roles at funded startups. |
| **Inputs**           | `ScraperConfig` (Apify actor ID, search parameters, max results), `APIFY_API_TOKEN` from environment. |
| **Outputs**          | `list[DS1 RawJobPosting]`. |
| **Dependencies**     | `httpx` (HTTP client), Apify REST API, C0, C8. No Playwright dependency. Shares `ApifyBaseScraper` base class with C2d. |
| **Error Handling**   | Same pattern as C2d (LinkedIn/Apify): actor run failures return structured error responses mapped to internal error types. If the Apify token is invalid or quota is exhausted, raises `ScraperQuotaError`. Polling for actor completion uses exponential backoff with a maximum wait of 5 minutes. |
| **Implementation Notes** | |

- Does **not** launch a browser. Communicates entirely via the Apify REST API using the `shahidirfan/wellfound-jobs-scraper` actor:
  1. `POST /v2/acts/{actorId}/runs` -- start the actor with search parameters (keywords, location filter, role type).
  2. Poll `GET /v2/acts/{actorId}/runs/{runId}` until status is `SUCCEEDED` or `FAILED`.
  3. `GET /v2/datasets/{datasetId}/items` -- retrieve results.
- Shares the same `ApifyBaseScraper` base class as C2d (LinkedIn), differing only in actor ID, input schema, and output field mapping.
- Wellfound provides rich company data (funding stage, team size, tech stack) which is captured in `DS2 Company`.
- Apify usage is metered; the config includes a `max_results` cap to control costs.
- Search parameters are configured in `config.yaml` under `scraping.wellfound`.

---

#### C2d -- LinkedIn Scraper (Apify)

| Attribute            | Detail |
| -------------------- | ------ |
| **Purpose**          | Retrieves LinkedIn job postings via the Apify REST API, avoiding direct LinkedIn scraping (which violates ToS and is technically challenging). |
| **Inputs**           | `ScraperConfig` (Apify actor ID, search parameters, max results), `APIFY_API_TOKEN` from environment. |
| **Outputs**          | `list[DS1 RawJobPosting]`. |
| **Dependencies**     | `httpx` (HTTP client), Apify REST API, C0, C8. No Playwright dependency. |
| **Error Handling**   | Apify actor run failures return structured error responses; the scraper maps these to internal error types. If the Apify token is invalid or quota is exhausted, raises `ScraperQuotaError`. Polling for actor completion uses exponential backoff with a maximum wait of 5 minutes. |
| **Implementation Notes** | |

- Does **not** launch a browser. Communicates entirely via the Apify REST API:
  1. `POST /v2/acts/{actorId}/runs` -- start the actor with search parameters (keywords, location filter, remote flag).
  2. Poll `GET /v2/acts/{actorId}/runs/{runId}` until status is `SUCCEEDED` or `FAILED`.
  3. `GET /v2/datasets/{datasetId}/items` -- retrieve results.
- LinkedIn data is typically richer in company information and seniority level, but salary data is inconsistent.
- Search parameters are configured in `config.yaml` under `scraping.linkedin` (keywords like "remote architect", "remote engineering manager", location set to "Worldwide").
- Apify usage is metered; the config includes a `max_results` cap to control costs.

---

### C3 -- Tier 1 Rule-Based Filter

| Attribute            | Detail |
| -------------------- | ------ |
| **Purpose**          | Fast, free, local filtering that eliminates clearly unqualified postings before any AI costs are incurred. Applies deterministic rules against structured and semi-structured job data. This is the primary cost-control gate. |
| **Inputs**           | `list[DS1 RawJobPosting]`, filter rules from `AppConfig`. |
| **Outputs**          | `list[DS3 ProcessedJob]` (jobs that pass), `list[DS10 FilterResult]` (audit trail for every job, pass or fail). |
| **Dependencies**     | C0 (config), C8 (database layer). No external APIs. |
| **Error Handling**   | Filter rules are evaluated independently. If one rule throws (e.g., regex compilation error on a malformed pattern), that rule is logged as errored and the job is flagged for manual review rather than silently dropped. The filter never crashes the pipeline; it degrades to "let it through" on individual rule failures. |
| **Implementation Notes** | |

- **Salary gate**: Extracts numeric salary from `salary_raw` using regex patterns that handle formats like "$120K-$150K", "120,000-150,000 USD", "EUR 90.000", etc. Normalizes to USD using a static exchange-rate table (updated manually in config). Jobs with `salary_min >= 90000 USD` pass. Jobs with no salary data are marked **AMBIGUOUS** (not rejected) -- they pass through to Tier 2 for AI assessment.
- **Location filter**: Scans `location_raw` and `description` for inclusion keywords (`remote`, `worldwide`, `anywhere`, `turkey`, `europe`, `emea`) and exclusion keywords (`us only`, `us-based only`, `must be located in`). Exclusion match = FAIL. Inclusion match = PASS. Neither = **AMBIGUOUS** (let Tier 2 assess).
- **Title matching**: Checks `title` against `title_whitelist` (regex patterns) and `title_blacklist`. If the title matches any `title_blacklist` pattern, the job is rejected (FAIL). If at least one whitelist pattern matches, the job passes. If no whitelist pattern matches, the job is marked **AMBIGUOUS** (not rejected).
- **Company whitelist/blacklist**: Jobs from whitelisted companies always pass immediately (skip other rules). Jobs from blacklisted companies are rejected. Other companies pass this rule.
- **Normalization**: During filtering, raw data is normalized into `DS3 ProcessedJob` fields (salary parsed to `salary_min`/`salary_max`/`currency`, location parsed to `location_policy`/`remote_regions`, description cleaned of HTML artifacts).
- **Fingerprint generation**: Computes `fingerprint_hash` and writes/updates `DS11 JobFingerprint`.

Filter rules are applied in order of computational cost (cheapest first):
1. Company blacklist (O(1) set lookup)
2. Title blacklist (fast regex)
3. Title whitelist (fast regex)
4. Location exclusion keywords (string search)
5. Location inclusion keywords (string search)
6. Salary gate (regex extraction + comparison)

---

### C4 -- Tier 2 Quick AI Filter

| Attribute            | Detail |
| -------------------- | ------ |
| **Purpose**          | Handles ambiguous cases that survive Tier 1 but lack clear structured signals. Uses cheap, fast AI models to make a quick yes/no/maybe decision with a brief reasoning string. Targets the "salary not listed but description sounds senior" and "remote but unclear on regions" scenarios. |
| **Inputs**           | `DS3 ProcessedJob` records with status `tier1_pass`, `DS8 ResumeProfile` (summary only, not full text -- to minimize tokens). |
| **Outputs**          | Updated `DS3 ProcessedJob` status (`tier2_pass`, `tier2_fail`, `tier2_maybe`), `DS4 MatchEvaluation` (tier=2). |
| **Dependencies**     | C0 (config, model selection), C7 (resume summaries), C8 (database), Anthropic SDK or OpenAI SDK. |
| **Error Handling**   | API errors (rate limits, timeouts, 5xx) trigger up to 3 retries with exponential backoff. If all retries fail for a specific job, the job is marked `tier2_error` and queued for the next run. Token budget tracking prevents runaway costs: if the cumulative token spend for a single run exceeds a configurable ceiling (`ai_models.tier2.max_tokens_per_run`), remaining jobs are deferred. Model fallback: if the primary provider is down, optionally falls back to the alternative provider (e.g., Anthropic -> OpenAI). |
| **Implementation Notes** | |

- **Model selection**: Default is Claude 3.5 Haiku (`claude-3-5-haiku-latest`) for its low cost and fast response. Fallback is GPT-4o-mini.
- **Prompt structure**: System prompt defines the evaluation criteria (remote-from-Turkey feasibility, seniority match, salary plausibility). User prompt contains the job's `title`, `company`, `location_policy`, `salary_min`/`salary_max` (if known), and a truncated `description_clean` (first 1500 characters). The resume summary (not full text) is included for context.
- **Response format**: Structured JSON output enforced via `response_format` parameter or prompt engineering:

```json
{
  "decision": "yes | no | maybe",
  "confidence": 0.85,
  "reasoning": "Role is listed as remote-worldwide, salary range $110K-$140K matches target, senior architect title aligns with experience.",
  "flags": ["salary_inferred", "region_unclear"]
}
```

- **Batching**: Jobs are processed in batches of 10 with concurrent API calls (`asyncio.gather` with a semaphore limiting to 5 simultaneous requests) to maximize throughput.
- **Cost tracking**: Every call logs `model_used` and `tokens_used` (prompt + completion) to `DS4 MatchEvaluation` for cost monitoring.

---

### C5 -- Tier 3 Deep AI Evaluator

| Attribute            | Detail |
| -------------------- | ------ |
| **Purpose**          | Performs comprehensive resume-to-job matching for jobs that passed Tier 2. Uses stronger (and more expensive) AI models to produce detailed fit scores, a recommended resume (from all registered profiles), strengths/weaknesses analysis, and actionable flags. This is the component that directly informs the user's apply/skip decision. |
| **Inputs**           | `DS3 ProcessedJob` records with status `tier2_pass` or `tier2_maybe`, all `DS8 ResumeProfile` records (extracted text, key skills, experience summary). |
| **Outputs**          | `DS4 MatchEvaluation` (tier=3, one record per resume type -- so 2 evaluations per job), updated `DS3 ProcessedJob` status (`evaluated`). |
| **Dependencies**     | C0 (config), C7 (full resume text), C8 (database), Anthropic SDK or OpenAI SDK. |
| **Error Handling**   | Same retry and fallback logic as C4, but with higher timeout thresholds (stronger models are slower). If one resume evaluation succeeds but the other fails, the successful one is saved and the failed one is retried independently. Cost ceiling is enforced per run (`ai_models.tier3.max_tokens_per_run`). |
| **Implementation Notes** | |

- **Model selection**: Default is Claude Sonnet 4 (`claude-sonnet-4-20250514`) for its strong analytical capabilities. Fallback is GPT-4o.
- **Multi-profile evaluation**: Each job is evaluated once per registered resume profile. The evaluation with the highest `overall_score` determines `recommended_resume`. With N profiles, this produces N evaluation records per job (cost scales linearly with profile count).
- **Prompt structure**: A detailed system prompt that establishes the evaluator persona (senior tech recruiter with knowledge of remote work policies, Turkish labor law implications, and US tech salary ranges). The user prompt includes:
  - Full job description
  - Full resume text (one at a time)
  - Specific evaluation criteria (remote-from-Turkey viability, salary alignment, seniority match, skill overlap, growth potential)
- **Response format**: Structured JSON:

```json
{
  "overall_score": 82,
  "fit_category": "strong_match",
  "skill_match_score": 85,
  "seniority_match_score": 90,
  "remote_compatibility_score": 75,
  "salary_alignment_score": 80,
  "strengths": [
    "12+ years of distributed systems experience directly maps to their microservices architecture requirements",
    "Previous team lead experience at comparable scale (50+ engineers)",
    "Cloud-native expertise (AWS, Kubernetes) matches their stack"
  ],
  "weaknesses": [
    "No explicit mention of their primary language (Go) in resume -- may need to highlight transferable experience",
    "Role mentions 'occasional travel to US HQ' which may complicate Turkey-based remote arrangement"
  ],
  "flags": ["travel_requirement", "language_gap_go"],
  "recommended_resume": "architect-developer",
  "reasoning": "The role emphasizes hands-on system design over people management. The Architect resume better highlights relevant technical depth. Consider adding Go experience from side projects to cover letter.",
  "cover_letter_hints": [
    "Emphasize distributed systems work at [Company X]",
    "Mention Kubernetes migration project that saved $2M",
    "Address remote-from-Turkey arrangement proactively"
  ]
}
```

- **Scoring rubric** (defined in system prompt):
  - 90-100: Exceptional match -- apply immediately
  - 75-89: Strong match -- worth applying
  - 60-74: Moderate match -- apply if pipeline is thin
  - 40-59: Weak match -- probably skip
  - 0-39: Poor match -- skip

---

### C6 -- Content Generator

| Attribute            | Detail |
| -------------------- | ------ |
| **Purpose**          | Generates personalized cover letters and "Why this company?" answers tailored to each shortlisted job. Maps the user's specific resume achievements to the job's stated requirements. Incorporates company research for authentic personalization beyond generic templates. |
| **Inputs**           | `DS3 ProcessedJob`, `DS4 MatchEvaluation` (Tier 3, including `cover_letter_hints`), `DS8 ResumeProfile` (the recommended resume), `DS2 Company` (research notes). |
| **Outputs**          | `DS5 CoverLetter`, `DS6 WhyCompany`. |
| **Dependencies**     | C0 (config), C5 (evaluation data for hints), C7 (resume text), C8 (database), Anthropic SDK or OpenAI SDK. |
| **Error Handling**   | Generation failures are non-blocking -- a failed cover letter does not prevent the job from appearing in the dashboard. Failed generations are marked with `status = "error"` and can be retried from the dashboard. If the model returns content that is too short (< 100 words for cover letter) or appears to be a refusal, the system retries with a slightly modified prompt. |
| **Implementation Notes** | |

- **Cover letter generation**:
  - System prompt establishes tone: professional but not stiff, confident but not arrogant, specific but not verbose.
  - Includes the user's resume text, the job description, the Tier 3 evaluation strengths/weaknesses, and any `cover_letter_hints`.
  - Instructs the model to open with a specific hook related to the company (not "I am writing to express my interest...").
  - Maps 2-3 specific resume achievements to 2-3 specific job requirements.
  - Addresses the remote-from-Turkey arrangement positively (timezone overlap with US/EU, proven remote track record).
  - Target length: 300-400 words.
  - Supports versioning: the user can request a regeneration from the dashboard, which creates a new version (`version` field increments) rather than overwriting.

- **"Why this company?" generation**:
  - Uses `DS2 Company` research notes (filled by the evaluator or manually).
  - References specific company achievements, products, or mission.
  - Connects the user's values and career goals to the company's direction.
  - Target length: 150-250 words.

- **Model selection**: Uses the `content_gen` model configuration (default GPT-4o for its strong creative writing).

---

### C7 -- Resume Manager

| Attribute            | Detail |
| -------------------- | ------ |
| **Purpose**          | Stores, serves, and manages the user's two resume PDFs. Extracts and caches resume text for AI context windows. Provides resume metadata and selection logic to other components. |
| **Inputs**           | Resume PDF files (manually placed in `data/resumes/`), user updates via dashboard. |
| **Outputs**          | `DS8 ResumeProfile` records, plain-text resume content for AI prompts. |
| **Dependencies**     | `PyMuPDF` or `pdfplumber` (PDF text extraction), C0 (config for file paths), C8 (database). |
| **Error Handling**   | PDF extraction failures are logged with details. If a PDF is corrupted or unreadable, the system falls back to a previously cached text extraction (stored in `DS8.extracted_text`). If no cached version exists, the component raises `ResumeUnavailableError` which prevents Tier 2/3 evaluation from running (since evaluation without resume context is meaningless). |
| **Implementation Notes** | |

- **Multi-profile model**: The system supports an arbitrary number of resume profiles. Each profile has a user-defined `label` (e.g., `"leadership"`, `"architect-developer"`, `"data-engineer"`) and an optional `description` explaining when to use it. There is no hardcoded limit on the number of profiles.
- **Text extraction**: On first load (or when PDF is updated), extracts full text using `PyMuPDF`, cleans it (removes headers/footers, fixes encoding issues), and stores in `DS8.extracted_text`.
- **Key skills extraction**: A one-time AI call (using the Tier 2 model to keep cost low) parses the extracted text and produces a structured `key_skills` list and `experience_summary` (stored in DS8). This is used by Tier 2 for quick context without sending the full resume.
- **Selection logic**: When a component needs "the resume" for a specific job, the Resume Manager checks `DS4.recommended_resume` from the Tier 3 evaluation. If no evaluation exists yet (Tier 2 stage), it provides all resume summaries.
- **Update detection**: Watches the `data/resumes/` directory for file changes (compares file hashes on each run). If a resume PDF is updated, triggers re-extraction and re-computation of key skills.

---

### C8 -- Database Layer

| Attribute            | Detail |
| -------------------- | ------ |
| **Purpose**          | Provides all data persistence via SQLite through SQLAlchemy ORM. Handles CRUD operations for all data structures, deduplication fingerprinting, query optimization, and schema migrations. |
| **Inputs**           | ORM model instances from all components. |
| **Outputs**          | Persisted data, query results, transaction confirmations. |
| **Dependencies**     | `sqlalchemy` (ORM), `alembic` (migrations), SQLite (engine). No external database server. |
| **Error Handling**   | All database operations are wrapped in explicit transactions with rollback on failure. Unique constraint violations (e.g., duplicate fingerprint insertion) are caught and handled gracefully (upsert pattern). Database lock contention (SQLite's single-writer limitation) is managed via retry with short backoff (relevant when the dashboard reads while the pipeline writes). Corrupt database detection triggers a warning in the dashboard; the system maintains a daily backup (`data/backups/jobhunter_{date}.db`). |
| **Implementation Notes** | |

- **SQLite rationale**: The system is single-user, local-first, and the dataset is small (thousands of jobs, not millions). SQLite eliminates the operational burden of a database server. WAL mode is enabled for better concurrent read/write behavior.
- **SQLAlchemy ORM**: All data structures (DS1-DS11) are mapped to SQLAlchemy declarative models. Relationships are defined (e.g., `ProcessedJob.evaluations`, `ProcessedJob.cover_letters`, `ProcessedJob.company`).
- **Migration support**: Alembic is configured for schema evolution. Initial migration creates all tables. Subsequent migrations handle field additions, index changes, etc.
- **Indexes**:
  - `fingerprint_hash` on `JobFingerprint` (unique)
  - `status` on `ProcessedJob` (for dashboard filtering)
  - `overall_score` on `MatchEvaluation` (for sorting)
  - `source_site` + `first_seen` on `ProcessedJob` (for scraper analytics)
  - Composite index on `job_id` + `resume_type` on `MatchEvaluation`
- **Connection configuration**: `check_same_thread=False` (required for Streamlit's threading model), `journal_mode=WAL`, `busy_timeout=5000`.
- **Backup strategy**: Before each scheduler run, copy the database file to `data/backups/` with a date-stamped filename. Retain the last 7 backups.

---

### C9 -- Dashboard (Streamlit)

| Attribute            | Detail |
| -------------------- | ------ |
| **Purpose**          | The sole user interface. Provides a job review workflow, filtering and sorting controls, an approve/reject mechanism, a "Ready to Apply" view that assembles all generated documents and application links, and a pipeline status tracker. |
| **Inputs**           | All data structures via C8 (database layer). User interactions (clicks, filters, text inputs). |
| **Outputs**          | Updated `DS7 ApplicationStatus` records, manual trigger signals to C1/C6, user-edited notes on `DS3`/`DS4`. |
| **Dependencies**     | `streamlit`, C0 (config), C8 (database), C1 (for manual scraper triggers), C6 (for on-demand content regeneration). |
| **Error Handling**   | Streamlit pages wrap database calls in try/except blocks and display user-friendly error messages via `st.error()`. Long-running operations (manual scrape trigger, content regeneration) display a spinner and stream progress. If the database is locked, the dashboard retries reads after a short delay and shows a "Pipeline is running, data may update momentarily" notice. |
| **Implementation Notes** | |

- **Page structure**:
  1. **Pipeline Overview** (home): Summary cards showing counts at each stage (new, reviewed, shortlisted, applying, applied). Recent scraper run status. Cost tracker (total tokens/spend).
  2. **Job Review**: Paginated table of evaluated jobs, sortable by score, date, source, salary. Expandable rows showing full evaluation, strengths/weaknesses, and recommended resume. Inline approve/reject buttons.
  3. **Shortlist**: Jobs the user has approved. Displays cover letter and "Why this company?" content (if generated). Buttons to regenerate content, edit inline, or change status.
  4. **Ready to Apply**: Final pre-application view. For each shortlisted job: application URL (clickable), recommended resume (with download link), generated cover letter (copyable), "Why this company?" answer (copyable), and a checklist of application steps.
  5. **Application Tracker**: Kanban-style board or table tracking jobs through statuses: `applied` -> `interviewing` -> `offered` / `rejected` / `withdrawn`. Notes field for recording interview feedback.
  6. **Settings**: Config viewer/editor for filter thresholds, model selection, scraper toggles. Trigger manual scraper runs. View scraper run history (`DS9`).
  7. **Analytics**: Charts showing jobs over time by source, pass rates by tier, score distribution, cost per tier, application funnel conversion.

- **Session state**: Streamlit's `st.session_state` is used to persist filter selections, page numbers, and expanded-row states across reruns.
- **Auto-refresh**: The Pipeline Overview page auto-refreshes every 60 seconds (configurable) to reflect pipeline progress during a run.
- **Data export**: CSV export of filtered job tables and evaluation results for offline analysis.

---

### C10 -- Scheduler

| Attribute            | Detail |
| -------------------- | ------ |
| **Purpose**          | Manages automated, periodic execution of the full pipeline. Orchestrates the end-to-end flow: scrape, filter, deduplicate, evaluate, generate. Provides logging, timing, and error reporting. |
| **Inputs**           | Trigger from Windows Task Scheduler (or manual CLI invocation). `AppConfig` from C0. |
| **Outputs**          | Completed pipeline run with all data structures populated. Log file per run in `logs/runs/`. Summary report (counts, errors, timing). |
| **Dependencies**     | C0 (config), C1 (scraper orchestrator), C3 (Tier 1 filter), C4 (Tier 2 filter), C5 (Tier 3 evaluator), C6 (content generator), C8 (database). |
| **Error Handling**   | The scheduler wraps the entire pipeline in a top-level exception handler. If any stage fails catastrophically (not individual job failures, which are handled by the stage itself), the scheduler logs the full traceback, writes an error summary to `logs/runs/{timestamp}_error.log`, and optionally triggers C11 (notification). The pipeline is designed to be re-runnable: a failed run can be restarted and it will pick up where it left off (jobs already processed are skipped via status checks). |
| **Implementation Notes** | |

- **Pipeline stages** (executed in order):

```
1. Load config                          (C0)
2. Backup database                      (C8)
3. Run scrapers                         (C1 -> C2a-C2d)
4. Apply Tier 1 filters to new jobs     (C3)
5. Apply Tier 2 AI filter               (C4)
6. Apply Tier 3 AI evaluation           (C5)
7. Generate content for high-score jobs  (C6, score >= threshold)
8. Log run summary                      (C10)
9. Send notification if applicable       (C11)
```

- **Windows Task Scheduler integration**: The scheduler is invoked via a Python script (`scripts/run_pipeline.py`) that Task Scheduler calls on a cron-like schedule. The script:
  1. Activates the virtual environment.
  2. Calls `pipeline.run()`.
  3. Exits with code 0 (success) or 1 (failure).
  Task Scheduler is configured with a `.xml` task definition that runs every 12 hours (default), with "Run whether user is logged on or not" enabled.
- **CLI interface**: `python -m jobhunter run [--stage scrape|filter|evaluate|generate|all] [--dry-run]` for manual or partial runs.
- **Logging**: Uses Python's `logging` module with both file and console handlers. Each run creates a timestamped log file. Log level is configurable in `config.yaml`. Structured logging (JSON format) is optional for machine parsing.
- **Idempotency**: Each stage checks job status before processing. A job already at `tier2_pass` will not be re-evaluated by Tier 2. This makes the pipeline safe to re-run after partial failures.
- **Timing**: Each stage's wall-clock time is recorded and included in the run summary for performance monitoring.

---

### C11 -- Notification Service (Optional/Future)

| Attribute            | Detail |
| -------------------- | ------ |
| **Purpose**          | Sends alerts to the user when high-scoring new matches are discovered. Reduces the need to manually check the dashboard after every pipeline run. |
| **Inputs**           | `DS4 MatchEvaluation` records with `overall_score >= min_score_to_notify` from the current run. `AppConfig` notification settings. |
| **Outputs**          | Sent email or desktop notification. |
| **Dependencies**     | C0 (config), C8 (database for evaluation data). For email: `smtplib` or a transactional email API. For desktop: `plyer` or `win10toast`. |
| **Error Handling**   | Notification failures are strictly non-blocking. A failed email send is logged but never causes the pipeline to report failure. Notifications are fire-and-forget. |
| **Implementation Notes** | |

- **Email notifications**: Uses SMTP (Gmail app password or a transactional service like SendGrid). The email contains:
  - Count of new high-scoring matches.
  - Top 3 jobs with title, company, score, and recommended resume.
  - Link to the local dashboard (if accessible).
- **Desktop notifications** (Windows): Uses `win10toast` or `plyer` to display a Windows toast notification with a summary.
- **Deduplication**: Only notifies about jobs evaluated in the *current* run, not previously evaluated jobs. Prevents notification fatigue on re-runs.
- **Gating**: Controlled by `notifications.enabled` in config. Default is `false` since this is a future/optional component.

---

## 4. Data Structures

All data structures are implemented as SQLAlchemy ORM models. Field types reference Python types; the corresponding SQLite column types are standard mappings (`str` -> `TEXT`, `int` -> `INTEGER`, `float` -> `REAL`, `datetime` -> `TEXT` stored as ISO 8601).

---

### DS1 -- RawJobPosting

Captures the raw, unprocessed scrape output before any normalization or filtering. Serves as the immutable audit trail of what was actually scraped.

| Field          | Type              | Constraints                        | Description |
| -------------- | ----------------- | ---------------------------------- | ----------- |
| `raw_id`       | `int`             | PK, autoincrement                  | Internal row identifier. |
| `source`       | `str`             | NOT NULL, enum: `remote_io`, `remote_rocketship`, `wellfound`, `linkedin` | Which scraper produced this record. |
| `source_url`   | `str`             | NOT NULL                           | Direct URL to the job posting on the source site. |
| `title`        | `str`             | NOT NULL                           | Job title as scraped (no normalization). |
| `company`      | `str`             | NOT NULL                           | Company name as scraped. |
| `salary_raw`   | `str \| None`     | NULLABLE                           | Raw salary string as it appeared on the page (e.g., "$120K-$150K", "Competitive", or `None` if absent). |
| `location_raw` | `str \| None`     | NULLABLE                           | Raw location string (e.g., "Remote - Worldwide", "Remote (US/EU)", "San Francisco, CA (Remote OK)"). |
| `description`  | `str`             | NOT NULL                           | Full job description text, stripped of HTML tags but otherwise unmodified. |
| `requirements` | `str \| None`     | NULLABLE                           | Extracted requirements/qualifications section if separately identifiable on the source page. |
| `raw_html`     | `str \| None`     | NULLABLE                           | Original HTML of the job detail page, stored for debugging scraper changes. May be large; consider compressing. |
| `scraped_at`   | `datetime`        | NOT NULL, DEFAULT `utcnow()`       | Timestamp when the scrape occurred (UTC). |
| `scraper_run_id` | `int \| None`   | FK -> `DS9.run_id`, NULLABLE       | Links to the scraper run that produced this record. |
| `fingerprint_hash` | `str`         | NOT NULL, INDEX                    | SHA-256 fingerprint for deduplication. Computed as `sha256(normalize(company) + "|" + normalize(title))` per ADR-008. |

---

### DS2 -- Company

Normalized company information, populated from scrape data and optionally enriched manually or via AI.

| Field            | Type            | Constraints                 | Description |
| ---------------- | --------------- | --------------------------- | ----------- |
| `company_id`     | `int`           | PK, autoincrement           | Internal company identifier. |
| `name`           | `str`           | NOT NULL, UNIQUE            | Canonical company name (normalized: trimmed, title-cased). |
| `website`        | `str \| None`   | NULLABLE                    | Company homepage URL. |
| `industry`       | `str \| None`   | NULLABLE                    | Industry vertical (e.g., "FinTech", "HealthTech", "DevTools"). |
| `size`           | `str \| None`   | NULLABLE                    | Company size bucket (e.g., "1-10", "11-50", "51-200", "201-1000", "1000+"). |
| `description`    | `str \| None`   | NULLABLE                    | Brief company description from scrape data or manual entry. |
| `glassdoor_url`  | `str \| None`   | NULLABLE                    | Glassdoor profile URL for user's own research. |
| `research_notes` | `str \| None`   | NULLABLE                    | Free-text notes from user or AI research. Used by C6 for cover letter personalization. |
| `created_at`     | `datetime`      | NOT NULL, DEFAULT `utcnow()` | When the company record was first created. |
| `updated_at`     | `datetime`      | NOT NULL, DEFAULT `utcnow()` | Last modification timestamp. |

---

### DS3 -- ProcessedJob

The canonical job record after normalization and Tier 1 filtering. This is the central entity that most other data structures reference.

| Field              | Type            | Constraints                        | Description |
| ------------------ | --------------- | ---------------------------------- | ----------- |
| `job_id`           | `int`           | PK, autoincrement                  | Internal job identifier. |
| `company_id`       | `int`           | FK -> `DS2.company_id`, NOT NULL, INDEX | Reference to the normalized company record. Required; jobs must link to a Company. |
| `raw_id`           | `int`           | FK -> `DS1.raw_id`, NOT NULL       | Back-reference to the original raw posting. |
| `title`            | `str`           | NOT NULL                           | Job title (may be lightly normalized, e.g., trimmed whitespace). |
| `salary_min`       | `int \| None`   | NULLABLE                           | Parsed minimum salary in the target currency (USD). `None` if salary was unparseable or absent. |
| `salary_max`       | `int \| None`   | NULLABLE                           | Parsed maximum salary in USD. |
| `currency`         | `str`           | NOT NULL, DEFAULT `"USD"`          | Original currency of the salary before conversion. |
| `location_policy`  | `str`           | NOT NULL, enum: `remote_worldwide`, `remote_regional`, `remote_country_specific`, `hybrid`, `onsite`, `unclear` | Normalized remote-work classification. |
| `remote_regions`   | `str \| None`   | NULLABLE                           | JSON-encoded list of allowed regions/countries if `location_policy` is `remote_regional` or `remote_country_specific` (e.g., `["US", "EU", "Turkey"]`). |
| `description_clean` | `str`          | NOT NULL                           | Cleaned and normalized job description (HTML removed, whitespace normalized, encoding fixed). |
| `requirements`     | `str \| None`   | NULLABLE                           | Extracted requirements section, cleaned. |
| `application_url`  | `str`           | NOT NULL                           | Direct link to apply (may differ from source URL if the job links to an external ATS). |
| `source_site`      | `str`           | NOT NULL                           | Which site this job was scraped from (same enum as `DS1.source`). |
| `fingerprint_hash` | `str`           | NOT NULL, UNIQUE INDEX             | Deduplication fingerprint (same as DS1). |
| `first_seen`       | `datetime`      | NOT NULL                           | When this job was first discovered. |
| `last_seen`        | `datetime`      | NOT NULL                           | When this job was last seen in a scrape (updated on each re-scrape). |
| `status`           | `str`           | NOT NULL, DEFAULT `"new"`, INDEX   | Pipeline status. Enum: `new`, `tier1_pass`, `tier1_fail`, `tier1_ambiguous`, `tier2_pass`, `tier2_fail`, `tier2_maybe`, `tier2_error`, `evaluated`, `shortlisted`, `rejected_by_user`, `applied`. |
| `created_at`       | `datetime`      | NOT NULL, DEFAULT `utcnow()`       | Record creation timestamp. |
| `updated_at`       | `datetime`      | NOT NULL, DEFAULT `utcnow()`       | Last modification timestamp. |

---

### DS4 -- MatchEvaluation

Stores AI evaluation results from both Tier 2 and Tier 3. Each job may have multiple evaluations (one per tier, and within Tier 3, one per resume type).

| Field              | Type            | Constraints                        | Description |
| ------------------ | --------------- | ---------------------------------- | ----------- |
| `eval_id`          | `int`           | PK, autoincrement                  | Internal evaluation identifier. |
| `job_id`           | `int`           | FK -> `DS3.job_id`, NOT NULL, INDEX | The job being evaluated. |
| `resume_id`        | `int \| None`   | FK -> `DS8.resume_id`, NULLABLE   | Which resume profile was used for this evaluation. `None` for Tier 2 evaluations (which use summary only, not a specific resume). |
| `tier_evaluated`   | `int`           | NOT NULL, CHECK `IN (2, 3)`        | Which tier produced this evaluation. |
| `overall_score`    | `int \| None`   | NULLABLE, CHECK `BETWEEN 0 AND 100` | Numeric fit score (0-100). Present for Tier 3; Tier 2 may use `None` (decision-based, not score-based). |
| `fit_category`     | `str \| None`   | NULLABLE, enum: `exceptional_match`, `strong_match`, `moderate_match`, `weak_match`, `poor_match` | Human-readable fit category derived from `overall_score`. |
| `skill_match_score` | `int \| None`  | NULLABLE, CHECK `BETWEEN 0 AND 100` | Sub-score: how well the candidate's skills match the requirements. Tier 3 only. |
| `seniority_match_score` | `int \| None` | NULLABLE, CHECK `BETWEEN 0 AND 100` | Sub-score: seniority level alignment. Tier 3 only. |
| `remote_compatibility_score` | `int \| None` | NULLABLE, CHECK `BETWEEN 0 AND 100` | Sub-score: likelihood that remote-from-Turkey is feasible. Tier 3 only. |
| `salary_alignment_score` | `int \| None` | NULLABLE, CHECK `BETWEEN 0 AND 100` | Sub-score: salary range vs. target alignment. Tier 3 only. |
| `strengths`        | `str \| None`   | NULLABLE                           | JSON-encoded list of strength statements. |
| `weaknesses`       | `str \| None`   | NULLABLE                           | JSON-encoded list of weakness/concern statements. |
| `flags`            | `str \| None`   | NULLABLE                           | JSON-encoded list of flag strings (e.g., `["travel_requirement", "visa_sponsorship_unclear"]`). |
| `recommended_resume_id` | `int \| None` | FK -> `DS8.resume_id`, NULLABLE | Which resume profile the AI recommends for this job. Populated in Tier 3. |
| `reasoning`        | `str \| None`   | NULLABLE                           | Free-text reasoning from the AI explaining the evaluation. |
| `cover_letter_hints` | `str \| None` | NULLABLE                           | JSON-encoded list of suggestions for cover letter personalization. Tier 3 only. |
| `decision`         | `str \| None`   | NULLABLE, enum: `yes`, `no`, `maybe` | Tier 2 decision field. |
| `confidence`       | `float \| None` | NULLABLE, CHECK `BETWEEN 0.0 AND 1.0` | Tier 2 confidence in the decision. |
| `model_used`       | `str`           | NOT NULL                           | Model identifier used (e.g., `claude-3-5-haiku-latest`, `gpt-4o`). |
| `prompt_tokens`    | `int \| None`   | NULLABLE                           | Number of prompt tokens consumed. |
| `completion_tokens` | `int \| None`  | NULLABLE                           | Number of completion tokens consumed. |
| `tokens_used`      | `int`           | NOT NULL                           | Total tokens consumed (prompt + completion). For cost tracking. |
| `cost_usd`         | `float \| None` | NULLABLE                           | Estimated cost in USD based on model pricing. |
| `evaluated_at`     | `datetime`      | NOT NULL, DEFAULT `utcnow()`       | When the evaluation was performed. |

---

### DS5 -- CoverLetter

Generated cover letter content. Supports versioning so the user can request regeneration without losing previous versions.

| Field          | Type          | Constraints                        | Description |
| -------------- | ------------- | ---------------------------------- | ----------- |
| `letter_id`    | `int`         | PK, autoincrement                  | Internal letter identifier. |
| `job_id`       | `int`         | FK -> `DS3.job_id`, NOT NULL, INDEX | The job this cover letter targets. |
| `resume_id`    | `int`         | FK -> `DS8.resume_id`, NOT NULL  | Which resume profile the letter was written for. |
| `content`      | `str`         | NOT NULL                           | Full cover letter text (Markdown or plain text). |
| `version`      | `int`         | NOT NULL, DEFAULT `1`              | Version number. Increments on regeneration. |
| `is_active`    | `bool`        | NOT NULL, DEFAULT `True`           | Whether this is the currently active version. Only one version per `job_id + resume_type` should be active. |
| `model_used`   | `str`         | NOT NULL                           | Model that generated this letter. |
| `prompt_tokens` | `int \| None` | NULLABLE                          | Prompt tokens consumed. |
| `completion_tokens` | `int \| None` | NULLABLE                       | Completion tokens consumed. |
| `tokens_used`  | `int`         | NOT NULL                           | Total tokens consumed. |
| `cost_usd`     | `float \| None` | NULLABLE                        | Estimated generation cost. |
| `generated_at` | `datetime`    | NOT NULL, DEFAULT `utcnow()`       | When the letter was generated. |

---

### DS6 -- WhyCompany

Generated "Why this company?" answers for use in applications and interviews.

| Field          | Type          | Constraints                        | Description |
| -------------- | ------------- | ---------------------------------- | ----------- |
| `answer_id`    | `int`         | PK, autoincrement                  | Internal answer identifier. |
| `job_id`       | `int`         | FK -> `DS3.job_id`, NOT NULL, INDEX | The job/company this answer targets. |
| `content`      | `str`         | NOT NULL                           | Full answer text. |
| `version`      | `int`         | NOT NULL, DEFAULT `1`              | Version number. Increments on regeneration. |
| `is_active`    | `bool`        | NOT NULL, DEFAULT `True`           | Whether this is the currently active version. |
| `model_used`   | `str`         | NOT NULL                           | Model that generated this answer. |
| `prompt_tokens` | `int \| None` | NULLABLE                          | Prompt tokens consumed. |
| `completion_tokens` | `int \| None` | NULLABLE                       | Completion tokens consumed. |
| `tokens_used`  | `int`         | NOT NULL                           | Total tokens consumed. |
| `cost_usd`     | `float \| None` | NULLABLE                        | Estimated generation cost. |
| `generated_at` | `datetime`    | NOT NULL, DEFAULT `utcnow()`       | When the answer was generated. |

---

### DS7 -- ApplicationStatus

Tracks each job through the user's application pipeline. Supports a linear-with-branches status flow.

| Field        | Type          | Constraints                        | Description |
| ------------ | ------------- | ---------------------------------- | ----------- |
| `status_id`  | `int`         | PK, autoincrement                  | Internal status record identifier. |
| `job_id`     | `int`         | FK -> `DS3.job_id`, NOT NULL, INDEX | The job being tracked. |
| `status`     | `str`         | NOT NULL, enum (see below)         | Current application status. |
| `notes`      | `str \| None` | NULLABLE                           | Free-text notes (e.g., "HR said they support Turkey remote", "Interview scheduled for March 15"). |
| `updated_at` | `datetime`    | NOT NULL, DEFAULT `utcnow()`       | When this status was set. |
| `updated_by` | `str`         | NOT NULL, DEFAULT `"system"`       | Who set this status: `system` (automated pipeline) or `user` (dashboard action). |

**Status enum values and transitions:**

```
new --> reviewed --> shortlisted --> applying --> applied --> interviewing --> offered
                                                       \--> rejected
                                                       \--> withdrawn
                 \--> rejected_by_user
```

| Status              | Description |
| ------------------- | ----------- |
| `new`               | Freshly evaluated, not yet reviewed by user. |
| `reviewed`          | User has seen the job in the dashboard. |
| `shortlisted`       | User has approved the job for application. |
| `applying`          | User is actively preparing the application. |
| `applied`           | Application has been submitted. |
| `interviewing`      | In interview process. |
| `offered`           | Received an offer. |
| `rejected`          | Rejected by the company (at any stage post-application). |
| `withdrawn`         | User withdrew the application. |
| `rejected_by_user`  | User decided not to pursue this job. |

Note: `DS7` stores the **full history** of status transitions (append-only). The current status is the most recent record for a given `job_id`.

---

### DS8 -- ResumeProfile

Metadata and extracted content for the user's resume profiles. Supports any number of profiles with user-defined labels.

| Field               | Type          | Constraints                        | Description |
| ------------------- | ------------- | ---------------------------------- | ----------- |
| `resume_id`         | `int`         | PK, autoincrement                  | Internal resume identifier. |
| `label`             | `str`         | NOT NULL, UNIQUE                   | User-defined label for this profile (e.g., `"leadership"`, `"architect-developer"`, `"data-engineer"`). Used in config, prompts, and dashboard display. |
| `description`       | `str \| None` | NULLABLE                           | Optional description of when this resume should be used (e.g., `"For engineering manager and VP-level roles"`). Included in AI evaluation prompts to guide resume recommendation. |
| `file_path`         | `str`         | NOT NULL                           | Absolute or project-relative path to the PDF file (e.g., `data/resumes/resume_leadership.pdf`). |
| `file_hash`         | `str`         | NOT NULL                           | SHA-256 hash of the PDF file. Used to detect when the user updates a resume. |
| `extracted_text`    | `str`         | NOT NULL                           | Full plain-text extraction from the PDF. |
| `key_skills`        | `str`         | NOT NULL                           | JSON-encoded list of skill strings extracted by AI (e.g., `["Python", "System Design", "Team Leadership", "AWS", "Kubernetes"]`). |
| `experience_summary` | `str`        | NOT NULL                           | AI-generated 2-3 sentence summary of the resume for use in Tier 2 prompts. |
| `years_of_experience` | `int \| None` | NULLABLE                         | Total years of professional experience extracted from the resume. |
| `last_updated`      | `datetime`    | NOT NULL, DEFAULT `utcnow()`       | When the profile was last refreshed (re-extracted from PDF). |

---

### DS9 -- ScraperRun

Audit log for every scraper execution. One record per scraper per orchestrated run.

| Field            | Type            | Constraints                        | Description |
| ---------------- | --------------- | ---------------------------------- | ----------- |
| `run_id`         | `int`           | PK, autoincrement                  | Internal run identifier. |
| `scraper_name`   | `str`           | NOT NULL, enum: `remote_io`, `remote_rocketship`, `wellfound`, `linkedin` | Which scraper was executed. |
| `started_at`     | `datetime`      | NOT NULL                           | When the scraper started. |
| `completed_at`   | `datetime \| None` | NULLABLE                        | When the scraper finished. `None` if still running or crashed without cleanup. |
| `duration_seconds` | `float \| None` | NULLABLE                         | Wall-clock duration. Computed as `completed_at - started_at`. |
| `status`         | `str`           | NOT NULL, DEFAULT `"running"`, enum: `running`, `success`, `partial_success`, `failed`, `timeout`, `blocked`, `cancelled` | Outcome of the run. `cancelled` indicates user-initiated stop from the dashboard. |
| `jobs_found`     | `int`           | NOT NULL, DEFAULT `0`              | Total number of job postings found during the scrape. |
| `jobs_new`       | `int`           | NOT NULL, DEFAULT `0`              | Number of postings that were new (not previously seen). |
| `jobs_updated`   | `int`           | NOT NULL, DEFAULT `0`              | Number of previously seen postings whose `last_seen` was updated. |
| `pages_scraped`  | `int`           | NOT NULL, DEFAULT `0`              | Number of listing pages processed. |
| `error_message`  | `str \| None`   | NULLABLE                           | Error details if status is `failed`, `timeout`, or `blocked`. |
| `error_traceback` | `str \| None`  | NULLABLE                           | Full Python traceback for debugging. |
| `config_snapshot` | `str \| None`  | NULLABLE                           | JSON-encoded snapshot of the scraper config used for this run (for reproducibility). |

---

### DS10 -- FilterResult

Audit trail for Tier 1 rule-based filtering. One record per raw job posting that enters the filter, regardless of outcome.

| Field            | Type          | Constraints                        | Description |
| ---------------- | ------------- | ---------------------------------- | ----------- |
| `filter_id`      | `int`         | PK, autoincrement                  | Internal filter result identifier. |
| `job_id`         | `int \| None` | FK -> `DS3.job_id`, NULLABLE       | Reference to the ProcessedJob if created. `None` if the job was rejected before a ProcessedJob record was created. |
| `raw_id`         | `int`         | FK -> `DS1.raw_id`, NOT NULL, UNIQUE | Reference to the raw posting that was filtered. One FilterResult per RawJobPosting. |
| `passed`         | `bool`        | NOT NULL                           | Whether the job passed Tier 1 rules (True for PASS or AMBIGUOUS, False for FAIL). |
| `decision`       | `str`         | NOT NULL, enum: `pass`, `fail`, `ambiguous` | Tri-state filter outcome. AMBIGUOUS jobs pass to Tier 2. |
| `rules_applied`  | `str`         | NOT NULL                           | JSON-encoded list of rule names that were evaluated (e.g., `["company_blacklist", "title_blacklist", "title_whitelist", "location_exclude", "location_include", "salary_gate"]`). |
| `rules_passed`   | `str`         | NOT NULL                           | JSON-encoded list of rule names that the job passed. |
| `rules_failed`   | `str`         | NOT NULL                           | JSON-encoded list of rule names that the job failed. Empty list `[]` if all passed. |
| `rule_details`   | `str \| None` | NULLABLE                           | JSON-encoded object with per-rule details (e.g., `{"salary_gate": {"parsed_min": 95000, "parsed_max": 120000, "threshold": 90000, "passed": true}}`). Useful for debugging filter logic. |
| `filtered_at`    | `datetime`    | NOT NULL, DEFAULT `utcnow()`       | When the filter was applied. |

---

### DS11 -- JobFingerprint

Deduplication tracking. Maps fingerprint hashes to canonical job records and tracks how many times and from which sources a job has been seen.

| Field              | Type          | Constraints                  | Description |
| ------------------ | ------------- | ---------------------------- | ----------- |
| `fingerprint_hash` | `str`         | PK (natural key)             | SHA-256 fingerprint: `sha256(normalize(company) + "|" + normalize(title))`. Natural primary key — no surrogate ID. Excludes source URL so cross-site duplicates are caught. |
| `job_id`           | `int`         | FK -> `DS3.job_id`, NOT NULL | The canonical ProcessedJob this fingerprint maps to. |
| `source_urls`      | `str`         | NOT NULL                     | JSON-encoded list of all source URLs where this job was found (e.g., `["https://remote.io/job/123", "https://linkedin.com/jobs/456"]`). Grows as the same job is found on multiple sites. |
| `first_seen`       | `datetime`    | NOT NULL                     | When this fingerprint was first encountered. |
| `last_seen`        | `datetime`    | NOT NULL                     | When this fingerprint was most recently encountered. |
| `times_seen`       | `int`         | NOT NULL, DEFAULT `1`        | Total number of times this job has been encountered across all scraper runs and sources. |

---

## 5. Cross-Cutting Concerns

### Logging

All components use Python's standard `logging` module configured via C0. Log format:

```
%(asctime)s | %(levelname)-8s | %(name)s | %(message)s
```

Log levels follow standard semantics:
- `DEBUG`: Detailed scraping steps, SQL queries, full AI prompts (only in development).
- `INFO`: Pipeline stage transitions, job counts, timing.
- `WARNING`: Retries, fallbacks, missing optional data.
- `ERROR`: Failed operations that were handled (e.g., one scraper failing).
- `CRITICAL`: Pipeline-halting failures (e.g., database corruption, missing config).

### Cost Tracking

Every AI API call records `model_used`, `prompt_tokens`, `completion_tokens`, and `cost_usd` in the relevant data structure (DS4, DS5, DS6). The dashboard aggregates this data to show daily/weekly/monthly AI spend broken down by tier and model. Budget alerts can be configured in C0.

### Security

- API keys (Anthropic, OpenAI, Apify) are never stored in `config.yaml` or committed to version control. They reside in `.env` (gitignored) or system environment variables.
- The SQLite database file should be excluded from version control.
- The dashboard runs on `localhost` only (Streamlit's default) and has no authentication (single-user system).

### Testing Strategy

- **Unit tests**: Each component has isolated unit tests with mocked dependencies. Scrapers are tested against saved HTML fixtures.
- **Integration tests**: Database layer tests use an in-memory SQLite instance. AI components are tested with recorded (cached) API responses.
- **End-to-end tests**: A `--dry-run` mode in the scheduler exercises the full pipeline with mock scrapers and AI responses.

### Performance Considerations

- SQLite WAL mode enables concurrent reads during pipeline writes.
- AI API calls within a tier are batched and parallelized (with concurrency limits).
- Raw HTML storage (`DS1.raw_html`) is the largest data consumer; consider periodic cleanup of old raw HTML (retain for 30 days).
- Playwright browser instances are reused across pages within a single scraper run (one browser context per scraper, not per page).

---

*End of document.*
