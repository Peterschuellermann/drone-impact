# F09 — Casualty Engine

**Status:** pending  
**Branch:** `feature/F09-casualty-engine`  
**Dependencies:** F04, F05, F06, F07, F08

---

## Goal

Implement the casualty engine. Given an array of Monte Carlo impact points (from any of the three physics modes), compute the expected casualties at each point. The engine combines:

1. **Blast model** — casualties from the warhead explosion
2. **Fragmentation model** — casualties from shrapnel
3. **Population lookup** — exposed population in the kill/injury zones
4. **Infrastructure penalty** — multiplier for impacts near critical facilities

This is the performance-critical integration layer between physics output and scoring.

---

## Acceptance Criteria

- [ ] `CasualtyEngine.compute(impact_points_wgs84, n_original_samples) -> float` returns expected casualties as a scalar (mean over samples)
- [ ] `CasualtyEngine.compute_per_point(impact_points_wgs84) -> np.ndarray` returns `(N,)` per-sample casualties
- [ ] With zero population and no infrastructure, expected casualties = 0.0
- [ ] Expected casualties scale with population density (double the population → double the casualties, approximately)
- [ ] Infrastructure penalty correctly inflates casualties near critical facilities
- [ ] Runs N=10,000 samples in < 200 ms on a single core (unit test with synthetic data)
- [ ] `pytest tests/unit/test_casualty.py` passes

---

## Casualty Model

From `/spec/casualty-model.md`.

### Blast model

```
lethal_radius_m    = config.casualty.blast.lethal_radius_m     (default: 5 m)
injury_radius_m    = config.casualty.blast.injury_radius_m     (default: 80 m)
tnt_equivalent_kg  = config.casualty.blast.tnt_equivalent_kg   (default: 30 kg)
```

Warhead detonation is assumed with `p_detonate = 1.0` in v1 (see open questions). 

For each impact point, the expected casualties from blast:
```
pop_lethal = population in circle of lethal_radius_m
pop_injury = population in annulus (lethal_radius_m, injury_radius_m)

blast_casualties = pop_lethal * p_lethal + pop_injury * p_injury
```

where `p_lethal = 0.9` (90% of people in lethal zone are casualties) and `p_injury = 0.3` (30% of people in injury zone are casualties). Add these to config as `blast_p_lethal` and `blast_p_injury`.

### Fragmentation model

```
lethal_radius_m  = config.casualty.fragmentation.lethal_radius_m  (default: 200 m)
danger_radius_m  = config.casualty.fragmentation.danger_radius_m  (default: 400 m)
```

For each impact point:
```
pop_frag_lethal = population in circle of frag_lethal_radius_m
pop_frag_danger = population in annulus (frag_lethal_radius_m, frag_danger_radius_m)

frag_casualties = pop_frag_lethal * p_frag_lethal + pop_frag_danger * p_frag_danger
```

where `p_frag_lethal = 0.5`, `p_frag_danger = 0.1`. Add these to config.

### Infrastructure penalty

```
total_casualties_raw = blast_casualties + frag_casualties
infra_penalty        = infrastructure_index.penalty(lat, lon)
total_casualties     = total_casualties_raw * (1.0 + infra_penalty)
```

### Expected casualties

The `compute()` method returns the mean over all N impact samples:
```
E[casualties] = mean(total_casualties[i] for i in 1..N)
```

---

## Implementation Steps

### 1. src/droneimpact/casualty/engine.py

```python
class CasualtyEngine:
    def __init__(self, population: PopulationIndex,
                 infrastructure: InfrastructureIndex,
                 config: CasualtyConfig):
        self._pop    = population
        self._infra  = infrastructure
        self._config = config

    def compute_per_point(self, impact_points_wgs84: np.ndarray) -> np.ndarray:
        """
        impact_points_wgs84: (N, 2) array of [lat, lon]
        Returns: (N,) array of expected casualties per impact point
        """
        lats = impact_points_wgs84[:, 0]
        lons = impact_points_wgs84[:, 1]

        blast    = self._config.blast
        frag     = self._config.fragmentation

        # Population lookups (batch)
        pop_lethal      = self._pop.query_batch(lats, lons, blast.lethal_radius_m)
        pop_injury      = self._pop.query_batch(lats, lons, blast.injury_radius_m)
                          - pop_lethal  # annulus only
        pop_frag_lethal = self._pop.query_batch(lats, lons, frag.lethal_radius_m)
        pop_frag_danger = self._pop.query_batch(lats, lons, frag.danger_radius_m)
                          - pop_frag_lethal

        blast_casualties = (pop_lethal       * blast.p_lethal
                          + pop_injury       * blast.p_injury)
        frag_casualties  = (pop_frag_lethal  * blast.p_frag_lethal
                          + pop_frag_danger  * blast.p_frag_danger)
        raw              = blast_casualties + frag_casualties

        # Infrastructure penalty
        infra_penalties  = self._infra.penalty_batch(lats, lons)

        return raw * (1.0 + infra_penalties)  # (N,)

    def compute(self, impact_points_wgs84: np.ndarray) -> float:
        """Returns mean expected casualties over all Monte Carlo samples."""
        per_point = self.compute_per_point(impact_points_wgs84)
        return float(per_point.mean())
```

**Note on the annulus subtraction:** `query_batch(radius=injury_radius_m) - query_batch(radius=lethal_radius_m)` gives the annulus population. This requires two calls per zone but is simpler than a dedicated annulus query. It can be optimised later if profiling shows it as a bottleneck.

**Config additions required:** Add to `config.yaml` under `casualty.blast`:
```yaml
p_lethal: 0.9
p_injury: 0.3
p_frag_lethal: 0.5
p_frag_danger: 0.1
```

### 2. Impact point conversion

The physics engines return ENU coordinates relative to the intercept point. Before passing to `CasualtyEngine`, the pipeline must convert ENU → WGS84. This conversion lives in the scoring engine (F10), which calls the physics engines and the casualty engine. F09 accepts WGS84 impact arrays only.

---

## Tests

### tests/unit/test_casualty.py

**Fixtures:**
```python
@pytest.fixture
def empty_engines(config):
    pop   = PopulationIndex.from_dict({})
    infra = InfrastructureIndex.from_features([], config.casualty.infrastructure)
    return CasualtyEngine(pop, infra, config.casualty)

@pytest.fixture
def populated_engines(config):
    from tests.fixtures.population_small import make_test_population
    cells = make_test_population(centre_lat=48.0, centre_lon=31.0, pop_density=5000.0)
    pop   = PopulationIndex.from_dict(cells)
    infra = InfrastructureIndex.from_features([], config.casualty.infrastructure)
    return CasualtyEngine(pop, infra, config.casualty)

@pytest.fixture
def infra_engines(config):
    pop = PopulationIndex.from_dict(
        make_test_population(48.0, 31.0, pop_density=5000.0))
    features = [{"type": "Feature",
                 "geometry": {"type": "Point", "coordinates": [31.0, 48.0]},
                 "properties": {"category": "hospital"}}]
    infra = InfrastructureIndex.from_features(features, config.casualty.infrastructure)
    return CasualtyEngine(pop, infra, config.casualty)
```

```python
def test_zero_population_zero_casualties(empty_engines):
    points = np.array([[48.0, 31.0], [48.01, 31.01]], dtype=np.float64)
    assert empty_engines.compute(points) == 0.0

def test_positive_casualties_in_populated_area(populated_engines):
    # 1000 impact points at the populated centre
    points = np.tile([48.0, 31.0], (1000, 1)).astype(np.float64)
    assert populated_engines.compute(points) > 0.0

def test_casualties_scale_with_population(config):
    low_cells  = make_test_population(48.0, 31.0, pop_density=100.0)
    high_cells = make_test_population(48.0, 31.0, pop_density=10000.0)
    infra = InfrastructureIndex.from_features([], config.casualty.infrastructure)
    eng_low  = CasualtyEngine(PopulationIndex.from_dict(low_cells),  infra, config.casualty)
    eng_high = CasualtyEngine(PopulationIndex.from_dict(high_cells), infra, config.casualty)
    points = np.tile([48.0, 31.0], (500, 1)).astype(np.float64)
    assert eng_high.compute(points) > eng_low.compute(points)

def test_infrastructure_inflates_casualties(config, populated_engines, infra_engines):
    points = np.tile([48.0, 31.0], (500, 1)).astype(np.float64)
    base   = populated_engines.compute(points)
    infra  = infra_engines.compute(points)
    assert infra > base

def test_compute_per_point_shape(populated_engines):
    points = np.random.default_rng(0).uniform(size=(200, 2)) * 0.1 + [48.0, 31.0]
    result = populated_engines.compute_per_point(points)
    assert result.shape == (200,)
    assert np.all(result >= 0.0)

def test_performance_10k_samples(populated_engines):
    import time
    rng = np.random.default_rng(42)
    points = rng.uniform(size=(10_000, 2)) * 0.05 + [48.0, 31.0]
    t0 = time.perf_counter()
    populated_engines.compute(points)
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0  # generous limit for unit tests with synthetic data
```

---

## Notes

- The `p_lethal`, `p_injury`, `p_frag_lethal`, `p_frag_danger` constants are rough estimates from blast physics literature for a 30 kg TNT equivalent warhead. They are configurable.
- In v2, `p_detonate` will be < 1.0, which will be multiplied into the blast and frag terms.
- The performance test (< 5 s for 10k samples) uses synthetic H3 data which is much faster than real Kontur. The < 200 ms target from the acceptance criteria is for production data; a separate performance benchmark in `tests/performance/` will assert that with real data.
