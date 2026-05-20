## Backend search backends

The API can run either entirely in memory using the bundled BM25 index or
delegate search to an external OpenSearch cluster. The backend is selected via
the `SEARCH_BACKEND` environment variable (`bm25` by default).

### Using the in-memory BM25 engine (default)

No additional setup is required; the application will load
`data/static_corpus/corpus.jsonl` at startup and keep all indexes in memory. The
same code path is still used by the test suite.

### Using OpenSearch

1. **Install OpenSearch and create credentials.** Provision an OpenSearch
   domain (self-hosted or managed). Create a user that has permissions to
   create/delete indexes and run bulk indexing operations.
2. **Set environment variables** (e.g. in `.env`):
   ```env
   SEARCH_BACKEND=opensearch
   OPENSEARCH_HOSTS=https://your-cluster.example.com:9200
   OPENSEARCH_USERNAME=your-user
   OPENSEARCH_PASSWORD=your-password
   # optional, but recommended when using HTTPS
   OPENSEARCH_CA_CERT=/path/to/ca.pem
   OPENSEARCH_INDEX_PREFIX=rag-template
   ```
3. **Start the API**. On startup the FastAPI app will synchronise the
   filesystem corpus with OpenSearch by re-creating per-space indexes and
   loading documents through the bulk API.
4. **Uploading new files.** Whenever a user uploads documents the API calls the
   selected backend's `index()` method; for OpenSearch this translates into a
   fresh bulk import for that space.

The OpenSearch backend currently stores documents with a Spanish analyser and
expects the same filesystem layout used by the BM25 implementation. This keeps
feature parity between both modes, enabling a gradual migration to a scalable
search cluster while retaining the local developer experience.

### OpenSearch Serverless (AOSS) on App Runner

You can run staging/prod on AWS OpenSearch Serverless using IAM role auth from App Runner while keeping local OpenSearch for dev.

1. Configure env for Serverless (example for staging):

   ```env
   # Backend selection
   SEARCH_BACKEND=opensearch

   # AOSS + SigV4
   OPENSEARCH_AWS_REGION=us-east-2
   OPENSEARCH_AWS_SERVICE=aoss
   # Use your collection endpoint hostname
   OPENSEARCH_HOSTS=https://<collection-id>.<region>.aoss.amazonaws.com
   OPENSEARCH_VERIFY_CERTS=true
   OPENSEARCH_INDEX_PREFIX=rag-template-stg
   ```

2. App Runner IAM role: attach a task role with permissions allowed by your AOSS data access policy (least-privilege). Typical actions include read/search and indexing on specific collections and indexes. Credentials are sourced automatically by boto3 in App Runner.
3. Networking: Prefer PrivateLink (AOSS VPC endpoint) and attach an App Runner VPC connector to the subnets where the endpoint lives. In your AOSS network access policy, allow the VPC endpoint ID. If you cannot use PrivateLink yet, enable public network access in the policy temporarily.
4. Behavior differences handled in code:
   - No cluster health wait on AOSS.
   - Index aliases/rollover are skipped; a stable index name per space is used instead.
   - Shard/replica counts are not set in Serverless (managed for you).
5. Local dev remains unchanged. Use Docker OpenSearch with:
   ```env
   SEARCH_BACKEND=opensearch
   OPENSEARCH_HOSTS=http://localhost:9200
   OPENSEARCH_VERIFY_CERTS=false
   ```

## Environments and .env files

This backend supports environment-specific configuration files using `APP_ENV`:

- Set the process environment variable `APP_ENV` to one of: `local` (default), `staging`, `production`.
- At startup, settings are loaded from `.env.{APP_ENV}` first (if present), then fall back to `.env`.

Important: Because `APP_ENV` is read before any `.env` files are parsed, you must set `APP_ENV` in the real process environment (systemd, Docker, ECS, etc.), not inside `.env`.

### Recommended files at repo root

- `.env` (for local dev)
- `.env.staging`
- `.env.production`

Example contents for staging/prod when using S3 + OpenSearch:

```env
# Backend selection
SEARCH_BACKEND=opensearch

# S3 corpus and files
S3_BUCKET=rag-template-data
S3_CORPUS_KEY=staging/corpus.jsonl   # or prod/corpus.jsonl
S3_FILES_PREFIX=staging/files/       # or prod/files/
S3_URL_TTL=604800                    # 7 days for presigned URLs

# OpenSearch cluster
OPENSEARCH_HOSTS=https://<EC2-private-ip>:9200
OPENSEARCH_USERNAME=rag_app
OPENSEARCH_PASSWORD=AppUserPwd_!234
OPENSEARCH_VERIFY_CERTS=false
# OPENSEARCH_INDEX_PREFIX=rag-template-stg  # optional: avoid collisions if sharing a cluster
```

For local development, keep your current setup (e.g. OpenSearch in Docker):

```env
# .env
SEARCH_BACKEND=opensearch
OPENSEARCH_HOSTS=http://localhost:9200
ALLOWED_ORIGINS=http://localhost:5173
```

Note: S3 variables are defined in settings and can be used by services to read the corpus and generate presigned file URLs, but the current indexers expect a filesystem corpus. When you’re ready to index directly from S3, wire these variables into your loader to fetch `S3_CORPUS_KEY` and generate file URLs from `S3_FILES_PREFIX`.
