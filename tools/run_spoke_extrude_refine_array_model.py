from __future__ import annotations

"""Legacy execution engine for the pinned current wheel route.

Use tools/build_current_wheel_model.py as the active entrypoint. This file still
contains historical implementation support, but rejected branches must not be
treated as available modeling strategies.
"""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cadquery as cq
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.run_section_diff_spoke_rebuild as section_diff
import tools.run_single_spoke_mesh_to_cad as single_spoke
import tools.run_spoke_side_extrude_model as side_model
import pipeline_modeling_codegen as production_codegen


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def collect_members(features: Dict[str, Any]) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    rows: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for motif_payload in features.get("spoke_motif_sections") or []:
        for member_payload in motif_payload.get("members", []) or []:
            rows.append((motif_payload, member_payload))
    return rows


def pick_template_member(
    features: Dict[str, Any],
    requested_member_index: Optional[int],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    rows = collect_members(features)
    if not rows:
        raise RuntimeError("no spoke members found in features")
    if requested_member_index is not None:
        for motif_payload, member_payload in rows:
            if int(member_payload.get("member_index", -1)) == int(requested_member_index):
                return motif_payload, member_payload
        raise ValueError(f"template member {requested_member_index} not found")
    rows.sort(
        key=lambda item: (
            len(item[1].get("sections") or []),
            float(max((sec.get("station_r", 0.0) for sec in item[1].get("sections") or []), default=0.0)),
        ),
        reverse=True,
    )
    return rows[0]


def member_section_station_span(member_payload: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    station_values: List[float] = []
    for section_key in ("sections", "tip_sections"):
        for section in member_payload.get(section_key) or []:
            if not isinstance(section, dict):
                continue
            station_r = float(section.get("station_r", 0.0) or 0.0)
            if station_r > 0.0:
                station_values.append(station_r)
    if not station_values:
        return None, None
    return float(min(station_values)), float(max(station_values))


def rotate_shape_z(shape: Any, delta_deg: float) -> Any:
    return shape.rotate((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), float(delta_deg))


def choose_base_width(
    samples: Sequence[Tuple[float, float, float, float]],
    mode: str,
    scale: float,
) -> float:
    widths = np.asarray([float(item[1]) for item in samples], dtype=float)
    rs = np.asarray([float(item[0]) for item in samples], dtype=float)
    if len(widths) == 0:
        return max(1.0, float(scale))
    r0 = float(np.min(rs))
    r1 = float(np.max(rs))
    if mode == "tip_max":
        gate = float(r0 + 0.72 * max(1e-6, r1 - r0))
        tip_widths = widths[rs >= gate]
        chosen = float(np.max(tip_widths)) if len(tip_widths) > 0 else float(np.max(widths))
    elif mode == "p95":
        chosen = float(np.percentile(widths, 95.0))
    elif mode == "median":
        chosen = float(np.median(widths))
    else:
        chosen = float(np.max(widths))
    return max(0.8, chosen * float(scale))


def build_extrude_from_silhouette(
    silhouette_poly: Any,
    angle_deg: float,
    total_width: float,
    face_mode: str,
    root_pad_mm: float = 0.0,
    tip_pad_mm: float = 0.0,
    profile_mode: str = "silhouette",
    rect_z_margin_mm: float = 0.0,
) -> Any:
    pts = [(float(x), float(y)) for x, y in list(silhouette_poly.exterior.coords)]
    if len(pts) < 4:
        raise RuntimeError("silhouette polygon too small")
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        raise RuntimeError("silhouette polygon degenerated")
    xs = [float(x) for x, _y in pts]
    x_min = float(min(xs))
    x_max = float(max(xs))
    ys = [float(y) for _x, y in pts]
    y_min = float(min(ys)) - max(0.0, float(rect_z_margin_mm))
    y_max = float(max(ys)) + max(0.0, float(rect_z_margin_mm))
    x_span = max(1e-6, x_max - x_min)
    edge_ratio = 0.18
    root_edge = float(x_min + (edge_ratio * x_span))
    tip_edge = float(x_max - (edge_ratio * x_span))
    if str(profile_mode) == "rectangle":
        stretched_pts = [
            (float(x_min - max(0.0, float(root_pad_mm))), float(y_min)),
            (float(x_max + max(0.0, float(tip_pad_mm))), float(y_min)),
            (float(x_max + max(0.0, float(tip_pad_mm))), float(y_max)),
            (float(x_min - max(0.0, float(root_pad_mm))), float(y_max)),
        ]
    else:
        stretched_pts = []
        for x, y in pts:
            local_x = float(x)
            if float(root_pad_mm) > 1e-6 and local_x <= root_edge:
                gain = max(0.0, min(1.0, (root_edge - local_x) / max(1e-6, root_edge - x_min)))
                local_x -= float(root_pad_mm) * gain
            if float(tip_pad_mm) > 1e-6 and local_x >= tip_edge:
                gain = max(0.0, min(1.0, (local_x - tip_edge) / max(1e-6, x_max - tip_edge)))
                local_x += float(tip_pad_mm) * gain
            stretched_pts.append((local_x, float(y)))
    angle_rad = math.radians(float(angle_deg))
    radial_dir = (math.cos(angle_rad), math.sin(angle_rad), 0.0)
    tangent_dir = (-math.sin(angle_rad), math.cos(angle_rad), 0.0)
    if str(face_mode) == "negative_z":
        plane_normal = tuple(float(v) for v in tangent_dir)
    else:
        plane_normal = tuple(float(-v) for v in tangent_dir)
    plane = cq.Plane(origin=(0.0, 0.0, 0.0), xDir=radial_dir, normal=plane_normal)
    return cq.Workplane(plane).polyline(stretched_pts).close().extrude(0.5 * float(total_width), both=True).val()


def extend_planform_profile_edges(
    profile: Dict[str, np.ndarray],
    *,
    root_pad_mm: float,
    tip_pad_mm: float,
    root_expand_mm: float = 0.0,
    tip_expand_mm: float = 0.0,
    steps: int = 1,
) -> Dict[str, np.ndarray]:
    xs = np.asarray(profile.get("x"), dtype=float)
    lower = np.asarray(profile.get("lower"), dtype=float)
    upper = np.asarray(profile.get("upper"), dtype=float)
    if len(xs) < 2 or len(lower) != len(xs) or len(upper) != len(xs):
        return profile
    out_x = xs.copy()
    out_lower = lower.copy()
    out_upper = upper.copy()
    step_count = max(1, int(steps))
    if float(root_pad_mm) > 1e-6:
        root_x: List[float] = []
        root_lower: List[float] = []
        root_upper: List[float] = []
        for idx in range(step_count, 0, -1):
            t = float(idx) / float(step_count)
            expand = max(0.0, float(root_expand_mm)) * t
            root_x.append(float(xs[0] - (float(root_pad_mm) * t)))
            root_lower.append(float(lower[0] - (0.5 * expand)))
            root_upper.append(float(upper[0] + (0.5 * expand)))
        out_x = np.concatenate((np.asarray(root_x, dtype=float), out_x))
        out_lower = np.concatenate((np.asarray(root_lower, dtype=float), out_lower))
        out_upper = np.concatenate((np.asarray(root_upper, dtype=float), out_upper))
    if float(tip_pad_mm) > 1e-6:
        tip_x: List[float] = []
        tip_lower: List[float] = []
        tip_upper: List[float] = []
        for idx in range(1, step_count + 1):
            t = float(idx) / float(step_count)
            expand = max(0.0, float(tip_expand_mm)) * t
            tip_x.append(float(xs[-1] + (float(tip_pad_mm) * t)))
            tip_lower.append(float(lower[-1] - (0.5 * expand)))
            tip_upper.append(float(upper[-1] + (0.5 * expand)))
        out_x = np.concatenate((out_x, np.asarray(tip_x, dtype=float)))
        out_lower = np.concatenate((out_lower, np.asarray(tip_lower, dtype=float)))
        out_upper = np.concatenate((out_upper, np.asarray(tip_upper, dtype=float)))
    extended = dict(profile)
    extended["x"] = out_x
    extended["lower"] = out_lower
    extended["upper"] = out_upper
    extended["span_x0"] = float(np.min(out_x))
    extended["span_x1"] = float(np.max(out_x))
    radial = profile.get("radial")
    tangent = profile.get("tangent")
    if radial is not None and tangent is not None:
        radial_arr = np.asarray(radial, dtype=float)
        tangent_arr = np.asarray(tangent, dtype=float)
        upper_xy = (out_x[:, None] * radial_arr[None, :]) + (out_upper[:, None] * tangent_arr[None, :])
        lower_xy = (out_x[:, None] * radial_arr[None, :]) + (out_lower[:, None] * tangent_arr[None, :])
        profile_radial = np.concatenate((np.linalg.norm(upper_xy, axis=1), np.linalg.norm(lower_xy, axis=1)))
        extended["profile_radial_r0"] = float(np.min(profile_radial))
        extended["profile_radial_r1"] = float(np.max(profile_radial))
    return extended


def build_radial_clip_solid(
    z0: float,
    z1: float,
    outer_r: float,
    inner_r: float = 0.0,
) -> Any:
    height = max(1.0, float(z1) - float(z0))
    wp = cq.Workplane("XY").workplane(offset=float(z0)).circle(float(outer_r))
    if float(inner_r) > 0.0:
        wp = wp.circle(float(inner_r))
    return wp.extrude(float(height)).val()


def build_radial_band_clip_solid(
    z0: float,
    z1: float,
    inner_r: float,
    outer_r: float,
) -> Any:
    if float(outer_r) <= float(inner_r) + 1e-6:
        raise ValueError("invalid radial band")
    return build_radial_clip_solid(z0=z0, z1=z1, outer_r=float(outer_r), inner_r=max(0.0, float(inner_r)))


def apply_revolved_boundary_cut(
    shape: Any,
    *,
    features: Dict[str, Any],
    z0: float,
    z1: float,
    inner_offset_mm: float = 0.0,
    outer_offset_mm: float = 0.0,
) -> Tuple[Any, Dict[str, Any]]:
    params = features.get("global_params") or {}
    try:
        inner_r = float(params.get("bore_radius")) + float(inner_offset_mm)
        outer_r = float(params.get("rim_max_radius")) + float(outer_offset_mm)
    except Exception:
        return shape, {"status": "missing_global_boundary"}
    inner_r = max(0.0, float(inner_r))
    outer_r = float(outer_r)
    if outer_r <= inner_r + 1.0:
        return shape, {"status": "invalid_boundary", "inner_r": inner_r, "outer_r": outer_r}
    try:
        annulus = build_radial_band_clip_solid(z0=z0, z1=z1, inner_r=inner_r, outer_r=outer_r)
        clipped = valid_single_shape(shape.intersect(annulus), "revolved boundary cut")
    except Exception as exc:
        return shape, {"status": "failed", "error": str(exc), "inner_r": inner_r, "outer_r": outer_r}
    return clipped, {"status": "applied", "inner_r": inner_r, "outer_r": outer_r}


def apply_revolved_inner_boundary_cut(
    shape: Any,
    *,
    features: Dict[str, Any],
    z0: float,
    z1: float,
    inner_offset_mm: float = 0.0,
) -> Tuple[Any, Dict[str, Any]]:
    params = features.get("global_params") or {}
    try:
        inner_r = float(params.get("bore_radius")) + float(inner_offset_mm)
    except Exception:
        return shape, {"status": "missing_bore_radius"}
    inner_r = max(0.0, float(inner_r))
    if inner_r <= 0.0:
        return shape, {"status": "invalid_inner_boundary", "inner_r": inner_r}
    try:
        cutter = build_radial_clip_solid(z0=z0, z1=z1, outer_r=inner_r)
        clipped = valid_single_shape(shape.cut(cutter), "revolved inner boundary cut")
    except Exception as exc:
        return shape, {"status": "failed", "error": str(exc), "inner_r": inner_r}
    return clipped, {"status": "applied", "inner_r": inner_r}


def rim_outer_radius_at_z(features: Dict[str, Any], z: float) -> Optional[float]:
    rows = []
    for item in (features.get("rim_profile") or {}).get("points") or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        try:
            rows.append((float(item[1]), float(item[0])))
        except Exception:
            continue
    if len(rows) < 2:
        return None
    rows.sort(key=lambda row: row[0])
    zs = np.asarray([row[0] for row in rows], dtype=float)
    rs = np.asarray([row[1] for row in rows], dtype=float)
    return float(np.interp(float(z), zs, rs, left=float(rs[0]), right=float(rs[-1])))


def build_rim_outer_curve_keep_solid(
    *,
    features: Dict[str, Any],
    z0: float,
    z1: float,
    inner_r: float,
    radial_offset_mm: float,
    samples: int,
) -> Tuple[Optional[Any], Dict[str, Any]]:
    rim_rows: List[Tuple[float, float]] = []
    for item in (features.get("rim_profile") or {}).get("points") or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        try:
            r = float(item[0]) + float(radial_offset_mm)
            z = float(item[1])
        except Exception:
            continue
        if z < float(z0) - 1e-6 or z > float(z1) + 1e-6:
            continue
        rim_rows.append((z, max(float(inner_r) + 1.0, r)))
    rim_rows.sort(key=lambda row: row[0])
    if not rim_rows or rim_rows[0][0] > float(z0) + 1e-6:
        r0 = rim_outer_radius_at_z(features, float(z0))
        if r0 is not None:
            rim_rows.insert(0, (float(z0), max(float(inner_r) + 1.0, float(r0) + float(radial_offset_mm))))
    if not rim_rows or rim_rows[-1][0] < float(z1) - 1e-6:
        r1 = rim_outer_radius_at_z(features, float(z1))
        if r1 is not None:
            rim_rows.append((float(z1), max(float(inner_r) + 1.0, float(r1) + float(radial_offset_mm))))
    if len(rim_rows) < 2:
        return None, {"status": "missing_rim_profile"}

    max_samples = max(4, int(samples))
    if len(rim_rows) > max_samples:
        idxs = np.linspace(0, len(rim_rows) - 1, max_samples).round().astype(int)
        rim_rows = [rim_rows[int(idx)] for idx in np.unique(idxs)]

    wires: List[Any] = []
    try:
        for z, r in rim_rows:
            wire = cq.Workplane("XY").workplane(offset=float(z)).circle(float(r)).wires().val()
            wires.append(wire)
        outer = cq.Solid.makeLoft(wires, ruled=False)
        outer = valid_single_shape(outer, "rim outer curve keep")
        if float(inner_r) > 0.0:
            inner_cut = build_radial_clip_solid(z0=float(z0) - 1.0, z1=float(z1) + 1.0, outer_r=float(inner_r))
            outer = valid_single_shape(outer.cut(inner_cut), "rim outer curve annulus")
    except Exception as exc:
        return None, {"status": "failed", "error": str(exc), "sample_count": int(len(rim_rows))}
    return outer, {
        "status": "built",
        "sample_count": int(len(rim_rows)),
        "z0": float(rim_rows[0][0]),
        "z1": float(rim_rows[-1][0]),
        "min_outer_r": float(min(row[1] for row in rim_rows)),
        "max_outer_r": float(max(row[1] for row in rim_rows)),
    }


def apply_revolved_rim_curve_boundary_cut(
    shape: Any,
    *,
    features: Dict[str, Any],
    z0: float,
    z1: float,
    inner_offset_mm: float = 0.0,
    outer_offset_mm: float = 0.0,
    samples: int = 32,
) -> Tuple[Any, Dict[str, Any]]:
    params = features.get("global_params") or {}
    try:
        inner_r = float(params.get("bore_radius")) + float(inner_offset_mm)
    except Exception:
        return shape, {"status": "missing_bore_radius"}
    keep, meta = build_rim_outer_curve_keep_solid(
        features=features,
        z0=float(z0),
        z1=float(z1),
        inner_r=max(0.0, float(inner_r)),
        radial_offset_mm=float(outer_offset_mm),
        samples=int(samples),
    )
    if keep is None:
        return shape, meta
    try:
        clipped = valid_single_shape(shape.intersect(keep), "rim curve boundary cut")
    except Exception as exc:
        meta = dict(meta)
        meta.update({"status": "failed_intersect", "error": str(exc)})
        return shape, meta
    meta = dict(meta)
    meta.update({"status": "applied", "inner_r": max(0.0, float(inner_r)), "outer_offset_mm": float(outer_offset_mm)})
    return clipped, meta


def build_post_rim_curve_outer_boundary_keep(
    *,
    features: Dict[str, Any],
    z_margin_mm: float,
    outer_offset_mm: float,
    samples: int,
) -> Tuple[Optional[Any], Dict[str, Any]]:
    z_values: List[float] = []
    for item in (features.get("rim_profile") or {}).get("points") or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        try:
            z_values.append(float(item[1]))
        except Exception:
            continue
    if not z_values:
        return None, {"status": "missing_rim_profile_z"}
    z_margin = max(0.0, float(z_margin_mm))
    keep, meta = build_rim_outer_curve_keep_solid(
        features=features,
        z0=float(min(z_values)) - z_margin,
        z1=float(max(z_values)) + z_margin,
        inner_r=0.0,
        radial_offset_mm=float(outer_offset_mm),
        samples=int(samples),
    )
    if keep is None:
        return None, meta
    meta = dict(meta)
    meta.update(
        {
            "status": "built",
            "outer_offset_mm": float(outer_offset_mm),
            "z_margin_mm": float(z_margin),
            "member_cut_count": 0,
            "member_failures": [],
        }
    )
    return keep, meta


def build_pcd_hole_cutter(
    features: Dict[str, Any],
    *,
    z0: float,
    z1: float,
    radius_scale: float = 1.0,
    extra_depth_mm: float = 8.0,
) -> Tuple[Optional[Any], Dict[str, Any]]:
    raise RuntimeError("archived dead path: use --post-use-production-hub-cuts instead")
    params = features.get("global_params") or {}
    try:
        pcd_radius = float(params.get("pcd_radius"))
        hole_radius = float(params.get("hole_radius")) * float(radius_scale)
        hole_count = int(params.get("hole_count"))
        phase_angle = float(params.get("pcd_phase_angle", 0.0) or 0.0)
    except Exception:
        return None, {"status": "missing_pcd_params"}
    if pcd_radius <= 0.0 or hole_radius <= 0.0 or hole_count <= 0:
        return None, {"status": "invalid_pcd_params", "pcd_radius": pcd_radius, "hole_radius": hole_radius, "hole_count": hole_count}
    z_start = float(z0) - float(extra_depth_mm)
    height = max(1.0, float(z1) - float(z0) + (2.0 * float(extra_depth_mm)))
    points = []
    for idx in range(hole_count):
        angle = math.radians(phase_angle + ((360.0 / float(hole_count)) * idx))
        points.append((math.cos(angle) * pcd_radius, math.sin(angle) * pcd_radius))
    try:
        cutter = cq.Workplane("XY").workplane(offset=z_start).pushPoints(points).circle(hole_radius).extrude(height).val()
        cutter = valid_single_shape(cutter, "pcd hole cutter")
    except Exception as exc:
        return None, {"status": "failed", "error": str(exc)}
    return cutter, {
        "status": "built",
        "pcd_radius": float(pcd_radius),
        "hole_radius": float(hole_radius),
        "hole_count": int(hole_count),
        "phase_angle_deg": float(phase_angle),
    }


def build_pcd_counterbore_cutter(
    features: Dict[str, Any],
    *,
    z0: float,
    z1: float,
    radius_scale: float = 1.65,
    depth_mm: float = 4.2,
    extra_top_mm: float = 2.0,
) -> Tuple[Optional[Any], Dict[str, Any]]:
    raise RuntimeError("archived dead path: use production lug-pocket cuts instead")
    params = features.get("global_params") or {}
    try:
        pcd_radius = float(params.get("pcd_radius"))
        hole_radius = float(params.get("hole_radius"))
        hole_count = int(params.get("hole_count"))
        phase_angle = float(params.get("pcd_phase_angle", 0.0) or 0.0)
        hub_face_z = float(params.get("hub_face_z", z1) or z1)
    except Exception:
        return None, {"status": "missing_pcd_counterbore_params"}
    counter_radius = max(hole_radius + 1.0, hole_radius * float(radius_scale))
    if pcd_radius <= 0.0 or counter_radius <= hole_radius or hole_count <= 0:
        return None, {
            "status": "invalid_pcd_counterbore_params",
            "pcd_radius": pcd_radius,
            "hole_radius": hole_radius,
            "counter_radius": counter_radius,
            "hole_count": hole_count,
        }
    cut_top = min(float(z1) + float(extra_top_mm), hub_face_z + float(extra_top_mm))
    cut_z0 = max(float(z0), cut_top - max(0.4, float(depth_mm)) - float(extra_top_mm))
    points = []
    for idx in range(hole_count):
        angle = math.radians(phase_angle + ((360.0 / float(hole_count)) * idx))
        points.append((math.cos(angle) * pcd_radius, math.sin(angle) * pcd_radius))
    try:
        cutter = cq.Workplane("XY").workplane(offset=cut_z0).pushPoints(points).circle(counter_radius).extrude(cut_top - cut_z0).val()
        cutter = valid_single_shape(cutter, "pcd counterbore cutter")
    except Exception as exc:
        return None, {"status": "failed", "error": str(exc)}
    return cutter, {
        "status": "built",
        "pcd_radius": float(pcd_radius),
        "hole_radius": float(hole_radius),
        "counter_radius": float(counter_radius),
        "hole_count": int(hole_count),
        "phase_angle_deg": float(phase_angle),
        "z0": float(cut_z0),
        "z1": float(cut_top),
        "depth_mm": float(depth_mm),
    }


def build_front_hub_groove_cutter(
    features: Dict[str, Any],
    *,
    z0: float,
    z1: float,
    depth_mm: float,
    inner_offset_mm: float = 4.0,
    outer_offset_mm: float = -4.0,
) -> Tuple[Optional[Any], Dict[str, Any]]:
    raise RuntimeError("archived dead path: front synthetic groove was rejected")
    params = features.get("global_params") or {}
    try:
        bore_radius = float(params.get("bore_radius"))
        pcd_radius = float(params.get("pcd_radius"))
        hub_radius = float(params.get("hub_radius"))
        hub_face_z = float(params.get("hub_face_z", z1) or z1)
    except Exception:
        return None, {"status": "missing_hub_groove_params"}
    inner_r = max(0.0, bore_radius + float(inner_offset_mm))
    outer_r = min(hub_radius - 1.0, pcd_radius + float(outer_offset_mm))
    if outer_r <= inner_r + 1.0:
        outer_r = min(hub_radius - 1.0, max(inner_r + 2.0, pcd_radius + 0.5 * (hub_radius - pcd_radius)))
    if outer_r <= inner_r + 1.0:
        return None, {"status": "invalid_groove_radii", "inner_r": inner_r, "outer_r": outer_r}
    cut_depth = max(0.2, float(depth_mm))
    cut_top = min(float(z1) + 1.0, hub_face_z + 2.0)
    cut_z0 = max(float(z0), cut_top - cut_depth - 2.0)
    try:
        cutter = build_radial_band_clip_solid(z0=cut_z0, z1=cut_top, inner_r=inner_r, outer_r=outer_r)
        cutter = valid_single_shape(cutter, "front hub groove cutter")
    except Exception as exc:
        return None, {"status": "failed", "error": str(exc), "inner_r": inner_r, "outer_r": outer_r}
    return cutter, {
        "status": "built",
        "inner_r": float(inner_r),
        "outer_r": float(outer_r),
        "z0": float(cut_z0),
        "z1": float(cut_top),
        "depth_mm": float(cut_depth),
    }


def apply_post_spoke_detail_cuts(
    shape: Any,
    *,
    features: Dict[str, Any],
    z0: float,
    z1: float,
    cut_pcd_holes: bool,
    pcd_radius_scale: float,
    pcd_extra_depth_mm: float,
    cut_pcd_counterbores: bool,
    pcd_counterbore_radius_scale: float,
    pcd_counterbore_depth_mm: float,
    cut_hub_groove: bool,
    hub_groove_depth_mm: float,
    hub_groove_inner_offset_mm: float,
    hub_groove_outer_offset_mm: float,
) -> Tuple[Any, Dict[str, Any]]:
    raise RuntimeError("archived dead path: use production hub cuts on the base hub body")
    result = shape
    meta: Dict[str, Any] = {
        "pcd_holes": {"status": "disabled"},
        "pcd_counterbores": {"status": "disabled"},
        "hub_groove": {"status": "disabled"},
    }
    if bool(cut_pcd_holes):
        cutter, cutter_meta = build_pcd_hole_cutter(
            features,
            z0=float(z0),
            z1=float(z1),
            radius_scale=float(pcd_radius_scale),
            extra_depth_mm=float(pcd_extra_depth_mm),
        )
        meta["pcd_holes"] = cutter_meta
        if cutter is not None:
            try:
                result = valid_single_shape(result.cut(cutter), "post pcd holes")
                meta["pcd_holes"] = dict(cutter_meta)
                meta["pcd_holes"]["status"] = "applied"
            except Exception as exc:
                meta["pcd_holes"] = dict(cutter_meta)
                meta["pcd_holes"].update({"status": "failed_cut", "error": str(exc)})
    if bool(cut_pcd_counterbores):
        cutter, cutter_meta = build_pcd_counterbore_cutter(
            features,
            z0=float(z0),
            z1=float(z1),
            radius_scale=float(pcd_counterbore_radius_scale),
            depth_mm=float(pcd_counterbore_depth_mm),
        )
        meta["pcd_counterbores"] = cutter_meta
        if cutter is not None:
            try:
                result = valid_single_shape(result.cut(cutter), "post pcd counterbores")
                meta["pcd_counterbores"] = dict(cutter_meta)
                meta["pcd_counterbores"]["status"] = "applied"
            except Exception as exc:
                meta["pcd_counterbores"] = dict(cutter_meta)
                meta["pcd_counterbores"].update({"status": "failed_cut", "error": str(exc)})
    if bool(cut_hub_groove):
        cutter, cutter_meta = build_front_hub_groove_cutter(
            features,
            z0=float(z0),
            z1=float(z1),
            depth_mm=float(hub_groove_depth_mm),
            inner_offset_mm=float(hub_groove_inner_offset_mm),
            outer_offset_mm=float(hub_groove_outer_offset_mm),
        )
        meta["hub_groove"] = cutter_meta
        if cutter is not None:
            try:
                result = valid_single_shape(result.cut(cutter), "post hub groove")
                meta["hub_groove"] = dict(cutter_meta)
                meta["hub_groove"]["status"] = "applied"
            except Exception as exc:
                meta["hub_groove"] = dict(cutter_meta)
                meta["hub_groove"].update({"status": "failed_cut", "error": str(exc)})
    return result, meta


def apply_post_spoke_detail_cuts_to_shapes(
    shapes: Sequence[Any],
    *,
    features: Dict[str, Any],
    z0: float,
    z1: float,
    cut_pcd_holes: bool,
    pcd_radius_scale: float,
    pcd_extra_depth_mm: float,
    cut_pcd_counterbores: bool,
    pcd_counterbore_radius_scale: float,
    pcd_counterbore_depth_mm: float,
    cut_hub_groove: bool,
    hub_groove_depth_mm: float,
    hub_groove_inner_offset_mm: float,
    hub_groove_outer_offset_mm: float,
) -> Tuple[List[Any], Dict[str, Any]]:
    raise RuntimeError("archived dead path: per-shape detail cuts were rejected")
    result = list(shapes)
    meta: Dict[str, Any] = {
        "pcd_holes": {"status": "disabled"},
        "pcd_counterbores": {"status": "disabled"},
        "hub_groove": {"status": "disabled"},
    }

    def cut_each(cutter: Any, label: str) -> Tuple[List[Any], int, List[Dict[str, Any]]]:
        next_shapes: List[Any] = []
        cut_count = 0
        failures: List[Dict[str, Any]] = []
        for shape_index, item in enumerate(result):
            try:
                next_shapes.append(valid_single_shape(item.cut(cutter), f"{label} shape {shape_index}"))
                cut_count += 1
            except Exception as exc:
                next_shapes.append(item)
                failures.append({"shape_index": int(shape_index), "error": str(exc)})
        return next_shapes, cut_count, failures

    if bool(cut_pcd_holes):
        cutter, cutter_meta = build_pcd_hole_cutter(
            features,
            z0=float(z0),
            z1=float(z1),
            radius_scale=float(pcd_radius_scale),
            extra_depth_mm=float(pcd_extra_depth_mm),
        )
        meta["pcd_holes"] = cutter_meta
        if cutter is not None:
            result, cut_count, failures = cut_each(cutter, "post pcd holes")
            meta["pcd_holes"] = dict(cutter_meta)
            meta["pcd_holes"].update(
                {
                    "status": "applied",
                    "shape_cut_count": int(cut_count),
                    "shape_failures": failures,
                }
            )

    if bool(cut_pcd_counterbores):
        cutter, cutter_meta = build_pcd_counterbore_cutter(
            features,
            z0=float(z0),
            z1=float(z1),
            radius_scale=float(pcd_counterbore_radius_scale),
            depth_mm=float(pcd_counterbore_depth_mm),
        )
        meta["pcd_counterbores"] = cutter_meta
        if cutter is not None:
            result, cut_count, failures = cut_each(cutter, "post pcd counterbores")
            meta["pcd_counterbores"] = dict(cutter_meta)
            meta["pcd_counterbores"].update(
                {
                    "status": "applied",
                    "shape_cut_count": int(cut_count),
                    "shape_failures": failures,
                }
            )

    if bool(cut_hub_groove):
        cutter, cutter_meta = build_front_hub_groove_cutter(
            features,
            z0=float(z0),
            z1=float(z1),
            depth_mm=float(hub_groove_depth_mm),
            inner_offset_mm=float(hub_groove_inner_offset_mm),
            outer_offset_mm=float(hub_groove_outer_offset_mm),
        )
        meta["hub_groove"] = cutter_meta
        if cutter is not None:
            result, cut_count, failures = cut_each(cutter, "post hub groove")
            meta["hub_groove"] = dict(cutter_meta)
            meta["hub_groove"].update(
                {
                    "status": "applied",
                    "shape_cut_count": int(cut_count),
                    "shape_failures": failures,
                }
            )

    return result, meta


def build_production_hub_cut_namespace(features: Dict[str, Any]) -> Dict[str, Any]:
    payload = json.loads(json.dumps(single_spoke.sanitize_for_json(features), ensure_ascii=False))
    payload["disable_spokes_modeling"] = True
    payload["debug_output_root"] = None
    namespace: Dict[str, Any] = {}
    code = production_codegen.generate_cadquery_code(payload)
    exec(code, namespace, namespace)
    return namespace


def apply_production_hub_detail_cuts_to_shapes(
    shapes: Sequence[Any],
    *,
    features: Dict[str, Any],
) -> Tuple[List[Any], Dict[str, Any]]:
    raise RuntimeError("archived dead path: per-shape production cuts were rejected")
    result = list(shapes)
    params = features.get("global_params") or {}
    meta: Dict[str, Any] = {
        "status": "disabled",
        "source": "pipeline_modeling_codegen.apply_post_revolve_hub_cuts",
        "lug_pockets": {"status": "disabled"},
        "pcd_holes": {"status": "disabled"},
        "hub_bottom_grooves": {"status": "disabled"},
    }
    try:
        namespace = build_production_hub_cut_namespace(features)
    except Exception as exc:
        meta.update({"status": "namespace_failed", "error": str(exc)})
        return result, meta

    def cut_each(cutter: Any, label: str) -> Tuple[int, List[Dict[str, Any]]]:
        nonlocal result
        cutter_obj = cutter
        if hasattr(cutter_obj, "val"):
            try:
                cutter_obj = cutter_obj.val()
            except Exception:
                pass
        next_shapes: List[Any] = []
        cut_count = 0
        failures: List[Dict[str, Any]] = []
        for shape_index, item in enumerate(result):
            try:
                next_shapes.append(valid_single_shape(item.cut(cutter_obj), f"{label} shape {shape_index}"))
                cut_count += 1
            except Exception as exc:
                next_shapes.append(item)
                failures.append({"shape_index": int(shape_index), "error": str(exc)})
        result = next_shapes
        return int(cut_count), failures

    pcd_radius = float(params.get("pcd_radius", 0.0) or 0.0)
    hole_radius = float(params.get("hole_radius", 0.0) or 0.0)
    phase = float(params.get("pcd_phase_angle", 0.0) or 0.0)
    hole_count = max(1, int(params.get("hole_count", params.get("spoke_num", 0)) or 0))
    hub_z_val = float(params.get("hub_z_offset", 0.0) or 0.0)
    hub_top_z = float(params.get("hub_top_z", hub_z_val + float(params.get("hub_thickness", 40.0) or 40.0)) or 0.0)
    hub_top_z = max(hub_z_val + 5.0, hub_top_z)
    hub_t_val = max(5.0, hub_top_z - hub_z_val)

    make_lug_pocket = namespace.get("make_lug_pocket_cutter")
    pocket_top_z = params.get("pocket_top_z")
    pocket_floor_z = params.get("pocket_floor_z")
    pocket_outer_r = params.get("pocket_radius")
    pocket_floor_r = params.get("pocket_floor_radius")
    pocket_meta: Dict[str, Any] = {
        "status": "disabled",
        "wall_cut_count": 0,
        "floor_cut_count": 0,
        "failures": [],
    }
    has_measured_pockets = callable(make_lug_pocket) and all(
        value is not None
        for value in (pocket_top_z, pocket_floor_z, pocket_outer_r, pocket_floor_r)
    )
    if has_measured_pockets and pcd_radius > 0.0 and hole_count > 0:
        pocket_top_z = min(hub_top_z, float(pocket_top_z))
        pocket_floor_z = max(hub_z_val + 1.0, min(float(pocket_top_z) - 0.5, float(pocket_floor_z)))
        pocket_outer_r = float(pocket_outer_r)
        pocket_floor_r = min(float(pocket_floor_r), float(pocket_outer_r) - 0.5)
        pocket_entry_z = float(pocket_top_z)
        face_candidates = []
        for key in ("hub_face_z", "hub_outer_face_z"):
            face_z = params.get(key)
            if face_z is None:
                continue
            try:
                face_candidates.append(min(hub_top_z, float(face_z)))
            except Exception:
                continue
        if face_candidates:
            pocket_entry_z = min(hub_top_z, max(pocket_entry_z, max(face_candidates)))
        for index in range(hole_count):
            angle_deg = phase + (360.0 / float(hole_count)) * index
            angle_rad = math.radians(angle_deg)
            center_x = pcd_radius * math.cos(angle_rad)
            center_y = pcd_radius * math.sin(angle_rad)
            try:
                wall_cutter, floor_cutter = make_lug_pocket(
                    center_x,
                    center_y,
                    pocket_entry_z,
                    pocket_floor_z,
                    pocket_outer_r,
                    pocket_floor_r,
                )
            except Exception as exc:
                pocket_meta["failures"].append({"index": int(index), "error": str(exc)})
                continue
            if wall_cutter is not None:
                cut_count, failures = cut_each(wall_cutter, f"production lug pocket {index} wall")
                pocket_meta["wall_cut_count"] = int(pocket_meta["wall_cut_count"]) + cut_count
                pocket_meta["failures"].extend(failures)
            if floor_cutter is not None:
                cut_count, failures = cut_each(floor_cutter, f"production lug pocket {index} floor")
                pocket_meta["floor_cut_count"] = int(pocket_meta["floor_cut_count"]) + cut_count
                pocket_meta["failures"].extend(failures)
        pocket_meta.update(
            {
                "status": "applied",
                "pocket_entry_z": float(pocket_entry_z),
                "pocket_floor_z": float(pocket_floor_z),
                "pocket_outer_r": float(pocket_outer_r),
                "pocket_floor_r": float(pocket_floor_r),
            }
        )
    else:
        pocket_meta["status"] = "missing_measured_pockets"
    meta["lug_pockets"] = pocket_meta

    hole_meta: Dict[str, Any] = {"status": "disabled", "shape_cut_count": 0, "failures": []}
    if pcd_radius > 0.0 and hole_radius > 0.0 and hole_count > 0:
        for index in range(hole_count):
            angle_deg = phase + (360.0 / float(hole_count)) * index
            angle_rad = math.radians(angle_deg)
            center_x = pcd_radius * math.cos(angle_rad)
            center_y = pcd_radius * math.sin(angle_rad)
            cutter = (
                cq.Workplane("XY")
                .workplane(offset=hub_z_val - 1.0)
                .center(center_x, center_y)
                .circle(hole_radius)
                .extrude(hub_t_val + 2.0)
            )
            cut_count, failures = cut_each(cutter, f"production pcd hole {index}")
            hole_meta["shape_cut_count"] = int(hole_meta["shape_cut_count"]) + cut_count
            hole_meta["failures"].extend(failures)
        hole_meta.update(
            {
                "status": "applied",
                "pcd_radius": float(pcd_radius),
                "hole_radius": float(hole_radius),
                "hole_count": int(hole_count),
                "phase_angle_deg": float(phase),
            }
        )
    else:
        hole_meta["status"] = "missing_pcd_params"
    meta["pcd_holes"] = hole_meta

    groove_regions = features.get("hub_bottom_groove_regions") or []
    groove_floor_z = params.get("hub_bottom_groove_floor_z")
    groove_top_z = params.get("hub_bottom_groove_top_z")
    apply_groove = namespace.get("apply_hub_bottom_groove_relief")
    groove_meta: Dict[str, Any] = {"status": "disabled", "shape_cut_count": 0, "failures": []}
    if callable(apply_groove) and groove_regions and groove_floor_z is not None and groove_top_z is not None:
        next_shapes = []
        for shape_index, item in enumerate(result):
            try:
                workplane_item = cq.Workplane("XY").newObject([item])
                cut_shape = apply_groove(
                    workplane_item,
                    groove_regions,
                    float(groove_floor_z),
                    min(hub_top_z, float(groove_top_z)),
                    float(params.get("bore_radius", 0.0) or 0.0),
                    hub_z_val,
                )
                if hasattr(cut_shape, "val"):
                    cut_shape = cut_shape.val()
                next_shapes.append(valid_single_shape(cut_shape, f"production hub bottom groove shape {shape_index}"))
                groove_meta["shape_cut_count"] = int(groove_meta["shape_cut_count"]) + 1
            except Exception as exc:
                next_shapes.append(item)
                groove_meta["failures"].append({"shape_index": int(shape_index), "error": str(exc)})
        result = next_shapes
        groove_meta.update(
            {
                "status": "applied",
                "region_count": int(len(groove_regions)),
                "floor_z": float(groove_floor_z),
                "top_z": float(groove_top_z),
            }
        )
    else:
        groove_meta["status"] = "missing_groove_inputs"
    meta["hub_bottom_grooves"] = groove_meta
    meta["status"] = "applied"
    return result, meta


def assemble_shapes_for_production_post_cuts(shapes: Sequence[Any]) -> Tuple[Any, Dict[str, Any]]:
    solids: List[Any] = []
    failures: List[Dict[str, Any]] = []
    for shape_index, item in enumerate(shapes):
        try:
            if isinstance(item, cq.Workplane):
                vals = item.vals()
            elif hasattr(item, "Solids"):
                vals = list(item.Solids())
            else:
                vals = [item]
            for val in vals:
                if val is not None and hasattr(val, "wrapped"):
                    solids.append(val)
        except Exception as exc:
            failures.append({"shape_index": int(shape_index), "error": str(exc)})
    if not solids:
        raise RuntimeError("no solids available for production post hub cuts")
    body = cq.Workplane("XY").newObject([cq.Compound.makeCompound(solids)])
    return body, {
        "input_shape_count": int(len(shapes)),
        "assembled_solid_count": int(len(solids)),
        "assembly_failures": failures,
    }


def workplane_volume(body: Any) -> Optional[float]:
    try:
        return float(sum(float(solid.Volume()) for solid in body.solids().vals()))
    except Exception:
        try:
            val = body.val()
            if hasattr(val, "Volume"):
                return float(val.Volume())
        except Exception:
            return None
    return None


def apply_production_hub_detail_cuts_to_assembled_body(
    shapes: Sequence[Any],
    *,
    features: Dict[str, Any],
) -> Tuple[List[Any], Dict[str, Any]]:
    meta: Dict[str, Any] = {
        "status": "disabled",
        "source": "pipeline_modeling_codegen.apply_post_revolve_hub_cuts",
        "mode": "assembled_body",
    }
    try:
        namespace = build_production_hub_cut_namespace(features)
    except Exception as exc:
        meta.update({"status": "namespace_failed", "error": str(exc)})
        return list(shapes), meta

    apply_post_revolve_hub_cuts = namespace.get("apply_post_revolve_hub_cuts")
    if not callable(apply_post_revolve_hub_cuts):
        meta.update({"status": "missing_apply_post_revolve_hub_cuts"})
        return list(shapes), meta

    try:
        body, assembly_meta = assemble_shapes_for_production_post_cuts(shapes)
    except Exception as exc:
        meta.update({"status": "assembly_failed", "error": str(exc)})
        return list(shapes), meta

    before_volume = workplane_volume(body)
    try:
        cut_body = apply_post_revolve_hub_cuts(body)
    except Exception as exc:
        meta.update({"status": "apply_failed", "error": str(exc), **assembly_meta})
        return list(shapes), meta

    validator = namespace.get("body_has_valid_shape")
    is_valid = False
    if callable(validator):
        try:
            is_valid = bool(validator(cut_body))
        except Exception:
            is_valid = False
    if not is_valid:
        try:
            is_valid = bool(section_diff.filter_valid_export_shapes(section_diff.collect_export_shapes(cut_body), "production assembled hub cuts"))
        except Exception:
            is_valid = False
    if not is_valid:
        meta.update({"status": "invalid_after_apply", **assembly_meta})
        return list(shapes), meta

    exported_shapes = section_diff.filter_valid_export_shapes(
        section_diff.collect_export_shapes(cut_body),
        "production assembled hub cuts",
    )
    if not exported_shapes:
        meta.update({"status": "empty_after_apply", **assembly_meta})
        return list(shapes), meta
    result_shape = exported_shapes[0] if len(exported_shapes) == 1 else cq.Compound.makeCompound(exported_shapes)
    after_volume = workplane_volume(cq.Workplane("XY").newObject([result_shape]))
    volume_removed = (before_volume - after_volume) if before_volume is not None and after_volume is not None else None
    status = "applied"
    if volume_removed is not None and abs(float(volume_removed)) <= 1e-3:
        status = "applied_no_volume_change"
    meta.update(
        {
            "status": status,
            **assembly_meta,
            "output_shape_count": int(len(exported_shapes)),
            "volume_before": before_volume,
            "volume_after": after_volume,
            "volume_removed": volume_removed,
        }
    )
    return [result_shape], meta


def smooth_finite(values: Sequence[float], radius: int = 2) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    out = arr.copy()
    for idx in range(len(arr)):
        lo = max(0, idx - int(radius))
        hi = min(len(arr), idx + int(radius) + 1)
        window = arr[lo:hi]
        window = window[np.isfinite(window)]
        if len(window):
            out[idx] = float(np.median(window))
    return out


def extract_member_planform_profile(
    member_submesh: Any,
    member_payload: Dict[str, Any],
    margin_mm: float,
    bins: int,
    lower_percentile: float,
    upper_percentile: float,
    min_width_mm: float,
    span_mode: str = "section",
    span_root_margin_mm: float = 4.0,
    span_tip_margin_mm: float = 4.0,
    full_span_percentile: float = 0.8,
) -> Tuple[Optional[Dict[str, np.ndarray]], Dict[str, Any]]:
    if member_submesh is None or getattr(member_submesh, "vertices", None) is None or len(member_submesh.vertices) < 10:
        return None, {"status": "missing_member_submesh"}

    angle_rad = math.radians(float(member_payload.get("angle", 0.0)))
    radial = np.asarray([math.cos(angle_rad), math.sin(angle_rad)], dtype=float)
    tangent = np.asarray([-math.sin(angle_rad), math.cos(angle_rad)], dtype=float)

    points = np.asarray(member_submesh.vertices, dtype=float)
    if points is None or len(points) < 10:
        return None, {"status": "empty_member_points"}

    xy = np.asarray(points[:, :2], dtype=float)
    local_x = xy @ radial
    local_y = xy @ tangent
    radial_r = np.linalg.norm(xy, axis=1)
    finite_mask = np.isfinite(local_x) & np.isfinite(local_y) & np.isfinite(radial_r)
    local_x = local_x[finite_mask]
    local_y = local_y[finite_mask]
    radial_r = radial_r[finite_mask]
    if len(local_x) < 20:
        return None, {"status": "insufficient_member_points", "point_count": int(len(local_x))}

    raw_min_x = float(np.min(local_x))
    raw_max_x = float(np.max(local_x))
    raw_min_r = float(np.min(radial_r))
    raw_max_r = float(np.max(radial_r))
    raw_x0 = raw_min_x
    raw_x1 = raw_max_x
    if str(span_mode) != "full":
        raw_x0 = float(np.percentile(local_x, max(0.0, min(5.0, float(full_span_percentile)))))
        raw_x1 = float(np.percentile(local_x, min(100.0, max(95.0, 100.0 - float(full_span_percentile)))))
    section_r0, section_r1 = member_section_station_span(member_payload)
    if str(span_mode) == "full" or section_r0 is None or section_r1 is None or section_r1 <= section_r0:
        x0 = raw_x0
        x1 = raw_x1
    else:
        x0 = float(section_r0)
        x1 = float(section_r1)
    x0 -= float(span_root_margin_mm)
    x1 += float(span_tip_margin_mm)
    span_mask = (local_x >= x0) & (local_x <= x1)
    local_x = local_x[span_mask]
    local_y = local_y[span_mask]
    radial_r = radial_r[span_mask]
    if len(local_x) < 20:
        return None, {"status": "empty_after_span_filter", "x0": x0, "x1": x1}

    edges = np.linspace(x0, x1, max(8, int(bins)) + 1)
    centers: List[float] = []
    lower: List[float] = []
    upper: List[float] = []
    min_points = max(8, int(len(local_x) / max(1, int(bins)) * 0.08))
    for idx in range(len(edges) - 1):
        mask = (local_x >= edges[idx]) & (local_x < edges[idx + 1])
        if np.count_nonzero(mask) < min_points:
            continue
        yy = local_y[mask]
        lo = float(np.percentile(yy, float(lower_percentile))) - float(margin_mm)
        hi = float(np.percentile(yy, float(upper_percentile))) + float(margin_mm)
        if hi <= lo + float(min_width_mm):
            mid = 0.5 * (lo + hi)
            lo = mid - (0.5 * float(min_width_mm))
            hi = mid + (0.5 * float(min_width_mm))
        centers.append(float(0.5 * (edges[idx] + edges[idx + 1])))
        lower.append(lo)
        upper.append(hi)

    if len(centers) < 4:
        return None, {"status": "too_few_planform_bins", "bin_count": int(len(centers))}

    centers_arr = np.asarray(centers, dtype=float)
    lower_arr = smooth_finite(lower, radius=2)
    upper_arr = smooth_finite(upper, radius=2)
    if len(centers_arr) > 0:
        if centers_arr[0] > x0 + 1e-6:
            centers_arr = np.concatenate((np.asarray([float(x0)], dtype=float), centers_arr))
            lower_arr = np.concatenate((np.asarray([float(lower_arr[0])], dtype=float), lower_arr))
            upper_arr = np.concatenate((np.asarray([float(upper_arr[0])], dtype=float), upper_arr))
        if centers_arr[-1] < x1 - 1e-6:
            centers_arr = np.concatenate((centers_arr, np.asarray([float(x1)], dtype=float)))
            lower_arr = np.concatenate((lower_arr, np.asarray([float(lower_arr[-1])], dtype=float)))
            upper_arr = np.concatenate((upper_arr, np.asarray([float(upper_arr[-1])], dtype=float)))
    upper_xy = (centers_arr[:, None] * radial[None, :]) + (upper_arr[:, None] * tangent[None, :])
    lower_xy = (centers_arr[:, None] * radial[None, :]) + (lower_arr[:, None] * tangent[None, :])
    profile_radial = np.concatenate((np.linalg.norm(upper_xy, axis=1), np.linalg.norm(lower_xy, axis=1)))
    profile = {
        "x": centers_arr,
        "lower": lower_arr,
        "upper": upper_arr,
        "radial": radial,
        "tangent": tangent,
        "span_x0": float(x0),
        "span_x1": float(x1),
        "raw_min_x": float(raw_min_x),
        "raw_max_x": float(raw_max_x),
        "radial_r0": float(np.min(radial_r)),
        "radial_r1": float(np.max(radial_r)),
        "raw_min_r": float(raw_min_r),
        "raw_max_r": float(raw_max_r),
        "profile_radial_r0": float(np.min(profile_radial)),
        "profile_radial_r1": float(np.max(profile_radial)),
    }
    return profile, {
        "status": "built",
        "point_count": int(len(local_x)),
        "bin_count": int(len(centers_arr)),
        "x0": float(x0),
        "x1": float(x1),
        "raw_min_x": float(raw_min_x),
        "raw_max_x": float(raw_max_x),
        "radial_r0": float(np.min(radial_r)),
        "radial_r1": float(np.max(radial_r)),
        "raw_min_r": float(raw_min_r),
        "raw_max_r": float(raw_max_r),
        "profile_radial_r0": float(np.min(profile_radial)),
        "profile_radial_r1": float(np.max(profile_radial)),
        "raw_x0": float(raw_x0),
        "raw_x1": float(raw_x1),
        "span_mode": str(span_mode),
        "span_root_margin_mm": float(span_root_margin_mm),
        "span_tip_margin_mm": float(span_tip_margin_mm),
        "full_span_percentile": float(full_span_percentile),
        "min_width_mm": float(np.min(upper_arr - lower_arr)),
        "max_width_mm": float(np.max(upper_arr - lower_arr)),
    }


def planform_profile_bounds_at(profile: Optional[Dict[str, np.ndarray]], station_r: float) -> Optional[Tuple[float, float]]:
    if profile is None:
        return None
    xs = np.asarray(profile.get("x"), dtype=float)
    lower = np.asarray(profile.get("lower"), dtype=float)
    upper = np.asarray(profile.get("upper"), dtype=float)
    if len(xs) < 2 or len(lower) != len(xs) or len(upper) != len(xs):
        return None
    x = float(station_r)
    if x < float(np.min(xs)) - 1.0 or x > float(np.max(xs)) + 1.0:
        return None
    return (
        float(np.interp(x, xs, lower)),
        float(np.interp(x, xs, upper)),
    )


def visual_constraint_for_member(payload: Optional[Dict[str, Any]], member_index: int) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    for row in payload.get("members") or []:
        if not isinstance(row, dict):
            continue
        try:
            if int(row.get("member_index", -1)) == int(member_index):
                return row
        except Exception:
            continue
    return None


def planform_profile_from_visual_constraint(row: Optional[Dict[str, Any]]) -> Tuple[Optional[Dict[str, np.ndarray]], Dict[str, Any]]:
    if not isinstance(row, dict):
        return None, {"status": "disabled"}
    profile_rows = [item for item in (row.get("planform_profile") or []) if isinstance(item, dict)]
    xs: List[float] = []
    lower: List[float] = []
    upper: List[float] = []
    for item in profile_rows:
        try:
            x = float(item.get("station_r", 0.0))
            lo = float(item.get("lower_y"))
            hi = float(item.get("upper_y"))
        except Exception:
            continue
        if x <= 0.0 or hi <= lo + 1e-6:
            continue
        xs.append(x)
        lower.append(lo)
        upper.append(hi)
    if len(xs) < 4:
        return None, {
            "status": "too_few_visual_constraint_bins",
            "member_index": int(row.get("member_index", -1)),
            "bin_count": int(len(xs)),
        }
    order = np.argsort(np.asarray(xs, dtype=float))
    xs_arr = np.asarray(xs, dtype=float)[order]
    lower_arr = np.asarray(lower, dtype=float)[order]
    upper_arr = np.asarray(upper, dtype=float)[order]
    return (
        {
            "x": xs_arr,
            "lower": lower_arr,
            "upper": upper_arr,
        },
        {
            "status": "built_from_visual_constraints",
            "member_index": int(row.get("member_index", -1)),
            "bin_count": int(len(xs_arr)),
            "min_width_mm": float(np.min(upper_arr - lower_arr)),
            "max_width_mm": float(np.max(upper_arr - lower_arr)),
        },
    )


def build_visual_groove_cutter(
    groove_row: Dict[str, Any],
    angle_deg: float,
    z0: float,
    z1: float,
    width_scale: float,
) -> Optional[Any]:
    groove = groove_row.get("groove") if isinstance(groove_row, dict) else None
    window = groove.get("window") if isinstance(groove, dict) else None
    if not isinstance(window, dict) or not bool(groove.get("detected")):
        return None
    try:
        r0 = float(window.get("radial_start_mm"))
        r1 = float(window.get("radial_end_mm"))
        cy = float(window.get("mean_center_y_mm"))
        mean_width = float(window.get("mean_width_mm"))
    except Exception:
        return None
    if r1 <= r0 + 1.0 or mean_width <= 1.0:
        return None
    groove_width = max(3.5, min(12.0, mean_width * float(width_scale)))
    y0 = cy - (0.5 * groove_width)
    y1 = cy + (0.5 * groove_width)
    theta = math.radians(float(angle_deg))
    radial = np.asarray([math.cos(theta), math.sin(theta)], dtype=float)
    tangent = np.asarray([-math.sin(theta), math.cos(theta)], dtype=float)

    def xy(local_r: float, local_y: float) -> Tuple[float, float]:
        pt = (radial * float(local_r)) + (tangent * float(local_y))
        return (float(pt[0]), float(pt[1]))

    pts = [xy(r0, y0), xy(r1, y0), xy(r1, y1), xy(r0, y1)]
    height = max(0.5, float(z1) - float(z0))
    try:
        return cq.Workplane("XY").workplane(offset=float(z0)).polyline(pts).close().extrude(height).val()
    except Exception:
        return None


def visual_groove_params_from_constraint(
    row: Optional[Dict[str, Any]],
    station_r: float,
    station_min: float,
    station_max: float,
    depth_scale: float,
    max_depth_mm: float,
    width_scale: float,
    edge_fade_mm: float,
) -> Optional[Dict[str, float]]:
    if not isinstance(row, dict):
        return None
    groove = row.get("groove") if isinstance(row, dict) else None
    window = groove.get("window") if isinstance(groove, dict) else None
    if not isinstance(window, dict) or not bool(groove.get("detected")):
        return None
    try:
        r0 = float(window.get("radial_start_mm"))
        r1 = float(window.get("radial_end_mm"))
        center_x = float(window.get("mean_center_y_mm"))
        mean_width = float(window.get("mean_width_mm"))
        mean_drop = float(window.get("mean_drop_mm"))
    except Exception:
        return None
    station = float(station_r)
    fade = max(0.5, float(edge_fade_mm))
    if station < r0 - fade or station > r1 + fade:
        return None
    if r1 <= r0 + 1.0 or mean_width <= 1.0 or mean_drop <= 0.1:
        return None
    if station < r0:
        gain = max(0.0, min(1.0, (station - (r0 - fade)) / fade))
    elif station > r1:
        gain = max(0.0, min(1.0, ((r1 + fade) - station) / fade))
    else:
        rel = (station - r0) / max(1e-6, r1 - r0)
        gain = math.sin(math.pi * max(0.0, min(1.0, rel)))
    global_ratio = (station - float(station_min)) / max(1e-6, float(station_max) - float(station_min))
    if global_ratio < 0.26 or global_ratio > 0.82:
        return None
    groove_width = max(5.0, min(18.0, mean_width * float(width_scale)))
    return {
        "strength": float(max(0.0, min(1.0, gain))),
        "center_x": float(center_x),
        "half_width": float(0.5 * groove_width),
        "depth": float(max(0.1, min(float(max_depth_mm), mean_drop * float(depth_scale)))),
    }


def build_member_planform_clip_solid(
    member_submesh: Any,
    member_payload: Dict[str, Any],
    z0: float,
    z1: float,
    margin_mm: float,
    bins: int,
    lower_percentile: float,
    upper_percentile: float,
    min_width_mm: float,
    root_pad_mm: float = 0.0,
    tip_pad_mm: float = 0.0,
    root_expand_mm: float = 0.0,
    tip_expand_mm: float = 0.0,
    extension_steps: int = 1,
    span_mode: str = "section",
    span_root_margin_mm: float = 4.0,
    span_tip_margin_mm: float = 4.0,
    full_span_percentile: float = 0.8,
) -> Tuple[Optional[Any], Dict[str, Any]]:
    profile, meta = extract_member_planform_profile(
        member_submesh,
        member_payload,
        margin_mm=float(margin_mm),
        bins=int(bins),
        lower_percentile=float(lower_percentile),
        upper_percentile=float(upper_percentile),
        min_width_mm=float(min_width_mm),
        span_mode=str(span_mode),
        span_root_margin_mm=float(span_root_margin_mm),
        span_tip_margin_mm=float(span_tip_margin_mm),
        full_span_percentile=float(full_span_percentile),
    )
    if profile is None:
        return None, meta
    profile = extend_planform_profile_edges(
        profile,
        root_pad_mm=float(root_pad_mm),
        tip_pad_mm=float(tip_pad_mm),
        root_expand_mm=float(root_expand_mm),
        tip_expand_mm=float(tip_expand_mm),
        steps=int(extension_steps),
    )
    meta = dict(meta)
    meta["root_pad_mm"] = float(root_pad_mm)
    meta["tip_pad_mm"] = float(tip_pad_mm)
    meta["root_expand_mm"] = float(root_expand_mm)
    meta["tip_expand_mm"] = float(tip_expand_mm)
    meta["extension_steps"] = int(extension_steps)

    centers_arr = np.asarray(profile["x"], dtype=float)
    lower_arr = np.asarray(profile["lower"], dtype=float)
    upper_arr = np.asarray(profile["upper"], dtype=float)
    radial = np.asarray(profile["radial"], dtype=float)
    tangent = np.asarray(profile["tangent"], dtype=float)

    upper_xy = [
        tuple((float(x) * radial + float(y) * tangent).tolist())
        for x, y in zip(centers_arr, upper_arr)
    ]
    lower_xy = [
        tuple((float(x) * radial + float(y) * tangent).tolist())
        for x, y in zip(centers_arr[::-1], lower_arr[::-1])
    ]
    polygon_xy = upper_xy + lower_xy
    if len(polygon_xy) < 6:
        return None, {"status": "too_few_polygon_points", "point_count": int(len(polygon_xy))}

    height = max(1.0, float(z1) - float(z0))
    try:
        clip = cq.Workplane("XY").workplane(offset=float(z0)).polyline(polygon_xy).close().extrude(height).val()
        clip = valid_single_shape(clip, "member planform clip")
    except Exception as exc:
        return None, {"status": "clip_build_failed", "error": str(exc)}

    return clip, meta


def shape_bbox(shape: Any) -> Tuple[float, float, float, float, float, float]:
    bb = shape.BoundingBox()
    return (
        float(bb.xmin),
        float(bb.xmax),
        float(bb.ymin),
        float(bb.ymax),
        float(bb.zmin),
        float(bb.zmax),
    )


def valid_single_shape(obj: Any, label: str) -> Any:
    valid = section_diff.filter_valid_export_shapes([obj], label)
    if not valid:
        raise RuntimeError(f"{label} invalid")
    return valid[0]


def shape_volume(shape: Any) -> float:
    try:
        return float(shape.Volume())
    except Exception:
        return 0.0


def apply_planform_clip_with_endpoint_preserve(
    *,
    template_shape: Any,
    planform_clip: Any,
    endpoint_source: Any,
    z0: float,
    z1: float,
    clip_inner_r: float,
    clip_outer_r: float,
    preserve_root_mm: float,
    preserve_tip_mm: float,
) -> Tuple[Any, Dict[str, Any]]:
    root_outer_r = max(0.0, float(clip_inner_r) + max(0.0, float(preserve_root_mm)))
    tip_inner_r = max(float(clip_inner_r), float(clip_outer_r) - max(0.0, float(preserve_tip_mm)))
    middle_inner_r = min(max(float(clip_inner_r), root_outer_r), float(clip_outer_r))
    middle_outer_r = max(middle_inner_r + 1.0, min(float(clip_outer_r), tip_inner_r))

    parts: List[Any] = []
    meta: Dict[str, Any] = {
        "mode": "endpoint_preserve",
        "preserve_root_mm": float(preserve_root_mm),
        "preserve_tip_mm": float(preserve_tip_mm),
        "clip_inner_r": float(clip_inner_r),
        "clip_outer_r": float(clip_outer_r),
        "middle_inner_r": float(middle_inner_r),
        "middle_outer_r": float(middle_outer_r),
        "root_outer_r": float(root_outer_r),
        "tip_inner_r": float(tip_inner_r),
    }

    try:
        middle_band = build_radial_band_clip_solid(
            z0=z0,
            z1=z1,
            inner_r=float(middle_inner_r),
            outer_r=float(middle_outer_r),
        )
        middle = template_shape.intersect(middle_band).intersect(planform_clip)
        parts.extend(section_diff.filter_valid_export_shapes([middle], "template planform middle clip"))
    except Exception as exc:
        meta["middle_error"] = str(exc)

    if root_outer_r > float(clip_inner_r) + 1e-6:
        try:
            root_band = build_radial_clip_solid(z0=z0, z1=z1, outer_r=float(root_outer_r))
            root_part = endpoint_source.intersect(root_band)
            parts.extend(section_diff.filter_valid_export_shapes([root_part], "template root endpoint preserve"))
        except Exception as exc:
            meta["root_error"] = str(exc)

    if float(clip_outer_r) > tip_inner_r + 1e-6:
        try:
            tip_band = build_radial_band_clip_solid(
                z0=z0,
                z1=z1,
                inner_r=float(tip_inner_r),
                outer_r=float(clip_outer_r),
            )
            tip_part = endpoint_source.intersect(tip_band)
            parts.extend(section_diff.filter_valid_export_shapes([tip_part], "template tip endpoint preserve"))
        except Exception as exc:
            meta["tip_error"] = str(exc)

    if not parts:
        meta["status"] = "fallback_full_clip"
        return valid_single_shape(template_shape.intersect(planform_clip), "template planform clip"), meta

    combined = parts[0] if len(parts) == 1 else cq.Compound.makeCompound(parts)
    meta["status"] = "built"
    meta["part_count"] = int(len(parts))
    return valid_single_shape(combined, "template planform endpoint preserve"), meta


def choose_best_refine_alignment(
    refine_body: Any,
    trim_source: Any,
    trim_clip: Any,
    refine_align_mode: str,
) -> Tuple[Any, str, float]:
    mode = str(refine_align_mode)
    if mode == "original":
        candidates: List[Tuple[str, Any]] = [("original", refine_body)]
    elif mode == "mirror_xy":
        candidates = [("mirror_xy", refine_body.mirror("XY"))]
    else:
        candidates = [("original", refine_body)]
        try:
            mirrored = refine_body.mirror("XY")
            candidates.append(("mirror_xy", mirrored))
        except Exception:
            pass
    best_shape = refine_body
    best_mode = "original"
    best_overlap = -1.0
    for mode, candidate in candidates:
        try:
            clipped = section_diff.filter_valid_export_shapes([candidate.intersect(trim_clip)], f"refine align {mode} clip")
            if not clipped:
                overlap = 0.0
            else:
                overlap_shapes = section_diff.filter_valid_export_shapes([clipped[0].intersect(trim_source)], f"refine align {mode} overlap")
                overlap = sum(shape_volume(shape) for shape in overlap_shapes)
        except Exception:
            overlap = 0.0
        if overlap > best_overlap:
            best_overlap = overlap
            best_shape = candidate
            best_mode = mode
    return best_shape, best_mode, float(best_overlap)


def canonicalize_local_section_loop(loop_points: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    pts = [(float(x), float(y)) for x, y in loop_points]
    if len(pts) < 4:
        return []
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return []
    signed_area = 0.0
    for idx in range(len(pts)):
        x1, y1 = pts[idx]
        x2, y2 = pts[(idx + 1) % len(pts)]
        signed_area += (x1 * y2) - (x2 * y1)
    if signed_area < 0.0:
        pts.reverse()
    start_idx = min(
        range(len(pts)),
        key=lambda idx: (
            round(float(pts[idx][1]), 6),
            round(float(pts[idx][0]), 6),
            round(-float(pts[idx][0]), 6),
        ),
    )
    pts = pts[start_idx:] + pts[:start_idx]
    pts.append(pts[0])
    return [(round(float(x), 3), round(float(y), 3)) for x, y in pts]


def resample_closed_loop(loop_points: Sequence[Tuple[float, float]], target_count: int = 64) -> List[Tuple[float, float]]:
    pts = [(float(x), float(y)) for x, y in loop_points]
    if len(pts) < 4:
        return []
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return []
    lengths = [0.0]
    total = 0.0
    for idx in range(len(pts)):
        x1, y1 = pts[idx]
        x2, y2 = pts[(idx + 1) % len(pts)]
        seg_len = math.hypot(x2 - x1, y2 - y1)
        total += seg_len
        lengths.append(total)
    if total <= 1e-6:
        return []
    sampled: List[Tuple[float, float]] = []
    step = total / max(3, int(target_count))
    for sample_idx in range(int(target_count)):
        target_len = sample_idx * step
        seg_idx = 0
        while seg_idx < len(pts) and lengths[seg_idx + 1] < target_len:
            seg_idx += 1
        x1, y1 = pts[seg_idx]
        x2, y2 = pts[(seg_idx + 1) % len(pts)]
        seg_start = lengths[seg_idx]
        seg_end = lengths[seg_idx + 1]
        if seg_end <= seg_start + 1e-9:
            t = 0.0
        else:
            t = (target_len - seg_start) / (seg_end - seg_start)
        sampled.append((x1 + ((x2 - x1) * t), y1 + ((y2 - y1) * t)))
    return [(round(float(x), 3), round(float(y), 3)) for x, y in sampled]


def closed_loop_signed_area(loop_points: Sequence[Tuple[float, float]]) -> float:
    pts = [(float(x), float(y)) for x, y in loop_points]
    if len(pts) < 3:
        return 0.0
    area = 0.0
    for idx in range(len(pts)):
        x1, y1 = pts[idx]
        x2, y2 = pts[(idx + 1) % len(pts)]
        area += (x1 * y2) - (x2 * y1)
    return area * 0.5


def align_resampled_loop(
    reference_loop: Sequence[Tuple[float, float]],
    candidate_loop: Sequence[Tuple[float, float]],
    allow_reverse: bool = False,
) -> List[Tuple[float, float]]:
    ref = [(float(x), float(y)) for x, y in reference_loop]
    cand = [(float(x), float(y)) for x, y in candidate_loop]
    if len(ref) != len(cand) or len(ref) < 3:
        return [(round(float(x), 3), round(float(y), 3)) for x, y in cand]
    if not allow_reverse:
        ref_area = closed_loop_signed_area(ref)
        cand_area = closed_loop_signed_area(cand)
        if abs(ref_area) > 1e-6 and abs(cand_area) > 1e-6 and (ref_area * cand_area) < 0.0:
            cand = list(reversed(cand))
    best_score = None
    best_loop = list(cand)
    reverse_options = (False, True) if allow_reverse else (False,)
    for reverse in reverse_options:
        working = list(reversed(cand)) if reverse else list(cand)
        for shift in range(len(ref)):
            score = 0.0
            for idx in range(len(ref)):
                rx, ry = ref[idx]
                cx, cy = working[(idx + shift) % len(ref)]
                dx = rx - cx
                dy = ry - cy
                score += (dx * dx) + (dy * dy)
            if best_score is None or score < best_score:
                best_score = score
                best_loop = [working[(idx + shift) % len(ref)] for idx in range(len(ref))]
    return [(round(float(x), 3), round(float(y), 3)) for x, y in best_loop]


def measure_section_polygon_fit(poly: Any, guide_poly: Optional[Any]) -> Tuple[float, float, float]:
    if poly is None or guide_poly is None:
        return 1.0, 0.0, 0.0
    area_ratio = float(poly.area) / max(1e-9, float(guide_poly.area))
    center_offset = math.hypot(
        float(poly.centroid.x - guide_poly.centroid.x),
        float(poly.centroid.y - guide_poly.centroid.y),
    )
    inter_area = float(poly.intersection(guide_poly).area)
    union_area = float(poly.union(guide_poly).area)
    iou = inter_area / max(1e-9, union_area)
    return area_ratio, center_offset, iou


def select_section_polygon_with_optional_submesh(
    *,
    ref_mesh: Any,
    base_mesh: Any,
    member_submesh: Optional[Any],
    origin: Any,
    normal: Any,
    x_dir: Any,
    y_dir: Any,
    guide_poly: Optional[Any],
    min_area: float,
    max_center_offset: float,
    min_area_ratio: float,
    max_area_ratio: float,
    prefer_member_submesh: bool = False,
) -> Tuple[Optional[Any], Optional[str], Optional[float], Optional[float], Optional[float]]:
    route_rows: List[Tuple[float, float, float, Any, str]] = []

    if member_submesh is not None:
        try:
            member_polys = section_diff.section_loops_local(member_submesh, origin, normal, x_dir, y_dir, min_area=float(min_area))
            chosen_member = section_diff.select_member_diff_polygon(member_polys, [], guide_poly, min_area=float(min_area))
            if chosen_member is not None and guide_poly is not None:
                area_ratio, center_offset, iou = measure_section_polygon_fit(chosen_member, guide_poly)
                if center_offset <= float(max_center_offset) and float(min_area_ratio) <= area_ratio <= float(max_area_ratio):
                    if bool(prefer_member_submesh):
                        return chosen_member, "member_submesh", area_ratio, center_offset, iou
                    route_rows.append((center_offset, -iou, abs(1.0 - area_ratio), chosen_member, "member_submesh"))
        except Exception:
            pass

    try:
        ref_polys = section_diff.section_loops_local(ref_mesh, origin, normal, x_dir, y_dir, min_area=float(min_area))
        base_polys = section_diff.section_loops_local(base_mesh, origin, normal, x_dir, y_dir, min_area=float(min_area))
        chosen_diff = section_diff.select_member_diff_polygon(ref_polys, base_polys, guide_poly, min_area=float(min_area))
        if chosen_diff is not None and guide_poly is not None:
            area_ratio, center_offset, iou = measure_section_polygon_fit(chosen_diff, guide_poly)
            if center_offset <= float(max_center_offset) and float(min_area_ratio) <= area_ratio <= float(max_area_ratio):
                route_rows.append((center_offset, -iou, abs(1.0 - area_ratio), chosen_diff, "diff"))
    except Exception:
        pass

    if not route_rows:
        return None, None, None, None, None

    route_rows.sort(key=lambda item: (float(item[0]), float(item[1]), float(item[2])))
    _, neg_iou, area_error, chosen_poly, source_name = route_rows[0]
    area_ratio, center_offset, iou = measure_section_polygon_fit(chosen_poly, guide_poly)
    return chosen_poly, source_name, area_ratio, center_offset, iou


def tune_local_section_loop(
    loop_points: Sequence[Tuple[float, float]],
    section_payload: Dict[str, Any],
) -> List[Tuple[float, float]]:
    pts = [(float(x), float(y)) for x, y in loop_points]
    if len(pts) < 4:
        return []
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 8:
        return [(round(float(x), 3), round(float(y), 3)) for x, y in pts]
    xs = [x for x, _ in pts]
    ys = [y for _, y in pts]
    x_min = min(xs)
    x_max = max(xs)
    x_span = max(1e-6, x_max - x_min)
    y_min = min(ys)
    y_max = max(ys)
    y_mid = 0.5 * (y_min + y_max)
    y_span = max(1e-6, y_max - y_min)
    station_ratio = max(0.0, min(1.0, float(section_payload.get("_ls_station_ratio", 0.5) or 0.5)))
    lower_strength = float(section_payload.get("_ls_lower_bias_strength", 0.0) or 0.0)
    lower_mid_start = float(section_payload.get("_ls_lower_bias_mid_start", 0.34) or 0.34)
    lower_mid_end = float(section_payload.get("_ls_lower_bias_mid_end", 0.82) or 0.82)
    upper_strength = float(section_payload.get("_ls_upper_bias_strength", 0.0) or 0.0)
    upper_mid_start = float(section_payload.get("_ls_upper_bias_mid_start", 0.30) or 0.30)
    upper_mid_end = float(section_payload.get("_ls_upper_bias_mid_end", 0.92) or 0.92)
    upper_x_start = float(section_payload.get("_ls_upper_bias_x_start", 0.0) or 0.0)
    upper_x_end = float(section_payload.get("_ls_upper_bias_x_end", 1.0) or 1.0)
    lower_x_start = float(section_payload.get("_ls_lower_bias_x_start", 0.0) or 0.0)
    lower_x_end = float(section_payload.get("_ls_lower_bias_x_end", 1.0) or 1.0)
    lower_auto_flip = bool(section_payload.get("_ls_lower_bias_auto_flip", False))
    root_shift_strength = float(section_payload.get("_ls_root_shift_strength", 0.0) or 0.0)
    root_shift_start = float(section_payload.get("_ls_root_shift_start", 0.0) or 0.0)
    root_shift_end = float(section_payload.get("_ls_root_shift_end", 0.0) or 0.0)
    root_thickness_strength = float(section_payload.get("_ls_root_thickness_strength", 0.0) or 0.0)
    root_thickness_start = float(section_payload.get("_ls_root_thickness_start", 0.0) or 0.0)
    root_thickness_end = float(section_payload.get("_ls_root_thickness_end", 0.0) or 0.0)
    mid_shift_strength = float(section_payload.get("_ls_mid_shift_strength", 0.0) or 0.0)
    mid_shift_start = float(section_payload.get("_ls_mid_shift_start", 0.26) or 0.26)
    mid_shift_end = float(section_payload.get("_ls_mid_shift_end", 0.80) or 0.80)
    mid_thickness_strength = float(section_payload.get("_ls_mid_thickness_strength", 0.0) or 0.0)
    mid_thickness_start = float(section_payload.get("_ls_mid_thickness_start", 0.26) or 0.26)
    mid_thickness_end = float(section_payload.get("_ls_mid_thickness_end", 0.80) or 0.80)
    tail_strength = float(section_payload.get("_ls_tail_thickness_strength", 0.0) or 0.0)
    tail_start = float(section_payload.get("_ls_tail_start_ratio", 0.72) or 0.72)
    planform_strength = float(section_payload.get("_ls_planform_match_strength", 0.0) or 0.0)
    planform_lower = section_payload.get("_ls_planform_x_lower")
    planform_upper = section_payload.get("_ls_planform_x_upper")
    planform_width_only = bool(section_payload.get("_ls_planform_width_only", False))
    planform_expand_only = bool(section_payload.get("_ls_planform_expand_only", False))
    planform_upper_only = bool(section_payload.get("_ls_planform_upper_only", False))
    planform_min_expand_mm = float(section_payload.get("_ls_planform_min_expand_mm", 0.0) or 0.0)
    groove_strength = float(section_payload.get("_ls_groove_strength", 0.0) or 0.0)
    groove_center_x = section_payload.get("_ls_groove_center_x")
    groove_half_width = float(section_payload.get("_ls_groove_half_width", 0.0) or 0.0)
    groove_depth = float(section_payload.get("_ls_groove_depth", 0.0) or 0.0)
    tuned = list(pts)
    if planform_strength > 1e-6 and planform_lower is not None and planform_upper is not None:
        target_lower = float(planform_lower)
        target_upper = float(planform_upper)
        target_width = max(1e-6, target_upper - target_lower)
        source_mid = 0.5 * (x_min + x_max)
        source_width = max(1e-6, x_span)
        if planform_expand_only:
            if target_width <= source_width:
                target_width = source_width + max(0.0, float(planform_min_expand_mm))
            elif planform_min_expand_mm > 1e-6:
                target_width = max(target_width, source_width + float(planform_min_expand_mm))
            if target_width <= source_width + 1e-6:
                target_width = source_width
        gain = max(0.0, min(1.0, float(planform_strength)))
        if planform_upper_only:
            if planform_expand_only:
                target_upper = max(target_upper, x_max + max(0.0, float(planform_min_expand_mm)))
            delta_upper = float(target_upper) - float(x_max)
            matched = []
            for x_val, y_val in tuned:
                x_norm = max(0.0, min(1.0, (float(x_val) - x_min) / x_span))
                x_weight = x_norm ** 1.35
                matched.append((float(x_val) + (delta_upper * gain * x_weight), y_val))
        else:
            target_mid = source_mid if planform_width_only else 0.5 * (target_lower + target_upper)
            width_scale = target_width / x_span
            matched = []
            for x_val, y_val in tuned:
                x_target = target_mid + ((float(x_val) - source_mid) * width_scale)
                x_new = float(x_val) + ((x_target - float(x_val)) * gain)
                matched.append((x_new, y_val))
        tuned = matched
        xs = [x for x, _ in tuned]
        x_min = min(xs)
        x_max = max(xs)
        x_span = max(1e-6, x_max - x_min)
    inferred_rear_side_sign = 1.0
    lower_band_points = [
        (float(x_val), float(y_val))
        for x_val, y_val in tuned
        if ((y_mid - float(y_val)) / y_span) > 0.18
    ]
    if len(lower_band_points) >= 4:
        low_half = [pt for pt in lower_band_points if pt[0] <= (x_min + (0.5 * x_span))]
        high_half = [pt for pt in lower_band_points if pt[0] > (x_min + (0.5 * x_span))]
        if low_half and high_half:
            low_half_mean_y = float(np.mean([pt[1] for pt in low_half]))
            high_half_mean_y = float(np.mean([pt[1] for pt in high_half]))
            inferred_rear_side_sign = (1.0 if high_half_mean_y <= low_half_mean_y else -1.0)
    if abs(lower_strength) > 1e-6 and lower_mid_end > lower_mid_start:
        phase = (station_ratio - lower_mid_start) / max(1e-6, lower_mid_end - lower_mid_start)
        phase = max(0.0, min(1.0, phase))
        gain = float(np.sin(np.pi * phase)) * lower_strength
        if abs(gain) > 1e-6:
            lowered = []
            for x_val, y_val in tuned:
                lower_norm = max(0.0, (y_mid - float(y_val)) / y_span)
                x_norm = (float(x_val) - x_min) / x_span
                if lower_auto_flip and inferred_rear_side_sign < 0.0:
                    x_norm = 1.0 - x_norm
                if x_norm < lower_x_start or x_norm > lower_x_end:
                    lowered.append((x_val, y_val))
                    continue
                x_span_norm = max(1e-6, lower_x_end - lower_x_start)
                x_local = max(0.0, min(1.0, (x_norm - lower_x_start) / x_span_norm))
                x_weight = float(np.sin(0.5 * np.pi * x_local)) ** 1.35
                lowered.append((x_val, y_val - ((gain * y_span) * (lower_norm ** 1.15) * x_weight)))
            tuned = lowered
    if abs(upper_strength) > 1e-6 and upper_mid_end > upper_mid_start:
        phase = (station_ratio - upper_mid_start) / max(1e-6, upper_mid_end - upper_mid_start)
        phase = max(0.0, min(1.0, phase))
        gain = float(np.sin(np.pi * phase)) * upper_strength
        if abs(gain) > 1e-6:
            raised = []
            for x_val, y_val in tuned:
                upper_norm = max(0.0, (float(y_val) - y_mid) / y_span)
                if upper_norm <= 0.10:
                    raised.append((x_val, y_val))
                    continue
                x_norm = (float(x_val) - x_min) / x_span
                if x_norm < upper_x_start or x_norm > upper_x_end:
                    raised.append((x_val, y_val))
                    continue
                x_span_norm = max(1e-6, upper_x_end - upper_x_start)
                x_local = max(0.0, min(1.0, (x_norm - upper_x_start) / x_span_norm))
                x_weight = float(np.sin(0.5 * np.pi * x_local)) ** 1.2
                raised.append((x_val, y_val + ((gain * y_span) * (upper_norm ** 1.15) * x_weight)))
            tuned = raised
    if abs(root_shift_strength) > 1e-6 and root_shift_end > root_shift_start:
        phase = (station_ratio - root_shift_start) / max(1e-6, root_shift_end - root_shift_start)
        phase = max(0.0, min(1.0, phase))
        gain = float(np.sin(np.pi * phase)) * root_shift_strength
        if abs(gain) > 1e-6:
            shift_delta = gain * y_span
            tuned = [(x_val, y_val + shift_delta) for x_val, y_val in tuned]
    if abs(root_thickness_strength) > 1e-6 and root_thickness_end > root_thickness_start:
        phase = (station_ratio - root_thickness_start) / max(1e-6, root_thickness_end - root_thickness_start)
        phase = max(0.0, min(1.0, phase))
        gain = float(np.sin(np.pi * phase)) * root_thickness_strength
        if abs(gain) > 1e-6:
            adjusted = []
            for x_val, y_val in tuned:
                y_rel = float(y_val) - y_mid
                adjusted.append((x_val, y_mid + (y_rel * max(0.35, 1.0 + gain))))
            tuned = adjusted
    if abs(mid_shift_strength) > 1e-6 and mid_shift_end > mid_shift_start:
        phase = (station_ratio - mid_shift_start) / max(1e-6, mid_shift_end - mid_shift_start)
        phase = max(0.0, min(1.0, phase))
        gain = float(np.sin(np.pi * phase)) * mid_shift_strength
        if abs(gain) > 1e-6:
            shift_delta = gain * y_span
            tuned = [(x_val, y_val + shift_delta) for x_val, y_val in tuned]
    if abs(mid_thickness_strength) > 1e-6 and mid_thickness_end > mid_thickness_start:
        phase = (station_ratio - mid_thickness_start) / max(1e-6, mid_thickness_end - mid_thickness_start)
        phase = max(0.0, min(1.0, phase))
        gain = float(np.sin(np.pi * phase)) * mid_thickness_strength
        if abs(gain) > 1e-6:
            thickened = []
            for x_val, y_val in tuned:
                y_rel = float(y_val) - y_mid
                thickened.append((x_val, y_mid + (y_rel * (1.0 + gain))))
            tuned = thickened
    if tail_strength > 1e-6 and station_ratio >= tail_start:
        phase = (station_ratio - tail_start) / max(1e-6, 1.0 - tail_start)
        phase = max(0.0, min(1.0, phase))
        gain = tail_strength * phase
        thickened = []
        for x_val, y_val in tuned:
            y_rel = float(y_val) - y_mid
            side_norm = abs(y_rel) / y_span
            thickened.append((x_val, y_mid + (y_rel * (1.0 + (gain * (side_norm ** 1.1))))))
        tuned = thickened
    if groove_strength > 1e-6 and groove_center_x is not None and groove_half_width > 0.4 and groove_depth > 0.1:
        try:
            center_x = float(groove_center_x)
        except Exception:
            center_x = 0.5 * (x_min + x_max)
        depth = max(0.0, min(0.38 * y_span, groove_depth * max(0.0, min(1.0, groove_strength))))
        if depth > 1e-6:
            grooved = []
            rail_half = max(0.45, min(1.8, groove_half_width * 0.18))
            for x_val, y_val in tuned:
                x_dist = abs(float(x_val) - center_x)
                upper_norm = max(0.0, (float(y_val) - y_mid) / y_span)
                if upper_norm <= 0.18 or x_dist >= groove_half_width:
                    grooved.append((x_val, y_val))
                    continue
                core = max(0.0, 1.0 - (x_dist / max(1e-6, groove_half_width - rail_half)))
                edge_fade = max(0.0, min(1.0, (groove_half_width - x_dist) / max(1e-6, rail_half)))
                notch_weight = max(0.0, min(1.0, core if x_dist <= groove_half_width - rail_half else edge_fade))
                grooved.append((x_val, y_val - (depth * (notch_weight ** 0.55) * (upper_norm ** 0.85))))
            tuned = grooved
    return [(round(float(x), 3), round(float(y), 3)) for x, y in tuned]


def build_local_section_wire(section_payload: Dict[str, Any], loop_points: Sequence[Tuple[float, float]]) -> Optional[Any]:
    plane_origin = section_payload.get("plane_origin") or []
    plane_normal = section_payload.get("plane_normal") or []
    plane_x_dir = section_payload.get("plane_x_dir") or []
    if len(plane_origin) < 3 or len(plane_normal) < 3 or len(plane_x_dir) < 3:
        return None
    try:
        plane = cq.Plane(
            origin=(float(plane_origin[0]), float(plane_origin[1]), float(plane_origin[2])),
            xDir=(float(plane_x_dir[0]), float(plane_x_dir[1]), float(plane_x_dir[2])),
            normal=(float(plane_normal[0]), float(plane_normal[1]), float(plane_normal[2])),
        )
        return cq.Workplane(plane).polyline([(float(x), float(y)) for x, y in loop_points]).close().wires().val()
    except Exception:
        return None


def interpolate_section_payload(
    section_a: Dict[str, Any],
    section_b: Dict[str, Any],
    loop_points: Sequence[Tuple[float, float]],
    ratio: float,
) -> Dict[str, Any]:
    payload = dict(section_b)
    r0 = float(section_a.get("station_r", 0.0))
    r1 = float(section_b.get("station_r", 0.0))
    payload["station_r"] = round(r0 + ((r1 - r0) * float(ratio)), 3)
    origin_a = list(section_a.get("plane_origin") or [])
    origin_b = list(section_b.get("plane_origin") or [])
    if len(origin_a) >= 3 and len(origin_b) >= 3:
        payload["plane_origin"] = [
            round(float(origin_a[idx]) + ((float(origin_b[idx]) - float(origin_a[idx])) * float(ratio)), 3)
            for idx in range(3)
        ]
    normal_a = list(section_a.get("plane_normal") or [])
    normal_b = list(section_b.get("plane_normal") or [])
    if len(normal_a) >= 3 and len(normal_b) >= 3:
        blended_normal = section_diff.normalize(
            np.asarray(
                [
                    float(normal_a[idx]) + ((float(normal_b[idx]) - float(normal_a[idx])) * float(ratio))
                    for idx in range(3)
                ],
                dtype=float,
            ),
            fallback=np.array([0.0, 0.0, 1.0], dtype=float),
        )
        payload["plane_normal"] = [round(float(v), 6) for v in blended_normal]
    x_dir_a = list(section_a.get("plane_x_dir") or [])
    x_dir_b = list(section_b.get("plane_x_dir") or [])
    if len(x_dir_a) >= 3 and len(x_dir_b) >= 3:
        blended_x_dir = section_diff.normalize(
            np.asarray(
                [
                    float(x_dir_a[idx]) + ((float(x_dir_b[idx]) - float(x_dir_a[idx])) * float(ratio))
                    for idx in range(3)
                ],
                dtype=float,
            ),
            fallback=np.array([1.0, 0.0, 0.0], dtype=float),
        )
        payload["plane_x_dir"] = [round(float(v), 6) for v in blended_x_dir]
    payload["points_local"] = [(round(float(x), 3), round(float(y), 3)) for x, y in loop_points]
    payload["_refine_bridge"] = True
    return payload


def build_gap_fill_section_candidate(
    section_a: Dict[str, Any],
    section_b: Dict[str, Any],
    ratio: float,
) -> Optional[Dict[str, Any]]:
    loop_a = section_a.get("points_local") or []
    loop_b = section_b.get("points_local") or []
    if len(loop_a) < 4 or len(loop_b) < 4:
        return None
    canonical_a = canonicalize_local_section_loop(loop_a)
    canonical_b = canonicalize_local_section_loop(loop_b)
    if len(canonical_a) < 4 or len(canonical_b) < 4:
        return None
    sampled_a = resample_closed_loop(canonical_a, target_count=64)
    sampled_b = resample_closed_loop(canonical_b, target_count=64)
    if len(sampled_a) < 12 or len(sampled_b) < 12:
        return None
    sampled_b = align_resampled_loop(sampled_a, sampled_b, allow_reverse=False)
    blended = []
    for pt_a, pt_b in zip(sampled_a, sampled_b):
        blended.append(
            (
                round(float(pt_a[0]) + ((float(pt_b[0]) - float(pt_a[0])) * float(ratio)), 3),
                round(float(pt_a[1]) + ((float(pt_b[1]) - float(pt_a[1])) * float(ratio)), 3),
            )
        )
    payload = interpolate_section_payload(section_a, section_b, blended + [blended[0]], ratio)
    payload["_refine_gap_fill"] = True
    return payload


def inject_gap_fill_sections(
    member_payload: Dict[str, Any],
    ref_mesh: Any,
    base_mesh: Any,
    member_submesh: Optional[Any],
    *,
    min_area: float,
    max_center_offset: float,
    min_area_ratio: float,
    max_area_ratio: float,
    max_gap_mm: float,
    prefer_member_submesh: bool = False,
) -> int:
    max_gap = float(max_gap_mm)
    if max_gap <= 0.0:
        return 0
    source_sections = [sec for sec in (member_payload.get("sections") or []) if isinstance(sec, dict) and float(sec.get("station_r", 0.0)) > 0.0]
    source_sections.sort(key=lambda sec: float(sec.get("station_r", 0.0)))
    if len(source_sections) < 2:
        return 0

    additions: List[Dict[str, Any]] = []
    for section_a, section_b in zip(source_sections[:-1], source_sections[1:]):
        r0 = float(section_a.get("station_r", 0.0))
        r1 = float(section_b.get("station_r", 0.0))
        gap_r = float(r1 - r0)
        if gap_r <= max_gap + 1e-6:
            continue
        fill_count = int(math.floor(gap_r / max_gap))
        if fill_count <= 0:
            continue
        ratios = [(idx + 1) / float(fill_count + 1) for idx in range(fill_count)]
        for ratio in ratios:
            candidate = build_gap_fill_section_candidate(section_a, section_b, ratio)
            if candidate is None:
                continue
            origin = section_diff.as_np3(candidate.get("plane_origin") or [0.0, 0.0, 0.0])
            normal = section_diff.normalize(
                section_diff.as_np3(candidate.get("plane_normal") or [0.0, 0.0, 1.0]),
                fallback=np.array([0.0, 0.0, 1.0]),
            )
            x_dir = section_diff.normalize(
                section_diff.as_np3(candidate.get("plane_x_dir") or [1.0, 0.0, 0.0]),
                fallback=np.array([1.0, 0.0, 0.0]),
            )
            y_dir = section_diff.normalize(np.cross(normal, x_dir), fallback=np.array([0.0, 1.0, 0.0]))
            x_dir = section_diff.normalize(np.cross(y_dir, normal), fallback=x_dir)
            guide_poly = section_diff.local_polygon_from_points(candidate.get("points_local") or [], min_area=0.1)
            chosen, source_name, area_ratio, center_offset, _ = select_section_polygon_with_optional_submesh(
                ref_mesh=ref_mesh,
                base_mesh=base_mesh,
                member_submesh=member_submesh,
                origin=origin,
                normal=normal,
                x_dir=x_dir,
                y_dir=y_dir,
                guide_poly=guide_poly,
                min_area=float(min_area),
                max_center_offset=float(max_center_offset),
                min_area_ratio=float(min_area_ratio),
                max_area_ratio=float(max_area_ratio),
                prefer_member_submesh=bool(prefer_member_submesh),
            )
            if chosen is None or guide_poly is None or source_name is None or area_ratio is None or center_offset is None:
                continue
            pts = section_diff.polygon_to_points_local(chosen)
            if len(pts) < 3:
                continue
            candidate["points_local"] = pts
            candidate["local_width"] = float(max(p[0] for p in pts) - min(p[0] for p in pts))
            candidate["local_height"] = float(max(p[1] for p in pts) - min(p[1] for p in pts))
            candidate["_refine_gap_fill_source"] = str(source_name)
            additions.append(candidate)
    if not additions:
        return 0
    merged_sections = list(source_sections) + additions
    merged_sections.sort(key=lambda sec: float(sec.get("station_r", 0.0)))
    member_payload["sections"] = merged_sections
    return int(len(additions))


def extract_candidate_section_from_mesh(
    *,
    candidate: Dict[str, Any],
    ref_mesh: Any,
    base_mesh: Any,
    member_submesh: Optional[Any],
    min_area: float,
    max_center_offset: float,
    min_area_ratio: float,
    max_area_ratio: float,
    prefer_member_submesh: bool,
) -> Optional[Dict[str, Any]]:
    origin = section_diff.as_np3(candidate.get("plane_origin") or [0.0, 0.0, 0.0])
    normal = section_diff.normalize(
        section_diff.as_np3(candidate.get("plane_normal") or [0.0, 0.0, 1.0]),
        fallback=np.array([0.0, 0.0, 1.0]),
    )
    x_dir = section_diff.normalize(
        section_diff.as_np3(candidate.get("plane_x_dir") or [1.0, 0.0, 0.0]),
        fallback=np.array([1.0, 0.0, 0.0]),
    )
    y_dir = section_diff.normalize(np.cross(normal, x_dir), fallback=np.array([0.0, 1.0, 0.0]))
    x_dir = section_diff.normalize(np.cross(y_dir, normal), fallback=x_dir)
    guide_poly = section_diff.local_polygon_from_points(candidate.get("points_local") or [], min_area=0.1)
    chosen, source_name, area_ratio, center_offset, _ = select_section_polygon_with_optional_submesh(
        ref_mesh=ref_mesh,
        base_mesh=base_mesh,
        member_submesh=member_submesh,
        origin=origin,
        normal=normal,
        x_dir=x_dir,
        y_dir=y_dir,
        guide_poly=guide_poly,
        min_area=float(min_area),
        max_center_offset=float(max_center_offset),
        min_area_ratio=float(min_area_ratio),
        max_area_ratio=float(max_area_ratio),
        prefer_member_submesh=bool(prefer_member_submesh),
    )
    if chosen is None or guide_poly is None or source_name is None or area_ratio is None or center_offset is None:
        return None
    pts = section_diff.polygon_to_points_local(chosen)
    if len(pts) < 3:
        return None
    result = dict(candidate)
    result["points_local"] = pts
    result["local_width"] = float(max(p[0] for p in pts) - min(p[0] for p in pts))
    result["local_height"] = float(max(p[1] for p in pts) - min(p[1] for p in pts))
    result["_refine_section_source"] = str(source_name)
    return result


def inject_dense_resample_sections(
    member_payload: Dict[str, Any],
    ref_mesh: Any,
    base_mesh: Any,
    member_submesh: Optional[Any],
    *,
    min_area: float,
    max_center_offset: float,
    min_area_ratio: float,
    max_area_ratio: float,
    target_spacing_mm: float,
    station_min_gap_mm: float,
    prefer_member_submesh: bool = False,
) -> int:
    spacing = float(target_spacing_mm)
    if spacing <= 0.0:
        return 0
    sections = [sec for sec in (member_payload.get("sections") or []) if isinstance(sec, dict) and float(sec.get("station_r", 0.0)) > 0.0]
    sections.sort(key=lambda sec: float(sec.get("station_r", 0.0)))
    if len(sections) < 2:
        return 0

    min_gap = max(0.5, float(station_min_gap_mm))
    station_values = np.asarray([float(sec.get("station_r", 0.0)) for sec in sections], dtype=float)
    r0 = float(np.min(station_values))
    r1 = float(np.max(station_values))
    if r1 <= r0 + spacing:
        return 0

    target_stations = np.arange(r0 + spacing, r1, spacing, dtype=float)
    if len(target_stations) == 0:
        return 0
    additions: List[Dict[str, Any]] = []
    existing = list(station_values)
    for target_r in target_stations:
        if min(abs(float(target_r) - float(sv)) for sv in existing) < min_gap:
            continue
        section_a: Optional[Dict[str, Any]] = None
        section_b: Optional[Dict[str, Any]] = None
        for left, right in zip(sections[:-1], sections[1:]):
            left_r = float(left.get("station_r", 0.0))
            right_r = float(right.get("station_r", 0.0))
            if left_r <= float(target_r) <= right_r and right_r > left_r + 1e-6:
                section_a = left
                section_b = right
                break
        if section_a is None or section_b is None:
            continue
        left_r = float(section_a.get("station_r", 0.0))
        right_r = float(section_b.get("station_r", 0.0))
        ratio = max(0.0, min(1.0, (float(target_r) - left_r) / max(1e-6, right_r - left_r)))
        candidate = build_gap_fill_section_candidate(section_a, section_b, ratio)
        if candidate is None:
            continue
        extracted = extract_candidate_section_from_mesh(
            candidate=candidate,
            ref_mesh=ref_mesh,
            base_mesh=base_mesh,
            member_submesh=member_submesh,
            min_area=float(min_area),
            max_center_offset=float(max_center_offset),
            min_area_ratio=float(min_area_ratio),
            max_area_ratio=float(max_area_ratio),
            prefer_member_submesh=bool(prefer_member_submesh),
        )
        if extracted is None:
            continue
        extracted["_refine_dense_resample"] = True
        additions.append(extracted)
        existing.append(float(target_r))
    if not additions:
        return 0
    merged = list(sections) + additions
    merged.sort(key=lambda sec: float(sec.get("station_r", 0.0)))
    member_payload["sections"] = merged
    return int(len(additions))


def clone_section_at_station(
    section: Dict[str, Any],
    station_r: float,
    angle_deg: float,
    tag: str,
) -> Optional[Dict[str, Any]]:
    cloned = json.loads(json.dumps(section))
    target_r = float(station_r)
    angle_rad = math.radians(float(angle_deg))
    origin = list(cloned.get("plane_origin") or [])
    if len(origin) < 3:
        return None
    cloned["station_r"] = round(target_r, 3)
    cloned["plane_origin"] = [
        round(math.cos(angle_rad) * target_r, 3),
        round(math.sin(angle_rad) * target_r, 3),
        round(float(origin[2]), 3),
    ]
    cloned["_refine_endpoint_extension"] = str(tag)
    return cloned


def inject_planform_endpoint_sections(
    member_payload: Dict[str, Any],
    planform_profile: Optional[Dict[str, np.ndarray]],
    *,
    angle_deg: float,
    min_gap_mm: float = 1.0,
) -> int:
    if planform_profile is None:
        return 0
    profile_x = np.asarray(planform_profile.get("x"), dtype=float)
    if len(profile_x) < 2:
        return 0
    target_inner = float(np.min(profile_x))
    target_outer = float(np.max(profile_x))
    source_sections = [
        sec
        for section_key in ("sections", "tip_sections")
        for sec in (member_payload.get(section_key) or [])
        if isinstance(sec, dict) and float(sec.get("station_r", 0.0)) > 0.0
    ]
    if len(source_sections) < 2:
        return 0
    source_sections.sort(key=lambda sec: float(sec.get("station_r", 0.0)))
    current_inner = float(source_sections[0].get("station_r", 0.0))
    current_outer = float(source_sections[-1].get("station_r", 0.0))
    additions: List[Dict[str, Any]] = []
    min_gap = max(0.1, float(min_gap_mm))
    if target_inner < current_inner - min_gap:
        cloned = clone_section_at_station(source_sections[0], target_inner, angle_deg, "inner_planform")
        if cloned is not None:
            additions.append(cloned)
    if target_outer > current_outer + min_gap:
        cloned = clone_section_at_station(source_sections[-1], target_outer, angle_deg, "outer_planform")
        if cloned is not None:
            additions.append(cloned)
    if not additions:
        return 0
    merged = [
        sec
        for sec in (member_payload.get("sections") or [])
        if isinstance(sec, dict) and float(sec.get("station_r", 0.0)) > 0.0
    ]
    merged.extend(additions)
    merged.sort(key=lambda sec: float(sec.get("station_r", 0.0)))
    member_payload["sections"] = merged
    return int(len(additions))


def section_local_y_bounds(section: Dict[str, Any]) -> Optional[Tuple[float, float, float]]:
    pts = section.get("points_local") or []
    ys = [float(pt[1]) for pt in pts if isinstance(pt, (list, tuple)) and len(pt) >= 2]
    if len(ys) < 3:
        return None
    y_min = float(min(ys))
    y_max = float(max(ys))
    return y_min, y_max, 0.5 * (y_min + y_max)


def repair_tail_z_outlier_sections(
    member_payload: Dict[str, Any],
    *,
    drop_threshold_mm: float = 18.0,
    tail_start_ratio: float = 0.72,
) -> int:
    rows: List[Tuple[float, str, int, Dict[str, Any], Tuple[float, float, float]]] = []
    for section_key in ("sections", "tip_sections"):
        for idx, section in enumerate(member_payload.get(section_key) or []):
            if not isinstance(section, dict):
                continue
            station_r = float(section.get("station_r", 0.0))
            bounds = section_local_y_bounds(section)
            if station_r <= 0.0 or bounds is None:
                continue
            rows.append((station_r, section_key, idx, section, bounds))
    if len(rows) < 3:
        return 0
    rows.sort(key=lambda row: row[0])
    station_values = [row[0] for row in rows]
    station_min = float(min(station_values))
    station_max = float(max(station_values))
    station_span = max(1e-6, station_max - station_min)
    repaired = 0
    stable_section: Optional[Dict[str, Any]] = None
    stable_bounds: Optional[Tuple[float, float, float]] = None
    for station_r, section_key, idx, section, bounds in rows:
        ratio = (float(station_r) - station_min) / station_span
        if stable_section is None or stable_bounds is None:
            stable_section = section
            stable_bounds = bounds
            continue
        y_min, y_max, y_mid = bounds
        _stable_min, stable_max, stable_mid = stable_bounds
        is_tail = ratio >= float(tail_start_ratio)
        dropped_mid = y_mid < stable_mid - float(drop_threshold_mm)
        dropped_top = y_max < stable_max - (0.65 * float(drop_threshold_mm))
        if is_tail and dropped_mid and dropped_top:
            repaired_section = json.loads(json.dumps(stable_section))
            original_origin = list(section.get("plane_origin") or [])
            repaired_section["station_r"] = round(float(station_r), 3)
            if len(original_origin) >= 3:
                repaired_section["plane_origin"] = [
                    round(float(original_origin[0]), 3),
                    round(float(original_origin[1]), 3),
                    round(float(original_origin[2]), 3),
                ]
            repaired_section["_refine_tail_z_repair"] = {
                "from_station_r": float(stable_section.get("station_r", 0.0)),
                "bad_mid_y": float(y_mid),
                "stable_mid_y": float(stable_mid),
            }
            member_payload[section_key][idx] = repaired_section
            repaired += 1
            continue
        stable_section = section
        stable_bounds = bounds
    return int(repaired)


def build_direct_section_refine_body(
    member_payload: Dict[str, Any],
    lower_strength: float,
    upper_strength: float,
    tail_strength: float,
    tail_start: float,
    root_shift_strength: float,
    root_shift_start: float,
    root_shift_end: float,
    root_thickness_strength: float,
    root_thickness_start: float,
    root_thickness_end: float,
    mid_shift_strength: float,
    mid_thickness_strength: float,
    lower_mid_start: float,
    lower_mid_end: float,
    upper_mid_start: float,
    upper_mid_end: float,
    mid_shift_start: float,
    mid_shift_end: float,
    mid_thickness_start: float,
    mid_thickness_end: float,
    lower_x_start: float,
    lower_x_end: float,
    upper_x_start: float,
    upper_x_end: float,
    lower_auto_flip: bool,
    tip_bridge_mode: str = "default",
    tip_bridge_ratio: float = 0.72,
) -> Any:
    patched_member = enrich_shape_tune_sections(
        json.loads(json.dumps(member_payload)),
        lower_strength=float(lower_strength),
        upper_strength=float(upper_strength),
        tail_strength=float(tail_strength),
        tail_start=float(tail_start),
        root_shift_strength=float(root_shift_strength),
        root_shift_start=float(root_shift_start),
        root_shift_end=float(root_shift_end),
        root_thickness_strength=float(root_thickness_strength),
        root_thickness_start=float(root_thickness_start),
        root_thickness_end=float(root_thickness_end),
        mid_shift_strength=float(mid_shift_strength),
        mid_thickness_strength=float(mid_thickness_strength),
        lower_mid_start=float(lower_mid_start),
        lower_mid_end=float(lower_mid_end),
        upper_mid_start=float(upper_mid_start),
        upper_mid_end=float(upper_mid_end),
        mid_shift_start=float(mid_shift_start),
        mid_shift_end=float(mid_shift_end),
        mid_thickness_start=float(mid_thickness_start),
        mid_thickness_end=float(mid_thickness_end),
        lower_x_start=float(lower_x_start),
        lower_x_end=float(lower_x_end),
        upper_x_start=float(upper_x_start),
        upper_x_end=float(upper_x_end),
        lower_auto_flip=bool(lower_auto_flip),
    )
    section_entries: List[Dict[str, Any]] = []
    prev_sampled: Optional[List[Tuple[float, float]]] = None
    for source_name in ("sections", "tip_sections"):
        for section in sorted(
            [sec for sec in (patched_member.get(source_name) or []) if isinstance(sec, dict) and float(sec.get("station_r", 0.0)) > 0.0],
            key=lambda sec: float(sec.get("station_r", 0.0)),
        ):
            loop_points = section.get("points_local") or []
            if len(loop_points) < 4:
                continue
            tuned = tune_local_section_loop(loop_points, section)
            canonical = canonicalize_local_section_loop(tuned)
            if len(canonical) < 4:
                continue
            sampled = resample_closed_loop(canonical, target_count=64)
            if len(sampled) < 12:
                continue
            if prev_sampled is not None:
                sampled = align_resampled_loop(prev_sampled, sampled, allow_reverse=False)
            sampled_closed = list(sampled) + [sampled[0]]
            section_clone = dict(section)
            section_clone["_refine_section_source"] = source_name
            section_clone["points_local"] = sampled_closed
            if source_name == "tip_sections":
                section_clone["terminal_contact"] = True
            section_entries.append(section_clone)
            prev_sampled = list(sampled)
    if len(section_entries) < 3:
        raise RuntimeError("not enough refine sections")

    bridged_sections: List[Dict[str, Any]] = []
    for idx, section in enumerate(section_entries):
        bridged_sections.append(section)
        if idx >= len(section_entries) - 1:
            continue
        next_section = section_entries[idx + 1]
        r0 = float(section.get("station_r", 0.0))
        r1 = float(next_section.get("station_r", 0.0))
        gap_r = float(r1 - r0)
        source_a = str(section.get("_refine_section_source") or "")
        source_b = str(next_section.get("_refine_section_source") or "")
        bridge_ratios: List[float] = []
        next_is_tip = source_b == "tip_sections" or bool(next_section.get("terminal_contact"))
        if next_is_tip and str(tip_bridge_mode) == "none":
            bridge_ratios = []
        elif next_is_tip and str(tip_bridge_mode) == "late":
            bridge_ratios = [max(0.05, min(0.95, float(tip_bridge_ratio)))]
        elif source_a != source_b:
            bridge_ratios = [0.5]
        if gap_r > 10.0 and not next_is_tip:
            bridge_ratios = [0.33, 0.66]
        elif gap_r > 6.0 and not bridge_ratios:
            bridge_ratios = [0.5]
        if not bridge_ratios:
            continue
        loop_a = list(section.get("points_local") or [])
        loop_b = list(next_section.get("points_local") or [])
        if len(loop_a) < 8 or len(loop_b) < 8:
            continue
        samples_a = loop_a[:-1]
        samples_b = align_resampled_loop(samples_a, loop_b[:-1], allow_reverse=False)
        for ratio in bridge_ratios:
            blended = []
            for pt_a, pt_b in zip(samples_a, samples_b):
                blended.append(
                    (
                        round(float(pt_a[0]) + ((float(pt_b[0]) - float(pt_a[0])) * float(ratio)), 3),
                        round(float(pt_a[1]) + ((float(pt_b[1]) - float(pt_a[1])) * float(ratio)), 3),
                    )
                )
            bridge_payload = interpolate_section_payload(section, next_section, blended + [blended[0]], ratio)
            bridged_sections.append(bridge_payload)

    bridged_sections.sort(key=lambda sec: float(sec.get("station_r", 0.0)))
    wires: List[Any] = []
    for section in bridged_sections:
        loop_points = section.get("points_local") or []
        wire = build_local_section_wire(section, loop_points)
        if wire is not None:
            wires.append(wire)
    if len(wires) < 3:
        raise RuntimeError("not enough refine wires")

    for ruled in (False, True):
        try:
            solid = cq.Solid.makeLoft(wires, ruled=ruled)
            valid = section_diff.filter_valid_export_shapes([solid], f"refine direct {'ruled' if ruled else 'smooth'}")
            if valid:
                return valid[0]
        except Exception:
            continue

    segment_solids: List[Any] = []
    for wire_a, wire_b in zip(wires[:-1], wires[1:]):
        built = False
        for ruled in (False, True):
            try:
                segment_solids.append(cq.Solid.makeLoft([wire_a, wire_b], ruled=ruled))
                built = True
                break
            except Exception:
                continue
        if not built:
            continue
    valid_segments = section_diff.filter_valid_export_shapes(segment_solids, "refine direct pairwise")
    if not valid_segments:
        raise RuntimeError("refine pairwise loft failed")
    return valid_segments[0] if len(valid_segments) == 1 else cq.Compound.makeCompound(valid_segments)


def enrich_shape_tune_sections(
    generated_member: Dict[str, Any],
    lower_strength: float,
    upper_strength: float,
    tail_strength: float,
    tail_start: float,
    root_shift_strength: float,
    root_shift_start: float,
    root_shift_end: float,
    root_thickness_strength: float,
    root_thickness_start: float,
    root_thickness_end: float,
    mid_shift_strength: float,
    mid_thickness_strength: float,
    lower_mid_start: float,
    lower_mid_end: float,
    upper_mid_start: float,
    upper_mid_end: float,
    mid_shift_start: float,
    mid_shift_end: float,
    mid_thickness_start: float,
    mid_thickness_end: float,
    lower_x_start: float,
    lower_x_end: float,
    upper_x_start: float,
    upper_x_end: float,
    lower_auto_flip: bool,
) -> Dict[str, Any]:
    section_pool = []
    for section_key in ("sections", "tip_sections"):
        section_pool.extend([
            section
            for section in (generated_member.get(section_key, []) or [])
            if isinstance(section, dict)
        ])
    station_values = [
        float(section.get("station_r", 0.0))
        for section in section_pool
        if float(section.get("station_r", 0.0)) > 0.0
    ]
    if station_values:
        station_min = min(station_values)
        station_max = max(station_values)
        station_span = max(1e-6, station_max - station_min)
    else:
        station_min = 0.0
        station_span = 1.0
    tuned_member = dict(generated_member)
    for section_key in ("sections", "tip_sections"):
        tuned_sections = []
        for section in tuned_member.get(section_key, []) or []:
            if not isinstance(section, dict):
                tuned_sections.append(section)
                continue
            cloned = dict(section)
            station_r = float(cloned.get("station_r", 0.0))
            station_ratio = (station_r - station_min) / station_span if station_r > 0.0 else 0.0
            station_ratio = max(0.0, min(1.0, station_ratio))
            cloned["_ls_station_ratio"] = station_ratio
            cloned["_ls_lower_bias_strength"] = float(lower_strength)
            cloned["_ls_lower_bias_mid_start"] = float(lower_mid_start)
            cloned["_ls_lower_bias_mid_end"] = float(lower_mid_end)
            cloned["_ls_upper_bias_strength"] = float(upper_strength)
            cloned["_ls_upper_bias_mid_start"] = float(upper_mid_start)
            cloned["_ls_upper_bias_mid_end"] = float(upper_mid_end)
            cloned["_ls_lower_bias_x_start"] = float(lower_x_start)
            cloned["_ls_lower_bias_x_end"] = float(lower_x_end)
            cloned["_ls_upper_bias_x_start"] = float(upper_x_start)
            cloned["_ls_upper_bias_x_end"] = float(upper_x_end)
            cloned["_ls_lower_bias_auto_flip"] = bool(lower_auto_flip)
            cloned["_ls_lower_bias_mid_focus"] = 0.58
            cloned["_ls_lower_bias_post_scale"] = 0.65
            cloned["_ls_root_shift_strength"] = float(root_shift_strength)
            cloned["_ls_root_shift_start"] = float(root_shift_start)
            cloned["_ls_root_shift_end"] = float(root_shift_end)
            cloned["_ls_root_thickness_strength"] = float(root_thickness_strength)
            cloned["_ls_root_thickness_start"] = float(root_thickness_start)
            cloned["_ls_root_thickness_end"] = float(root_thickness_end)
            cloned["_ls_mid_shift_strength"] = float(mid_shift_strength)
            cloned["_ls_mid_shift_start"] = float(mid_shift_start)
            cloned["_ls_mid_shift_end"] = float(mid_shift_end)
            cloned["_ls_mid_thickness_strength"] = float(mid_thickness_strength)
            cloned["_ls_mid_thickness_start"] = float(mid_thickness_start)
            cloned["_ls_mid_thickness_end"] = float(mid_thickness_end)
            cloned["_ls_tail_thickness_strength"] = float(tail_strength)
            cloned["_ls_tail_start_ratio"] = float(tail_start)
            cloned["_ls_tail_x_start"] = 0.0
            cloned["_ls_tail_x_end"] = 1.0
            cloned["_ls_tail_auto_flip"] = True
            tuned_sections.append(cloned)
        tuned_member[section_key] = tuned_sections
    return tuned_member


def apply_visual_groove_section_tags(
    member_payload: Dict[str, Any],
    visual_constraint_row: Optional[Dict[str, Any]],
    depth_scale: float,
    max_depth_mm: float,
    width_scale: float,
    edge_fade_mm: float,
) -> int:
    if not isinstance(visual_constraint_row, dict):
        return 0
    station_values = [
        float(section.get("station_r", 0.0))
        for section_key in ("sections", "tip_sections")
        for section in (member_payload.get(section_key) or [])
        if isinstance(section, dict) and float(section.get("station_r", 0.0)) > 0.0
    ]
    if not station_values:
        return 0
    station_min = min(station_values)
    station_max = max(station_values)
    tagged = 0
    for section_key in ("sections", "tip_sections"):
        for section in member_payload.get(section_key) or []:
            if not isinstance(section, dict):
                continue
            params = visual_groove_params_from_constraint(
                visual_constraint_row,
                station_r=float(section.get("station_r", 0.0)),
                station_min=float(station_min),
                station_max=float(station_max),
                depth_scale=float(depth_scale),
                max_depth_mm=float(max_depth_mm),
                width_scale=float(width_scale),
                edge_fade_mm=float(edge_fade_mm),
            )
            if params is None:
                continue
            section["_ls_groove_strength"] = float(params["strength"])
            section["_ls_groove_center_x"] = float(params["center_x"])
            section["_ls_groove_half_width"] = float(params["half_width"])
            section["_ls_groove_depth"] = float(params["depth"])
            tagged += 1
    return int(tagged)


def build_refine_reference_body(
    features: Dict[str, Any],
    motif_payload: Dict[str, Any],
    member_payload: Dict[str, Any],
    ref_mesh: Any,
    base_mesh: Any,
    member_submesh: Optional[Any],
    min_area: float,
    max_center_offset: float,
    min_area_ratio: float,
    max_area_ratio: float,
    gap_fill_mm: float,
    dense_resample_spacing_mm: float,
    dense_resample_min_gap_mm: float,
    lower_strength: float,
    upper_strength: float,
    tail_strength: float,
    tail_start: float,
    root_shift_strength: float,
    root_shift_start: float,
    root_shift_end: float,
    root_thickness_strength: float,
    root_thickness_start: float,
    root_thickness_end: float,
    mid_shift_strength: float,
    mid_thickness_strength: float,
    lower_mid_start: float,
    lower_mid_end: float,
    upper_mid_start: float,
    upper_mid_end: float,
    mid_shift_start: float,
    mid_shift_end: float,
    mid_thickness_start: float,
    mid_thickness_end: float,
    lower_x_start: float,
    lower_x_end: float,
    upper_x_start: float,
    upper_x_end: float,
    lower_auto_flip: bool,
    planform_profile: Optional[Dict[str, np.ndarray]] = None,
    planform_match_strength: float = 0.0,
    planform_match_start: float = 0.0,
    planform_match_end: float = 1.0,
    planform_width_only: bool = False,
    planform_expand_only: bool = False,
    planform_upper_only: bool = False,
    planform_min_expand_mm: float = 0.0,
    repair_tail_z_outliers: bool = False,
    tail_z_drop_threshold_mm: float = 18.0,
    tip_bridge_mode: str = "default",
    tip_bridge_ratio: float = 0.72,
    prefer_member_submesh_sections: bool = False,
) -> Tuple[Any, int]:
    del features
    del motif_payload

    patched_member = json.loads(json.dumps(member_payload))
    replaced = 0
    for section_key in ("sections", "tip_sections"):
        for sec in patched_member.get(section_key) or []:
            if not isinstance(sec, dict):
                continue
            origin = section_diff.as_np3(sec.get("plane_origin") or [0.0, 0.0, 0.0])
            normal = section_diff.normalize(
                section_diff.as_np3(sec.get("plane_normal") or [0.0, 0.0, 1.0]),
                fallback=np.array([0.0, 0.0, 1.0]),
            )
            x_dir = section_diff.normalize(
                section_diff.as_np3(sec.get("plane_x_dir") or [1.0, 0.0, 0.0]),
                fallback=np.array([1.0, 0.0, 0.0]),
            )
            y_dir = section_diff.normalize(np.cross(normal, x_dir), fallback=np.array([0.0, 1.0, 0.0]))
            x_dir = section_diff.normalize(np.cross(y_dir, normal), fallback=x_dir)
            guide_poly = section_diff.local_polygon_from_points(sec.get("points_local") or [], min_area=0.1)
            chosen, source_name, area_ratio, center_offset, _ = select_section_polygon_with_optional_submesh(
                ref_mesh=ref_mesh,
                base_mesh=base_mesh,
                member_submesh=member_submesh,
                origin=origin,
                normal=normal,
                x_dir=x_dir,
                y_dir=y_dir,
                guide_poly=guide_poly,
                min_area=float(min_area),
                max_center_offset=float(max_center_offset),
                min_area_ratio=float(min_area_ratio),
                max_area_ratio=float(max_area_ratio),
                prefer_member_submesh=bool(prefer_member_submesh_sections),
            )
            if chosen is None or guide_poly is None or source_name is None or area_ratio is None or center_offset is None:
                continue
            pts = section_diff.polygon_to_points_local(chosen)
            if len(pts) < 3:
                continue
            sec["points_local"] = pts
            sec["local_width"] = float(max(p[0] for p in pts) - min(p[0] for p in pts))
            sec["local_height"] = float(max(p[1] for p in pts) - min(p[1] for p in pts))
            sec["_refine_section_source"] = str(source_name)
            replaced += 1
    gap_filled = inject_gap_fill_sections(
        patched_member,
        ref_mesh,
        base_mesh,
        member_submesh,
        min_area=float(min_area),
        max_center_offset=float(max_center_offset),
        min_area_ratio=float(min_area_ratio),
        max_area_ratio=float(max_area_ratio),
        max_gap_mm=float(gap_fill_mm),
        prefer_member_submesh=bool(prefer_member_submesh_sections),
    )
    dense_filled = inject_dense_resample_sections(
        patched_member,
        ref_mesh,
        base_mesh,
        member_submesh,
        min_area=float(min_area),
        max_center_offset=float(max_center_offset),
        min_area_ratio=float(min_area_ratio),
        max_area_ratio=float(max_area_ratio),
        target_spacing_mm=float(dense_resample_spacing_mm),
        station_min_gap_mm=float(dense_resample_min_gap_mm),
        prefer_member_submesh=bool(prefer_member_submesh_sections),
    )
    z_repaired = 0
    if bool(repair_tail_z_outliers):
        z_repaired = repair_tail_z_outlier_sections(
            patched_member,
            drop_threshold_mm=float(tail_z_drop_threshold_mm),
            tail_start_ratio=float(tail_start),
        )
    endpoint_filled = inject_planform_endpoint_sections(
        patched_member,
        planform_profile,
        angle_deg=float(member_payload.get("angle", 0.0)),
        min_gap_mm=float(dense_resample_min_gap_mm),
    )
    visual_groove_tagged = 0
    if planform_profile is not None and float(planform_match_strength) > 1e-6:
        station_values = [
            float(sec.get("station_r", 0.0))
            for section_key in ("sections", "tip_sections")
            for sec in (patched_member.get(section_key) or [])
            if isinstance(sec, dict) and float(sec.get("station_r", 0.0)) > 0.0
        ]
        station_min = min(station_values) if station_values else 0.0
        station_max = max(station_values) if station_values else 1.0
        station_span = max(1e-6, station_max - station_min)
        for section_key in ("sections", "tip_sections"):
            for sec in patched_member.get(section_key) or []:
                if not isinstance(sec, dict):
                    continue
                station_r = float(sec.get("station_r", 0.0))
                if station_r <= 0.0:
                    continue
                bounds = planform_profile_bounds_at(planform_profile, station_r)
                if bounds is None:
                    continue
                ratio = max(0.0, min(1.0, (station_r - station_min) / station_span))
                start = float(planform_match_start)
                end = float(planform_match_end)
                if end <= start:
                    local_gain = float(planform_match_strength)
                else:
                    phase = max(0.0, min(1.0, (ratio - start) / max(1e-6, end - start)))
                    local_gain = float(planform_match_strength) * float(np.sin(np.pi * phase))
                if local_gain <= 1e-6:
                    continue
                sec["_ls_planform_x_lower"] = float(bounds[0])
                sec["_ls_planform_x_upper"] = float(bounds[1])
                sec["_ls_planform_match_strength"] = float(max(0.0, min(1.0, local_gain)))
                sec["_ls_planform_width_only"] = bool(planform_width_only)
                sec["_ls_planform_expand_only"] = bool(planform_expand_only)
                sec["_ls_planform_upper_only"] = bool(planform_upper_only)
                sec["_ls_planform_min_expand_mm"] = float(planform_min_expand_mm)
    visual_constraint_row = member_payload.get("_visual_constraint_row")
    if isinstance(visual_constraint_row, dict) and bool(member_payload.get("_apply_visual_section_groove")):
        visual_groove_tagged = apply_visual_groove_section_tags(
            patched_member,
            visual_constraint_row,
            depth_scale=float(member_payload.get("_visual_section_groove_depth_scale", 0.22) or 0.22),
            max_depth_mm=float(member_payload.get("_visual_section_groove_max_depth_mm", 1.8) or 1.8),
            width_scale=float(member_payload.get("_visual_section_groove_width_scale", 0.42) or 0.42),
            edge_fade_mm=float(member_payload.get("_visual_section_groove_edge_fade_mm", 5.0) or 5.0),
        )
    refine_shape = build_direct_section_refine_body(
        patched_member,
        lower_strength=float(lower_strength),
        upper_strength=float(upper_strength),
        tail_strength=float(tail_strength),
        tail_start=float(tail_start),
        root_shift_strength=float(root_shift_strength),
        root_shift_start=float(root_shift_start),
        root_shift_end=float(root_shift_end),
        root_thickness_strength=float(root_thickness_strength),
        root_thickness_start=float(root_thickness_start),
        root_thickness_end=float(root_thickness_end),
        mid_shift_strength=float(mid_shift_strength),
        mid_thickness_strength=float(mid_thickness_strength),
        lower_mid_start=float(lower_mid_start),
        lower_mid_end=float(lower_mid_end),
        upper_mid_start=float(upper_mid_start),
        upper_mid_end=float(upper_mid_end),
        mid_shift_start=float(mid_shift_start),
        mid_shift_end=float(mid_shift_end),
        mid_thickness_start=float(mid_thickness_start),
        mid_thickness_end=float(mid_thickness_end),
        lower_x_start=float(lower_x_start),
        lower_x_end=float(lower_x_end),
        upper_x_start=float(upper_x_start),
        upper_x_end=float(upper_x_end),
        lower_auto_flip=bool(lower_auto_flip),
        tip_bridge_mode=str(tip_bridge_mode),
        tip_bridge_ratio=float(tip_bridge_ratio),
    )
    refine_shape = valid_single_shape(refine_shape, "refine body")
    return refine_shape, int(replaced + gap_filled + dense_filled + z_repaired + endpoint_filled + visual_groove_tagged)


def build_template_shape(
    features: Dict[str, Any],
    motif_payload: Dict[str, Any],
    member_payload: Dict[str, Any],
    ref_mesh: Any,
    base_mesh: Any,
    member_submesh: Optional[Any],
    base_bbox: Tuple[float, float, float, float, float, float],
    args: argparse.Namespace,
) -> Tuple[Any, Dict[str, Any]]:
    silhouette_poly = side_model.positive_meridional_diff_polygon(
        ref_mesh,
        base_mesh,
        member_payload,
        min_area=float(args.min_area),
    )
    if silhouette_poly is None:
        raise RuntimeError("template silhouette extraction failed")

    band_samples = side_model.extract_section_band_samples(
        ref_mesh,
        base_mesh,
        member_payload,
        min_area=float(args.min_area),
        max_center_offset=float(args.max_center_offset),
        min_area_ratio=float(args.min_area_ratio),
        max_area_ratio=float(args.max_area_ratio),
    )
    if not band_samples:
        raise RuntimeError("template width sampling failed")

    base_width = choose_base_width(
        band_samples,
        mode=str(args.base_width_mode),
        scale=float(args.base_width_scale),
    )
    template_angle = float(member_payload.get("angle", 0.0))
    base_solid = build_extrude_from_silhouette(
        silhouette_poly,
        angle_deg=template_angle,
        total_width=float(base_width),
        face_mode=str(args.face_mode),
        root_pad_mm=float(args.base_root_pad_mm),
        tip_pad_mm=float(args.base_tip_pad_mm),
        profile_mode=str(args.base_profile_mode),
        rect_z_margin_mm=float(args.base_rect_z_margin_mm),
    )
    base_solid = valid_single_shape(base_solid, "base extrude")

    planform_profile: Optional[Dict[str, np.ndarray]] = None
    planform_profile_meta: Dict[str, Any] = {"status": "disabled"}
    visual_constraint_row = visual_constraint_for_member(
        getattr(args, "visual_constraints_payload", None),
        int(member_payload.get("member_index", -1)),
    )
    build_member_payload = member_payload
    section_groove_enabled = (
        bool(args.use_visual_constraints)
        and bool(args.apply_visual_section_groove)
        and visual_constraint_row is not None
    )
    if section_groove_enabled:
        build_member_payload = dict(member_payload)
        build_member_payload["_visual_constraint_row"] = visual_constraint_row
        build_member_payload["_apply_visual_section_groove"] = True
        build_member_payload["_visual_section_groove_depth_scale"] = float(args.visual_section_groove_depth_scale)
        build_member_payload["_visual_section_groove_max_depth_mm"] = float(args.visual_section_groove_max_depth_mm)
        build_member_payload["_visual_section_groove_width_scale"] = float(args.visual_section_groove_width_scale)
        build_member_payload["_visual_section_groove_edge_fade_mm"] = float(args.visual_section_groove_edge_fade_mm)
    if bool(args.use_visual_constraints) and visual_constraint_row is not None:
        planform_profile, planform_profile_meta = planform_profile_from_visual_constraint(visual_constraint_row)
    elif bool(args.refine_planform_match):
        planform_profile, planform_profile_meta = extract_member_planform_profile(
            member_submesh,
            member_payload,
            margin_mm=float(args.planform_margin_mm),
            bins=int(args.planform_bins),
            lower_percentile=float(args.planform_lower_percentile),
            upper_percentile=float(args.planform_upper_percentile),
            min_width_mm=float(args.planform_min_width_mm),
            span_mode=str(args.planform_span_mode),
            span_root_margin_mm=float(args.planform_span_root_margin_mm),
            span_tip_margin_mm=float(args.planform_span_tip_margin_mm),
            full_span_percentile=float(args.planform_full_span_percentile),
        )
    if planform_profile is not None:
        planform_profile = extend_planform_profile_edges(
            planform_profile,
            root_pad_mm=float(args.planform_root_pad_mm),
            tip_pad_mm=float(args.planform_tip_pad_mm),
            root_expand_mm=float(args.planform_root_expand_mm),
            tip_expand_mm=float(args.planform_tip_expand_mm),
            steps=int(args.planform_extension_steps),
        )
        planform_profile_meta = dict(planform_profile_meta)
        planform_profile_meta["root_pad_mm"] = float(args.planform_root_pad_mm)
        planform_profile_meta["tip_pad_mm"] = float(args.planform_tip_pad_mm)
        planform_profile_meta["root_expand_mm"] = float(args.planform_root_expand_mm)
        planform_profile_meta["tip_expand_mm"] = float(args.planform_tip_expand_mm)
        planform_profile_meta["extension_steps"] = int(args.planform_extension_steps)

    refine_body, replaced = build_refine_reference_body(
        features,
        motif_payload,
        build_member_payload,
        ref_mesh,
        base_mesh,
        member_submesh,
        min_area=float(args.min_area),
        max_center_offset=float(args.max_center_offset),
        min_area_ratio=float(args.min_area_ratio),
        max_area_ratio=float(args.max_area_ratio),
        gap_fill_mm=float(args.refine_gap_fill_mm),
        dense_resample_spacing_mm=float(args.refine_dense_spacing_mm),
        dense_resample_min_gap_mm=float(args.refine_dense_min_gap_mm),
        lower_strength=float(args.refine_lower_strength),
        upper_strength=float(args.refine_upper_strength),
        tail_strength=float(args.refine_tail_strength),
        tail_start=float(args.refine_tail_start),
        root_shift_strength=float(args.refine_root_shift_strength),
        root_shift_start=float(args.refine_root_shift_start),
        root_shift_end=float(args.refine_root_shift_end),
        root_thickness_strength=float(args.refine_root_thickness_strength),
        root_thickness_start=float(args.refine_root_thickness_start),
        root_thickness_end=float(args.refine_root_thickness_end),
        mid_shift_strength=float(args.refine_mid_shift_strength),
        mid_thickness_strength=float(args.refine_mid_thickness_strength),
        lower_mid_start=float(args.refine_lower_mid_start),
        lower_mid_end=float(args.refine_lower_mid_end),
        upper_mid_start=float(args.refine_upper_mid_start),
        upper_mid_end=float(args.refine_upper_mid_end),
        mid_shift_start=float(args.refine_mid_shift_start),
        mid_shift_end=float(args.refine_mid_shift_end),
        mid_thickness_start=float(args.refine_mid_thickness_start),
        mid_thickness_end=float(args.refine_mid_thickness_end),
        lower_x_start=float(args.refine_lower_x_start),
        lower_x_end=float(args.refine_lower_x_end),
        upper_x_start=float(args.refine_upper_x_start),
        upper_x_end=float(args.refine_upper_x_end),
        lower_auto_flip=bool(args.refine_lower_auto_flip),
        planform_profile=planform_profile,
        planform_match_strength=float(args.refine_planform_match_strength),
        planform_match_start=float(args.refine_planform_match_start),
        planform_match_end=float(args.refine_planform_match_end),
        planform_width_only=bool(args.refine_planform_width_only),
        planform_expand_only=bool(args.refine_planform_expand_only),
        planform_upper_only=bool(args.refine_planform_upper_only),
        planform_min_expand_mm=float(args.refine_planform_min_expand_mm),
        repair_tail_z_outliers=bool(args.repair_tail_z_outliers),
        tail_z_drop_threshold_mm=float(args.tail_z_drop_threshold_mm),
        tip_bridge_mode=str(args.tip_bridge_mode),
        tip_bridge_ratio=float(args.tip_bridge_ratio),
        prefer_member_submesh_sections=bool(args.prefer_member_submesh_sections),
    )
    refine_body = valid_single_shape(refine_body, "refine reference")

    sb = silhouette_poly.bounds
    r0 = float(sb[0])
    r1 = float(sb[2])
    z0 = float(base_bbox[4] - 20.0)
    z1 = float(base_bbox[5] + 20.0)
    section_r0, section_r1 = member_section_station_span(member_payload)

    root_keep_r = float(r0 + float(args.root_keep_ratio) * max(1e-6, r1 - r0))
    transition_keep_r = min(float(r1), float(root_keep_r + float(args.transition_keep_width)))
    refine_inner_r = float(transition_keep_r)
    trim_outer_r = float(r1 + 25.0)
    tip_shell_start_r: Optional[float] = None
    if bool(args.keep_tip_shell):
        tip_shell_start_r = float(r0 + float(args.tip_keep_ratio) * max(1e-6, r1 - r0))

    root_part: Optional[Any] = None
    transition_part: Optional[Any] = None
    if str(args.refine_span_mode) == "planform_full" and planform_profile is not None:
        profile_x = np.asarray(planform_profile.get("x"), dtype=float)
        if len(profile_x) >= 2:
            refine_inner_r = max(
                0.0,
                min(
                    float(np.min(profile_x)),
                    float(planform_profile.get("radial_r0", float(np.min(profile_x)))),
                    float(planform_profile.get("profile_radial_r0", float(np.min(profile_x)))),
                ),
            )
            trim_outer_r = max(
                float(refine_inner_r) + 1.0,
                float(planform_profile.get("radial_r1", float(np.max(profile_x)))),
                float(planform_profile.get("profile_radial_r1", float(np.max(profile_x)))),
            )
        if refine_inner_r > 1e-6:
            root_clip = build_radial_clip_solid(z0=z0, z1=z1, outer_r=float(refine_inner_r))
            root_part = valid_single_shape(base_solid.intersect(root_clip), "root keep")
        trim_clip = build_radial_clip_solid(
            z0=z0,
            z1=z1,
            outer_r=float(trim_outer_r),
            inner_r=float(refine_inner_r),
        )
    elif str(args.refine_span_mode) == "section_span" and section_r0 is not None and section_r1 is not None:
        refine_inner_r = max(0.0, float(section_r0) - float(args.refine_root_span_margin_mm))
        trim_outer_r = max(
            refine_inner_r + 1.0,
            float(section_r1) + float(args.refine_tip_span_margin_mm),
        )
        if refine_inner_r > 1e-6:
            root_clip = build_radial_clip_solid(z0=z0, z1=z1, outer_r=float(refine_inner_r))
            root_part = valid_single_shape(base_solid.intersect(root_clip), "root keep")
        trim_clip = build_radial_clip_solid(
            z0=z0,
            z1=z1,
            outer_r=float(trim_outer_r),
            inner_r=float(refine_inner_r),
        )
    else:
        root_clip = build_radial_clip_solid(z0=z0, z1=z1, outer_r=float(root_keep_r))
        transition_clip = build_radial_clip_solid(
            z0=z0,
            z1=z1,
            outer_r=float(transition_keep_r),
            inner_r=float(root_keep_r),
        )
        trim_clip = build_radial_clip_solid(
            z0=z0,
            z1=z1,
            outer_r=float(trim_outer_r),
            inner_r=float(transition_keep_r),
        )
        root_part = valid_single_shape(base_solid.intersect(root_clip), "root keep")
        transition_part = valid_single_shape(base_solid.intersect(transition_clip), "transition keep")
    if tip_shell_start_r is not None:
        trim_outer_r = max(float(refine_inner_r) + 1.0, min(float(trim_outer_r), float(tip_shell_start_r)))
        trim_clip = build_radial_clip_solid(
            z0=z0,
            z1=z1,
            outer_r=float(trim_outer_r),
            inner_r=float(refine_inner_r),
        )
    trim_source = valid_single_shape(base_solid.intersect(trim_clip), "trim source")
    refine_body, refine_align_mode, refine_overlap_volume = choose_best_refine_alignment(
        refine_body,
        trim_source,
        trim_clip,
        refine_align_mode=str(args.refine_align_mode),
    )
    refine_part = valid_single_shape(refine_body.intersect(trim_clip), "trim refine")
    planform_clip: Optional[Any] = None
    planform_clip_meta: Dict[str, Any] = {"status": "disabled"}
    if bool(args.planform_clip):
        planform_clip, planform_clip_meta = build_member_planform_clip_solid(
            member_submesh,
            member_payload,
            z0=z0,
            z1=z1,
            margin_mm=float(args.planform_margin_mm),
            bins=int(args.planform_bins),
            lower_percentile=float(args.planform_lower_percentile),
            upper_percentile=float(args.planform_upper_percentile),
            min_width_mm=float(args.planform_min_width_mm),
            root_pad_mm=float(args.planform_root_pad_mm),
            tip_pad_mm=float(args.planform_tip_pad_mm),
            root_expand_mm=float(args.planform_root_expand_mm),
            tip_expand_mm=float(args.planform_tip_expand_mm),
            extension_steps=int(args.planform_extension_steps),
            span_mode=str(args.planform_span_mode),
            span_root_margin_mm=float(args.planform_span_root_margin_mm),
            span_tip_margin_mm=float(args.planform_span_tip_margin_mm),
            full_span_percentile=float(args.planform_full_span_percentile),
        )

    template_shape = base_solid
    replace_inner_r = float(refine_inner_r)
    replace_outer_r = float(trim_outer_r)
    if (
        bool(args.keep_base_outside_refine_sections)
        and str(args.refine_span_mode) != "planform_full"
        and section_r0 is not None
        and section_r1 is not None
    ):
        replace_inner_r = max(float(refine_inner_r), float(section_r0))
        replace_outer_r = min(float(trim_outer_r), float(section_r1))

    if str(args.trim_mode) == "planform_base":
        trim_excess = []
    elif str(args.trim_mode) == "replace_refine":
        try:
            template_shape = template_shape.cut(trim_source)
        except Exception:
            pass
        template_shape = template_shape.fuse(refine_part)
        trim_excess = []
    elif str(args.trim_mode) == "root_intersection_replace":
        trim_excess = []
        root_split_r = float(replace_inner_r + (float(args.trim_root_intersection_ratio) * max(1e-6, replace_outer_r - replace_inner_r)))
        root_split_r = max(float(replace_inner_r), min(float(replace_outer_r), root_split_r))
        replace_tail_cut_outer_r = max(
            float(root_split_r),
            float(replace_outer_r) - max(0.0, float(args.replace_tail_overlap_mm)),
        )
        if root_split_r > replace_inner_r + 1e-6:
            root_band_clip = build_radial_band_clip_solid(z0=z0, z1=z1, inner_r=replace_inner_r, outer_r=root_split_r)
            root_trim_source = valid_single_shape(base_solid.intersect(root_band_clip), "root intersection source")
            root_refine_part = valid_single_shape(refine_body.intersect(root_band_clip), "root intersection refine")
            try:
                root_excess = section_diff.filter_valid_export_shapes(
                    [root_trim_source.cut(root_refine_part)],
                    "root intersection excess",
                )
            except Exception:
                root_excess = []
            if root_excess:
                template_shape = template_shape.cut(root_excess[0])
        if replace_tail_cut_outer_r > root_split_r + 1e-6:
            replace_band_clip = build_radial_band_clip_solid(z0=z0, z1=z1, inner_r=root_split_r, outer_r=replace_tail_cut_outer_r)
            replace_trim_source = valid_single_shape(base_solid.intersect(replace_band_clip), "replace tail source")
            replace_refine_part = valid_single_shape(refine_body.intersect(replace_band_clip), "replace tail refine")
            try:
                template_shape = template_shape.cut(replace_trim_source)
            except Exception:
                pass
        if replace_outer_r > root_split_r + 1e-6:
            replace_refine_clip = build_radial_band_clip_solid(z0=z0, z1=z1, inner_r=root_split_r, outer_r=replace_outer_r)
            replace_refine_part = valid_single_shape(refine_body.intersect(replace_refine_clip), "replace tail refine")
            template_shape = template_shape.fuse(replace_refine_part)
    else:
        try:
            cut_candidate = trim_source.cut(refine_part)
            trim_excess = section_diff.filter_valid_export_shapes([cut_candidate], "trim excess")
        except Exception:
            trim_excess = []
        if trim_excess:
            template_shape = template_shape.cut(trim_excess[0])
    if root_part is not None:
        template_shape = template_shape.fuse(root_part)
    if transition_part is not None:
        template_shape = template_shape.fuse(transition_part)
    planform_endpoint_preserve_meta: Dict[str, Any] = {"status": "disabled"}
    if planform_clip is not None:
        preserve_root_mm = max(0.0, float(args.planform_preserve_root_mm))
        preserve_tip_mm = max(0.0, float(args.planform_preserve_tip_mm))
        if preserve_root_mm > 1e-6 or preserve_tip_mm > 1e-6:
            template_shape, planform_endpoint_preserve_meta = apply_planform_clip_with_endpoint_preserve(
                template_shape=template_shape,
                planform_clip=planform_clip,
                endpoint_source=template_shape,
                z0=z0,
                z1=z1,
                clip_inner_r=float(refine_inner_r),
                clip_outer_r=float(trim_outer_r),
                preserve_root_mm=float(preserve_root_mm),
                preserve_tip_mm=float(preserve_tip_mm),
            )
        else:
            template_shape = valid_single_shape(template_shape.intersect(planform_clip), "template planform clip")
    groove_applied = False
    groove_meta: Dict[str, Any] = {"status": "disabled"}
    if bool(args.use_visual_constraints) and bool(args.apply_visual_grooves) and visual_constraint_row is not None:
        groove_window = ((visual_constraint_row.get("groove") or {}).get("window") or {})
        cut_depth = max(1.0, min(float(args.visual_groove_max_depth_mm), float(groove_window.get("mean_drop_mm", 0.0)) * float(args.visual_groove_depth_scale)))
        shape_z0 = float(shape_bbox(template_shape)[4])
        shape_z1 = float(shape_bbox(template_shape)[5])
        if str(args.visual_groove_face) == "negative_z":
            cutter = build_visual_groove_cutter(
                visual_constraint_row,
                angle_deg=float(template_angle),
                z0=shape_z0 - 1.0,
                z1=shape_z0 + cut_depth,
                width_scale=float(args.visual_groove_width_scale),
            )
        else:
            cutter = build_visual_groove_cutter(
                visual_constraint_row,
                angle_deg=float(template_angle),
                z0=shape_z1 - cut_depth,
                z1=shape_z1 + 1.0,
                width_scale=float(args.visual_groove_width_scale),
            )
        if cutter is not None:
            try:
                grooved = section_diff.filter_valid_export_shapes(
                    [template_shape.cut(cutter)],
                    "visual groove cut",
                )
            except Exception:
                grooved = []
            if grooved:
                template_shape = grooved[0]
                groove_applied = True
                groove_meta = {
                    "status": "applied",
                    "cut_depth_mm": float(cut_depth),
                    "window": groove_window,
                }
            else:
                groove_meta = {"status": "cut_failed", "window": groove_window}
    boundary_cut_meta: Dict[str, Any] = {"status": "disabled"}
    if bool(args.revolved_boundary_cut):
        if str(args.boundary_outer_mode) == "none":
            template_shape, boundary_cut_meta = apply_revolved_inner_boundary_cut(
                template_shape,
                features=features,
                z0=z0,
                z1=z1,
                inner_offset_mm=float(args.boundary_inner_offset_mm),
            )
        elif str(args.boundary_outer_mode) == "rim_curve":
            template_shape, boundary_cut_meta = apply_revolved_rim_curve_boundary_cut(
                template_shape,
                features=features,
                z0=z0,
                z1=z1,
                inner_offset_mm=float(args.boundary_inner_offset_mm),
                outer_offset_mm=float(args.boundary_outer_offset_mm),
                samples=int(args.rim_curve_boundary_samples),
            )
        else:
            template_shape, boundary_cut_meta = apply_revolved_boundary_cut(
                template_shape,
                features=features,
                z0=z0,
                z1=z1,
                inner_offset_mm=float(args.boundary_inner_offset_mm),
                outer_offset_mm=float(args.boundary_outer_offset_mm),
            )
    template_shape = valid_single_shape(template_shape, "template fused")

    meta = {
        "template_member_index": int(member_payload.get("member_index", -1)),
        "template_angle_deg": float(template_angle),
        "base_width_mm": float(base_width),
        "base_profile_mode": str(args.base_profile_mode),
        "base_rect_z_margin_mm": float(args.base_rect_z_margin_mm),
        "base_root_pad_mm": float(args.base_root_pad_mm),
        "base_tip_pad_mm": float(args.base_tip_pad_mm),
        "width_samples": len(band_samples),
        "section_replaced_count": int(replaced),
        "face_mode": str(args.face_mode),
        "refine_span_mode": str(args.refine_span_mode),
        "root_keep_r": float(root_keep_r),
        "transition_keep_r": float(transition_keep_r),
        "refine_inner_r": float(refine_inner_r),
        "trim_outer_r": float(trim_outer_r),
        "section_span_r0": float(section_r0) if section_r0 is not None else None,
        "section_span_r1": float(section_r1) if section_r1 is not None else None,
        "refine_align_mode": str(refine_align_mode),
        "refine_overlap_volume": float(refine_overlap_volume),
        "trim_mode": str(args.trim_mode),
        "trim_root_intersection_ratio": float(args.trim_root_intersection_ratio),
        "keep_base_outside_refine_sections": bool(args.keep_base_outside_refine_sections),
        "replace_inner_r": float(replace_inner_r),
        "replace_outer_r": float(replace_outer_r),
        "replace_tail_overlap_mm": float(args.replace_tail_overlap_mm),
        "refine_gap_fill_mm": float(args.refine_gap_fill_mm),
        "refine_dense_spacing_mm": float(args.refine_dense_spacing_mm),
        "refine_dense_min_gap_mm": float(args.refine_dense_min_gap_mm),
        "planform_clip": bool(args.planform_clip),
        "planform_root_pad_mm": float(args.planform_root_pad_mm),
        "planform_tip_pad_mm": float(args.planform_tip_pad_mm),
        "planform_root_expand_mm": float(args.planform_root_expand_mm),
        "planform_tip_expand_mm": float(args.planform_tip_expand_mm),
        "planform_extension_steps": int(args.planform_extension_steps),
        "planform_span_mode": str(args.planform_span_mode),
        "planform_span_root_margin_mm": float(args.planform_span_root_margin_mm),
        "planform_span_tip_margin_mm": float(args.planform_span_tip_margin_mm),
        "planform_full_span_percentile": float(args.planform_full_span_percentile),
        "planform_preserve_root_mm": float(args.planform_preserve_root_mm),
        "planform_preserve_tip_mm": float(args.planform_preserve_tip_mm),
        "planform_clip_meta": planform_clip_meta,
        "planform_endpoint_preserve_meta": planform_endpoint_preserve_meta,
        "refine_planform_match": bool(args.refine_planform_match),
        "refine_planform_match_strength": float(args.refine_planform_match_strength),
        "refine_planform_match_start": float(args.refine_planform_match_start),
        "refine_planform_match_end": float(args.refine_planform_match_end),
        "refine_planform_width_only": bool(args.refine_planform_width_only),
        "refine_planform_expand_only": bool(args.refine_planform_expand_only),
        "refine_planform_upper_only": bool(args.refine_planform_upper_only),
        "refine_planform_min_expand_mm": float(args.refine_planform_min_expand_mm),
        "refine_planform_profile_meta": planform_profile_meta,
        "repair_tail_z_outliers": bool(args.repair_tail_z_outliers),
        "tail_z_drop_threshold_mm": float(args.tail_z_drop_threshold_mm),
        "use_visual_constraints": bool(args.use_visual_constraints),
        "visual_constraint_member": int(visual_constraint_row.get("member_index", -1)) if isinstance(visual_constraint_row, dict) else None,
        "apply_visual_grooves": bool(args.apply_visual_grooves),
        "visual_groove_applied": bool(groove_applied),
        "visual_groove_meta": groove_meta,
        "apply_visual_section_groove": bool(section_groove_enabled),
        "visual_section_groove_depth_scale": float(args.visual_section_groove_depth_scale),
        "visual_section_groove_width_scale": float(args.visual_section_groove_width_scale),
        "revolved_boundary_cut": bool(args.revolved_boundary_cut),
        "boundary_outer_mode": str(args.boundary_outer_mode),
        "boundary_inner_offset_mm": float(args.boundary_inner_offset_mm),
        "boundary_outer_offset_mm": float(args.boundary_outer_offset_mm),
        "rim_curve_boundary_samples": int(args.rim_curve_boundary_samples),
        "revolved_boundary_cut_meta": boundary_cut_meta,
        "tip_bridge_mode": str(args.tip_bridge_mode),
        "tip_bridge_ratio": float(args.tip_bridge_ratio),
        "prefer_member_submesh_sections": bool(args.prefer_member_submesh_sections),
        "refine_lower_mid_start": float(args.refine_lower_mid_start),
        "refine_lower_mid_end": float(args.refine_lower_mid_end),
        "refine_upper_strength": float(args.refine_upper_strength),
        "refine_upper_mid_start": float(args.refine_upper_mid_start),
        "refine_upper_mid_end": float(args.refine_upper_mid_end),
        "refine_lower_x_start": float(args.refine_lower_x_start),
        "refine_lower_x_end": float(args.refine_lower_x_end),
        "refine_upper_x_start": float(args.refine_upper_x_start),
        "refine_upper_x_end": float(args.refine_upper_x_end),
        "refine_lower_auto_flip": bool(args.refine_lower_auto_flip),
        "refine_tail_start": float(args.refine_tail_start),
        "refine_root_shift_strength": float(args.refine_root_shift_strength),
        "refine_root_shift_start": float(args.refine_root_shift_start),
        "refine_root_shift_end": float(args.refine_root_shift_end),
        "refine_root_thickness_strength": float(args.refine_root_thickness_strength),
        "refine_root_thickness_start": float(args.refine_root_thickness_start),
        "refine_root_thickness_end": float(args.refine_root_thickness_end),
        "refine_mid_shift_start": float(args.refine_mid_shift_start),
        "refine_mid_shift_end": float(args.refine_mid_shift_end),
        "refine_mid_thickness_start": float(args.refine_mid_thickness_start),
        "refine_mid_thickness_end": float(args.refine_mid_thickness_end),
        "silhouette_bounds": [float(v) for v in sb],
    }
    return template_shape, meta


def run_template_pointcloud_diagnostic(
    *,
    features_path: Path,
    reference_stl_path: Path,
    candidate_stl_path: Path,
    member_index: int,
    sample_count: int,
    bins: int,
    min_bin_points: int,
    reuse_submesh_cache: bool,
    output_json_path: Path,
    output_plot_path: Optional[Path],
    output_dir: Path,
) -> Dict[str, Any]:
    from tools.diagnose_single_spoke_radial_error import build_plot, sanitize_json
    from tools.diagnose_template_member_radial_error import diagnose_member

    payload = diagnose_member(
        features_path=features_path,
        stl_path=reference_stl_path,
        candidate_stl_path=candidate_stl_path,
        member_index=int(member_index),
        sample_count=int(sample_count),
        bins=int(bins),
        min_bin_points=int(min_bin_points),
        reuse_submesh_cache=bool(reuse_submesh_cache),
        output_dir=output_dir,
    )
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(sanitize_json(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    if output_plot_path is not None:
        output_plot_path.parent.mkdir(parents=True, exist_ok=True)
        build_plot(
            output_path=output_plot_path,
            stl_rows=payload["source_rows"],
            step_rows=payload["candidate_rows"],
            delta_rows=payload["bins"],
        )
    return payload


def run_full_visual_evaluation(
    *,
    reference_stl_path: Path,
    step_path: Path,
    features_path: Path,
    output_metrics_path: Path,
    compare_dir: Path,
    visual_sample_size: int,
    eval_seed: int,
    max_eval_stl_bytes: int,
) -> Dict[str, Any]:
    from agents.evaluation_agent import EvaluationAgent
    from tools.run_modelonly_patch_eval import build_spoke_zoom, compute_metrics

    compare_dir.mkdir(parents=True, exist_ok=True)
    agent = EvaluationAgent(
        stl_path=str(reference_stl_path),
        step_path=str(step_path),
        features_path=str(features_path),
        config={
            "visual_sample_size": int(visual_sample_size),
            "eval_seed": int(eval_seed),
            "step_mesh_fallback_path": None,
            "max_eval_stl_bytes": int(max_eval_stl_bytes),
        },
    )
    comparison_path = compare_dir / "evaluation_comparison.png"
    spoke_zoom_path = compare_dir / "evaluation_comparison_spoke_zoom.png"
    agent.visualize_comparison(str(comparison_path))
    build_spoke_zoom(agent, spoke_zoom_path)
    metrics = compute_metrics(agent)
    metrics["step_path"] = str(step_path)
    metrics["features_path"] = str(features_path)
    metrics["compare_dir"] = str(compare_dir)
    metrics["comparison_path"] = str(comparison_path)
    metrics["spoke_zoom_path"] = str(spoke_zoom_path)
    output_metrics_path.parent.mkdir(parents=True, exist_ok=True)
    output_metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build one spoke by radial-section extrusion, trim it with section-guided refinement, then array it."
    )
    parser.add_argument(
        "--allow-legacy-engine-direct-use",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--features", required=True, help="Features JSON path")
    parser.add_argument("--base-step", required=True, help="Spoke-free STEP path")
    parser.add_argument("--reference-stl", default=str(ROOT / "input" / "wheel.stl"), help="Reference STL path")
    parser.add_argument("--output-step", required=True, help="Output STEP path")
    parser.add_argument("--output-stl", required=True, help="Output STL path")
    parser.add_argument("--template-output-step", default=None, help="Optional STEP path for the single template spoke")
    parser.add_argument("--template-output-stl", default=None, help="Optional STL path for the single template spoke")
    parser.add_argument("--template-only", action="store_true", help="Export only the single template spoke and skip the arrayed wheel assembly")
    parser.add_argument("--meta-out", default=None, help="Optional metadata JSON path")
    parser.add_argument("--template-member-index", type=int, default=2, help="Member used to build the single-spoke template")
    parser.add_argument("--alternate-template-member-index", type=int, default=None, help="Optional second member used to build an alternating slot-specific template")
    parser.add_argument("--base-width-mode", choices=["tip_max", "max", "p95", "median"], default="tip_max", help="How to select the extrusion base width")
    parser.add_argument("--base-width-scale", type=float, default=1.0, help="Scale applied to the chosen extrusion width")
    parser.add_argument("--base-profile-mode", choices=["silhouette", "rectangle"], default="silhouette", help="Radial/Z profile used for the raw spoke base body")
    parser.add_argument("--base-rect-z-margin-mm", type=float, default=0.0, help="Extra local-Z margin for --base-profile-mode rectangle")
    parser.add_argument("--base-root-pad-mm", type=float, default=0.0, help="Extra local-radial length added to the base extrude near the root end")
    parser.add_argument("--base-tip-pad-mm", type=float, default=0.0, help="Extra local-radial length added to the base extrude near the tail/tip end")
    parser.add_argument("--face-mode", choices=["positive_z", "negative_z"], default="positive_z", help="Which spoke face the radial extrusion base should occupy")
    parser.add_argument("--root-keep-ratio", type=float, default=0.24, help="Inner radial fraction preserved from the pure extrude body")
    parser.add_argument("--transition-keep-width", type=float, default=18.0, help="Extra radial width preserved from the raw extrude body after the root keep zone")
    parser.add_argument("--keep-tip-shell", action="store_true", help="Preserve the outermost shell of the raw extrude body")
    parser.add_argument("--tip-keep-ratio", type=float, default=0.86, help="When keep-tip-shell is enabled, radial start ratio of that kept shell")
    parser.add_argument("--refine-span-mode", choices=["legacy", "section_span", "planform_full"], default="legacy", help="How the refine trim span is selected along the spoke radius")
    parser.add_argument("--refine-root-span-margin-mm", type=float, default=0.0, help="How far inside the first real section the refine trim is allowed to extend")
    parser.add_argument("--refine-tip-span-margin-mm", type=float, default=0.0, help="How far outside the last real section the refine trim is allowed to extend")
    parser.add_argument("--refine-gap-fill-mm", type=float, default=0.0, help="Inject additional mesh-derived refine sections whenever adjacent stations are farther apart than this gap")
    parser.add_argument("--refine-dense-spacing-mm", type=float, default=0.0, help="Inject dense mesh-derived refine sections at a fixed station spacing across the full radial span")
    parser.add_argument("--refine-dense-min-gap-mm", type=float, default=1.2, help="Minimum station gap used to avoid duplicate dense refine sections")
    parser.add_argument("--planform-clip", action="store_true", help="Clip the template by the source member front-view planform before arraying")
    parser.add_argument("--planform-margin-mm", type=float, default=1.2, help="Margin applied to the extracted member planform clip")
    parser.add_argument("--planform-bins", type=int, default=42, help="Radial bin count used for source member planform extraction")
    parser.add_argument("--planform-lower-percentile", type=float, default=3.0, help="Lower tangent percentile used by the planform clip")
    parser.add_argument("--planform-upper-percentile", type=float, default=97.0, help="Upper tangent percentile used by the planform clip")
    parser.add_argument("--planform-min-width-mm", type=float, default=8.0, help="Minimum tangent width enforced on the planform clip")
    parser.add_argument("--planform-span-mode", choices=["section", "full"], default="section", help="Radial range used to extract member planform")
    parser.add_argument("--planform-span-root-margin-mm", type=float, default=4.0, help="Extra inward radial margin for planform extraction")
    parser.add_argument("--planform-span-tip-margin-mm", type=float, default=4.0, help="Extra outward radial margin for planform extraction")
    parser.add_argument("--planform-full-span-percentile", type=float, default=0.8, help="Endpoint percentile used by --planform-span-mode full")
    parser.add_argument("--planform-root-pad-mm", type=float, default=0.0, help="Extend the planform clip/profile radially inward by duplicating the first edge bin")
    parser.add_argument("--planform-tip-pad-mm", type=float, default=0.0, help="Extend the planform clip/profile radially outward by duplicating the last edge bin")
    parser.add_argument("--planform-root-expand-mm", type=float, default=0.0, help="Widen the generated root planform extension at the connection end")
    parser.add_argument("--planform-tip-expand-mm", type=float, default=0.0, help="Widen the generated tail/rim planform extension at the connection end")
    parser.add_argument("--planform-extension-steps", type=int, default=1, help="Number of contour samples used to extend root/tail planform instead of a single flat edge")
    parser.add_argument("--planform-preserve-root-mm", type=float, default=0.0, help="Keep the root connection zone from the unclipped spoke when applying planform clip")
    parser.add_argument("--planform-preserve-tip-mm", type=float, default=0.0, help="Keep the tail/rim connection zone from the unclipped spoke when applying planform clip")
    parser.add_argument("--refine-planform-match", action="store_true", help="Match section local-x width to the source member front-view planform envelope")
    parser.add_argument("--refine-planform-match-strength", type=float, default=0.45, help="Blend strength for source planform-driven section width matching")
    parser.add_argument("--refine-planform-match-start", type=float, default=0.18, help="Station-ratio start for planform-driven section width matching")
    parser.add_argument("--refine-planform-match-end", type=float, default=0.88, help="Station-ratio end for planform-driven section width matching")
    parser.add_argument("--refine-planform-width-only", action="store_true", help="Use the source planform only to resize local section width without moving the section center")
    parser.add_argument("--refine-planform-expand-only", action="store_true", help="Use planform matching only when it widens the local section")
    parser.add_argument("--refine-planform-upper-only", action="store_true", help="Use planform matching to move only the positive tangent/upper boundary while preserving the lower boundary")
    parser.add_argument("--refine-planform-min-expand-mm", type=float, default=0.0, help="Minimum width expansion applied when expand-only planform matching is active")
    parser.add_argument("--visual-constraints-json", default=None, help="Optional spoke_visual_constraints JSON from extract_spoke_visual_constraints.py")
    parser.add_argument("--use-visual-constraints", action="store_true", help="Use visual-constraint planform profiles instead of extracting a new planform from the member submesh")
    parser.add_argument("--apply-visual-grooves", action="store_true", help="Cut shallow front-face spoke grooves from detected visual constraints")
    parser.add_argument("--visual-groove-face", choices=["positive_z", "negative_z"], default="positive_z", help="Which axial face receives visual groove cuts")
    parser.add_argument("--visual-groove-depth-scale", type=float, default=0.42, help="Scale applied to detected groove drop for groove cut depth")
    parser.add_argument("--visual-groove-max-depth-mm", type=float, default=3.2, help="Maximum visual groove cut depth")
    parser.add_argument("--visual-groove-width-scale", type=float, default=0.28, help="Fraction of detected spoke width used as groove cutter width")
    parser.add_argument("--apply-visual-section-groove", action="store_true", help="Shape local section upper faces into a shallow visual groove instead of boolean cutting")
    parser.add_argument("--visual-section-groove-depth-scale", type=float, default=0.22, help="Scale applied to detected groove drop for section-profile groove depth")
    parser.add_argument("--visual-section-groove-max-depth-mm", type=float, default=1.8, help="Maximum section-profile visual groove depth")
    parser.add_argument("--visual-section-groove-width-scale", type=float, default=0.42, help="Fraction of detected spoke width used by section-profile groove")
    parser.add_argument("--visual-section-groove-edge-fade-mm", type=float, default=5.0, help="Radial fade distance at visual section-groove start/end")
    parser.add_argument("--revolved-boundary-cut", action="store_true", help="Clip each spoke template to the wheel annulus between center bore and rim outer radius")
    parser.add_argument("--boundary-outer-mode", choices=["none", "cylinder", "rim_curve"], default="cylinder", help="Outer boundary used by --revolved-boundary-cut; none cuts only the center bore")
    parser.add_argument("--boundary-inner-offset-mm", type=float, default=0.0, help="Offset added to bore_radius for the revolved inner boundary cut")
    parser.add_argument("--boundary-outer-offset-mm", type=float, default=0.0, help="Offset added to rim_max_radius for the revolved outer boundary cut")
    parser.add_argument("--rim-curve-boundary-samples", type=int, default=32, help="Rim profile sample count used by --boundary-outer-mode rim_curve")
    parser.add_argument("--post-rim-curve-boundary-cut", action="store_true", help="After all spokes are assembled, clip the whole wheel to the rim outer profile curve")
    parser.add_argument("--post-rim-curve-boundary-offset-mm", type=float, default=0.0, help="Radial offset for the post-spoke rim curve boundary")
    parser.add_argument("--post-rim-curve-boundary-samples", type=int, default=48, help="Rim profile sample count for the post-spoke outer boundary")
    parser.add_argument("--post-rim-curve-boundary-z-margin-mm", type=float, default=2.0, help="Extra Z margin for the post-spoke rim curve boundary")
    parser.add_argument("--post-use-production-hub-cuts", action="store_true", help="After all spokes are assembled, reuse the STL-to-STEP production lug-pocket and hub-groove cuts")
    parser.add_argument("--tip-bridge-mode", choices=["default", "late", "none"], default="default", help="How refine loft bridges from normal sections into tip sections")
    parser.add_argument("--tip-bridge-ratio", type=float, default=0.72, help="Bridge ratio used when --tip-bridge-mode late")
    parser.add_argument("--trim-mode", choices=["intersection", "replace_refine", "root_intersection_replace", "planform_base"], default="intersection", help="How the middle trim band combines extrusion base and refine body")
    parser.add_argument("--trim-root-intersection-ratio", type=float, default=0.28, help="For root_intersection_replace, radial fraction of the refine band that remains cut-only near the root")
    parser.add_argument("--keep-base-outside-refine-sections", action="store_true", help="Do not replace/cut base material outside the actual first/last refine section stations")
    parser.add_argument("--replace-tail-overlap-mm", type=float, default=0.0, help="Keep this much raw base under the outer end of the refine replacement so the tail joins without a planar split")
    parser.add_argument("--refine-align-mode", choices=["original", "mirror_xy", "auto"], default="original", help="How the section-guided refine body is aligned before trimming")
    parser.add_argument("--refine-lower-strength", type=float, default=-0.22, help="Lower-edge bias used by the section-guided refine body")
    parser.add_argument("--refine-lower-mid-start", type=float, default=0.34, help="Station-ratio start of the lower-edge bias window")
    parser.add_argument("--refine-lower-mid-end", type=float, default=0.82, help="Station-ratio end of the lower-edge bias window")
    parser.add_argument("--refine-upper-strength", type=float, default=0.0, help="Upper-edge bias used by the section-guided refine body")
    parser.add_argument("--refine-upper-mid-start", type=float, default=0.30, help="Station-ratio start of the upper-edge bias window")
    parser.add_argument("--refine-upper-mid-end", type=float, default=0.92, help="Station-ratio end of the upper-edge bias window")
    parser.add_argument("--refine-lower-x-start", type=float, default=0.0, help="Normalized local-x start of the lower-edge bias band")
    parser.add_argument("--refine-lower-x-end", type=float, default=1.0, help="Normalized local-x end of the lower-edge bias band")
    parser.add_argument("--refine-upper-x-start", type=float, default=0.0, help="Normalized local-x start of the upper-edge bias band")
    parser.add_argument("--refine-upper-x-end", type=float, default=1.0, help="Normalized local-x end of the upper-edge bias band")
    parser.add_argument("--refine-lower-auto-flip", action="store_true", help="Flip the lower-edge x gate automatically when the local section orientation is reversed")
    parser.add_argument("--refine-mid-shift-strength", type=float, default=0.0, help="Whole-section vertical shift strength applied only to the middle station band")
    parser.add_argument("--refine-mid-shift-start", type=float, default=0.26, help="Station-ratio start of the whole-section vertical shift window")
    parser.add_argument("--refine-mid-shift-end", type=float, default=0.80, help="Station-ratio end of the whole-section vertical shift window")
    parser.add_argument("--refine-mid-thickness-strength", type=float, default=0.0, help="Relative thickness scaling applied only to the middle station band")
    parser.add_argument("--refine-mid-thickness-start", type=float, default=0.26, help="Station-ratio start of the thickness scaling window")
    parser.add_argument("--refine-mid-thickness-end", type=float, default=0.80, help="Station-ratio end of the thickness scaling window")
    parser.add_argument("--refine-tail-strength", type=float, default=0.18, help="Tail-thickness bias used by the section-guided refine body")
    parser.add_argument("--refine-tail-start", type=float, default=0.72, help="Station-ratio start of the tail-thickness window")
    parser.add_argument("--repair-tail-z-outliers", action="store_true", help="Repair tail sections that jump onto a lower Z layer before refine lofting")
    parser.add_argument("--tail-z-drop-threshold-mm", type=float, default=18.0, help="Local section-Y drop used to detect a bad tail Z-layer section")
    parser.add_argument("--refine-root-shift-strength", type=float, default=0.0, help="Whole-section vertical shift strength applied only to the root station band")
    parser.add_argument("--refine-root-shift-start", type=float, default=0.0, help="Station-ratio start of the root-shift window")
    parser.add_argument("--refine-root-shift-end", type=float, default=0.0, help="Station-ratio end of the root-shift window")
    parser.add_argument("--refine-root-thickness-strength", type=float, default=0.0, help="Relative thickness scaling applied only to the root station band")
    parser.add_argument("--refine-root-thickness-start", type=float, default=0.0, help="Station-ratio start of the root thickness window")
    parser.add_argument("--refine-root-thickness-end", type=float, default=0.0, help="Station-ratio end of the root thickness window")
    parser.add_argument("--min-area", type=float, default=0.8, help="Minimum section polygon area")
    parser.add_argument("--max-center-offset", type=float, default=6.0, help="Section centroid gate")
    parser.add_argument("--min-area-ratio", type=float, default=0.45, help="Section area ratio lower bound")
    parser.add_argument("--max-area-ratio", type=float, default=1.85, help="Section area ratio upper bound")
    parser.add_argument("--template-diagnose", action="store_true", help="After exporting the template spoke, run point-cloud radial diagnostics against the source member mesh")
    parser.add_argument("--template-diag-json", default=None, help="Optional output JSON path for template spoke diagnostics")
    parser.add_argument("--template-diag-plot", default=None, help="Optional plot path for template spoke diagnostics")
    parser.add_argument("--template-diag-output-dir", default=str(ROOT / "output"), help="Working directory used for source member submesh cache")
    parser.add_argument("--template-diag-sample-count", type=int, default=20000, help="Point sample count used for template diagnostics")
    parser.add_argument("--template-diag-bins", type=int, default=18, help="Number of radial bins used for template diagnostics")
    parser.add_argument("--template-diag-min-bin-points", type=int, default=40, help="Minimum points per radial bin for template diagnostics")
    parser.add_argument("--reuse-submesh-cache", action="store_true", help="Reuse cached source member submeshes for template diagnostics")
    parser.add_argument("--refine-use-member-submesh", action="store_true", help="When extracting refine sections, fall back to the isolated source member submesh instead of relying only on full-wheel diff sections")
    parser.add_argument("--prefer-member-submesh-sections", action="store_true", help="Prefer isolated source member submesh sections over full-wheel diff sections whenever both pass gates")
    parser.add_argument("--member-submesh-output-dir", default=None, help="Optional cache directory for source member submesh extraction")
    parser.add_argument("--full-evaluate", action="store_true", help="After exporting the full wheel STEP, run visual/point-cloud evaluation")
    parser.add_argument("--eval-metrics-json", default=None, help="Optional output JSON path for full-wheel evaluation metrics")
    parser.add_argument("--eval-compare-dir", default=None, help="Optional output directory for full-wheel comparison images")
    parser.add_argument("--visual-sample-size", type=int, default=30000, help="Sample count used by the full-wheel evaluation")
    parser.add_argument("--eval-seed", type=int, default=42, help="Deterministic evaluation seed")
    parser.add_argument("--max-eval-stl-bytes", type=int, default=280 * 1024 * 1024, help="Max temporary STL size allowed during full-wheel evaluation")
    args = parser.parse_args()
    if not bool(args.allow_legacy_engine_direct_use):
        raise SystemExit(
            "Direct use of this legacy execution engine is disabled. "
            "Use tools/build_current_wheel_model.py so rejected experiment branches stay hidden."
        )

    features_path = Path(args.features).resolve()
    base_step_path = Path(args.base_step).resolve()
    reference_stl_path = Path(args.reference_stl).resolve()
    output_step_path = Path(args.output_step).resolve()
    output_stl_path = Path(args.output_stl).resolve()
    template_output_step_path = Path(args.template_output_step).resolve() if args.template_output_step else None
    template_output_stl_path = Path(args.template_output_stl).resolve() if args.template_output_stl else None
    meta_out_path = Path(args.meta_out).resolve() if args.meta_out else None
    template_diag_json_path = Path(args.template_diag_json).resolve() if args.template_diag_json else None
    template_diag_plot_path = Path(args.template_diag_plot).resolve() if args.template_diag_plot else None
    template_diag_output_dir = Path(args.template_diag_output_dir).resolve()
    member_submesh_output_dir = Path(args.member_submesh_output_dir).resolve() if args.member_submesh_output_dir else template_diag_output_dir
    eval_metrics_json_path = Path(args.eval_metrics_json).resolve() if args.eval_metrics_json else None
    eval_compare_dir = Path(args.eval_compare_dir).resolve() if args.eval_compare_dir else None
    visual_constraints_path = Path(args.visual_constraints_json).resolve() if args.visual_constraints_json else None

    features = load_json(features_path)
    args.visual_constraints_payload = load_json(visual_constraints_path) if visual_constraints_path is not None else None
    ref_mesh = single_spoke.load_trimesh(reference_stl_path, features=features)
    base_mesh = section_diff.build_base_mesh_from_step(base_step_path, 0.7, 0.7)
    base_body = cq.importers.importStep(str(base_step_path))
    base_shapes = section_diff.filter_valid_export_shapes(section_diff.collect_export_shapes(base_body), "base import")
    if not base_shapes:
        raise RuntimeError("no valid base body")
    base_shape = base_shapes[0] if len(base_shapes) == 1 else cq.Compound.makeCompound(base_shapes)
    base_bbox = shape_bbox(base_shape)

    template_motif, template_member = pick_template_member(features, args.template_member_index)
    template_member_submesh = None
    if bool(args.refine_use_member_submesh) or bool(args.planform_clip) or bool(args.refine_planform_match) or bool(args.prefer_member_submesh_sections):
        from tools.diagnose_member_spoke_overlap import build_or_load_source_submesh

        template_member_submesh = build_or_load_source_submesh(
            source_mesh=ref_mesh,
            features=features,
            member_index=int(template_member.get("member_index", -1)),
            output_dir=member_submesh_output_dir,
            reuse_cache=bool(args.reuse_submesh_cache),
        )
    template_shape, template_meta = build_template_shape(
        features,
        template_motif,
        template_member,
        ref_mesh,
        base_mesh,
        template_member_submesh,
        base_bbox,
        args,
    )
    alternate_template_shape: Optional[Any] = None
    alternate_template_meta: Optional[Dict[str, Any]] = None
    alternate_template_member: Optional[Dict[str, Any]] = None
    if args.alternate_template_member_index is not None:
        alternate_motif, alternate_template_member = pick_template_member(features, args.alternate_template_member_index)
        alternate_member_submesh = None
        if bool(args.refine_use_member_submesh) or bool(args.planform_clip) or bool(args.refine_planform_match) or bool(args.prefer_member_submesh_sections):
            from tools.diagnose_member_spoke_overlap import build_or_load_source_submesh

            alternate_member_submesh = build_or_load_source_submesh(
                source_mesh=ref_mesh,
                features=features,
                member_index=int(alternate_template_member.get("member_index", -1)),
                output_dir=member_submesh_output_dir,
                reuse_cache=bool(args.reuse_submesh_cache),
            )
        alternate_template_shape, alternate_template_meta = build_template_shape(
            features,
            alternate_motif,
            alternate_template_member,
            ref_mesh,
            base_mesh,
            alternate_member_submesh,
            base_bbox,
            args,
        )
    if template_output_step_path is not None:
        template_output_step_path.parent.mkdir(parents=True, exist_ok=True)
        section_diff.export_step_occ(template_shape, template_output_step_path, {})
    if template_output_stl_path is not None:
        template_output_stl_path.parent.mkdir(parents=True, exist_ok=True)
        cq.exporters.export(template_shape, str(template_output_stl_path), tolerance=0.8, angularTolerance=0.8)
    template_diag_candidate_stl_path = template_output_stl_path
    if bool(args.template_diagnose) and template_diag_candidate_stl_path is None and not bool(args.template_only):
        template_diag_candidate_stl_path = output_step_path.with_name(f"{output_step_path.stem}_template_diag.stl")
        template_diag_candidate_stl_path.parent.mkdir(parents=True, exist_ok=True)
        cq.exporters.export(template_shape, str(template_diag_candidate_stl_path), tolerance=0.8, angularTolerance=0.8)

    template_diag_payload: Optional[Dict[str, Any]] = None
    template_diag_json_written: Optional[Path] = None
    template_diag_plot_written: Optional[Path] = None
    if bool(args.template_only):
        export_shape = section_diff.export_step_occ(template_shape, output_step_path, {})
        cq.exporters.export(export_shape, str(output_stl_path), tolerance=0.8, angularTolerance=0.8)
        if bool(args.template_diagnose):
            candidate_stl_path = output_stl_path
            template_diag_json_written = (
                template_diag_json_path
                if template_diag_json_path is not None
                else output_step_path.with_name(f"{output_step_path.stem}.template_diag.json")
            )
            template_diag_plot_written = (
                template_diag_plot_path
                if template_diag_plot_path is not None
                else output_step_path.with_name(f"{output_step_path.stem}.template_diag.png")
            )
            template_diag_payload = run_template_pointcloud_diagnostic(
                features_path=features_path,
                reference_stl_path=reference_stl_path,
                candidate_stl_path=candidate_stl_path,
                member_index=int(template_member.get("member_index", -1)),
                sample_count=int(args.template_diag_sample_count),
                bins=int(args.template_diag_bins),
                min_bin_points=int(args.template_diag_min_bin_points),
                reuse_submesh_cache=bool(args.reuse_submesh_cache),
                output_json_path=template_diag_json_written,
                output_plot_path=template_diag_plot_written,
                output_dir=template_diag_output_dir,
            )
        if meta_out_path is not None:
            payload = {
                "features": str(features_path),
                "base_step": str(base_step_path),
                "reference_stl": str(reference_stl_path),
                "output_step": str(output_step_path),
                "output_stl": str(output_stl_path),
                "template_output_step": str(template_output_step_path) if template_output_step_path is not None else None,
                "template_output_stl": str(template_output_stl_path) if template_output_stl_path is not None else None,
                "template_only": True,
                "template": template_meta,
                "alternate_template": alternate_template_meta,
                "template_diag_json": str(template_diag_json_written) if template_diag_json_written is not None else None,
                "template_diag_plot": str(template_diag_plot_written) if template_diag_plot_written is not None else None,
                "template_diag_summary": {
                    "front_overlap_proxy": float(template_diag_payload.get("front_overlap_proxy")),
                    "nn_mean_fwd_mm": float(template_diag_payload.get("nn_mean_fwd_mm")),
                    "nn_mean_bwd_mm": float(template_diag_payload.get("nn_mean_bwd_mm")),
                    "zones": template_diag_payload.get("zones"),
                }
                if template_diag_payload is not None
                else None,
                "members": [],
            }
            meta_out_path.parent.mkdir(parents=True, exist_ok=True)
            meta_out_path.write_text(json.dumps(single_spoke.sanitize_for_json(payload), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[*] template member: {template_meta['template_member_index']} angle={template_meta['template_angle_deg']:.3f}")
        print(f"[*] base width: {template_meta['base_width_mm']:.3f}")
        print(f"[*] section replacements: {template_meta['section_replaced_count']}")
        if template_diag_payload is not None:
            print(f"[*] template diag front_overlap_proxy: {float(template_diag_payload['front_overlap_proxy']):.4f}")
            print(
                "[*] template diag zones: root={0:.4f} mid={1:.4f} tail={2:.4f}".format(
                    float((template_diag_payload.get("zones") or {}).get("root", {}).get("band_overlap", float("nan"))),
                    float((template_diag_payload.get("zones") or {}).get("mid", {}).get("band_overlap", float("nan"))),
                    float((template_diag_payload.get("zones") or {}).get("tail", {}).get("band_overlap", float("nan"))),
                )
            )
        print(f"[*] output step: {output_step_path}")
        print(f"[*] output stl: {output_stl_path}")
        return

    template_rows: List[Tuple[Optional[int], float, Any, Dict[str, Any]]] = [
        (
            int(template_member.get("slot_index", -1)),
            float(template_member.get("angle", 0.0)),
            template_shape,
            template_meta,
        )
    ]
    if alternate_template_shape is not None and alternate_template_meta is not None and alternate_template_member is not None:
        template_rows.append(
            (
                int(alternate_template_member.get("slot_index", -1)),
                float(alternate_template_member.get("angle", 0.0)),
                alternate_template_shape,
                alternate_template_meta,
            )
        )
    template_by_slot = {int(slot_index): (angle_deg, shape, meta) for slot_index, angle_deg, shape, meta in template_rows if slot_index is not None}
    default_template_angle = float(template_member.get("angle", 0.0))
    post_boundary_keep: Optional[Any] = None
    post_boundary_meta: Dict[str, Any] = {"status": "disabled"}
    if bool(args.post_rim_curve_boundary_cut):
        post_boundary_keep, post_boundary_meta = build_post_rim_curve_outer_boundary_keep(
            features=features,
            z_margin_mm=float(args.post_rim_curve_boundary_z_margin_mm),
            outer_offset_mm=float(args.post_rim_curve_boundary_offset_mm),
            samples=int(args.post_rim_curve_boundary_samples),
        )
    base_shape_count = len(base_shapes)
    all_shapes: List[Any] = list(base_shapes)
    member_stats: List[Dict[str, Any]] = []
    for motif_payload, member_payload in collect_members(features):
        member_index = int(member_payload.get("member_index", -1))
        target_angle = float(member_payload.get("angle", 0.0))
        slot_index = int(member_payload.get("slot_index", -1))
        chosen_template_angle = default_template_angle
        chosen_template_shape = template_shape
        chosen_template_member_index = int(template_meta.get("template_member_index", -1))
        if slot_index in template_by_slot:
            chosen_template_angle, chosen_template_shape, chosen_template_meta = template_by_slot[slot_index]
            chosen_template_member_index = int(chosen_template_meta.get("template_member_index", -1))
        delta = float(target_angle - chosen_template_angle)
        rotated_shape = rotate_shape_z(chosen_template_shape, delta)
        valid = section_diff.filter_valid_export_shapes([rotated_shape], f"array member {member_index}")
        if not valid:
            member_stats.append(
                {
                    "member_index": member_index,
                    "status": "invalid_after_rotate",
                    "delta_deg": delta,
                    "slot_index": slot_index,
                    "template_member_index": chosen_template_member_index,
                }
            )
            continue
        if post_boundary_keep is not None:
            clipped_valid: List[Any] = []
            for shape_index, member_shape in enumerate(valid):
                try:
                    clipped_valid.append(
                        valid_single_shape(
                            member_shape.intersect(post_boundary_keep),
                            f"post rim curve member {member_index}.{shape_index}",
                        )
                    )
                    post_boundary_meta["member_cut_count"] = int(post_boundary_meta.get("member_cut_count", 0)) + 1
                except Exception as exc:
                    failures = post_boundary_meta.setdefault("member_failures", [])
                    if isinstance(failures, list):
                        failures.append(
                            {
                                "member_index": int(member_index),
                                "shape_index": int(shape_index),
                                "error": str(exc),
                            }
                        )
                    clipped_valid.append(member_shape)
            valid = clipped_valid
        all_shapes.extend(valid)
        member_stats.append(
            {
                "member_index": member_index,
                "status": "built",
                "delta_deg": delta,
                "slot_index": slot_index,
                "target_angle_deg": target_angle,
                "template_member_index": chosen_template_member_index,
            }
        )
        print(f"[*] extrude-refine member={member_index}: slot={slot_index} template={chosen_template_member_index} delta={delta:.3f}")

    post_detail_meta: Dict[str, Any] = {"status": "disabled"}
    if bool(args.post_use_production_hub_cuts):
        cut_base_shapes, detail_meta = apply_production_hub_detail_cuts_to_assembled_body(
            all_shapes[:base_shape_count],
            features=features,
        )
        detail_meta["target"] = "base_hub_body"
        all_shapes = list(cut_base_shapes) + list(all_shapes[base_shape_count:])
        post_detail_meta = {"status": "applied", **detail_meta}
    export_input = all_shapes[0] if len(all_shapes) == 1 else cq.Compound.makeCompound(all_shapes)
    if post_boundary_keep is not None:
        try:
            export_input = valid_single_shape(
                export_input.intersect(post_boundary_keep),
                "final assembled rim curve boundary cut",
            )
            post_boundary_meta["final_assembled_cut"] = "applied"
        except Exception as exc:
            post_boundary_meta["final_assembled_cut"] = "failed"
            post_boundary_meta["final_assembled_error"] = str(exc)
    export_shape = section_diff.export_step_occ(export_input, output_step_path, {})
    cq.exporters.export(export_shape, str(output_stl_path), tolerance=0.8, angularTolerance=0.8)

    if bool(args.template_diagnose) and template_diag_candidate_stl_path is not None:
        template_diag_json_written = (
            template_diag_json_path
            if template_diag_json_path is not None
            else output_step_path.with_name(f"{output_step_path.stem}.template_diag.json")
        )
        template_diag_plot_written = (
            template_diag_plot_path
            if template_diag_plot_path is not None
            else output_step_path.with_name(f"{output_step_path.stem}.template_diag.png")
        )
        template_diag_payload = run_template_pointcloud_diagnostic(
            features_path=features_path,
            reference_stl_path=reference_stl_path,
            candidate_stl_path=template_diag_candidate_stl_path,
            member_index=int(template_member.get("member_index", -1)),
            sample_count=int(args.template_diag_sample_count),
            bins=int(args.template_diag_bins),
            min_bin_points=int(args.template_diag_min_bin_points),
            reuse_submesh_cache=bool(args.reuse_submesh_cache),
            output_json_path=template_diag_json_written,
            output_plot_path=template_diag_plot_written,
            output_dir=template_diag_output_dir,
        )

    evaluation_payload: Optional[Dict[str, Any]] = None
    evaluation_metrics_written: Optional[Path] = None
    evaluation_compare_written: Optional[Path] = None
    if bool(args.full_evaluate):
        evaluation_metrics_written = (
            eval_metrics_json_path
            if eval_metrics_json_path is not None
            else output_step_path.with_name(f"{output_step_path.stem}_seed{int(args.eval_seed)}.metrics.json")
        )
        evaluation_compare_written = (
            eval_compare_dir
            if eval_compare_dir is not None
            else output_step_path.parent / f"compare_{output_step_path.stem}_seed{int(args.eval_seed)}"
        )
        evaluation_payload = run_full_visual_evaluation(
            reference_stl_path=reference_stl_path,
            step_path=output_step_path,
            features_path=features_path,
            output_metrics_path=evaluation_metrics_written,
            compare_dir=evaluation_compare_written,
            visual_sample_size=int(args.visual_sample_size),
            eval_seed=int(args.eval_seed),
            max_eval_stl_bytes=int(args.max_eval_stl_bytes),
        )

    if meta_out_path is not None:
        payload = {
            "features": str(features_path),
            "base_step": str(base_step_path),
            "reference_stl": str(reference_stl_path),
            "output_step": str(output_step_path),
            "output_stl": str(output_stl_path),
            "template_output_step": str(template_output_step_path) if template_output_step_path is not None else None,
            "template_output_stl": str(template_output_stl_path) if template_output_stl_path is not None else None,
            "template": template_meta,
            "alternate_template": alternate_template_meta,
            "template_diag_json": str(template_diag_json_written) if template_diag_json_written is not None else None,
            "template_diag_plot": str(template_diag_plot_written) if template_diag_plot_written is not None else None,
            "template_diag_summary": {
                "front_overlap_proxy": float(template_diag_payload.get("front_overlap_proxy")),
                "nn_mean_fwd_mm": float(template_diag_payload.get("nn_mean_fwd_mm")),
                "nn_mean_bwd_mm": float(template_diag_payload.get("nn_mean_bwd_mm")),
                "zones": template_diag_payload.get("zones"),
            }
            if template_diag_payload is not None
            else None,
            "evaluation_metrics_json": str(evaluation_metrics_written) if evaluation_metrics_written is not None else None,
            "evaluation_compare_dir": str(evaluation_compare_written) if evaluation_compare_written is not None else None,
            "evaluation_summary": {
                "front_overlap": float(evaluation_payload.get("front_overlap")),
                "side_overlap": float(evaluation_payload.get("side_overlap")),
                "spoke_overlap": float(evaluation_payload.get("spoke_overlap")),
                "nn_mean_fwd_mm": float(evaluation_payload.get("nn_mean_fwd_mm")),
                "nn_mean_bwd_mm": float(evaluation_payload.get("nn_mean_bwd_mm")),
            }
            if evaluation_payload is not None
            else None,
            "post_rim_curve_boundary_cut": post_boundary_meta,
            "post_spoke_detail_cuts": post_detail_meta,
            "members": member_stats,
        }
        meta_out_path.parent.mkdir(parents=True, exist_ok=True)
        meta_out_path.write_text(json.dumps(single_spoke.sanitize_for_json(payload), ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[*] template member: {template_meta['template_member_index']} angle={template_meta['template_angle_deg']:.3f}")
    print(f"[*] base width: {template_meta['base_width_mm']:.3f}")
    print(f"[*] section replacements: {template_meta['section_replaced_count']}")
    if template_diag_payload is not None:
        print(f"[*] template diag front_overlap_proxy: {float(template_diag_payload['front_overlap_proxy']):.4f}")
        print(
            "[*] template diag zones: root={0:.4f} mid={1:.4f} tail={2:.4f}".format(
                float((template_diag_payload.get("zones") or {}).get("root", {}).get("band_overlap", float("nan"))),
                float((template_diag_payload.get("zones") or {}).get("mid", {}).get("band_overlap", float("nan"))),
                float((template_diag_payload.get("zones") or {}).get("tail", {}).get("band_overlap", float("nan"))),
            )
        )
    if evaluation_payload is not None:
        print(
            "[*] eval metrics: front={0:.4f} side={1:.4f} spoke={2:.4f} fwd={3:.4f} bwd={4:.4f}".format(
                float(evaluation_payload.get("front_overlap")),
                float(evaluation_payload.get("side_overlap")),
                float(evaluation_payload.get("spoke_overlap")),
                float(evaluation_payload.get("nn_mean_fwd_mm")),
                float(evaluation_payload.get("nn_mean_bwd_mm")),
            )
        )
    print(f"[*] output step: {output_step_path}")
    print(f"[*] output stl: {output_stl_path}")


if __name__ == "__main__":
    main()
