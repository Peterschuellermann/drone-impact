# Dashboard

## Overview

A Streamlit web application providing interactive visualization of drone engagement analysis. Connects to the DroneImpact API and presents results as maps, charts, and tables. Supports single-drone and batch analysis modes.

---

## Modes

### Single Drone

Sidebar inputs: latitude, longitude, altitude (MSL), heading, speed, evaluation spacing, max range, Monte Carlo sample count (100–5000). Calls `POST /analyze/single` and displays results in four tabs:

| Tab | Content |
|---|---|
| Trajectory Map | Folium map with evaluation points colour-coded by engagement score (green→red), impact ellipses, recommended engagement marker |
| Impact Distribution | Plotly scatter of impact points by mode |
| Risk Profile | Dual-axis chart: expected casualties and engagement score vs distance |
| Statistics | Markdown panel with mode breakdowns, simulation metadata, miss branch casualties |

Below the trajectory map, a fallout inspection panel shows impact ellipses and the combined danger zone for the selected evaluation point. Points are selected by clicking directly on the trajectory map — the clicked point is highlighted and the fallout map zooms to the impact area. The recommended engagement point is selected by default. Selection persists across Streamlit reruns via `st.session_state`.

A trajectory replay slider animates the drone's progress along the trajectory, highlighting the current evaluation point and its score. Frames are pre-computed from the trajectory scores and drone speed.

GeoJSON export is available — outputs trajectory line and evaluation points as a FeatureCollection.

### Batch Analysis

Sidebar includes a Monte Carlo sample count slider (100–5000, default 2000) applied to all drones in the batch. Input via manual form (1–5 drones) or CSV upload (up to 100 drones). Required CSV columns: `lat`, `lon`, `altitude_m`, `heading_deg`, `speed_m_s`. Optional: `drone_id`.

Calls `POST /analyze/batch`. For >5 drones, uses async mode with polling (`GET /analyze/batch/{batch_id}` every 2 seconds, 120s timeout).

Displays:
- **Batch map** — multi-drone trajectories with layer control, each drone in a distinct colour (20-colour palette)
- **Priority table** — all drones ranked by expected casualties (descending)
- **Drill-down** — select a single drone for its full detail view (trajectory map with risk zones, click-to-inspect fallout, GeoJSON export, trajectory replay)
- **Compare** — multi-select up to 3 drones for side-by-side comparison

---

## API Integration

| Function | Endpoint | Behaviour |
|---|---|---|
| `call_api()` | `POST /analyze/single` | Synchronous, 120s timeout |
| `call_batch_api()` | `POST /analyze/batch` | Sync for ≤5 drones; async + polling for >5 |

API URL resolution: `DRONEIMPACT_API_URL` environment variable, falling back to `http://localhost:8000`.

API responses are cached in Streamlit's `@st.cache_data` with a 300-second TTL.

---

## Visualization Components

All rendering functions live in `dashboard/components.py`:

| Function | Returns | Purpose |
|---|---|---|
| `make_trajectory_map()` | `folium.Map` | Evaluation points (clickable), impact ellipses, recommended marker; optional `selected_point_idx` highlights the selected point |
| `make_coloured_trajectory()` | `folium.Map` | Trajectory line with engagement-score colour gradient; optional `zoom_bounds` for fallout zoom |
| `parse_point_index_from_tooltip()` | `int \| None` | Extracts point index from a clicked marker's tooltip string |
| `compute_fallout_bounds()` | `list` | Computes bounding box covering all impact ellipses for a point |
| `make_impact_scatter()` | `plotly.Figure` | Impact point scatter by mode |
| `make_risk_profile()` | `plotly.Figure` | Dual-axis casualties/score vs distance |
| `make_stats_panel()` | Markdown `str` | Summary statistics |
| `make_batch_map()` | `folium.Map` | Multi-drone map with layer control |
| `make_priority_table()` | `list[dict]` | Drones sorted by expected casualties |
| `prepare_animation_frames()` | `list[dict]` | Frame data for trajectory replay |

Colour mapping: `_score_colour()` maps engagement scores to a green→red gradient. `_drone_colour()` assigns colours from a 20-colour palette for batch mode.

---

## File Layout

```
src/droneimpact/dashboard/
├── __init__.py
├── app.py              # Streamlit entry point, page routing
├── components.py       # Map/chart/table rendering functions
├── utils.py            # API calls, formatting, GeoJSON export
├── batch_input.py      # Manual form and CSV upload for batch mode
└── data_loader.py      # Data file loading utilities
```

---

## Configuration

```yaml
dashboard:
  api_endpoint: "http://localhost:8000"    # not actively used; env var takes precedence
  default_max_range_m: 250000
  default_evaluation_spacing_m: 500
  cache_ttl_sec: 300
```

Runtime API URL is controlled by `DRONEIMPACT_API_URL` environment variable. In Docker Compose this is set to `http://api:8000`.

---

## Dependencies

Declared as the `dashboard` extra in `pyproject.toml`:

- `streamlit>=1.30`
- `streamlit-folium>=0.18`
- `folium>=0.16`
- `branca>=0.7`
- `plotly>=5.18`
- `geopandas>=0.14`

---

## Deployment

### Docker Compose

Two services defined in `docker-compose.yml`:

| Service | Image | Port | Purpose |
|---|---|---|---|
| `api` | `Dockerfile` | 8000 | FastAPI backend |
| `dashboard` | `Dockerfile.dashboard` | 8501 | Streamlit frontend |

The dashboard container depends on the API container (healthy condition). Both mount `./data` (read-only) and `config.yaml`.

### Local Development

```bash
pip install -e ".[dashboard]"
streamlit run src/droneimpact/dashboard/app.py
```

Requires the API to be running at `http://localhost:8000` (or set `DRONEIMPACT_API_URL`).

---

## Tests

| Test file | Coverage |
|---|---|
| `tests/unit/test_dashboard_components.py` | Trajectory map, impact scatter, risk profile, stats panel, format helpers, GeoJSON export |
| `tests/unit/test_batch_components.py` | Batch map, priority table, CSV parsing (valid, missing columns, bad values, empty) |
| `tests/unit/test_animation.py` | Animation frame generation, coloured trajectory rendering |

All dashboard tests are unit tests — they verify component output types and content without requiring a running API or Streamlit server.
