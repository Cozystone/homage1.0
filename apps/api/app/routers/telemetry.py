from fastapi import APIRouter

from app.services.alpha_services import telemetry_gpu, telemetry_system

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.get("/gpu")
def gpu() -> dict:
    return telemetry_gpu()


@router.get("/system")
def system() -> dict:
    return telemetry_system()
