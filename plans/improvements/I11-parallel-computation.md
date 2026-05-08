# I11 — Parallel Computation

## Problem

All computation is single-threaded. The two hot loops — per-evaluation-point scoring within a trajectory, and per-drone processing in batch requests — run sequentially despite each iteration being independent.

**Single-drone analysis** iterates over ~500 evaluation points (250 km at 500 m spacing). Each point runs three Monte Carlo simulations (M1/M2/M3, 10k samples each), converts ENU→WGS84, and queries population + infrastructure indices. These points are fully independent once the miss-branch casualty (computed from the last trajectory point) is known.

**Batch analysis** iterates over up to 100 drones sequentially. Each drone is completely independent — no shared mutable state.

Both loops can be parallelized to reduce wall-clock time proportionally to available cores.

## Architecture Constraints

**GIL and parallelism strategy:**
- NumPy array operations (M1/M3 simulations, coordinate transforms) release the GIL. ThreadPoolExecutor gives real parallelism for these.
- M2's time-stepping loop has Python control flow between NumPy calls. The GIL is held between array ops but released during each op. Threading still helps — the overlap is partial but significant.
- H3 lookups and scipy cKDTree queries release the GIL.
- **Conclusion:** ThreadPoolExecutor is effective for per-point parallelism within a single drone. ProcessPoolExecutor is needed for full parallelism across drones in batch.

**Data sharing:**
- `PopulationIndex` (dict + H3), `DEMIndex` (NumPy array), `InfrastructureIndex` (cKDTree) are loaded once at startup, read-only during requests.
- ThreadPoolExecutor: shared directly (same process).
- ProcessPoolExecutor: use `fork` start method. Workers inherit parent memory via copy-on-write with no serialization or duplication cost. Data is read-only, so COW pages are never copied.
- `fork` is safe here: data is loaded before the process pool is created, the rasterio file handle is closed after DEM load, and no threads exist yet during pool initialization.

**RNG independence:**
- The current `np.random.Generator` is passed through the scoring loop. Parallel execution requires independent RNGs per unit of work.
- NumPy's `SeedSequence.spawn()` creates statistically independent child sequences, guaranteeing non-overlapping streams.

**Miss-branch cache:**
- Module-level `_miss_cache` dict in `scoring/engine.py`. Under ThreadPoolExecutor, CPython's GIL makes dict read/write atomic — safe without locks.
- Under ProcessPoolExecutor (batch), each process gets its own cache. Acceptable — different drones rarely share cache keys (different trajectory endpoints).

## Changes

### 1. Config: add parallelism settings

**File:** `src/droneimpact/config.py`

Add a new `ParallelismConfig` model and include it in `AppConfig`:

```python
import os

class ParallelismConfig(BaseModel):
    point_workers: int = 0      # ThreadPool workers for per-point scoring; 0 = cpu_count
    batch_workers: int = 0      # ProcessPool workers for batch drones; 0 = cpu_count
    batch_parallel_threshold: int = 2  # min drones to trigger parallel batch

    @property
    def effective_point_workers(self) -> int:
        return self.point_workers or os.cpu_count() or 1

    @property
    def effective_batch_workers(self) -> int:
        return self.batch_workers or os.cpu_count() or 1
```

In `AppConfig`:

```python
class AppConfig(BaseModel):
    ...
    parallelism: ParallelismConfig = ParallelismConfig()
```

**File:** `config.yaml`

```yaml
parallelism:
  point_workers: 0    # 0 = auto (cpu_count)
  batch_workers: 0
  batch_parallel_threshold: 2
```

### 2. Scoring engine: parallel per-point evaluation

**File:** `src/droneimpact/scoring/engine.py`

Replace the sequential `for i, pt in enumerate(trajectory):` loop with a `ThreadPoolExecutor.map()` call. Apply to both `_score_all_points` (short trajectories) and the main `score_trajectory` method (long trajectories, non-empty points + dense points).

**RNG handling:**

```python
from numpy.random import SeedSequence

# In score_trajectory, before the parallel loop:
base_seed = rng.bit_generator.seed_seq
child_seeds = base_seed.spawn(n_points_to_score)
point_rngs = [np.random.default_rng(s) for s in child_seeds]
```

Each point gets its own RNG. Results are deterministic for a given base seed regardless of thread scheduling.

**Parallel loop (long trajectory path):**

```python
from concurrent.futures import ThreadPoolExecutor

def _score_point_wrapper(args):
    pt, agl, n_samples, casualty_engine, miss_cas, point_rng, compute_ell = args
    return self._score_point(pt, agl, n_samples, casualty_engine, miss_cas, point_rng, compute_ell)

# Prepare work items
work = []
for i, pt in enumerate(trajectory):
    if classifications[i] == 0:
        n_points_skipped += 1
        continue
    agl = dem.msl_to_agl(pt.lat, pt.lon, pt.altitude_m)
    compute_ell = classifications[i] == 2
    work.append((i, pt, agl, compute_ell))

child_seeds = base_seed.spawn(len(work))
point_rngs = [np.random.default_rng(s) for s in child_seeds]

max_workers = self._config.parallelism.effective_point_workers

with ThreadPoolExecutor(max_workers=max_workers) as pool:
    futures = []
    for idx, (i, pt, agl, compute_ell) in enumerate(work):
        fut = pool.submit(
            self._score_point,
            pt, agl, n_samples, casualty_engine, miss_casualties,
            point_rngs[idx], compute_ell,
        )
        futures.append((i, fut))

    for i, fut in futures:
        ps, dists = fut.result()
        ps.population_within_frag_radius = float(pop_at_points[i])
        scored_originals[i] = ps
        impact_dists.extend(dists)
```

Same pattern for `_score_all_points` and the dense-point loop.

**Fallback:** If `effective_point_workers == 1`, skip the ThreadPoolExecutor and run the existing sequential loop. This avoids overhead for single-core machines and makes debugging easier.

### 3. Batch handler: parallel per-drone evaluation

**File:** `src/droneimpact/api/batch.py`

Replace the sequential `for drone_req in batch_request.drones:` loop with `ProcessPoolExecutor`.

**Process pool creation at startup:**

**File:** `src/droneimpact/main.py`

```python
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor

# Module-level worker state (set by initializer in each forked process)
_worker_state = None

def _init_worker(state_dict):
    global _worker_state
    _worker_state = state_dict

@asynccontextmanager
async def lifespan(app: FastAPI):
    ...  # existing data loading
    
    n_workers = cfg.parallelism.effective_batch_workers
    ctx = mp.get_context("fork")
    
    # State dict holds references to loaded data — forked workers inherit them
    state_dict = {
        "config": app.state.config,
        "dem": app.state.dem,
        "population": app.state.population,
        "infrastructure": app.state.infrastructure,
    }
    
    executor = ProcessPoolExecutor(
        max_workers=n_workers,
        mp_context=ctx,
        initializer=_init_worker,
        initargs=(state_dict,),
    )
    app.state.batch_executor = executor
    
    yield
    
    executor.shutdown(wait=False)
```

**File:** `src/droneimpact/api/batch.py`

```python
from concurrent.futures import ProcessPoolExecutor, as_completed

def _analyze_one_worker(drone_req_dict: dict, config_dict: dict) -> dict:
    """Top-level function for ProcessPoolExecutor (must be picklable)."""
    # Access worker-local state set by initializer
    from droneimpact.main import _worker_state
    ...
    
def _execute_batch(batch_request, state) -> dict:
    executor = state.batch_executor
    n_workers = state.config.parallelism.effective_batch_workers
    threshold = state.config.parallelism.batch_parallel_threshold
    
    if len(batch_request.drones) < threshold or n_workers <= 1:
        # Sequential path (unchanged)
        ...
    
    # Parallel path
    futures = {}
    for drone_req in batch_request.drones:
        fut = executor.submit(_analyze_one, drone_req, state)
        futures[fut] = drone_req.drone_id or "unknown"
    
    results = []
    errors = []
    for fut in as_completed(futures):
        drone_id = futures[fut]
        try:
            results.append(fut.result())
        except Exception as exc:
            errors.append({"drone_id": drone_id, "error": str(exc)})
    ...
```

**Important:** With `fork`, the worker function `_analyze_one` can access `_worker_state` directly — the data indices are already in memory (inherited from the parent). No serialization of the 750 MB data is needed.

**macOS caveat:** `fork` works on macOS for this use case (no Objective-C runtime interaction in NumPy/scipy/h3 worker paths). If issues arise on macOS, the config can set `batch_workers: 1` to disable process parallelism and rely on thread-based per-point parallelism only.

### 4. Interaction between the two levels

When batch parallel is active, each worker process scores one drone at a time. Within that drone, the per-point ThreadPoolExecutor runs.

To avoid oversubscription (e.g., 4 process workers × 4 thread workers = 16 concurrent threads on a 4-core machine), the per-point thread count should be reduced when running inside a batch worker:

```python
# In ScoringEngine.score_trajectory:
if is_batch_worker():
    max_workers = 1  # batch parallelism already saturates cores
else:
    max_workers = self._config.parallelism.effective_point_workers
```

Or simpler: when batch parallelism is active, per-point parallelism is automatically set to 1 thread (sequential within each drone, parallel across drones). This avoids complexity and is optimal: N processes × 1 thread = N cores utilized without contention.

## Tests

### Unit tests

**File:** `tests/unit/test_parallel_scoring.py`

1. **Determinism:** Score a short trajectory (5 points) with `point_workers=1` and `point_workers=4`, same seed. Assert identical `engagement_score` for every point (to float precision).
2. **Correctness:** Score a trajectory with `point_workers=4` using synthetic population. Assert the recommended engagement point matches the sequential result.
3. **RNG independence:** Verify that `SeedSequence.spawn(N)` produces N distinct RNGs that generate non-overlapping sequences.

**File:** `tests/unit/test_parallel_batch.py`

4. **Batch determinism:** Process a 3-drone batch with `batch_workers=1` and `batch_workers=2`. Assert that the set of results is identical (order may differ).
5. **Error isolation:** Submit a batch where one drone has an invalid altitude. Assert that the other drones succeed and the error is captured.

### Integration tests

6. **Concurrent health check:** Start a single-drone analysis with `point_workers=4`. Simultaneously request `GET /health`. Assert health responds within 100 ms.
7. **Batch throughput:** Process a 10-drone batch with `batch_workers=2`. Assert total time is less than 6× single-drone time (accounting for overhead).

### Performance tests

Update `tests/performance/test_latency.py`:

8. **Single drone with parallelism:** Assert < 500 ms (should be significantly under budget now).
9. **Batch of 50 with parallelism:** Assert < 15 s. Log per-drone time distribution.

## Acceptance Criteria

- [ ] `config.yaml` has `parallelism` section; `ParallelismConfig` validates in Pydantic
- [ ] Per-point scoring runs in ThreadPoolExecutor with configurable worker count
- [ ] Batch scoring runs in ProcessPoolExecutor with fork-based workers
- [ ] Results are deterministic for a given seed regardless of worker count
- [ ] Setting `point_workers: 1` and `batch_workers: 1` reproduces the sequential code path exactly
- [ ] All existing tests pass without modification
- [ ] Performance tests pass with default parallelism settings
- [ ] No new dependencies added (uses stdlib `concurrent.futures` and `multiprocessing`)

## Spec Updates

**File:** `spec/architecture.md`

Update the "Batch Processing" section to reflect the implemented parallelism strategy:
- ProcessPoolExecutor with fork-based workers for inter-drone parallelism
- ThreadPoolExecutor for intra-trajectory per-point parallelism
- Oversubscription avoidance strategy
- Config parameters

## Dependencies

None — all prerequisite bugfixes (B02 event loop blocking) are already merged.

## Files to Modify

- `src/droneimpact/config.py` — add `ParallelismConfig`
- `src/droneimpact/scoring/engine.py` — ThreadPoolExecutor for per-point loops
- `src/droneimpact/api/batch.py` — ProcessPoolExecutor for per-drone loop
- `src/droneimpact/main.py` — create process pool at startup
- `config.yaml` — add `parallelism` section
- `spec/architecture.md` — document parallelism strategy
- `tests/unit/test_parallel_scoring.py` — new
- `tests/unit/test_parallel_batch.py` — new
