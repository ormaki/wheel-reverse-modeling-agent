from __future__ import annotations

import math
import os
import re
import time
from typing import Callable

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon as MplPolygon


def downsample_curve(points, max_points=4000):
    """Reduce preview-only point clouds to a manageable size."""
    if points is None:
        return []
    pts = [[round(float(p[0]), 3), round(float(p[1]), 3)] for p in points if len(p) >= 2]
    if len(pts) <= max_points:
        return pts
    step = max(1, len(pts) // max_points)
    return pts[::step]


def create_perception_preview(preview_data, image_path, show_window=True):
    """Render a perception preview image before modeling continues."""
    section_points = np.asarray(preview_data.get("orthographic_section_points", []), dtype=float)
    section_profile = preview_data.get("orthographic_face_profile", [])
    rotary_profile = preview_data.get("rotary_face_profile", [])
    rim_profile = preview_data.get("rim_profile", [])
    hub_profile = preview_data.get("hub_profile", [])
    spoke_regions = preview_data.get("spoke_regions", [])
    spoke_voids = preview_data.get("spoke_voids", [])
    spoke_motif_topology = preview_data.get("spoke_motif_topology", {})
    params = preview_data.get("global_params", {})
    preview_section_angle = float(preview_data.get("preview_section_angle_deg", 0.0))

    fig, axes = plt.subplots(1, 3, figsize=(19, 8), gridspec_kw={"width_ratios": [1.35, 1.0, 1.0]})
    for ax in axes[:2]:
        if len(section_points) > 0:
            ax.scatter(section_points[:, 0], section_points[:, 1], s=2, c="#d3d3d3", alpha=0.25, label="Orthographic Section Points")
        if section_profile:
            arr = np.asarray(section_profile, dtype=float)
            ax.plot(arr[:, 0], arr[:, 1], color="#222222", linewidth=1.8, linestyle="--", label="Orthographic Face Envelope")
        if rotary_profile:
            arr = np.asarray(rotary_profile, dtype=float)
            ax.plot(arr[:, 0], arr[:, 1], color="#d62828", linewidth=2.3, label="Unified Rotary Face")
        if hub_profile:
            arr = np.asarray(hub_profile, dtype=float)
            ax.plot(arr[:, 0], arr[:, 1], color="#2a9d8f", linewidth=1.8, label="Hub Profile")
        if rim_profile:
            arr = np.asarray(rim_profile, dtype=float)
            ax.plot(arr[:, 0], arr[:, 1], color="#1d4ed8", linewidth=1.6, label="Rim Profile")

        key_levels = [
            ("hub_face_z", "#2a9d8f"),
            ("hub_top_z", "#e76f51"),
            ("pocket_top_z", "#8d99ae"),
            ("center_relief_z", "#6a4c93"),
        ]
        for key, color in key_levels:
            z_val = params.get(key)
            if z_val is not None:
                ax.axhline(float(z_val), color=color, linewidth=0.9, linestyle=":", alpha=0.85)

        ax.set_xlabel("Radius (mm)")
        ax.set_ylabel("Z (mm)")
        ax.grid(True, alpha=0.18)
        ax.set_aspect("equal", adjustable="box")

    axes[0].set_title(f"Full Front Cross-Section Preview (section angle={preview_section_angle:.2f} deg)")
    rim_outer_r = max([float(p[0]) for p in rim_profile], default=max([float(p[0]) for p in rotary_profile], default=50.0))
    center_zoom_r = max(
        params.get("hub_radius", 0.0) * 1.45,
        params.get("pcd_radius", 0.0) + params.get("hole_radius", 0.0) + 18.0,
        80.0
    )
    axes[1].set_xlim(0.0, min(rim_outer_r, center_zoom_r))
    if section_points.size > 0:
        z_min = float(np.min(section_points[:, 1]))
        z_max = float(np.max(section_points[:, 1]))
        z_span = max(10.0, z_max - z_min)
        axes[1].set_ylim(z_max - z_span * 0.38, z_max + z_span * 0.05)
    axes[1].set_title("Center / Hub Zoom")

    motif_ax = axes[2]
    motif_ax.set_title("Spoke Motif Topology")
    motif_ax.set_xlabel("X (mm)")
    motif_ax.set_ylabel("Y (mm)")
    motif_ax.grid(True, alpha=0.18)
    motif_ax.set_aspect("equal", adjustable="box")

    cmap = plt.get_cmap("tab10")
    groups = spoke_motif_topology.get("groups", []) if isinstance(spoke_motif_topology, dict) else []
    region_group_map = {}
    for group in groups:
        for member_idx in group.get("member_indices", []):
            region_group_map[int(member_idx)] = int(group.get("group_index", 0))

    all_xy = []
    for region in spoke_voids or []:
        pts = region.get("points", []) if isinstance(region, dict) else region
        if len(pts) >= 4:
            arr = np.asarray(pts, dtype=float)
            motif_ax.plot(arr[:, 0], arr[:, 1], color="#c7c7c7", linewidth=0.8, alpha=0.8)
            all_xy.append(arr[:, :2])
    for idx, region in enumerate(spoke_regions or []):
        pts = region.get("points", []) if isinstance(region, dict) else region
        if len(pts) < 4:
            continue
        arr = np.asarray(pts, dtype=float)
        group_idx = region_group_map.get(int(idx), idx)
        color = cmap(group_idx % 10)
        patch = MplPolygon(arr[:, :2], closed=True, facecolor=color, edgecolor="#1f1f1f", linewidth=0.8, alpha=0.42)
        motif_ax.add_patch(patch)
        centroid = np.mean(arr[:-1, :2], axis=0) if len(arr) > 1 else np.mean(arr[:, :2], axis=0)
        motif_ax.text(float(centroid[0]), float(centroid[1]), str(idx), fontsize=7, ha="center", va="center", color="#111111")
        all_xy.append(arr[:, :2])

    for group in groups:
        start_angle = group.get("group_start_angle")
        end_angle = group.get("group_end_angle")
        outer_r = group.get("outer_r")
        if start_angle is None or end_angle is None or outer_r is None:
            continue
        boundary_r = float(outer_r) + 12.0
        for angle_deg in (start_angle, end_angle):
            ang = math.radians(float(angle_deg))
            motif_ax.plot(
                [0.0, boundary_r * math.cos(ang)],
                [0.0, boundary_r * math.sin(ang)],
                color="#5f0f40",
                linewidth=0.9,
                linestyle="--",
                alpha=0.55
            )

    if all_xy:
        xy_stack = np.vstack(all_xy)
        xy_limit = max(80.0, float(np.max(np.abs(xy_stack))) * 1.08)
        motif_ax.set_xlim(-xy_limit, xy_limit)
        motif_ax.set_ylim(-xy_limit, xy_limit)

    motif_title_suffix = "insufficient spoke data"
    if groups:
        motif_title_suffix = (
            f"{spoke_motif_topology.get('motif_type', 'unknown')}, "
            f"motifs={spoke_motif_topology.get('motif_count', 0)}, "
            f"members={spoke_motif_topology.get('members_per_motif', 0)}"
        )
    motif_ax.set_title(f"Spoke Motif Topology\n{motif_title_suffix}")

    handles, labels = axes[0].get_legend_handles_labels()
    dedup = {}
    for handle, label in zip(handles, labels):
        dedup[label] = handle
    if dedup:
        fig.legend(dedup.values(), dedup.keys(), loc="upper center", ncol=3, frameon=False)

    stats = preview_data.get("rotary_profile_stats", {})
    fig.suptitle(
        "Perception Preview Before Modeling\n"
        f"Rotary bins={stats.get('radial_bins_with_hits', 0)}, "
        f"valid sections={stats.get('valid_sections', 0)}, "
        f"median spread={stats.get('median_spread', 0.0):.2f} mm, "
        f"guarded={stats.get('guarded', False)}",
        fontsize=13
    )
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(image_path, dpi=180, bbox_inches="tight")
    print(f"[*] Perception preview saved: {os.path.abspath(image_path)}")

    if show_window:
        try:
            print("[*] Opening perception preview window for user confirmation...")
            plt.show(block=True)
        except Exception as exc:
            print(f"[!] Preview window display failed: {exc}")
    plt.close(fig)


def create_spokeless_section_preview(
    preview_data,
    image_path,
    show_window=True,
    derive_spoke_band_limits_fn: Callable | None = None,
    build_hybrid_profile_fn: Callable | None = None,
    split_profile_by_radius_gap_fn: Callable | None = None,
):
    """Render a dedicated preview for the spoke-free reference section."""
    if derive_spoke_band_limits_fn is None or build_hybrid_profile_fn is None or split_profile_by_radius_gap_fn is None:
        raise ValueError("Spokeless preview requires injected geometry helper callables.")

    spokeless_points = np.asarray(preview_data.get("spokeless_section_points", []), dtype=float)
    spokeless_upper_profile = preview_data.get("spokeless_upper_profile", []) or []
    spokeless_lower_profile = preview_data.get("spokeless_lower_profile", []) or []
    spokeless_region = preview_data.get("spokeless_guarded_section_region", {}) or {}
    spokeless_regions = preview_data.get("spokeless_guarded_section_regions", []) or []
    spokeless_fragments = preview_data.get("spokeless_reference_fragments", {}) or {}
    spokeless_hybrid_profile = preview_data.get("spokeless_hybrid_profile", []) or []
    guarded_region = preview_data.get("guarded_section_region", {}) or {}
    rotary_profile = preview_data.get("rotary_face_profile", []) or []
    hub_profile = preview_data.get("hub_profile", []) or []
    rim_profile = preview_data.get("rim_profile", []) or []
    spoke_regions = preview_data.get("spoke_regions", []) or []
    params = preview_data.get("global_params", {}) or {}
    spokeless_angle = preview_data.get("spokeless_section_angle_deg")

    has_region = bool(spokeless_region and spokeless_region.get("outer"))
    has_regions = any(isinstance(region, dict) and region.get("outer") for region in spokeless_regions)
    if spokeless_points.size == 0 and not has_region and not has_regions:
        return None

    fig, axes = plt.subplots(1, 2, figsize=(15, 7), gridspec_kw={"width_ratios": [1.25, 1.0]})

    cross_ax = axes[0]
    if spokeless_points.size > 0:
        cross_ax.scatter(
            spokeless_points[:, 0],
            spokeless_points[:, 1],
            s=3,
            c="#bdbdbd",
            alpha=0.32,
            label="Spokeless Section Points"
        )

    def plot_region_outline(ax, region_payload, color, label=None, linestyle="-", linewidth=1.8, alpha=0.95):
        if not isinstance(region_payload, dict):
            return
        outer = np.asarray(region_payload.get("outer", []), dtype=float)
        if outer.ndim == 2 and len(outer) >= 3:
            ax.plot(
                outer[:, 0],
                outer[:, 1],
                color=color,
                linewidth=linewidth,
                linestyle=linestyle,
                alpha=alpha,
                label=label
            )
        for hole in region_payload.get("holes", []):
            hole_arr = np.asarray(hole, dtype=float)
            if hole_arr.ndim == 2 and len(hole_arr) >= 3:
                ax.plot(
                    hole_arr[:, 0],
                    hole_arr[:, 1],
                    color=color,
                    linewidth=max(1.0, linewidth - 0.4),
                    linestyle=":",
                    alpha=0.75
                )

    region_descs = spokeless_fragments.get("regions", [])
    hub_region_index = spokeless_fragments.get("hub_region_index")
    rim_region_index = spokeless_fragments.get("rim_region_index")
    mid_region_index = spokeless_fragments.get("mid_region_index")
    band_inner_r, band_outer_r = derive_spoke_band_limits_fn(spoke_regions, params)
    hybrid_profile = spokeless_hybrid_profile or build_hybrid_profile_fn(
        rotary_profile,
        spokeless_upper_profile,
        band_inner_r,
        band_outer_r,
        reference_fragments=spokeless_fragments,
        profile_key="upper_profile"
    )
    cmap = plt.get_cmap("tab10")

    if guarded_region:
        plot_region_outline(cross_ax, guarded_region, "#222222", label="Full Guarded Section", linestyle="--", linewidth=1.4, alpha=0.85)
    for idx, region in enumerate(spokeless_regions):
        region_color = cmap(idx % 10)
        plot_region_outline(
            cross_ax,
            region,
            region_color,
            label="Spokeless Candidate" if idx == 0 else None,
            linewidth=1.5,
            alpha=0.82
        )
        desc = next((item for item in region_descs if int(item.get("index", -1)) == idx), None)
        if desc is not None:
            marker = []
            if idx == hub_region_index:
                marker.append("H")
            if idx == rim_region_index:
                marker.append("R")
            if idx == mid_region_index:
                marker.append("M")
            suffix = f" [{' / '.join(marker)}]" if marker else ""
            cross_ax.text(
                float(desc["centroid_r"]),
                float(desc["centroid_z"]),
                f"{idx}{suffix}",
                fontsize=8,
                ha="center",
                va="center",
                color="#111111",
                bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor=region_color, alpha=0.85)
            )
    if spokeless_region:
        plot_region_outline(cross_ax, spokeless_region, "#1d4ed8", label="Selected Spokeless Section", linewidth=2.2, alpha=0.95)
    upper_segments = split_profile_by_radius_gap_fn(spokeless_upper_profile, max_gap=5.0)
    lower_segments = split_profile_by_radius_gap_fn(spokeless_lower_profile, max_gap=5.0)
    for seg_idx, segment in enumerate(upper_segments):
        seg_arr = np.asarray(segment, dtype=float)
        seg_mask = (seg_arr[:, 0] >= float(band_inner_r)) & (seg_arr[:, 0] <= float(band_outer_r))
        if np.count_nonzero(seg_mask) >= 2:
            cross_ax.plot(
                seg_arr[seg_mask, 0],
                seg_arr[seg_mask, 1],
                color="#f77f00",
                linewidth=2.0,
                alpha=0.95,
                label="Spokeless Upper Envelope (Spoke Band)" if seg_idx == 0 else None
            )
    for seg_idx, segment in enumerate(lower_segments):
        seg_arr = np.asarray(segment, dtype=float)
        seg_mask = (seg_arr[:, 0] >= float(band_inner_r)) & (seg_arr[:, 0] <= float(band_outer_r))
        if np.count_nonzero(seg_mask) >= 2:
            cross_ax.plot(
                seg_arr[seg_mask, 0],
                seg_arr[seg_mask, 1],
                color="#577590",
                linewidth=1.8,
                alpha=0.9,
                linestyle="--",
                label="Spokeless Lower Envelope (Spoke Band)" if seg_idx == 0 else None
            )
    if hybrid_profile:
        hybrid_arr = np.asarray(hybrid_profile, dtype=float)
        cross_ax.plot(
            hybrid_arr[:, 0],
            hybrid_arr[:, 1],
            color="#c1121f",
            linewidth=2.4,
            alpha=0.92,
            label="Hybrid Candidate Profile"
        )
    cross_ax.axvspan(float(band_inner_r), float(band_outer_r), color="#f77f00", alpha=0.06)
    for desc in region_descs:
        if desc["index"] == hub_region_index and desc.get("upper_profile"):
            hub_arr = np.asarray(desc["upper_profile"], dtype=float)
            cross_ax.plot(hub_arr[:, 0], hub_arr[:, 1], color="#ff7f0e", linewidth=2.0, alpha=0.95, label="Hub Reference Fragment")
        if desc["index"] == rim_region_index and desc.get("upper_profile"):
            rim_frag_arr = np.asarray(desc["upper_profile"], dtype=float)
            cross_ax.plot(rim_frag_arr[:, 0], rim_frag_arr[:, 1], color="#2a9d8f", linewidth=2.0, alpha=0.95, label="Rim Reference Fragment")
    if rotary_profile:
        rotary_arr = np.asarray(rotary_profile, dtype=float)
        cross_ax.plot(rotary_arr[:, 0], rotary_arr[:, 1], color="#2a9d8f", linewidth=1.6, alpha=0.9, label="Unified Rotary Face")
    if hub_profile:
        hub_arr = np.asarray(hub_profile, dtype=float)
        cross_ax.plot(hub_arr[:, 0], hub_arr[:, 1], color="#6a4c93", linewidth=1.4, alpha=0.9, label="Hub Profile")
    if rim_profile:
        rim_arr = np.asarray(rim_profile, dtype=float)
        cross_ax.plot(rim_arr[:, 0], rim_arr[:, 1], color="#1d3557", linewidth=1.2, alpha=0.7, label="Rim Profile")

    cross_ax.set_xlabel("Radius (mm)")
    cross_ax.set_ylabel("Z (mm)")
    cross_ax.grid(True, alpha=0.18)
    cross_ax.set_aspect("equal", adjustable="box")
    angle_suffix = f"{float(spokeless_angle):.2f} deg" if spokeless_angle is not None else "n/a"
    cross_ax.set_title(f"Spoke-Free Section Cross-Section\nangle={angle_suffix}")
    handles, labels = cross_ax.get_legend_handles_labels()
    dedup = {}
    for handle, label in zip(handles, labels):
        dedup[label] = handle
    if dedup:
        cross_ax.legend(dedup.values(), dedup.keys(), loc="best", frameon=False, fontsize=8)

    topo_ax = axes[1]
    topo_ax.set_title("Spoke-Free Section Topology")
    topo_ax.set_xlabel("Radius (mm)")
    topo_ax.set_ylabel("Z (mm)")
    topo_ax.grid(True, alpha=0.18)
    topo_ax.set_aspect("equal", adjustable="box")
    for idx, region in enumerate(spokeless_regions):
        region_color = cmap(idx % 10)
        outer = np.asarray(region.get("outer", []), dtype=float)
        if outer.ndim == 2 and len(outer) >= 3:
            topo_ax.fill(outer[:, 0], outer[:, 1], color=region_color, alpha=0.18)
            topo_ax.plot(outer[:, 0], outer[:, 1], color=region_color, linewidth=1.6)
        for hole in region.get("holes", []):
            hole_arr = np.asarray(hole, dtype=float)
            if hole_arr.ndim == 2 and len(hole_arr) >= 3:
                topo_ax.fill(hole_arr[:, 0], hole_arr[:, 1], color="white", alpha=1.0)
                topo_ax.plot(hole_arr[:, 0], hole_arr[:, 1], color=region_color, linewidth=1.0, linestyle="--")
        desc = next((item for item in region_descs if int(item.get("index", -1)) == idx), None)
        if desc is not None:
            marker = []
            if idx == hub_region_index:
                marker.append("H")
            if idx == rim_region_index:
                marker.append("R")
            if idx == mid_region_index:
                marker.append("M")
            suffix = f" [{' / '.join(marker)}]" if marker else ""
            topo_ax.text(
                float(desc["centroid_r"]),
                float(desc["centroid_z"]),
                f"{idx}{suffix}",
                fontsize=8,
                ha="center",
                va="center",
                color="#111111",
                bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor=region_color, alpha=0.85)
            )

    if spokeless_points.size > 0:
        topo_ax.scatter(spokeless_points[:, 0], spokeless_points[:, 1], s=2, c="#7f7f7f", alpha=0.15)
    for seg_idx, segment in enumerate(upper_segments):
        seg_arr = np.asarray(segment, dtype=float)
        seg_mask = (seg_arr[:, 0] >= float(band_inner_r)) & (seg_arr[:, 0] <= float(band_outer_r))
        if np.count_nonzero(seg_mask) >= 2:
            topo_ax.plot(
                seg_arr[seg_mask, 0],
                seg_arr[seg_mask, 1],
                color="#f77f00",
                linewidth=1.8,
                alpha=0.95,
                label="Upper Envelope (Spoke Band)" if seg_idx == 0 else None
            )
    topo_ax.axvline(float(band_inner_r), color="#c1121f", linewidth=1.0, linestyle=":", alpha=0.65)
    topo_ax.axvline(float(band_outer_r), color="#c1121f", linewidth=1.0, linestyle=":", alpha=0.65)

    region_summary_lines = []
    for desc in region_descs:
        marker = []
        if desc["index"] == hub_region_index:
            marker.append("H")
        if desc["index"] == rim_region_index:
            marker.append("R")
        if desc["index"] == mid_region_index:
            marker.append("M")
        prefix = f"[{'/'.join(marker)}] " if marker else ""
        region_summary_lines.append(
            f"{prefix}{desc['index']}: R={desc['inner_r']:.1f}->{desc['outer_r']:.1f}, "
            f"Z={desc['z_min']:.1f}->{desc['z_max']:.1f}, A={desc['area']:.0f}"
        )
    if region_summary_lines:
        summary_text = "\n".join(region_summary_lines[:8])
        summary_text += f"\nBand: R={band_inner_r:.1f}->{band_outer_r:.1f}"
        fig.text(
            0.5,
            0.01,
            summary_text,
            ha="center",
            va="bottom",
            fontsize=8,
            family="monospace"
        )

    fig.suptitle("Spoke-Free Reference Section Preview\nclosed-region candidates vs raw section envelopes", fontsize=13)
    fig.tight_layout(rect=[0, 0.05, 1, 0.94])
    fig.savefig(image_path, dpi=180, bbox_inches="tight")
    print(f"[*] Spoke-free section preview saved: {os.path.abspath(image_path)}")
    if show_window:
        try:
            print("[*] Opening spoke-free section preview window for confirmation...")
            plt.show(block=True)
        except Exception as exc:
            print(f"[!] Spoke-free preview window display failed: {exc}")
    plt.close(fig)
    return image_path


def save_hub_face_groove_debug_plot(output_path, groove_regions, lug_boss_regions, center_core_region, bore_radius=None):
    if not output_path or not groove_regions:
        return
    try:
        fig, ax = plt.subplots(figsize=(7, 7))
        ax.set_aspect("equal", adjustable="box")

        if center_core_region:
            core_pts = center_core_region.get("points", []) if isinstance(center_core_region, dict) else center_core_region
            if len(core_pts) >= 4:
                xs = [p[0] for p in core_pts]
                ys = [p[1] for p in core_pts]
                ax.fill(xs, ys, color="#d9d9d9", alpha=0.6, linewidth=0)

        for region in lug_boss_regions or []:
            pts = region.get("points", []) if isinstance(region, dict) else region
            if len(pts) < 4:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            ax.fill(xs, ys, color="#9ecae1", alpha=0.55, linewidth=0)

        for region in groove_regions:
            pts = region.get("opening_points", region.get("points", [])) if isinstance(region, dict) else region
            if len(pts) < 4:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            ax.fill(xs, ys, color="#ef3b2c", alpha=0.75, linewidth=0)
            ax.plot(xs, ys, color="#a50f15", linewidth=1.2)

        if bore_radius is not None and float(bore_radius) > 0:
            bore_circle = plt.Circle((0.0, 0.0), float(bore_radius), color="#636363", fill=False, linewidth=1.0)
            ax.add_patch(bore_circle)

        extent = 0.0
        for region in (lug_boss_regions or []):
            pts = region.get("points", []) if isinstance(region, dict) else region
            for x, y in pts[:-1]:
                extent = max(extent, abs(float(x)), abs(float(y)))
        for region in groove_regions:
            pts = region.get("opening_points", region.get("points", [])) if isinstance(region, dict) else region
            for x, y in pts[:-1]:
                extent = max(extent, abs(float(x)), abs(float(y)))
        extent = max(extent, float(bore_radius or 0.0) + 8.0, 60.0)
        ax.set_xlim(-extent, extent)
        ax.set_ylim(-extent, extent)
        ax.set_title("Hub Groove Debug Overlay")
        ax.grid(True, alpha=0.2)
        fig.tight_layout()
        fig.savefig(output_path, dpi=180)
        plt.close(fig)
        print(f"[*] Hub groove debug overlay saved: {output_path}")
    except Exception as groove_debug_exc:
        print(f"[!] Hub groove debug overlay failed: {groove_debug_exc}")


TIMESTAMPED_STEP_NAME_RE = re.compile(r"\d{8}_\d{6}")


def ensure_timestamped_step_path(output_step_path):
    """Ensure exported STEP filenames always carry a timestamp suffix."""
    if not output_step_path:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        return os.path.join("output", f"wheel_{timestamp}.step")

    root, ext = os.path.splitext(output_step_path)
    if not ext:
        ext = ".step"

    file_stem = os.path.basename(root)
    if TIMESTAMPED_STEP_NAME_RE.search(file_stem):
        return f"{root}{ext}"

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return f"{root}_{timestamp}{ext}"


def generate_evaluation_comparison_bundle(stl_path, step_path, features_path, output_dir, sample_size=30000):
    """Export a consistent multiview + single-spoke comparison bundle for one STEP result."""
    try:
        from agents.evaluation_agent import EvaluationAgent
    except Exception as exc:
        print(f"[!] Evaluation bundle unavailable: {exc}")
        return {}

    os.makedirs(output_dir, exist_ok=True)
    artifacts = {}

    try:
        step_root, _ = os.path.splitext(str(step_path))
        agent = EvaluationAgent(
            stl_path=str(stl_path),
            step_path=str(step_path),
            features_path=str(features_path),
            config={
                "visual_sample_size": int(sample_size),
                "step_mesh_fallback_path": f"{step_root}_compare.stl",
                "max_eval_stl_bytes": 280 * 1024 * 1024,
            },
        )
    except Exception as exc:
        print(f"[!] Evaluation agent init failed: {exc}")
        return artifacts

    comparison_path = os.path.join(output_dir, "evaluation_comparison.png")
    try:
        artifacts["evaluation_comparison"] = agent.visualize_comparison(comparison_path)
    except Exception as exc:
        print(f"[!] Evaluation multiview export failed: {exc}")

    try:
        visual_sample_size = int(agent.config.get("visual_sample_size", sample_size))
        stl_points_raw = agent._sample_surface_points(agent.stl_mesh, agent.stl_vertices, sample_size=visual_sample_size)
        step_points_raw = agent._sample_surface_points(agent.step_mesh, agent.step_vertices, sample_size=visual_sample_size)

        stl_points = agent._canonicalize_wheel_points(stl_points_raw)
        step_points = agent._canonicalize_wheel_points(step_points_raw)
        step_points, align_meta = agent._align_step_to_stl_visual(stl_points, step_points)

        front_stl = agent._project_canonical_points(stl_points, "front")
        front_step = agent._project_canonical_points(step_points, "front")
        spoke_band_stl = agent._filter_spoke_band(front_stl)
        spoke_band_step = agent._filter_spoke_band(front_step)
        spoke_angle = agent._estimate_single_spoke_angle(spoke_band_stl, spoke_band_step)

        stl_spoke = agent._extract_single_spoke_closeup(front_stl, spoke_angle)
        step_spoke = agent._extract_single_spoke_closeup(front_step, spoke_angle)
        stl_spoke, step_spoke, orient_deg = agent._orient_closeup_pair(stl_spoke, step_spoke)

        fig, axes = plt.subplots(1, 3, figsize=(16, 5.8))
        panels = [
            ("STL single spoke", True, False),
            ("STEP single spoke", False, True),
            ("Overlay single spoke", True, True),
        ]
        for ax, (title, show_stl, show_step) in zip(axes, panels):
            if show_stl:
                agent._plot_projected_points(ax, stl_spoke, color="#1f77b4", label="STL", point_size=1.3, alpha=0.65)
            if show_step:
                agent._plot_projected_points(ax, step_spoke, color="#2ca02c", label="STEP", point_size=1.3, alpha=0.65)
            agent._set_projection_limits(ax, [stl_spoke, step_spoke], zoom=1.0)
            ax.set_title(
                f"{title}\nangle={spoke_angle:.1f} deg orient={orient_deg:.1f} deg align={align_meta.get('axial_rotation_deg', 0.0):.1f} deg"
            )
            if show_stl or show_step:
                ax.legend(loc="upper right", frameon=False, markerscale=8)

        plt.tight_layout()
        spoke_zoom_path = os.path.join(output_dir, "evaluation_comparison_spoke_zoom.png")
        plt.savefig(spoke_zoom_path, dpi=170, bbox_inches="tight")
        plt.close(fig)
        artifacts["evaluation_comparison_spoke_zoom"] = spoke_zoom_path
        print(f"[*] Single-spoke comparison saved: {spoke_zoom_path}")
    except Exception as exc:
        print(f"[!] Single-spoke comparison export failed: {exc}")

    return artifacts
