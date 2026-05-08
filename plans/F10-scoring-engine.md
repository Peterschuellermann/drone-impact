# F10 — Scoring Engine + Explainability

**Status:** pending  
**Branch:** `feature/F10-scoring-engine`  
**Dependencies:** F09

---

## Goal

Implement the scoring engine. For each trajectory point, it:
1. Runs all three physics simulations (M1, M2, M3) to get impact distributions
2. Converts ENU impact points to WGS84
3. Calls the casualty engine to get expected casualties per mode
4. Combines mode casualties into a single engagement score using the formula from the spec
5. Finds the recommended engagement point (argmin)
6. Generates human-readable explainability text

This is the main orchestration layer that ties physics, casualty estimation, and scoring together.

---

## Acceptance Criteria

- [ ] `ScoringEngine.score_trajectory(trajectory, dem, casualty_engine, config) -> TrajectoryResult` returns a complete scored trajectory
- [ ] The recommended engagement point is the trajectory point with the lowest engagement score
- [ ] Engagement score follows the formula from `/spec/engagement-model.md`
- [ ] Miss branch (drone flies full trajectory) is computed and included
- [ ] Per-mode breakdowns are returned
- [ ] Explainability text is generated for the recommended point
- [ ] Impact ellipses (90% confidence) are computed for each mode at the recommended point
- [ ] `pytest tests/unit/test_scoring.py` passes

---

## Scoring Formula

From `/spec/overview.md`:

```
E[casualties | engage at P_i] =
    P_kill × Σ_k ( p(mode_k | hit) × E[casualties | D_k(P_i)] )
  + (1 - P_kill) × E[casualties | drone reaches end of trajectory]
```

Where:
- `P_kill = 0.50` (from config)
- `mode_weights = {propulsion_loss: 0.40, loss_of_control: 0.35, break_apart: 0.25}`
- `D_k(P_i)` = impact distribution from `simulate_m1`, `simulate_m2`, or `simulate_m3`
- Miss branch = casualties if drone completes trajectory and impacts the final point (M1 simulation from final point as a proxy for whole-trajectory impact)

---

## Data Structures

```python
@dataclass
class ModeScore:
    weight: float
    expected_casualties: float
    cep_m: float  # circular error probable — radius containing 50% of impact points

@dataclass
class PointScore:
    point_index: int
    lat: float
    lon: float
    altitude_m: float
    distance_from_start_m: float
    expected_casualties: float
    engagement_score: float
    breakdown: dict[str, ModeScore]
    miss_branch_expected_casualties: float

@dataclass
class ImpactEllipse:
    centre_lat: float
    centre_lon: float
    semi_major_m: float
    semi_minor_m: float
    orientation_deg: float

@dataclass
class ImpactDistribution:
    point_index: int
    mode: str
    impact_ellipse: ImpactEllipse

@dataclass
class RecommendedEngagement:
    point_index: int
    lat: float
    lon: float
    altitude_m: float
    distance_from_current_m: float
    expected_casualties: float
    engagement_score: float
    reasoning: str

@dataclass
class TrajectoryResult:
    trajectory_scores: list[PointScore]
    recommended_engagement: RecommendedEngagement
    impact_distributions: list[ImpactDistribution]
    metadata: dict
```

Define these in `src/droneimpact/scoring/types.py`.

---

## Implementation Steps

### 1. src/droneimpact/scoring/engine.py

```python
class ScoringEngine:
    def __init__(self, config: AppConfig):
        self._config = config

    def score_trajectory(
        self,
        trajectory: list[TrajectoryPoint],
        dem: DEMIndex,
        casualty_engine: CasualtyEngine,
        intercept_point_origin: tuple[float, float],  # (lat, lon) of drone's current pos
        rng: np.random.Generator | None = None,
    ) -> TrajectoryResult:
        ...
```

**Per-evaluation-point logic:**

For each `TrajectoryPoint p_i` in trajectory:
1. Compute `altitude_agl = dem.msl_to_agl(p_i.lat, p_i.lon, p_i.altitude_m)`
2. Run M1, M2, M3 simulations: `enu_points_m1 = simulate_m1(altitude_agl, p_i.heading, N, config)`
3. Convert ENU → WGS84: `wgs84_m1 = enu_to_wgs84_batch(enu_points_m1[:, 0], enu_points_m1[:, 1], p_i.lat, p_i.lon)` where origin is `(p_i.lat, p_i.lon)`
4. Compute casualties: `cas_m1 = casualty_engine.compute(wgs84_m1)`
5. Repeat for M2, M3
6. Compute engagement score: `score = p_kill * (w_m1*cas_m1 + w_m2*cas_m2 + w_m3*cas_m3) + (1-p_kill) * miss_casualties`
7. Build `PointScore`

**Miss branch:**
- Simulate what happens if the drone reaches the last trajectory point and detonates there
- Use M1 simulation from the last trajectory point (propulsion loss → glide to impact) as the terminal event model
- `miss_casualties = casualty_engine.compute(simulate_m1_wgs84(last_point))`
- This is computed once and reused across all evaluation points (it's the same for all)

**Recommended engagement point:**
```python
scores = [ps.engagement_score for ps in point_scores]
best_idx = np.argmin(scores)
recommended = point_scores[best_idx]
```

**Explainability text:**
Generate a short natural-language string from rules. Examples:
- "Low population density; debris falls in open field."
- "Engaging here avoids overflying Mykolaiv suburbs (high density area at index 15)."
- "Optimal: no critical infrastructure within 500 m of impact zone."

Rules (implement as a simple `explain(point_score, all_scores) -> str` function):
1. If `expected_casualties < 0.01`: "Very low population in impact zone."
2. If `expected_casualties < next_best * 0.5`: "Significantly safer than all other engagement points."
3. If this point avoids an infrastructure penalty but later points have one: "Avoids critical infrastructure zone."
4. Default: "Minimum expected casualties along trajectory."

### 2. src/droneimpact/scoring/ellipse.py

**`compute_impact_ellipse(enu_points: np.ndarray) -> ImpactEllipse`**

From a `(N, 2)` ENU point cloud, compute the 90% confidence ellipse:
1. Compute covariance matrix of the ENU points
2. Eigendecompose: `eigenvalues, eigenvectors = np.linalg.eigh(cov)`
3. For 90% confidence: scale factor = `chi2.ppf(0.90, df=2)` ≈ 4.61
4. `semi_major = sqrt(eigenvalues[-1] * scale_factor)`, `semi_minor = sqrt(eigenvalues[0] * scale_factor)`
5. Orientation = angle of major eigenvector from north
6. Convert centre (0, 0) ENU → WGS84 for `centre_lat, centre_lon`

**`compute_cep(enu_points: np.ndarray) -> float`**

Returns radius of the smallest circle containing 50% of impact points (CEP):
```python
ranges = np.sqrt((enu_points**2).sum(axis=1))
return float(np.percentile(ranges, 50))
```

---

## Tests

### tests/unit/test_scoring.py

Use synthetic DEMIndex (flat terrain), synthetic PopulationIndex (moderate urban density), and synthetic InfrastructureIndex (no facilities) for a clean integration test.

```python
@pytest.fixture
def scoring_setup(config):
    dem   = DEMIndex.from_array(np.full((10, 10), 0.0), 30.0, 47.0, 32.0, 49.0)
    cells = make_test_population(48.0, 31.0, pop_density=1000.0, radius_cells=5)
    pop   = PopulationIndex.from_dict(cells)
    infra = InfrastructureIndex.from_features([], config.casualty.infrastructure)
    cas_engine = CasualtyEngine(pop, infra, config.casualty)
    scoring    = ScoringEngine(config)
    sv = StateVector(lat=48.1, lon=31.0, altitude_m=400.0, heading_deg=180.0, speed_m_s=51.4)
    trajectory = discretise_trajectory(sv, spacing_m=500, max_range_m=5000)
    return scoring, trajectory, dem, cas_engine

def test_score_trajectory_returns_correct_structure(scoring_setup):
    scoring, trajectory, dem, cas = scoring_setup
    result = scoring.score_trajectory(trajectory, dem, cas, (48.1, 31.0))
    assert len(result.trajectory_scores) == len(trajectory)
    assert result.recommended_engagement is not None
    assert result.recommended_engagement.point_index < len(trajectory)

def test_recommended_is_minimum_score(scoring_setup):
    scoring, trajectory, dem, cas = scoring_setup
    result = scoring.score_trajectory(trajectory, dem, cas, (48.1, 31.0))
    scores  = [ps.engagement_score for ps in result.trajectory_scores]
    best_score = min(scores)
    assert result.recommended_engagement.engagement_score == pytest.approx(best_score, rel=0.001)

def test_engagement_scores_positive(scoring_setup):
    scoring, trajectory, dem, cas = scoring_setup
    result = scoring.score_trajectory(trajectory, dem, cas, (48.1, 31.0))
    for ps in result.trajectory_scores:
        assert ps.engagement_score >= 0.0

def test_mode_weights_sum_to_one(config):
    w = config.engagement.mode_weights
    total = w.propulsion_loss + w.loss_of_control + w.break_apart
    assert abs(total - 1.0) < 1e-6

def test_reasoning_is_nonempty_string(scoring_setup):
    scoring, trajectory, dem, cas = scoring_setup
    result = scoring.score_trajectory(trajectory, dem, cas, (48.1, 31.0))
    assert isinstance(result.recommended_engagement.reasoning, str)
    assert len(result.recommended_engagement.reasoning) > 10

def test_cep_is_positive(scoring_setup):
    scoring, trajectory, dem, cas = scoring_setup
    result = scoring.score_trajectory(trajectory, dem, cas, (48.1, 31.0))
    for dist in result.impact_distributions:
        assert dist.impact_ellipse.semi_major_m > 0
        assert dist.impact_ellipse.semi_minor_m > 0
        assert dist.impact_ellipse.semi_major_m >= dist.impact_ellipse.semi_minor_m
```

### tests/unit/test_ellipse.py

```python
def test_cep_zero_variance():
    # All points at same location → CEP = 0
    points = np.zeros((1000, 2))
    assert compute_cep(points) == 0.0

def test_ellipse_circular_distribution():
    rng = np.random.default_rng(0)
    points = rng.normal(0, 100, (5000, 2))  # isotropic
    ellipse = compute_impact_ellipse_enu(points)
    # Semi-major and semi-minor should be roughly equal
    ratio = ellipse.semi_major_m / ellipse.semi_minor_m
    assert 0.5 < ratio < 3.0

def test_ellipse_elongated_distribution():
    rng = np.random.default_rng(1)
    # Strong north-south elongation
    east  = rng.normal(0, 50,  5000)
    north = rng.normal(0, 500, 5000)
    points = np.stack([east, north], axis=1)
    ellipse = compute_impact_ellipse_enu(points)
    assert ellipse.semi_major_m > ellipse.semi_minor_m * 3
```

---

## Notes

- Run M1, M2, M3 for each trajectory point. With 500 m spacing and 250 km max range, there are up to 500 evaluation points. At N=10,000 samples each, this is 500 × 3 × 10,000 = 15 M samples total. This is the main performance concern addressed in F14.
- To reduce the trajectory evaluation count in the scoring engine, consider reducing N per point to 1,000 and using full N=10,000 only for the recommended point's final output. This is a v1 optimisation hint — implement if performance tests fail.
