# Architecture

## Design Principles

1. **Physics-first, data-expandable:** The core engine is a Monte Carlo physics simulator. All parameters are configurable. The architecture must support replacing or augmenting the physics model with a data-driven model without changing the API contract.
2. **Fast by default:** Single-drone analysis must complete in < 500 ms. Batch of 50 drones < 15 s. Achieve this via vectorised computation, not distributed systems.
3. **Explainable outputs:** Every recommendation includes a structured rationale derivable from the data without an LLM.
4. **Country-agnostic:** Geography-specific data (population grids, infrastructure) is a runtime configuration, not a code assumption. Swapping from Ukraine to another country requires only data replacement.
5. **Single deployable unit (v1):** No microservices, no separate workers. One process handles API and computation. Add async workers in v2 if batch latency requires it.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        REST API Layer                        │
│   POST /analyze/single   POST /analyze/batch   GET /batch/  │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                     Orchestration Layer                      │
│  - Input validation                                         │
│  - Trajectory discretisation                                │
│  - Async job management (batch)                             │
└──────┬──────────────────────────────────────────────────────┘
       │
       ├──────────────────────────────────────────────────────┐
       ▼                                                      ▼
┌─────────────────────┐                          ┌───────────────────────┐
│   Physics Engine    │                          │   Casualty Engine     │
│                     │                          │                       │
│ - Trajectory gen    │    impact point array    │ - Population lookup   │
│ - Monte Carlo sim   │ ───────────────────────► │ - Blast model         │
│ - Mode M1/M2/M3     │                          │ - Frag model          │
│ - ENU ↔ WGS84      │                          │ - Infra penalty       │
└─────────────────────┘                          └───────────────────────┘
                                                          │
                                                          ▼
                                                 ┌─────────────────────┐
                                                 │   Scoring Engine    │
                                                 │                     │
                                                 │ - Pop pre-scan      │
                                                 │ - Adaptive res.     │
                                                 │ - Miss branch cache │
                                                 │ - E[casualties] per │
                                                 │   point and mode    │
                                                 │ - Engagement score  │
                                                 │ - Argmin → P*       │
                                                 │ - Zone classif.     │
                                                 │ - Explainability    │
                                                 └─────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    Pre-loaded Data Layer                    │
│                                                             │
│  Population H3 index  │  DEM array  │  Infra R-tree        │
│  (Kontur, ~200 MB)    │  (SRTM)     │  (OSM, ~50 MB)       │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Specifications

### REST API

**Framework:** FastAPI (Python)

**Endpoints:**

```
POST /analyze/single
  Request:  SingleDroneInput (see inputs-outputs.md)
  Response: SingleDroneOutput
  Timeout:  30 s

POST /analyze/batch
  Request:  BatchInput
  Response: BatchOutput or { batch_id, status: "processing" }
  Timeout:  120 s (sync), immediate (async)

GET /batch/{batch_id}
  Response: BatchOutput with status field

GET /health
  Response: { status: "ok", data_loaded: bool, population_cells: int }
```

**Content type:** `application/json`

**Authentication:** None in v1. Add API key header (`X-API-Key`) in v2.

---

### Physics Engine

The performance-critical path. Must run entirely in vectorised NumPy or equivalent (Numba JIT, JAX) — no per-sample Python loops.

**Vectorised Monte Carlo structure:**

```python
def simulate_mode_M1(n_samples: int, pos_enu: np.ndarray, speed: float, altitude_agl: float) -> np.ndarray:
    """
    Returns impact points as (N, 2) array of (x_east, y_north) in ENU metres.
    """
    heading_samples = np.random.normal(nominal_heading, σ_heading, n_samples)  # (N,)
    glide_ratio     = np.random.normal(5.0, 0.8, n_samples)                    # (N,)
    range_samples   = altitude_agl * glide_ratio                                # (N,)
    
    x_impact = range_samples * np.sin(np.radians(heading_samples))
    y_impact = range_samples * np.cos(np.radians(heading_samples))
    
    return np.stack([x_impact, y_impact], axis=1)                               # (N, 2)
```

All three modes operate this way. The M2 integration loop is vectorised across all N samples simultaneously (each timestep is a batch matrix operation).

**DEM access pattern:** Pre-load DEM as a 2D float32 array. Use bilinear interpolation for altitude lookups. Wrap in a class with `get_elevation(lat, lon)` and `get_elevation_batch(lats, lons)` (the batch version is critical for performance).

---

### Casualty Engine

Operates on arrays of impact points from the physics engine.

```python
def compute_casualties(impact_points_wgs84: np.ndarray) -> np.ndarray:
    """
    impact_points_wgs84: (N, 2) array of (lat, lon)
    Returns: (N,) array of expected casualties per impact
    """
    # 1. Look up population for each impact point neighbourhood
    pop_exposures = population_index.query_batch(impact_points_wgs84, radius_m=400)
    
    # 2. Apply P_casualty weighting over radius bins
    weighted_pop = apply_casualty_curve(pop_exposures)
    
    # 3. Compute infrastructure penalty
    infra_penalties = infrastructure_index.nearest_penalty_batch(impact_points_wgs84)
    
    return weighted_pop * (1.0 + infra_penalties)
```

**Population index:** Backed by a dictionary `h3_cell → population_count` (persons per cell) at resolution 8 (~460 m cells), with `grid_disk` for neighbourhood queries. Storing counts rather than density avoids per-cell area errors when summing across H3 cells at different latitudes. The `query_batch(lats, lons, radius_m)` method computes the disk size from the edge length and sums population in all cells within the radius. The `PopulationIndex` is accessible from `CasualtyEngine` via a `population` property for use in the scoring engine's population pre-scan.

**Infrastructure index:** R-tree (shapely `STRtree`) for fast nearest-neighbour queries. Pre-compute per-category maximum search radius to bound the query.

---

### Data Loading at Startup

All data is loaded once at process start. No file I/O during request handling.

```
Startup sequence:
  1. Load DEM → 2D float32 array + geographic bounds + resolution
  2. Load Kontur GPKG → H3 int64 → float32 dict + KV store
  3. Load OSM infrastructure GeoJSON → build STRtree per category
  4. Validate all data loaded; expose via /health endpoint
  5. Begin accepting requests
```

Estimated startup time: 10–30 seconds. Acceptable for a server process; unacceptable for a Lambda/serverless function. v1 targets a long-running server deployment.

**Memory budget (Ukraine data):**
| Dataset | Estimated size in memory |
|---|---|
| Kontur H3 dict (res 9) | ~400 MB |
| SRTM DEM (Ukraine box) | ~300 MB |
| OSM infrastructure R-trees | ~50 MB |
| **Total** | **~750 MB** |

A server with 2 GB RAM is sufficient. 4 GB recommended for headroom.

---

### Batch Processing

For ≤ 5 drones: synchronous, return results in response.  
For > 5 drones or `async: true`: return job ID, process in background thread pool.

**Parallelism:** Two levels implemented, configurable via `config.yaml` `parallelism` section:

1. **Per-drone batch parallelism (ProcessPoolExecutor):** `_execute_batch` submits each drone to a process pool created at server startup. Workers use `fork` start method and inherit pre-loaded data indices (DEM, population, infrastructure) via copy-on-write — no serialization or memory duplication. Each drone is fully independent. Observed speedup: **~11x** for 10 drones on 14 cores. Configurable via `batch_workers` (default: `0` = cpu_count). `batch_parallel_threshold` controls the minimum drone count to trigger parallelism (default: 2).

2. **Per-point scoring parallelism (ThreadPoolExecutor):** `ScoringEngine._score_points_parallel` distributes evaluation points across threads. Each point gets an independent RNG via `SeedSequence.spawn()` for deterministic results regardless of thread scheduling. However, benchmarking showed Python's GIL limits effectiveness — thread overhead and GIL contention negate gains even though NumPy releases the GIL during array operations. Default is `point_workers: 1` (sequential). The infrastructure is retained for future use with Numba `nogil` JIT compilation.

When batch parallelism is active, per-point threading inside each worker is forced to 1 to avoid oversubscription.

**Job storage (v1):** In-memory dict `job_id → BatchOutput`. Completed jobs expire after 1 hour (TTL). A background timer or lazy eviction on access is sufficient. Replace with Redis or a database in v2.

---

### Recommended Tech Stack

| Component | Recommendation | Rationale |
|---|---|---|
| Language | Python 3.11+ | Ecosystem (NumPy, SciPy, H3, shapely, FastAPI) |
| API framework | FastAPI | Async, auto-OpenAPI docs, pydantic validation |
| Numerical engine | NumPy + Numba | Vectorised + JIT for tight loops |
| Geospatial | shapely, pyproj, h3-py, rasterio | Standard Python geo stack |
| DEM loading | rasterio | GeoTIFF access with windowed reads |
| OSM parsing | pyosmium or osmium CLI | Fast PBF parsing |
| Population data | h3-py + numpy | H3 integer indexing |
| Testing | pytest + hypothesis | Property-based testing for physics |
| Containerisation | Docker | Reproducible deployment |

**Avoid:**
- GeoPandas for hot paths — it is slow for row-level operations. Use shapely + NumPy directly.
- GDAL Python bindings directly — use rasterio as the abstraction layer.
- Any database in v1 — all data lives in memory.

---

## API Contract Stability

The JSON schema for `SingleDroneInput` and `SingleDroneOutput` is the **stable interface**. Internal implementation (physics parameters, casualty model, data sources) may change without breaking the API contract. Use semantic versioning: breaking changes bump the major version (`/v2/analyze/single`).

---

## Configuration

All tunable parameters are loaded from a configuration file (YAML or TOML), not hard-coded. The configuration file includes:

```yaml
physics:
  n_monte_carlo_samples: 2000
  evaluation_spacing_m: 500
  shahed136:
    mass_kg: 200
    warhead_mass_kg: 45
    cruise_speed_m_s: 51.4
    glide_ratio: 5.0
    drag_coeff_tumbling: 0.8
    reference_area_m2: 3.5
    fragment_reference_area_m2: 0.5
    fragment_mass_mean_kg: 50.0
    fragment_mass_std_kg: 10.0
  m1_sigma_heading_deg: 5.0
  m1_sigma_glide_ratio: 0.8
  m2_sigma_init_deg: 30.0
  m2_sigma_turn_deg_per_s: 15.0
  m2_dt_s: 1.0
  m2_max_time_s: 300.0
  m2_descent_rate_m_s: 1.5
  m2_power_duration_min_s: 1.0
  m2_power_duration_max_s: 10.0
  m3_heading_spread_deg: 60.0
  m3_sigma_speed_m_s: 10.0
  m3_speed_reduction_factor: 0.7
  m3_sigma_cd: 0.15
  m3_dt_s: 0.1
  m3_max_steps: 1000
  m3_pitch_range_deg: 20.0
  atmosphere_scale_height_m: 8500.0

engagement:
  p_kill: 0.50
  mode_weights:
    propulsion_loss: 0.40
    loss_of_control: 0.35
    break_apart: 0.25
  mode_enable:
    propulsion_loss: true
    loss_of_control: true
    break_apart: true

casualty:
  blast:
    tnt_equivalent_kg: 30.0
    lethal_radius_m: 5.0
    injury_radius_m: 80.0
    p_lethal: 0.9
    p_injury: 0.3
  fragmentation:
    lethal_radius_m: 200.0
    danger_radius_m: 400.0
    p_frag_lethal: 0.5
    p_frag_danger: 0.1
  blast_bands:
    - {radius_m: 5, probability: 1.00}
    - {radius_m: 15, probability: 0.50}
    - {radius_m: 35, probability: 0.10}
    - {radius_m: 80, probability: 0.01}
  frag_bands:
    - {radius_m: 20, probability: 1.00}
    - {radius_m: 80, probability: 0.30}
    - {radius_m: 200, probability: 0.10}
    - {radius_m: 400, probability: 0.02}
  infrastructure:
    penalty_radius_m: 500.0
    max_penalty: 10.0
    weights:
      power_plant: 5.0
      hospital: 4.0
      water_works: 4.0
      bridge: 3.0
      school: 2.0

scoring:
  population_empty_threshold: 0.0
  population_high_risk_threshold: 50.0
  dense_spacing_m: 50.0
  miss_cache_agl_round_m: 10.0
  miss_cache_heading_round_deg: 1.0
  zone_caution_threshold: 0.1
  zone_nogo_threshold: 1.0

data:
  population_path: "./data/kontur_ukraine.gpkg"
  dem_path: "./data/ukraine_dem.tif"
  infrastructure_path: "./data/ukraine_infra.geojson"

dashboard:
  api_endpoint: "http://localhost:8000"
  default_max_range_m: 250000
  default_evaluation_spacing_m: 500
  cache_ttl_sec: 300
```

---

## Deployment (v1)

Single Docker container:

```dockerfile
FROM python:3.11-slim
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY ./data /app/data        # pre-processed datasets
COPY ./src /app/src
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
```

Single worker (uvicorn). Async FastAPI handles concurrent requests. Physics engine is CPU-bound; add `--workers N` for multi-core if needed (note: in-memory data is not shared across workers without additional setup — use `preload_app=True` with gunicorn or shared memory).

**Minimum server spec:** 2 vCPU, 4 GB RAM  
**Recommended spec:** 4 vCPU, 8 GB RAM (for batch workloads)

---

## Testing Strategy

| Layer | Approach |
|---|---|
| Physics engine | Unit tests with known inputs; validate impact distributions against analytical solutions |
| Casualty model | Regression tests with fixed population grids; verify blast radius thresholds |
| API | FastAPI `TestClient` integration tests |
| Monte Carlo convergence | Assert that E[casualties] converges as N increases; test at N=100, 1000, 10000 |
| Performance | Benchmark single-drone and batch-50 latency; fail if above budget |
| Data loading | Smoke test that all data indices load without error and respond correctly |

**Physics validation approach:** For M1 (propulsion loss), the analytical solution is deterministic for zero variance. Set σ_heading = 0, verify that all N samples land at the exact expected glide range. This catches unit/coordinate errors.

---

## Future Architecture Changes

| Feature | Required change |
|---|---|
| Wind/weather | Add atmospheric data loading at startup; pass wind vector to physics engine |
| ML trajectory model | Add new trajectory-prediction module; plug in before Monte Carlo |
| Dashboard | Streamlit dashboard implemented; connects to API for trajectory visualization and zone display |
| Historical data DB | Add PostGIS for storing impact events; separate ingestion service |
| Real-time tracker integration | Add WebSocket endpoint or gRPC stream; out of scope for v1 |
