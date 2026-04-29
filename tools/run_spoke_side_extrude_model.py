from __future__ import annotations

import argparse
import json
import math
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cadquery as cq
import numpy as np
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.run_section_diff_spoke_rebuild as section_diff
import tools.run_single_spoke_mesh_to_cad as single_spoke
import tools.build_exactmembers_fused_assembly as exactmembers


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_member_set(raw: Optional[str]) -> Optional[set[int]]:
    if not raw:
        return None
    values: set[int] = set()
    for token in str(raw).split(","):
        token = token.strip()
        if token:
            values.add(int(token))
    return values if values else None


def iter_polygons(geom: Any) -> List[Polygon]:
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


def positive_meridional_diff_polygon(
    ref_mesh: Any,
    base_mesh: Any,
    member_payload: Dict[str, Any],
    min_area: float,
) -> Optional[Polygon]:
    sections = member_payload.get("sections") or []
    station_rs = [float(sec.get("station_r", 0.0)) for sec in sections]
    if station_rs:
        exp_r0 = max(0.0, min(station_rs) - 10.0)
        exp_r1 = max(station_rs) + 18.0
    else:
        exp_r0, exp_r1 = 0.0, 400.0

    z_values: List[float] = []
    for sec in sections:
        origin_xyz = sec.get("plane_origin") or [0.0, 0.0, 0.0]
        points_local = sec.get("points_local") or []
        if len(origin_xyz) < 3 or not points_local:
            continue
        base_z = float(origin_xyz[2])
        ys = [float(pt[1]) for pt in points_local if len(pt) >= 2]
        if ys:
            z_values.extend([base_z + min(ys), base_z + max(ys)])
    if z_values:
        exp_z0 = min(z_values) - 4.0
        exp_z1 = max(z_values) + 4.0
    else:
        exp_z0, exp_z1 = -200.0, 200.0

    expected_box = box(exp_r0, exp_z0, exp_r1, exp_z1)
    origin = np.asarray([0.0, 0.0, 0.0], dtype=float)
    z_dir = np.asarray([0.0, 0.0, 1.0], dtype=float)

    best: Optional[Tuple[float, Polygon]] = None
    base_angle = float(member_payload.get("angle", 0.0))
    search_offsets = [0.0, -5.0, 5.0, -10.0, 10.0, -15.0, 15.0]
    for offset_deg in search_offsets:
        angle_rad = math.radians(base_angle + float(offset_deg))
        radial_dir = np.asarray([math.cos(angle_rad), math.sin(angle_rad), 0.0], dtype=float)
        tangent_dir = np.asarray([-math.sin(angle_rad), math.cos(angle_rad), 0.0], dtype=float)
        ref_polys = section_diff.section_loops_local(
            ref_mesh,
            origin=origin,
            normal=tangent_dir,
            x_dir=radial_dir,
            y_dir=z_dir,
            min_area=float(min_area),
        )
        base_polys = section_diff.section_loops_local(
            base_mesh,
            origin=origin,
            normal=tangent_dir,
            x_dir=radial_dir,
            y_dir=z_dir,
            min_area=float(min_area),
        )
        if not ref_polys:
            continue
        diff_geom = unary_union(ref_polys)
        if base_polys:
            diff_geom = diff_geom.difference(unary_union(base_polys))
        for poly in iter_polygons(diff_geom):
            if float(poly.area) < float(min_area):
                continue
            cx = float(poly.centroid.x)
            if cx <= 0.0:
                continue
            inter_area = float(poly.intersection(expected_box).area)
            if inter_area <= 0.0:
                continue
            union_area = float(poly.union(expected_box).area)
            iou = inter_area / max(1e-9, union_area)
            score = (
                (5.0 * iou)
                + (0.001 * inter_area)
                - (0.0002 * abs(cx - 0.5 * (exp_r0 + exp_r1)))
                - (0.01 * abs(float(offset_deg)))
            )
            if best is None or score > best[0]:
                best = (score, poly)
    if best is None:
        return None
    poly = best[1]
    try:
        poly = poly.buffer(0.0)
    except Exception:
        return None
    if poly.is_empty:
        return None
    if isinstance(poly, MultiPolygon):
        poly = max(poly.geoms, key=lambda g: float(g.area))
    return poly


def extract_section_band_samples(
    ref_mesh: Any,
    base_mesh: Any,
    member_payload: Dict[str, Any],
    min_area: float,
    max_center_offset: float,
    min_area_ratio: float,
    max_area_ratio: float,
) -> List[Tuple[float, float, float, float]]:
    samples: List[Tuple[float, float, float, float]] = []
    for sec in member_payload.get("sections") or []:
        origin = section_diff.as_np3(sec.get("plane_origin") or [0.0, 0.0, 0.0])
        normal = section_diff.normalize(section_diff.as_np3(sec.get("plane_normal") or [0.0, 0.0, 1.0]), fallback=np.array([0.0, 0.0, 1.0]))
        x_dir = section_diff.normalize(section_diff.as_np3(sec.get("plane_x_dir") or [1.0, 0.0, 0.0]), fallback=np.array([1.0, 0.0, 0.0]))
        y_dir = section_diff.normalize(np.cross(normal, x_dir), fallback=np.array([0.0, 1.0, 0.0]))
        x_dir = section_diff.normalize(np.cross(y_dir, normal), fallback=x_dir)

        guide_poly = section_diff.local_polygon_from_points(sec.get("points_local") or [], min_area=0.1)
        ref_polys = section_diff.section_loops_local(ref_mesh, origin, normal, x_dir, y_dir, min_area=float(min_area))
        base_polys = section_diff.section_loops_local(base_mesh, origin, normal, x_dir, y_dir, min_area=float(min_area))
        chosen = section_diff.select_member_diff_polygon(ref_polys, base_polys, guide_poly, min_area=float(min_area))
        if chosen is None or guide_poly is None:
            continue
        area_ratio = float(chosen.area) / max(1e-9, float(guide_poly.area))
        center_offset = math.hypot(
            float(chosen.centroid.x - guide_poly.centroid.x),
            float(chosen.centroid.y - guide_poly.centroid.y),
        )
        if center_offset > float(max_center_offset):
            continue
        if area_ratio < float(min_area_ratio) or area_ratio > float(max_area_ratio):
            continue
        bounds = chosen.bounds
        width = float(bounds[2] - bounds[0])
        z0 = float(origin[2] + bounds[1])
        z1 = float(origin[2] + bounds[3])
        station_r = float(sec.get("station_r", 0.0))
        if station_r > 0.0 and width > 0.5:
            samples.append((station_r, width, z0, z1))

    if not samples:
        for sec in member_payload.get("sections") or []:
            station_r = float(sec.get("station_r", 0.0))
            width = float(sec.get("target_width", sec.get("local_width", 0.0)) or 0.0)
            target_z_band = sec.get("target_z_band") or [0.0, 0.0]
            if len(target_z_band) >= 2:
                z0 = float(target_z_band[0])
                z1 = float(target_z_band[1])
            else:
                z0 = float((sec.get("plane_origin") or [0.0, 0.0, 0.0])[2] - 10.0)
                z1 = float((sec.get("plane_origin") or [0.0, 0.0, 0.0])[2] + 10.0)
            if station_r > 0.0 and width > 0.5:
                samples.append((station_r, width, z0, z1))
    samples.sort(key=lambda item: item[0])
    return samples


def apply_section_replacements(
    ref_mesh: Any,
    base_mesh: Any,
    member_payload: Dict[str, Any],
    min_area: float,
    max_center_offset: float,
    min_area_ratio: float,
    max_area_ratio: float,
) -> Tuple[Dict[str, Any], int]:
    patched = deepcopy(member_payload)
    replaced = 0
    sections = patched.get("sections") or []
    for sec in sections:
        origin = section_diff.as_np3(sec.get("plane_origin") or [0.0, 0.0, 0.0])
        normal = section_diff.normalize(section_diff.as_np3(sec.get("plane_normal") or [0.0, 0.0, 1.0]), fallback=np.array([0.0, 0.0, 1.0]))
        x_dir = section_diff.normalize(section_diff.as_np3(sec.get("plane_x_dir") or [1.0, 0.0, 0.0]), fallback=np.array([1.0, 0.0, 0.0]))
        y_dir = section_diff.normalize(np.cross(normal, x_dir), fallback=np.array([0.0, 1.0, 0.0]))
        x_dir = section_diff.normalize(np.cross(y_dir, normal), fallback=x_dir)

        guide_poly = section_diff.local_polygon_from_points(sec.get("points_local") or [], min_area=0.1)
        ref_polys = section_diff.section_loops_local(ref_mesh, origin, normal, x_dir, y_dir, min_area=float(min_area))
        base_polys = section_diff.section_loops_local(base_mesh, origin, normal, x_dir, y_dir, min_area=float(min_area))
        chosen = section_diff.select_member_diff_polygon(ref_polys, base_polys, guide_poly, min_area=float(min_area))
        if chosen is None or guide_poly is None:
            continue
        area_ratio = float(chosen.area) / max(1e-9, float(guide_poly.area))
        center_offset = math.hypot(
            float(chosen.centroid.x - guide_poly.centroid.x),
            float(chosen.centroid.y - guide_poly.centroid.y),
        )
        if center_offset > float(max_center_offset):
            continue
        if area_ratio < float(min_area_ratio) or area_ratio > float(max_area_ratio):
            continue
        pts = section_diff.polygon_to_points_local(chosen)
        if len(pts) < 3:
            continue
        sec["points_local"] = pts
        sec["local_width"] = float(max(p[0] for p in pts) - min(p[0] for p in pts))
        sec["local_height"] = float(max(p[1] for p in pts) - min(p[1] for p in pts))
        replaced += 1
    patched["actual_z_profiles"] = []
    patched["actual_z_profile_count"] = 0
    patched["actual_z_stack_mode"] = "none"
    patched["tip_sections"] = []
    patched["actual_z_prefer_local_section"] = True
    return patched, replaced


def build_side_band_solids(
    silhouette_poly: Polygon,
    band_samples: Sequence[Tuple[float, float, float, float]],
    angle_deg: float,
    min_band_area: float,
    global_width_scale: float,
    root_width_scale: float,
    tip_width_scale: float,
) -> List[Any]:
    if not band_samples:
        return []
    angle_rad = math.radians(float(angle_deg))
    radial_dir = (math.cos(angle_rad), math.sin(angle_rad), 0.0)
    tangent_dir = (math.sin(angle_rad), -math.cos(angle_rad), 0.0)
    plane = cq.Plane(origin=(0.0, 0.0, 0.0), xDir=radial_dir, normal=tangent_dir)
    wp = cq.Workplane(plane)
    sil_r0 = float(silhouette_poly.bounds[0])
    sil_r1 = float(silhouette_poly.bounds[2])
    sil_span = max(1e-6, sil_r1 - sil_r0)

    samples = list(band_samples)
    if len(samples) == 1:
        r0 = float(silhouette_poly.bounds[0])
        r1 = float(silhouette_poly.bounds[2])
        _, width0, z0, z1 = samples[0]
        samples = [(r0, width0, z0, z1), (r1, width0, z0, z1)]

    solids: List[Any] = []
    for (r_a, w_a, z0_a, z1_a), (r_b, w_b, z0_b, z1_b) in zip(samples[:-1], samples[1:]):
        left = float(min(r_a, r_b))
        right = float(max(r_a, r_b))
        if right - left < 1.0:
            continue
        band_z0 = float(min(z0_a, z0_b))
        band_z1 = float(max(z1_a, z1_b))
        band_geom = silhouette_poly.intersection(box(left, band_z0, right, band_z1))
        band_polys = [poly for poly in iter_polygons(band_geom) if float(poly.area) >= float(min_band_area)]
        if not band_polys:
            continue
        mid_r = 0.5 * (left + right)
        phase = max(0.0, min(1.0, (mid_r - sil_r0) / sil_span))
        width_scale = float(global_width_scale)
        if phase < 0.35:
            local_phase = phase / 0.35
            width_scale *= float(root_width_scale) + ((1.0 - float(root_width_scale)) * local_phase)
        elif phase > 0.70:
            local_phase = (phase - 0.70) / 0.30
            width_scale *= 1.0 + ((float(tip_width_scale) - 1.0) * local_phase)
        width = max(0.5, 0.5 * (float(w_a) + float(w_b)) * width_scale)
        for poly in band_polys:
            pts = [(float(x), float(y)) for x, y in list(poly.exterior.coords)]
            if len(pts) < 4:
                continue
            if pts[0] == pts[-1]:
                pts = pts[:-1]
            try:
                solid = wp.polyline(pts).close().extrude(0.5 * float(width), both=True).val()
            except Exception:
                continue
            solids.append(solid)
    return solids


def build_full_silhouette_solid(
    silhouette_poly: Polygon,
    band_samples: Sequence[Tuple[float, float, float, float]],
    angle_deg: float,
    global_width_scale: float,
    root_width_scale: float,
    tip_width_scale: float,
    radial_clip: Optional[Tuple[float, float]] = None,
) -> Optional[Any]:
    if silhouette_poly is None or silhouette_poly.is_empty or not band_samples:
        return None
    work_poly = silhouette_poly
    if radial_clip is not None:
        r0, r1 = radial_clip
        clipped = work_poly.intersection(box(float(r0), -1000.0, float(r1), 1000.0))
        polys = [poly for poly in iter_polygons(clipped) if float(poly.area) >= 5.0]
        if not polys:
            return None
        work_poly = max(polys, key=lambda poly: float(poly.area))
    pts = [(float(x), float(y)) for x, y in list(silhouette_poly.exterior.coords)]
    if work_poly is not silhouette_poly:
        pts = [(float(x), float(y)) for x, y in list(work_poly.exterior.coords)]
    if len(pts) < 4:
        return None
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return None

    samples = sorted(band_samples, key=lambda item: float(item[0]))
    widths = np.asarray([float(item[1]) for item in samples], dtype=float)
    rs = np.asarray([float(item[0]) for item in samples], dtype=float)
    r0 = float(np.min(rs))
    r1 = float(np.max(rs))
    r_mid = float(0.5 * (r0 + r1))
    root_widths = widths[rs <= (r0 + 0.38 * max(1e-6, r1 - r0))]
    tip_widths = widths[rs >= (r0 + 0.68 * max(1e-6, r1 - r0))]

    base_width = float(np.median(widths))
    if len(root_widths) > 0:
        base_width = max(base_width, float(np.median(root_widths)) * float(root_width_scale))
    if len(tip_widths) > 0:
        base_width = 0.7 * base_width + 0.3 * (float(np.median(tip_widths)) * float(tip_width_scale))
    base_width *= float(global_width_scale)
    base_width = max(0.8, base_width)

    angle_rad = math.radians(float(angle_deg))
    radial_dir = (math.cos(angle_rad), math.sin(angle_rad), 0.0)
    tangent_dir = (math.sin(angle_rad), -math.cos(angle_rad), 0.0)
    plane = cq.Plane(origin=(0.0, 0.0, 0.0), xDir=radial_dir, normal=tangent_dir)
    wp = cq.Workplane(plane)
    try:
        return wp.polyline(pts).close().extrude(0.5 * base_width, both=True).val()
    except Exception:
        return None


def fuse_member_solids(solids: Sequence[Any]) -> Any:
    if not solids:
        return None
    fused = solids[0]
    for solid in solids[1:]:
        try:
            fused = fused.fuse(solid)
        except Exception:
            return cq.Compound.makeCompound(list(solids))
    return fused


def refine_member_shape_by_intersection(
    member_shape: Any,
    member_payload: Dict[str, Any],
    motif_payload: Dict[str, Any],
    build_member_fn: Any,
    body_valid_fn: Any,
) -> Any:
    try:
        local_body = build_member_fn(member_payload, motif_payload)
    except Exception:
        return member_shape
    if local_body is None:
        return member_shape
    if callable(body_valid_fn):
        try:
            if not bool(body_valid_fn(local_body)):
                return member_shape
        except Exception:
            return member_shape
    local_shapes = section_diff.filter_valid_export_shapes(section_diff.collect_export_shapes(local_body), "local refine")
    if not local_shapes:
        return member_shape
    def _shape_volume(shape: Any) -> float:
        volume_attr = getattr(shape, "Volume", None)
        if callable(volume_attr):
            try:
                return float(volume_attr())
            except Exception:
                return 0.0
        return 0.0

    local_shape = max(local_shapes, key=_shape_volume)
    try:
        refined = member_shape.intersect(local_shape)
    except Exception:
        return member_shape
    refined_shapes = section_diff.filter_valid_export_shapes([refined], "intersect refine")
    return refined_shapes[0] if refined_shapes else member_shape


def main() -> None:
    parser = argparse.ArgumentParser(description="Build spoke bodies from meridional side silhouettes plus section-derived width bands.")
    parser.add_argument("--features", required=True, help="Features JSON path")
    parser.add_argument("--base-step", required=True, help="No-spoke STEP path")
    parser.add_argument("--reference-stl", default=str(ROOT / "input" / "wheel.stl"), help="Reference STL path")
    parser.add_argument("--output-step", required=True, help="Output STEP path")
    parser.add_argument("--output-stl", required=True, help="Output STL path")
    parser.add_argument("--meta-out", default=None, help="Optional metadata JSON path")
    parser.add_argument("--only-members", default=None, help="Optional comma-separated member indices")
    parser.add_argument("--min-area", type=float, default=5.0, help="Minimum 2D polygon area")
    parser.add_argument("--min-band-area", type=float, default=10.0, help="Minimum side band polygon area")
    parser.add_argument("--base-mesh-linear-tol", type=float, default=0.7, help="Base STEP triangulation tolerance")
    parser.add_argument("--base-mesh-angular-tol", type=float, default=0.7, help="Base STEP triangulation angular tolerance")
    parser.add_argument("--max-center-offset", type=float, default=6.0, help="Section width sample centroid gate")
    parser.add_argument("--min-area-ratio", type=float, default=0.45, help="Section width sample min area ratio")
    parser.add_argument("--max-area-ratio", type=float, default=1.85, help="Section width sample max area ratio")
    parser.add_argument("--refine-intersect", action="store_true", help="Intersect side-extrude base with local-section rebuilt member to trim overfill")
    parser.add_argument("--global-width-scale", type=float, default=1.0, help="Global width scale applied to all side-extrude bands")
    parser.add_argument("--root-width-scale", type=float, default=1.0, help="Width scale near the inner/root side of the silhouette")
    parser.add_argument("--tip-width-scale", type=float, default=1.0, help="Width scale near the outer/tip side of the silhouette")
    parser.add_argument("--base-mode", choices=["band", "full", "hybrid", "root_hybrid"], default="full", help="How to turn the radial silhouette into a base solid")
    parser.add_argument("--root-full-ratio", type=float, default=0.38, help="For root_hybrid, fraction of radial span covered by the full radial-section base")
    args = parser.parse_args()

    features_path = Path(args.features).resolve()
    base_step_path = Path(args.base_step).resolve()
    reference_stl_path = Path(args.reference_stl).resolve()
    output_step_path = Path(args.output_step).resolve()
    output_stl_path = Path(args.output_stl).resolve()
    meta_out_path = Path(args.meta_out).resolve() if args.meta_out else None
    only_members = parse_member_set(args.only_members)

    features = load_json(features_path)
    ref_mesh = single_spoke.load_trimesh(reference_stl_path, features=features)
    base_mesh = section_diff.build_base_mesh_from_step(
        base_step_path,
        linear_tol=float(args.base_mesh_linear_tol),
        angular_tol=float(args.base_mesh_angular_tol),
    )
    base_body = cq.importers.importStep(str(base_step_path))
    base_shapes = section_diff.filter_valid_export_shapes(section_diff.collect_export_shapes(base_body), "base import")
    if not base_shapes:
        raise RuntimeError("no valid base shapes")
    generated_namespace = exactmembers.prepare_generated_namespace(features) if bool(args.refine_intersect) else {}
    build_member_fn = generated_namespace.get("build_motif_member_spoke") if isinstance(generated_namespace, dict) else None
    body_valid_fn = generated_namespace.get("body_has_valid_shape") if isinstance(generated_namespace, dict) else None

    all_shapes: List[Any] = list(base_shapes)
    member_stats: List[Dict[str, Any]] = []
    for motif_payload in features.get("spoke_motif_sections") or []:
        for member_payload in motif_payload.get("members", []) or []:
            member_index = int(member_payload.get("member_index", -1))
            if only_members is not None and member_index not in only_members:
                continue

            silhouette_poly = positive_meridional_diff_polygon(
                ref_mesh,
                base_mesh,
                member_payload,
                min_area=float(args.min_area),
            )
            band_samples = extract_section_band_samples(
                ref_mesh,
                base_mesh,
                member_payload,
                min_area=float(args.min_area),
                max_center_offset=float(args.max_center_offset),
                min_area_ratio=float(args.min_area_ratio),
                max_area_ratio=float(args.max_area_ratio),
            )
            width_sample_count = len(band_samples)
            if silhouette_poly is None or not band_samples:
                member_stats.append(
                    {
                        "member_index": member_index,
                        "status": "skipped",
                        "width_sample_count": width_sample_count,
                        "silhouette_area": None if silhouette_poly is None else float(silhouette_poly.area),
                    }
                )
                print(f"[!] side-extrude skip member={member_index}: silhouette={silhouette_poly is not None} width_samples={width_sample_count}")
                continue

            band_solids = build_side_band_solids(
                silhouette_poly,
                band_samples,
                angle_deg=float(member_payload.get("angle", 0.0)),
                min_band_area=float(args.min_band_area),
                global_width_scale=float(args.global_width_scale),
                root_width_scale=float(args.root_width_scale),
                tip_width_scale=float(args.tip_width_scale),
            )
            full_solid = build_full_silhouette_solid(
                silhouette_poly,
                band_samples,
                angle_deg=float(member_payload.get("angle", 0.0)),
                global_width_scale=float(args.global_width_scale),
                root_width_scale=float(args.root_width_scale),
                tip_width_scale=float(args.tip_width_scale),
            )
            root_full_solid = None
            if str(args.base_mode) == "root_hybrid":
                sb = silhouette_poly.bounds
                clip_r1 = float(sb[0] + max(1.0, float(args.root_full_ratio)) * max(1e-6, sb[2] - sb[0]))
                root_full_solid = build_full_silhouette_solid(
                    silhouette_poly,
                    band_samples,
                    angle_deg=float(member_payload.get("angle", 0.0)),
                    global_width_scale=float(args.global_width_scale),
                    root_width_scale=float(args.root_width_scale),
                    tip_width_scale=float(args.tip_width_scale),
                    radial_clip=(float(sb[0]), float(clip_r1)),
                )
            solids: List[Any] = []
            if str(args.base_mode) == "band":
                solids = list(band_solids)
            elif str(args.base_mode) == "full":
                if full_solid is not None:
                    solids = [full_solid]
            elif str(args.base_mode) == "root_hybrid":
                if root_full_solid is not None:
                    solids.append(root_full_solid)
                solids.extend(band_solids)
            else:
                if full_solid is not None:
                    solids.append(full_solid)
                solids.extend(band_solids)
            valid_solids = section_diff.filter_valid_export_shapes(solids, f"member {member_index} side bands")
            if not valid_solids:
                member_stats.append(
                    {
                        "member_index": member_index,
                        "status": "no_valid_solids",
                        "width_sample_count": width_sample_count,
                        "silhouette_area": float(silhouette_poly.area),
                    }
                )
                print(f"[!] side-extrude skip member={member_index}: no valid solids")
                continue

            member_shape = fuse_member_solids(valid_solids)
            replaced_sections = 0
            if bool(args.refine_intersect) and callable(build_member_fn):
                patched_member_payload, replaced_sections = apply_section_replacements(
                    ref_mesh,
                    base_mesh,
                    member_payload,
                    min_area=float(args.min_area),
                    max_center_offset=float(args.max_center_offset),
                    min_area_ratio=float(args.min_area_ratio),
                    max_area_ratio=float(args.max_area_ratio),
                )
                member_shape = refine_member_shape_by_intersection(
                    member_shape,
                    patched_member_payload,
                    motif_payload,
                    build_member_fn,
                    body_valid_fn,
                )
            member_shapes = section_diff.filter_valid_export_shapes([member_shape], f"member {member_index} fused")
            if member_shapes:
                all_shapes.extend(member_shapes)
                appended_count = len(member_shapes)
            else:
                all_shapes.extend(valid_solids)
                appended_count = len(valid_solids)
            member_stats.append(
                {
                    "member_index": member_index,
                    "status": "built",
                    "width_sample_count": width_sample_count,
                    "band_solid_count": len(valid_solids),
                    "export_shape_count": int(appended_count),
                    "replaced_sections": int(replaced_sections),
                    "silhouette_area": float(silhouette_poly.area),
                    "silhouette_bounds": [float(v) for v in silhouette_poly.bounds],
                }
            )
            print(f"[*] side-extrude member={member_index}: bands={len(valid_solids)} width_samples={width_sample_count} export_shapes={appended_count}")

    export_input = all_shapes[0] if len(all_shapes) == 1 else cq.Compound.makeCompound(all_shapes)
    export_shape = section_diff.export_step_occ(export_input, output_step_path, {})
    cq.exporters.export(export_shape, str(output_stl_path), tolerance=0.8, angularTolerance=0.8)

    if meta_out_path is not None:
        meta_out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "features": str(features_path),
            "base_step": str(base_step_path),
            "reference_stl": str(reference_stl_path),
            "output_step": str(output_step_path),
            "output_stl": str(output_stl_path),
            "members": member_stats,
        }
        meta_out_path.write_text(json.dumps(single_spoke.sanitize_for_json(payload), ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[*] output step: {output_step_path}")
    print(f"[*] output stl: {output_stl_path}")


if __name__ == "__main__":
    main()
