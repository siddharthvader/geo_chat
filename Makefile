.PHONY: setup-web setup-api run-api run-web ingest-fetch ingest-parse ingest-index eval

setup-web:
	npm install

setup-api:
	python3 -m venv .venv
	. .venv/bin/activate && pip install -r apps/api/requirements.txt

run-api:
	. .venv/bin/activate && cd apps/api && uvicorn app.main:app --reload --port 8000

run-web:
	npm run dev:web:npm

ingest-fetch:
	. .venv/bin/activate && python scripts/ingest/fetch_sources.py

ingest-parse:
	. .venv/bin/activate && python scripts/ingest/parse_sources.py

ingest-index:
	. .venv/bin/activate && python scripts/ingest/chunk_embed_index.py

eval:
	. .venv/bin/activate && python scripts/eval/run_eval.py
