# Agentic RAG Template

Reusable full-stack RAG chat application with a FastAPI backend and React frontends.

The project is organised as a monorepo:

- `backend/` - FastAPI API that indexes a document corpus and serves search, file, chat, and optional DuckDB analytics endpoints/tools.
- `frontend/` - main React + Vite app (Supabase auth, chat UI, search experience).
- `landing/` - optional marketing/landing site built with React + Vite.
- `data/` - local static corpus used by the default in-memory BM25 backend.

For backend-specific details (BM25 vs OpenSearch, environments, `.env` layout), see [backend/README.md](backend/README.md).

## Domain Config

Generic template defaults live in [backend/config/domain_config.yaml](backend/config/domain_config.yaml):

```yaml
app_name: "Agentic RAG Template"
default_space: "default"
domain: "generic"
language: "es"
retrieval_backend: "opensearch"
tools:
  retrieval: true
  sql: false
  charts: false
```

## Tech Stack

- **Backend:** Python, FastAPI, Uvicorn, DuckDB analytics over CSVs, OpenSearch or in-memory BM25 (`rank-bm25`), S3 integration via `boto3`.
- **Frontend:** React, Vite, Tailwind CSS, Radix UI, Supabase (auth & database), Vitest + Testing Library.
- **Infra (optional):** OpenSearch / OpenSearch Serverless, S3-style object storage, App Runner or similar container runtime.

## Getting Started

Clone the repo and switch into the project directory:

```bash
git clone <your-fork-or-origin-url>
cd agentic-rag-template
```

Copy example env files and fill in provider keys only for the integrations you use:

```bash
cp backend/.env.example .env
cp frontend/.env.example frontend/.env
cp landing/.env.example landing/.env
```

### 1. Backend

Create and activate a Python virtualenv (Python 3.10+ recommended), then install dependencies:

```bash
cd backend
pip install -r requirements.txt
```

Run the API with Uvicorn:

```bash
.venv/bin/uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend App

```bash
cd frontend
npm install
npm run dev
```

The dev server typically runs on `http://localhost:5173`. Ensure the backend CORS `ALLOWED_ORIGINS` includes this origin.

### 3. Landing Site

```bash
cd landing
npm install
npm run dev
```

## Testing

- **Backend tests:** from `backend/`, run `pytest`.
- **Frontend tests:** from `frontend/`, run `npm test`.

## SQL Analytics Over CSVs

The backend can load structured CSV datasets into a local DuckDB file and expose them to the chat agent through tools:

- `describe_schema`
- `preview_table`
- `validate_metric_name`
- `run_sql`
- `generate_chart`
- `generate_executive_report`

Enable the tools with environment variables:

```env
TOOL_SQL=true
TOOL_CHARTS=true
ANALYTICS_DATA_DIR=data/analytics
ANALYTICS_DB_PATH=data/analytics/analytics.duckdb
ANALYTICS_METRIC_CONFIG=backend/config/rappi_metrics.yaml
ANALYTICS_MAX_ROWS=200
ANALYTICS_ANOMALY_THRESHOLD=0.10
```

Install backend dependencies from the repo root or backend directory:

```bash
pip install -r backend/requirements.txt
```

CSV uploads through the existing upload endpoint are still saved and indexed as documents. If a `.csv` matches a known analytics shape, it is also loaded into DuckDB.

Supported generic CSV shapes:

- Metrics input data: `COUNTRY, CITY, ZONE, ZONE_TYPE, ZONE_PRIORITIZATION, METRIC, L8W_VALUE ... L0W_VALUE`
- Orders data: `COUNTRY, CITY, ZONE, METRIC, L8W ... L0W`

These are normalized into:

- `metrics_long(country, city, zone, zone_type, zone_prioritization, metric, week, value)`
- `orders_long(country, city, zone, metric, week, orders)`

You can also build the database from Python:

```bash
python -c "from backend.app.services.analytics import load_csv_directory; print(load_csv_directory('data/analytics/input'))"
```

Run the backend:

```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Run analytics tests:

```bash
python -m pytest -q backend/tests/test_analytics.py
```

Example questions:

- "¿Cuáles son las 5 zonas con mayor Lead Penetration esta semana?"
- "Compara Perfect Orders entre zonas Wealthy y Non Wealthy en México"
- "Muestra la evolución de Gross Profit UE en Chapinero las últimas 8 semanas"
- "¿Cuál es el promedio de Lead Penetration por país?"
- "¿Qué zonas tienen alto Lead Penetration pero bajo Perfect Orders?"
- "¿Cuáles son las zonas que más crecen en órdenes en las últimas 5 semanas y qué podría explicar el crecimiento?"

The included [Rappi-style metric dictionary](backend/config/rappi_metrics.yaml) is an example configuration only; the analytics module itself is generic.
