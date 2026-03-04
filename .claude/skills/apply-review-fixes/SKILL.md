---
name: apply-review-fixes
description: Apply code review fixes autonomously, iterate until build passes, and write a response file with outcomes. Use when processing code review feedback that requires applying fixes across multiple files with build verification.
---

# Apply Review Fixes

Apply all fixes from a code review file autonomously, iterate until build is clean, and write a response file with outcomes and any pushbacks.

## Arguments

- First argument: `[ROUND_NUMBER]` — review round number (e.g., `1`, `2`, `3`)
- Second argument: `[ANALYSIS_DOC]` — related analysis document path, or `none` if not applicable (e.g., `tmp/ai/temp/hobby/resume_matcher/analysis/r1/m2.md`)
- Third argument: `[MILESTONE]` — current milestone (e.g., `M2`, `M3`)

## Fixed Files (Constants)

- Review input: `./tmp/review_code.md`
- Response output: `./tmp/response_code.md`

## Workflow

1. Read `./tmp/review_code.md`.

2. For each comment, categorize as one of:
   - **Apply** — valid fix, consistent with architecture and CLAUDE.md
   - **Pushback** — debatable, conflicts with CLAUDE.md rules or ADRs, or expands scope
   - **Defer** — out of scope for `[MILESTONE]`, cosmetic-only, or post-milestone

3. For all **Apply** items: create sub-tasks per review category and apply fixes in parallel using isolated worktrees where files would conflict. Apply fixes to the relevant files.

4. After all fixes are applied, run:
   ```bash
   ruff check .
   mypy .
   pytest -x -q
   ```

5. If any errors occur: analyze the output, apply corrections, re-run. Do NOT stop until all three commands pass with zero errors.

6. APPEND (do not overwrite) to `./tmp/response_code.md` using this format:

```markdown
## Round [ROUND_NUMBER]

### [ID] — [COMMENT_TITLE]
**Status:** Applied | Pushed back | Deferred

**[If Applied]**
Change: file:line — what was changed

**[If Pushed back]**
Reason: cite CLAUDE.md rule number or ADR

**[If Deferred]**
Reason: why / Suggested timing: milestone or trigger

---
```

7. Print a final summary: `X applied, Y pushed back, Z deferred. Build: PASS/FAIL.`

## Rules

- Do not stop until the build passes cleanly and all comments are addressed
- Respect CLAUDE.md guidelines for code changes
- If a fix would expand scope significantly, categorize as Defer

## Example Usage

```
/apply-review-fixes 1 tmp/ai/temp/hobby/resume_matcher/analysis/r1/m2.md M2
```

This reads `./tmp/review_code.md`, processes round 1 comments for M2 milestone, applies fixes, runs build until clean, and appends responses to `./tmp/response_code.md`.

```
/apply-review-fixes 2 none M3
```

This processes round 2 with no related analysis document.
