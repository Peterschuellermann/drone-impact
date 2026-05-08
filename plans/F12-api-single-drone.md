# F12 — Single-Drone REST API Endpoint

**Status:** pending  
**Branch:** `feature/F12-api-single-drone`  
**Dependencies:** F10, F11

---

## Goal

Implement the `POST /analyze/single` endpoint. This is the primary API surface. It accepts a single drone state vector, runs the full analysis pipeline (trajectory → physics → casualty → scoring), and returns the scored trajectory with the recommended engagement point.

---

## Acceptance Criteria

- [ ] `POST /analyze/single` returns HTTP 200 with the correct response schema on valid input
- [ ] All validation rules from `/spec/inputs-outputs.md` are enforced (invalid inputs return HTTP 422)
- [ ] Response includes `trajectory_scores`, `recommended_engagement`, `impact_distributions`, and `metadata`
- [ ] Response time < 2 s in integration tests (with synthetic in-memory data)
- [ ] If data is not loaded, returns HTTP 503 with a clear error message
- [ ] `drone_id` is echoed in the response
- [ ] `computed_at_utc` is a valid ISO 8601 timestamp
- [ ] `pytest tests/integration/test_api_single.py` passes

---

## Request Schema

From `/spec/inputs-outputs.md`:

```python
class TrajectoryInput(BaseModel):
    lat: float
    lon: float
    altitude_m: float = Field(gt=0, le=10_000)
    heading_deg: float = Field(ge=0, lt=360)
    speed_m_s: float = Field(ge=20, le=300)

class SingleDroneRequest(BaseModel):
    drone_id: str | None = None
    trajectory: TrajectoryInput
    max_range_m: int = Field(default=250_000, ge=1_000, le=1_000_000)
    evaluation_spacing_m: int = Field(default=500, ge=100, le=5_000)
    include_heatmap: bool = False
```

---

## Response Schema

```python
class ModeBreakdown(BaseModel):
    weight: float
    expected_casualties: float
    cep_m: float

class TrajectoryPointScore(BaseModel):
    point_index: int
    lat: float
    lon: float
    altitude_m: float
    distance_from_current_m: float
    expected_casualties: float
    engagement_score: float
    breakdown: dict[str, ModeBreakdown]
    miss_branch_expected_casualties: float

class ImpactEllipseSchema(BaseModel):
    centre_lat: float
    centre_lon: float
    semi_major_m: float
    semi_minor_m: float
    orientation_deg: float

class ImpactDistributionSchema(BaseModel):
    point_index: int
    mode: str
    impact_ellipse: ImpactEllipseSchema

class RecommendedEngagementSchema(BaseModel):
    point_index: int
    lat: float
    lon: float
    altitude_m: float
    distance_from_current_m: float
    expected_casualties: float
    engagement_score: float
    reasoning: str

class MetadataSchema(BaseModel):
    n_trajectory_points: int
    n_monte_carlo_samples: int
    simulation_time_ms: float
    population_dataset: str
    infrastructure_dataset: str

class SingleDroneResponse(BaseModel):
    drone_id: str | None
    computed_at_utc: str
    recommended_engagement: RecommendedEngagementSchema
    trajectory_scores: list[TrajectoryPointScore]
    impact_distributions: list[ImpactDistributionSchema]
    metadata: MetadataSchema
```

Define request and response schemas in `src/droneimpact/api/schemas.py`.

---

## Implementation Steps

### 1. src/droneimpact/api/analyze.py

```python
from fastapi import APIRouter, Request, HTTPException
from droneimpact.api.schemas import SingleDroneRequest, SingleDroneResponse
from droneimpact.api import get_app_state
from droneimpact.physics.trajectory import discretise_trajectory
from droneimpact.physics.types import StateVector
from droneimpact.casualty.engine import CasualtyEngine
from droneimpact.scoring.engine import ScoringEngine
from datetime import datetime, timezone
import time

router = APIRouter(prefix="/analyze")

@router.post("/single", response_model=SingleDroneResponse)
async def analyze_single(request_body: SingleDroneRequest, request: Request) -> SingleDroneResponse:
    state = get_app_state(request)

    if not state.data_loaded:
        raise HTTPException(status_code=503, detail="Data not loaded. Check /health.")

    t_start = time.perf_counter()

    sv = StateVector(
        lat=request_body.trajectory.lat,
        lon=request_body.trajectory.lon,
        altitude_m=request_body.trajectory.altitude_m,
        heading_deg=request_body.trajectory.heading_deg,
        speed_m_s=request_body.trajectory.speed_m_s,
    )
    trajectory = discretise_trajectory(
        sv,
        spacing_m=request_body.evaluation_spacing_m,
        max_range_m=request_body.max_range_m,
    )

    casualty_engine = CasualtyEngine(
        population=state.population,
        infrastructure=state.infrastructure,
        config=state.config.casualty,
    )
    scoring_engine = ScoringEngine(config=state.config)

    result = scoring_engine.score_trajectory(
        trajectory=trajectory,
        dem=state.dem,
        casualty_engine=casualty_engine,
        intercept_point_origin=(sv.lat, sv.lon),
    )

    elapsed_ms = (time.perf_counter() - t_start) * 1000

    return _build_response(request_body, result, elapsed_ms, state.config)


def _build_response(req, result, elapsed_ms, config) -> SingleDroneResponse:
    """Map internal TrajectoryResult to the API response schema."""
    ...
```

The `_build_response` function maps each `PointScore` to a `TrajectoryPointScore`, builds the `RecommendedEngagementSchema`, and assembles `MetadataSchema`.

### 2. Register router in main.py

```python
from droneimpact.api.analyze import router as analyze_router
app.include_router(analyze_router)
```

---

## Tests

### tests/integration/test_api_single.py

Use the same patching approach as F11 to inject mock data, then call the real API.

```python
VALID_REQUEST = {
    "drone_id": "test-001",
    "trajectory": {
        "lat": 48.3794,
        "lon": 31.1656,
        "altitude_m": 400,
        "heading_deg": 315.0,
        "speed_m_s": 51.4
    },
    "max_range_m": 10000,
    "evaluation_spacing_m": 1000
}

@pytest.fixture
async def client(mock_dem, mock_population, mock_infra):
    # Reuse mocks from F11 test conftest
    ...  # patch + create_app + AsyncClient

async def test_single_returns_200(client):
    resp = await client.post("/analyze/single", json=VALID_REQUEST)
    assert resp.status_code == 200

async def test_single_response_schema(client):
    resp = await client.post("/analyze/single", json=VALID_REQUEST)
    body = resp.json()
    assert "recommended_engagement" in body
    assert "trajectory_scores" in body
    assert "impact_distributions" in body
    assert "metadata" in body
    assert body["drone_id"] == "test-001"

async def test_single_recommended_engagement_valid(client):
    resp = await client.post("/analyze/single", json=VALID_REQUEST)
    rec = resp.json()["recommended_engagement"]
    assert 0.0 <= rec["lat"] <= 90.0
    assert rec["engagement_score"] >= 0.0
    assert len(rec["reasoning"]) > 5

async def test_single_trajectory_ordered(client):
    resp = await client.post("/analyze/single", json=VALID_REQUEST)
    scores = resp.json()["trajectory_scores"]
    distances = [s["distance_from_current_m"] for s in scores]
    assert distances == sorted(distances)

async def test_single_invalid_altitude(client):
    bad = {**VALID_REQUEST, "trajectory": {**VALID_REQUEST["trajectory"], "altitude_m": -10}}
    resp = await client.post("/analyze/single", json=bad)
    assert resp.status_code == 422

async def test_single_invalid_heading(client):
    bad = {**VALID_REQUEST, "trajectory": {**VALID_REQUEST["trajectory"], "heading_deg": 400}}
    resp = await client.post("/analyze/single", json=bad)
    assert resp.status_code == 422

async def test_single_invalid_speed(client):
    bad = {**VALID_REQUEST, "trajectory": {**VALID_REQUEST["trajectory"], "speed_m_s": 5}}
    resp = await client.post("/analyze/single", json=bad)
    assert resp.status_code == 422

async def test_single_503_when_data_not_loaded():
    # App without patched data loading
    from droneimpact.main import create_app
    app = create_app()
    with patch("droneimpact.main.DEMIndex.load_from_file",
               side_effect=FileNotFoundError):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/analyze/single", json=VALID_REQUEST)
    assert resp.status_code == 503

async def test_single_computed_at_utc_format(client):
    resp = await client.post("/analyze/single", json=VALID_REQUEST)
    ts = resp.json()["computed_at_utc"]
    datetime.fromisoformat(ts)  # raises ValueError if not valid ISO 8601

async def test_metadata_fields(client):
    resp = await client.post("/analyze/single", json=VALID_REQUEST)
    meta = resp.json()["metadata"]
    assert meta["n_monte_carlo_samples"] == 10000
    assert meta["simulation_time_ms"] > 0
    assert meta["n_trajectory_points"] > 0
```

---

## Notes

- `include_heatmap` (GeoJSON output) is in the schema but returns `null` in v1 — the field is reserved for a later version. Document this in the spec.
- The `population_dataset` and `infrastructure_dataset` fields in `MetadataSchema` should be filled from config (file paths) in v1; in v2 they will carry dataset version strings from the files themselves.
- The `evaluation_spacing_m=1000` in the test (instead of default 500) reduces the number of trajectory points and makes integration tests faster.
