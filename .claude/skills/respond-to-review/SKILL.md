---
name: respond-to-review
description: Respond to an analysis document review by categorizing each comment, applying accepted edits to source documents, and writing a structured response. Use when processing review feedback on analysis/spec documents.
---

# Respond to Review

Respond to an analysis document review. For each accepted item, apply the surgical edit to the source document(s) AND write a response entry.

## Arguments

- First argument: `[ROUND_NUMBER]` — review round number (e.g., `1`, `2`, `3`)
- Second argument: `[ANALYSIS_FILE]` — milestone analysis document to edit (e.g., `tmp/ai/temp/hobby/resume_matcher/analysis/r1/m2.md`)
- Third argument: `[ARCH_FILE]` — architecture document to edit (e.g., `docs/architecture/components_r1.md`)

## Fixed Files (Constants)

- Review input: `./tmp/review_analysis.md`
- Response output: `./tmp/response_analysis.md`

## Workflow

1. Read `./tmp/review_analysis.md`.

2. For each comment, categorize as one of:
   - **Applied** — valid fix, make the edit
   - **Pushed back** — conflicts with CLAUDE.md rules, ADRs, or is debatable
   - **Deferred** — out of scope, belongs in a later milestone
   - **Needs clarification** — cannot categorize without more information

3. **If Applied:** Make the surgical edit to `[ANALYSIS_FILE]` and/or `[ARCH_FILE]` as described by the review item. Keep changes minimal per CLAUDE.md guideline 14.

4. APPEND (do not overwrite) to `./tmp/response_analysis.md` under this header:

```markdown
## Round [ROUND_NUMBER]

### [ID] — [COMMENT_TITLE or short quote from review]
**Status:** Applied | Pushed back | Deferred | Needs clarification

**[If Applied]**
Change: what was changed and where — file:section or file:line

**[If Pushed back]**
Reason: cite CLAUDE.md rule number, ADR reference, or architectural principle.
Be direct. If the reviewer is correct but out of scope, say so.

**[If Deferred]**
Reason: why this belongs in a later milestone or is low priority
Suggested timing: milestone or trigger (e.g. "M3 calibration phase")

**[If Needs clarification]**
Question: what needs to be answered before this can be categorized

---
```

5. Print a summary: `Applied: X | Pushed back: Y | Deferred: Z | Needs clarification: W`

## Rules for Categorization

- Respect CLAUDE.md guideline 14: do not accept grammatical/punctuation-only changes on analysis documents unless they change meaning
- Respect CLAUDE.md guideline 9: refactor nearby smells only if it reduces complexity without expanding scope
- Do not accept scope expansions without flagging them as deferred

## Example Usage

```
/respond-to-review 1 tmp/ai/temp/hobby/resume_matcher/analysis/r1/m2.md docs/architecture/components_r1.md
```

This reads `./tmp/review_analysis.md`, processes round 1 comments, edits the M2 analysis and components doc as needed, and appends responses to `./tmp/response_analysis.md`.
