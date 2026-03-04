---
name: review-code
description: Review recent repository commits against a milestone analysis document and project architecture constraints to find implementation defects and drift. Use when asked to audit the last N commits for bugs, architecture violations, spec drift, security issues, and missing tests before merge.
---

# Review Code

Audit the latest commits with a code-review mindset, using the analysis doc as the implementation contract and `CLAUDE.md`/ADRs as hard architecture constraints.

## Parameters

| Placeholder | Example |
|-------------|---------|
| `[COMMIT_COUNT]` | `1` |
| `[ANALYSIS_DOC]` | `tmp/ai/temp/hobby/resume_matcher/analysis/r1/m2.md` |

Fixed behavior:
- Response input (round > 1): `./tmp/response_code.md`
- Review output: `./tmp/review_code.md`

## Workflow

1. Resolve inputs:
   - Required: `[COMMIT_COUNT]`, `[ANALYSIS_DOC]`
2. Read context:
   - `CLAUDE.md` (hard constraints)
   - `docs/architecture/adrs.md` (accepted architecture decisions)
   - `[ANALYSIS_DOC]` (spec contract for the milestone)
3. If `./tmp/response_code.md` exists:
   - Read it first.
   - Do not re-raise pushed-back or deferred items unless new concrete evidence exists in the reviewed commits.
4. Collect target commits:
   - Use the last `[COMMIT_COUNT]` commits from `HEAD`.
   - Review each commit's changed files and patch.
5. For each commit, identify only:
   - `Bug`: logic errors, unhandled edge cases, missing boundary error handling, race conditions, data integrity issues
   - `Architecture`: conflicts with `CLAUDE.md` rules or unresolved ADR constraints
   - `Spec Drift`: divergences from `[ANALYSIS_DOC]`
   - `Security`: OWASP Top 10, injection risks, auth bypass, exposed secrets
   - `Test Gap`: risky logic paths without meaningful test coverage
6. Do not flag:
   - Style preferences not backed by a linter rule
   - Refactoring opportunities that expand scope
   - Missing comments or docstrings
   - Hypothetical future requirements
7. Cite evidence with precise file/line and commit hash.
8. Write output using the exact template below.
9. Write the final review to `./tmp/review_code.md`.

## Output Template (Use Exactly)

---
## [Issue Title]

**Severity:** Critical | High | Medium | Low
**File:** path/to/file.py:[line_number]
**Commit:** [short hash]
**Category:** Bug | Architecture | Spec Drift | Security | Test Gap

**Description:**
[Clear explanation of the problem]

**Expected (per [ANALYSIS_DOC] or CLAUDE.md):**
[What should happen]

**Suggested fix:**
[Concrete suggestion — be specific enough for Claude to act on it without ambiguity]

---

## Summary
| Severity | Count |
|----------|-------|
| Critical | X |
| High     | Y |
| Medium   | Z |
| Low      | W |
