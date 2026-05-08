# F15 — Data Visualization Dashboard

**Status:** pending  
**Branch:** `feature/F15-data-visualization-dashboard`  
**Dependencies:** F12 (Single-Drone REST API)

---

## Goal

Create an interactive Streamlit dashboard that visualizes drone impact analysis results. Displays:
- Drone trajectory with evaluation points
- Population density heatmap (Kontur data)
- Impact zones (Monte Carlo scatter where drone lands if shot down at each point)
- Statistical breakdown (expected casualties, mode probabilities, CEP circles)
- Recommended engagement point highlighted
- Toggleable layers (infrastructure, terrain)

The dashboard consumes output from the `/analyze/single` REST API endpoint and displays all results interactively.

---

## Acceptance Criteria

- [ ] Streamlit app (`src/droneimpact/dashboard/app.py`) starts without errors
- [ ] `streamlit run src/droneimpact/dashboard/app.py` launches on `localhost:8501`
- [ ] Input form accepts drone state (lat, lon, altitude, heading, speed)
- [ ] Calls `/analyze/single` API via httpx (or configurable endpoint)
- [ ] Displays 2D map with:
  - Trajectory line (blue, start point green, end point red)
  - Evaluation point markers (size scaled by casualty risk)
  - Recommended engagement point (star marker, bold red)
  - Population density heatmap overlay (Kontur dataset — pre-loaded GeoJSON)
  - Optional infrastructure layer (OSM POIs)
- [ ] Displays impact scatter plot:
  - Monte Carlo impact points colored by mode (propulsion loss, loss of control, break apart)
  - CEP confidence ellipses per mode
  - Legend and hover tooltips
- [ ] Displays casualty statistics panel:
  - Expected casualties at recommended point
  - Mode breakdown (weight %, expected casualties, CEP)
  - Miss branch expected casualties
  - P_kill and engagement score
- [ ] Displays risk profile chart:
  - Line chart: expected casualties vs. distance along trajectory
  - Highlight recommended point
  - Interactive hover details
- [ ] Cache API responses (5-minute TTL) to avoid duplicate calls during dashboard interaction
- [ ] Error handling: display user-friendly messages if API is unreachable or returns invalid data
- [ ] Export button: save results as GeoJSON (trajectory + impact points + statistics)

---

## Implementation Steps

### 1. Directory structure

Create:
```
src/droneimpact/dashboard/
├── __init__.py
├── app.py                   # Main Streamlit entry point
├── components.py            # Reusable visualization functions
├── data_loader.py           # Load Kontur, OSM, DEM fixture data
└── utils.py                 # Helper functions (caching, API calls, formatting)
```

### 2. Install Streamlit and dependencies

Add to `pyproject.toml` `[project.optional-dependencies]`:
- `dashboard`: streamlit>=1.30, streamlit-folium, folium, branca, requests-cache, geopandas, geojson

Update dev dependencies to include dashboard tools.

### 3. Implement `app.py`

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  DroneImpact Analysis Dashboard                              │
├─────────────────────────────────────────────────────────────┤
│ Input Panel (sidebar)        │  Main Visualization Area      │
│ - Drone State Input Form     │  - 2D Map (Folium)            │
│ - API Endpoint Config        │  - Impact Scatter (Plotly)    │
│ - Submit Button              │  - Risk Profile Chart         │
│                              │  - Statistics Summary         │
│                              │  - Export Button              │
└─────────────────────────────────────────────────────────────┘
```

**Features:**
- Sidebar form: latitude, longitude, altitude_m, heading_deg, speed_m_s, evaluation_spacing_m, max_range_m
- Submit button calls `components.call_api()`
- Use `@st.cache_data(ttl=300)` to cache API responses
- Display loading spinner during API call
- On success: populate all visualization tabs
- On error: display error message with retry button

### 4. Implement `components.py`

**Function: `make_trajectory_map(result: dict) -> folium.Map`**
- Input: `/analyze/single` API response
- Draw Folium map centered on trajectory midpoint
- Add trajectory line (blue LineString)
- Add evaluation point markers (circles, radius/color by casualty)
- Add recommended point (red star, bold)
- Add Kontur population heatmap as GeoJSON layer (pre-loaded from `data/kontur_population.geojson`)
- Optional: add OSM infrastructure layer (POIs from fixture)
- Include layer control (toggle heatmap, infrastructure)
- Zoom: fit bounds to trajectory + 2 km buffer
- Return folium Map object

**Function: `make_impact_scatter(result: dict) -> go.Figure`**
- Input: trajectory_scores[i].breakdown.modes
- For recommended point only: extract Monte Carlo impact points
- Filter by mode (propulsion_loss, loss_of_control, break_apart)
- Create scatter: x=lon, y=lat, color=mode, hover=casualties/CEP
- Add CEP circles (plotly Scattergeo or custom circles)
- Return Plotly Figure

**Function: `make_risk_profile(result: dict) -> go.Figure`**
- X-axis: distance_from_current_m
- Y-axis: expected_casualties
- Line chart across all trajectory_scores
- Highlight recommended point
- Shade by mode (stacked area)
- Return Plotly Figure

**Function: `make_stats_panel(result: dict) -> str`**
- Format recommended engagement stats as markdown
- Show: distance, casualty estimate, mode breakdown, reasoning
- Return markdown string for `st.markdown()`

### 5. Implement `data_loader.py`

- `load_kontur_population() -> dict`: Load pre-cached Kontur GeoJSON from `data/fixtures/kontur_population_ukraine.geojson`
  - If missing, download from Kontur API or use dummy data
  - Return GeoJSON feature collection
- `load_osm_infrastructure() -> dict`: Load fixture OSM POIs (hospitals, police, etc.) from `data/fixtures/osm_poi.geojson`
  - If missing, return empty collection
- `load_dem_fixture() -> np.ndarray`: Optional DEM raster for 3D terrain (future enhancement)

### 6. Implement `utils.py`

- `call_api(endpoint: str, drone_state: dict) -> dict`: 
  - POST to `/analyze/single`
  - Return JSON response or raise exception with user-friendly message
  - Handle network errors, timeouts, invalid responses
- `cache_response(key: str, ttl_sec: int)`: Decorator for `@st.cache_data`
- `format_casualties(num: float) -> str`: Format casualty estimate as "X.XX casualties" or "1 in Y odds"
- `export_geojson(result: dict) -> str`: Convert API response to GeoJSON (trajectory + impact points)

### 7. Configuration

Add to `config.yaml`:
```yaml
dashboard:
  api_endpoint: "http://localhost:8000"
  default_max_range_m: 250000
  default_evaluation_spacing_m: 500
  kontur_population_path: "data/fixtures/kontur_population_ukraine.geojson"
  osm_poi_path: "data/fixtures/osm_poi_ukraine.geojson"
  cache_ttl_sec: 300
```

### 8. Testing

- `tests/integration/test_dashboard_api_calls.py`:
  - Mock `/analyze/single` response
  - Verify components render without error
  - Verify GeoJSON export roundtrips
- `tests/unit/test_components.py`:
  - Verify map/chart generation with sample data
  - Verify stats formatting
  - Verify error handling for malformed API responses

### 9. Documentation

Add to `src/droneimpact/dashboard/README.md`:
```markdown
# DroneImpact Dashboard

## Installation

```bash
pip install -e ".[dashboard]"
```

## Running

```bash
streamlit run src/droneimpact/dashboard/app.py
```

Opens at http://localhost:8501

## Configuration

Edit `config.yaml` to set API endpoint, fixture paths, and cache TTL.

## Data

Requires pre-loaded fixture files:
- `data/fixtures/kontur_population_ukraine.geojson` (population grid)
- `data/fixtures/osm_poi_ukraine.geojson` (infrastructure POIs)

If missing, dummy data is used for demonstration.
```

---

## Notes

- **Prototype data:** If Kontur/OSM fixture files are missing, dashboard displays dummy/synthetic data for demonstration. In production, load from real data sources.
- **API availability:** Assumes `/analyze/single` endpoint is running (separate service or same FastAPI app).
- **Performance:** Caching prevents excessive API calls during interactive exploration. 5-minute TTL balances freshness vs. responsiveness.
- **Future enhancements:** 3D terrain visualization, time-of-day population adjustment, wind overlay, batch mode, export to PDF.

