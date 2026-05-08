# I01 — M2 Powered Phase Duration and Ballistic Transition

## Problem

The M2 (loss of control) mode runs the drone at full power for the entire simulation
(up to `m2_max_time_s = 300 s`). The spec requires the powered phase to last only
`T_power ~ Uniform(1, 10) s`, after which the drone should enter a tumbling ballistic
phase (similar to M3).

Current behaviour: a drone at 400 m AGL with 51.4 m/s cruise speed can fly for
267 seconds (until altitude = 0), covering up to 13.7 km. The spec intends the
powered phase to be brief, followed by a rapid ballistic descent.

## Spec Reference

`spec/physics-model.md`, lines 113–141:
- "Drone remains powered for 1–10 seconds after hit (sampled uniformly)"
- "After power loss or impact with ground: enters tumbling ballistic"
- Angular rates: ω_roll, ω_pitch, ω_yaw described for the powered phase

## Impact

M2 footprints are much larger than intended. This makes the M2 casualty contribution
unrealistically high compared to M1 and M3, and distorts the engagement score formula.

## Proposed Changes

1. Add `m2_power_duration_min_s` (default 1.0) and `m2_power_duration_max_s`
   (default 10.0) to `PhysicsConfig`.
2. Sample `T_power ~ Uniform(min, max)` per Monte Carlo sample.
3. During `t < T_power`: maintain current heading-drift + powered-flight model.
4. After `T_power`: switch to ballistic tumble with drag (reuse M3 drag physics):
   - Kill engine thrust (drone decelerates via drag only)
   - Apply gravity: `v_vert -= g * dt`
   - Apply drag: `a_drag = 0.5 * rho * A_tumble * Cd * |v| / m`
5. Terminate when altitude ≤ 0.

## Testing

- Verify mean M2 range is significantly shorter than current (closer to 1–3 km)
- Existing `test_m2_wider_footprint_than_m1` may need updated bounds
- Add test: M2 with T_power=0 should produce footprint similar to M3
- Performance: ensure M2 doesn't exceed latency budget despite two-phase integration

## Dependencies

None (standalone physics change).
