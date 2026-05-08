# I08 — M2 Altitude-Dependent Air Density

## Problem

M2's ballistic phase uses constant sea-level air density (`_RHO = 1.225 kg/m³`), while M3 was updated in I02 to use an exponential atmosphere model `ρ(z) = 1.225 × exp(-z/8500)`. At 1000 m AGL, air density is ~11% lower than sea level, so M2's drag is overestimated at altitude, producing a tighter footprint than physically correct.

## Spec Reference

`spec/physics-model.md` line 22: "Air density (ρ) at sea level — 1.225 kg/m³ — ISA standard; altitude-corrected in simulation"

The spec requires altitude correction. M3 implements this; M2 does not.

## Change

**File:** `src/droneimpact/physics/m2.py`

1. Move the drag pre-factor computation (`half_rho_A_Cd_over_m`) out of the constant section. Split it into a constant part (`0.5 * A * Cd / m`) and a per-step density lookup.
2. Inside the ballistic phase loop body, compute `rho = 1.225 * np.exp(-alt / config.atmosphere_scale_height_m)` and use it for the drag calculation, matching M3's approach.
3. The powered phase does not model drag, so no change needed there.

No config changes required — `atmosphere_scale_height_m` already exists in `PhysicsConfig`.

## Tests

- Add `test_m2_high_altitude_extends_range`: compare mean range at 100 m vs 2000 m AGL. The ratio should exceed 1.1 (same structure as `test_high_altitude_extends_range` in test_physics_m3.py).
- Existing M2 tests should continue to pass (footprints shift slightly due to density correction, but bounds are generous).

## Dependencies

None.
