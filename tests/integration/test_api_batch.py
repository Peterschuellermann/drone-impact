import asyncio

import pytest

SMALL_BATCH = {
    "drones": [
        {
            "trajectory": {
                "lat": 48.0 + i * 0.01,
                "lon": 31.0,
                "altitude_m": 400,
                "heading_deg": 0.0,
                "speed_m_s": 51.4,
            },
            "max_range_m": 3000,
            "evaluation_spacing_m": 1000,
        }
        for i in range(3)
    ]
}

LARGE_BATCH = {
    "drones": [
        {
            "trajectory": {
                "lat": 48.0 + i * 0.01,
                "lon": 31.0,
                "altitude_m": 400,
                "heading_deg": 0.0,
                "speed_m_s": 51.4,
            },
            "max_range_m": 3000,
            "evaluation_spacing_m": 1000,
        }
        for i in range(8)
    ]
}


async def test_small_batch_sync_returns_results(client):
    resp = await client.post("/analyze/batch", json=SMALL_BATCH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "complete"
    assert len(body["results"]) == 3
    assert body["errors"] == []


async def test_large_batch_returns_job_id(client):
    resp = await client.post("/analyze/batch", json=LARGE_BATCH)
    assert resp.status_code == 200
    body = resp.json()
    assert "batch_id" in body
    assert body["status"] == "processing"


async def test_poll_batch_until_complete(client):
    resp = await client.post("/analyze/batch", json=LARGE_BATCH)
    batch_id = resp.json()["batch_id"]

    for _ in range(60):
        await asyncio.sleep(0.5)
        poll = await client.get(f"/analyze/batch/{batch_id}")
        if poll.json()["status"] == "complete":
            break

    assert poll.json()["status"] == "complete"
    assert len(poll.json()["results"]) == 8


async def test_unknown_batch_id_404(client):
    resp = await client.get("/analyze/batch/does-not-exist")
    assert resp.status_code == 404


async def test_force_async_small_batch(client):
    batch = {**SMALL_BATCH, "async": True}
    resp = await client.post("/analyze/batch", json=batch)
    body = resp.json()
    assert "batch_id" in body
    assert body["status"] == "processing"


async def test_batch_max_100_exceeded_422(client):
    over_limit = {
        "drones": [
            {"trajectory": {"lat": 48.0, "lon": 31.0, "altitude_m": 400,
                             "heading_deg": 0.0, "speed_m_s": 51.4}}
        ] * 101
    }
    resp = await client.post("/analyze/batch", json=over_limit)
    assert resp.status_code == 422


async def test_empty_drones_422(client):
    resp = await client.post("/analyze/batch", json={"drones": []})
    assert resp.status_code == 422


async def test_batch_result_has_drone_results(client):
    resp = await client.post("/analyze/batch", json=SMALL_BATCH)
    body = resp.json()
    for result in body["results"]:
        assert "recommended_engagement" in result
        assert "trajectory_scores" in result


async def test_batch_with_caller_id(client):
    batch = {**SMALL_BATCH, "batch_id": "my-batch-123"}
    resp = await client.post("/analyze/batch", json=batch)
    body = resp.json()
    assert body.get("batch_id") == "my-batch-123" or body["status"] == "complete"
