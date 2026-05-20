from pathlib import Path
import io
from dotenv import load_dotenv
import os
import asyncio
from types import SimpleNamespace

# Load the .env file from project root (2 levels up from /backend/tests)
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

import pytest

from backend.app.core.config import settings
from backend.app.api.v1.endpoints import search as search_ep
from backend.app.api.v1.endpoints import chat as chat_ep
from backend.app.api.v1.endpoints import files as files_ep
# from backend.app.api.v1.schemas import ChatRequest   # no longer used
from backend.app.services import auth
from backend.app.services.search import search_engine
from starlette.datastructures import UploadFile


# These tests now target the OpenSearch backend (default in settings).


@pytest.fixture()
def test_env(tmp_path, monkeypatch):
    """Prepare temp dirs, reset databases and index a small document."""
    # Point CORPUS_PATH to a temporary directory with a tiny corpus.jsonl
    corpus_dir = tmp_path / "static_corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    corpus_file = corpus_dir / "corpus.jsonl"
    corpus_file.write_text(
        '{"id": "1", "title": "Product Handbook", "text": "The handbook explains document retrieval workflows."}\n'
        '{"id": "2", "title": "Support Policy", "text": "Priority levels guide support responses."}\n'
        '{"id": "3", "title": "Security Overview", "text": "Security guidance covers secrets and uploads."}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "CORPUS_PATH", str(corpus_dir))

    monkeypatch.setattr(settings, "DATA_UPLOAD", str(tmp_path / "uploads"))
    monkeypatch.setattr(files_ep, "UPLOADS_ROOT", Path(settings.DATA_UPLOAD))
    files_ep.UPLOADS_ROOT.mkdir(parents=True, exist_ok=True)

    # Build a minimal UserData and stub accessible spaces for endpoints
    import uuid as _uuid
    user = auth.UserData(user_id=str(_uuid.uuid4()), username="alice", spaces=["personal"], first_name="Alice", last_name="Test")
    monkeypatch.setattr(search_ep, "get_accessible_spaces", lambda u: [settings.DEFAULT_SPACE, "alice/personal"])
    monkeypatch.setattr(files_ep, "get_accessible_spaces", lambda u: [settings.DEFAULT_SPACE, "alice/personal"])

    # Index the built-in default corpus and a simple personal document
    # For OpenSearch backend, this will create/refresh the alias for the space.
    search_engine.index(settings.DEFAULT_SPACE)

    # Create a simple document in alice's personal space
    uploads_dir = Path(settings.DATA_UPLOAD) / "alice" / "personal"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    (uploads_dir / "doc1.txt").write_text("hello world test document", encoding="utf-8")

    search_engine.index("alice/personal")
    return user


@pytest.fixture()
def fake_openai(monkeypatch):
    """Mock the OpenAI Responses client used by chat_ep.client."""
    class FakeItem:
        def __init__(self, type="message", name=None, arguments=None, call_id=None, summary=None):
            self.type = type
            self.name = name
            self.arguments = arguments
            self.call_id = call_id
            self.summary = summary
        # The endpoint calls sanitize_output_items which expects model_dump() or dict-like
        def model_dump(self):
            # Minimal assistant message; sanitize_output_items will keep role+content
            return {"type": "message", "role": "assistant", "content": "Test answer"}

    class FakeResponse:
        def __init__(self, text="Test answer"):
            self.output = [FakeItem("message")]
            self.output_text = text

    class FakeResponsesAPI:
        def create(self, model, instructions, input, tools, parallel_tool_calls, tool_choice, max_tool_calls, reasoning, stream=None):
            # Return a one-shot assistant message so the loop exits
            return FakeResponse("Test answer")

    class FakeClient:
        def __init__(self):
            self.responses = FakeResponsesAPI()

    monkeypatch.setattr(chat_ep, "client", FakeClient())
    return True


def test_search_basic(test_env):
    user = test_env
    resp = search_ep.search(q="handbook", top_k=3, space=settings.DEFAULT_SPACE, user=user)
    assert resp.results
    hit = resp.results[0]
    assert hit.score > 0


def test_file_upload_creates_file_and_indexes(test_env, monkeypatch):
    user = test_env
    uploaded = UploadFile(filename="new.txt", file=io.BytesIO(b"some content"))
    indexed = []

    def fake_index(space):
        indexed.append(space)

    monkeypatch.setattr(search_engine, "index", fake_index)

    resp = asyncio.run(files_ep.upload_file(files=[uploaded], space="alice/personal", user=user))
    saved = resp["uploaded"][0]["saved_path"]
    path = Path(settings.DATA_UPLOAD) / "alice" / "personal" / saved
    assert path.exists()
    assert indexed == ["alice/personal"]
