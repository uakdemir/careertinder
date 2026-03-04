---
name: review-analysis
description: Review a milestone analysis document against architecture specs, ADRs, and prior milestone artifacts to catch implementation risks before coding starts. Use when asked to audit analysis/spec docs for completeness, consistency, ambiguity, scope creep, missing decisions, or hidden technical risk, including follow-up rounds with a prior response file.
---

# Review Analysis

Review a single analysis document as the primary target, but evaluate it against shared context so findings are accurate and non-duplicative with previous rounds.

## Arguments

- First argument: `[ANALYSIS_DOC]` (required) — e.g., `tmp/ai/temp/hobby/resume_matcher/analysis/r1/m2.md`

Fixed files:
- Response input (round > 1): `./tmp/response_analysis.md`
- Review output: `./tmp/review_analysis.md`

## Workflow

1. Read `[ANALYSIS_DOC]`.
2. Read the shared context:
   - `CLAUDE.md` (coding guidelines, project conventions)
   - `docs/architecture/components_r1.md`
   - `docs/architecture/adrs.md`
   - Prior milestones under `tmp/ai/temp/hobby/resume_matcher/analysis/r1/`
3. If `./tmp/response_analysis.md` exists:
   - Read it before producing findings.
   - Do not re-raise pushed-back or deferred items unless there is new concrete evidence.
4. Treat all context and `[ANALYSIS_DOC]` as one unified review set.
5. Review for:
   - `Completeness`: required sections present, acceptance criteria defined, edge cases covered (partial failure, empty data, concurrent requests)
   - `Consistency`: contradictions with ADRs, components spec, or prior milestone docs
   - `Ambiguity`: requirements that allow materially different implementations
   - `Scope Creep`: requirements that exceed milestone goal
   - `Missing Decision`: architecture choices implied but not explicitly made
   - `Risk`: technically underspecified requirements or hidden complexity
6. Do not flag:
   - Grammar or punctuation
   - Stylistic formatting preferences
   - Hypothetical future requirements outside scope
7. Group findings by file and section path, assign stable IDs (`ID-001`, `ID-002`, ...), and priority (`P0`, `P1`, `P2`).
8. Use the exact output template below.
9. Write the exact review output to `./tmp/review_analysis.md`.

## Output Template (Use Exactly)

---

## By file

### [ANALYSIS_DOC] - <Section name or overall>
- [P0][ID-001] <Issue title>
  - Type: Completeness | Consistency | Ambiguity | Scope Creep | Missing Decision | Risk
  - Evidence: <quote a short excerpt or refer to section heading>
  - Fix: <specific suggestion - exact wording or minimal diff-style instruction>

- [P1][ID-002] <Issue title>
  - Type: ...
  - Evidence: ...
  - Fix: ...

### <related file if applicable, e.g. docs/architecture/components_r1.md>
- [P1][ID-003] ...

## Unknown / cross-cutting
- [P?][ID-NNN] <item that spans sections or cannot be tied to a specific location>

## Top 5 highest impact fixes
1. [ANALYSIS_DOC] [ID-001] - <one-line reason>
2. ...

## Summary
- Blocking issues (must resolve before implementation): X
- Important issues (should resolve): Y
- Minor issues (can address during implementation): Z
- Overall assessment: Ready for implementation | Needs revision | Major revision required

---

## Priority Definitions

- `P0` - blocking: must resolve before implementation starts
- `P1` - important: should resolve, risk if deferred
- `P2` - minor: low urgency, can address inline during implementation
