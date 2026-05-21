# Rappi RAG

Full-stack retrieval-augmented generation app for local document search, uploads, and agentic chat. This repo is configured for an interview/demo hand-in: reviewers can run it locally with only an OpenAI API key.

The production-oriented integrations are still present, but optional. Supabase, Stripe, OpenSearch, S3, and hosted infrastructure are not required for the local demo path.
There is a corpus.jsonl in the data/ directory with sample documents. For this review, the corpus.jsonl can be ignored, since the .xlsx file has to be uploaded manually. 

## Quickstart: Local Demo

Prerequisites:

- Python 3.10+; Python 3.12 works.
- Node.js 20+ recommended for the frontend. Node 18 may run tests with warnings because some dependencies declare Node 20 engines.
- An OpenAI API key.

From the repo root:

```bash
cp backend/.env.demo .env
```

Edit `.env` and set:

```env
OPENAI_API_KEY=sk-...
```

Create a virtualenv and install backend dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements.txt
```

Run the backend:

```bash
.venv/bin/uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

In a second terminal, run the frontend:

```bash
cd frontend
npm install
npm run dev -- --mode demo
```

Open:

```text
http://localhost:5173
```

In demo mode:

- Auth is disabled and the backend returns a fixed local user, `demo@example.com`.
- Search uses local BM25 over `data/static_corpus/corpus.jsonl`.
- Uploads are stored on the local filesystem. You can upload CSV files directly, or one `.xlsx` workbook whose worksheets are converted into separate CSV files internally.
- After uploading analytics data, ask the chat: `Give me the executive report for the data`. The response is generated as Markdown from the loaded DuckDB analytics tables.
- Chat history is stored in browser `localStorage`.
- Billing/Stripe flows are disabled.
- Supabase, OpenSearch, S3, and Stripe env vars can stay blank.

The frontend also falls back to demo mode automatically when Supabase frontend env vars are blank, but `npm run dev -- --mode demo` is the clearest command for reviewers.

## How to use the SQL Analytics Feature

1) Go to tab "Subir".
2) Under "Elige espacio" select "personal".
3) Click "eligir archivos".
4) Upload the *xlsx file (Sistema de Análisis Inteligente para Operaciones Rappi - Dummy Data (2) (1) (3) (1) (1) (1) (1) (1).xlsx).
5) Then switch back to "Chat" Tab and ask any analytical question, for example:
- Preguntas de filtrado: "¿Cuáles son las 5 zonas con mayor % Lead Penetration esta semana?" 
- Comparaciones: "Compara el Perfect Order entre zonas Wealthy y Non Wealthy en México" 
- Tendencias temporales: "Muestra la evolución de Gross Profit UE en Chapinero últimas 8 semanas" 
- Agregaciones: "¿Cuál es el promedio de Lead Penetration por país?"
- Análisis multivariable: "¿Qué zonas tienen alto Lead Penetration pero bajo Perfect Order?" 
- Preguntas de inferencia: ¿ cuáles son las zonas que más crecen en órdenes en las últimas 5 semanas y que podría explicar el crecimiento? 

## Recommended Demo Env

Backend demo env lives in `backend/.env.demo`. Copy it to repo-root `.env` because the backend settings loader reads `.env` from the current working directory when launched from the repo root.

Important values:

```env
DEMO_MODE=true
AUTH_DISABLED=true
SEARCH_BACKEND=bm25
CORPUS_PATH=data/static_corpus
DATA_UPLOAD=backend/app/api/data/user_uploads
OPENAI_API_KEY=sk-...
```

Frontend demo env lives in `frontend/.env.demo`:

```env
VITE_API_BASE=http://localhost:8000
VITE_DEMO_MODE=true
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
```

## Repo Structure

```text
.
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/     FastAPI route handlers for auth, search, upload, chat, billing
│   │   ├── core/                 settings, security, logging
│   │   ├── models/               backend data models
│   │   ├── prompts/              system prompt for the chat agent
│   │   └── services/             auth, BM25/OpenSearch search, analytics, storage helpers
│   ├── config/                   domain and analytics configuration
│   ├── tests/                    backend pytest suite
│   ├── .env.demo                 local demo backend env template
│   ├── .env.example              general backend env template
│   └── requirements.txt          pinned Python dependencies
├── frontend/
│   ├── src/
│   │   ├── api/                  small frontend API helpers
│   │   ├── components/           shared UI components, chat sidebar, markdown/citation rendering
│   │   ├── context/              auth context
│   │   ├── hooks/                API and space-loading hooks
│   │   ├── lib/                  Supabase client, demo-mode storage, utilities
│   │   ├── routes/               landing, search, uploads, chat, auth pages
│   │   └── test/                 frontend test setup and MSW handlers
│   ├── supabase/migrations/      Supabase schema migrations for production-style auth/history
│   ├── .env.demo                 local demo frontend env template
│   └── package.json              Vite/React scripts and dependencies
├── landing/                      optional standalone marketing/landing Vite app
├── data/
│   ├── static_corpus/            local JSONL corpus used by BM25 demo mode
│   └── analytics/                local DuckDB analytics sample/database
├── Dockerfile.backend            backend container build
└── pytest.ini                    pytest configuration
```

## How The App Fits Together

The backend is a FastAPI API mounted under `/v1`. The most relevant endpoints are:

- `GET /v1/user/spaces`: list spaces available to the current user.
- `POST /v1/user/spaces`: create a local personal space.
- `GET /v1/search`: search documents in a space.
- `POST /v1/upload`: upload files into a space and reindex that space.
- `POST /v1/chat/agentic/stream`: stream an agentic chat response using OpenAI.
- `GET /v1/billing/status`: returns demo status locally; production can use Stripe.

Search is selected by `SEARCH_BACKEND`:

- `bm25`: local in-memory search. This is the recommended demo backend.
- `opensearch`: optional production-style backend if a cluster is configured.

Auth is selected by demo flags:

- `DEMO_MODE=true` or `AUTH_DISABLED=true`: no bearer token required; fixed local user.
- Demo disabled: the backend verifies Supabase JWTs and uses Supabase-backed user/space data.

The frontend is a Vite React app. In demo mode, it skips login, omits Authorization headers, and stores chat sidebar/history data in `localStorage`. When Supabase env vars are provided and demo mode is off, the original Supabase auth/database flow is used.

Upload behavior:

- Multiple `.csv` files can be uploaded together.
- One `.xlsx` or `.xlsm` workbook can be uploaded at a time.
- Each worksheet in the workbook is saved as a separate generated `.csv` file in the selected space.
- Generated CSVs are passed through the same DuckDB analytics loader as direct CSV uploads.

Executive report behavior:

- Ask the chat for an executive report, for example: `Give me the executive report for the data`.
- The backend detects that request and returns a deterministic Markdown report from DuckDB.
- The report includes an executive summary, anomalies, concerning trends, benchmarking, correlations, opportunities, recommendations, and caveats.
- This path does not require a separate file selector; it analyzes all analytics rows currently loaded into DuckDB.

## Testing

Backend focused tests:

```bash
SEARCH_BACKEND=bm25 .venv/bin/python -m pytest -q backend/tests/test_auth.py backend/tests/test_search_chat_files.py
```

All frontend tests:

```bash
cd frontend
npm test
```

Frontend typecheck:

```bash
cd frontend
npm run typecheck
```

The most recent verification for this hand-in passed:

- Backend focused tests: `18 passed`
- Frontend tests: `22 passed`
- Frontend typecheck: passed

## Optional Production Integrations

These are not needed for the local demo:

- Supabase: auth, user profiles, spaces, persisted chat history.
- Stripe: billing portal/status.
- OpenSearch: persistent/scalable retrieval backend.
- S3: hosted corpus/files.
- Hosted runtime: App Runner or similar container deployment.

Use `backend/.env.example` and `frontend/.env.example` as the starting point when enabling those integrations.

## Backend Details

For more backend-specific notes about BM25, OpenSearch, analytics tools, and environment variables, see [backend/README.md](backend/README.md).
