## Backend

FastAPI backend for the Agentic RAG Template. It serves search, file upload, auth, billing, and agentic chat endpoints over a configurable document corpus.

## Local Quickstart

### Demo mode: no Supabase required

Use this path for a local interview demo. It requires only `OPENAI_API_KEY` for agentic chat; search and uploads work with local BM25 and local files.

From the repo root:

```bash
cp backend/.env.demo .env
# edit .env and set OPENAI_API_KEY=sk-...

python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Expected local demo settings:

```env
DEMO_MODE=true
AUTH_DISABLED=true
SEARCH_BACKEND=bm25
CORPUS_PATH=data/static_corpus
SUPABASE_URL=
SUPABASE_SECRET_KEY=
STRIPE_SECRET_KEY=
S3_BUCKET=
```

Start the frontend in a second terminal:

```bash
cd frontend
npm install
npm run dev -- --mode demo
```

Demo mode returns a fixed user (`demo@example.com`) from `get_current_user`, exposes the default corpus space plus `demo@example.com/personal`, and keeps Supabase/Stripe code present but inactive.

### Standard local setup

Create a virtualenv from the repo root and install dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
```

Create local environment settings:

```bash
cp backend/.env.example .env
```

For the simplest local path, keep:

```env
SEARCH_BACKEND=bm25
CORPUS_PATH=data/static_corpus
```

Run the API:

```bash
.venv/bin/uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

## Domain Config

Template-level defaults live in `backend/config/domain_config.yaml`:

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

Environment variables can still override runtime settings such as `SEARCH_BACKEND`, `OPENSEARCH_HOSTS`, and `OPENAI_CHAT_MODEL`.

## Search Backends

### BM25

BM25 is the easiest local backend. It loads `data/static_corpus/corpus.jsonl` into memory and supports uploaded text files through the same search interface.

### OpenSearch

Use OpenSearch when you want a persistent/scalable retrieval backend:

```env
SEARCH_BACKEND=opensearch
OPENSEARCH_HOSTS=http://localhost:9200
OPENSEARCH_VERIFY_CERTS=false
OPENSEARCH_INDEX_PREFIX=rag-template
```

For managed OpenSearch or OpenSearch Serverless, also configure credentials, TLS, and SigV4 options as needed:

```env
OPENSEARCH_USERNAME=
OPENSEARCH_PASSWORD=
OPENSEARCH_CA_CERT=
OPENSEARCH_SIGV4=false
OPENSEARCH_AWS_REGION=
OPENSEARCH_AWS_SERVICE=aoss
```

## Optional Integrations

OpenAI is required for agentic chat:

```env
OPENAI_API_KEY=
OPENAI_CHAT_MODEL=gpt-5-nano
```

## SQL Analytics Tools

Structured CSV datasets can be loaded into DuckDB and queried by the chat agent when `TOOL_SQL=true`.

```env
TOOL_SQL=true
TOOL_CHARTS=true
ANALYTICS_DATA_DIR=data/analytics
ANALYTICS_DB_PATH=data/analytics/analytics.duckdb
ANALYTICS_METRIC_CONFIG=backend/config/rappi_metrics.yaml
```

Supported CSV layouts:

- Metrics: `COUNTRY, CITY, ZONE, ZONE_TYPE, ZONE_PRIORITIZATION, METRIC, L8W_VALUE ... L0W_VALUE`
- Orders: `COUNTRY, CITY, ZONE, METRIC, L8W ... L0W`

The loader writes long-form tables into DuckDB:

- `metrics_long(country, city, zone, zone_type, zone_prioritization, metric, week, value)`
- `orders_long(country, city, zone, metric, week, orders)`

CSV files uploaded through `/upload` are saved as before; recognized analytics CSVs are also appended to the configured DuckDB database.

The upload endpoint also accepts one `.xlsx` or `.xlsm` workbook at a time. Each worksheet is converted to a separate generated `.csv` file in the selected upload space, then each generated CSV is passed through the same analytics loader. Upload either multiple CSV files or one Excel workbook; mixing Excel with other files in one request is rejected.

After CSV/XLSX data is loaded, users can ask the chat for a Markdown executive report, for example:

```text
Give me the executive report for the data
```

The chat endpoint detects this request and returns the deterministic DuckDB report from `generate_executive_report()` directly, covering anomalies, trends, benchmarking, correlations, and opportunities across all currently loaded analytics rows.

To load a local directory manually:

```bash
python -c "from backend.app.services.analytics import load_csv_directory; print(load_csv_directory('data/analytics/input'))"
```

Analytics tools available to the LLM:

- `describe_schema` for tables, columns, metrics, dimensions, week labels, and metric descriptions.
- `preview_table` for sample rows from safe known tables.
- `validate_metric_name` for exact/fuzzy metric mapping.
- `run_sql` for safe read-only SELECT queries with row limits and numeric summaries.
- `generate_chart` for Plotly-compatible line, bar, and scatter specs.
- `generate_executive_report` for deterministic anomalies, trends, benchmarking, correlations, and opportunities.

Example Rappi-style questions:

- "¿Cuáles son las 5 zonas con mayor Lead Penetration esta semana?"
- "Compara Perfect Orders entre zonas Wealthy y Non Wealthy en México"
- "Muestra la evolución de Gross Profit UE en Chapinero las últimas 8 semanas"
- "¿Cuál es el promedio de Lead Penetration por país?"
- "¿Qué zonas tienen alto Lead Penetration pero bajo Perfect Orders?"
- "¿Cuáles son las zonas que más crecen en órdenes en las últimas 5 semanas y qué podría explicar el crecimiento?"

Supabase and Stripe are optional unless you use authenticated app flows and billing:

```env
SUPABASE_URL=
SUPABASE_SECRET_KEY= # backend-only sb_secret_... key
SUPABASE_JWKS_URL= # optional; defaults to ${SUPABASE_URL}/auth/v1/.well-known/jwks.json

STRIPE_SECRET_KEY=
BILLING_RETURN_URL=http://localhost:5173/settings/billing
FRONTEND_BASE_URL=http://localhost:5173
```

## Tests

Run the focused backend suite with BM25:

```bash
env SEARCH_BACKEND=bm25 .venv/bin/python -m pytest -q backend/tests/test_auth.py backend/tests/test_search_chat_files.py
```

Run SQL analytics tests:

```bash
.venv/bin/python -m pytest -q backend/tests/test_analytics.py
```

Run the same suite against OpenSearch after starting a local OpenSearch service:

```bash
env SEARCH_BACKEND=opensearch .venv/bin/python -m pytest -q backend/tests/test_auth.py backend/tests/test_search_chat_files.py
```
