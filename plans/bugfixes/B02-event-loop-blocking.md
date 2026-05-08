# B02 — Fix: API Handlers Block the Event Loop

## Problem

`POST /analyze/single` and `POST /analyze/batch` are declared as `async def` but
execute CPU-bound Monte Carlo simulation synchronously on the event loop. While an
analysis is running, the entire server is unresponsive — even `GET /health` hangs
until the computation finishes.

This also affects the async batch path: `BackgroundTasks.add_task` runs the callback
on the same event loop, so it blocks identically.

## Root Cause

FastAPI's `async def` endpoints run on the asyncio event loop. CPU-bound work
(NumPy/Numba simulation, H3 lookups) in an `async def` handler never yields
control, so no other requests can be served concurrently.

FastAPI does handle `def` (non-async) endpoints differently — it runs them in a
thread pool via `run_in_threadpool`. But for `async def`, the developer is
responsible for offloading blocking work.

## Proposed Fix

**Option A (simplest): Change handlers to `def` instead of `async def`**

FastAPI automatically runs `def` route handlers in a thread pool. This is a
one-line change per endpoint and immediately fixes the health-check blocking
issue. Multiple requests would run in separate threads.

Affected endpoints:
- `analyze_single` in `api/analyze.py`
- `analyze_batch` in `api/batch.py`

Downside: the GIL limits true parallelism for CPU-bound Python code. However,
NumPy releases the GIL during array operations, so there is partial benefit.
The main win is that I/O-bound handlers (health, job polling) are no longer
blocked.

**Option B (better concurrency): Use `run_in_executor` with a ProcessPoolExecutor**

Keep `async def` but offload the scoring call:

```python
import asyncio
from concurrent.futures import ProcessPoolExecutor

executor = ProcessPoolExecutor(max_workers=2)

async def analyze_single(body, request):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, _do_analysis, body, state)
    return result
```

This gives true parallelism (separate processes, no GIL) but requires that all
arguments to `_do_analysis` are picklable. The large data indices
(`PopulationIndex`, `DEMIndex`, `InfrastructureIndex`) would need to be loaded
per-worker or shared via memory-mapped files.

**Recommendation: Start with Option A.** It is a minimal, low-risk change that
unblocks health checks and job polling. Option B can be done later if true
parallel analysis is needed (e.g., batch of 50 drones should use multiple cores).

## Implementation Steps

### 1. Convert `analyze_single` to sync def

In `src/droneimpact/api/analyze.py`:

```python
# Before
async def analyze_single(body: SingleDroneRequest, request: Request) -> SingleDroneResponse:

# After
def analyze_single(body: SingleDroneRequest, request: Request) -> SingleDroneResponse:
```

### 2. Convert `analyze_batch` to sync def

In `src/droneimpact/api/batch.py`:

```python
# Before
async def analyze_batch(body: BatchRequest, request: Request, background_tasks: BackgroundTasks):

# After
def analyze_batch(body: BatchRequest, request: Request, background_tasks: BackgroundTasks):
```

### 3. Fix async batch execution

The current async batch path uses `BackgroundTasks`, which runs on the event
loop. With a `def` handler, `BackgroundTasks` still runs after the response is
sent but still on the event loop.

Replace `BackgroundTasks` with `threading.Thread` for async batch jobs:

```python
if use_async:
    thread = threading.Thread(
        target=_run_batch_job,
        args=(job.batch_id, body, state, request.app.state.job_store),
    )
    thread.start()
    return {"batch_id": job.batch_id, "status": "processing"}
```

This is already thread-safe — `JobStore` uses a `threading.Lock`.

### 4. Convert `get_batch_result` to sync def

```python
def get_batch_result(batch_id: str, request: Request):
```

## Testing

- Verify that `GET /health` responds within 100 ms while a single-drone analysis
  is in progress.
- Verify that an async batch job runs to completion in a background thread.
- All existing integration tests must pass.
- Add a test that issues a health check concurrently with an analysis request.

## Acceptance Criteria

- [ ] `GET /health` responds within 100 ms while analysis is running
- [ ] Async batch jobs complete successfully in background threads
- [ ] All existing tests pass
- [ ] No changes to API contracts or response schemas

## Dependencies

None.

## Files to Modify

- `src/droneimpact/api/analyze.py` — `async def` → `def`
- `src/droneimpact/api/batch.py` — `async def` → `def`, replace `BackgroundTasks` with `threading.Thread`
