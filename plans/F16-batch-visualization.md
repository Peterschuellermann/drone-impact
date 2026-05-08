# F16 — Batch Visualization

**Status:** pending  
**Branch:** `feature/F16-batch-visualization`  
**Dependencies:** F15, F13

---

## Goal

Extend the Streamlit dashboard (F15) with a batch analysis view. An analyst submits multiple drone state vectors at once, the dashboard calls `/analyze/batch`, and displays all results on a shared map with a priority ranking table. Clicking a drone in the table drills down into the single-drone visualisation components built in F15.

---

## Acceptance Criteria

- [ ] Dashboard has a "Batch Analysis" page/tab accessible from the sidebar
- [ ] Batch input accepts multiple drone states via: (a) manual form for up to 5 drones, (b) CSV file upload
- [ ] CSV format: `drone_id,lat,lon,altitude_m,heading_deg,speed_m_s` — one row per drone
- [ ] Calls `/analyze/batch` with `async_=true` for >5 drones; polls `GET /analyze/batch/{batch_id}` with a progress indicator
- [ ] Displays a shared Folium map with all drone trajectories, each in a distinct colour
- [ ] Recommended engagement points for all drones shown on the shared map
- [ ] Priority ranking table below the map: columns `drone_id`, `expected_casualties`, `engagement_score`, `recommended_distance_m`, sorted by expected casualties descending
- [ ] Clicking a row in the table expands a drill-down section that shows the full single-drone visualisation (map, impact scatter, risk profile, stats panel) using F15's `components.py` functions
- [ ] Comparison view: select 2–3 drones via checkboxes, display side-by-side statistics panels
- [ ] Handles partial failures: if some drones error, show successful results and list errors
- [ ] Loading state: spinner with "Analysing N drones…" during API call; for async, show "Processing… polling every 2s"
- [ ] Works with 1–50 drones without UI degradation

---

## Implementation Steps

### 1. Batch input component

Add `batch_input.py` to `src/droneimpact/dashboard/`:

- `render_batch_input() -> list[dict] | None`: renders sidebar form with two input modes
  - **Manual mode:** dynamic form rows (add/remove drone), each row has lat/lon/altitude/heading/speed fields
  - **CSV upload:** `st.file_uploader` accepting `.csv`, parse with `csv.DictReader`, validate required columns and value ranges
- Returns list of drone state dicts matching `SingleDroneRequest.trajectory` schema, or `None` if not yet submitted
- Validate: reject empty list, reject >100 drones, show field-level errors for invalid values

### 2. Batch API call with async polling

Add to `utils.py`:

- `call_batch_api(endpoint: str, drones: list[dict]) -> dict`: POST to `/analyze/batch` with `async_` flag set automatically based on drone count
- For sync responses (≤5 drones): return result directly
- For async responses: poll `GET /analyze/batch/{batch_id}` every 2 seconds, update a `st.progress` bar, timeout after 120 seconds
- Cache with `@st.cache_data(ttl=300)` keyed on sorted drone inputs
- Raise descriptive exceptions on network errors, timeouts, or batch failure

### 3. Shared map

Add to `components.py`:

- `make_batch_map(batch_result: dict) -> folium.Map`: renders all trajectories on one map
  - Assign each drone a colour from a categorical palette (up to 50 distinct colours)
  - Draw trajectory lines per drone, labelled by `drone_id`
  - Show recommended engagement point per drone (star marker in drone's colour)
  - Fit bounds to all trajectories combined with 5 km buffer
  - Layer control to toggle individual drones on/off
  - Legend mapping drone_id to colour

### 4. Priority ranking table

Add to `components.py`:

- `make_priority_table(batch_result: dict) -> pd.DataFrame`: extracts key fields from each drone result
  - Columns: `drone_id`, `expected_casualties`, `engagement_score`, `recommended_distance_m`, `lat`, `lon`
  - Sorted by `expected_casualties` descending
  - Render via `st.dataframe` with row selection enabled

### 5. Drill-down and comparison

In the batch page:

- When user selects a row in the priority table, render F15's `make_trajectory_map`, `make_impact_scatter`, `make_risk_profile`, and `make_stats_panel` for that drone's result in an expander below the table
- Comparison mode: checkboxes in the table select 2–3 drones; display their `make_stats_panel` outputs in side-by-side `st.columns`

### 6. Error handling

- If `batch_result["errors"]` is non-empty, show a warning banner listing failed drone IDs and error messages
- Successful results are still displayed normally
- If all drones fail, show error message with retry button

### 7. Batch page layout

```
┌─────────────────────────────────────────────────────────┐
│  Batch Analysis                                          │
├─────────────────────────────────────────────────────────┤
│ Sidebar: Input Mode Toggle   │  Shared Map (all drones)  │
│ - Manual / CSV Upload        │                           │
│ - Drone list preview         │  Priority Ranking Table   │
│ - Submit button              │  (sortable, selectable)   │
│                              │                           │
│                              │  Drill-down / Comparison  │
│                              │  (expands below table)    │
└─────────────────────────────────────────────────────────┘
```

### 8. Testing

- `tests/unit/test_batch_input.py`: validate CSV parsing (valid, missing columns, bad values, empty)
- `tests/unit/test_batch_components.py`: verify `make_batch_map` and `make_priority_table` with mock batch results containing 1, 5, and 50 drones
- `tests/integration/test_batch_dashboard.py`: mock `/analyze/batch` endpoint, verify full page renders without error, verify drill-down produces valid components

---

## Notes

- Reuses F15's `components.py` functions for drill-down — no duplication of single-drone visualisation logic.
- The batch API already handles up to 100 drones and auto-async >5, so the dashboard just needs to handle the polling pattern.
- Colour assignment is deterministic by drone index so colours are stable across re-renders.
