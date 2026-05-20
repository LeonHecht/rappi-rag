"""OpenSearch-backed search service.

This module mirrors the interface of :mod:`backend.app.services.bm25`
so the rest of the application can switch between backends depending on
``settings.SEARCH_BACKEND``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from opensearchpy import OpenSearch, helpers
from opensearchpy import AWSV4SignerAuth, RequestsHttpConnection
from opensearchpy.exceptions import NotFoundError

# Optional S3 support (used when S3_* settings are configured)
try:  # lazy optional dependency
    import boto3  # type: ignore
    from botocore.exceptions import ClientError  # type: ignore
except Exception:  # pragma: no cover - optional
    boto3 = None
    ClientError = Exception

from ..core.config import settings


class OpenSearchSearch:
    def __init__(self) -> None:
        self._client: OpenSearch | None = None
        self._s3_client = None

    # ------------------------------------------------------------------
    # Client helpers
    # ------------------------------------------------------------------
    def _build_hosts(self) -> tuple[list[dict[str, Any]], bool | None]:
        hosts: list[dict[str, Any]] = []
        use_ssl: bool | None = None

        raw_hosts = [h.strip() for h in settings.OPENSEARCH_HOSTS.split(",") if h.strip()]
        if not raw_hosts:
            raise RuntimeError("OPENSEARCH_HOSTS is empty; cannot initialize OpenSearch client.")

        for raw in raw_hosts:
            if raw.startswith("http://") or raw.startswith("https://"):
                parsed = urlparse(raw)
                scheme = parsed.scheme or "http"
                host = parsed.hostname or "localhost"
                if parsed.port:
                    port = parsed.port
                else:
                    port = 443 if scheme == "https" else 80
                hosts.append({"host": host, "port": port})
                if use_ssl is None:
                    use_ssl = scheme == "https"
            else:
                if ":" in raw:
                    host_part, port_part = raw.split(":", 1)
                    try:
                        port = int(port_part)
                    except ValueError:
                        port = 9200
                    hosts.append({"host": host_part, "port": port})
                else:
                    hosts.append({"host": raw, "port": 9200})
        return hosts, use_ssl
    
    def _get_client(self) -> OpenSearch:
        if self._client is None:
            hosts, use_ssl = self._build_hosts()

            client_kwargs: dict[str, Any] = {
                "hosts": hosts,
                "http_compress": True,
                "timeout": settings.OPENSEARCH_TIMEOUT,
                "verify_certs": settings.OPENSEARCH_VERIFY_CERTS,
            }

            aws_region = getattr(settings, "OPENSEARCH_AWS_REGION", None)

            # --- Branch 1: AWS (Managed / Serverless via IAM + SigV4) ---
            if aws_region:
                if boto3 is None:
                    raise RuntimeError(
                        "boto3 is required for AWS OpenSearch IAM auth but is not installed."
                    )

                service = getattr(settings, "OPENSEARCH_AWS_SERVICE", "aoss")

                session = boto3.Session()
                credentials = session.get_credentials()
                if credentials is None:
                    raise RuntimeError("No AWS credentials available for OpenSearch IAM auth.")

                auth = AWSV4SignerAuth(credentials, aws_region, service)

                client_kwargs.update(
                    {
                        "http_auth": auth,
                        "use_ssl": True,
                        "verify_certs": True,
                        "connection_class": RequestsHttpConnection,
                    }
                )

            # --- Branch 2: Local / non-AWS clusters (dev) ---
            else:
                auth = None
                if settings.OPENSEARCH_USERNAME and settings.OPENSEARCH_PASSWORD:
                    auth = (settings.OPENSEARCH_USERNAME, settings.OPENSEARCH_PASSWORD)

                if auth:
                    client_kwargs["http_auth"] = auth

                if use_ssl is not None:
                    client_kwargs["use_ssl"] = use_ssl
                if settings.OPENSEARCH_CA_CERT:
                    client_kwargs["ca_certs"] = settings.OPENSEARCH_CA_CERT

            self._client = OpenSearch(**client_kwargs)

        return self._client

    # ------------------------------------------------------------------
    # Index helpers
    # ------------------------------------------------------------------
    def _index_name(self, space: str) -> str:
        safe = space.replace("/", "__").replace(" ", "_").lower()
        safe = re.sub(r"[^a-z0-9_\-]+", "-", safe)
        return f"{settings.OPENSEARCH_INDEX_PREFIX}-{safe}"
    
    def _create_index_if_needed(self, client: OpenSearch, index_name: str) -> None:
        if client.indices.exists(index=index_name):
            return

        # Base index settings, used for both local and AOSS
        index_settings: dict[str, Any] = {}
        service = getattr(settings, "OPENSEARCH_AWS_SERVICE", "aoss")

        # Only set shards/replicas when NOT on Serverless
        if service != "aoss":
            index_settings.update(
                {
                    "number_of_shards": 1,
                    "number_of_replicas": 1,
                }
            )

        body = {
            "settings": {
                "index": index_settings,
                "analysis": {
                    "analyzer": {
                        "spanish_default": {
                            "type": "standard",
                            "stopwords": "_spanish_",
                        }
                    }
                },
            },
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "title": {
                        "type": "text",
                        "analyzer": "spanish_default",
                        "fields": {"raw": {"type": "keyword"}},
                    },
                    "text": {
                        "type": "text",
                        "analyzer": "spanish_default",
                    },
                    "space": {"type": "keyword"},
                    "download_url": {"type": "keyword"},
                }
            },
        }

        client.indices.create(index=index_name, body=body)

    def _resolve_download_url(self, doc_id: str) -> str | None:
        # Prefer S3 presigned URL if configured and presigning during indexing is enabled
        if (
            getattr(settings, "S3_BUCKET", None)
            and getattr(settings, "S3_FILES_PREFIX", None)
            and getattr(settings, "S3_PRESIGN_ON_INDEX", False)
        ):
            url = self._presign_by_id(doc_id)
            if url:
                return url

        # Filesystem fallback (dev/local)
        files_root = Path(settings.CORPUS_PATH) / "files"
        for ext in (".pdf", ".PDF", ".htm", ".html", ".HTML", ".docx", ".doc", ".txt"):
            candidate = files_root / f"{doc_id}{ext}"
            if candidate.exists():
                return f"/files/{candidate.name}"
        return None

    def _presign_by_id(self, doc_id: str) -> str | None:
        """Attempt to generate a presigned S3 URL for a given document id.
        Tries a set of known extensions and returns the first existing object's URL.
        """
        if boto3 is None:
            return None
        bucket = getattr(settings, "S3_BUCKET", None)
        prefix_raw = getattr(settings, "S3_FILES_PREFIX", None)
        if not bucket or not prefix_raw:
            return None
        try:
            client = self._get_s3_client()
            prefix = str(prefix_raw).rstrip("/") + "/"
            for ext in (".pdf", ".PDF", ".htm", ".html", ".HTML", ".docx", ".doc", ".txt"):
                key = f"{prefix}{doc_id}{ext}"
                try:
                    client.head_object(Bucket=bucket, Key=key)
                except ClientError:
                    continue
                try:
                    return client.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": bucket, "Key": key},
                        ExpiresIn=int(getattr(settings, "S3_URL_TTL", 604800)),
                    )
                except Exception:
                    return None
        except Exception:
            return None
        return None

    def _load_documents(self, space: str) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []

        if space == settings.DEFAULT_SPACE:
            # Try S3 first if configured
            if getattr(settings, "S3_BUCKET", None) and getattr(settings, "S3_CORPUS_KEY", None) and boto3 is not None:
                try:
                    client = self._get_s3_client()
                    obj = client.get_object(Bucket=settings.S3_BUCKET, Key=settings.S3_CORPUS_KEY)
                    body = obj["Body"]
                    # Iterate lines to avoid loading whole file into memory
                    for raw in body.iter_lines():
                        if not raw:
                            continue
                        try:
                            line = raw.decode("utf-8")
                            rec = json.loads(line)
                        except Exception:
                            continue
                        doc_id = rec.get("id") or rec.get("doc_id")
                        if not doc_id:
                            continue
                        title = rec.get("title", "")
                        text = rec.get("text", "")
                        documents.append({
                            "id": doc_id,
                            "title": title,
                            "text": text,
                            "space": space,
                            "download_url": self._resolve_download_url(doc_id),
                        })
                except Exception as e:
                    print(f"[OpenSearch] Failed to load corpus from S3: {e}. Falling back to filesystem.")

            # Filesystem fallback or if S3 not configured
            if not documents:
                jsonl_file = Path(settings.CORPUS_PATH) / "corpus.jsonl"
                if not jsonl_file.exists():
                    print(f"[OpenSearch] corpus.jsonl not found for space '{space}'.")
                    return []
                with jsonl_file.open(encoding="utf-8") as fh:
                    for line in fh:
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        doc_id = obj.get("id") or obj.get("doc_id")
                        if not doc_id:
                            continue
                        title = obj.get("title", "")
                        text = obj.get("text", "")
                        documents.append(
                            {
                                "id": doc_id,
                                "title": title,
                                "text": text,
                                "space": space,
                                "download_url": self._resolve_download_url(doc_id),
                            }
                        )
        else:
            dir_path = Path(settings.DATA_UPLOAD) / space
            if not dir_path.exists():
                print(f"[OpenSearch] Upload directory '{dir_path}' missing for space '{space}'.")
                return []
            for file in dir_path.glob("**/*.txt"):
                try:
                    text = file.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    text = file.read_text(encoding="latin-1")
                documents.append(
                    {
                        "id": file.stem,
                        "title": file.stem,
                        "text": text,
                        "space": space,
                        "download_url": None,
                    }
                )

        return documents

    def _alias_name(self, space: str) -> str:
        # stable alias clients will search against
        safe = space.replace("/", "__").replace(" ", "_").lower()
        safe = re.sub(r"[^a-z0-9_\-]+", "-", safe)
        return f"{settings.OPENSEARCH_INDEX_PREFIX}-{safe}"

    def _build_index_name(self, space: str, suffix: str) -> str:
        # concrete index name for a build (timestamp)
        base = self._alias_name(space)
        return f"{base}-{suffix}"

    def _bulk_actions(self, index_name: str, docs: Iterable[dict[str, Any]]):
        for doc in docs:
            yield {
                "_op_type": "index",
                "_index": index_name,
                "_id": doc["id"],
                "_source": doc,
            }

    def _wait_for_cluster(self, timeout=30):
        c = self._get_client()
        import time
        for _ in range(timeout):
            try:
                c.cluster.health(wait_for_status="yellow", request_timeout=5)
                return
            except Exception:
                time.sleep(1)
        raise RuntimeError("OpenSearch not ready")

    # ------------------------------------------------------------------
    # S3 helpers
    # ------------------------------------------------------------------
    def _get_s3_client(self):
        if self._s3_client is None:
            if boto3 is None:
                raise RuntimeError("boto3 is required for S3 operations but is not installed.")
            # Rely on environment/instance role for credentials
            self._s3_client = boto3.client("s3")
        return self._s3_client
    
    def _is_serverless(self):
        return getattr(settings, "OPENSEARCH_AWS_SERVICE", "aoss") == "aoss" and getattr(settings, "OPENSEARCH_AWS_REGION", None)
    
    # ------------------------------------------------------------------
    # Public API (mirrors BM25Search)
    # ------------------------------------------------------------------
    def index(self, space: str | None = None) -> None:
        space = space or settings.DEFAULT_SPACE
        if not self._is_serverless():
            self._wait_for_cluster()
        
        client = self._get_client()
        alias = self._alias_name(space)

        documents = self._load_documents(space)
        if not documents:
            print(f"[OpenSearch] No documents to index for space '{space}'.")
            return

        build_name = (
            alias if self._is_serverless() else self._build_index_name(space, suffix=str(int(__import__("time").time())))
        )

        # create build index (mapping/analyzer same as before)
        self._create_index_if_needed(client, build_name)

        # bulk index into build
        helpers.bulk(
            client,
            self._bulk_actions(build_name, documents),
            chunk_size=settings.OPENSEARCH_BULK_CHUNK_SIZE,
            refresh="wait_for",
            raise_on_error=False,
            raise_on_exception=False,
        )

        if not self._is_serverless():
            # alias swap (atomic)
            actions = []
            if client.indices.exists_alias(name=alias):
                olds = list(client.indices.get_alias(name=alias).keys())
                for o in olds:
                    actions.append({"remove": {"index": o, "alias": alias}})
            actions.append({"add": {"index": build_name, "alias": alias}})
            client.indices.update_aliases(body={"actions": actions})

            # optional: clean up old indices with same prefix (keep last N)
            keep_n = 2
            all_idxs = [i for i in client.indices.get_alias(index=f"{alias}-*").keys()]
            # sort by name (timestamp suffix makes this work)
            for old in sorted(all_idxs)[:-keep_n]:
                if old != build_name:
                    client.indices.delete(index=old, ignore=[404])

            print(f"[OpenSearch] Indexed {len(documents)} docs into alias '{alias}' via '{build_name}'.")
        else:
            print(f"[OpenSearch] Indexed {len(documents)} docs into serverless index '{build_name}'.")

    def has_space(self, space: str) -> bool:
        """Return True if the logical space exists (alias or index)."""
        client = self._get_client()
        alias = self._alias_name(space)
        if client.indices.exists_alias(name=alias):
            return True
        try:
            return bool(client.indices.exists(index=alias))
        except Exception:
            return False

    def search(self, query: str, top_k: int = 30, space: str | None = None) -> list[dict[str, Any]]:
        space = space or settings.DEFAULT_SPACE
        client = self._get_client()
        alias = self._alias_name(space)
        target_index = alias
        if not client.indices.exists_alias(name=alias):
            if not client.indices.exists(index=alias):
                print(f"[OpenSearch] Alias/index '{alias}' missing for space '{space}'.")
                return []

        body = {
            "size": top_k,
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["title^2", "text"],
                    "type": "best_fields",
                }
            },
            "highlight": {
                "fields": {
                    "text": {
                        "fragment_size": 200,
                        "number_of_fragments": 1,
                    }
                }
            },
        }

        response = client.search(index=target_index, body=body)
        hits: list[dict[str, Any]] = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit.get("_source", {})
            snippet = ""
            highlight = hit.get("highlight", {}).get("text")
            if highlight:
                snippet = " … ".join(highlight)
            else:
                text = source.get("text", "")
                snippet = " ".join(text.split()[:50])
            # Lazily presign S3 URLs at query time if missing in index
            dl_url = source.get("download_url")
            if not dl_url and getattr(settings, "S3_PRESIGN_ON_QUERY", True):
                dl_url = self._presign_by_id(source.get("id") or hit.get("_id"))
            hits.append(
                {
                    "id": source.get("id") or hit.get("_id"),
                    "title": source.get("title", ""),
                    "score": float(hit.get("_score") or 0.0),
                    "snippet": snippet,
                    "download_url": dl_url,
                }
            )
        return hits

    def get_document_by_id(self, space: str, doc_id: str) -> dict[str, Any] | None:
        client = self._get_client()
        alias = self._alias_name(space)
        try:
            doc = client.get(index=alias, id=doc_id)
        except NotFoundError:
            return None

        source = doc.get("_source", {})
        dl_url = source.get("download_url")
        if not dl_url and getattr(settings, "S3_PRESIGN_ON_QUERY", True):
            dl_url = self._presign_by_id(doc_id)
        return {
            "id": doc_id,
            "title": source.get("title", ""),
            "text": source.get("text", ""),
            "download_url": dl_url,
        }
    
    def fetch_passages(
        self,
        *,
        space: str,
        doc_id: str,
        query: str,
        per_id: int = 3,
        max_tokens: int = 350,
        chars_per_token: int = 4,   # ≈ Spanish tokens; tweak if you like
    ) -> list[dict]:
        """
        Return up to `per_id` passages from the given doc (id=doc_id) that best match `query`.
        Each passage is ~`max_tokens` tokens (approx via chars_per_token).
        """
        client = self._get_client()
        alias = self._alias_name(space)
        target_index = alias
        if not client.indices.exists_alias(name=alias):
            if not client.indices.exists(index=alias):
                return []

        fragment_size = max(128, min(8192, int(max_tokens * chars_per_token)))

        body = {
            "size": 1,  # we only need this one doc
            "query": {
                "bool": {
                    "must": [
                        {"term": {"id": doc_id}},            # restrict to this doc
                        {"multi_match": {                     # score relevance within the doc
                            "query": query,
                            "fields": ["title^2", "text"],
                            "type": "best_fields",
                        }},
                    ]
                }
            },
            # highlighter extracts top fragments by score
            "highlight": {
                "order": "score",
                "fields": {
                    "text": {
                        "type": "unified",
                        "fragment_size": fragment_size,
                        "number_of_fragments": per_id,
                        "no_match_size": fragment_size,  # fallback if no term hits
                        "pre_tags": ["<em>"],
                        "post_tags": ["</em>"],
                    }
                }
            },
            # optional: fetch the _score and only a small part of _source
            "_source": {"includes": ["id", "title", "download_url"]},
        }

        res = client.search(index=target_index, body=body)
        hits = res.get("hits", {}).get("hits", [])
        if not hits:
            return []

        hit = hits[0]
        frags = hit.get("highlight", {}).get("text", []) or []

        # Build normalized passages
        passages = []
        for i, frag in enumerate(frags[:per_id]):
            # Lazily presign S3 URLs if missing
            dl_url = hit.get("_source", {}).get("download_url")
            if not dl_url and getattr(settings, "S3_PRESIGN_ON_QUERY", True):
                dl_url = self._presign_by_id(doc_id)
            passages.append({
                "doc_id": doc_id,
                "rank": i + 1,
                "passage": frag,      # contains <em> .. </em> around matched terms
                "approx_tokens": fragment_size // chars_per_token,
                "score": float(hit.get("_score") or 0.0),
                "title": hit.get("_source", {}).get("title", ""),
                "download_url": dl_url,
            })

        # If the highlighter produced nothing (rare), fallback to the beginning of the doc
        if not passages:
            print("[OpenSearch] Highlighter returned no passages; only returning snippet of document.")
            doc = self.get_document_by_id(space, doc_id)
            if not doc:
                return []
            text = doc.get("text", "") or ""
            snippet = text[:fragment_size]
            passages = [{
                "doc_id": doc_id,
                "rank": 1,
                "passage": snippet,
                "approx_tokens": fragment_size // chars_per_token,
                "score": 0.0,
                "title": doc.get("title", ""),
                "download_url": doc.get("download_url"),
            }]

        return passages


opensearch_engine = OpenSearchSearch()

