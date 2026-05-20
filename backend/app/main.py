from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from .core.config import settings
from .api.v1.endpoints import search
from .services.search import search_engine
from .api.v1.endpoints import files
from .api.v1.endpoints import chat
from .api.v1.endpoints import auth
from .api.v1.endpoints import billing
from .api.v1.endpoints import billing


app = FastAPI(
    title=f"{settings.APP_NAME} API",
    version=settings.API_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(","),  # or ["*"] for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search.router, prefix=f"/{settings.API_VERSION}")
app.include_router(files.router, prefix=f"/{settings.API_VERSION}")
app.include_router(chat.router, prefix=f"/{settings.API_VERSION}")
app.include_router(auth.router, prefix=f"/{settings.API_VERSION}")
app.include_router(billing.router, prefix=f"/{settings.API_VERSION}")
app.include_router(billing.router, prefix=f"/{settings.API_VERSION}")

static_dir = Path(__file__).resolve().parent / "static" / "downloads"
app.mount("/downloads", StaticFiles(directory=static_dir), name="downloads")

@app.get("/ping")
def ping():
    return {"status": "pong"}

@app.on_event("startup")
def on_startup():
    """Conditionally (re)index spaces at startup.

    Behavior:
    - If SKIP_REINDEX_ON_STARTUP is set, only index a space if it doesn't exist yet.
    - If FORCE_REINDEX_ON_STARTUP is true, always rebuild indexes.
    - Default (both false): always index the main corpus space and any upload spaces
      (preserves previous local dev behavior).
    """
    force = settings.FORCE_REINDEX_ON_STARTUP
    skip = settings.SKIP_REINDEX_ON_STARTUP

    def needs_index(space: str) -> bool:
        return False
        if force:
            return True
        if skip:
            # Only build if backend reports space missing
            try:
                return not search_engine.has_space(space)
            except Exception:
                return True  # conservative fallback
        # default legacy behavior: always index
        return True

    # Main corpus space
    if needs_index(settings.DEFAULT_SPACE):
        search_engine.index(space=settings.DEFAULT_SPACE)

    # User upload spaces
    uploads_root = Path(settings.DATA_UPLOAD)
    if uploads_root.exists():
        for path in uploads_root.glob("*/*"):
            if path.is_dir():
                rel = path.relative_to(uploads_root)
                space_name = str(rel)
                if needs_index(space_name):
                    search_engine.index(space=space_name)
