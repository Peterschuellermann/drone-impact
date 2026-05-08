# F20 — Safe Intercept Constraint

**Status:** pending
**Branch:** `feature/F20-safe-intercept-constraint`
**Dependencies:** F10

---

## Goal

Modify the scoring engine so that the recommended engagement point never requires the drone to fly over a high-risk trajectory section to reach it. Currently, the engine picks `argmin(engagement_score)` over all evaluation points — it may recommend waiting for a low-risk point that is far downrange, even if the drone must first overfly a dense city to get there.

The new constraint: a point is only eligible for recommendation if **no preceding point** on the trajectory exceeds a configurable risk threshold. If all points past a certain distance are blocked by an upstream high-risk zone, the engine recommends the best point **before** that zone.

---

## Motivation

A drone can malfunction, be hit by other defences, or deviate from its trajectory at any time. Recommending an engagement point 50 km past a major city assumes the drone will obligingly fly over the city without incident. If the drone crashes over the city before reaching the recommended point, the system's recommendation was actively harmful. The safe-intercept constraint eliminates this failure mode.

---

## Acceptance Criteria

- [ ] New config parameter `engagement.high_risk_threshold` (float, expected casualties) — default `0.5`
- [ ] A trajectory point is flagged `high_risk: true` when its `engagement_score` (hit-branch only, excluding the miss-branch constant) exceeds the threshold
- [ ] The recommended engagement point is chosen from the set of **eligible** points: points where no preceding point (lower index) is high-risk
- [ ] If no eligible points exist (the drone is already over or approaching a high-risk zone with no safe engagement opportunity before it), the engine recommends the point with the lowest score among the first contiguous safe segment, and sets `"constrained": true` in the response
- [ ] The API response includes a new field `risk_zones: [{start_index, end_index, start_distance_m, end_distance_m, peak_expected_casualties}]` listing contiguous high-risk segments
- [ ] The `reasoning` text mentions the constraint when it changes the recommendation (e.g., "Engaging before Kyiv suburbs — later points have lower debris risk but require overflying high-density area")
- [ ] Explainability: when the unconstrained optimum differs from the constrained recommendation, the response includes both: `recommended_engagement` (constrained) and `unconstrained_optimum` (the old argmin, for operator awareness)
- [ ] All existing tests pass — the constraint does not change recommendations when no high-risk zones exist on the trajectory
- [ ] New tests in `tests/unit/test_safe_intercept.py` validate the constraint logic

---

## Risk Threshold Design

The threshold applies to the **hit-branch expected casualties** only, not the full engagement score (which includes the constant miss-branch term):

```
hit_casualties(P_i) = Σ_k ( p_k × C_k(P_i) )
```

This isolates the debris risk from the terminal-impact risk. A point is high-risk when the debris from shooting the drone down there would cause significant casualties — regardless of what happens if the drone is missed.

**Default threshold: 0.5 expected casualties.** This means: if shooting the drone down at this point would, on average, cause 0.5 or more casualties from debris alone, the point is marked high-risk and the system will not recommend waiting past it.

The threshold is configurable. Operators in different contexts may want stricter (0.1) or more permissive (2.0) values.

---

## Implementation Steps

### 1. Add config parameter

In `config.yaml`:
```yaml
engagement:
  p_kill: 0.50
  high_risk_threshold: 0.5  # expected hit-branch casualties above which a point is high-risk
  mode_weights:
    propulsion_loss: 0.40
    loss_of_control: 0.35
    break_apart: 0.25
```

In `src/droneimpact/config.py`, add `high_risk_threshold: float = 0.5` to the engagement config model.

### 2. Add hit-branch casualty field to PointScore

In `src/droneimpact/scoring/types.py`, add to `PointScore`:
```python
hit_branch_expected_casualties: float  # Σ_k(p_k × C_k) — debris risk only, no miss term
high_risk: bool = False                # True when hit_branch exceeds threshold
```

Compute this in `_score_point()` — it is `hit_casualties` (already computed, just not stored).

### 3. Add risk zone detection

In `src/droneimpact/scoring/engine.py`, add a method:

```python
def _find_risk_zones(
    self, point_scores: list[PointScore], threshold: float,
) -> list[dict]:
    """Identify contiguous segments where hit_branch_expected_casualties > threshold."""
```

Returns a list of `{start_index, end_index, start_distance_m, end_distance_m, peak_expected_casualties}`.

### 4. Modify recommendation logic

In both `_score_all_points()` and the two-pass path of `score_trajectory()`:

```python
# After computing all point scores:
threshold = self._config.engagement.high_risk_threshold

# Flag high-risk points
for ps in point_scores:
    ps.high_risk = ps.hit_branch_expected_casualties > threshold

# Build eligible set: points with no high-risk predecessor
eligible = []
blocked = False
for ps in point_scores:
    if ps.high_risk:
        blocked = True
    if not blocked:
        eligible.append(ps)

# Fallback: if no eligible points, use all points before the first high-risk zone
if not eligible:
    eligible = [ps for ps in point_scores if not ps.high_risk][:1] or point_scores[:1]

# Constrained recommendation
best_constrained = min(eligible, key=lambda ps: ps.engagement_score)

# Unconstrained recommendation (existing argmin)
best_unconstrained = min(point_scores, key=lambda ps: ps.engagement_score)

constrained = best_constrained.point_index != best_unconstrained.point_index
```

### 5. Update API response schema

In `src/droneimpact/scoring/types.py` and `src/droneimpact/api/schemas.py`:

Add to `TrajectoryResult`:
```python
risk_zones: list[RiskZone]
unconstrained_optimum: RecommendedEngagement | None  # only present when constrained != unconstrained
```

Add to the trajectory score output per point:
```python
high_risk: bool
```

Add `RiskZone` type:
```python
@dataclass
class RiskZone:
    start_index: int
    end_index: int
    start_distance_m: float
    end_distance_m: float
    peak_expected_casualties: float
```

### 6. Update explainability

In `src/droneimpact/scoring/explain.py`, add a rule:

- If the recommendation was constrained (differs from unconstrained optimum): "Engaging before [risk zone description] — lower-risk points exist further along trajectory but require overflying high-density area (expected casualties {X})."

### 7. Update spec

Update `/spec/engagement-model.md` to document the safe-intercept constraint, the threshold parameter, and the constrained vs. unconstrained recommendation distinction.

### 8. Tests

`tests/unit/test_safe_intercept.py`:

```python
def test_no_high_risk_zones_recommendation_unchanged():
    """When all points are below threshold, constrained == unconstrained."""

def test_high_risk_zone_blocks_downstream_recommendation():
    """When point 5 is high-risk, the recommendation comes from points 0-4."""

def test_constrained_flag_set_when_recommendation_differs():
    """response.unconstrained_optimum is set when the constraint changes the pick."""

def test_risk_zones_detected():
    """Contiguous high-risk segments are correctly identified and returned."""

def test_all_points_high_risk_uses_first_point():
    """Fallback: when no safe point exists, recommend the first (or least-bad) point."""

def test_threshold_configurable():
    """Changing high_risk_threshold changes which points are flagged."""

def test_hit_branch_excludes_miss_term():
    """high_risk flag is based on hit-branch casualties only, not full engagement score."""
```

---

## Notes

- The constraint is a **filter on the recommendation**, not a change to the engagement score formula. All `engagement_score` values in the response remain unchanged — operators see the full risk picture.
- The two-pass scoring path needs care: the coarse pass may miss a high-risk zone between stride points. After the coarse pass, check if any coarse point is high-risk. If so, ensure the refinement pass includes points around the risk zone boundaries.
- The `unconstrained_optimum` field lets operators override the system when they have additional context (e.g., they know the drone will not pass over the city because of air defence coverage upstream).
- The threshold applies to `hit_branch_expected_casualties` (debris-only risk) rather than `engagement_score` (which includes the miss-branch constant). This is deliberate: the miss-branch term is the same for all points and would bias the threshold toward or away from flagging depending on the terminal-impact risk.
