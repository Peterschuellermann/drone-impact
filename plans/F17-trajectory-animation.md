# F17 — Trajectory Animation

**Status:** pending  
**Branch:** `feature/F17-trajectory-animation`  
**Dependencies:** F15

---

## Goal

Add trajectory animation to the Streamlit dashboard. After a single-drone analysis completes, the user can replay the drone's flight along its trajectory on the map. The drone icon moves from start to end, and at each evaluation point the engagement score and expected casualties update in real time. The recommended engagement point is highlighted when the drone reaches it.

This helps analysts understand how risk changes along the flight path and why a particular engagement point is recommended.

---

## Acceptance Criteria

- [ ] "Replay trajectory" button appears on the single-drone analysis page after results load
- [ ] Clicking replay animates a drone icon moving along the trajectory line on the Folium map
- [ ] Animation speed is controllable: 1×, 2×, 5× real-time, plus a "step" mode that advances one evaluation point per click
- [ ] As the drone moves, a live statistics panel updates: current position, distance along trajectory, expected casualties, engagement score
- [ ] Trajectory line behind the drone is colour-coded by engagement score (green = low risk → red = high risk)
- [ ] When the drone reaches the recommended engagement point, a visual pulse/highlight draws attention to it
- [ ] Pause/resume controls
- [ ] Animation works smoothly for trajectories with 10–500 evaluation points
- [ ] Step mode enables frame-by-frame analysis of individual evaluation points

---

## Implementation Steps

### 1. Animation data preparation

Add to `components.py`:

- `prepare_animation_frames(result: dict) -> list[dict]`: extracts per-point data from `trajectory_scores`
  - Each frame: `{lat, lon, altitude_m, distance_from_current_m, expected_casualties, engagement_score, is_recommended, colour}`
  - `colour`: map `engagement_score` to a green→yellow→red gradient (normalised across the trajectory)
  - Compute inter-point time intervals from `distance_from_current_m` and the drone's speed (from the original request)

### 2. Animated map rendering

Use `streamlit-folium` with Folium's `TimestampedGeoJson` plugin or a custom JavaScript approach:

- **Option A — TimestampedGeoJson:** construct a GeoJSON FeatureCollection where each feature has a `time` property derived from cumulative travel time. Folium renders the animation natively with a timeline slider.
- **Option B — Streamlit component with JavaScript:** if TimestampedGeoJson doesn't support the required interactivity (live stats update, pause/resume), build a lightweight `st.components.v1.html` wrapper that:
  - Renders a Leaflet map with the trajectory
  - Animates a marker along the path using `requestAnimationFrame`
  - Posts the current frame index back to Streamlit via `Streamlit.setComponentValue`

Start with Option A. Fall back to Option B only if the timeline slider doesn't integrate cleanly with Streamlit's reactivity model.

### 3. Colour-coded trajectory line

Add to `components.py`:

- `make_coloured_trajectory(result: dict) -> folium.Map`: draws trajectory as a series of short line segments, each coloured by that evaluation point's engagement score
  - Use `folium.ColorLine` or individual `folium.PolyLine` segments
  - Colour scale: green (#22c55e) at score 0 → yellow (#eab308) at midpoint → red (#ef4444) at max score
  - Add a colour bar legend to the map

### 4. Live statistics panel

During animation, display a panel (outside the map) that updates at each frame:

- Current evaluation point index / total
- Lat/lon and altitude
- Distance from start
- Expected casualties (with bar chart showing mode breakdown)
- Engagement score
- "★ RECOMMENDED" label when at the recommended point

Implement with `st.empty()` containers that are overwritten at each animation step.

### 5. Playback controls

Render below the map:

- **Play/Pause** toggle button
- **Speed** selector: `st.select_slider` with options `["1×", "2×", "5×", "Step"]`
- **Scrubber**: `st.slider` from 0 to N-1 evaluation points, updates map position when dragged
- In step mode, play button becomes "Next →" and "← Prev" buttons

### 6. Recommended point highlight

When the animation reaches the recommended engagement point:

- Pulse effect on the map marker (CSS animation via custom HTML, or a larger/brighter marker)
- Statistics panel border changes to highlight colour
- Brief text callout: "Recommended engagement point — lowest expected casualties"

### 7. Integration with F15 page

- Add a "Replay" section below the existing static analysis results on the single-drone page
- The animated map replaces the static map when replay is active; a "Show static view" button returns to the original F15 map
- Animation state does not affect the cached API response

### 8. Testing

- `tests/unit/test_animation_frames.py`: verify `prepare_animation_frames` produces correct frame count, colours, and timing from a mock `SingleDroneResponse`
- `tests/unit/test_coloured_trajectory.py`: verify `make_coloured_trajectory` returns a valid Folium map with the correct number of line segments and colour range
- `tests/integration/test_animation_page.py`: mock API response, verify replay section renders without error, verify playback controls exist

---

## Notes

- The animation is purely client-side replay of already-computed results — no additional API calls.
- Folium's `TimestampedGeoJson` is the simplest path but may not support live stats updates. Evaluate during implementation and escalate to Option B if needed.
- Performance: for 500 evaluation points, pre-compute all frame data upfront. The map rendering should not re-request tiles on each frame.
