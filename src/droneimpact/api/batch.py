from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from droneimpact.api import get_app_state
from droneimpact.api.analyze import _build_response
from droneimpact.api.schemas import SingleDroneRequest
from droneimpact.casualty.engine import CasualtyEngine
from droneimpact.physics.trajectory import discretise_trajectory
from droneimpact.physics.types import StateVector
from droneimpact.scoring.engine import ScoringEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze")

SYNC_THRESHOLD = 5


# ── Job store ──────────────────────────────────────────────────────────────────

@dataclass
class BatchJob:
    batch_id: str
    status: str  # "processing" | "complete" | "partial" | "failed"
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    result: dict | None = None
    error: str | None = None


class JobStore:
    def __init__(self, ttl_s: float = 3600.0):
        self._jobs: dict[str, BatchJob] = {}
        self._lock = threading.Lock()
        self._ttl_s = ttl_s
        self._last_eviction = 0.0

    def _evict_expired(self) -> None:
        """Remove completed jobs older than TTL. Caller must hold self._lock."""
        now = time.time()
        if now - self._last_eviction < 60.0:
            return
        self._last_eviction = now
        expired = [
            bid for bid, job in self._jobs.items()
            if job.completed_at is not None and now - job.completed_at > self._ttl_s
        ]
        for bid in expired:
            del self._jobs[bid]

    def create(self, batch_id: str | None = None) -> BatchJob:
        bid = batch_id or str(uuid.uuid4())
        job = BatchJob(batch_id=bid, status="processing")
        with self._lock:
            self._evict_expired()
            self._jobs[bid] = job
        return job

    def get(self, batch_id: str) -> BatchJob | None:
        with self._lock:
            self._evict_expired()
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


# ── Worker process state ──────────────────────────────────────────────────────

_worker_state = None


def _init_batch_worker(state_dict: dict) -> None:
    global _worker_state
    _worker_state = state_dict
    from droneimpact.physics.warmup import warmup_jit
    warmup_jit()


def _analyze_one_in_worker(drone_req_dict: dict) -> dict:
    """Top-level function for ProcessPoolExecutor — must be picklable."""
    state = _worker_state
    drone_req = SingleDroneRequest.model_validate(drone_req_dict)
    return _analyze_one(drone_req, state, point_workers=1)


# ── Execution ──────────────────────────────────────────────────────────────────

def _analyze_one(drone_req: SingleDroneRequest, state, point_workers: int | None = None) -> dict:
    t0 = time.perf_counter()
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
    casualty_engine = CasualtyEngine(
        population=state.population,
        infrastructure=state.infrastructure,
        config=state.config.casualty,
    )
    scoring_engine = ScoringEngine(config=state.config, max_point_workers=point_workers)
    n_samples = drone_req.n_monte_carlo_samples or state.config.physics.n_monte_carlo_samples
    result = scoring_engine.score_trajectory(
        trajectory=trajectory,
        dem=state.dem,
        casualty_engine=casualty_engine,
        intercept_point_origin=(sv.lat, sv.lon),
        n_samples=n_samples,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return _build_response(drone_req, result, elapsed_ms, state).model_dump()


def _execute_batch(batch_request: BatchRequest, state, executor: ProcessPoolExecutor | None = None) -> dict:
    n_drones = len(batch_request.drones)
    threshold = state.config.parallelism.batch_parallel_threshold
    use_parallel = executor is not None and n_drones >= threshold

    results = []
    errors = []

    if use_parallel:
        futures = {}
        for drone_req in batch_request.drones:
            fut = executor.submit(_analyze_one_in_worker, drone_req.model_dump())
            futures[fut] = drone_req.drone_id or "unknown"

        for fut in as_completed(futures):
            drone_id = futures[fut]
            try:
                results.append(fut.result())
            except Exception as exc:
                logger.warning("Drone %s failed: %s", drone_id, traceback.format_exc())
                errors.append({"drone_id": drone_id, "error": str(exc)})
    else:
        for drone_req in batch_request.drones:
            try:
                results.append(_analyze_one(drone_req, state))
            except Exception as exc:
                logger.warning(
                    "Drone %s failed: %s",
                    drone_req.drone_id or "unknown",
                    traceback.format_exc(),
                )
                errors.append({
                    "drone_id": drone_req.drone_id or "unknown",
                    "error": str(exc),
                })

    if not results and errors:
        status = "failed"
    elif errors:
        status = "partial"
    else:
        status = "complete"

    return {
        "batch_id": batch_request.batch_id,
        "status": status,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "errors": errors,
    }


def _run_batch_job(batch_id: str, batch_request: BatchRequest, state, job_store: JobStore,
                   executor: ProcessPoolExecutor | None = None):
    try:
        result = _execute_batch(batch_request, state, executor=executor)
        job_store.update(batch_id, status=result["status"], result=result,
                         completed_at=time.time())
    except Exception as exc:
        job_store.update(batch_id, status="failed", error=str(exc))


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/batch")
def analyze_batch(
    body: BatchRequest,
    request: Request,
):
    state = get_app_state(request)
    if not state.data_loaded:
        raise HTTPException(status_code=503, detail="Data not loaded. Check /health.")

    executor = getattr(request.app.state, "batch_executor", None)

    use_async = body.async_ or len(body.drones) > SYNC_THRESHOLD
    job = request.app.state.job_store.create(body.batch_id)

    if use_async:
        thread = threading.Thread(
            target=_run_batch_job,
            args=(job.batch_id, body, state, request.app.state.job_store, executor),
        )
        thread.start()
        return {"batch_id": job.batch_id, "status": "processing"}

    body.batch_id = job.batch_id
    result = _execute_batch(body, state, executor=executor)
    request.app.state.job_store.update(
        job.batch_id, status=result["status"], result=result, completed_at=time.time()
    )
    return result


@router.get("/batch/{batch_id}")
def get_batch_result(batch_id: str, request: Request):
    job = request.app.state.job_store.get(batch_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Batch job {batch_id!r} not found.")
    if job.status == "processing":
        return {"batch_id": batch_id, "status": "processing"}
    if job.result is not None:
        return job.result
    return {"batch_id": batch_id, "status": "failed", "error": job.error}
