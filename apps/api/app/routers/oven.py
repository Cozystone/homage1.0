from fastapi import APIRouter

from app.services.alpha_services import alpha_service

router = APIRouter(prefix="/api/oven", tags=["oven"])


@router.post("/dry-run")
def dry_run() -> dict:
    return alpha_service.run_oven_dry_run()


@router.get("/status")
def oven_status() -> dict:
    return alpha_service.oven_status()
