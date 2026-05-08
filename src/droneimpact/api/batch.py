from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from droneimpact.api import get_app_state
from droneimpact.api.analyze import _build_response
from droneimpact.api.schemas import SingleDroneRequest
from droneimpact.casualty.engine import CasualtyEngine
from droneimpact.physics.trajectory import discretise_trajectory
from droneimpact.physics.types import StateVector
from droneimpact.scoring.engine import ScoringEngine

router = APIRouter(prefix="/analyze")

SYNC_THRESHOLD = 5


# ── Job store ──────────────────────────────────────────────────────────────────

@dataclass
class BatchJob:
    batch_id: str
    status: str  # "processing" | "complete" | "failed"
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    result: dict | None = None
    error: str | None = None


class JobStore:
    def __init__(self):
        self._jobs: dict[str, BatchJob] = {}
        self._lock = threading.Lock()

    def create(self, batch_id: str | None = None) -> BatchJob:
        bid = batch_id or str(uuid.uuid4())
        job = BatchJob(batch_id=bid, status="processing")
        with self._lock:
            self._jobs[bid] = job
        return job

    def get(self, batch_id: str) -> BatchJob | None:
        with self._lock:
            return self._jobs.get(batch_id)

    def update(self, batch_id: str, **kwargs) -> None:
        with self._lock:
            job = self._jobs.get(batch_id)
            if job:
                for k, v in kwargs.items():
                    setattr(job, k, v)


# ── Schemas ────────────────────────────────────────────────────────────────────

class BatchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    batch_id: str | None = None
    drones: list[SingleDroneRequest] = Field(min_length=1, max_length=100)
    async_: bool = Field(default=False, alias="async")


# ── Execution ──────────────────────────────────────────────────────────────────

def _analyze_one(drone_req: SingleDroneRequest, state) -> dict:
    sv = StateVector(
        lat=drone_req.trajectory.lat,
        lon=drone_req.trajectory.lon,
        altitude_m=drone_req.trajectory.altitude_m,
        heading_deg=drone_req.trajectory.heading_deg,
        speed_m_s=drone_req.trajectory.speed_m_s,
    )
    trajectory = discretise_trajectory(
        sv,
        spacing_m=drone_req.evaluation_spacing_m,
        max_range_m=drone_req.max_range_m,
    )
    casualty_engine = CasualtyEngine(state.population, state.infrastructure, state.config.casualty)
    scoring_engine = ScoringEngine(config=state.config)
    t0 = time.perf_counter()
    result = scoring_engine.score_trajectory(
        trajectory=trajectory,
        dem=state.dem,
        casualty_engine=casualty_engine,
        intercept_point_origin=(sv.lat, sv.lon),
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return _build_response(drone_req, result, elapsed_ms, state).model_dump()


def _execute_batch(batch_request: BatchRequest, state) -> dict:
    results = []
    errors = []
    for drone_req in batch_request.drones:
        try:
            results.append(_analyze_one(drone_req, state))
        except Exception as exc:
            errors.append({
                "drone_id": drone_req.drone_id or "unknown",
                "error": str(exc),
            })
    return {
        "batch_id": batch_request.batch_id,
        "status": "complete",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "errors": errors,
    }


def _run_batch_job(batch_id: str, batch_request: BatchRequest, state, job_store: JobStore):
    try:
        result = _execute_batch(batch_request, state)
        job_store.update(batch_id, status="complete", result=result,
                         completed_at=time.time())
    except Exception as exc:
        job_store.update(batch_id, status="failed", error=str(exc))


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/batch")
async def analyze_batch(
    body: BatchRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    state = get_app_state(request)
    if not state.data_loaded:
        raise HTTPException(status_code=503, detail="Data not loaded. Check /health.")

    use_async = body.async_ or len(body.drones) > SYNC_THRESHOLD
    job = request.app.state.job_store.create(body.batch_id)

    if use_async:
        background_tasks.add_task(
            _run_batch_job, job.batch_id, body, state, request.app.state.job_store
        )
        return {"batch_id": job.batch_id, "status": "processing"}

    result = _execute_batch(body, state)
    request.app.state.job_store.update(
        job.batch_id, status="complete", result=result, completed_at=time.time()
    )
    return result


@router.get("/batch/{batch_id}")
async def get_batch_result(batch_id: str, request: Request):
    job = request.app.state.job_store.get(batch_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Batch job {batch_id!r} not found.")
    if job.status == "processing":
        return {"batch_id": batch_id, "status": "processing"}
    if job.status == "failed":
        return {"batch_id": batch_id, "status": "failed", "error": job.error}
    return job.result
