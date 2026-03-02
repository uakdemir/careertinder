## Apply Review Fixes

Apply all fixes from a review file autonomously, iterate until build is clean, and write a response file with outcomes and any pushbacks.

### Arguments
- First argument: path to the review file (default: `tmp/review.md`)
- Second argument: path to the response file (default: `tmp/response.md`)

### Steps

1. Read the review file specified (or `tmp/review.md` if not given).

2. For each comment/issue in the review file, categorize it as:
   - **Apply** — valid, actionable fix
   - **Pushback** — debatable or conflicts with CLAUDE.md / architecture decisions
   - **Defer** — out of scope, post-milestone, or cosmetic-only

3. For all **Apply** items: create parallel sub-tasks per review category, each applying its fixes independently using `isolation: "worktree"` where files don't conflict.

4. After all fixes are applied, run:
   ```
   ruff check .
   mypy . --ignore-missing-imports
   pytest -x -q
   ```

5. If lint, type-check, or test errors occur: analyze the error output, apply corrections, re-run. Do not stop until all three pass with zero errors.

6. Write the response file (default: `tmp/response.md`) with one section per review comment:
   - **Applied** — what was changed and where (file:line)
   - **Pushed back** — reasoning (cite CLAUDE.md rule number or ADR if applicable)
   - **Deferred** — why and suggested milestone

7. Print a summary: total comments, applied/pushed-back/deferred counts, build status.
