from fastapi import APIRouter, HTTPException, status

from app.services.ingestion.scheduler import IngestionScheduler, get_scheduler

router = APIRouter()


def _scheduler() -> IngestionScheduler:
    try:
        return get_scheduler()
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)
        )


@router.get("/status")
def status_route() -> dict:
    """Current scheduler state + last tick stats."""
    return _scheduler().status()


@router.post("/run", status_code=status.HTTP_200_OK)
async def run_once() -> dict:
    """Manually trigger one ingestion tick — independent of the loop state.

    Safe to call even when INGESTION_ENABLED=false; useful for demos.
    """
    return await _scheduler().run_once()


@router.post("/start", status_code=status.HTTP_202_ACCEPTED)
async def start() -> dict:
    """Start the periodic loop. No-op if already running."""
    sch = _scheduler()
    await sch.start()
    return sch.status()


@router.post("/stop", status_code=status.HTTP_202_ACCEPTED)
async def stop() -> dict:
    """Stop the periodic loop. Manual /run still works after."""
    sch = _scheduler()
    await sch.stop()
    return sch.status()
