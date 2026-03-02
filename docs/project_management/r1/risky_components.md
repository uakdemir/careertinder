# JobHunter — Risky Components Analysis

> Which parts of the system are most likely to consume development time, and what can we do about it?

**Context:** Claude Opus generates all code. The user provides async review, live testing, API credentials, and resume PDFs. The target is a working MVP in 1-2 weeks.

---

## Risk Summary

| Component | Risk Level | Why | Mitigation |
|---|---|---|---|
| **C2c: Wellfound Scraper (Apify)** | **LOW** | Now uses Apify REST API (same pattern as LinkedIn). No auth, no browser, no CAPTCHA risk. | Implement alongside LinkedIn Apify scraper. Share `ApifyBaseScraper` base class. |
| **C2a/C2b: Remote.io / RemoteRocketship Scrapers** | **MEDIUM** | HTML structure unknown until inspected live; sites may use anti-bot measures | Start early (Day 1-2). Save HTML fixtures for offline iteration. User inspects page, shares selectors. |
| **C2c/C2d: Wellfound + LinkedIn (Apify)** | **LOW** | Both use Apify REST API, well-documented, deterministic JSON output. Share `ApifyBaseScraper`. | Implement both in ~1-2 hours total. Only risk is Apify actor format changes. |
| **C5: Tier 3 Deep AI Evaluator** | **LOW-MEDIUM** | Prompt tuning is iterative; structured JSON parsing may need adjustments | Use structured output mode. Test on 5-10 real jobs and adjust. Budget 1-2 iterations. |
| **C9: Dashboard** | **LOW** | Streamlit is fast to build for simple use cases | Keep MVP minimal: one table page + one detail page. No charts. |
| **C8: Database Layer** | **NEGLIGIBLE** | SQLAlchemy + Alembic is deterministic. Claude generates models from spec. | Zero risk. Generated from components_r1.md DS1-DS11 in one pass. |
| **C0: Config Manager** | **NEGLIGIBLE** | YAML + Pydantic validation is well-understood | Zero risk. Generated in minutes. |

---

## Detailed Risk Analysis

### RISK 1: Playwright Scrapers (C2a, C2b) — Hours, Not Days

**Why these are the primary time sink:**

Playwright scrapers are integrations against moving targets. The development loop is:

```
1. Claude writes scraper code based on assumptions about page structure
2. User runs the scraper
3. Scraper fails (wrong selectors, anti-bot block, missing pagination, JS not loaded)
4. User shares the error or page HTML
5. Claude adjusts selectors/logic
6. Repeat steps 2-5 until it works
```

This loop takes **15-30 minutes per iteration**, and each scraper may need 3-5 iterations. That's 1-2 hours per scraper spread over real wall-clock time because the user must be available to run the code.

**Breakdown by scraper:**

| Scraper | Est. Iterations | Est. Wall Time | Why |
|---|---|---|---|
| Remote.io | 3-5 | 1-2 hours | Static-ish HTML, likely the easiest target |
| RemoteRocketship | 3-5 | 1-2 hours | Similar to Remote.io, possible infinite-scroll |
| LinkedIn (Apify) | 1-2 | 30 min | REST API, no HTML parsing, deterministic |
| Wellfound (Apify) | 1-2 | 30 min | REST API via `shahidirfan/wellfound-jobs-scraper`, same pattern as LinkedIn |

**Note:** Wellfound was previously the #1 risk (HIGH — authenticated Playwright scraping with 2FA, CAPTCHA, session management). The decision to use Apify's Wellfound actor (see ADR-004) eliminates this risk entirely. Wellfound and LinkedIn now share the same `ApifyBaseScraper` base class and follow an identical integration pattern.

**Mitigation strategy:**

1. **Start with Apify scrapers (LinkedIn + Wellfound).** Both are REST APIs with JSON output — zero HTML parsing risk. Get two scrapers fully working end-to-end in ~1 hour to validate the entire pipeline (ingest → DB → dedup).

2. **Start Playwright scrapers on Day 1-2.** Begin the iterative testing loop early since it's calendar-time-bound, not compute-bound.

3. **Save raw HTML fixtures.** On the first successful page load, save the HTML to `tests/fixtures/`. All subsequent selector tuning happens offline against saved HTML — no more live requests needed for logic changes.

---

### RISK 2: AI Prompt Quality (C4, C5, C6)

**Why it matters:**

The AI evaluation produces scores and recommendations that the user acts on. Bad prompts → bad scores → missed good jobs or wasted time on bad ones. The quality loop is:

```
1. Claude writes prompt templates
2. Run evaluation on 5-10 real scraped jobs
3. Review AI output: Are scores reasonable? Is reasoning coherent? Is the JSON valid?
4. Adjust prompts (more specific rubric, better examples, stricter format instructions)
5. Repeat until output quality is acceptable
```

**Estimated iterations:** 2-3 rounds, each taking 30-60 minutes (running against real jobs + reviewing output).

**Mitigation:**

1. **Use structured output mode** (`response_format: json`) from day one. This eliminates 90% of parsing failures.
2. **Start with Claude Sonnet for Tier 3** — it follows structured instructions reliably.
3. **Skip OpenAI fallback for MVP.** Dual-provider doubles the prompt engineering surface area. Add it post-MVP.
4. **Include 2-3 few-shot examples** in the system prompt showing expected JSON output. This dramatically improves consistency.
5. **Accept "good enough" on first pass.** Prompt tuning is unbounded — timebox it to 2 rounds and iterate post-MVP based on real usage.

---

### RISK 3: Dashboard Scope Creep (C9)

**Why it's a risk:**

Dashboards attract feature requests. Once you see data, you want filters, charts, export, keyboard shortcuts, dark mode, etc. Each feature is individually small but collectively they bloat M5.

**Mitigation: Define MVP Dashboard upfront**

The MVP dashboard has exactly 3 pages:

| Page | What It Shows | Complexity |
|---|---|---|
| **Job List** | Table of evaluated jobs, sortable by score/date/salary. Filters: status, source, score range. Inline Approve/Reject buttons. | 2-3 hours |
| **Job Detail** | Click a job → see full description + AI evaluation + strengths/weaknesses + recommended resume. Link to apply. | 1-2 hours |
| **Ready to Apply** | Jobs with status `shortlisted`. Shows: apply link, recommended resume, cover letter, why-company answer. Copy buttons. | 1-2 hours |

**NOT in MVP:** Charts, analytics, cost tracking dashboard, scraper health page, Kanban board, export. These are all post-MVP and add zero value until the pipeline is running reliably.

---

### RISK 4: Salary Parsing (C3)

**Why it's worth calling out:**

Salary strings in job postings are wildly inconsistent:
- `$120K - $150K`
- `120,000-150,000 USD`
- `EUR 90.000`
- `$7,500/mo`
- `Competitive`
- `DOE`
- (blank)

A naive parser will miss formats and either over-filter (rejecting good jobs) or under-filter (wasting AI budget).

**Mitigation:**

1. **Default to "pass through" on unparseable salary.** Better to let an ambiguous job reach Tier 2 ($0.001 cost) than to silently drop a good match.
2. **Build a test corpus of 20+ real salary strings** from the first scraper run. Use this as the ground truth for parser tests.
3. **Keep it simple:** regex-based extraction is sufficient. Don't build a full NLP salary parser for MVP.

---

## Components That Are NOT Risky

These components are deterministic, well-specified, and Claude Opus can generate them with near-zero iteration:

| Component | Why It's Safe | Est. Time |
|---|---|---|
| C0: Config Manager | YAML + Pydantic. Spec is in components_r1.md. | 30 min |
| C8: Database Layer | SQLAlchemy models generated from DS1-DS11 spec. Alembic migration. | 1 hour |
| C7: Resume Manager | PDF extraction with pdfplumber. Hash-based change detection. | 1 hour |
| C3: Rule Engine (non-salary) | Title matching, location keywords, blacklist/whitelist. Simple string logic. | 1 hour |
| C10: Scheduler | Pipeline orchestrator calling stages in order. Lock file. | 30 min |
| C4: Tier 2 AI Filter | API wrapper + prompt + JSON parsing. Same pattern as C5 but simpler. | 1 hour |
| C6: Content Generator | Same API pattern as C4/C5 with different prompts. | 1 hour |

---

## Recommended Day-by-Day Plan

| Day | Focus | User Involvement Needed |
|---|---|---|
| **Day 1** | M0 (Foundation) + Start M1 (Apify scrapers first: LinkedIn + Wellfound, then Remote.io) | Provide API keys, run scrapers, report results |
| **Day 2** | Finish M1 scrapers (RemoteRocketship) + M2 (Rule Filtering) | Run scrapers, review filter results |
| **Day 3** | M3 (AI Evaluation) + M4 (Content Generation) | Review AI evaluation quality on real jobs |
| **Day 4** | M5 (Minimal Dashboard) + M6 (Automation) | Review dashboard, test pipeline end-to-end |
| **Day 5-7** | M7 (Fix issues, tune prompts, add 2nd scraper iteration) | Use the system for real, report issues |

**Key principle:** The user's time is the bottleneck, not Claude's. Minimize the number of "run this and tell me what happens" cycles by getting scraper HTML fixtures early and front-loading live testing.
