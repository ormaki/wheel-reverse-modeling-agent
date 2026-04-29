from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import cadquery as cq
import numpy as np
import trimesh


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import stl_to_step_pipeline as pipeline


def align_mesh_to_feature_space(
    mesh: trimesh.Trimesh,
    features: Optional[Dict[str, Any]] = None,
) -> trimesh.Trimesh:
    aligned = mesh.copy()
    try:
        aligned.apply_translation(-aligned.centroid)
        aligned.apply_transform(aligned.principal_inertia_transform)
        extents = aligned.extents
        axis_idx = int(np.argmin(extents))
        if axis_idx != 2:
            mat = np.eye(4)
            if axis_idx == 0:
                theta = -np.pi / 2
                c, s = np.cos(theta), np.sin(theta)
                mat[:3, :3] = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
            elif axis_idx == 1:
                theta = np.pi / 2
                c, s = np.cos(theta), np.sin(theta)
                mat[:3, :3] = np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
            aligned.apply_transform(mat)
    except Exception as exc:
        print(f"[!] Pose alignment failed, keeping mesh as-is: {exc}")

    try:
        z_shift = float((features or {}).get("global_params", {}).get("rim_profile_z_shift", 0.0))
    except Exception:
        z_shift = 0.0
    if abs(z_shift) > 1e-6:
        aligned.vertices[:, 2] = np.asarray(aligned.vertices[:, 2], dtype=float) + z_shift
    return aligned


def load_trimesh(mesh_path: Path, features: Optional[Dict[str, Any]] = None) -> trimesh.Trimesh:
    loaded = trimesh.load(str(mesh_path))
    if isinstance(loaded, trimesh.Trimesh):
        return align_mesh_to_feature_space(loaded, features=features)
    if isinstance(loaded, trimesh.Scene):
        meshes = [
            geom
            for geom in loaded.geometry.values()
            if isinstance(geom, trimesh.Trimesh) and len(geom.vertices) > 0
        ]
        if meshes:
            return align_mesh_to_feature_space(trimesh.util.concatenate(meshes), features=features)
    raise ValueError(f"Unable to coerce mesh from: {mesh_path}")


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
        except Exception:
            val = None
        return [val] if hasattr(val, "wrapped") else []
    if hasattr(obj, "wrapped"):
        return [obj]
    if isinstance(obj, (list, tuple)):
        shapes: List[Any] = []
        for item in obj:
            shapes.extend(collect_export_shapes(item))
        return shapes
    return []


def export_step_occ(obj: Any, output_path: Path) -> None:
    shapes = []
    for idx, shape in enumerate(collect_export_shapes(obj)):
        try:
            if hasattr(shape, "isValid") and (not shape.isValid()):
                print(f"[!] export shape {idx} rejected: invalid")
                continue
        except Exception as exc:
            print(f"[!] export shape {idx} validation failed: {exc}")
            continue
        shapes.append(shape)
    if not shapes:
        raise ValueError("No exportable shapes were produced.")

    export_shape = shapes[0] if len(shapes) == 1 else cq.Compound.makeCompound(shapes)
    if hasattr(export_shape, "isValid") and (not export_shape.isValid()):
        raise ValueError("Export shape is invalid and was rejected before STEP write.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if pipeline.OCP_STEP_EXPORT_AVAILABLE:
        pipeline.Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
        writer = pipeline.STEPControl_Writer()
        writer.Transfer(export_shape.wrapped, pipeline.STEPControl_AsIs)
        status = writer.Write(str(output_path))
        if int(status) != int(pipeline.IFSelect_RetDone):
            raise RuntimeError(f"OCC STEP export failed with status {int(status)}")
    else:
        cq.exporters.export(export_shape, str(output_path))


def pick_default_member(spoke_motif_sections: Sequence[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    candidates: List[Tuple[int, int, int, Dict[str, Any], Dict[str, Any]]] = []
    for motif_payload in spoke_motif_sections or []:
        for member_payload in motif_payload.get("members", []) or []:
            candidates.append(
                (
                    int(member_payload.get("actual_z_profile_count", 0)),
                    int(len(member_payload.get("sections", []) or [])),
                    -int(member_payload.get("member_index", 0)),
                    motif_payload,
                    member_payload,
                )
            )
    if not candidates:
        raise ValueError("No member candidates found in spoke_motif_sections.")
    candidates.sort(reverse=True, key=lambda item: (item[0], item[1], item[2]))
    _, _, _, motif_payload, member_payload = candidates[0]
    return motif_payload, member_payload


def resolve_member_payload(
    features: Dict[str, Any],
    member_index: Optional[int],
    motif_index: Optional[int],
    slot_index: Optional[int],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    spoke_motif_sections = features.get("spoke_motif_sections") or []
    if not spoke_motif_sections:
        raise ValueError("Features JSON does not contain spoke_motif_sections.")

    if member_index is not None:
        for motif_payload in spoke_motif_sections:
            for member_payload in motif_payload.get("members", []) or []:
                if int(member_payload.get("member_index", -1)) == int(member_index):
                    return motif_payload, member_payload
        raise ValueError(f"Member index {member_index} was not found in spoke_motif_sections.")

    if motif_index is not None:
        for motif_payload in spoke_motif_sections:
            if int(motif_payload.get("motif_index", -1)) != int(motif_index):
                continue
            if slot_index is None:
                members = motif_payload.get("members", []) or []
                if not members:
                    break
                member_payload = max(
                    members,
                    key=lambda item: (
                        int(item.get("actual_z_profile_count", 0)),
                        int(len(item.get("sections", []) or [])),
                        -int(item.get("member_index", 0)),
                    ),
                )
                return motif_payload, member_payload
            for member_payload in motif_payload.get("members", []) or []:
                if int(member_payload.get("slot_index", -1)) == int(slot_index):
                    return motif_payload, member_payload
        raise ValueError(f"Motif/slot selection not found: motif={motif_index}, slot={slot_index}")

    return pick_default_member(spoke_motif_sections)


def compute_member_hints(
    member_payload: Dict[str, Any],
    root_points: Sequence[Sequence[float]],
) -> Dict[str, Optional[float]]:
    region_points = member_payload.get("region", []) or []
    sections = member_payload.get("sections", []) or []
    region_radii = [math.hypot(float(x), float(y)) for x, y in region_points[:-1]] if len(region_points) >= 4 else []
    if not region_radii:
        raise ValueError("Member region points are missing or invalid.")
    expected_inner_r = float(min(region_radii))
    expected_outer_r = float(max(region_radii))
    expected_span = float(max(1.0, expected_outer_r - expected_inner_r))

    projected_widths = []
    for section_payload in sections:
        projected_sample = pipeline.extract_projected_section_sample(section_payload)
        if projected_sample is None:
            continue
        try:
            projected_widths.append(float(projected_sample.get("width", 0.0)))
        except Exception:
            continue
    expected_width = float(np.median(np.asarray(projected_widths, dtype=float))) if projected_widths else None

    guide_inner_r = float(expected_inner_r)
    guide_outer_r = float(expected_outer_r)
    section_station_radii = []
    for section_payload in sections:
        try:
            section_station_radii.append(float(section_payload.get("station_r", 0.0)))
        except Exception:
            continue
    if section_station_radii:
        first_station_r = min(section_station_radii)
        last_station_r = max(section_station_radii)
        inner_extend = max(7.0, min(14.0, expected_span * 0.15 + 1.8))
        outer_extend = max(18.0, min(36.0, expected_span * 0.36 + 4.0))
        guide_inner_r = min(guide_inner_r, max(0.0, first_station_r - inner_extend))
        guide_outer_r = max(guide_outer_r, last_station_r + outer_extend)
    if root_points and len(root_points) >= 4:
        try:
            root_radii = [math.hypot(float(x), float(y)) for x, y in root_points[:-1]]
        except Exception:
            root_radii = []
        if root_radii:
            guide_inner_r = min(
                guide_inner_r,
                max(
                    0.0,
                    float(np.percentile(np.asarray(root_radii, dtype=float), 8.0))
                    - max(2.0, min(5.2, expected_span * 0.07 + 1.0)),
                ),
            )
    guide_outer_r = max(
        float(guide_outer_r),
        float(expected_outer_r) + max(18.0, min(34.0, expected_span * 0.34 + 3.8)),
    )
    return {
        "expected_inner_r": expected_inner_r,
        "expected_outer_r": expected_outer_r,
        "expected_span": expected_span,
        "expected_width": expected_width,
        "guide_inner_r": guide_inner_r,
        "guide_outer_r": guide_outer_r,
    }


def build_guided_submesh(
    source_mesh: trimesh.Trimesh,
    member_payload: Dict[str, Any],
    root_points: Sequence[Sequence[float]],
    profile_hints: Dict[str, Optional[float]],
) -> Tuple[Optional[trimesh.Trimesh], Dict[str, Any]]:
    region_points = member_payload.get("region", []) or []
    member_sections = member_payload.get("sections", []) or []
    member_tip_sections = member_payload.get("tip_sections", []) or []
    member_angle_deg = float(member_payload.get("angle", 0.0))

    guide_geom = pipeline.build_member_actual_slice_guide(
        region_points,
        member_sections=member_sections,
        root_points=root_points,
        tip_sections=member_tip_sections,
        buffer_pad=2.05,
        guide_inner_r=profile_hints.get("guide_inner_r"),
        guide_outer_r=profile_hints.get("guide_outer_r"),
        relaxed=True,
    )
    if guide_geom is None or guide_geom.is_empty:
        return None, {"guide_area": 0.0, "guide_width_hint": None}

    z_values = []
    for section_payload in member_sections:
        plane_origin = section_payload.get("plane_origin", []) or []
        pts_local = section_payload.get("points_local", []) or []
        if len(plane_origin) < 3 or len(pts_local) < 4:
            continue
        try:
            base_z = float(plane_origin[2])
            ys = [float(y_val) for _, y_val in pts_local[:-1] if len(pts_local) >= 5]
        except Exception:
            ys = []
        if ys:
            z_values.extend([base_z + min(ys), base_z + max(ys)])
    if not z_values:
        vertices = np.asarray(source_mesh.vertices, dtype=float)
        z_values = [float(np.min(vertices[:, 2])), float(np.max(vertices[:, 2]))]

    submesh = pipeline.extract_member_guided_submesh(
        source_mesh,
        guide_geom,
        min(z_values),
        max(z_values),
        radial_inner=profile_hints.get("guide_inner_r"),
        radial_outer=profile_hints.get("guide_outer_r"),
        member_angle_deg=member_angle_deg,
        region_points=region_points,
        root_points=root_points,
        expected_span=profile_hints.get("expected_span"),
        expected_width=profile_hints.get("expected_width"),
        guide_buffer=3.2,
        min_faces=28,
    )
    guide_meta = {
        "guide_area": float(getattr(guide_geom, "area", 0.0)),
        "guide_width_hint": None,
    }
    return submesh, guide_meta


def regenerate_actual_z_profiles(
    source_mesh: trimesh.Trimesh,
    member_payload: Dict[str, Any],
    root_points: Sequence[Sequence[float]],
    sample_count: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    profile_meta: Dict[str, Any] = {}
    profiles = pipeline.extract_member_actual_z_profile_stack(
        source_mesh,
        member_payload.get("region", []) or [],
        member_payload.get("sections", []) or [],
        member_payload.get("tip_sections", []) or [],
        float(member_payload.get("angle", 0.0)),
        root_points=root_points,
        sample_count=int(sample_count),
        meta_out=profile_meta,
    )
    return profiles, profile_meta


def get_cached_actual_z_profiles(member_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    cached_profiles: List[Dict[str, Any]] = []
    for profile in member_payload.get("actual_z_profiles", []) or []:
        if not isinstance(profile, dict):
            continue
        points = profile.get("points", []) or []
        if len(points) < 4:
            continue
        try:
            z_level = float(profile.get("z", 0.0))
        except Exception:
            continue
        cached_profiles.append(
            {
                "z": z_level,
                "points": points,
            }
        )
    return cached_profiles


def compute_root_profile_gap(
    member_payload: Dict[str, Any],
    root_points: Sequence[Sequence[float]],
    z_profiles: Sequence[Dict[str, Any]],
) -> Optional[float]:
    if len(root_points or []) < 4 or len(z_profiles or []) < 1:
        return None
    try:
        root_outer_r = max(
            math.hypot(float(x), float(y))
            for x, y in list(root_points)[:-1]
        )
    except Exception:
        return None
    try:
        first_profile = min(z_profiles, key=lambda item: float(item.get("z", 0.0)))
    except Exception:
        return None
    pts = first_profile.get("points", []) or []
    if len(pts) < 4:
        return None
    try:
        first_inner_r = min(math.hypot(float(x), float(y)) for x, y in pts[:-1])
    except Exception:
        return None
    return float(first_inner_r - root_outer_r)


def build_member_root_overlap_pad(
    member_payload: Dict[str, Any],
    root_points: Sequence[Sequence[float]],
    z_profiles: Sequence[Dict[str, Any]],
    bore_radius: float = 0.0,
    min_band_area: float = 4.0,
    radial_band_width: float = 18.0,
) -> Optional[Any]:
    if len(root_points or []) < 4:
        return None
    try:
        root_poly = pipeline.largest_polygon(
            pipeline.normalize_geom(pipeline.Polygon(root_points)),
            min_area=float(min_band_area),
        )
    except Exception:
        root_poly = None
    if root_poly is None or root_poly.is_empty:
        return None

    prepared_profiles = [profile for profile in (z_profiles or []) if isinstance(profile, dict)]
    if len(prepared_profiles) < 4:
        return None
    prepared_profiles = sorted(prepared_profiles, key=lambda profile: float(profile.get("z", 0.0)))
    seed_profiles = prepared_profiles[: min(8, len(prepared_profiles))]

    root_outer_candidates = []
    z_seed = []
    for profile in seed_profiles:
        try:
            z_seed.append(float(profile.get("z", 0.0)))
        except Exception:
            continue
        pts = profile.get("points", []) or []
        if len(pts) < 4:
            continue
        try:
            root_outer_candidates.append(min(math.hypot(float(x), float(y)) for x, y in pts[:-1]))
        except Exception:
            continue
    if not root_outer_candidates or not z_seed:
        return None

    root_outer_r = float(np.percentile(np.asarray(root_outer_candidates, dtype=float), 35.0)) + 1.8
    root_inner_r = max(float(bore_radius) + 0.8, root_outer_r - float(radial_band_width))
    if root_outer_r <= root_inner_r + 1.2:
        return None

    try:
        root_band_poly = pipeline.normalize_geom(
            root_poly.intersection(pipeline.circle_polygon(root_outer_r, 180)).difference(
                pipeline.circle_polygon(root_inner_r, 180)
            )
        )
        root_band_poly = pipeline.largest_polygon(root_band_poly, min_area=float(min_band_area))
    except Exception:
        root_band_poly = None

    if root_band_poly is None or root_band_poly.is_empty:
        try:
            root_band_poly = pipeline.largest_polygon(root_poly, min_area=float(min_band_area))
        except Exception:
            root_band_poly = None
    if root_band_poly is None or root_band_poly.is_empty:
        return None

    z_low = min(z_seed) - 1.6
    z_high = min(min(z_seed) + 3.2, max(z_seed) + 0.8)
    pad_height = max(1.4, z_high - z_low)
    candidate_polys = [root_band_poly]
    try:
        cleaned = pipeline.normalize_geom(root_band_poly.buffer(0))
        if cleaned is not None and not cleaned.is_empty:
            candidate_polys.append(cleaned)
    except Exception:
        pass
    try:
        hull = root_band_poly.convex_hull
        if hull is not None and not hull.is_empty:
            candidate_polys.append(hull)
    except Exception:
        pass

    member_index = member_payload.get("member_index")
    for candidate_index, candidate_poly in enumerate(candidate_polys):
        try:
            poly = pipeline.largest_polygon(candidate_poly, min_area=float(min_band_area))
        except Exception:
            poly = None
        if poly is None or poly.is_empty:
            continue
        pad_loop = [(round(float(x), 3), round(float(y), 3)) for x, y in list(poly.exterior.coords)]
        if len(pad_loop) < 4:
            continue
        try:
            pad_body = (
                cq.Workplane("XY")
                .workplane(offset=float(z_low))
                .polyline(pad_loop).close()
                .extrude(float(pad_height))
            )
            if candidate_index > 0:
                print(
                    f"[*] root overlap pad fallback for member {member_index}: candidate={candidate_index}"
                )
            return cq.Workplane("XY").newObject([pad_body.findSolid()])
        except Exception:
            continue

    print(f"[!] root overlap pad failed for member {member_index}: no valid pad candidate")
    return None


def member_local_to_world(
    coords: Sequence[Sequence[float]],
    member_angle_deg: float,
) -> List[List[float]]:
    theta = math.radians(float(member_angle_deg))
    cos_theta = math.cos(theta)
    sin_theta = math.sin(theta)
    world_coords: List[List[float]] = []
    for coord in coords:
        if len(coord) < 2:
            continue
        local_r = float(coord[0])
        local_t = float(coord[1])
        world_x = (cos_theta * local_r) - (sin_theta * local_t)
        world_y = (sin_theta * local_r) + (cos_theta * local_t)
        world_coords.append([round(world_x, 6), round(world_y, 6)])
    if world_coords and world_coords[0] != world_coords[-1]:
        world_coords.append(list(world_coords[0]))
    return world_coords


def build_root_anchor_profiles(
    z_profiles: Sequence[Dict[str, Any]],
    root_points: Sequence[Sequence[float]],
    member_angle_deg: float,
    gap_threshold: float = 3.0,
    anchor_count: int = 3,
    anchor_span: Optional[float] = None,
    target_count: int = 64,
    alpha_start: float = 0.10,
    alpha_end: float = 0.82,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    profile_meta: Dict[str, Any] = {
        "used": False,
        "anchor_count": 0,
        "gap_mm": None,
    }
    prepared_profiles = [
        profile for profile in (z_profiles or [])
        if isinstance(profile, dict) and len(profile.get("points", []) or []) >= 4
    ]
    if len(prepared_profiles) < 2 or len(root_points or []) < 4:
        return list(prepared_profiles), profile_meta

    root_gap = compute_root_profile_gap({}, root_points, prepared_profiles)
    profile_meta["gap_mm"] = None if root_gap is None else round(float(root_gap), 3)
    if root_gap is None or float(root_gap) < float(gap_threshold):
        return list(prepared_profiles), profile_meta

    sorted_profiles = sorted(prepared_profiles, key=lambda item: float(item.get("z", 0.0)))
    first_profile = sorted_profiles[0]
    second_profile = sorted_profiles[1]
    try:
        first_z = float(first_profile.get("z", 0.0))
        second_z = float(second_profile.get("z", first_z + 1.0))
    except Exception:
        return list(sorted_profiles), profile_meta

    root_local = pipeline.world_loop_to_member_local(root_points, member_angle_deg)
    first_local = pipeline.world_loop_to_member_local(first_profile.get("points", []) or [], member_angle_deg)
    if len(root_local) < 4 or len(first_local) < 4:
        return list(sorted_profiles), profile_meta

    root_sample = pipeline.resample_closed_loop_outer(root_local, target_count=int(target_count))
    first_sample = pipeline.resample_closed_loop_outer(first_local, target_count=int(target_count))
    if len(root_sample) < 8 or len(first_sample) < 8:
        return list(sorted_profiles), profile_meta

    root_sample = pipeline.align_resampled_loop_outer(
        first_sample,
        root_sample,
        allow_reverse=False,
    )

    local_delta = max(0.45, min(1.8, (second_z - first_z) * 0.65))
    if anchor_span is None:
        anchor_span = max(1.8, min(4.2, float(root_gap) * 0.12 + 1.6))
    anchor_span = max(float(local_delta) * float(anchor_count), float(anchor_span))
    max_anchor_count = max(1, int(anchor_count))
    anchor_z_values = np.linspace(float(first_z) - float(anchor_span), float(first_z) - float(local_delta), max_anchor_count)
    alpha_start = max(0.0, min(0.95, float(alpha_start)))
    alpha_end = max(alpha_start + 0.02, min(0.98, float(alpha_end)))
    blend_values = np.linspace(alpha_start, alpha_end, max_anchor_count)

    anchor_profiles: List[Dict[str, Any]] = []
    for z_level, alpha in zip(anchor_z_values.tolist(), blend_values.tolist()):
        blended_local = []
        for (rr, rt), (fr, ft) in zip(root_sample[:-1], first_sample[:-1]):
            blended_local.append(
                [
                    round((float(rr) * (1.0 - float(alpha))) + (float(fr) * float(alpha)), 6),
                    round((float(rt) * (1.0 - float(alpha))) + (float(ft) * float(alpha)), 6),
                ]
            )
        if blended_local and blended_local[0] != blended_local[-1]:
            blended_local.append(list(blended_local[0]))
        world_loop = member_local_to_world(blended_local, member_angle_deg)
        if len(world_loop) < 4:
            continue
        anchor_profiles.append(
            {
                "z": round(float(z_level), 6),
                "points": world_loop,
                "points_local": blended_local,
                "source": "root_anchor",
            }
        )

    if not anchor_profiles:
        return list(sorted_profiles), profile_meta

    profile_meta["used"] = True
    profile_meta["anchor_count"] = int(len(anchor_profiles))
    return anchor_profiles + list(sorted_profiles), profile_meta


def normalize_profiles_for_loft(
    profiles: Sequence[Dict[str, Any]],
    member_angle_deg: float,
    target_count: int,
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    previous_loop = None
    previous_z = None
    for profile in sorted(profiles, key=lambda item: float(item.get("z", 0.0))):
        try:
            z_level = float(profile.get("z", 0.0))
        except Exception:
            continue
        if previous_z is not None and abs(z_level - previous_z) < 0.08:
            continue
        local_loop = pipeline.world_loop_to_member_local(profile.get("points", []) or [], member_angle_deg)
        if len(local_loop) < 4:
            continue
        sampled_loop = pipeline.resample_closed_loop_outer(local_loop, target_count=int(target_count))
        if len(sampled_loop) < 8:
            continue
        if previous_loop is not None:
            sampled_loop = pipeline.align_resampled_loop_outer(
                previous_loop,
                sampled_loop,
                allow_reverse=False,
            )
        world_loop = member_local_to_world(sampled_loop, member_angle_deg)
        if len(world_loop) < 4:
            continue
        normalized.append(
            {
                "z": round(z_level, 6),
                "points": world_loop,
                "points_local": [[round(float(x), 6), round(float(y), 6)] for x, y in sampled_loop],
            }
        )
        previous_loop = sampled_loop
        previous_z = z_level
    return normalized


def thin_profiles_for_loft(
    profiles: Sequence[Dict[str, Any]],
    max_profiles: int,
) -> List[Dict[str, Any]]:
    if len(profiles) <= int(max_profiles):
        return list(profiles)
    raw_indices = np.linspace(0, len(profiles) - 1, int(max_profiles))
    indices = sorted({int(round(float(idx))) for idx in raw_indices})
    if len(indices) < 3:
        indices = [0, len(profiles) // 2, len(profiles) - 1]
    return [profiles[idx] for idx in indices]


def build_world_z_profile_wire(profile_payload: Dict[str, Any]) -> Optional[Any]:
    pts = profile_payload.get("points", []) or []
    if len(pts) < 4:
        return None
    try:
        z_level = float(profile_payload.get("z", 0.0))
    except Exception:
        return None
    loop = [(float(x), float(y)) for x, y in pts]
    if loop[0] == loop[-1]:
        loop = loop[:-1]
    if len(loop) < 3:
        return None
    try:
        return (
            cq.Workplane("XY")
            .workplane(offset=z_level)
            .polyline(loop).close()
            .wires().val()
        )
    except Exception as exc:
        print(f"[!] Z-profile wire build failed: {exc}")
        return None


def profile_stack_bbox(profiles: Sequence[Dict[str, Any]]) -> Optional[Tuple[float, float, float, float, float, float]]:
    xs: List[float] = []
    ys: List[float] = []
    zs: List[float] = []
    for profile in profiles:
        try:
            z_level = float(profile.get("z", 0.0))
        except Exception:
            continue
        for point in profile.get("points", []) or []:
            if len(point) < 2:
                continue
            try:
                xs.append(float(point[0]))
                ys.append(float(point[1]))
                zs.append(z_level)
            except Exception:
                continue
    if not xs or not ys or not zs:
        return None
    return (
        float(min(xs)),
        float(max(xs)),
        float(min(ys)),
        float(max(ys)),
        float(min(zs)),
        float(max(zs)),
    )


def body_bbox(body: Any) -> Optional[Tuple[float, float, float, float, float, float]]:
    shapes = collect_export_shapes(body)
    if not shapes:
        return None
    try:
        shape = shapes[0] if len(shapes) == 1 else cq.Compound.makeCompound(shapes)
        bb = shape.BoundingBox()
        return (
            float(bb.xmin),
            float(bb.xmax),
            float(bb.ymin),
            float(bb.ymax),
            float(bb.zmin),
            float(bb.zmax),
        )
    except Exception:
        return None


def loft_body_is_plausible(
    body: Any,
    profiles: Sequence[Dict[str, Any]],
) -> bool:
    expected = profile_stack_bbox(profiles)
    actual = body_bbox(body)
    if expected is None or actual is None:
        return False
    ex0, ex1, ey0, ey1, ez0, ez1 = expected
    ax0, ax1, ay0, ay1, az0, az1 = actual
    expected_x = max(1.0, ex1 - ex0)
    expected_y = max(1.0, ey1 - ey0)
    expected_z = max(1.0, ez1 - ez0)
    actual_x = max(0.0, ax1 - ax0)
    actual_y = max(0.0, ay1 - ay0)
    actual_z = max(0.0, az1 - az0)
    if actual_x > max(expected_x + 28.0, expected_x * 1.7):
        return False
    if actual_y > max(expected_y + 28.0, expected_y * 1.7):
        return False
    if actual_z > max(expected_z + 14.0, expected_z * 1.45):
        return False
    if ax0 < ex0 - 24.0 or ax1 > ex1 + 24.0:
        return False
    if ay0 < ey0 - 24.0 or ay1 > ey1 + 24.0:
        return False
    if az0 < ez0 - 8.0 or az1 > ez1 + 8.0:
        return False
    return True


def loft_from_profiles(
    profiles: Sequence[Dict[str, Any]],
    prefer_ruled: bool = False,
) -> Tuple[cq.Workplane, str]:
    wires = []
    for profile in profiles:
        wire = build_world_z_profile_wire(profile)
        if wire is not None:
            wires.append(wire)
    if len(wires) < 3:
        raise ValueError(f"Not enough valid loft wires: {len(wires)}")

    primary_modes = [True, False] if prefer_ruled else [False, True]
    for ruled in primary_modes:
        try:
            solid = cq.Solid.makeLoft(wires, ruled=ruled)
            body = cq.Workplane("XY").newObject([solid])
            if loft_body_is_plausible(body, profiles):
                return body, ("multi-wire-ruled" if ruled else "multi-wire-smooth")
            print(f"[!] multi-wire {'ruled' if ruled else 'smooth'} loft rejected by bbox plausibility gate")
        except Exception as exc:
            print(f"[!] multi-wire {'ruled' if ruled else 'smooth'} loft failed: {exc}")

    segment_shapes = []
    for wire_a, wire_b in zip(wires[:-1], wires[1:]):
        try:
            seg_solid = cq.Solid.makeLoft([wire_a, wire_b], ruled=False)
        except Exception:
            seg_solid = cq.Solid.makeLoft([wire_a, wire_b], ruled=True)
        segment_shapes.append(seg_solid)
    if len(segment_shapes) < 2:
        body = cq.Workplane("XY").newObject(segment_shapes)
        if loft_body_is_plausible(body, profiles):
            return body, "pairwise"
        raise ValueError("Pairwise loft fallback is not plausible.")
    compound = cq.Compound.makeCompound(segment_shapes)
    body = cq.Workplane("XY").newObject([compound])
    if loft_body_is_plausible(body, profiles):
        return body, "pairwise-compound"
    raise ValueError("Pairwise compound loft fallback is not plausible.")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitize_for_json(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def sanitize_for_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): sanitize_for_json(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_for_json(item) for item in value]
    if hasattr(value, "geom_type"):
        if hasattr(value, "wkt"):
            return value.wkt
        return str(value)
    return str(value)


def default_stem(label: str) -> str:
    return f"{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract one spoke-local mesh window, regenerate XY@Z profiles, and loft a single-spoke CAD preview."
    )
    parser.add_argument("--stl", default=str(ROOT / "input" / "wheel.stl"), help="Source STL path")
    parser.add_argument("--features", required=True, help="Features JSON path")
    parser.add_argument("--output-dir", default=str(ROOT / "output"), help="Output directory")
    parser.add_argument("--label", default="single_spoke_mesh_to_cad", help="Artifact label")
    parser.add_argument("--member-index", type=int, help="Global member index to target")
    parser.add_argument("--motif-index", type=int, help="Motif index to target")
    parser.add_argument("--slot-index", type=int, help="Member slot inside the motif")
    parser.add_argument("--sample-count", type=int, default=9, help="Profile stack sample count hint")
    parser.add_argument("--profile-point-count", type=int, default=64, help="Per-profile resample point count")
    parser.add_argument("--max-loft-profiles", type=int, default=8, help="Max profiles kept for lofting")
    parser.add_argument("--prefer-ruled", action="store_true", help="Prefer ruled lofts over smooth lofts for boolean-stable members")
    args = parser.parse_args()

    stl_path = Path(args.stl).resolve()
    features_path = Path(args.features).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not stl_path.exists():
        raise FileNotFoundError(f"STL not found: {stl_path}")
    if not features_path.exists():
        raise FileNotFoundError(f"Features JSON not found: {features_path}")

    with features_path.open("r", encoding="utf-8") as handle:
        features = json.load(handle)

    source_mesh = load_trimesh(stl_path, features=features)
    motif_payload, member_payload = resolve_member_payload(
        features,
        member_index=args.member_index,
        motif_index=args.motif_index,
        slot_index=args.slot_index,
    )
    member_index = int(member_payload.get("member_index", -1))
    root_regions = features.get("spoke_root_regions") or []
    root_entry = root_regions[member_index] if 0 <= member_index < len(root_regions) else {}
    root_points = root_entry.get("points", []) if isinstance(root_entry, dict) else root_entry

    stem = default_stem(args.label)
    submesh_stl_path = output_dir / f"{stem}.submesh.stl"
    raw_profiles_path = output_dir / f"{stem}.profiles.raw.json"
    loft_profiles_path = output_dir / f"{stem}.profiles.loft.json"
    step_path = output_dir / f"{stem}.step"
    stl_out_path = output_dir / f"{stem}.stl"
    meta_path = output_dir / f"{stem}.meta.json"

    profile_hints = compute_member_hints(member_payload, root_points)
    submesh, guide_meta = build_guided_submesh(source_mesh, member_payload, root_points, profile_hints)
    if submesh is not None:
        submesh.export(str(submesh_stl_path))

    raw_profiles, profile_meta = regenerate_actual_z_profiles(
        source_mesh,
        member_payload,
        root_points=root_points,
        sample_count=int(args.sample_count),
    )
    if len(raw_profiles) < 3:
        cached_profiles = get_cached_actual_z_profiles(member_payload)
        if len(cached_profiles) >= 3:
            raw_profiles = cached_profiles
            profile_meta = {
                "prefer_local_section": bool(member_payload.get("actual_z_prefer_local_section")),
                "stack_mode": str(member_payload.get("actual_z_stack_mode") or "cached"),
                "profile_count": int(len(cached_profiles)),
                "source_label": "cached_features_fallback",
            }
    if len(raw_profiles) < 3:
        raise RuntimeError(f"Regenerated profile stack is too small: {len(raw_profiles)}")
    write_json(
        raw_profiles_path,
        {
            "member_index": member_index,
            "motif_index": int(motif_payload.get("motif_index", -1)),
            "profile_meta": profile_meta,
            "profiles": raw_profiles,
        },
    )

    normalized_profiles = normalize_profiles_for_loft(
        raw_profiles,
        member_angle_deg=float(member_payload.get("angle", 0.0)),
        target_count=int(args.profile_point_count),
    )
    loft_profiles = thin_profiles_for_loft(normalized_profiles, max_profiles=int(args.max_loft_profiles))
    if len(loft_profiles) < 3:
        raise RuntimeError(f"Loft profile stack is too small after normalization/thinning: {len(loft_profiles)}")
    write_json(
        loft_profiles_path,
        {
            "member_index": member_index,
            "motif_index": int(motif_payload.get("motif_index", -1)),
            "normalized_profile_count": len(normalized_profiles),
            "loft_profile_count": len(loft_profiles),
            "profiles": loft_profiles,
        },
    )

    loft_body, loft_mode = loft_from_profiles(loft_profiles, prefer_ruled=bool(args.prefer_ruled))
    export_step_occ(loft_body, step_path)
    cq.exporters.export(
        loft_body,
        str(stl_out_path),
        tolerance=0.6,
        angularTolerance=0.6,
    )

    meta = {
        "source_stl": str(stl_path),
        "features_path": str(features_path),
        "motif_index": int(motif_payload.get("motif_index", -1)),
        "member_index": member_index,
        "slot_index": int(member_payload.get("slot_index", -1)),
        "member_angle_deg": float(member_payload.get("angle", 0.0)),
        "cached_actual_z_profile_count": int(member_payload.get("actual_z_profile_count", 0)),
        "regenerated_profile_meta": profile_meta,
        "normalized_profile_count": int(len(normalized_profiles)),
        "loft_profile_count": int(len(loft_profiles)),
        "loft_mode": loft_mode,
        "submesh_faces": int(len(submesh.faces)) if submesh is not None else 0,
        "submesh_vertices": int(len(submesh.vertices)) if submesh is not None else 0,
        "submesh_stl": str(submesh_stl_path) if submesh is not None else None,
        "raw_profiles_path": str(raw_profiles_path),
        "loft_profiles_path": str(loft_profiles_path),
        "step_path": str(step_path),
        "stl_path": str(stl_out_path),
        "profile_hints": profile_hints,
        "guide_meta": guide_meta,
    }
    write_json(meta_path, meta)

    print(f"[*] Motif={meta['motif_index']} member={member_index} slot={meta['slot_index']} angle={meta['member_angle_deg']:.3f}")
    print(f"[*] Cached actual_z profiles: {meta['cached_actual_z_profile_count']}")
    print(f"[*] Actual-z source: {profile_meta.get('source_label')}")
    print(f"[*] Regenerated profiles: {profile_meta.get('profile_count', len(raw_profiles))} mode={profile_meta.get('stack_mode')}")
    print(f"[*] Normalized profiles: {len(normalized_profiles)}")
    print(f"[*] Loft profiles: {len(loft_profiles)} mode={loft_mode}")
    if submesh is not None:
        print(f"[*] Guided submesh exported: {submesh_stl_path} faces={len(submesh.faces)}")
    print(f"[*] STEP: {step_path}")
    print(f"[*] STL: {stl_out_path}")
    print(f"[*] Meta: {meta_path}")


if __name__ == "__main__":
    main()
