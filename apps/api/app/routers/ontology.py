from fastapi import APIRouter

from app.services.alpha_services import alpha_service

router = APIRouter(prefix="/api/ontology", tags=["ontology"])


@router.post("/run")
def run_ontology() -> dict:
    return alpha_service.run_ontology()


@router.get("/status")
def ontology_status() -> dict:
    return alpha_service.ontology_status()


@router.get("/graph")
def ontology_graph() -> dict:
    return alpha_service.ontology_graph()
