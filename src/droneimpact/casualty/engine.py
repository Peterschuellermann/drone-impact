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
        lats = impact_points_wgs84[:, 0]
        lons = impact_points_wgs84[:, 1]

        blast = self._config.blast
        frag = self._config.fragmentation

        # Population lookups
        pop_blast_lethal = self._pop.query_batch(lats, lons, blast.lethal_radius_m)
        pop_blast_zone = self._pop.query_batch(lats, lons, blast.injury_radius_m)
        pop_blast_injury = np.maximum(pop_blast_zone - pop_blast_lethal, 0.0)

        pop_frag_lethal = self._pop.query_batch(lats, lons, frag.lethal_radius_m)
        pop_frag_zone = self._pop.query_batch(lats, lons, frag.danger_radius_m)
        pop_frag_danger = np.maximum(pop_frag_zone - pop_frag_lethal, 0.0)

        blast_cas = (
            pop_blast_lethal * blast.p_lethal
            + pop_blast_injury * blast.p_injury
        )
        frag_cas = (
            pop_frag_lethal * frag.p_frag_lethal
            + pop_frag_danger * frag.p_frag_danger
        )
        raw = blast_cas + frag_cas

        infra_penalties = self._infra.penalty_batch(lats, lons)
        return (raw * (1.0 + infra_penalties)).astype(np.float64)

    def compute(self, impact_points_wgs84: np.ndarray) -> float:
        """Returns mean expected casualties over all Monte Carlo samples."""
        return float(self.compute_per_point(impact_points_wgs84).mean())
