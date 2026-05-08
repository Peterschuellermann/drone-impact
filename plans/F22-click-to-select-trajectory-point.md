# F22 — Click-to-Select Trajectory Point with Impact Zoom

**Status:** pending
**Branch:** `feature/F22-click-to-select`
**Dependencies:** F21

---

## Goal

Replace the dropdown menu for inspecting evaluation points with direct click interaction on the trajectory map. When the user clicks an evaluation point marker on the map, the dashboard selects that point and zooms to its debris fallout area — centering the map on the impact zone so the operator can see which areas on the ground are at risk.

Currently, the user must scroll through a `st.selectbox` dropdown to pick a point, then scroll down past the trajectory map to see the fallout visualization on a separate map. This disconnects the spatial intuition ("where on the trajectory am I looking?") from the result ("what does the fallout look like here?"). Clicking directly on the map is faster, more intuitive, and keeps the spatial context in one place.

---

## Acceptance Criteria

- [ ] Evaluation point markers on the trajectory map are clickable — clicking one selects it for inspection
- [ ] The `st.selectbox` dropdown for point inspection is removed
- [ ] When a point is clicked, the fallout area map zooms and centers on the impact area (the area covered by the mode ellipses), not the full trajectory
- [ ] The fallout ellipses (M1/M2/M3), combined danger zone, risk zone overlay, and detail panel still render as they do today (F21 functionality preserved)
- [ ] The selected point is visually highlighted on the trajectory map (distinct marker style from unselected points)
- [ ] If no point has been clicked yet, the recommended engagement point is selected by default
- [ ] Clicking a different point replaces the previous selection (no stacking)
- [ ] The selected point index persists across Streamlit reruns (stored in `st.session_state`)
- [ ] Works for trajectories with 10–500 evaluation points
- [ ] Existing unit and integration tests continue to pass

---

## Implementation Steps

### 1. Enable click return from the trajectory map

In `app.py`, the trajectory map is rendered with:

```python
st_folium(traj_map, width="stretch", height=600, returned_objects=[])
```

Change `returned_objects=[]` to capture the last object clicked. `st_folium` returns a dict with `last_object_clicked` or `last_object_clicked_tooltip` when the user clicks a marker. Use this to identify the selected evaluation point.

```python
map_data = st_folium(traj_map, width="stretch", height=600)
```

The returned `map_data` dict contains `last_object_clicked` (lat/lon of the clicked marker) and `last_object_clicked_tooltip` (the tooltip string of the clicked marker).

### 2. Match click to evaluation point

When `map_data["last_object_clicked"]` is not None, match it to the nearest evaluation point:

- Parse the tooltip string to extract the point index directly (the tooltip already contains `"Point {pt['point_index']} | ..."`)
- Alternatively, compute the haversine distance from the click lat/lon to each evaluation point and pick the closest within a tolerance (e.g. 100 m)
- Store the matched point index in `st.session_state["selected_point_idx"]`

Prefer tooltip parsing — it's exact and avoids floating-point matching issues. Add the point index to the tooltip in a parseable format (e.g. prefix `"[P12] Point 12 | ..."` or embed it as a data attribute).

### 3. Remove the dropdown

Remove the `st.selectbox("Inspect evaluation point", ...)` block (app.py lines ~127–143). Replace it with a text indicator showing the currently selected point:

```python
st.caption(f"Selected: Point #{selected_pt['point_index']} — {dist_km:.1f} km from drone (click a point on the map to change)")
```

### 4. Zoom the fallout map to the impact area

Currently the fallout map (`make_coloured_trajectory`) uses `fit_bounds` to show the entire trajectory. When a point is selected, the map should instead zoom to the impact area.

Add a new function or parameter to `make_coloured_trajectory` (or create a new function `make_impact_focus_map`):

```python
def make_impact_focus_map(
    result: dict,
    selected_point: dict,
    impact_data: dict,
) -> folium.Map:
```

This function:
1. Creates a map centered on the selected point's location
2. Draws the full trajectory as a thin background line (for context)
3. Highlights the selected point with a prominent marker
4. Computes the bounding box of all impact ellipses from `impact_data["modes"]` — uses the largest semi-major axis plus a margin to set `fit_bounds`
5. Adds fallout overlay and risk zone overlay as before

The zoom level should be tight enough that individual ellipses are clearly visible, but with enough margin (~20%) to show surrounding context (nearby roads, buildings, terrain).

### 5. Highlight the selected point on the trajectory map

In `make_trajectory_map` (or in `app.py` after map creation), add a visually distinct marker for the selected point:

- Larger radius (12px vs 3-10px for regular points)
- Different colour (#8b5cf6 purple, matching the current selected-point style)
- Thicker border
- Pulsing effect via CSS if feasible with Folium, otherwise just the static highlight

Pass `selected_point_index` to `make_trajectory_map` so it can apply the highlight during rendering, avoiding adding a second marker after the fact (which could cause tooltip conflicts).

### 6. Handle the default selection

On initial load (no click yet), default to the recommended engagement point:

```python
if "selected_point_idx" not in st.session_state:
    st.session_state["selected_point_idx"] = rec_idx
```

### 7. Handle st_folium rerender carefully

`st_folium` causes a Streamlit rerun when the user clicks. This means:
- The click handler updates `session_state`
- Streamlit reruns
- The map re-renders with the new selection

This is the normal Streamlit flow. However, the trajectory map must NOT reset its view on rerun — only the fallout map should zoom to the impact area. Keep the trajectory map's `fit_bounds` on the full trajectory so the user maintains spatial context.

To prevent infinite rerender loops, ensure the `returned_objects` or `key` parameter is set so that `st_folium` doesn't trigger a rerun when the map is re-rendered with the same data.

### 8. Testing

Update existing tests to remove dropdown-related assertions if any exist.

Add to `tests/unit/test_dashboard.py` or a new test file:

```python
def test_match_click_to_evaluation_point():
    """Clicking near an evaluation point selects the correct point index."""

def test_impact_focus_map_bounds():
    """Impact focus map fit_bounds covers all mode ellipses with margin."""

def test_default_selection_is_recommended():
    """When no point has been clicked, the recommended point is selected."""
```

---

## Notes

- `streamlit-folium` returns click data via `last_object_clicked` (a dict with `lat` and `lng`) and `last_object_clicked_tooltip` (string). The tooltip approach is more reliable for matching — coordinates may have floating-point drift between what Folium renders and what it returns.
- The trajectory map and fallout map remain separate: the trajectory map shows the full flight path at overview zoom, while the fallout map zooms to the selected point's impact area. This preserves the spatial overview while giving detail on demand.
- Removing the dropdown simplifies the UI and eliminates the "scroll to find the point, scroll down to see the result" pattern. The click-to-select flow is: see point on map → click it → see impact area immediately below.
- The `st_folium` rerender behavior is the main implementation risk. If clicking causes a full page rerender that resets the trajectory map scroll position, consider using `st_folium`'s `key` parameter and caching the map object to stabilize the view.
