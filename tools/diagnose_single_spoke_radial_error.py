from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.evaluation_agent import EvaluationAgent


def interval_overlap_ratio(a0: float, a1: float, b0: float, b1: float) -> float:
    lo = max(float(a0), float(b0))
    hi = min(float(a1), float(b1))
    denom = max(1e-6, max(float(a1), float(b1)) - min(float(a0), float(b0)))
    return max(0.0, (hi - lo) / denom)


def sanitize_json(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {str(key): sanitize_json(value) for key, value in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [sanitize_json(item) for item in payload]
    if isinstance(payload, np.ndarray):
        return sanitize_json(payload.tolist())
    if isinstance(payload, (np.floating, float)):
        return float(payload)
    if isinstance(payload, (np.integer, int)):
        return int(payload)
    if isinstance(payload, (np.bool_, bool)):
        return bool(payload)
    return payload


def root_left_score(points: np.ndarray, use_left: bool) -> float:
    if points is None or len(points) == 0:
        return -1.0
    xs = np.asarray(points[:, 0], dtype=float)
    ys = np.asarray(points[:, 1], dtype=float)
    x_mid = 0.5 * (float(np.min(xs)) + float(np.max(xs)))
    mask = xs <= x_mid if use_left else xs > x_mid
    if int(np.count_nonzero(mask)) < 24:
        return -1.0
    band = ys[mask]
    span = float(np.percentile(band, 95.0) - np.percentile(band, 5.0))
    density = float(np.count_nonzero(mask)) / max(1.0, float(len(points)))
    return span + (18.0 * density)


def orient_root_left(stl_spoke: np.ndarray, step_spoke: np.ndarray) -> Tuple[np.ndarray, np.ndarray, bool]:
    left_score = max(root_left_score(stl_spoke, True), root_left_score(step_spoke, True))
    right_score = max(root_left_score(stl_spoke, False), root_left_score(step_spoke, False))
    if right_score <= left_score:
        return stl_spoke, step_spoke, False
    stl_flip = np.asarray(stl_spoke, dtype=float).copy()
    step_flip = np.asarray(step_spoke, dtype=float).copy()
    stl_flip[:, 0] *= -1.0
    step_flip[:, 0] *= -1.0
    return stl_flip, step_flip, True


def build_bin_rows(points: np.ndarray, bin_edges: np.ndarray, min_points: int) -> List[Dict[str, float]]:
    rows: List[Dict[str, float]] = []
    xs = np.asarray(points[:, 0], dtype=float)
    ys = np.asarray(points[:, 1], dtype=float)
    x_min = float(bin_edges[0])
    x_max = float(bin_edges[-1])
    x_span = max(1e-6, x_max - x_min)
    for idx in range(len(bin_edges) - 1):
        lo = float(bin_edges[idx])
        hi = float(bin_edges[idx + 1])
        if idx == len(bin_edges) - 2:
            mask = (xs >= lo) & (xs <= hi)
        else:
            mask = (xs >= lo) & (xs < hi)
        count = int(np.count_nonzero(mask))
        row: Dict[str, float] = {
            "bin_index": int(idx),
            "x0": lo,
            "x1": hi,
            "x_mid": 0.5 * (lo + hi),
            "x_norm_mid": (0.5 * (lo + hi) - x_min) / x_span,
            "count": int(count),
        }
        if count >= int(min_points):
            band = ys[mask]
            row.update(
                {
                    "y05": float(np.percentile(band, 5.0)),
                    "y25": float(np.percentile(band, 25.0)),
                    "y50": float(np.percentile(band, 50.0)),
                    "y75": float(np.percentile(band, 75.0)),
                    "y95": float(np.percentile(band, 95.0)),
                    "y_min": float(np.min(band)),
                    "y_max": float(np.max(band)),
                }
            )
        rows.append(row)
    return rows


def zone_name(x_norm: float) -> str:
    if x_norm < 0.26:
        return "root"
    if x_norm < 0.78:
        return "mid"
    return "tail"


def compare_bin_rows(
    stl_rows: List[Dict[str, float]],
    step_rows: List[Dict[str, float]],
    min_points: int,
) -> Tuple[List[Dict[str, float]], Dict[str, Dict[str, float]]]:
    rows: List[Dict[str, float]] = []
    zone_weights: Dict[str, float] = {"root": 0.0, "mid": 0.0, "tail": 0.0}
    zone_accum: Dict[str, Dict[str, float]] = {
        "root": {"lower_delta": 0.0, "center_delta": 0.0, "upper_delta": 0.0, "band_overlap": 0.0, "width_ratio": 0.0},
        "mid": {"lower_delta": 0.0, "center_delta": 0.0, "upper_delta": 0.0, "band_overlap": 0.0, "width_ratio": 0.0},
        "tail": {"lower_delta": 0.0, "center_delta": 0.0, "upper_delta": 0.0, "band_overlap": 0.0, "width_ratio": 0.0},
    }
    for stl_row, step_row in zip(stl_rows, step_rows):
        row = {
            "bin_index": int(stl_row["bin_index"]),
            "x0": float(stl_row["x0"]),
            "x1": float(stl_row["x1"]),
            "x_mid": float(stl_row["x_mid"]),
            "x_norm_mid": float(stl_row["x_norm_mid"]),
            "stl_count": int(stl_row["count"]),
            "step_count": int(step_row["count"]),
        }
        if int(stl_row["count"]) >= int(min_points) and int(step_row["count"]) >= int(min_points):
            stl_lower = float(stl_row["y05"])
            stl_center = float(stl_row["y50"])
            stl_upper = float(stl_row["y95"])
            step_lower = float(step_row["y05"])
            step_center = float(step_row["y50"])
            step_upper = float(step_row["y95"])
            stl_band = max(1e-6, stl_upper - stl_lower)
            step_band = max(1e-6, step_upper - step_lower)
            weight = float(min(int(stl_row["count"]), int(step_row["count"])))
            overlap = interval_overlap_ratio(stl_lower, stl_upper, step_lower, step_upper)
            width_ratio = step_band / stl_band
            row.update(
                {
                    "lower_delta": step_lower - stl_lower,
                    "center_delta": step_center - stl_center,
                    "upper_delta": step_upper - stl_upper,
                    "band_overlap": overlap,
                    "width_ratio": width_ratio,
                    "stl_band": stl_band,
                    "step_band": step_band,
                }
            )
            zone = zone_name(float(stl_row["x_norm_mid"]))
            zone_weights[zone] += weight
            for key in ("lower_delta", "center_delta", "upper_delta", "band_overlap", "width_ratio"):
                zone_accum[zone][key] += weight * float(row[key])
        rows.append(row)
    zone_summary: Dict[str, Dict[str, float]] = {}
    for zone, accum in zone_accum.items():
        weight = max(1e-6, zone_weights[zone])
        zone_summary[zone] = {"sample_weight": float(zone_weights[zone])}
        for key, total in accum.items():
            zone_summary[zone][key] = float(total / weight) if zone_weights[zone] > 0.0 else float("nan")
    return rows, zone_summary


def build_plot(
    output_path: Path,
    stl_rows: List[Dict[str, float]],
    step_rows: List[Dict[str, float]],
    delta_rows: List[Dict[str, float]],
) -> None:
    x = np.asarray([float(row["x_norm_mid"]) for row in stl_rows], dtype=float)
    fig, axes = plt.subplots(2, 1, figsize=(11.2, 7.6), sharex=True)

    def row_array(rows: List[Dict[str, float]], key: str) -> np.ndarray:
        values = []
        for row in rows:
            values.append(float(row[key]) if key in row else np.nan)
        return np.asarray(values, dtype=float)

    axes[0].plot(x, row_array(stl_rows, "y05"), color="#1f77b4", linewidth=1.4, label="STL y05")
    axes[0].plot(x, row_array(stl_rows, "y50"), color="#1f77b4", linewidth=2.1, label="STL y50")
    axes[0].plot(x, row_array(stl_rows, "y95"), color="#1f77b4", linewidth=1.4, linestyle="--", label="STL y95")
    axes[0].plot(x, row_array(step_rows, "y05"), color="#2ca02c", linewidth=1.4, label="STEP y05")
    axes[0].plot(x, row_array(step_rows, "y50"), color="#2ca02c", linewidth=2.1, label="STEP y50")
    axes[0].plot(x, row_array(step_rows, "y95"), color="#2ca02c", linewidth=1.4, linestyle="--", label="STEP y95")
    axes[0].set_ylabel("y")
    axes[0].set_title("Single-spoke envelope by radial progress")
    axes[0].grid(alpha=0.18)
    axes[0].legend(ncol=3, fontsize=8, frameon=False)

    axes[1].plot(x, row_array(delta_rows, "lower_delta"), color="#d62728", linewidth=2.0, label="lower delta")
    axes[1].plot(x, row_array(delta_rows, "center_delta"), color="#ff7f0e", linewidth=1.8, label="center delta")
    axes[1].plot(x, row_array(delta_rows, "upper_delta"), color="#9467bd", linewidth=1.8, label="upper delta")
    axes[1].plot(x, row_array(delta_rows, "band_overlap"), color="#17becf", linewidth=1.6, label="band overlap")
    axes[1].axhline(0.0, color="#444444", linewidth=1.0, alpha=0.55)
    axes[1].set_xlabel("x_norm (root -> tip)")
    axes[1].set_ylabel("delta / overlap")
    axes[1].set_title("STEP minus STL delta by radial progress")
    axes[1].grid(alpha=0.18)
    axes[1].legend(ncol=4, fontsize=8, frameon=False)

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def diagnose(
    step_path: Path,
    features_path: Path,
    stl_path: Path,
    compare_stl_path: Path | None,
    sample_size: int,
    eval_seed: int,
    bins: int,
    min_bin_points: int,
) -> Dict[str, Any]:
    agent = EvaluationAgent(
        stl_path=str(stl_path),
        step_path=str(step_path),
        features_path=str(features_path),
        config={
            "visual_sample_size": int(sample_size),
            "eval_seed": int(eval_seed),
            "step_mesh_fallback_path": str(compare_stl_path) if compare_stl_path else None,
        },
    )

    stl_raw = agent._sample_surface_points(agent.stl_mesh, agent.stl_vertices, sample_size=int(sample_size))
    step_raw = agent._sample_surface_points(agent.step_mesh, agent.step_vertices, sample_size=int(sample_size))
    stl_points = agent._canonicalize_wheel_points(stl_raw)
    step_points = agent._canonicalize_wheel_points(step_raw)
    step_points, align_meta = agent._align_step_to_stl_visual(stl_points, step_points)

    front_stl = agent._project_canonical_points(stl_points, "front")
    front_step = agent._project_canonical_points(step_points, "front")
    spoke_band_stl = agent._filter_spoke_band(front_stl)
    spoke_band_step = agent._filter_spoke_band(front_step)
    spoke_angle = agent._estimate_single_spoke_angle(spoke_band_stl, spoke_band_step)

    stl_spoke = agent._extract_single_spoke_closeup(front_stl, spoke_angle)
    step_spoke = agent._extract_single_spoke_closeup(front_step, spoke_angle)
    stl_spoke, step_spoke, orient_deg = agent._orient_closeup_pair(stl_spoke, step_spoke)
    stl_spoke, step_spoke, root_flipped = orient_root_left(stl_spoke, step_spoke)

    merged = np.vstack([stl_spoke, step_spoke])
    x_min = float(np.min(merged[:, 0]))
    x_max = float(np.max(merged[:, 0]))
    bin_edges = np.linspace(x_min, x_max, int(bins) + 1)

    stl_rows = build_bin_rows(stl_spoke, bin_edges, min_points=int(min_bin_points))
    step_rows = build_bin_rows(step_spoke, bin_edges, min_points=int(min_bin_points))
    delta_rows, zone_summary = compare_bin_rows(stl_rows, step_rows, min_points=int(min_bin_points))

    return {
        "align_meta": dict(align_meta),
        "spoke_angle_deg": float(spoke_angle),
        "spoke_orient_deg": float(orient_deg),
        "root_flipped_for_report": bool(root_flipped),
        "bins": delta_rows,
        "zones": zone_summary,
        "stl_rows": stl_rows,
        "step_rows": step_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose single-spoke radial error from the existing visual comparison path.")
    parser.add_argument("--step", required=True, help="STEP path")
    parser.add_argument("--features", required=True, help="Features JSON path")
    parser.add_argument("--stl", default=str(ROOT / "input" / "wheel.stl"), help="Reference STL path")
    parser.add_argument("--compare-stl", default=None, help="Optional STL exported from the STEP candidate")
    parser.add_argument("--output-json", required=True, help="Diagnostic JSON output path")
    parser.add_argument("--output-plot", default=None, help="Optional diagnostic plot path")
    parser.add_argument("--visual-sample-size", type=int, default=30000, help="Surface sample count")
    parser.add_argument("--eval-seed", type=int, default=42, help="Deterministic evaluation seed")
    parser.add_argument("--bins", type=int, default=16, help="Number of radial bins in the spoke close-up")
    parser.add_argument("--min-bin-points", type=int, default=40, help="Minimum points per bin per side")
    args = parser.parse_args()

    step_path = Path(args.step).resolve()
    features_path = Path(args.features).resolve()
    stl_path = Path(args.stl).resolve()
    compare_stl_path = Path(args.compare_stl).resolve() if args.compare_stl else None
    output_json = Path(args.output_json).resolve()
    output_plot = Path(args.output_plot).resolve() if args.output_plot else None

    payload = diagnose(
        step_path=step_path,
        features_path=features_path,
        stl_path=stl_path,
        compare_stl_path=compare_stl_path,
        sample_size=int(args.visual_sample_size),
        eval_seed=int(args.eval_seed),
        bins=int(args.bins),
        min_bin_points=int(args.min_bin_points),
    )

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(sanitize_json(payload), ensure_ascii=False, indent=2), encoding="utf-8")

    if output_plot is not None:
        build_plot(
            output_path=output_plot,
            stl_rows=payload["stl_rows"],
            step_rows=payload["step_rows"],
            delta_rows=payload["bins"],
        )

    print(f"[*] radial diagnostic json: {output_json}")
    if output_plot is not None:
        print(f"[*] radial diagnostic plot: {output_plot}")
    for zone_name_key in ("root", "mid", "tail"):
        zone = payload["zones"].get(zone_name_key, {})
        print(
            "[*] zone={0} lower_delta={1:.4f} center_delta={2:.4f} upper_delta={3:.4f} "
            "band_overlap={4:.4f} width_ratio={5:.4f}".format(
                zone_name_key,
                float(zone.get("lower_delta", float("nan"))),
                float(zone.get("center_delta", float("nan"))),
                float(zone.get("upper_delta", float("nan"))),
                float(zone.get("band_overlap", float("nan"))),
                float(zone.get("width_ratio", float("nan"))),
            )
        )


if __name__ == "__main__":
    main()
