# F21 — Fallout Area Visualization

**Status:** pending
**Branch:** `feature/F21-fallout-area-visualization`
**Dependencies:** F15, F20

---

## Goal

When the user selects any evaluation point on the trajectory map, the dashboard highlights the potential debris fallout area for that point. This shows the geographic extent of the impact distribution across all three failure modes (M1 propulsion loss, M2 loss of control, M3 break apart), giving the operator an immediate visual sense of which areas on the ground are at risk if the drone is engaged at that point.

Currently the dashboard shows impact ellipses only for the recommended engagement point. This feature extends that to any point the user clicks on.

---

## Acceptance Criteria

- [ ] Clicking or selecting any evaluation point on the trajectory map displays the debris fallout area for that point
- [ ] The fallout area shows three overlaid regions — one per failure mode (M1, M2, M3) — colour-coded to match the existing mode colour scheme (blue/orange/red)
- [ ] Each region is rendered as a filled semi-transparent polygon (90% confidence ellipse) on the map
- [ ] A combined "danger zone" outline encompasses all three mode ellipses, showing the total area at risk
- [ ] A sidebar panel or popup shows the point's statistics: expected casualties, mode breakdown, distance from drone, and whether the point is in a risk zone (from F20)
- [ ] The API provides impact distribution data for all requested points (not just the recommended one)
- [ ] Risk zone segments from F20 are visually highlighted on the trajectory line (red shading or thicker red line)
- [ ] Selecting the recommended engagement point shows the same visualization (no special case)
- [ ] Smooth UX: selecting a new point replaces the previous fallout visualization (no stacking)
- [ ] `pytest tests/unit/test_fallout_viz.py` passes
- [ ] `pytest tests/integration/test_fallout_api.py` passes

---

## Implementation Steps

### 1. Extend the API to return impact distributions for all points

Currently `impact_distributions` contains ellipses for the recommended point only (and refined candidates in two-pass mode). To support interactive selection, the API must return ellipses for every scored point.

In `src/droneimpact/scoring/engine.py`:

- In `_score_all_points()`: set `compute_ellipses=True` for all points (already the case for small trajectories).
- In the two-pass path: compute ellipses during the coarse pass as well as the refine pass. For interpolated (unscored) points, the dashboard will call a lightweight endpoint.

**Alternative — on-demand endpoint:**

Add a new lightweight endpoint that computes the impact distribution for a single trajectory point without re-running the full trajectory scoring:

```
POST /analyze/point-impact
Request:
{
  "lat": float,
  "lon": float,
  "altitude_m": float,
  "heading_deg": float,
  "speed_m_s": float
}
Response:
{
  "modes": {
    "propulsion_loss": { "impact_ellipse": {...}, "expected_casualties": float },
    "loss_of_control": { "impact_ellipse": {...}, "expected_casualties": float },
    "break_apart":     { "impact_ellipse": {...}, "expected_casualties": float }
  },
  "combined_danger_zone": {
    "type": "Polygon",
    "coordinates": [...]  // GeoJSON polygon encompassing all three ellipses
  }
}
```

This keeps the main API response compact while allowing the dashboard to fetch impact data for any point on demand. **Prefer this approach** — it avoids bloating the main response with ellipses for 500 points.

### 2. Implement the point-impact endpoint

In `src/droneimpact/api/analyze.py`:

```python
@router.post("/analyze/point-impact")
async def analyze_point_impact(request: PointImpactRequest) -> PointImpactResponse:
    """Compute impact distribution for a single trajectory point."""
```

This endpoint:
1. Converts MSL altitude to AGL via DEM
2. Runs M1, M2, M3 physics simulations at the given point
3. Computes impact ellipses and casualties for each mode
4. Computes the combined danger zone polygon (convex hull of the three 90% ellipses)
5. Returns the result

It reuses `ScoringEngine._score_point()` with `compute_ellipses=True`. No trajectory scoring, no miss-branch — this is a point query only.

### 3. Add combined danger zone computation

In `src/droneimpact/scoring/ellipse.py`:

```python
def compute_combined_danger_zone(
    ellipses: list[ImpactEllipse],
) -> list[tuple[float, float]]:
    """Compute GeoJSON polygon coordinates encompassing all mode ellipses.
    
    Returns the convex hull of sampled points on all ellipse boundaries.
    """
```

Sample 72 points (every 5°) on each ellipse boundary, take the union, compute the convex hull using `shapely.geometry.MultiPoint.convex_hull`.

### 4. Update dashboard trajectory map for interactive selection

In `src/droneimpact/dashboard/components.py`:

Replace the static Folium evaluation-point markers with clickable markers. When a marker is clicked:

1. Store the selected point index in `st.session_state.selected_point`
2. Call `POST /analyze/point-impact` with the selected point's state vector
3. Render the response:
   - Draw three filled semi-transparent ellipse polygons on the map (one per mode)
   - Draw the combined danger zone outline (dashed black line)
   - Show a detail panel below the map with the point's statistics

**Folium click handling:**

Folium does not support native click callbacks into Streamlit. Options:
- **Option A (recommended):** Add a `st.selectbox` or `st.slider` alongside the map labelled "Select evaluation point" with options = point indices (and distances). Selecting a point triggers the impact query and redraws the map with the fallout overlay.
- **Option B:** Use `streamlit-folium`'s `st_folium()` return value to capture the last clicked marker coordinates, then match to the nearest evaluation point.

Option A is simpler and more reliable. Implement Option A first; Option B can be added later as a UX enhancement.

### 5. Draw fallout ellipses on the map

In `src/droneimpact/dashboard/components.py`, add:

```python
def add_fallout_overlay(
    map_obj: folium.Map,
    impact_response: dict,
    mode_colors: dict = {"propulsion_loss": "blue", "loss_of_control": "orange", "break_apart": "red"},
) -> folium.Map:
    """Draw impact ellipses and combined danger zone on the map."""
```

Each ellipse is drawn as a `folium.Polygon` with:
- 72-point boundary (5° sampling of the parametric ellipse)
- Semi-transparent fill (`fill_opacity=0.2`)
- Solid border with mode colour
- Tooltip showing mode name and expected casualties

The combined danger zone is drawn as a dashed black polygon outline (`dash_array="10 5"`).

### 6. Draw risk zones on the trajectory

Using the `risk_zones` field from F20:

```python
def add_risk_zone_overlay(
    map_obj: folium.Map,
    trajectory_scores: list[dict],
    risk_zones: list[dict],
) -> folium.Map:
    """Highlight high-risk trajectory segments in red."""
```

For each risk zone, draw a thick red polyline over the corresponding trajectory segment.

### 7. Detail panel for selected point

Below the map, show a collapsible panel when a point is selected:

```
Selected Point: #12 (6.0 km from drone)
├── Expected casualties: 0.031
├── High risk: No
├── Mode breakdown:
│   ├── M1 Propulsion loss (40%): 0.012 cas, CEP 850 m
│   ├── M2 Loss of control (35%): 0.025 cas, CEP 2100 m
│   └── M3 Break apart (25%):     0.008 cas, CEP 320 m
└── Risk zone: None (or "Inside risk zone #1")
```

### 8. Tests

`tests/unit/test_fallout_viz.py`:

```python
def test_combined_danger_zone_contains_all_ellipses():
    """Convex hull of three ellipses contains all sampled boundary points."""

def test_ellipse_polygon_generation():
    """72-point polygon approximation of an ellipse is geometrically valid."""

def test_risk_zone_overlay_segments():
    """Risk zone polyline coordinates match the trajectory segment."""
```

`tests/integration/test_fallout_api.py`:

```python
def test_point_impact_endpoint_returns_all_modes():
    """POST /analyze/point-impact returns impact data for all three modes."""

def test_point_impact_ellipses_valid():
    """Returned ellipses have positive semi-major/minor and valid orientation."""

def test_point_impact_combined_zone_is_valid_polygon():
    """combined_danger_zone is a valid GeoJSON polygon."""
```

---

## API Schema Additions

### PointImpactRequest

```json
{
  "lat": 48.3794,
  "lon": 31.1656,
  "altitude_m": 400,
  "heading_deg": 315.0,
  "speed_m_s": 51.4
}
```

Same validation rules as `SingleDroneInput.trajectory`.

### PointImpactResponse

```json
{
  "modes": {
    "propulsion_loss": {
      "weight": 0.40,
      "expected_casualties": 0.12,
      "cep_m": 850,
      "impact_ellipse": {
        "centre_lat": 48.3821,
        "centre_lon": 31.1589,
        "semi_major_m": 1200,
        "semi_minor_m": 400,
        "orientation_deg": 315
      }
    },
    "loss_of_control": { ... },
    "break_apart": { ... }
  },
  "combined_danger_zone": {
    "type": "Polygon",
    "coordinates": [[ [lon1, lat1], [lon2, lat2], ... ]]
  },
  "metadata": {
    "n_monte_carlo_samples": 10000,
    "simulation_time_ms": 42
  }
}
```

---

## Notes

- The `point-impact` endpoint is lightweight — it runs three physics simulations for a single point (~50 ms). No trajectory scoring, no miss-branch computation. This supports interactive use without noticeable latency.
- The combined danger zone polygon is the convex hull of the three ellipse boundaries. It is an overestimate (the true union is non-convex) but simple, fast, and conservative.
- F20 dependency: risk zones are displayed on the trajectory line, but the fallout visualization itself does not require F20. If F21 is implemented before F20, omit the risk zone overlay and add it when F20 lands. However, implementing F20 first is recommended so the full picture is available.
- Ellipse rendering uses parametric sampling (not SVG ellipse elements) because Folium/Leaflet polygons handle rotation and projection more reliably than CSS transforms on map overlays.
