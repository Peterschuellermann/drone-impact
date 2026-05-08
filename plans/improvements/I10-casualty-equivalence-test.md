# I10 — Banded/Two-Zone Casualty Equivalence Test

## Problem

The casualty engine has two code paths: the banded model (`_compute_banded`) and the legacy two-zone fallback. Both implement the same concept (concentric rings with union probability), but using different data structures and loops. There is no test confirming they produce equivalent results when configured with matching parameters. A regression in either path could go undetected.

## Change

**File:** `tests/unit/test_casualty.py`

Add `test_banded_matches_twozone_when_configured_equivalently`:

1. Configure `blast_bands` and `frag_bands` to match the two-zone model's radii and probabilities exactly:
   - blast_bands: `[{5m, p_lethal}, {80m, p_injury}]`
   - frag_bands: `[{200m, p_frag_lethal}, {400m, p_frag_danger}]`
2. Create two engines: one with these bands, one with `blast_bands=None, frag_bands=None` (two-zone fallback).
3. Run both on the same impact points and assert the results are approximately equal (`pytest.approx(rel=0.1)`).

The tolerance is generous because the two implementations use slightly different ring decomposition (mid-point lookup vs explicit ring assignment), so exact equality is not expected.

## Dependencies

None.
