## Analyze Milestone

Create a detailed analysis document for a milestone, producing an implementation-ready specification that follows the exact structure established in the M0 analysis.

### Arguments
- First argument: milestone identifier (e.g. `M1`, `M2`)
- Second argument: release number (e.g. `r1`, `r2`)

### Steps

1. Parse arguments: let `MILESTONE` = first argument (e.g. `M1`), `RELEASE` = second argument (e.g. `r1`), `MILESTONE_LOWER` = lowercase of first argument (e.g. `m1`).

2. Read ALL context files in order:
   - `CLAUDE.md`
   - `.claude/hotspots.md`
   - `docs/architecture/components_{RELEASE}.md` (component specs C0-C11, data structures DS1-DS11, interaction diagram)
   - `docs/architecture/adrs.md` (all architectural decision records)
   - `docs/project_management/{RELEASE}/release_roadmap.md` (milestone definitions, task lists, acceptance criteria)
   - `tmp/ai/temp/hobby/resume_matcher/analysis/{RELEASE}/user_stories.md` (user stories, priority matrix, dependencies)

3. Read any previously completed milestone analysis documents in `tmp/ai/temp/hobby/resume_matcher/analysis/{RELEASE}/` to understand what has already been built, conventions established, and open questions resolved or deferred.

4. Produce the analysis document following this exact section structure (use `m0.md` as the formatting reference):

   **Header block:**
   ```
   # MX — [Name]: Detailed Analysis
   > Milestone, Complexity, Est. Duration, Depends on, Blocks
   ```

   **Required sections (in order):**
   - **1. Objective** — bulleted checklist of verifiable end-states (not tasks)
   - **2. Deliverables** — table: `#` | `Deliverable` | `Components Touched` | `Acceptance Test`. Use D-numbering (D1, D2, ...). Reference C0-C11 and DS1-DS11.
   - **3. Folder Structure** — code block tree of new/modified files, with `### Decisions & Rationale` subsection
   - **4 through N. Detailed Specification: Dx — [Name]** — one section per deliverable, each containing:
     - Overview (2-3 sentences)
     - Design (class/function signatures as Python code blocks with type hints, config schemas, data flows, algorithms, integration points with prior milestones)
     - Key Design Decisions (bullet list, cite ADRs)
     - Edge Cases (table: `Scenario` | `Behavior`)
     - Test Plan (specific test cases with expected outcomes)
   - **N+1. Implementation Order** — dependency-ordered numbered list with deliverable tags
   - **N+2. Open Questions & Decisions Needed** — table: `#` | `Question` | `Options` | `Recommendation`
   - **N+3. Risk Assessment** — table: `Risk` | `Impact` | `Likelihood` | `Mitigation`
   - **N+4. Acceptance Criteria** — numbered list with bold labels, expanded from roadmap
   - **N+5. Out of Scope** — table: `Item` | `Why deferred` | `Milestone`

5. Before writing, verify the quality checklist:
   - Every deliverable traces to at least one component (C0-C11) or data structure (DS1-DS11)
   - Every deliverable traces to at least one user story (US-X.Y)
   - All roadmap task list items for this milestone are covered
   - Post-MVP items are in "Out of Scope", not in deliverables
   - All class/function signatures include type hints
   - Edge cases cover error conditions, not just happy paths
   - Implementation order respects dependencies
   - No deliverable duplicates infrastructure from prior milestones
   - Integration points with prior milestones are explicit

6. Write the document to `tmp/ai/temp/hobby/resume_matcher/analysis/{RELEASE}/{MILESTONE_LOWER}.md`.

### Specification Guidelines

- **Be concrete**: provide actual class names, method signatures, parameter types, return types — not vague descriptions.
- **Reference the architecture**: trace every component, data structure, and design choice back to `components_{RELEASE}.md`, `adrs.md`, or `user_stories.md`.
- **Respect scope**: only specify in-scope items per the roadmap. Note `*(Post-MVP)*` items as out-of-scope.
- **Build on prior milestones**: reuse existing infrastructure (config loader, DB session, logging, models). Do not re-specify what exists.
- **Show integration**: explain which existing functions, models, and config sections this milestone's code connects to.

### Style Rules

- Match `m0.md` formatting exactly (heading levels, tables, code blocks, blockquotes).
- Keep prose concise — prefer tables and code blocks over paragraphs.
- Use consistent references: `C0` not "config manager", `DS9` not "scraper run table".
- No commentary or meta-discussion — the document is the specification.
- Do not modify any existing architecture documents.
