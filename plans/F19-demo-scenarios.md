# F19 — Demo Scenarios

**Status:** pending
**Branch:** `feature/F19-demo-scenarios`
**Dependencies:** F12, F15

---

## Goal

Provide a library of pre-built drone flight scenarios that demonstrate the system's capabilities using realistic Shahed-136 attack paths. Each scenario defines a drone state vector representing a drone in flight along a known attack corridor from Russia into Ukraine.

Scenarios cover:
- **Land approaches:** from Bryansk, Belgorod, Kursk, and Crimea
- **Sea approaches:** from the Black Sea toward Odesa and the southern coast
- **Target cities:** Kyiv, Odesa, Kharkiv, Dnipro, Mykolaiv, Zaporizhzhia

The dashboard gains a scenario selector that auto-fills the input form and runs the analysis with one click.

---

## Acceptance Criteria

- [ ] At least 6 pre-defined scenarios exist, covering land and sea approaches to major Ukrainian cities
- [ ] Scenarios are defined in `config.yaml` under `scenarios:` — not hard-coded in Python
- [ ] Each scenario has: `name`, `description`, `trajectory` (lat, lon, altitude_m, heading_deg, speed_m_s), and optionally `max_range_m`
- [ ] Dashboard sidebar has a "Demo Scenarios" dropdown above the manual input form
- [ ] Selecting a scenario populates all input fields and auto-submits the analysis
- [ ] "Custom" option in the dropdown allows manual input (current behaviour)
- [ ] Scenario coordinates are geographically accurate (drone starts along a plausible approach corridor, heading toward the target city)
- [ ] Each scenario produces a meaningful analysis result (trajectory crosses areas of varying population density)
- [ ] `pytest tests/unit/test_scenarios.py` passes — validates scenario loading and coordinate sanity

---

## Scenarios

### Land approaches

| # | Name | Start (lat, lon) | Heading | Target | Description |
|---|---|---|---|---|---|
| 1 | Bryansk → Kyiv | 52.0, 33.5 | ~231° | Kyiv | Long-range overland from Russia's Bryansk oblast; crosses low-density terrain then approaches Kyiv metro |
| 2 | Belgorod → Kharkiv | 50.5, 36.8 | ~216° | Kharkiv | Short-range cross-border; urban impact within 80 km |
| 3 | Crimea → Mykolaiv | 46.2, 33.8 | ~302° | Mykolaiv | Overland from northern Crimea through Kherson oblast |
| 4 | Rostov → Dnipro | 48.0, 38.0 | ~283° | Dnipro | East-to-west overland; long flight over Zaporizhzhia oblast |

### Sea approaches

| # | Name | Start (lat, lon) | Heading | Target | Description |
|---|---|---|---|---|---|
| 5 | Black Sea → Odesa | 46.0, 31.5 | ~326° | Odesa | Maritime approach from the south; crosses coastline into dense port city |
| 6 | Black Sea → Kyiv | 45.5, 32.0 | ~349° | Kyiv | Long-range maritime launch; overflies Kherson/Mykolaiv oblasts then north to Kyiv |

All drones use: `altitude_m: 400`, `speed_m_s: 51.4` (standard Shahed-136 cruise parameters).

The implementation agent should verify exact headings by computing the bearing from start to target city centre and adjust if needed.

---

## Implementation Steps

### 1. Add scenario definitions to config.yaml

```yaml
scenarios:
  - name: "Bryansk → Kyiv"
    description: "Overland from Bryansk, Russia — long-range approach to Kyiv"
    trajectory:
      lat: 52.0
      lon: 33.5
      altitude_m: 400
      heading_deg: 231.0
      speed_m_s: 51.4
    max_range_m: 250000
  # ... 5 more scenarios
```

### 2. Extend config schema

In `src/droneimpact/config.py`, add:

```python
class ScenarioConfig(BaseModel):
    name: str
    description: str
    trajectory: TrajectoryInput  # reuse the existing schema
    max_range_m: int = 250000

class AppConfig(BaseModel):
    # ... existing fields ...
    scenarios: list[ScenarioConfig] = []
```

### 3. Add scenario loader utility

In `src/droneimpact/dashboard/utils.py`, add a function that loads scenarios from config and returns them as a list for the dropdown:

```python
def load_scenarios(config_path: str = "config.yaml") -> list[dict]:
    """Load demo scenarios from config. Returns list of {name, description, trajectory, max_range_m}."""
```

### 4. Update dashboard sidebar

In `src/droneimpact/dashboard/app.py`:

- Add a selectbox at the top of the sidebar: "Select Scenario" with options = scenario names + "Custom"
- When a scenario is selected, populate `st.session_state` with its values and auto-submit
- When "Custom" is selected, show the existing manual input form
- Display scenario description below the selector as `st.caption`

### 5. Tests

`tests/unit/test_scenarios.py`:

```python
def test_scenarios_load_from_config():
    """All scenarios parse without error."""

def test_scenario_coordinates_in_bounds():
    """Start positions are within plausible geographic bounds (44-55°N, 22-41°E)."""

def test_scenario_headings_toward_target():
    """Each scenario heading roughly points toward the named target city (within ±30°)."""

def test_scenario_names_unique():
    """No duplicate scenario names."""
```

---

## Notes

- Scenario coordinates place the drone **in flight** along the approach corridor, not at the launch site. The launch phase is not modelled.
- Headings in the table are approximate. The implementation agent should compute exact bearings from start position to target city centre.
- The `max_range_m` should be set so the trajectory extends past the target city, giving the scoring engine a full picture of the approach.
- Without real DEM/population data loaded, the scenarios still function but produce flat-terrain results. The dashboard should note this.
