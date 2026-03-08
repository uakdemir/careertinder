.PHONY: dashboard db migrate scrape filter evaluate evaluate-dry lint test check

# ── Application ──────────────────────────────────────────────
dashboard:
	.venv/bin/streamlit run jobhunter/dashboard/app.py

db:
	.venv/bin/python run.py init-db

migrate: db

scrape:
	.venv/bin/python run.py scrape

filter:
	.venv/bin/python run.py filter

evaluate:
	.venv/bin/python run.py evaluate

evaluate-dry:
	.venv/bin/python run.py evaluate --dry-run

ingest:
	.venv/bin/python run.py ingest-resumes

# ── Development ──────────────────────────────────────────────
lint:
	.venv/bin/python -m ruff check .

typecheck:
	.venv/bin/python -m mypy . --ignore-missing-imports

test:
	.venv/bin/python -m pytest -v

check: lint typecheck test
