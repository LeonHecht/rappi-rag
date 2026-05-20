# Copyright 2025 Leon Hecht
# Licensed under the Apache License, Version 2.0 (see LICENSE file)

import json
from pathlib import Path
from rank_bm25 import BM25Okapi
from ..core.config import settings
import unicodedata
import re


class BM25Search:

    def __init__(self) -> None:
        
        self.corpus = {}
        self.tokenized = {}
        self.bm25_models = {}

    # helper to strip accents
    def strip_accents(self, s: str) -> str:
        return ''.join(
            c for c in unicodedata.normalize('NFD', s)
            if unicodedata.category(c) != 'Mn'
        )

    # helper to normalize tokens: strip accents, lowercase, and drop non‐letters
    def normalize_token(self, tok: str) -> str:
        tok = self.strip_accents(tok.lower())
        # drop any non-alphanumeric characters to match test queries
        tok = re.sub(r"[^a-z0-9]+", "", tok)
        return tok

    def index(self, space=None):
        """Load documents from CORPUS_PATH into BM25 index."""
        space = space or settings.DEFAULT_SPACE

        print("Loading corpus and initializing BM25 index...")
        
        self.corpus[space] = []  # dict to hold documents for the space
        self.tokenized[space] = []  # list to hold tokenized documents for the space

        if space == settings.DEFAULT_SPACE:
            self.tokenized[space] = []
            jsonl_file = Path(settings.CORPUS_PATH) / "corpus.jsonl"
            if jsonl_file.exists():
                # Load JSONL format
                with jsonl_file.open(encoding="utf-8") as f:
                    for line in f:
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        
                        doc_id = obj.get("id")
                        
                        title = obj.get("title", "")
                        
                        text = obj.get("text", "")
                        
                        content = f"{title} {text}".strip()
                        tokens_norm = [self.normalize_token(w) for w in content.split()]

                        self.corpus[space].append({"id": doc_id, "title": title, "text": content})
                        self.tokenized[space].append(tokens_norm)
            else:
                raise Exception("corpus.jsonl file missing.")
        else:
            # Load .txt files in directory
            dir_path = Path(settings.DATA_UPLOAD) / space
            for file in dir_path.glob("**/*.txt"):
                text = file.read_text(encoding="utf-8")
                tokens = text.split()
                self.corpus[space].append({"id": file.stem, "text": text})
                self.tokenized[space].append(tokens)
        # Build BM25
        tokens = self.tokenized[space]
        if tokens:
            # index only the list for this space
            self.bm25_models[space] = BM25Okapi(tokens)
        else:
            self.bm25_models[space] = None
        print("Done loading corpus and initializing BM25 index.")

    def has_space(self, space: str) -> bool:
        model = self.bm25_models.get(space)
        return model is not None

    def get_document_by_id(self, space: str, doc_id: str) -> dict | None:
        """
        Return {"id","title","text"} for a given doc_id from the doc-level corpus.
        """
        corpus = getattr(self, "corpus", None) or getattr(self, "corpus_doc", None)
        if corpus is None or space not in corpus:
            return None
        for d in corpus[space]:
            # old engine used {"id", "title", "text"} at doc level
            if d.get("id") == doc_id:
                return d
        return None

    def search(self, query: str, top_k: int = 30, space: str | None = None) -> list[dict]:
        """
        Perform BM25 search over the loaded corpus.

        Parameters
        ----------
        query : str
            The search query string.
        top_k : int
            Number of top results to return.

        Returns top_k results as list of dicts with:
        - id: document ID
        - score: BM25 score
        - snippet: first 100 words of the text
        - download_url: path under /files to fetch the original doc
        """
        space = space or settings.DEFAULT_SPACE
        print(f"Searching in space '{space}' with query: '{query}' and top_k={top_k}")
        model = self.bm25_models[space]
        if model is None:
            print(f"No BM25 model found for space '{space}'. Please index the corpus first.")
            return []
        
        tokenized_query = [self.normalize_token(t) for t in query.split() if t]
        if not tokenized_query:
            print("Empty query after normalization, returning empty results.")
            return []
        print(f"Searching for query: {tokenized_query}")
        scores = model.get_scores(tokenized_query)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        top_indices = [i for i in top_indices if scores[i] > 0][:top_k]
        
        print(f"Found {len(top_indices)} relevant documents in space '{space}'.")

        results = []
        tokenized_query_cleaned = [tok for tok in tokenized_query if len(tok) > 3]
        if len(tokenized_query_cleaned) > 0:
            tokenized_query = tokenized_query_cleaned
            
        for i in top_indices:
            doc = self.corpus[space][i]
            print(f"Processing document ID {doc['id']} with score {scores[i]:.4f}")
            text = doc["text"]
            print(f"Document text length: {len(text)} characters")

            # find first exact match of any query term and take 50-word window
            snippet = ""
            doc_tokens = text.split()
            for idx, orig_tok in enumerate(doc_tokens):
                if self.normalize_token(orig_tok) in tokenized_query:
                    start = max(idx - 25, 0)
                    snippet_tokens = doc_tokens[start : start + 50]
                    snippet = " ".join(snippet_tokens)
                    break
            
            if snippet == "":
                print(f"Warning: No snippet found for document ID {doc['id']}")
                
            # detect the actual file extension (pdf, html, docx, etc.)
            file_url = None
            for ext in (".pdf", ".PDF", ".htm", ".html", ".HTML", ".docx", ".doc", ".txt"):
                candidate = Path(settings.CORPUS_PATH) / "files" / f"{doc['id']}{ext}"
                if candidate.exists():
                    file_url = f"/files/{candidate.name}"
                    break
            if file_url is None:
                print(f"Warning: No file found for document ID {doc['id']}")

            title = doc.get("title") or ""
            results.append({
                "id": doc["id"],
                "title": title,
                "score": float(scores[i]),
                "snippet": snippet,
                "download_url": file_url,
            })
        return results
    

bm25_engine = BM25Search()
