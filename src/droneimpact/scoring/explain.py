from __future__ import annotations

from droneimpact.scoring.types import PointScore


def explain(best: PointScore, all_scores: list[PointScore]) -> str:
    scores = [ps.engagement_score for ps in all_scores]
    sorted_scores = sorted(scores)
    second_best = sorted_scores[1] if len(sorted_scores) > 1 else None

    if best.expected_casualties < 0.001:
        return "Very low population in impact zone; minimal civilian risk."

    if second_best is not None and second_best > 0 and best.engagement_score < second_best * 0.5:
        return (
            f"Significantly safer than all other options "
            f"({best.engagement_score:.3f} vs next best {second_best:.3f} expected casualties)."
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

    return (
        f"Minimum expected casualties along trajectory "
        f"({best.expected_casualties:.3f} expected)."
    )
