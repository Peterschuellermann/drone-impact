from __future__ import annotations

import math

import folium
import plotly.graph_objects as go


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = (math.radians(v) for v in (lat1, lon1, lat2, lon2))
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return math.degrees(math.atan2(x, y)) % 360


def add_direction_arrows(
    map_obj: folium.Map,
    points: list[list[float]],
    color: str = "#3b82f6",
    group: folium.FeatureGroup | None = None,
) -> None:
    if len(points) < 3:
        return

    interval = max(1, len(points) // 10)
    target = group if group is not None else map_obj

    for idx in range(interval, len(points) - 1, interval):
        p0 = points[idx]
        p1 = points[idx + 1] if idx + 1 < len(points) else points[idx]
        bearing = _bearing(p0[0], p0[1], p1[0], p1[1])

        folium.RegularPolygonMarker(
            location=p0,
            number_of_sides=3,
            radius=6,
            rotation=bearing - 90,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.5,
            weight=1,
            opacity=0.5,
        ).add_to(target)


MODE_COLOURS = {
    "propulsion_loss": "#3b82f6",
    "loss_of_control": "#f59e0b",
    "break_apart": "#ef4444",
}

MODE_LABELS = {
    "propulsion_loss": "Propulsion Loss (M1)",
    "loss_of_control": "Loss of Control (M2)",
    "break_apart": "Break Apart (M3)",
}


def _score_colour(score: float, max_score: float) -> str:
    if max_score <= 0:
        return "#22c55e"
    t = min(score / max_score, 1.0)
    if t < 0.5:
        r = int(34 + (234 - 34) * (t / 0.5))
        g = int(197 + (179 - 197) * (t / 0.5))
        b = int(94 + (8 - 94) * (t / 0.5))
    else:
        r = int(234 + (239 - 234) * ((t - 0.5) / 0.5))
        g = int(179 + (68 - 179) * ((t - 0.5) / 0.5))
        b = int(8 + (68 - 8) * ((t - 0.5) / 0.5))
    return f"#{r:02x}{g:02x}{b:02x}"


def _eval_point_tooltip(pt: dict) -> str:
    return (
        f"Point {pt['point_index']} | "
        f"Dist: {pt['distance_from_current_m']:.0f} m | "
        f"Casualties: {pt['expected_casualties']:.3f} | "
        f"Score: {pt['engagement_score']:.3f}"
    )


def parse_point_index_from_tooltip(tooltip: str | None) -> int | None:
    if not tooltip or not tooltip.startswith("Point "):
        return None
    try:
        return int(tooltip.split("|")[0].strip().removeprefix("Point "))
    except (ValueError, IndexError):
        return None


def make_trajectory_map(
    result: dict,
    selected_point_idx: int | None = None,
) -> folium.Map:
    scores = result["trajectory_scores"]
    rec = result["recommended_engagement"]

    mid_idx = len(scores) // 2
    center_lat = scores[mid_idx]["lat"] if scores else rec["lat"]
    center_lon = scores[mid_idx]["lon"] if scores else rec["lon"]

    m = folium.Map(location=[center_lat, center_lon], zoom_start=8, tiles="OpenStreetMap")

    trajectory_group = folium.FeatureGroup(name="Trajectory", show=True)

    coords = [[pt["lat"], pt["lon"]] for pt in scores]
    if coords:
        folium.PolyLine(coords, color="#3b82f6", weight=3, opacity=0.8).add_to(trajectory_group)
        add_direction_arrows(m, coords, color="#3b82f6", group=trajectory_group)

    if scores:
        folium.CircleMarker(
            [scores[0]["lat"], scores[0]["lon"]],
            radius=8, color="#22c55e", fill=True, fill_opacity=1.0,
            tooltip="Start",
        ).add_to(trajectory_group)
        folium.CircleMarker(
            [scores[-1]["lat"], scores[-1]["lon"]],
            radius=8, color="#ef4444", fill=True, fill_opacity=1.0,
            tooltip="End",
        ).add_to(trajectory_group)

    max_cas = max((pt["expected_casualties"] for pt in scores), default=1.0) or 1.0
    eval_group = folium.FeatureGroup(name="Evaluation Points", show=True)
    for pt in scores:
        is_selected = pt["point_index"] == selected_point_idx
        r = 3 + 7 * (pt["expected_casualties"] / max_cas)
        folium.CircleMarker(
            [pt["lat"], pt["lon"]],
            radius=12 if is_selected else r,
            color="#8b5cf6" if is_selected else "#6366f1",
            fill=True,
            fill_opacity=1.0 if is_selected else 0.5,
            weight=4 if is_selected else 2,
            tooltip=_eval_point_tooltip(pt),
        ).add_to(eval_group)

    folium.Marker(
        [rec["lat"], rec["lon"]],
        icon=folium.Icon(color="red", icon="star", prefix="fa"),
        tooltip=(
            f"RECOMMENDED | "
            f"Casualties: {rec['expected_casualties']:.3f} | "
            f"Score: {rec['engagement_score']:.3f}"
        ),
    ).add_to(trajectory_group)

    impact_group = folium.FeatureGroup(name="Impact Ellipses", show=False)
    for dist in result.get("impact_distributions", []):
        if dist["point_index"] != rec["point_index"]:
            continue
        ellipse = dist["impact_ellipse"]
        mode = dist["mode"]
        colour = MODE_COLOURS.get(mode, "#888888")
        folium.Circle(
            [ellipse["centre_lat"], ellipse["centre_lon"]],
            radius=ellipse["semi_major_m"],
            color=colour,
            fill=True,
            fill_opacity=0.15,
            tooltip=f"{MODE_LABELS.get(mode, mode)} CEP",
        ).add_to(impact_group)

    trajectory_group.add_to(m)
    eval_group.add_to(m)
    impact_group.add_to(m)
    folium.LayerControl().add_to(m)

    if coords:
        m.fit_bounds(
            [[min(p[0] for p in coords) - 0.02, min(p[1] for p in coords) - 0.02],
             [max(p[0] for p in coords) + 0.02, max(p[1] for p in coords) + 0.02]]
        )

    return m


def make_impact_scatter(result: dict) -> go.Figure:
    rec = result["recommended_engagement"]
    rec_idx = rec["point_index"]

    fig = go.Figure()

    distributions = [
        d for d in result.get("impact_distributions", [])
        if d["point_index"] == rec_idx
    ]

    for dist in distributions:
        mode = dist["mode"]
        ellipse = dist["impact_ellipse"]
        colour = MODE_COLOURS.get(mode, "#888888")
        label = MODE_LABELS.get(mode, mode)

        n_pts = 60
        angles = [2 * math.pi * i / n_pts for i in range(n_pts + 1)]
        orient_rad = math.radians(ellipse["orientation_deg"])
        lat_per_m = 1 / 111320
        lon_per_m = 1 / (111320 * math.cos(math.radians(ellipse["centre_lat"])))

        lats, lons = [], []
        for a in angles:
            x = ellipse["semi_major_m"] * math.cos(a)
            y = ellipse["semi_minor_m"] * math.sin(a)
            rx = x * math.cos(orient_rad) - y * math.sin(orient_rad)
            ry = x * math.sin(orient_rad) + y * math.cos(orient_rad)
            lats.append(ellipse["centre_lat"] + ry * lat_per_m)
            lons.append(ellipse["centre_lon"] + rx * lon_per_m)

        r_c = int(colour[1:3], 16)
        g_c = int(colour[3:5], 16)
        b_c = int(colour[5:7], 16)
        fill_rgba = f"rgba({r_c},{g_c},{b_c},0.2)"

        fig.add_trace(go.Scattergl(
            x=lons, y=lats,
            mode="lines",
            fill="toself",
            fillcolor=fill_rgba,
            line=dict(color=colour, width=2),
            name=label,
            hoverinfo="name",
        ))

        fig.add_trace(go.Scattergl(
            x=[ellipse["centre_lon"]], y=[ellipse["centre_lat"]],
            mode="markers",
            marker=dict(color=colour, size=8, symbol="x"),
            name=f"{label} centre",
            showlegend=False,
        ))

    fig.add_trace(go.Scattergl(
        x=[rec["lon"]], y=[rec["lat"]],
        mode="markers",
        marker=dict(color="red", size=14, symbol="star"),
        name="Recommended",
    ))

    fig.update_layout(
        title="Impact Distribution at Recommended Point",
        xaxis_title="Longitude",
        yaxis_title="Latitude",
        yaxis=dict(scaleanchor="x", scaleratio=1),
        height=500,
        margin=dict(t=40, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    return fig


def make_risk_profile(result: dict) -> go.Figure:
    scores = result["trajectory_scores"]
    rec = result["recommended_engagement"]

    distances = [pt["distance_from_current_m"] / 1000 for pt in scores]
    casualties = [pt["expected_casualties"] for pt in scores]
    engagement = [pt["engagement_score"] for pt in scores]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=distances, y=casualties,
        mode="lines+markers",
        name="Expected Casualties",
        line=dict(color="#ef4444", width=2),
        marker=dict(size=4),
        hovertemplate="Distance: %{x:.1f} km<br>Casualties: %{y:.4f}<extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=distances, y=engagement,
        mode="lines+markers",
        name="Engagement Score",
        line=dict(color="#3b82f6", width=2),
        marker=dict(size=4),
        yaxis="y2",
        hovertemplate="Distance: %{x:.1f} km<br>Score: %{y:.4f}<extra></extra>",
    ))

    rec_dist = rec["distance_from_current_m"] / 1000
    fig.add_vline(
        x=rec_dist,
        line_dash="dash", line_color="#22c55e", line_width=2,
        annotation_text="Recommended",
        annotation_position="top",
    )

    fig.update_layout(
        title="Risk Profile Along Trajectory",
        xaxis_title="Distance (km)",
        yaxis=dict(title=dict(text="Expected Casualties", font=dict(color="#ef4444")), side="left"),
        yaxis2=dict(
            title=dict(text="Engagement Score", font=dict(color="#3b82f6")),
            side="right", overlaying="y",
        ),
        height=400,
        margin=dict(t=40, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified",
    )

    return fig


def make_stats_panel(result: dict) -> str:
    rec = result["recommended_engagement"]
    scores = result["trajectory_scores"]
    meta = result["metadata"]

    rec_score = None
    for pt in scores:
        if pt["point_index"] == rec["point_index"]:
            rec_score = pt
            break

    lines = [
        "### Recommended Engagement",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Distance | {rec['distance_from_current_m'] / 1000:.1f} km |",
        f"| Position | {rec['lat']:.5f}, {rec['lon']:.5f} |",
        f"| Altitude | {rec['altitude_m']:.0f} m |",
        f"| Expected Casualties | {rec['expected_casualties']:.4f} |",
        f"| Engagement Score | {rec['engagement_score']:.4f} |",
        "",
        f"**Reasoning:** {rec['reasoning']}",
    ]

    if rec_score:
        lines.extend([
            "",
            "### Mode Breakdown",
            "",
            "| Mode | Weight | Expected Casualties | CEP (m) |",
            "|---|---|---|---|",
        ])
        for mode_key, mode_data in rec_score["breakdown"].items():
            label = MODE_LABELS.get(mode_key, mode_key)
            lines.append(
                f"| {label} | {mode_data['weight']:.0%} | "
                f"{mode_data['expected_casualties']:.4f} | "
                f"{mode_data['cep_m']:.0f} |"
            )
        lines.extend([
            "",
            f"**Miss branch casualties:** {rec_score['miss_branch_expected_casualties']:.4f}",
        ])

    lines.extend([
        "",
        "### Simulation Info",
        "",
        f"- **Trajectory points:** {meta['n_trajectory_points']}",
        f"- **Monte Carlo samples:** {meta['n_monte_carlo_samples']}",
        f"- **Simulation time:** {meta['simulation_time_ms']:.0f} ms",
    ])

    return "\n".join(lines)


BATCH_PALETTE = [
    "#3b82f6", "#ef4444", "#22c55e", "#f59e0b", "#8b5cf6",
    "#ec4899", "#06b6d4", "#84cc16", "#f97316", "#6366f1",
    "#14b8a6", "#e11d48", "#a855f7", "#0ea5e9", "#d946ef",
    "#10b981", "#f43f5e", "#7c3aed", "#0891b2", "#65a30d",
]


def _drone_colour(index: int) -> str:
    return BATCH_PALETTE[index % len(BATCH_PALETTE)]


def make_drone_overview_map(
    drones: list[dict],
    selected_idx: int | None = None,
) -> folium.Map:
    if not drones:
        return folium.Map(location=[48.5, 35.0], zoom_start=6)

    m = folium.Map(tiles="OpenStreetMap")
    all_lats, all_lons = [], []

    for i, d in enumerate(drones):
        traj = d.get("trajectory", d)
        lat, lon = traj["lat"], traj["lon"]
        heading = traj["heading_deg"]
        drone_id = d.get("drone_id", f"Drone {i + 1}")
        colour = _drone_colour(i)
        is_selected = (i == selected_idx)

        all_lats.append(lat)
        all_lons.append(lon)

        radius = 10 if is_selected else 6
        weight = 4 if is_selected else 2
        opacity = 1.0 if is_selected else 0.7

        folium.CircleMarker(
            [lat, lon],
            radius=radius,
            color=colour,
            fill=True,
            fill_opacity=opacity,
            weight=weight,
            tooltip=(
                f"{drone_id} | "
                f"Alt: {traj['altitude_m']:.0f}m | "
                f"Hdg: {heading:.0f}° | "
                f"Spd: {traj['speed_m_s']:.1f} m/s"
            ),
        ).add_to(m)

        arrow_len = 0.15
        end_lat = lat + arrow_len * math.cos(math.radians(heading))
        end_lon = lon + arrow_len * math.sin(math.radians(heading)) / math.cos(math.radians(lat))
        folium.PolyLine(
            [[lat, lon], [end_lat, end_lon]],
            color=colour, weight=3 if is_selected else 2, opacity=opacity,
        ).add_to(m)

        folium.Marker(
            [lat, lon],
            icon=folium.DivIcon(
                html=(
                    f'<div style="font-size:9px;font-weight:{"bold" if is_selected else "normal"};'
                    f'color:{colour};text-shadow:1px 1px 2px white,-1px -1px 2px white;'
                    f'white-space:nowrap;">{drone_id}</div>'
                ),
                icon_size=(80, 14),
                icon_anchor=(-5, 14),
            ),
        ).add_to(m)

    if all_lats:
        m.fit_bounds([
            [min(all_lats) - 0.2, min(all_lons) - 0.2],
            [max(all_lats) + 0.2, max(all_lons) + 0.2],
        ])

    return m


def make_batch_map(batch_result: dict, selected_drone_idx: int | None = None) -> folium.Map:
    results = batch_result.get("results", [])
    if not results:
        return folium.Map(location=[48.5, 35.0], zoom_start=6)

    all_lats, all_lons = [], []
    m = folium.Map(tiles="OpenStreetMap")

    for i, drone_result in enumerate(results):
        colour = _drone_colour(i)
        drone_id = drone_result.get("drone_id") or f"Drone {i + 1}"
        scores = drone_result["trajectory_scores"]
        rec = drone_result["recommended_engagement"]
        is_selected = (i == selected_drone_idx)

        line_weight = 5 if is_selected else 3
        line_opacity = 1.0 if is_selected else 0.7

        group = folium.FeatureGroup(name=drone_id, show=True)

        coords = [[pt["lat"], pt["lon"]] for pt in scores]
        if coords:
            folium.PolyLine(coords, color=colour, weight=line_weight, opacity=line_opacity).add_to(group)
            add_direction_arrows(m, coords, color=colour, group=group)
            all_lats.extend(pt["lat"] for pt in scores)
            all_lons.extend(pt["lon"] for pt in scores)

        folium.Marker(
            [rec["lat"], rec["lon"]],
            icon=folium.Icon(color="red", icon="star", prefix="fa"),
            tooltip=f"{drone_id} — Casualties: {rec['expected_casualties']:.3f}",
        ).add_to(group)

        group.add_to(m)

    folium.LayerControl().add_to(m)

    if all_lats:
        m.fit_bounds([
            [min(all_lats) - 0.05, min(all_lons) - 0.05],
            [max(all_lats) + 0.05, max(all_lons) + 0.05],
        ])

    return m


def make_priority_table(batch_result: dict) -> list[dict]:
    results = batch_result.get("results", [])
    rows = []
    for i, dr in enumerate(results):
        rec = dr["recommended_engagement"]
        rows.append({
            "drone_id": dr.get("drone_id") or f"Drone {i + 1}",
            "expected_casualties": round(rec["expected_casualties"], 4),
            "engagement_score": round(rec["engagement_score"], 4),
            "recommended_distance_m": round(rec["distance_from_current_m"], 0),
            "lat": round(rec["lat"], 5),
            "lon": round(rec["lon"], 5),
        })
    rows.sort(key=lambda r: r["expected_casualties"], reverse=True)
    return rows


def prepare_animation_frames(result: dict, speed_m_s: float = 51.4) -> list[dict]:
    scores = result["trajectory_scores"]
    rec_idx = result["recommended_engagement"]["point_index"]
    if not scores:
        return []

    max_score = max(pt["engagement_score"] for pt in scores) or 1.0
    cumulative_time = 0.0

    frames = []
    for i, pt in enumerate(scores):
        if i > 0:
            prev = scores[i - 1]
            dx = pt["distance_from_current_m"] - prev["distance_from_current_m"]
            cumulative_time += max(dx, 0) / speed_m_s

        frames.append({
            "lat": pt["lat"],
            "lon": pt["lon"],
            "altitude_m": pt["altitude_m"],
            "distance_from_current_m": pt["distance_from_current_m"],
            "expected_casualties": pt["expected_casualties"],
            "engagement_score": pt["engagement_score"],
            "is_recommended": pt["point_index"] == rec_idx,
            "colour": _score_colour(pt["engagement_score"], max_score),
            "time_s": cumulative_time,
            "point_index": pt["point_index"],
        })

    return frames


def compute_fallout_bounds(
    point_lat: float,
    point_lon: float,
    impact_response: dict,
) -> list[list[float]]:
    """Compute a [[south, west], [north, east]] bounding box covering the impact ellipses."""
    lat_per_m = 1.0 / 111_320.0
    lon_per_m = 1.0 / (111_320.0 * max(math.cos(math.radians(point_lat)), 0.01))

    max_offset_lat = 500 * lat_per_m
    max_offset_lon = 500 * lon_per_m

    modes = impact_response.get("modes", {})
    for mode_data in modes.values():
        ellipse = mode_data.get("impact_ellipse", {})
        semi_major = ellipse.get("semi_major_m", 0)
        if semi_major <= 0:
            continue
        c_lat = ellipse.get("centre_lat", point_lat)
        c_lon = ellipse.get("centre_lon", point_lon)
        offset_lat = abs(c_lat - point_lat) + semi_major * lat_per_m
        offset_lon = abs(c_lon - point_lon) + semi_major * lon_per_m
        max_offset_lat = max(max_offset_lat, offset_lat)
        max_offset_lon = max(max_offset_lon, offset_lon)

    padding = 1.2
    return [
        [point_lat - max_offset_lat * padding, point_lon - max_offset_lon * padding],
        [point_lat + max_offset_lat * padding, point_lon + max_offset_lon * padding],
    ]


def make_coloured_trajectory(
    result: dict,
    zoom_bounds: list[list[float]] | None = None,
) -> folium.Map:
    scores = result["trajectory_scores"]
    rec = result["recommended_engagement"]

    if not scores:
        return folium.Map(location=[rec["lat"], rec["lon"]], zoom_start=8)

    max_score = max(pt["engagement_score"] for pt in scores) or 1.0
    mid = scores[len(scores) // 2]
    m = folium.Map(location=[mid["lat"], mid["lon"]], zoom_start=8, tiles="OpenStreetMap")

    coords = []
    for i in range(len(scores) - 1):
        a, b = scores[i], scores[i + 1]
        colour = _score_colour(a["engagement_score"], max_score)
        folium.PolyLine(
            [[a["lat"], a["lon"]], [b["lat"], b["lon"]]],
            color=colour, weight=5, opacity=0.9,
        ).add_to(m)
        coords.append([a["lat"], a["lon"]])
    coords.append([scores[-1]["lat"], scores[-1]["lon"]])
    add_direction_arrows(m, coords, color="#374151")

    folium.Marker(
        [rec["lat"], rec["lon"]],
        icon=folium.Icon(color="red", icon="star", prefix="fa"),
        tooltip="Recommended engagement point",
    ).add_to(m)

    if zoom_bounds:
        m.fit_bounds(zoom_bounds)
    else:
        coords = [[pt["lat"], pt["lon"]] for pt in scores]
        m.fit_bounds([
            [min(p[0] for p in coords) - 0.02, min(p[1] for p in coords) - 0.02],
            [max(p[0] for p in coords) + 0.02, max(p[1] for p in coords) + 0.02],
        ])

    return m


def add_fallout_overlay(
    map_obj: folium.Map,
    impact_response: dict,
    mode_colors: dict | None = None,
) -> folium.Map:
    """Draw impact ellipses and combined danger zone on a Folium map.

    Each mode ellipse is rendered as a semi-transparent polygon.
    The combined danger zone is drawn as a dashed black outline.
    """
    if mode_colors is None:
        mode_colors = {
            "propulsion_loss": "#3b82f6",
            "loss_of_control": "#f59e0b",
            "break_apart": "#ef4444",
        }

    fallout_group = folium.FeatureGroup(name="Fallout Area", show=True)

    modes = impact_response.get("modes", {})
    for mode_name, mode_data in modes.items():
        ellipse = mode_data.get("impact_ellipse", {})
        colour = mode_colors.get(mode_name, "#888888")
        label = MODE_LABELS.get(mode_name, mode_name)
        casualties = mode_data.get("expected_casualties", 0.0)

        centre_lat = ellipse.get("centre_lat", 0)
        centre_lon = ellipse.get("centre_lon", 0)
        semi_major = ellipse.get("semi_major_m", 0)
        semi_minor = ellipse.get("semi_minor_m", 0)
        orient_deg = ellipse.get("orientation_deg", 0)

        if semi_major <= 0 or semi_minor <= 0:
            continue

        lat_per_m = 1.0 / 111_320.0
        lon_per_m = 1.0 / (111_320.0 * math.cos(math.radians(centre_lat)))
        orient_rad = math.radians(orient_deg)

        boundary = []
        for i in range(72):
            angle = 2.0 * math.pi * i / 72
            e = semi_major * math.cos(angle)
            n = semi_minor * math.sin(angle)
            re = e * math.sin(orient_rad) + n * math.cos(orient_rad)
            rn = e * math.cos(orient_rad) - n * math.sin(orient_rad)
            lat = centre_lat + rn * lat_per_m
            lon = centre_lon + re * lon_per_m
            boundary.append([lat, lon])

        folium.Polygon(
            locations=boundary,
            color=colour,
            weight=2,
            fill=True,
            fill_color=colour,
            fill_opacity=0.2,
            tooltip=f"{label}: {casualties:.4f} expected casualties",
        ).add_to(fallout_group)

    combined = impact_response.get("combined_danger_zone", {})
    coords = combined.get("coordinates", [])
    if coords and len(coords) > 0 and len(coords[0]) >= 3:
        # GeoJSON coordinates are [lon, lat], Folium needs [lat, lon]
        hull_points = [[c[1], c[0]] for c in coords[0]]
        folium.Polygon(
            locations=hull_points,
            color="#000000",
            weight=2,
            dash_array="10 5",
            fill=False,
            tooltip="Combined danger zone",
        ).add_to(fallout_group)

    fallout_group.add_to(map_obj)
    return map_obj


_CATEGORY_COLOURS = {
    "residential": "#ef4444",
    "industrial": "#f97316",
    "energy": "#eab308",
    "military": "#a855f7",
    "unknown": "#9ca3af",
}


def add_strike_overlay(map_obj: folium.Map, feature_collection: dict) -> folium.Map:
    features = feature_collection.get("features", [])
    if not features:
        return map_obj

    group = folium.FeatureGroup(name="Strike Locations", show=False)
    for feat in features:
        coords = feat.get("geometry", {}).get("coordinates", [None, None])
        lon, lat = coords[0], coords[1]
        if lat is None or lon is None:
            continue
        props = feat.get("properties", {})
        cat = props.get("category", "unknown")
        colour = _CATEGORY_COLOURS.get(cat, "#9ca3af")
        popup_html = (
            f"<b>{props.get('location_name', 'Unknown')}</b><br>"
            f"Date: {props.get('date', '—')}<br>"
            f"Category: {cat}<br>"
            f"Source: {props.get('source', '—')}<br>"
            f"{props.get('description', '')[:120]}"
        )
        folium.CircleMarker(
            location=[lat, lon],
            radius=5,
            color=colour,
            fill=True,
            fill_opacity=0.7,
            weight=1,
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=f"{cat} — {props.get('date', '—')}",
        ).add_to(group)

    group.add_to(map_obj)
    return map_obj


def add_risk_zone_overlay(
    map_obj: folium.Map,
    trajectory_scores: list[dict],
    risk_zones: list[dict],
) -> folium.Map:
    """Highlight high-risk trajectory segments with thick red polyline."""
    if not risk_zones:
        return map_obj

    risk_group = folium.FeatureGroup(name="Risk Zones", show=True)

    score_by_index = {pt["point_index"]: pt for pt in trajectory_scores}

    for rz in risk_zones:
        start_idx = rz["start_index"]
        end_idx = rz["end_index"]
        peak = rz.get("peak_expected_casualties", 0)

        segment_coords = []
        for idx in range(start_idx, end_idx + 1):
            pt = score_by_index.get(idx)
            if pt:
                segment_coords.append([pt["lat"], pt["lon"]])

        if len(segment_coords) >= 2:
            folium.PolyLine(
                segment_coords,
                color="#dc2626",
                weight=8,
                opacity=0.6,
                tooltip=f"Risk zone: peak casualties {peak:.4f}",
            ).add_to(risk_group)

    risk_group.add_to(map_obj)
    return map_obj


SHELTERING_COLOURS = {
    "reinforced_concrete": "#1e40af",
    "masonry": "#b45309",
    "light_structure": "#65a30d",
}

SHELTERING_LABELS = {
    "reinforced_concrete": "Reinforced Concrete",
    "masonry": "Masonry",
    "light_structure": "Light Structure",
}


def add_sheltering_overlay(
    map_obj: folium.Map,
    building_cells: list[dict],
) -> folium.Map:
    if not building_cells:
        return map_obj

    shelter_group = folium.FeatureGroup(name="Building Sheltering", show=False)

    for cell in building_cells:
        cls = cell["protection_class"]
        colour = SHELTERING_COLOURS.get(cls, "#888888")
        label = SHELTERING_LABELS.get(cls, cls)
        boundary = cell["boundary"]
        folium.Polygon(
            locations=boundary,
            color=colour,
            fill=True,
            fill_color=colour,
            fill_opacity=0.35,
            weight=1,
            opacity=0.5,
            tooltip=label,
        ).add_to(shelter_group)

    shelter_group.add_to(map_obj)
    return map_obj


def make_point_detail_panel(point_data: dict, impact_response: dict) -> str:
    """Generate markdown summary for a selected evaluation point."""
    dist_km = point_data.get("distance_from_current_m", 0) / 1000
    idx = point_data.get("point_index", 0)
    high_risk = point_data.get("high_risk", False)

    lines = [
        f"### Selected Point: #{idx} ({dist_km:.1f} km from drone)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Position | {point_data.get('lat', 0):.5f}, {point_data.get('lon', 0):.5f} |",
        f"| Altitude | {point_data.get('altitude_m', 0):.0f} m |",
        f"| Expected Casualties | {point_data.get('expected_casualties', 0):.4f} |",
        f"| High Risk | {'Yes' if high_risk else 'No'} |",
    ]

    modes = impact_response.get("modes", {})
    if modes:
        lines.extend([
            "",
            "### Mode Breakdown",
            "",
            "| Mode | Weight | Expected Casualties | CEP (m) |",
            "|---|---|---|---|",
        ])
        for mode_key, mode_data in modes.items():
            label = MODE_LABELS.get(mode_key, mode_key)
            weight = mode_data.get("weight", 0)
            cas = mode_data.get("expected_casualties", 0)
            cep = mode_data.get("cep_m", 0)
            lines.append(f"| {label} | {weight:.0%} | {cas:.4f} | {cep:.0f} |")

    meta = impact_response.get("metadata", {})
    sim_time = meta.get("simulation_time_ms", 0)
    if sim_time:
        lines.extend([
            "",
            f"*Point impact computed in {sim_time:.0f} ms*",
        ])

    return "\n".join(lines)
