from datetime import datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

VALID_REQUEST = {
    "drone_id": "test-001",
    "trajectory": {
        "lat": 48.3794,
        "lon": 31.1656,
        "altitude_m": 400,
        "heading_deg": 315.0,
        "speed_m_s": 51.4,
    },
    "max_range_m": 5000,
    "evaluation_spacing_m": 1000,
}


async def test_single_returns_200(client):
    resp = await client.post("/analyze/single", json=VALID_REQUEST)
    assert resp.status_code == 200


async def test_single_response_keys(client):
    resp = await client.post("/analyze/single", json=VALID_REQUEST)
    body = resp.json()
    assert "recommended_engagement" in body
    assert "trajectory_scores" in body
    assert "impact_distributions" in body
    assert "metadata" in body


async def test_drone_id_echoed(client):
    resp = await client.post("/analyze/single", json=VALID_REQUEST)
    assert resp.json()["drone_id"] == "test-001"


async def test_none_drone_id(client):
    req = {k: v for k, v in VALID_REQUEST.items() if k != "drone_id"}
    resp = await client.post("/analyze/single", json=req)
    assert resp.status_code == 200
    assert resp.json()["drone_id"] is None


async def test_recommended_engagement_fields(client):
    resp = await client.post("/analyze/single", json=VALID_REQUEST)
    rec = resp.json()["recommended_engagement"]
    assert isinstance(rec["point_index"], int)
    assert isinstance(rec["lat"], float)
    assert rec["engagement_score"] >= 0.0
    assert len(rec["reasoning"]) > 5


async def test_trajectory_scores_ordered(client):
    resp = await client.post("/analyze/single", json=VALID_REQUEST)
    scores = resp.json()["trajectory_scores"]
    dists = [s["distance_from_current_m"] for s in scores]
    assert dists == sorted(dists)


async def test_recommended_is_min_score(client):
    resp = await client.post("/analyze/single", json=VALID_REQUEST)
    body = resp.json()
    all_scores = [s["engagement_score"] for s in body["trajectory_scores"]]
    assert body["recommended_engagement"]["engagement_score"] == pytest.approx(
        min(all_scores), rel=0.001
    )


async def test_impact_distributions_count(client):
    resp = await client.post("/analyze/single", json=VALID_REQUEST)
    body = resp.json()
    n_pts = body["metadata"]["n_trajectory_points"]
    assert len(body["impact_distributions"]) == n_pts * 3


async def test_metadata_fields(client, config):
    resp = await client.post("/analyze/single", json=VALID_REQUEST)
    meta = resp.json()["metadata"]
    assert meta["n_monte_carlo_samples"] == config.physics.n_monte_carlo_samples
    assert meta["simulation_time_ms"] > 0
    assert meta["n_trajectory_points"] > 0


async def test_computed_at_utc_parseable(client):
    resp = await client.post("/analyze/single", json=VALID_REQUEST)
    ts = resp.json()["computed_at_utc"]
    datetime.fromisoformat(ts)  # raises if not valid ISO 8601


async def test_invalid_altitude_422(client):
    bad = {**VALID_REQUEST, "trajectory": {**VALID_REQUEST["trajectory"], "altitude_m": -10}}
    resp = await client.post("/analyze/single", json=bad)
    assert resp.status_code == 422


async def test_invalid_heading_422(client):
    bad = {**VALID_REQUEST, "trajectory": {**VALID_REQUEST["trajectory"], "heading_deg": 400}}
    resp = await client.post("/analyze/single", json=bad)
    assert resp.status_code == 422


async def test_invalid_speed_422(client):
    bad = {**VALID_REQUEST, "trajectory": {**VALID_REQUEST["trajectory"], "speed_m_s": 5}}
    resp = await client.post("/analyze/single", json=bad)
    assert resp.status_code == 422


async def test_503_when_data_not_loaded(config):
    from fastapi import FastAPI
    from droneimpact.api.analyze import router as analyze_router

    app = FastAPI()
    app.include_router(analyze_router)
    app.state.config = config
    app.state.dem = None
    app.state.population = None
    app.state.infrastructure = None
    app.state.data_loaded = False
    app.state.population_cells = 0

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/analyze/single", json=VALID_REQUEST)
    assert resp.status_code == 503


async def test_breakdown_mode_keys(client):
    resp = await client.post("/analyze/single", json=VALID_REQUEST)
    for ps in resp.json()["trajectory_scores"]:
        assert set(ps["breakdown"].keys()) == {
            "propulsion_loss", "loss_of_control", "break_apart"
        }
