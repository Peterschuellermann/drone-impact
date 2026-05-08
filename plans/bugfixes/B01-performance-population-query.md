# B01 — Performance: Vectorise Population and Infrastructure Queries

## Problem

A single-drone analysis with default settings (501 evaluation points, 10k Monte Carlo
samples) takes several minutes instead of the budgeted 500 ms. A 6-point trajectory
takes 12 seconds.

The bottleneck is the casualty engine's inner loop. For each evaluation point, each
mode, `CasualtyEngine.compute()` calls `PopulationIndex.query_batch()` four times
(one per blast/frag radius) and `InfrastructureIndex.penalty_batch()` once. Both
`*_batch` methods are Python `for` loops over 10k impact points:

- `PopulationIndex.query_batch` → for each point: `h3.latlng_to_cell` + `h3.grid_disk`
  + dict lookups. With 4 radii × 10k points × 3 modes × 501 eval points = ~60M
  Python-level H3 calls.
- `InfrastructureIndex.penalty_batch` → for each point: 5 STRtree nearest-neighbor
  queries. With 10k × 3 × 501 = ~15M Shapely queries.

## Root Cause

The data layer was written for correctness first, with Python loops and per-point
function calls. There is no vectorisation or spatial indexing on the hot path.

## Proposed Changes

### 1. Pre-build a NumPy population lookup array at startup

In `PopulationIndex.__init__` (or a post-load step), convert the `dict[str, float]`
into a structure that supports vectorised queries:

- Create a sorted array of all H3 cell indices (as integers via `h3.cell_to_int`)
  and a parallel array of population densities.
- For batch queries: convert all lat/lon pairs to H3 cells in one vectorised call
  (h3 4.x has `h3.latlng_to_cell` that can be applied via `np.vectorize` or the
  `h3ronpy` library for true vectorisation). Then use `np.searchsorted` on the
  sorted index for O(log N) lookup per point instead of Python dict access.
- For the k-ring expansion: at small k (k=1 for most radii at res 8), precompute
  each cell's disk neighbors once and cache them. The number of unique H3 cells
  in the dataset is ~300k; this lookup table fits easily in memory.

### 2. Vectorise infrastructure penalty

Replace the per-point Python loop in `InfrastructureIndex.penalty_batch` with a
bulk nearest-neighbor query:

- Use `STRtree.query_nearest` with an array of points (Shapely 2.x supports this).
- Or: convert infrastructure coordinates to a `scipy.spatial.cKDTree` at load time.
  `cKDTree.query(points, k=1)` returns nearest distances for all 10k points in one
  call. The equirectangular distance approximation already used in `_nearest_dist_m`
  is sufficient.

### 3. Two-pass scoring (optional, if still over budget)

Reduce work by running a coarse pass first:

- **Pass 1:** Run each evaluation point with N=200 Monte Carlo samples. This gives
  a rough score per point at 1/50th the cost.
- **Pass 2:** Run the top-5 lowest-scoring points (and their immediate neighbors)
  with the full N=10,000 samples to get accurate scores.
- This reduces total simulation from 501 × 10k = 5M samples to 501 × 200 + ~10 × 10k
  = ~200k samples — a 25× speedup.
- The two-pass approach is already suggested in F14's notes (item 1).

### 4. Reduce redundant coordinate conversions

In `ScoringEngine.score_trajectory`, `_to_wgs84` converts ENU → WGS84 then
`CasualtyEngine.compute` converts WGS84 → H3. Consider passing ENU offsets
directly and converting to H3 in a single step, avoiding the intermediate WGS84
lat/lon materialization for 10k points.

## Testing

- Existing unit tests must continue to pass — results should be numerically equivalent
  (within Monte Carlo variance for the two-pass approach).
- Performance test `test_single_drone_under_500ms` must pass with real data.
- Add a benchmark comparing old vs new `query_batch` throughput on 10k random points.

## Acceptance Criteria

- [ ] `PopulationIndex.query_batch` processes 10k points in < 10 ms (currently ~seconds)
- [ ] `InfrastructureIndex.penalty_batch` processes 10k points in < 5 ms
- [ ] Single-drone analysis (501 points, 10k MC samples) completes in < 500 ms
- [ ] All existing unit and integration tests pass
- [ ] Performance benchmark test passes with `--run-perf`

## Dependencies

None — this is a bugfix for existing functionality.

## Files to Modify

- `src/droneimpact/data/population.py` — vectorised query
- `src/droneimpact/data/infrastructure.py` — bulk nearest-neighbor
- `src/droneimpact/scoring/engine.py` — two-pass scoring (if needed)
- `src/droneimpact/casualty/engine.py` — no logic changes, but verify it works with new batch outputs
