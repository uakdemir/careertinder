## Implement Milestone

Implement a milestone from its analysis document autonomously, following the project's architecture docs and coding guidelines.

### Arguments
- First argument: path to the milestone analysis file (e.g. `tmp/ai/temp/hobby/resume_matcher/analysis/r1/m0.md`)

### Steps

1. Read the analysis file specified in the first argument.

2. Read context files:
   - `CLAUDE.md` (coding guidelines, project conventions)
   - `.claude/hotspots.md` (key file locations)
   - `docs/architecture/components_r1.md` (component specs, data structures)
   - `docs/architecture/adrs.md` (architectural decisions)

3. Create a task list from the deliverables in the analysis document.

4. Implement each deliverable in the order defined in the analysis document:
   - Before writing code for a deliverable, read the relevant component spec (C0-C11) and data structure spec (DS1-DS11) from `components_r1.md`.
   - Follow all coding guidelines in `CLAUDE.md`.
   - Do not implement anything marked "Out of Scope" or "(Post-MVP)".

5. After each deliverable, verify:
   ```
   ruff check .
   mypy . --ignore-missing-imports
   pytest -v
   ```
   If any fail, fix the issue before moving to the next deliverable.

6. Create focused tests per the analysis doc's test plan. Tests must be deterministic, use in-memory SQLite, and require no external services or API keys.

7. When all deliverables are done, run a final verification:
   ```
   ruff check .
   mypy . --ignore-missing-imports
   pytest -v
   ```
   Report the results.

8. Do not commit. The user will review and commit manually.
