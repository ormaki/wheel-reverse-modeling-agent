from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import trimesh
from scipy.spatial import cKDTree


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.run_single_spoke_mesh_to_cad as single_spoke


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


def load_mesh(mesh_path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load(str(mesh_path))
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
    raise ValueError(f"Unable to load mesh: {mesh_path}")


def sample_points(mesh: trimesh.Trimesh, count: int, seed: int) -> np.ndarray:
    if mesh is None or len(mesh.vertices) == 0:
        return np.zeros((0, 3), dtype=float)
    rng = np.random.default_rng(int(seed))
    if getattr(mesh, "faces", None) is not None and len(mesh.faces) > 0:
        sampled, _ = trimesh.sample.sample_surface(mesh, int(count), seed=rng)
        return np.asarray(sampled, dtype=float)
    verts = np.asarray(mesh.vertices, dtype=float)
    if len(verts) <= int(count):
        return verts
    idx = rng.choice(len(verts), int(count), replace=False)
    return verts[idx]


def find_member_payload(features: Dict[str, Any], member_index: int) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    for motif_payload in features.get("spoke_motif_sections") or []:
        for member_payload in motif_payload.get("members", []) or []:
            try:
                if int(member_payload.get("member_index", -1)) == int(member_index):
                    return motif_payload, member_payload
            except Exception:
                continue
    return None, None


def submesh_cache_path(output_dir: Path, member_index: int) -> Path:
    return output_dir / f"_member_src_submesh_{member_index}.stl"


def build_or_load_source_submesh(
    source_mesh: trimesh.Trimesh,
    features: Dict[str, Any],
    member_index: int,
    output_dir: Path,
    reuse_cache: bool,
) -> Optional[trimesh.Trimesh]:
    cache_path = submesh_cache_path(output_dir, member_index)
    if reuse_cache and cache_path.exists():
        return load_mesh(cache_path)

    motif_payload, member_payload = find_member_payload(features, member_index)
    if member_payload is None:
        return None

    root_regions = features.get("spoke_root_regions") or []
    root_entry = root_regions[member_index] if 0 <= member_index < len(root_regions) else {}
    root_points = root_entry.get("points", []) if isinstance(root_entry, dict) else root_entry
    profile_hints = single_spoke.compute_member_hints(member_payload, root_points)
    submesh, _ = single_spoke.build_guided_submesh(source_mesh, member_payload, root_points, profile_hints)
    if submesh is None or len(submesh.vertices) == 0:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    submesh.export(str(cache_path))
    return submesh


def evaluate_pair(src_mesh: trimesh.Trimesh, cand_mesh: trimesh.Trimesh, sample_count: int, seed: int) -> Dict[str, float]:
    src_points = sample_points(src_mesh, count=sample_count, seed=seed)
    cand_points = sample_points(cand_mesh, count=sample_count, seed=seed + 17)

    front_src = src_points[:, [0, 1]]
    front_cand = cand_points[:, [0, 1]]
    side_src = src_points[:, [0, 2]]
    side_cand = cand_points[:, [0, 2]]

    tree_cand = cKDTree(cand_points) if len(cand_points) else None
    tree_src = cKDTree(src_points) if len(src_points) else None
    d_fwd = tree_cand.query(src_points, k=1)[0] if tree_cand is not None and len(src_points) else np.array([])
    d_bwd = tree_src.query(cand_points, k=1)[0] if tree_src is not None and len(cand_points) else np.array([])

    return {
        "front_overlap": float(projection_overlap_score(front_src, front_cand, bins=100)),
        "side_overlap": float(projection_overlap_score(side_src, side_cand, bins=96)),
        "spoke_overlap_proxy": float(projection_overlap_score(front_src, front_cand, bins=120)),
        "nn_mean_fwd_mm": float(np.mean(d_fwd)) if len(d_fwd) else float("nan"),
        "nn_mean_bwd_mm": float(np.mean(d_bwd)) if len(d_bwd) else float("nan"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fast per-member overlap diagnosis for spoke reconstruction.")
    parser.add_argument("--features", required=True, help="Features JSON path")
    parser.add_argument("--stl", required=True, help="Reference/source STL path")
    parser.add_argument("--member-dir", default=str(ROOT / "output"), help="Directory containing _member_diag_{i}.stl")
    parser.add_argument("--member-pattern", default="_member_diag_{member}.stl", help="Candidate member STL pattern")
    parser.add_argument("--member-count", type=int, default=10, help="Total member count to inspect")
    parser.add_argument("--sample-count", type=int, default=12000, help="Surface sample count per mesh")
    parser.add_argument("--output-json", required=True, help="Output diagnostics JSON path")
    parser.add_argument("--reuse-submesh-cache", action="store_true", help="Reuse cached _member_src_submesh_*.stl")
    args = parser.parse_args()

    features_path = Path(args.features).resolve()
    source_stl = Path(args.stl).resolve()
    member_dir = Path(args.member_dir).resolve()
    output_json = Path(args.output_json).resolve()

    with features_path.open("r", encoding="utf-8") as handle:
        features = json.load(handle)
    source_mesh = single_spoke.load_trimesh(source_stl, features=features)

    rows: List[Dict[str, Any]] = []
    for member_index in range(int(args.member_count)):
        candidate_name = str(args.member_pattern).format(member=member_index)
        candidate_path = member_dir / candidate_name
        row: Dict[str, Any] = {
            "member_index": int(member_index),
            "candidate_path": str(candidate_path),
            "status": "ok",
        }

        if not candidate_path.exists():
            row["status"] = "missing_candidate"
            rows.append(row)
            continue

        source_submesh = build_or_load_source_submesh(
            source_mesh=source_mesh,
            features=features,
            member_index=member_index,
            output_dir=member_dir,
            reuse_cache=bool(args.reuse_submesh_cache),
        )
        if source_submesh is None:
            row["status"] = "missing_source_submesh"
            rows.append(row)
            continue

        try:
            candidate_mesh = load_mesh(candidate_path)
            metrics = evaluate_pair(
                src_mesh=source_submesh,
                cand_mesh=candidate_mesh,
                sample_count=int(args.sample_count),
                seed=20260418 + member_index,
            )
            row.update(metrics)
            row["source_submesh_path"] = str(submesh_cache_path(member_dir, member_index))
            row["source_faces"] = int(len(source_submesh.faces)) if getattr(source_submesh, "faces", None) is not None else 0
            row["candidate_faces"] = int(len(candidate_mesh.faces)) if getattr(candidate_mesh, "faces", None) is not None else 0
        except Exception as exc:
            row["status"] = "failed"
            row["error"] = str(exc)
        rows.append(row)

    scored = [row for row in rows if row.get("status") == "ok"]
    scored.sort(key=lambda item: float(item.get("spoke_overlap_proxy", -1.0)))
    summary = {
        "worst_members_by_overlap": [int(item["member_index"]) for item in scored[:5]],
        "best_members_by_overlap": [int(item["member_index"]) for item in scored[-3:]],
        "min_spoke_overlap_proxy": float(scored[0]["spoke_overlap_proxy"]) if scored else None,
        "max_spoke_overlap_proxy": float(scored[-1]["spoke_overlap_proxy"]) if scored else None,
        "mean_spoke_overlap_proxy": float(np.mean([float(item["spoke_overlap_proxy"]) for item in scored])) if scored else None,
        "inspected_members": int(len(rows)),
        "scored_members": int(len(scored)),
    }

    payload = {
        "features": str(features_path),
        "stl": str(source_stl),
        "member_dir": str(member_dir),
        "member_pattern": str(args.member_pattern),
        "member_count": int(args.member_count),
        "sample_count": int(args.sample_count),
        "summary": summary,
        "members": rows,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[*] Diagnostics saved: {output_json}")
    print(
        f"[*] overlap proxy range: "
        f"{summary['min_spoke_overlap_proxy']} .. {summary['max_spoke_overlap_proxy']}"
    )
    print(f"[*] worst members: {summary['worst_members_by_overlap']}")


if __name__ == "__main__":
    main()
