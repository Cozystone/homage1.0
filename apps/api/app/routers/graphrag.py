from pydantic import BaseModel
from fastapi import APIRouter

from app.services.alpha_services import alpha_service

router = APIRouter(prefix="/api/graphrag", tags=["graphrag"])


class GraphRAGQuery(BaseModel):
    query: str
    web_search: bool = False
    web_search_provider: str | None = None
    brain_mode: str = "unified"
    locale: str | None = None
    include_trace: bool = True


@router.post("/query")
async def query_graphrag(request: GraphRAGQuery) -> dict:
    return await alpha_service.query_graphrag(
        request.query,
        request.web_search,
        request.web_search_provider,
        brain_mode=request.brain_mode,
        locale=request.locale,
        include_trace=request.include_trace,
    )


@router.get("/status")
def graphrag_status() -> dict:
    return alpha_service.graphrag_status()
