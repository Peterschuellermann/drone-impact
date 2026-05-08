from __future__ import annotations

import numpy as np

from droneimpact.config import CasualtyBand, CasualtyConfig
from droneimpact.data.infrastructure import InfrastructureIndex
from droneimpact.data.population import PopulationIndex


class CasualtyEngine:
    def __init__(
        self,
        population: PopulationIndex,
        infrastructure: InfrastructureIndex,
        config: CasualtyConfig,
    ):
        self._pop = population
        self._infra = infrastructure
        self._config = config

    @staticmethod
    def _lookup_band_probability(
        bands: list[CasualtyBand], distance: float
    ) -> float:
        """Return the probability for a given distance from sorted bands.

        Each band defines a radius threshold; the probability applies to the
        region *inside* that radius.  For a given distance, find the first band
        whose ``radius_m`` exceeds the distance and return its probability.
        If the distance exceeds all band radii, return 0.
        """
        for band in bands:
            if band.radius_m > distance:
                return band.probability
        return 0.0

    def _compute_banded(self, impact_points_wgs84: np.ndarray) -> np.ndarray:
        """Stepped multi-band casualty model.

        Uses configurable blast_bands and frag_bands to compute expected
        casualties in concentric annular rings, combining blast and
        fragmentation probabilities via the union formula.
        """
        if impact_points_wgs84.shape[0] == 0:
            return np.array([], dtype=np.float64)

        lats = impact_points_wgs84[:, 0]
        lons = impact_points_wgs84[:, 1]

        blast_bands = self._config.blast_bands
        frag_bands = self._config.frag_bands

        # Collect all unique radii from both band sets, sorted ascending
        all_radii = sorted(
            {b.radius_m for b in blast_bands} | {b.radius_m for b in frag_bands}
        )

        # Query cumulative population at each radius
        pop_within: dict[float, np.ndarray] = {}
        for r in all_radii:
            pop_within[r] = self._pop.query_batch(lats, lons, r)

        # Accumulate casualties per annular ring
        n = len(lats)
        raw = np.zeros(n, dtype=np.float64)
        prev_pop = np.zeros(n, dtype=np.float32)
        prev_radius = 0.0

        for r in all_radii:
            ring_pop = np.maximum(pop_within[r] - prev_pop, 0.0)

            # Mid-point of the annular ring determines which band applies
            mid = (prev_radius + r) / 2.0
            p_blast = self._lookup_band_probability(blast_bands, mid)
            p_frag = self._lookup_band_probability(frag_bands, mid)
            p_combined = 1.0 - (1.0 - p_blast) * (1.0 - p_frag)

            raw += ring_pop * p_combined
            prev_pop = pop_within[r]
            prev_radius = r

        infra_penalties = self._infra.penalty_batch(lats, lons)
        return (raw * (1.0 + infra_penalties)).astype(np.float64)

    def compute_per_point(self, impact_points_wgs84: np.ndarray) -> np.ndarray:
        """
        impact_points_wgs84: (N, 2) array of [lat, lon]
        Returns: (N,) array of expected casualties per impact point.
        """
        if self._config.blast_bands and self._config.frag_bands:
            return self._compute_banded(impact_points_wgs84)

        if impact_points_wgs84.shape[0] == 0:
            return np.array([], dtype=np.float64)

        lats = impact_points_wgs84[:, 0]
        lons = impact_points_wgs84[:, 1]

        blast = self._config.blast
        frag = self._config.fragmentation

        # Population in concentric rings (blast radii nest inside frag radii)
        pop_0_blast_lethal = self._pop.query_batch(lats, lons, blast.lethal_radius_m)
        pop_0_blast_injury = self._pop.query_batch(lats, lons, blast.injury_radius_m)
        pop_0_frag_lethal = self._pop.query_batch(lats, lons, frag.lethal_radius_m)
        pop_0_frag_danger = self._pop.query_batch(lats, lons, frag.danger_radius_m)

        ring_blast_lethal = pop_0_blast_lethal
        ring_blast_injury = np.maximum(pop_0_blast_injury - pop_0_blast_lethal, 0.0)
        ring_frag_only = np.maximum(pop_0_frag_lethal - pop_0_blast_injury, 0.0)
        ring_frag_danger = np.maximum(pop_0_frag_danger - pop_0_frag_lethal, 0.0)

        # Combined probability per zone using union: P = 1 - (1-P_blast)(1-P_frag)
        p_zone1 = 1.0 - (1.0 - blast.p_lethal) * (1.0 - frag.p_frag_lethal)
        p_zone2 = 1.0 - (1.0 - blast.p_injury) * (1.0 - frag.p_frag_lethal)

        raw = (
            ring_blast_lethal * p_zone1
            + ring_blast_injury * p_zone2
            + ring_frag_only * frag.p_frag_lethal
            + ring_frag_danger * frag.p_frag_danger
        )

        infra_penalties = self._infra.penalty_batch(lats, lons)
        return (raw * (1.0 + infra_penalties)).astype(np.float64)

    def compute(self, impact_points_wgs84: np.ndarray) -> float:
        """Returns mean expected casualties over all Monte Carlo samples."""
        per_point = self.compute_per_point(impact_points_wgs84)
        if per_point.size == 0:
            return 0.0
        return float(per_point.mean())
