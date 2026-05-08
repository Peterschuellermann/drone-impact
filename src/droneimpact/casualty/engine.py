from __future__ import annotations

import numpy as np

from droneimpact.config import CasualtyConfig
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

    def compute_per_point(self, impact_points_wgs84: np.ndarray) -> np.ndarray:
        """
        impact_points_wgs84: (N, 2) array of [lat, lon]
        Returns: (N,) array of expected casualties per impact point.
        """
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
