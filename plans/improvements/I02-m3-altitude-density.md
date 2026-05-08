# I02 — M3 Altitude-Dependent Air Density

## Problem

M3 (break apart) uses a constant sea-level air density `ρ = 1.225 kg/m³` for drag
calculations throughout the entire ballistic trajectory. The spec requires an
exponential atmosphere model: `ρ(z) = 1.225 * exp(-z / 8500)`.

At typical engagement altitudes (300–1000 m AGL), the density error is 3.5–11%.
This overestimates drag at altitude and underestimates it near ground level,
shifting the impact footprint closer to the intercept point than it should be.

## Spec Reference

`spec/physics-model.md`, line 22: "altitude-corrected in simulation"
`spec/physics-model.md`, lines 156, 188–191: `ρ(z) = 1.225 * exp(-z / 8500)`

## Proposed Changes

1. Add `atmosphere_scale_height_m: float = 8500.0` to `PhysicsConfig`.
2. In the M3 integration loop, compute altitude-corrected density each timestep:
   ```python
   rho = 1.225 * np.exp(-alt / config.atmosphere_scale_height_m)
   a_drag = 0.5 * rho * A * Cd / mass * spd
   ```
3. This moves `half_rho_A` from a precomputed constant to a per-step computation.
   To preserve vectorisation, compute `rho` as an (N,) array from the `alt` array.

## Performance Impact

One extra `np.exp` call per timestep. With 200 samples and ~100 timesteps, this is
~20k exponentials — negligible compared to the rest of the simulation.

## Testing

- Test: higher altitude produces slightly longer range (less drag at altitude)
- Validate M3 footprint at 1000 m matches expected physics
- Performance regression test: ensure single-drone stays under 500 ms

## Dependencies

None. Should also apply to M2 if/when I01 adds ballistic phase to M2.
