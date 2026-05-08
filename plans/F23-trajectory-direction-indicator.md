# F23 — Trajectory Direction Indicator

**Status:** pending
**Branch:** `feature/F23-trajectory-direction`
**Dependencies:** F15

---

## Goal

Add visual direction-of-travel indicators to the trajectory line on all maps in the dashboard. Currently the trajectory is drawn as a plain polyline with start (green) and end (red) markers, but there is no indication of which direction the drone is flying along the line. For long trajectories spanning hundreds of kilometers, it is not obvious which end is the start and which is the end — especially when zoomed in to a section of the trajectory where the endpoint markers are not visible.

Direction arrows along the trajectory give the operator an immediate sense of the flight path direction at any zoom level.

---

## Acceptance Criteria

- [ ] The trajectory line on all maps (trajectory map, fallout map, coloured trajectory, batch map) shows direction of travel
- [ ] Direction is indicated by arrow markers placed at regular intervals along the trajectory line
- [ ] Arrows point in the direction of drone travel (from current position toward the target)
- [ ] Arrows are spaced so that at least 2–3 are visible at any reasonable zoom level
- [ ] Arrows do not clutter the map — they are subtle (small, semi-transparent) but clearly directional
- [ ] The start marker (green) and end marker (red) remain as they are
- [ ] Arrow style is consistent across all map types (trajectory, fallout, batch)
- [ ] Works for trajectories with as few as 2 points and as many as 500
- [ ] Existing unit and integration tests continue to pass

---

## Implementation Steps

### 1. Evaluate Folium direction options

Two viable approaches:

**Option A — `folium.plugins.AntPath`:**
Replaces `folium.PolyLine` with `AntPath`, which renders an animated dashed line that "flows" in the direction of travel. This is the simplest approach — one line of code change per map.

Pros: zero custom code, built-in Folium plugin, visually clear direction.
Cons: animated lines may be distracting; cannot control arrow shape; visual style may clash with the existing colour-coded trajectory (which draws individual segments with different colours).

**Option B — Arrow markers at intervals:**
Keep the existing polyline and add small arrow-head markers at regular intervals along the trajectory. Each arrow is a `folium.RegularPolygonMarker` (triangle) rotated to match the local heading at that point.

Pros: works with colour-coded trajectory segments; non-animated; more control over appearance.
Cons: more code; must compute heading at each arrow position.

**Recommendation:** Use Option B for the colour-coded trajectory (`make_coloured_trajectory`) and the fallout map (since they use per-segment colouring that `AntPath` would override). Use Option A for `make_trajectory_map` and `make_batch_map` where the trajectory is a single-colour polyline — unless the visual inconsistency is jarring, in which case use Option B everywhere.

Evaluate both during implementation. If `AntPath` works well visually, prefer it for simplicity.

### 2. Implement arrow placement logic

Add to `components.py`:

```python
def add_direction_arrows(
    map_obj: folium.Map,
    trajectory_points: list[dict],
    colour: str = "#3b82f6",
    interval: int = 5,
    group: folium.FeatureGroup | None = None,
) -> None:
```

Parameters:
- `trajectory_points`: list of dicts with `lat`, `lon` keys (evaluation points along the trajectory)
- `colour`: arrow fill colour (should match the trajectory line colour)
- `interval`: place an arrow every N points (adaptive — see below)
- `group`: Folium feature group to add arrows to (for layer control)

Logic:
1. Compute the total number of points
2. Choose `interval` adaptively: target ~8–12 arrows total regardless of trajectory length. `interval = max(1, len(points) // 10)`
3. For each arrow position, compute the local heading from the previous point to the next point (central difference): `heading = atan2(lon_next - lon_prev, lat_next - lat_prev)`
4. Place a small triangle marker:
   ```python
   folium.RegularPolygonMarker(
       location=[lat, lon],
       number_of_sides=3,
       radius=6,
       rotation=heading_deg,
       color=colour,
       fill=True,
       fill_color=colour,
       fill_opacity=0.7,
       weight=1,
   )
   ```

### 3. Add arrows to `make_trajectory_map`

After drawing the trajectory polyline and evaluation point markers, call `add_direction_arrows` with the trajectory points. Add the arrows to the "Trajectory" feature group so they toggle with the trajectory layer.

### 4. Add arrows to `make_coloured_trajectory`

After drawing the colour-coded segments, call `add_direction_arrows`. Use a neutral colour (e.g. `#374151` dark grey) so the arrows are visible against any segment colour.

### 5. Add arrows to `make_batch_map`

For each drone's trajectory, call `add_direction_arrows` with that drone's colour. Add to the drone's feature group.

### 6. Add arrows to `make_impact_focus_map` (if F22 creates one)

If F22 introduces a separate impact-focus map, add arrows there too. If F23 is implemented before F22, just cover the existing maps.

### 7. Testing

`tests/unit/test_direction_arrows.py`:

```python
def test_arrow_count_scales_with_trajectory_length():
    """Arrow count stays in 8-12 range for trajectories of varying length."""

def test_arrow_heading_matches_trajectory_direction():
    """Arrow rotation angle points from start toward end of trajectory."""

def test_arrows_added_to_map():
    """Calling add_direction_arrows adds RegularPolygonMarker children to the map."""

def test_short_trajectory_gets_arrows():
    """A trajectory with only 2-3 points still gets at least one arrow."""
```

---

## Notes

- `folium.RegularPolygonMarker` with `number_of_sides=3` creates a triangle. The `rotation` parameter rotates it in degrees. By default the triangle points up (north); rotation of 0° = north, 90° = east, etc. The heading computation must account for this orientation.
- The arrows should be added to the same feature group as the trajectory line so they respect the layer toggle in the layer control.
- For the batch map, each drone already has its own feature group — add that drone's direction arrows to the same group.
- `AntPath` alternative: if during implementation `AntPath` looks good on the single-colour maps, it can be used as `folium.plugins.AntPath(coords, color=colour, weight=3, delay=1000)`. It animates a flowing dash pattern that implies direction. Test with the actual map to see if the animation is helpful or distracting.
- Arrow size (radius=6) and opacity (0.7) should be tuned visually during implementation. The goal is "visible when you look for them, not distracting when you don't."
