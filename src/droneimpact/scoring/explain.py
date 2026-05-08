from __future__ import annotations

from droneimpact.scoring.types import EngagementZone, PointScore


def explain(
    best: PointScore,
    all_scores: list[PointScore],
    zones: list[EngagementZone] | None = None,
    *,
    is_constrained: bool = False,
) -> str:
    if is_constrained:
        return (
            "Engaging before high-risk zone — lower-risk points exist "
            "further along trajectory but require overflying high-density area."
        )

    scores = [ps.engagement_score for ps in all_scores]
    sorted_scores = sorted(scores)
    second_best = sorted_scores[1] if len(sorted_scores) > 1 else None

    nogo_count = 0
    if zones:
        nogo_count = sum(1 for z in zones if z.classification == "no_go")

    if best.expected_casualties < 0.001:
        if nogo_count:
            return (
                f"Very low population in impact zone; minimal civilian risk. "
                f"Trajectory passes through {nogo_count} no-go zone(s)."
            )
        return "Very low population in impact zone; minimal civilian risk."

    if second_best is not None and second_best > 0 and best.engagement_score < second_best * 0.5:
        suffix = ""
        if nogo_count:
            suffix = f" Avoids {nogo_count} no-go zone(s) along trajectory."
        return (
            f"Significantly safer than all other options "
            f"({best.engagement_score:.3f} vs next best {second_best:.3f} expected casualties)."
            f"{suffix}"
        )

    has_infra_penalty = any(
        ps.engagement_score > best.engagement_score * 1.5
        for ps in all_scores
        if ps.point_index != best.point_index
    )
    if has_infra_penalty:
        return (
            "Minimum expected casualties; engaging here avoids "
            "higher-risk points along the trajectory."
        )

    suffix = ""
    if nogo_count:
        suffix = f" Trajectory has {nogo_count} no-go zone(s)."
    return (
        f"Minimum expected casualties along trajectory "
        f"({best.expected_casualties:.3f} expected).{suffix}"
    )
