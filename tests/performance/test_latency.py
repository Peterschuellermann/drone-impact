"""
Performance benchmark tests — require real data files.
Run with: pytest tests/performance/test_latency.py --run-perf
Skipped automatically without --run-perf flag.
"""
import asyncio
import os
import time

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.perf

SINGLE_REQUEST = {
    "trajectory": {
        "lat": 48.3794,
        "lon": 31.1656,
        "altitude_m": 400,
        "heading_deg": 315.0,
        "speed_m_s": 51.4,
    },
    "max_range_m": 250_000,
    "evaluation_spacing_m": 500,
}


@pytest.fixture(scope="module")
def real_app():
    if not os.path.exists("data/kontur_ukraine.gpkg"):
        pytest.skip("Real data files not found in data/ — cannot run performance tests")
    from droneimpact.main import create_app
    return create_app()


@pytest.mark.asyncio
async def test_single_drone_under_500ms(real_app):
    async with AsyncClient(transport=ASGITransport(app=real_app), base_url="http://test") as c:
        # Warm-up (Numba JIT compile on first call)
        warmup = {**SINGLE_REQUEST, "max_range_m": 5000, "evaluation_spacing_m": 1000}
        await c.post("/analyze/single", json=warmup)

        # Timed run
        t0 = time.perf_counter()
        resp = await c.post("/analyze/single", json=SINGLE_REQUEST)
        elapsed_ms = (time.perf_counter() - t0) * 1000

    assert resp.status_code == 200
    sim_ms = resp.json()["metadata"]["simulation_time_ms"]
    print(f"\nSingle drone: wall={elapsed_ms:.0f}ms sim={sim_ms:.0f}ms")
    assert elapsed_ms < 500, f"Single drone took {elapsed_ms:.0f} ms (budget: 500 ms)"


@pytest.mark.asyncio
async def test_batch_50_under_15s(real_app):
    batch = {
        "drones": [
            {
                **SINGLE_REQUEST,
                "drone_id": f"drone-{i:03d}",
                "trajectory": {**SINGLE_REQUEST["trajectory"],
                               "lat": 48.3794 + i * 0.01},
            }
            for i in range(50)
        ]
    }
    async with AsyncClient(transport=ASGITransport(app=real_app), base_url="http://test") as c:
        t0 = time.perf_counter()
        resp = await c.post("/analyze/batch", json=batch)
        body = resp.json()
        batch_id = body.get("batch_id")

        if batch_id:
            for _ in range(30):
                await asyncio.sleep(1)
                poll = await c.get(f"/analyze/batch/{batch_id}")
                if poll.json()["status"] == "complete":
                    break

        elapsed = time.perf_counter() - t0

    print(f"\nBatch of 50: {elapsed:.1f}s")
    assert elapsed < 15.0, f"Batch of 50 took {elapsed:.1f}s (budget: 15s)"
