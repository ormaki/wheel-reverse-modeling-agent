from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import cadquery as cq
import numpy as np
import trimesh
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.build_exactmembers_fused_assembly as exactmembers
import tools.run_single_spoke_mesh_to_cad as single_spoke


def parse_member_set(raw: Optional[str]) -> Optional[set[int]]:
    if not raw:
        return None
    values: set[int] = set()
    for token in str(raw).split(","):
        token = token.strip()
        if token:
            values.add(int(token))
    return values if values else None


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def as_np3(values: Sequence[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=float).reshape(3)
    return arr


def normalize(vec: np.ndarray, fallback: Optional[np.ndarray] = None) -> np.ndarray:
    length = float(np.linalg.norm(vec))
    if length <= 1e-9:
        if fallback is None:
            raise ValueError("zero-length vector")
        return normalize(np.asarray(fallback, dtype=float))
    return vec / length


def iter_polygons(geom: Any) -> Iterable[Polygon]:
    if geom is None or getattr(geom, "is_empty", True):
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    geoms = getattr(geom, "geoms", None)
    if geoms is None:
        return []
    return [poly for poly in geoms if isinstance(poly, Polygon)]


def local_polygon_from_points(points_local: Sequence[Sequence[float]], min_area: float) -> Optional[Polygon]:
    pts = [(float(x), float(y)) for x, y in points_local if len((x, y)) == 2]
    if len(pts) < 3:
        return None
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    poly = Polygon(pts)
    if poly.is_empty:
        return None
    try:
        poly = poly.buffer(0.0)
    except Exception:
        return None
    if poly.is_empty:
        return None
    if isinstance(poly, MultiPolygon):
        poly = max(poly.geoms, key=lambda g: float(g.area))
    if float(poly.area) < float(min_area):
        return None
    return poly


def section_loops_local(
    mesh: trimesh.Trimesh,
    origin: np.ndarray,
    normal: np.ndarray,
    x_dir: np.ndarray,
    y_dir: np.ndarray,
    min_area: float,
) -> List[Polygon]:
    try:
        sec = mesh.section(plane_origin=origin, plane_normal=normal)
    except Exception:
        sec = None
    if sec is None:
        return []

    loops: List[Polygon] = []
    for path in sec.discrete:
        if path is None:
            continue
        if len(path) < 3:
            continue
        pts_local: List[Tuple[float, float]] = []
        for p in path:
            p3 = np.asarray(p, dtype=float)
            rel = p3 - origin
            u = float(np.dot(rel, x_dir))
            v = float(np.dot(rel, y_dir))
            pts_local.append((u, v))
        if len(pts_local) < 3:
            continue
        if pts_local[0] != pts_local[-1]:
            pts_local.append(pts_local[0])
        poly = Polygon(pts_local)
        if poly.is_empty:
            continue
        try:
            poly = poly.buffer(0.0)
        except Exception:
            continue
        if poly.is_empty:
            continue
        if isinstance(poly, MultiPolygon):
            poly = max(poly.geoms, key=lambda g: float(g.area))
        if float(poly.area) < float(min_area):
            continue
        loops.append(poly)
    return loops


def select_member_diff_polygon(
    ref_polys: Sequence[Polygon],
    base_polys: Sequence[Polygon],
    guide_poly: Optional[Polygon],
    min_area: float,
) -> Optional[Polygon]:
    if not ref_polys:
        return None
    ref_union = unary_union(ref_polys)
    if base_polys:
        base_union = unary_union(base_polys)
        diff_geom = ref_union.difference(base_union)
    else:
        diff_geom = ref_union

    candidates = [poly for poly in iter_polygons(diff_geom) if float(poly.area) >= float(min_area)]
    if not candidates:
        return None

    if guide_poly is None:
        return max(candidates, key=lambda p: float(p.area))

    scored: List[Tuple[float, Polygon]] = []
    gc = guide_poly.centroid
    for poly in candidates:
        inter_area = float(poly.intersection(guide_poly).area)
        union_area = float(poly.union(guide_poly).area)
        iou = inter_area / max(1e-9, union_area)
        dc = poly.centroid
        dist = math.hypot(float(dc.x - gc.x), float(dc.y - gc.y))
        score = iou - (0.01 * dist)
        scored.append((score, poly))
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[0][1]


def polygon_to_points_local(poly: Polygon) -> List[List[float]]:
    pts = [(float(x), float(y)) for x, y in list(poly.exterior.coords)]
    if len(pts) < 4:
        return []
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    return [[float(x), float(y)] for x, y in pts]


def collect_export_shapes(obj: Any) -> List[Any]:
    if obj is None:
        return []
    if isinstance(obj, cq.Workplane):
        try:
            vals = obj.vals()
        except Exception:
            vals = []
        shapes = [val for val in vals if hasattr(val, "wrapped")]
        if shapes:
            return shapes
        try:
            val = obj.val()
            if hasattr(val, "wrapped"):
                return [val]
        except Exception:
            return []
    elif hasattr(obj, "wrapped"):
        return [obj]
    return []


def filter_valid_export_shapes(shapes: Sequence[Any], label: str) -> List[Any]:
    valid: List[Any] = []
    for idx, shape in enumerate(shapes):
        try:
            is_valid = bool(shape.isValid()) if hasattr(shape, "isValid") else True
        except Exception:
            is_valid = False
        if not is_valid:
            print(f"[!] {label} shape {idx} rejected: invalid")
            continue
        valid.append(shape)
    return valid


def recover_export_body(body: Any, namespace: Dict[str, Any]) -> Any:
    body_has_valid_shape_fn = namespace.get("body_has_valid_shape")
    if callable(body_has_valid_shape_fn):
        try:
            if bool(body_has_valid_shape_fn(body)):
                return body
        except Exception:
            pass
    select_largest_fn = namespace.get("select_largest_solid_body")
    if callable(select_largest_fn):
        try:
            largest = select_largest_fn(body, "section-diff export")
            if largest is not None:
                return largest
        except Exception:
            pass
    return body


def export_step_occ(obj: Any, output_path: Path, namespace: Dict[str, Any]) -> Any:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export_obj = recover_export_body(obj, namespace)
    shapes = filter_valid_export_shapes(collect_export_shapes(export_obj), "STEP export")
    if not shapes:
        raise RuntimeError("no valid shapes for STEP export")
    export_shape = shapes[0] if len(shapes) == 1 else cq.Compound.makeCompound(shapes)
    if exactmembers.pipeline.OCP_STEP_EXPORT_AVAILABLE:
        exactmembers.pipeline.Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
        writer = exactmembers.pipeline.STEPControl_Writer()
        writer.Transfer(export_shape.wrapped, exactmembers.pipeline.STEPControl_AsIs)
        status = writer.Write(str(output_path))
        if int(status) != int(exactmembers.pipeline.IFSelect_RetDone):
            raise RuntimeError(f"OCC STEP export failed with status {int(status)}")
    else:
        cq.exporters.export(export_shape, str(output_path))
    return export_shape


def build_base_mesh_from_step(step_path: Path, linear_tol: float, angular_tol: float) -> trimesh.Trimesh:
    body = cq.importers.importStep(str(step_path))
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as handle:
        tmp_stl = Path(handle.name)
    cq.exporters.export(body, str(tmp_stl), tolerance=float(linear_tol), angularTolerance=float(angular_tol))
    mesh = trimesh.load_mesh(str(tmp_stl), force="mesh")
    try:
        tmp_stl.unlink(missing_ok=True)
    except Exception:
        pass
    if not isinstance(mesh, trimesh.Trimesh):
        raise RuntimeError("failed to build base mesh from STEP")
    return mesh


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild spoke members via section-difference (reference mesh minus no-spoke base mesh) and fuse into no-spoke STEP."
    )
    parser.add_argument("--features", required=True, help="Features JSON path (with spoke_motif_sections)")
    parser.add_argument("--base-step", required=True, help="No-spoke base STEP path")
    parser.add_argument("--reference-stl", default=str(Path("input") / "wheel.stl"), help="Reference STL path")
    parser.add_argument("--output-step", required=True, help="Output STEP path")
    parser.add_argument("--output-stl", required=True, help="Output STL path")
    parser.add_argument("--meta-out", default=None, help="Optional metadata JSON path")
    parser.add_argument("--min-section-area", type=float, default=4.0, help="Minimum kept section polygon area")
    parser.add_argument("--slice-stride", type=int, default=1, help="Use every N-th section for rebuild")
    parser.add_argument("--max-sections-per-member", type=int, default=0, help="Optional cap for selected sections per member; 0 means no cap")
    parser.add_argument("--base-mesh-linear-tol", type=float, default=0.7, help="Linear meshing tolerance when triangulating base STEP")
    parser.add_argument("--base-mesh-angular-tol", type=float, default=0.7, help="Angular meshing tolerance when triangulating base STEP")
    parser.add_argument("--only-members", default=None, help="Optional comma-separated member indices to rebuild")
    parser.add_argument("--build-only-replaced-members", action="store_true", help="Only build members that had at least one section replaced")
    parser.add_argument("--member-only-output", action="store_true", help="Export rebuilt member solids only, without the no-spoke base")
    parser.add_argument("--force-local-only", action="store_true", help="Clear actual-z/tip payloads and force local-section-only member rebuild")
    parser.add_argument("--max-center-offset", type=float, default=6.0, help="Reject extracted section when centroid offset from guide exceeds this local-mm threshold")
    parser.add_argument("--min-area-ratio", type=float, default=0.45, help="Reject extracted section when area/guide_area is below this ratio")
    parser.add_argument("--max-area-ratio", type=float, default=1.85, help="Reject extracted section when area/guide_area exceeds this ratio")
    args = parser.parse_args()

    features_path = Path(args.features).resolve()
    base_step_path = Path(args.base_step).resolve()
    reference_stl_path = Path(args.reference_stl).resolve()
    output_step_path = Path(args.output_step).resolve()
    output_stl_path = Path(args.output_stl).resolve()
    meta_out_path = Path(args.meta_out).resolve() if args.meta_out else None
    only_members = parse_member_set(args.only_members)

    features = load_json(features_path)
    features_local = deepcopy(features)

    ref_mesh = single_spoke.load_trimesh(reference_stl_path, features=features_local)
    if not isinstance(ref_mesh, trimesh.Trimesh):
        raise RuntimeError("reference mesh load failed")
    base_mesh = build_base_mesh_from_step(
        base_step_path,
        linear_tol=float(args.base_mesh_linear_tol),
        angular_tol=float(args.base_mesh_angular_tol),
    )

    motif_sections = features_local.get("spoke_motif_sections") or []
    if not motif_sections:
        raise RuntimeError("features missing spoke_motif_sections")

    rebuilt_count = 0
    replaced_member_indices: set[int] = set()
    section_stats: List[Dict[str, Any]] = []
    for motif_idx, motif_payload in enumerate(motif_sections):
        members = motif_payload.get("members") or []
        for member_idx, member_payload in enumerate(members):
            member_index = int(member_payload.get("member_index", member_idx))
            if only_members is not None and member_index not in only_members:
                continue
            sections = list(member_payload.get("sections") or [])
            if not sections:
                continue
            print(f"[*] section-diff rebuild motif={motif_idx} member={member_index} sections={len(sections)}")
            selected: List[Tuple[int, Dict[str, Any]]] = []
            stride = max(1, int(args.slice_stride))
            for sec_index, sec in enumerate(sections):
                if (sec_index % stride) != 0:
                    continue
                selected.append((sec_index, sec))
            if int(args.max_sections_per_member) > 0 and len(selected) > int(args.max_sections_per_member):
                idxs = np.linspace(0, len(selected) - 1, int(args.max_sections_per_member))
                keep = sorted({int(round(float(v))) for v in idxs})
                selected = [selected[k] for k in keep]

            member_replaced = 0
            for sec_index, section_payload in selected:
                origin = as_np3(section_payload.get("plane_origin") or [0.0, 0.0, 0.0])
                normal = normalize(as_np3(section_payload.get("plane_normal") or [0.0, 0.0, 1.0]), fallback=np.array([0.0, 0.0, 1.0]))
                x_dir = normalize(as_np3(section_payload.get("plane_x_dir") or [1.0, 0.0, 0.0]), fallback=np.array([1.0, 0.0, 0.0]))
                y_dir = normalize(np.cross(normal, x_dir), fallback=np.array([0.0, 1.0, 0.0]))
                x_dir = normalize(np.cross(y_dir, normal), fallback=x_dir)

                guide_poly = local_polygon_from_points(section_payload.get("points_local") or [], min_area=float(args.min_section_area))
                ref_polys = section_loops_local(
                    ref_mesh,
                    origin=origin,
                    normal=normal,
                    x_dir=x_dir,
                    y_dir=y_dir,
                    min_area=float(args.min_section_area),
                )
                base_polys = section_loops_local(
                    base_mesh,
                    origin=origin,
                    normal=normal,
                    x_dir=x_dir,
                    y_dir=y_dir,
                    min_area=float(args.min_section_area),
                )
                chosen = select_member_diff_polygon(
                    ref_polys,
                    base_polys,
                    guide_poly=guide_poly,
                    min_area=float(args.min_section_area),
                )
                if chosen is None:
                    continue
                if guide_poly is not None:
                    guide_area = float(guide_poly.area)
                    chosen_area = float(chosen.area)
                    area_ratio = chosen_area / max(1e-9, guide_area)
                    center_offset = math.hypot(
                        float(chosen.centroid.x - guide_poly.centroid.x),
                        float(chosen.centroid.y - guide_poly.centroid.y),
                    )
                    if center_offset > float(args.max_center_offset):
                        continue
                    if area_ratio < float(args.min_area_ratio) or area_ratio > float(args.max_area_ratio):
                        continue
                pts = polygon_to_points_local(chosen)
                if len(pts) < 3:
                    continue
                section_payload["points_local"] = pts
                x_min = float(min(p[0] for p in pts))
                x_max = float(max(p[0] for p in pts))
                y_min = float(min(p[1] for p in pts))
                y_max = float(max(p[1] for p in pts))
                section_payload["local_width"] = float(x_max - x_min)
                section_payload["local_height"] = float(y_max - y_min)
                member_replaced += 1

            section_stats.append(
                {
                    "motif_index": int(motif_idx),
                    "member_index": int(member_index),
                    "selected_sections": int(len(selected)),
                    "replaced_sections": int(member_replaced),
                }
            )
            print(f"[*] section-diff result motif={motif_idx} member={member_index} replaced={member_replaced}/{len(selected)}")
            if member_replaced > 0:
                rebuilt_count += 1
                replaced_member_indices.add(member_index)

    if rebuilt_count <= 0:
        raise RuntimeError("no member sections were rebuilt from section difference")

    generated_namespace = exactmembers.prepare_generated_namespace(features_local)
    build_member_fn = generated_namespace.get("build_motif_member_spoke")
    body_valid_fn = generated_namespace.get("body_has_valid_shape")
    if not callable(build_member_fn):
        raise RuntimeError("generated namespace missing build_motif_member_spoke")

    base_body = cq.importers.importStep(str(base_step_path))
    base_shapes = filter_valid_export_shapes(collect_export_shapes(base_body), "base import")
    if not base_shapes:
        raise RuntimeError("no valid base solid from STEP")
    final_shapes: List[Any] = [] if bool(args.member_only_output) else [base_shapes[0]]
    built_member_solids = 0
    skipped_members = 0
    for motif_payload in features_local.get("spoke_motif_sections") or []:
        for member_payload in motif_payload.get("members", []) or []:
            member_index = int(member_payload.get("member_index", -1))
            if only_members is not None and member_index not in only_members:
                continue
            if bool(args.build_only_replaced_members) and member_index not in replaced_member_indices:
                continue
            member_payload_build = member_payload
            if bool(args.force_local_only):
                member_payload_build = deepcopy(member_payload)
                member_payload_build["actual_z_profiles"] = []
                member_payload_build["actual_z_profile_count"] = 0
                member_payload_build["actual_z_stack_mode"] = "none"
                member_payload_build["tip_sections"] = []
                member_payload_build["actual_z_prefer_local_section"] = True
            try:
                member_body = build_member_fn(member_payload_build, motif_payload)
            except Exception:
                member_body = None
            if member_body is None:
                skipped_members += 1
                print(f"[!] build skip member={member_index}: build returned None")
                continue
            if callable(body_valid_fn):
                try:
                    if not bool(body_valid_fn(member_body)):
                        skipped_members += 1
                        print(f"[!] build skip member={member_index}: invalid body")
                        continue
                except Exception:
                    pass
            member_shapes = filter_valid_export_shapes(collect_export_shapes(member_body), f"member {member_index} export")
            if not member_shapes:
                skipped_members += 1
                print(f"[!] build skip member={member_index}: no valid member shape")
                continue
            member_shape = max(
                member_shapes,
                key=lambda shp: float(getattr(shp, "Volume", lambda: 0.0)() if callable(getattr(shp, "Volume", None)) else 0.0),
            )
            final_shapes.append(member_shape)
            built_member_solids += 1
            print(f"[*] build appended member={member_index}")

    output_step_path.parent.mkdir(parents=True, exist_ok=True)
    output_stl_path.parent.mkdir(parents=True, exist_ok=True)
    export_input = final_shapes[0] if len(final_shapes) == 1 else cq.Compound.makeCompound(final_shapes)
    export_shape = export_step_occ(export_input, output_step_path, generated_namespace)
    cq.exporters.export(export_shape, str(output_stl_path), tolerance=0.8, angularTolerance=0.8)

    if meta_out_path is not None:
        meta_out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "features": str(features_path),
            "base_step": str(base_step_path),
            "reference_stl": str(reference_stl_path),
            "output_step": str(output_step_path),
            "output_stl": str(output_stl_path),
            "rebuilt_member_count": int(rebuilt_count),
            "built_member_solids": int(built_member_solids),
            "skipped_members": int(skipped_members),
            "member_only_output": bool(args.member_only_output),
            "section_stats": section_stats,
        }
        meta_out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[*] rebuilt members: {rebuilt_count}")
    print(f"[*] built member solids: {built_member_solids}")
    print(f"[*] skipped members: {skipped_members}")
    print(f"[*] output step: {output_step_path}")
    print(f"[*] output stl: {output_stl_path}")


if __name__ == "__main__":
    main()
