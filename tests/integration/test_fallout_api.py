import pytest

VALID_POINT_REQUEST = {
    "lat": 48.3794,
    "lon": 31.1656,
    "altitude_m": 400,
    "heading_deg": 315.0,
    "speed_m_s": 51.4,
}


async def test_point_impact_endpoint_returns_all_modes(client):
    """POST /analyze/point-impact returns impact data for all three modes."""
    resp = await client.post("/analyze/point-impact", json=VALID_POINT_REQUEST)
    assert resp.status_code == 200
    body = resp.json()
    assert "modes" in body
    assert set(body["modes"].keys()) == {
        "propulsion_loss", "loss_of_control", "break_apart",
    }


async def test_point_impact_ellipses_valid(client):
    """Returned ellipses have positive semi-major/minor and valid orientation."""
    resp = await client.post("/analyze/point-impact", json=VALID_POINT_REQUEST)
    body = resp.json()
    for mode_name, mode_data in body["modes"].items():
        ellipse = mode_data["impact_ellipse"]
        assert ellipse["semi_major_m"] > 0, f"{mode_name} semi_major_m must be > 0"
        assert ellipse["semi_minor_m"] > 0, f"{mode_name} semi_minor_m must be > 0"
        assert 0 <= ellipse["orientation_deg"] < 360


async def test_point_impact_combined_zone_is_polygon(client):
    """combined_danger_zone is a valid GeoJSON Polygon."""
    resp = await client.post("/analyze/point-impact", json=VALID_POINT_REQUEST)
    body = resp.json()
    zone = body["combined_danger_zone"]
    assert zone["type"] == "Polygon"
    assert "coordinates" in zone
    coords = zone["coordinates"]
    assert len(coords) == 1
    assert len(coords[0]) >= 4


async def test_point_impact_metadata(client):
    """Response includes simulation metadata."""
    resp = await client.post("/analyze/point-impact", json=VALID_POINT_REQUEST)
    body = resp.json()
    meta = body["metadata"]
    assert "n_monte_carlo_samples" in meta
    assert meta["n_monte_carlo_samples"] > 0
    assert "simulation_time_ms" in meta
    assert meta["simulation_time_ms"] > 0


async def test_point_impact_mode_weights_sum_to_one(client):
    """Mode weights should sum to approximately 1.0."""
    resp = await client.post("/analyze/point-impact", json=VALID_POINT_REQUEST)
    body = resp.json()
    total = sum(m["weight"] for m in body["modes"].values())
    assert abs(total - 1.0) < 0.01


async def test_point_impact_invalid_altitude_422(client):
    """Invalid altitude returns 422."""
    bad = {**VALID_POINT_REQUEST, "altitude_m": -10}
    resp = await client.post("/analyze/point-impact", json=bad)
    assert resp.status_code == 422


async def test_point_impact_invalid_speed_422(client):
    """Invalid speed returns 422."""
    bad = {**VALID_POINT_REQUEST, "speed_m_s": 5}
    resp = await client.post("/analyze/point-impact", json=bad)
    assert resp.status_code == 422
