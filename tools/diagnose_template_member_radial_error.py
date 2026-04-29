from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict

import numpy as np
from scipy.spatial import cKDTree


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.diagnose_member_spoke_overlap import build_or_load_source_submesh, load_mesh, sample_points
from tools.diagnose_single_spoke_radial_error import (
    build_bin_rows,
    build_plot,
    compare_bin_rows,
    orient_root_left,
    sanitize_json,
)
import tools.run_single_spoke_mesh_to_cad as single_spoke


def rotation_matrix_2d(angle_deg: float) -> np.ndarray:
    angle_rad = math.radians(float(angle_deg))
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    return np.asarray([[c, -s], [s, c]], dtype=float)


def find_member_angle(features: Dict[str, Any], member_index: int) -> float:
    for motif_payload in features.get("spoke_motif_sections") or []:
        for member_payload in motif_payload.get("members", []) or []:
            try:
                if int(member_payload.get("member_index", -1)) == int(member_index):
                    return float(member_payload.get("angle", 0.0))
            except Exception:
                continue
    raise ValueError(f"member {member_index} not found")


def projection_overlap_score(ref_points: np.ndarray, cand_points: np.ndarray, bins: int = 120) -> float:
    if ref_points is None or cand_points is None or len(ref_points) == 0 or len(cand_points) == 0:
        return -1.0
    merged = np.vstack([ref_points, cand_points])
    mins = merged.min(axis=0)
    maxs = merged.max(axis=0)
    center = 0.5 * (mins + maxs)
    span = float(max(np.max(maxs - mins), 1.0))
    ref_norm = (ref_points - center) / span
    cand_norm = (cand_points - center) / span
    hist_range = [[-0.6, 0.6], [-0.6, 0.6]]
    hist_ref, _, _ = np.histogram2d(ref_norm[:, 0], ref_norm[:, 1], bins=bins, range=hist_range)
    hist_cand, _, _ = np.histogram2d(cand_norm[:, 0], cand_norm[:, 1], bins=bins, range=hist_range)
    if hist_ref.sum() > 0:
        hist_ref = hist_ref / hist_ref.sum()
    if hist_cand.sum() > 0:
        hist_cand = hist_cand / hist_cand.sum()
    return float(np.minimum(hist_ref, hist_cand).sum())


def orient_member_front(
    src_points: np.ndarray,
    cand_points: np.ndarray,
    angle_deg: float,
) -> tuple[np.ndarray, np.ndarray]:
    src_front = np.asarray(src_points[:, [0, 1]], dtype=float)
    cand_front = np.asarray(cand_points[:, [0, 1]], dtype=float)

    rotation = rotation_matrix_2d(-float(angle_deg))
    src_rot = src_front @ rotation.T
    cand_rot = cand_front @ rotation.T

    merged = np.vstack([src_rot, cand_rot])
    center = np.mean(merged, axis=0)
    src_rot = src_rot - center
    cand_rot = cand_rot - center
    src_rot, cand_rot, _ = orient_root_left(src_rot, cand_rot)
    return src_rot, cand_rot


def diagnose_member(
    features_path: Path,
    stl_path: Path,
    candidate_stl_path: Path,
    member_index: int,
    sample_count: int,
    bins: int,
    min_bin_points: int,
    reuse_submesh_cache: bool,
    output_dir: Path,
) -> Dict[str, Any]:
    with features_path.open("r", encoding="utf-8") as handle:
        features = json.load(handle)

    source_mesh = single_spoke.load_trimesh(stl_path, features=features)
    source_submesh = build_or_load_source_submesh(
        source_mesh=source_mesh,
        features=features,
        member_index=int(member_index),
        output_dir=output_dir,
        reuse_cache=bool(reuse_submesh_cache),
    )
    if source_submesh is None:
        raise RuntimeError(f"source submesh unavailable for member {member_index}")

    candidate_mesh = load_mesh(candidate_stl_path)
    src_points = sample_points(source_submesh, count=int(sample_count), seed=20260422 + int(member_index))
    cand_points = sample_points(candidate_mesh, count=int(sample_count), seed=20260511 + int(member_index))
    if len(src_points) == 0 or len(cand_points) == 0:
        raise RuntimeError("empty source or candidate sample set")

    src_center = np.mean(src_points, axis=0)
    cand_center = np.mean(cand_points, axis=0)
    cand_points = cand_points + (src_center - cand_center)

    angle_deg = find_member_angle(features, int(member_index))
    src_front, cand_front = orient_member_front(src_points, cand_points, angle_deg=angle_deg)

    merged = np.vstack([src_front, cand_front])
    x_min = float(np.min(merged[:, 0]))
    x_max = float(np.max(merged[:, 0]))
    bin_edges = np.linspace(x_min, x_max, int(bins) + 1)
    src_rows = build_bin_rows(src_front, bin_edges, min_points=int(min_bin_points))
    cand_rows = build_bin_rows(cand_front, bin_edges, min_points=int(min_bin_points))
    delta_rows, zone_summary = compare_bin_rows(src_rows, cand_rows, min_points=int(min_bin_points))

    src_tree = cKDTree(src_points)
    cand_tree = cKDTree(cand_points)
    d_fwd = cand_tree.query(src_points, k=1)[0]
    d_bwd = src_tree.query(cand_points, k=1)[0]

    return {
        "member_index": int(member_index),
        "member_angle_deg": float(angle_deg),
        "front_overlap_proxy": float(projection_overlap_score(src_front, cand_front, bins=120)),
        "nn_mean_fwd_mm": float(np.mean(d_fwd)) if len(d_fwd) else float("nan"),
        "nn_mean_bwd_mm": float(np.mean(d_bwd)) if len(d_bwd) else float("nan"),
        "nn_p95_fwd_mm": float(np.percentile(d_fwd, 95.0)) if len(d_fwd) else float("nan"),
        "nn_p95_bwd_mm": float(np.percentile(d_bwd, 95.0)) if len(d_bwd) else float("nan"),
        "zones": zone_summary,
        "bins": delta_rows,
        "source_rows": src_rows,
        "candidate_rows": cand_rows,
        "source_submesh_faces": int(len(source_submesh.faces)) if getattr(source_submesh, "faces", None) is not None else 0,
        "candidate_faces": int(len(candidate_mesh.faces)) if getattr(candidate_mesh, "faces", None) is not None else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose a single template spoke against the source member submesh.")
    parser.add_argument("--features", required=True, help="Features JSON path")
    parser.add_argument("--stl", required=True, help="Reference STL path")
    parser.add_argument("--candidate-stl", required=True, help="Template spoke STL path")
    parser.add_argument("--member-index", type=int, default=2, help="Member index used as the source comparison target")
    parser.add_argument("--sample-count", type=int, default=20000, help="Surface sample count per mesh")
    parser.add_argument("--bins", type=int, default=18, help="Number of radial bins")
    parser.add_argument("--min-bin-points", type=int, default=40, help="Minimum points per bin per side")
    parser.add_argument("--output-json", required=True, help="Output JSON path")
    parser.add_argument("--output-plot", default=None, help="Optional output plot path")
    parser.add_argument("--output-dir", default=str(ROOT / "output"), help="Working directory for submesh cache")
    parser.add_argument("--reuse-submesh-cache", action="store_true", help="Reuse cached source member submesh")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    payload = diagnose_member(
        features_path=Path(args.features).resolve(),
        stl_path=Path(args.stl).resolve(),
        candidate_stl_path=Path(args.candidate_stl).resolve(),
        member_index=int(args.member_index),
        sample_count=int(args.sample_count),
        bins=int(args.bins),
        min_bin_points=int(args.min_bin_points),
        reuse_submesh_cache=bool(args.reuse_submesh_cache),
        output_dir=output_dir,
    )

    output_json = Path(args.output_json).resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(sanitize_json(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[*] member radial diagnostic json: {output_json}")

    if args.output_plot:
        output_plot = Path(args.output_plot).resolve()
        build_plot(
            output_path=output_plot,
            stl_rows=payload["source_rows"],
            step_rows=payload["candidate_rows"],
            delta_rows=payload["bins"],
        )
        print(f"[*] member radial diagnostic plot: {output_plot}")

    for zone_name in ("root", "mid", "tail"):
        zone = payload["zones"].get(zone_name, {})
        print(
            "[*] zone={0} lower_delta={1:.4f} center_delta={2:.4f} upper_delta={3:.4f} "
            "band_overlap={4:.4f} width_ratio={5:.4f}".format(
                zone_name,
                float(zone.get("lower_delta", float("nan"))),
                float(zone.get("center_delta", float("nan"))),
                float(zone.get("upper_delta", float("nan"))),
                float(zone.get("band_overlap", float("nan"))),
                float(zone.get("width_ratio", float("nan"))),
            )
        )
    print(
        "[*] front_overlap_proxy={0:.4f} nn_mean_fwd_mm={1:.4f} nn_mean_bwd_mm={2:.4f}".format(
            float(payload["front_overlap_proxy"]),
            float(payload["nn_mean_fwd_mm"]),
            float(payload["nn_mean_bwd_mm"]),
        )
    )


if __name__ == "__main__":
    main()
