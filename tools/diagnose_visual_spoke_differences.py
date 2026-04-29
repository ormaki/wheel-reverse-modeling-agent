from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from scipy.spatial import cKDTree


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.evaluation_agent import EvaluationAgent


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load(str(path))
    if isinstance(loaded, trimesh.Trimesh):
        return loaded
    if isinstance(loaded, trimesh.Scene):
        meshes = [
            geom
            for geom in loaded.geometry.values()
            if isinstance(geom, trimesh.Trimesh) and len(geom.vertices) > 0
        ]
        if meshes:
            return trimesh.util.concatenate(meshes)
    raise ValueError(f"Unable to load mesh: {path}")


def make_eval_helper(features: Dict[str, Any], seed: int) -> EvaluationAgent:
    agent = object.__new__(EvaluationAgent)
    agent.features = features
    agent.config = {"eval_seed": int(seed)}
    agent.eval_seed = int(seed)
    agent._rng = np.random.default_rng(int(seed))
    agent.stl_mesh = None
    agent.stl_vertices = np.zeros((0, 3), dtype=float)
    agent.step_mesh = None
    agent.step_vertices = np.zeros((0, 3), dtype=float)
    agent.differences = []
    return agent


def sample_mesh(agent: EvaluationAgent, mesh: trimesh.Trimesh, sample_count: int) -> np.ndarray:
    vertices = np.asarray(mesh.vertices, dtype=float)
    return agent._sample_surface_points(mesh, vertices, sample_size=int(sample_count))


def collect_members(features: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for motif in features.get("spoke_motif_sections") or []:
        for member in motif.get("members", []) or []:
            if not isinstance(member, dict):
                continue
            try:
                rows.append(
                    {
                        "member_index": int(member.get("member_index", len(rows))),
                        "slot_index": int(member.get("slot_index", -1)),
                        "feature_angle_deg": float(member.get("angle", 0.0)),
                    }
                )
            except Exception:
                continue
    rows.sort(key=lambda item: int(item["member_index"]))
    return rows


def wrap_angle_deg(values: np.ndarray | float) -> np.ndarray | float:
    return (np.asarray(values) + 180.0) % 360.0 - 180.0


def angle_delta_deg(values: np.ndarray, center_deg: float) -> np.ndarray:
    return np.abs((values - float(center_deg) + 180.0) % 360.0 - 180.0)


def fit_feature_angle_transform(
    members: Sequence[Dict[str, Any]],
    stl_band_2d: np.ndarray,
    bins: int = 720,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not members or stl_band_2d is None or len(stl_band_2d) == 0:
        return list(members), {"angle_sign": 1.0, "angle_offset_deg": 0.0, "score": 0.0}

    angles = np.degrees(np.arctan2(stl_band_2d[:, 1], stl_band_2d[:, 0]))
    hist_edges = np.linspace(-180.0, 180.0, int(bins) + 1)
    hist, _ = np.histogram(angles, bins=hist_edges)
    hist = hist.astype(float)
    if hist.sum() > 0:
        hist = hist / hist.sum()

    feature_angles = np.asarray([float(row["feature_angle_deg"]) for row in members], dtype=float)
    offsets = np.linspace(-180.0, 180.0, 1441)
    best_sign = 1.0
    best_offset = 0.0
    best_score = -1.0

    for sign in (1.0, -1.0):
        transformed = sign * feature_angles.reshape(-1, 1) + offsets.reshape(1, -1)
        wrapped = ((transformed + 180.0) % 360.0) - 180.0
        idx = np.floor((wrapped + 180.0) / 360.0 * len(hist)).astype(int)
        idx = np.clip(idx, 0, len(hist) - 1)
        scores = hist[idx].sum(axis=0)
        score_idx = int(np.argmax(scores))
        if float(scores[score_idx]) > best_score:
            best_score = float(scores[score_idx])
            best_sign = float(sign)
            best_offset = float(offsets[score_idx])

    adjusted: List[Dict[str, Any]] = []
    for row in members:
        copy = dict(row)
        copy["diagnostic_angle_deg"] = float(wrap_angle_deg(best_sign * float(row["feature_angle_deg"]) + best_offset))
        adjusted.append(copy)
    return adjusted, {"angle_sign": best_sign, "angle_offset_deg": best_offset, "score": best_score}


def localize_front_points(points_2d: np.ndarray, angle_deg: float) -> np.ndarray:
    if points_2d is None or len(points_2d) == 0:
        return np.zeros((0, 2), dtype=float)
    theta = math.radians(-float(angle_deg))
    rotation = np.array(
        [[math.cos(theta), -math.sin(theta)], [math.sin(theta), math.cos(theta)]],
        dtype=float,
    )
    return np.asarray(points_2d, dtype=float) @ rotation.T


def select_member_points(
    points_2d: np.ndarray,
    angle_deg: float,
    inner_r: float,
    outer_r: float,
    half_span_deg: float,
    radial_expand: float,
) -> Tuple[np.ndarray, np.ndarray]:
    if points_2d is None or len(points_2d) == 0:
        return np.zeros((0, 2), dtype=float), np.zeros((0,), dtype=bool)
    radii = np.linalg.norm(points_2d, axis=1)
    angles = np.degrees(np.arctan2(points_2d[:, 1], points_2d[:, 0]))
    mask = (
        (angle_delta_deg(angles, float(angle_deg)) <= float(half_span_deg))
        & (radii >= max(0.0, float(inner_r) * (1.0 - float(radial_expand))))
        & (radii <= float(outer_r) * (1.0 + float(radial_expand)))
    )
    local = localize_front_points(points_2d[mask], angle_deg)
    return local, mask


def nearest_flags(ref: np.ndarray, cand: np.ndarray, threshold_mm: float) -> Tuple[np.ndarray, np.ndarray]:
    if ref is None or len(ref) == 0:
        return np.zeros((0,), dtype=bool), np.zeros((0,), dtype=float)
    if cand is None or len(cand) == 0:
        return np.ones((len(ref),), dtype=bool), np.full((len(ref),), np.inf, dtype=float)
    distances = cKDTree(cand).query(ref, k=1)[0]
    return distances > float(threshold_mm), distances


def radial_zone_labels(local_points: np.ndarray, inner_r: float, outer_r: float) -> np.ndarray:
    if local_points is None or len(local_points) == 0:
        return np.zeros((0,), dtype=int)
    denom = max(1e-6, float(outer_r) - float(inner_r))
    t = (local_points[:, 0] - float(inner_r)) / denom
    labels = np.zeros((len(local_points),), dtype=int)
    labels[t >= 0.34] = 1
    labels[t >= 0.68] = 2
    return labels


def envelope(points: np.ndarray, x_edges: np.ndarray, min_points: int = 12) -> Dict[str, np.ndarray]:
    centers = 0.5 * (x_edges[:-1] + x_edges[1:])
    lower = np.full(len(centers), np.nan, dtype=float)
    upper = np.full(len(centers), np.nan, dtype=float)
    mid = np.full(len(centers), np.nan, dtype=float)
    width = np.full(len(centers), np.nan, dtype=float)
    if points is None or len(points) == 0:
        return {"x": centers, "lower": lower, "upper": upper, "mid": mid, "width": width}
    x = points[:, 0]
    y = points[:, 1]
    for idx in range(len(centers)):
        mask = (x >= x_edges[idx]) & (x < x_edges[idx + 1])
        if np.count_nonzero(mask) < int(min_points):
            continue
        yy = y[mask]
        lower[idx] = float(np.percentile(yy, 8.0))
        upper[idx] = float(np.percentile(yy, 92.0))
        mid[idx] = float(np.median(yy))
        width[idx] = float(upper[idx] - lower[idx])
    return {"x": centers, "lower": lower, "upper": upper, "mid": mid, "width": width}


def nanmean_abs(values: np.ndarray) -> float:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    return float(np.mean(np.abs(finite))) if len(finite) else 0.0


def nanmean_signed(values: np.ndarray) -> float:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    return float(np.mean(finite)) if len(finite) else 0.0


def zone_counts(flags: np.ndarray, zones: np.ndarray) -> Dict[str, int]:
    names = ["root", "mid", "tail"]
    return {
        names[idx]: int(np.count_nonzero(flags & (zones == idx)))
        for idx in range(3)
    }


def summarize_member(
    member: Dict[str, Any],
    stl_local: np.ndarray,
    step_local: np.ndarray,
    threshold_mm: float,
    inner_r: float,
    outer_r: float,
) -> Dict[str, Any]:
    stl_unmatched, stl_dist = nearest_flags(stl_local, step_local, threshold_mm)
    step_unmatched, step_dist = nearest_flags(step_local, stl_local, threshold_mm)
    combined = np.vstack([pts for pts in (stl_local, step_local) if len(pts) > 0]) if (len(stl_local) or len(step_local)) else np.zeros((0, 2))
    if len(combined):
        x_edges = np.linspace(float(np.percentile(combined[:, 0], 1.0)), float(np.percentile(combined[:, 0], 99.0)), 28)
    else:
        x_edges = np.linspace(float(inner_r), float(outer_r), 28)
    env_stl = envelope(stl_local, x_edges)
    env_step = envelope(step_local, x_edges)
    lower_delta = env_step["lower"] - env_stl["lower"]
    upper_delta = env_step["upper"] - env_stl["upper"]
    center_delta = env_step["mid"] - env_stl["mid"]
    width_delta = env_step["width"] - env_stl["width"]

    stl_zones = radial_zone_labels(stl_local, inner_r, outer_r)
    step_zones = radial_zone_labels(step_local, inner_r, outer_r)
    total = max(1, len(stl_local) + len(step_local))
    unmatched_total = int(np.count_nonzero(stl_unmatched) + np.count_nonzero(step_unmatched))
    envelope_error = (
        nanmean_abs(lower_delta)
        + nanmean_abs(upper_delta)
        + nanmean_abs(center_delta)
        + (0.5 * nanmean_abs(width_delta))
    )

    return {
        "member_index": int(member["member_index"]),
        "slot_index": int(member.get("slot_index", -1)),
        "feature_angle_deg": float(member.get("feature_angle_deg", 0.0)),
        "diagnostic_angle_deg": float(member.get("diagnostic_angle_deg", 0.0)),
        "stl_points": int(len(stl_local)),
        "step_points": int(len(step_local)),
        "stl_only_points": int(np.count_nonzero(stl_unmatched)),
        "step_only_points": int(np.count_nonzero(step_unmatched)),
        "stl_only_zone_counts": zone_counts(stl_unmatched, stl_zones),
        "step_only_zone_counts": zone_counts(step_unmatched, step_zones),
        "unmatched_ratio": float(unmatched_total / total),
        "median_nn_stl_to_step_mm": float(np.median(stl_dist)) if len(stl_dist) else float("nan"),
        "median_nn_step_to_stl_mm": float(np.median(step_dist)) if len(step_dist) else float("nan"),
        "p90_nn_stl_to_step_mm": float(np.percentile(stl_dist, 90.0)) if len(stl_dist) else float("nan"),
        "p90_nn_step_to_stl_mm": float(np.percentile(step_dist, 90.0)) if len(step_dist) else float("nan"),
        "mean_lower_delta_mm": nanmean_signed(lower_delta),
        "mean_upper_delta_mm": nanmean_signed(upper_delta),
        "mean_center_delta_mm": nanmean_signed(center_delta),
        "mean_abs_lower_delta_mm": nanmean_abs(lower_delta),
        "mean_abs_upper_delta_mm": nanmean_abs(upper_delta),
        "mean_abs_center_delta_mm": nanmean_abs(center_delta),
        "mean_width_delta_mm": float(np.nanmean(width_delta)) if np.any(np.isfinite(width_delta)) else 0.0,
        "visual_error_score": float(unmatched_total / total + 0.08 * envelope_error),
    }


def plot_full_front_diff(
    output_path: Path,
    stl_band: np.ndarray,
    step_band: np.ndarray,
    threshold_mm: float,
) -> None:
    stl_unmatched, _ = nearest_flags(stl_band, step_band, threshold_mm)
    step_unmatched, _ = nearest_flags(step_band, stl_band, threshold_mm)

    fig, ax = plt.subplots(figsize=(10, 10))
    if len(stl_band):
        ax.scatter(stl_band[:, 0], stl_band[:, 1], s=0.18, c="#b7d7f0", alpha=0.18, linewidths=0, label="STL band")
        ax.scatter(stl_band[stl_unmatched, 0], stl_band[stl_unmatched, 1], s=0.55, c="#1667b7", alpha=0.75, linewidths=0, label="STL-only / missing STEP")
    if len(step_band):
        ax.scatter(step_band[:, 0], step_band[:, 1], s=0.18, c="#b8ddb5", alpha=0.18, linewidths=0, label="STEP band")
        ax.scatter(step_band[step_unmatched, 0], step_band[step_unmatched, 1], s=0.55, c="#e4552f", alpha=0.75, linewidths=0, label="STEP-only / extra CAD")
    ax.set_aspect("equal")
    ax.set_title(f"Front-view spoke-band visual difference, threshold={threshold_mm:.1f} mm")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.legend(loc="upper right", frameon=False, markerscale=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_polar_heatmap(
    output_path: Path,
    stl_band: np.ndarray,
    step_band: np.ndarray,
    inner_r: float,
    outer_r: float,
) -> Dict[str, Any]:
    angle_edges = np.linspace(-180.0, 180.0, 145)
    radial_edges = np.linspace(float(inner_r), float(outer_r), 50)

    def hist(points: np.ndarray) -> np.ndarray:
        if points is None or len(points) == 0:
            return np.zeros((len(angle_edges) - 1, len(radial_edges) - 1), dtype=float)
        angles = np.degrees(np.arctan2(points[:, 1], points[:, 0]))
        radii = np.linalg.norm(points, axis=1)
        h, _, _ = np.histogram2d(angles, radii, bins=[angle_edges, radial_edges])
        return h.astype(float)

    h_stl = hist(stl_band)
    h_step = hist(step_band)
    h_stl_norm = h_stl / max(1.0, float(h_stl.sum()))
    h_step_norm = h_step / max(1.0, float(h_step.sum()))
    diff = h_step_norm - h_stl_norm

    fig, ax = plt.subplots(figsize=(13, 5.2))
    mesh = ax.pcolormesh(angle_edges, radial_edges, diff.T, cmap="coolwarm", shading="auto")
    ax.set_xlabel("canonical angle (deg)")
    ax.set_ylabel("front radius (mm)")
    ax.set_title("Polar density difference: red=extra STEP, blue=missing STEP")
    fig.colorbar(mesh, ax=ax, label="normalized STEP-STL density")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)

    sector_error = np.sum(np.abs(diff), axis=1)
    worst_indices = np.argsort(sector_error)[-10:][::-1]
    return {
        "worst_angle_bins": [
            {
                "angle0_deg": float(angle_edges[idx]),
                "angle1_deg": float(angle_edges[idx + 1]),
                "error": float(sector_error[idx]),
            }
            for idx in worst_indices
        ]
    }


def plot_member_panels(
    output_path: Path,
    member_rows: Sequence[Dict[str, Any]],
    member_points: Dict[int, Tuple[np.ndarray, np.ndarray]],
    threshold_mm: float,
) -> None:
    fig, axes = plt.subplots(2, 5, figsize=(20, 8.5))
    axes = axes.reshape(-1)
    for ax, row in zip(axes, member_rows):
        idx = int(row["member_index"])
        stl_local, step_local = member_points[idx]
        stl_unmatched, _ = nearest_flags(stl_local, step_local, threshold_mm)
        step_unmatched, _ = nearest_flags(step_local, stl_local, threshold_mm)
        if len(stl_local):
            ax.scatter(stl_local[:, 0], stl_local[:, 1], s=0.30, c="#a9cfee", alpha=0.22, linewidths=0)
            ax.scatter(stl_local[stl_unmatched, 0], stl_local[stl_unmatched, 1], s=1.3, c="#1667b7", alpha=0.78, linewidths=0)
        if len(step_local):
            ax.scatter(step_local[:, 0], step_local[:, 1], s=0.30, c="#b7ddb3", alpha=0.22, linewidths=0)
            ax.scatter(step_local[step_unmatched, 0], step_local[step_unmatched, 1], s=1.3, c="#e4552f", alpha=0.78, linewidths=0)
        valid = [pts for pts in (stl_local, step_local) if len(pts)]
        if valid:
            merged = np.vstack(valid)
            q0 = np.percentile(merged, 1.0, axis=0)
            q1 = np.percentile(merged, 99.0, axis=0)
            span = np.maximum(q1 - q0, 1.0)
            pad = 0.08 * span
            ax.set_xlim(q0[0] - pad[0], q1[0] + pad[0])
            ax.set_ylim(q0[1] - pad[1], q1[1] + pad[1])
        ax.set_aspect("equal")
        ax.set_title(
            f"m{idx} slot{int(row.get('slot_index', -1))} angle={float(row.get('diagnostic_angle_deg', 0.0)):.1f}\n"
            f"blue=missing STEP, red=extra STEP"
        )
        ax.set_xticks([])
        ax.set_yticks([])
    for ax in axes[len(member_rows) :]:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_worst_profiles(
    output_path: Path,
    summaries: Sequence[Dict[str, Any]],
    member_points: Dict[int, Tuple[np.ndarray, np.ndarray]],
    max_members: int = 4,
) -> None:
    worst = sorted(summaries, key=lambda item: float(item["visual_error_score"]), reverse=True)[: int(max_members)]
    fig, axes = plt.subplots(len(worst), 1, figsize=(12, max(3.2, 2.7 * len(worst))))
    if len(worst) == 1:
        axes = np.asarray([axes])
    for ax, summary in zip(axes, worst):
        idx = int(summary["member_index"])
        stl_local, step_local = member_points[idx]
        valid = [pts for pts in (stl_local, step_local) if len(pts)]
        if valid:
            merged = np.vstack(valid)
            x_edges = np.linspace(float(np.percentile(merged[:, 0], 1.0)), float(np.percentile(merged[:, 0], 99.0)), 32)
        else:
            x_edges = np.linspace(0.0, 1.0, 32)
        e_stl = envelope(stl_local, x_edges)
        e_step = envelope(step_local, x_edges)
        ax.plot(e_stl["x"], e_stl["lower"], color="#1667b7", linewidth=1.2, label="STL lower")
        ax.plot(e_stl["x"], e_stl["upper"], color="#1667b7", linewidth=1.2, linestyle="--", label="STL upper")
        ax.plot(e_step["x"], e_step["lower"], color="#e4552f", linewidth=1.2, label="STEP lower")
        ax.plot(e_step["x"], e_step["upper"], color="#e4552f", linewidth=1.2, linestyle="--", label="STEP upper")
        ax.set_title(
            f"member {idx}: score={float(summary['visual_error_score']):.3f}, "
            f"unmatched={float(summary['unmatched_ratio']):.3f}, width_delta={float(summary['mean_width_delta_mm']):.2f} mm"
        )
        ax.set_xlabel("local radial x (mm)")
        ax.set_ylabel("local tangent y (mm)")
        ax.grid(alpha=0.2)
        ax.legend(loc="upper right", ncol=4, fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Visual spoke-difference diagnostics for STL-vs-candidate wheel meshes.")
    parser.add_argument("--features", required=True, help="Features JSON path")
    parser.add_argument("--reference-stl", required=True, help="Reference STL path")
    parser.add_argument("--candidate-stl", required=True, help="Candidate CAD-exported STL path")
    parser.add_argument("--output-dir", required=True, help="Output diagnostic directory")
    parser.add_argument("--sample-count", type=int, default=65000, help="Surface sample count per mesh")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic sampling seed")
    parser.add_argument("--diff-threshold-mm", type=float, default=2.4, help="2D nearest-neighbor threshold for visual missing/extra points")
    parser.add_argument("--member-half-span-deg", type=float, default=11.5, help="Angular half-span for each member close-up")
    parser.add_argument("--radial-expand", type=float, default=0.08, help="Radial expansion around the spoke band")
    parser.add_argument("--summary-json", default=None, help="Optional output summary JSON path")
    args = parser.parse_args()

    features_path = Path(args.features).resolve()
    reference_stl_path = Path(args.reference_stl).resolve()
    candidate_stl_path = Path(args.candidate_stl).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_json_path = Path(args.summary_json).resolve() if args.summary_json else output_dir / "visual_spoke_diagnostics.json"

    features = load_json(features_path)
    agent = make_eval_helper(features, int(args.seed))
    stl_mesh = load_mesh(reference_stl_path)
    step_mesh = load_mesh(candidate_stl_path)

    stl_raw = sample_mesh(agent, stl_mesh, int(args.sample_count))
    step_raw = sample_mesh(agent, step_mesh, int(args.sample_count))
    stl_points = agent._canonicalize_wheel_points(stl_raw)
    step_points = agent._canonicalize_wheel_points(step_raw)
    step_points, align_meta = agent._align_step_to_stl_visual(stl_points, step_points)

    front_stl = agent._project_canonical_points(stl_points, "front")
    front_step = agent._project_canonical_points(step_points, "front")
    inner_r, outer_r = agent._derive_spoke_band_limits(front_stl)
    radii_stl = np.linalg.norm(front_stl, axis=1)
    radii_step = np.linalg.norm(front_step, axis=1)
    stl_band = front_stl[(radii_stl >= inner_r) & (radii_stl <= outer_r)]
    step_band = front_step[(radii_step >= inner_r) & (radii_step <= outer_r)]

    members = collect_members(features)
    members, angle_fit = fit_feature_angle_transform(members, stl_band)

    member_points: Dict[int, Tuple[np.ndarray, np.ndarray]] = {}
    member_summaries: List[Dict[str, Any]] = []
    for member in members:
        angle = float(member["diagnostic_angle_deg"])
        stl_local, _ = select_member_points(
            front_stl,
            angle,
            inner_r,
            outer_r,
            float(args.member_half_span_deg),
            float(args.radial_expand),
        )
        step_local, _ = select_member_points(
            front_step,
            angle,
            inner_r,
            outer_r,
            float(args.member_half_span_deg),
            float(args.radial_expand),
        )
        idx = int(member["member_index"])
        member_points[idx] = (stl_local, step_local)
        member_summaries.append(
            summarize_member(
                member,
                stl_local,
                step_local,
                float(args.diff_threshold_mm),
                inner_r,
                outer_r,
            )
        )

    full_front_path = output_dir / "visual_full_front_diff.png"
    polar_path = output_dir / "visual_polar_heatmap.png"
    members_path = output_dir / "visual_member_overlays.png"
    worst_profiles_path = output_dir / "visual_worst_member_profiles.png"
    plot_full_front_diff(full_front_path, stl_band, step_band, float(args.diff_threshold_mm))
    polar_payload = plot_polar_heatmap(polar_path, stl_band, step_band, inner_r, outer_r)
    plot_member_panels(members_path, members, member_points, float(args.diff_threshold_mm))
    plot_worst_profiles(worst_profiles_path, member_summaries, member_points)

    member_summaries_sorted = sorted(member_summaries, key=lambda item: float(item["visual_error_score"]), reverse=True)
    payload = {
        "features": str(features_path),
        "reference_stl": str(reference_stl_path),
        "candidate_stl": str(candidate_stl_path),
        "sample_count": int(args.sample_count),
        "diff_threshold_mm": float(args.diff_threshold_mm),
        "align_meta": {
            "axial_rotation_deg": float(align_meta.get("axial_rotation_deg", 0.0)),
            "axis_signs": list(align_meta.get("axis_signs", (1.0, 1.0, 1.0))),
            "translation": list(align_meta.get("translation", (0.0, 0.0, 0.0))),
            "score": float(align_meta.get("score", 0.0)),
        },
        "angle_fit": angle_fit,
        "spoke_band": {"inner_r": float(inner_r), "outer_r": float(outer_r)},
        "artifacts": {
            "full_front_diff": str(full_front_path),
            "polar_heatmap": str(polar_path),
            "member_overlays": str(members_path),
            "worst_member_profiles": str(worst_profiles_path),
        },
        "polar": polar_payload,
        "worst_members": [
            {
                "member_index": int(row["member_index"]),
                "slot_index": int(row["slot_index"]),
                "diagnostic_angle_deg": float(row["diagnostic_angle_deg"]),
                "visual_error_score": float(row["visual_error_score"]),
                "unmatched_ratio": float(row["unmatched_ratio"]),
                "stl_only_zone_counts": row["stl_only_zone_counts"],
                "step_only_zone_counts": row["step_only_zone_counts"],
                "mean_lower_delta_mm": float(row["mean_lower_delta_mm"]),
                "mean_upper_delta_mm": float(row["mean_upper_delta_mm"]),
                "mean_center_delta_mm": float(row["mean_center_delta_mm"]),
                "mean_abs_lower_delta_mm": float(row["mean_abs_lower_delta_mm"]),
                "mean_abs_upper_delta_mm": float(row["mean_abs_upper_delta_mm"]),
                "mean_abs_center_delta_mm": float(row["mean_abs_center_delta_mm"]),
                "mean_width_delta_mm": float(row["mean_width_delta_mm"]),
            }
            for row in member_summaries_sorted[:6]
        ],
        "members": member_summaries_sorted,
    }
    summary_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[*] visual diagnostics: {output_dir}")
    print(f"[*] summary: {summary_json_path}")
    print("[*] worst members:")
    for row in payload["worst_members"]:
        print(
            "    member={member_index} slot={slot_index} score={visual_error_score:.3f} "
            "unmatched={unmatched_ratio:.3f} angle={diagnostic_angle_deg:.1f}".format(**row)
        )


if __name__ == "__main__":
    main()
