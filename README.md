# Agentic RAG Template

Reusable full-stack RAG chat application with a FastAPI backend and React frontends.

The project is organised as a monorepo:

- `backend/` - FastAPI API that indexes a document corpus and serves search, file and chat endpoints (BM25 or OpenSearch backends).
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

- **Backend:** Python, FastAPI, Uvicorn, OpenSearch or in-memory BM25 (`rank-bm25`), S3 integration via `boto3`.
- **Frontend:** React, Vite, Tailwind CSS, Radix UI, Supabase (auth & database), Vitest + Testing Library.
- **Infra (optional):** OpenSearch / OpenSearch Serverless, S3-style object storage, App Runner or similar container runtime.

## Getting Started

Clone the repo and switch into the project directory:

```bash
git clone <your-fork-or-origin-url>
cd agentic-rag-template
```

### 1. Backend

Create and activate a Python virtualenv (Python 3.10+ recommended), then install dependencies:

```bash
cd backend
pip install -r requirements.txt
```

Set up your environment:

```bash
cp ../env.staging .env   # or create .env manually
```

Run the API with Uvicorn:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
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
