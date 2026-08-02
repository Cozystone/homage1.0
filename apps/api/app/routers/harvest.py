from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.web_search import DEFAULT_QUERY, provider_status, search_web

router = APIRouter(prefix="/api/harvest", tags=["harvest"])


class WebSearchRequest(BaseModel):
    query: str = DEFAULT_QUERY
    count: int = Field(default=5, ge=1, le=10)
    provider: str | None = None


@router.get("/web-search/status")
def web_search_status(provider: str | None = None) -> dict[str, Any]:
    return provider_status(provider)


@router.post("/web-search")
async def web_search(request: WebSearchRequest) -> dict[str, Any]:
    return await search_web(request.query, request.count, request.provider)
