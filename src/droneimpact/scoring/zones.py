from __future__ import annotations

import numpy as np

from droneimpact.config import ScoringConfig
from droneimpact.scoring.types import EngagementZone, PointScore


def classify_zones(
    point_scores: list[PointScore],
    scoring_cfg: ScoringConfig,
) -> list[EngagementZone]:
    if not point_scores:
        return []

    classifications = _classify_points(point_scores, scoring_cfg)
    zones: list[EngagementZone] = []
    zone_start = 0

    for i in range(1, len(point_scores) + 1):
        if i == len(point_scores) or classifications[i] != classifications[zone_start]:
            zone_scores = point_scores[zone_start:i]
            cls = classifications[zone_start]
            zones.append(_build_zone(cls, zone_scores, scoring_cfg))
            zone_start = i

    return zones


def _classify_points(
    point_scores: list[PointScore],
    scoring_cfg: ScoringConfig,
) -> list[str]:
    result = []
    for ps in point_scores:
        if ps.expected_casualties >= scoring_cfg.zone_nogo_threshold:
            result.append("no_go")
        elif ps.expected_casualties >= scoring_cfg.zone_caution_threshold:
            result.append("caution")
        else:
            result.append("clear")
    return result


def _build_zone(
    classification: str,
    scores: list[PointScore],
    scoring_cfg: ScoringConfig,
) -> EngagementZone:
    first = scores[0]
    last = scores[-1]
    casualties = [ps.expected_casualties for ps in scores]
    population = sum(ps.population_within_frag_radius for ps in scores)

    reasons = _generate_reasons(classification, scores, scoring_cfg)

    return EngagementZone(
        classification=classification,
        start_index=first.point_index,
        end_index=last.point_index,
        start_distance_m=first.distance_from_start_m,
        end_distance_m=last.distance_from_start_m,
        start_lat=first.lat,
        start_lon=first.lon,
        end_lat=last.lat,
        end_lon=last.lon,
        peak_expected_casualties=max(casualties),
        mean_expected_casualties=float(np.mean(casualties)),
        population_in_zone=population,
        reasons=reasons,
    )


def _generate_reasons(
    classification: str,
    scores: list[PointScore],
    scoring_cfg: ScoringConfig,
) -> list[str]:
    reasons: list[str] = []
    max_pop = max(ps.population_within_frag_radius for ps in scores)
    peak_cas = max(ps.expected_casualties for ps in scores)

    if classification == "clear":
        if max_pop == 0:
            reasons.append("Unpopulated area; zero civilians within fragmentation radius")
        else:
            reasons.append(f"Low civilian risk; peak population {max_pop:.0f} within frag radius")
    elif classification == "caution":
        reasons.append(f"Population density: up to {max_pop:.0f} persons within frag radius")
        reasons.append(
            f"Expected casualties {peak_cas:.3f} approach caution threshold "
            f"({scoring_cfg.zone_caution_threshold})"
        )
    elif classification == "no_go":
        reasons.append(f"Dense population: up to {max_pop:.0f} persons within frag radius")
        reasons.append(
            f"Expected casualties {peak_cas:.3f} exceed no-go threshold "
            f"({scoring_cfg.zone_nogo_threshold})"
        )

    return reasons
