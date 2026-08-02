from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.services.datagate_service import (
    DataGateRunAccepted,
    DataGateRunAlreadyRunning,
    DataGateRunRequest,
    DataGateStatus,
    datagate_service,
)


router = APIRouter(prefix="/api/datagate", tags=["datagate"])


@router.post(
    "/run",
    response_model=DataGateRunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def run_datagate(
    background_tasks: BackgroundTasks,
    request: DataGateRunRequest | None = None,
) -> DataGateRunAccepted:
    try:
        accepted = datagate_service.start_run(request or DataGateRunRequest())
    except DataGateRunAlreadyRunning as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    background_tasks.add_task(datagate_service.run_pending)
    return accepted


@router.get("/status", response_model=DataGateStatus)
def datagate_status() -> DataGateStatus:
    return datagate_service.status()
