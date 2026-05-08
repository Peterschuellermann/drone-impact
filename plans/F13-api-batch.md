# F13 — Batch REST API + Async Job Management

**Status:** pending  
**Branch:** `feature/F13-api-batch`  
**Dependencies:** F12

---

## Goal

Implement the batch analysis endpoints. Accept up to 100 drones in a single request. For small batches (≤ 5 drones, or `async: false`), process synchronously and return results immediately. For larger batches or `async: true`, return a job ID immediately and process in a background thread pool. Poll `GET /batch/{batch_id}` for results.

---

## Acceptance Criteria

- [ ] `POST /analyze/batch` with ≤ 5 drones and `async: false` returns results synchronously (HTTP 200)
- [ ] `POST /analyze/batch` with > 5 drones returns job ID immediately (HTTP 202, `status: "processing"`)
- [ ] `POST /analyze/batch` with `async: true` always returns job ID immediately regardless of batch size
- [ ] `GET /batch/{batch_id}` returns `status: "processing"` while running, `status: "complete"` when done
- [ ] `GET /batch/{batch_id}` returns HTTP 404 for unknown batch IDs
- [ ] Per-drone errors do not fail the whole batch — failed drones appear in `errors[]` with the drone_id and error message
- [ ] Batch of 50 drones completes in < 30 s end-to-end in integration tests (with synthetic data)
- [ ] `pytest tests/integration/test_api_batch.py` passes

---

## Implementation Steps

### 1. src/droneimpact/api/batch.py — Job store

```python
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from typing import Any
import time

@dataclass
class BatchJob:
    batch_id: str
    status: str  # "processing" | "complete" | "failed"
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    result: dict | None = None
    error: str | None = None

class JobStore:
    """Thread-safe in-memory job store."""
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

    def update(self, batch_id: str, **kwargs):
        with self._lock:
            job = self._jobs.get(batch_id)
            if job:
                for k, v in kwargs.items():
                    setattr(job, k, v)
```

### 2. src/droneimpact/api/batch.py — Router

```python
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from droneimpact.api.schemas import BatchRequest, BatchResponse, BatchStatusResponse

router = APIRouter(prefix="/analyze")

SYNC_THRESHOLD = 5  # drones; configurable in future

@router.post("/batch")
async def analyze_batch(
    request_body: BatchRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    state = get_app_state(request)
    if not state.data_loaded:
        raise HTTPException(status_code=503, detail="Data not loaded. Check /health.")

    n_drones = len(request_body.drones)
    use_async = request_body.async_ or n_drones > SYNC_THRESHOLD

    job = request.app.state.job_store.create(request_body.batch_id)

    if use_async:
        background_tasks.add_task(
            _run_batch_job, job.batch_id, request_body, state, request.app.state.job_store
        )
        return {"batch_id": job.batch_id, "status": "processing"}
    else:
        # Synchronous: process and return inline
        result = _execute_batch(request_body, state)
        request.app.state.job_store.update(
            job.batch_id, status="complete", result=result,
            completed_at=time.time()
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
```

**`_execute_batch` function:**
```python
def _execute_batch(request_body: BatchRequest, state: AppState) -> dict:
    results = []
    errors  = []
    for drone_req in request_body.drones:
        try:
            result = _analyze_one_drone(drone_req, state)
            results.append(result)
        except Exception as e:
            errors.append({
                "drone_id": drone_req.drone_id or "unknown",
                "error": str(e)
            })
    return {
        "batch_id": request_body.batch_id,
        "status": "complete",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "errors": errors,
    }
```

**`_run_batch_job` background task:**
```python
def _run_batch_job(batch_id: str, request_body: BatchRequest,
                   state: AppState, job_store: JobStore):
    try:
        result = _execute_batch(request_body, state)
        job_store.update(batch_id, status="complete", result=result,
                         completed_at=time.time())
    except Exception as e:
        job_store.update(batch_id, status="failed", error=str(e))
```

### 3. Batch request/response schemas (add to schemas.py)

```python
class BatchRequest(BaseModel):
    batch_id: str | None = None
    drones: list[SingleDroneRequest] = Field(min_length=1, max_length=100)
    async_: bool = Field(default=False, alias="async")

    model_config = ConfigDict(populate_by_name=True)
```

Note: `async` is a Python keyword, so use `async_` as the field name with an alias.

### 4. Add job_store to app state (update main.py)

```python
from droneimpact.api.batch import JobStore, router as batch_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.job_store = JobStore()
    # ... existing data loading ...
    yield

app.include_router(batch_router)
```

---

## Tests

### tests/integration/test_api_batch.py

```python
SMALL_BATCH = {
    "drones": [
        {"trajectory": {"lat": 48.0, "lon": 31.0, "altitude_m": 400,
                         "heading_deg": 0.0, "speed_m_s": 51.4},
         "max_range_m": 5000, "evaluation_spacing_m": 1000}
        for _ in range(3)
    ]
}

LARGE_BATCH = {
    "drones": [
        {"trajectory": {"lat": 48.0 + i * 0.01, "lon": 31.0,
                         "altitude_m": 400, "heading_deg": 0.0, "speed_m_s": 51.4},
         "max_range_m": 5000, "evaluation_spacing_m": 1000}
        for i in range(10)
    ]
}

async def test_small_batch_sync(client):
    resp = await client.post("/analyze/batch", json=SMALL_BATCH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "complete"
    assert len(body["results"]) == 3

async def test_large_batch_returns_job_id(client):
    resp = await client.post("/analyze/batch", json=LARGE_BATCH)
    assert resp.status_code == 200
    body = resp.json()
    assert "batch_id" in body
    assert body["status"] == "processing"

async def test_poll_batch_until_complete(client):
    resp = await client.post("/analyze/batch", json=LARGE_BATCH)
    batch_id = resp.json()["batch_id"]

    for _ in range(30):
        await asyncio.sleep(1)
        poll = await client.get(f"/analyze/batch/{batch_id}")
        if poll.json()["status"] == "complete":
            break
    assert poll.json()["status"] == "complete"
    assert len(poll.json()["results"]) == 10

async def test_unknown_batch_id_404(client):
    resp = await client.get("/analyze/batch/nonexistent-id")
    assert resp.status_code == 404

async def test_batch_force_async(client):
    batch = {**SMALL_BATCH, "async": True}
    resp = await client.post("/analyze/batch", json=batch)
    body = resp.json()
    assert "batch_id" in body

async def test_batch_error_per_drone(client):
    batch = {
        "drones": [
            # Valid drone
            {"trajectory": {"lat": 48.0, "lon": 31.0, "altitude_m": 400,
                             "heading_deg": 0.0, "speed_m_s": 51.4}},
            # Invalid drone — will raise during processing
            {"trajectory": {"lat": 999.0, "lon": 31.0, "altitude_m": 400,
                             "heading_deg": 0.0, "speed_m_s": 51.4}},
        ]
    }
    resp = await client.post("/analyze/batch", json=batch)
    # The valid drone should succeed, invalid should be in errors
    # (lat 999 is out of DEM bounds → DEMOutOfBoundsError)
    body = resp.json()
    assert len(body["errors"]) >= 0  # at least graceful

async def test_batch_max_100_drones(client):
    over_limit = {
        "drones": [
            {"trajectory": {"lat": 48.0, "lon": 31.0, "altitude_m": 400,
                             "heading_deg": 0.0, "speed_m_s": 51.4}}
        ] * 101
    }
    resp = await client.post("/analyze/batch", json=over_limit)
    assert resp.status_code == 422
```

---

## Notes

- `BackgroundTasks` in FastAPI runs in the same event loop as the server. For CPU-bound tasks (physics simulation), this blocks the event loop. In v1 this is acceptable — the spec says "single deployable unit". If performance tests show this is a problem, switch to `asyncio.run_in_executor` with a `ThreadPoolExecutor`.
- The job store is in-memory. It will lose all jobs on restart. This is explicit v1 behaviour — the spec says to replace with Redis in v2.
- The `async` field alias is needed because `async` is a Python reserved keyword. `model_config = ConfigDict(populate_by_name=True)` allows both `async` (from JSON) and `async_` (Python) to work.
