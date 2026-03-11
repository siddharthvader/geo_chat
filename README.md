# BuildingTalk

3D landmark viewer + grounded chat with citations and camera hotspot actions.

## Monorepo layout

```txt
buildingtalk/
  apps/
    web/                 # Next.js + React + R3F viewer/chat UI
    api/                 # FastAPI chat/hotspots backend
  packages/
    shared/              # shared TypeScript contracts
  data/
    sources/             # raw source files + manifest
    processed/           # parsed source JSON
    hotspots/            # handcrafted hotspot registry
    models/              # source GLB assets
    evals/               # eval questions + reports
  infra/
    db/
      init.sql           # pgvector schema + indexes
  scripts/
    ingest/
    eval/
    model/
    hotspots/
  docker-compose.yml
```

## Prerequisites

- Node 20+ (npm 10+)
- Python 3.9+
- Optional: Docker (for Postgres + pgvector)
- Optional: OpenAI/OpenRouter API key (for full LLM answers)

## Quick local run (no Docker required)

This mode works without Postgres and falls back to keyword retrieval from `data/processed`.

1. Install web deps:

```bash
npm install
```

2. Setup Python env:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt
```

3. Configure env files:

```bash
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local
```

Optional frontend tuning:

- `NEXT_PUBLIC_CHAT_TIMEOUT_MS=25000`
- `NEXT_PUBLIC_ANALYTICS_DEBUG=false`

4. Ensure model files exist:

```bash
mkdir -p apps/web/public/models
cp palace.glb apps/web/public/models/palace.glb
```

5. Start API:

```bash
source .venv/bin/activate
cd apps/api
uvicorn app.main:app --reload --port 8000
```

6. Start web (new terminal):

```bash
npm run dev:web:npm
```

7. Open:

- `http://localhost:3000`

## Full RAG mode (Postgres + pgvector)

1. Start Postgres:

```bash
docker-compose up -d db
```

2. Set DB + model keys in `apps/api/.env`:

- `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/buildingtalk`
- `OPENAI_API_KEY` (or `OPENROUTER_API_KEY` + `LLM_PROVIDER=openrouter`)
- `LLM_MODEL`
- `EMBED_MODEL`
- `BUILDINGS_FILE=data/buildings/buildings.json`

3. Ingest sources:

```bash
source .venv/bin/activate
python scripts/ingest/fetch_sources.py
python scripts/ingest/parse_sources.py
python scripts/ingest/chunk_embed_index.py
```

If you want to repopulate `data/processed` quickly with a curated Palace-specific corpus (Wikipedia, Wikidata, NPS, SF city pages, LOC), run:

```bash
source .venv/bin/activate
python scripts/ingest/populate_palace_processed.py
```

4. Run API + web as above.

## Buildings registry

- Building metadata is in `data/buildings/buildings.json`
- Each building points to a hotspots file in `data/hotspots/*.json`
- API endpoint: `GET /buildings`

## Eval harness

With API running:

```bash
source .venv/bin/activate
python scripts/eval/run_eval.py
```

Output: `data/evals/report.md`

`data/evals/questions.json` supports optional `building_id` per case.

## Optional make commands

```bash
make setup-web
make setup-api
make run-api
make run-web
make ingest-fetch
make ingest-parse
make ingest-index
make eval
```

## Demo script (5 questions)

1. `What are the weeping ladies?`
2. `Why does this structure look like a ruin?`
3. `When was the Palace reconstructed?`
4. `What details show classical Corinthian influence?`
5. `What is the role of the lagoon axis in the composition?`

## Production notes

- The chat API now enforces grounded citations:
  - If no grounded citation is available, response falls back to: `I don’t have enough in the provided sources to answer confidently.`
- Camera fly-to only runs when hotspot confidence is high.
- For public demos, use an always-on API plan to avoid cold-start latency.
- Model attribution is shown in the UI footer (Sketchfab source + license).
- Debug controls are hidden by default and only enabled when opening the app with `?debug=1`.

## Key files

- `data/hotspots/palace_hotspots.json`
- `data/buildings/buildings.json`
- `apps/api/app/api/routes.py`
- `apps/api/app/services/llm.py`
- `apps/api/app/services/retrieval.py`
- `apps/web/src/components/BuildingViewer.tsx`
- `apps/web/src/app/page.tsx`
- `scripts/ingest/chunk_embed_index.py`
- `scripts/eval/run_eval.py`
