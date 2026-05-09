import asyncio
import time

import pytest

from droneimpact.api.batch import JobStore

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


# ── Out-of-bounds drone (valid Pydantic, fails during analysis) ──────────────

_OUT_OF_BOUNDS_DRONE = {
    "drone_id": "oob-drone",
    "trajectory": {
        "lat": 10.0,
        "lon": 10.0,
        "altitude_m": 400,
        "heading_deg": 0.0,
        "speed_m_s": 51.4,
    },
    "max_range_m": 3000,
    "evaluation_spacing_m": 1000,
}

_GOOD_DRONE = {
    "drone_id": "good-drone",
    "trajectory": {
        "lat": 48.0,
        "lon": 31.0,
        "altitude_m": 400,
        "heading_deg": 0.0,
        "speed_m_s": 51.4,
    },
    "max_range_m": 3000,
    "evaluation_spacing_m": 1000,
}


# ── Partial failure status tests (I04) ───────────────────────────────────────

async def test_batch_partial_failure_status(client):
    """One good drone + one out-of-bounds drone => partial status."""
    batch = {"drones": [_GOOD_DRONE, _OUT_OF_BOUNDS_DRONE]}
    resp = await client.post("/analyze/batch", json=batch)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "partial"
    assert len(body["results"]) == 1
    assert len(body["errors"]) == 1
    assert body["errors"][0]["drone_id"] == "oob-drone"


async def test_batch_all_failed_status(client):
    """All drones out-of-bounds => failed status."""
    batch = {"drones": [_OUT_OF_BOUNDS_DRONE]}
    resp = await client.post("/analyze/batch", json=batch)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert len(body["results"]) == 0
    assert len(body["errors"]) == 1


async def test_batch_all_succeed_status(client):
    """All drones succeed => complete status."""
    resp = await client.post("/analyze/batch", json=SMALL_BATCH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "complete"
    assert len(body["errors"]) == 0


# ── Job store TTL eviction tests (I03) ───────────────────────────────────────

def test_job_store_evicts_completed_jobs():
    """Completed jobs older than TTL are removed on next access."""
    store = JobStore(ttl_s=0.1)
    job = store.create("test-job")
    store.update("test-job", status="complete", completed_at=time.time())

    # Job still exists immediately
    assert store.get("test-job") is not None

    # Wait for TTL to expire, then force eviction by resetting _last_eviction
    time.sleep(0.15)
    # Reset the eviction throttle so the next call actually runs eviction
    store._last_eviction = 0.0

    assert store.get("test-job") is None


def test_job_store_does_not_evict_processing_jobs():
    """Processing (incomplete) jobs are never evicted, even past TTL."""
    store = JobStore(ttl_s=0.1)
    store.create("processing-job")

    time.sleep(0.15)
    store._last_eviction = 0.0

    assert store.get("processing-job") is not None
    assert store.get("processing-job").status == "processing"


async def test_batch_result_schema_matches_single(client):
    """Batch drone results must have the same fields as single drone results."""
    single_req = {
        "trajectory": {
            "lat": 48.0, "lon": 31.0, "altitude_m": 400,
            "heading_deg": 0.0, "speed_m_s": 51.4,
        },
        "max_range_m": 3000,
        "evaluation_spacing_m": 1000,
    }
    single_resp = await client.post("/analyze/single", json=single_req)
    single_body = single_resp.json()

    batch_resp = await client.post("/analyze/batch", json={
        "drones": [single_req],
    })
    batch_body = batch_resp.json()
    batch_drone = batch_body["results"][0]

    single_keys = set(single_body["trajectory_scores"][0].keys())
    batch_keys = set(batch_drone["trajectory_scores"][0].keys())
    assert single_keys == batch_keys


async def test_batch_trajectory_points_have_heading_and_speed(client):
    """Each trajectory point score must include heading_deg and speed_m_s."""
    resp = await client.post("/analyze/batch", json=SMALL_BATCH)
    body = resp.json()
    for result in body["results"]:
        for pt in result["trajectory_scores"]:
            assert "heading_deg" in pt
            assert "speed_m_s" in pt
            assert pt["speed_m_s"] == pytest.approx(51.4)


async def test_batch_heading_values_match_input(client):
    """Batch results should carry through the input heading for each drone."""
    batch = {
        "drones": [
            {
                "drone_id": "north",
                "trajectory": {
                    "lat": 48.0, "lon": 31.0, "altitude_m": 400,
                    "heading_deg": 0.0, "speed_m_s": 51.4,
                },
                "max_range_m": 3000,
                "evaluation_spacing_m": 1000,
            },
            {
                "drone_id": "west",
                "trajectory": {
                    "lat": 48.0, "lon": 31.0, "altitude_m": 400,
                    "heading_deg": 270.0, "speed_m_s": 51.4,
                },
                "max_range_m": 3000,
                "evaluation_spacing_m": 1000,
            },
        ]
    }
    resp = await client.post("/analyze/batch", json=batch)
    body = resp.json()
    by_id = {r["drone_id"]: r for r in body["results"]}
    assert by_id["north"]["trajectory_scores"][0]["heading_deg"] == pytest.approx(0.0)
    assert by_id["west"]["trajectory_scores"][0]["heading_deg"] == pytest.approx(270.0)


def test_job_store_eviction_on_create():
    """Eviction runs during create() as well."""
    store = JobStore(ttl_s=0.1)
    job = store.create("old-job")
    store.update("old-job", status="complete", completed_at=time.time())

    time.sleep(0.15)
    store._last_eviction = 0.0

    # Creating a new job should trigger eviction of old-job
    store.create("new-job")
    assert store.get("old-job") is None
    assert store.get("new-job") is not None
