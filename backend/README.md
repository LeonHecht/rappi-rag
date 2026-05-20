## Backend

FastAPI backend for the Agentic RAG Template. It serves search, file upload, auth, billing, and agentic chat endpoints over a configurable document corpus.

## Local Quickstart

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

Supabase and Stripe are optional unless you use authenticated app flows and billing:

```env
SUPABASE_URL=
SUPABASE_KEY=
SUPABASE_JWKS_URL=
SUPABASE_JWT_SECRET=

STRIPE_SECRET_KEY=
BILLING_RETURN_URL=http://localhost:5173/settings/billing
FRONTEND_BASE_URL=http://localhost:5173
```

## Tests

Run the focused backend suite with BM25:

```bash
env SEARCH_BACKEND=bm25 .venv/bin/python -m pytest -q backend/tests/test_auth.py backend/tests/test_search_chat_files.py
```

Run the same suite against OpenSearch after starting a local OpenSearch service:

```bash
env SEARCH_BACKEND=opensearch .venv/bin/python -m pytest -q backend/tests/test_auth.py backend/tests/test_search_chat_files.py
```
