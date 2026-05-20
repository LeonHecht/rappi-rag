from fastapi import APIRouter, Query, HTTPException, Depends
# from typing import List, Dict
from ..schemas import SearchResponse, SearchResult
from backend.app.services.search import search_engine
from backend.app.dependencies import get_current_user
from backend.app.services.auth import get_accessible_spaces, UserData
from backend.app.core.config import settings


router = APIRouter()

@router.get("/spaces")
def list_spaces(user: UserData = Depends(get_current_user)):
    """Return available search spaces for the current user."""
    return {"spaces": get_accessible_spaces(user)}

@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1),
    top_k: int = Query(10, ge=1, le=50),
    space: str = Query(..., min_length=1, description=f"Contexto: {settings.DEFAULT_SPACE}|my_uploads|<other>"),
    user: UserData = Depends(get_current_user),
):
    print(f"Received search query: '{q}' in space '{space}' with top_k={top_k}")
    if space not in get_accessible_spaces(user):
        raise HTTPException(403, detail="Space not accessible")
    if not search_engine.has_space(space):
        raise HTTPException(400, detail=f"Unknown space '{space}'")
    hits = search_engine.search(q, top_k, space)
    results = [SearchResult(**hit) for hit in hits]
    return SearchResponse(query_log_id=1, results=results)

# @router.post("/search", response_model=SearchResponse, summary="Run a BM25 or transformer search")
# def search(request: Request, req: SearchRequest = Body(..., description="Your search parameters")) -> SearchResponse:
#     """
#     Execute a search and log the query.

#     1. Validates non-empty query.
#     2. Captures client IP, country, and city.
#     3. Inserts a QueryLog row and retrieves its ID.
#     4. Runs either BM25 or transformer search.
#     5. Returns the log ID along with the hits.
#     """
#     if not req.query.strip():
#         raise HTTPException(status_code=400, detail="Query must not be empty")
    
#     client_ip = request.client.host or "Unknown"
#     country   = country_from_ip(client_ip) or "Unknown"
#     city      = city_from_ip(client_ip) or "Unknown"
    
#     # 1) Log the search
#     with Session(engine) as sess:
#         log = QueryLog(
#             client_ip=client_ip,
#             country=country,
#             city=city,
#             mode="semantica" if req.use_transformer else "exacta",
#             query=req.query.strip(),
#         )
#         sess.add(log)
#         sess.commit()
#         sess.refresh(log)  # populates log.id

#     # 2) Run the actual search  
#     if req.use_transformer:
#         hits = transformer_search(req.query, top_k=req.top_k)
#     else:
#         # existing BM25 search returns full results
#         hits = bm25_search(req.query, top_k=req.top_k)
    
#     # 3) Return both the log ID and the results
#     return SearchResponse(query_log_id=log.id, results=hits)
