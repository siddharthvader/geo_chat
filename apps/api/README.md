# BuildingTalk API

## Setup (venv + pip)

```bash
python3 -m venv ../../.venv
source ../../.venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run

```bash
source ../../.venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

## Endpoints

- `GET /health`
- `GET /hotspots`
- `POST /chat`
