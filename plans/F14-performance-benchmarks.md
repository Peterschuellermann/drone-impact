# F14 — Performance Benchmarks

**Status:** pending  
**Branch:** `feature/F14-performance-benchmarks`  
**Dependencies:** F12, F13

---

## Goal

Implement performance benchmark tests that assert the latency budgets defined in the spec. These tests require real data files (DEM, Kontur, OSM) and are skipped by default in CI. They are run manually on a target server with real data loaded.

Additionally, profile the hot paths and document any performance findings in a benchmark report in `/spec/performance.md`.

---

## Acceptance Criteria

- [ ] `pytest tests/performance/ --run-perf` runs without collection errors when data files are absent (skipped with a clear message)
- [ ] `pytest tests/performance/ --run-perf` asserts single-drone < 500 ms when data is present
- [ ] `pytest tests/performance/ --run-perf` asserts batch of 50 drones < 15 s when data is present
- [ ] A `conftest.py` skip mechanism prevents performance tests from running without `--run-perf`
- [ ] Monte Carlo convergence tests (N=100 → 1,000 → 10,000) show E[casualties] converges; this runs without real data using synthetic population
- [ ] `/spec/performance.md` documents measured latency breakdown per component

---

## Implementation Steps

### 1. tests/conftest.py — `--run-perf` flag

Add to the root `conftest.py`:

```python
def pytest_addoption(parser):
    parser.addoption("--run-perf", action="store_true", default=False,
                     help="Run performance benchmark tests (requires real data)")

def pytest_configure(config):
    config.addinivalue_line("markers",
        "perf: mark test as performance benchmark (skipped without --run-perf)")

def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-perf"):
        skip_perf = pytest.mark.skip(reason="Pass --run-perf to run performance benchmarks")
        for item in items:
            if "perf" in item.keywords:
                item.add_marker(skip_perf)
```

### 2. tests/performance/test_latency.py

```python
import pytest
import time
import httpx
from httpx import AsyncClient, ASGITransport

pytestmark = pytest.mark.perf

@pytest.fixture(scope="module")
def real_app():
    """Creates an app with real data files loaded. Skips if data files not present."""
    import os
    from droneimpact.main import create_app
    if not os.path.exists("data/kontur_ukraine.gpkg"):
        pytest.skip("Real data files not found — cannot run performance tests")
    return create_app()

SINGLE_REQUEST = {
    "trajectory": {
        "lat": 48.3794, "lon": 31.1656,
        "altitude_m": 400, "heading_deg": 315.0, "speed_m_s": 51.4
    },
    "max_range_m": 250_000,
    "evaluation_spacing_m": 500
}

@pytest.mark.asyncio
async def test_single_drone_under_500ms(real_app):
    async with AsyncClient(transport=ASGITransport(app=real_app), base_url="http://test") as c:
        # Warm up (Numba JIT compile on first call)
        await c.post("/analyze/single", json={**SINGLE_REQUEST, "max_range_m": 5000})
        # Timed run
        t0 = time.perf_counter()
        resp = await c.post("/analyze/single", json=SINGLE_REQUEST)
        elapsed_ms = (time.perf_counter() - t0) * 1000
    assert resp.status_code == 200
    sim_ms = resp.json()["metadata"]["simulation_time_ms"]
    print(f"\nSingle drone: total={elapsed_ms:.0f}ms, sim={sim_ms:.0f}ms")
    assert elapsed_ms < 500

@pytest.mark.asyncio
async def test_batch_50_under_15s(real_app):
    batch = {
        "drones": [
            {**SINGLE_REQUEST, "drone_id": f"drone-{i:03d}",
             "trajectory": {**SINGLE_REQUEST["trajectory"],
                            "lat": 48.3794 + i * 0.01}}
            for i in range(50)
        ]
    }
    async with AsyncClient(transport=ASGITransport(app=real_app), base_url="http://test") as c:
        t0 = time.perf_counter()
        resp = await c.post("/analyze/batch", json=batch)
        batch_id = resp.json().get("batch_id")

        if batch_id:
            # Async job — poll until done
            for _ in range(60):
                await asyncio.sleep(1)
                poll = await c.get(f"/analyze/batch/{batch_id}")
                if poll.json()["status"] == "complete":
                    break
        elapsed = time.perf_counter() - t0

    print(f"\nBatch of 50: {elapsed:.1f}s")
    assert elapsed < 15.0
```

### 3. tests/performance/test_convergence.py

These tests do NOT require real data — they use synthetic population.

```python
# NOT marked with perf — runs in normal CI

@pytest.fixture
def casualty_engine_synthetic(config):
    cells = make_test_population(48.0, 31.0, pop_density=5000.0, radius_cells=10)
    pop   = PopulationIndex.from_dict(cells)
    infra = InfrastructureIndex.from_features([], config.casualty.infrastructure)
    return CasualtyEngine(pop, infra, config.casualty)

def test_monte_carlo_convergence(casualty_engine_synthetic, config):
    """E[casualties] converges as N increases."""
    sv = StateVector(lat=48.0, lon=31.0, altitude_m=400.0, heading_deg=0.0, speed_m_s=51.4)

    results = {}
    for n in [100, 1_000, 10_000]:
        rng = np.random.default_rng(42)
        enu = simulate_m1(400.0, 0.0, n, config.physics, rng=rng)
        wgs84 = enu_to_wgs84_batch(enu[:, 0], enu[:, 1], 48.0, 31.0)
        results[n] = casualty_engine_synthetic.compute(
            np.column_stack([wgs84[:, 1], wgs84[:, 0]]))  # [lat, lon]

    # Convergence check: N=10k should be close to N=1k
    rel_diff = abs(results[10_000] - results[1_000]) / max(results[1_000], 1e-9)
    assert rel_diff < 0.15  # within 15%

    # N=100 vs N=10k may differ more (high variance)
    print(f"\nConvergence: N=100: {results[100]:.4f}, "
          f"N=1k: {results[1_000]:.4f}, N=10k: {results[10_000]:.4f}")
```

### 4. spec/performance.md

Create this file during implementation of this plan, after running the benchmarks. It should contain:
- Measured latency for each component (trajectory gen, M1/M2/M3 sim, casualty engine, scoring)
- Memory footprint with Ukraine data loaded
- Bottleneck identification
- Any optimisations applied to meet the budget

---

## Notes

- The convergence test uses relative difference. If `results[1_000] == 0.0` (empty synthetic area), the test will trivially pass — ensure `make_test_population` covers the impact zone.
- Numba JIT compilation takes ~1–3 seconds on first invocation. The performance test includes a warm-up call before the timed run. This is intentional — the spec target is for a warm server.
- If performance targets are not met after implementation, the acceptable optimisation strategies (in order of preference) are:
  1. Reduce N for trajectory evaluation (use N=1,000 per point; N=10,000 only for final recommended point)
  2. Vectorise the H3 lookups in `PopulationIndex.query_batch` using a pre-built NumPy array
  3. Numba JIT on the physics engine inner loops
  4. Do NOT add caching or async parallelism to meet the budget without first confirming the bottleneck
