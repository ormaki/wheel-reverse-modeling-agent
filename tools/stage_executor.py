from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import json
import traceback

import cadquery as cq

import stl_to_step_pipeline as pipeline


class BuildStage(str, Enum):
    REVOLVE_BODY = "01"
    PCD_HOLES = "02"
    HUB_GROOVES = "03"
    SPOKES = "04"

    @classmethod
    def parse(cls, value: str) -> "BuildStage":
        normalized = str(value).strip().lower()
        alias_map = {
            "1": cls.REVOLVE_BODY,
            "01": cls.REVOLVE_BODY,
            "revolve": cls.REVOLVE_BODY,
            "revolve-body": cls.REVOLVE_BODY,
            "body": cls.REVOLVE_BODY,
            "2": cls.PCD_HOLES,
            "02": cls.PCD_HOLES,
            "pcd": cls.PCD_HOLES,
            "pcd-holes": cls.PCD_HOLES,
            "holes": cls.PCD_HOLES,
            "3": cls.HUB_GROOVES,
            "03": cls.HUB_GROOVES,
            "grooves": cls.HUB_GROOVES,
            "hub-grooves": cls.HUB_GROOVES,
            "4": cls.SPOKES,
            "04": cls.SPOKES,
            "spokes": cls.SPOKES,
            "full-spokes": cls.SPOKES,
        }
        if normalized not in alias_map:
            raise ValueError(f"Unsupported stage: {value}")
        return alias_map[normalized]


@dataclass
class StagePaths:
    stage_dir: Path
    model_path: Path
    notes_path: Path
    features_path: Path
    manifest_path: Path
    preview_root: Path


class StageExecutor:
    STAGE_BASENAMES = {
        BuildStage.REVOLVE_BODY: "01_revolve_body",
        BuildStage.PCD_HOLES: "02_pcd_holes",
        BuildStage.HUB_GROOVES: "03_hub_grooves",
        BuildStage.SPOKES: "04_spokes",
    }

    STAGE_LABELS = {
        BuildStage.REVOLVE_BODY: "revolve_body_only",
        BuildStage.PCD_HOLES: "revolve_plus_pcd_holes",
        BuildStage.HUB_GROOVES: "revolve_plus_pcd_holes_plus_grooves",
        BuildStage.SPOKES: "full_spoke_generation",
    }

    def __init__(self, output_dir: str = "./output") -> None:
        self.output_dir = Path(output_dir)

    def run_stage(self, stl_path: str, stage: str, output_format: str = "step") -> dict:
        parsed_stage = BuildStage.parse(stage)
        paths = self._prepare_paths(parsed_stage, output_format)
        warnings: list[str] = []
        manifest: dict = {
            "stage": parsed_stage.value,
            "stage_label": self.STAGE_LABELS[parsed_stage],
            "stl_path": str(Path(stl_path).resolve()),
            "model_path": str(paths.model_path.resolve()),
            "notes_path": str(paths.notes_path.resolve()),
            "features_path": str(paths.features_path.resolve()),
            "warnings": warnings,
        }

        try:
            if parsed_stage is BuildStage.SPOKES:
                features, namespace = self._execute_namespace(
                    stl_path=stl_path,
                    preview_root=paths.preview_root,
                    disable_spokes=False,
                )
                final_body = namespace.get("result")
            else:
                features, namespace = self._execute_namespace(
                    stl_path=stl_path,
                    preview_root=paths.preview_root,
                    disable_spokes=True,
                )
                if parsed_stage is BuildStage.REVOLVE_BODY:
                    final_body = namespace.get("result")
                elif parsed_stage is BuildStage.PCD_HOLES:
                    hub_body = self._apply_pcd_holes_only(namespace, warnings)
                    final_body = self._assemble_with_rim(namespace, hub_body, "stage 02 assembly")
                else:
                    hub_body = self._apply_pcd_holes_only(namespace, warnings)
                    hub_body = self._apply_hub_grooves_only(namespace, hub_body, warnings)
                    final_body = self._assemble_with_rim(namespace, hub_body, "stage 03 assembly")

            if final_body is None:
                raise ValueError("Stage execution did not produce a model body.")

            self._export_body(final_body, paths.model_path, output_format)
            self._write_features(features, parsed_stage, paths.features_path)
            manifest["status"] = "completed"
        except Exception as exc:
            manifest["status"] = "failed"
            manifest["error"] = str(exc)
            warnings.append(str(exc))
            self._write_notes(paths.notes_path, manifest, traceback.format_exc())
            with paths.manifest_path.open("w", encoding="utf-8") as handle:
                json.dump(manifest, handle, indent=2, ensure_ascii=False)
            raise

        self._write_notes(paths.notes_path, manifest, None)
        with paths.manifest_path.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, ensure_ascii=False)

        return {
            "stage": parsed_stage.value,
            "stage_model": str(paths.model_path),
            "stage_notes": str(paths.notes_path),
            "stage_features": str(paths.features_path),
            "stage_manifest": str(paths.manifest_path),
        }

    def _prepare_paths(self, stage: BuildStage, output_format: str) -> StagePaths:
        stage_dir = self.output_dir / "stages" / stage.value
        stage_dir.mkdir(parents=True, exist_ok=True)
        basename = self.STAGE_BASENAMES[stage]
        return StagePaths(
            stage_dir=stage_dir,
            model_path=stage_dir / f"{basename}.{output_format}",
            notes_path=stage_dir / f"{basename}_notes.md",
            features_path=stage_dir / f"{basename}_features.json",
            manifest_path=stage_dir / f"{basename}_manifest.json",
            preview_root=stage_dir / basename,
        )

    def _execute_namespace(self, stl_path: str, preview_root: Path, disable_spokes: bool) -> tuple[dict, dict]:
        features = pipeline.extract_features_from_stl(stl_path, return_preview=False)
        features["disable_spokes_modeling"] = bool(disable_spokes)
        features["debug_output_root"] = str(preview_root.resolve())
        code = pipeline.generate_cadquery_code(features)
        namespace: dict = {}
        exec(code, namespace, namespace)
        return features, namespace

    def _apply_pcd_holes_only(self, namespace: dict, warnings: list[str]):
        body = namespace.get("hub_body")
        params = namespace.get("params", {})
        safe_cut = namespace.get("safe_cut")
        hub_z_val = namespace.get("hub_z_val")
        hub_t_val = namespace.get("hub_t_val")
        if body is None or not callable(safe_cut):
            raise ValueError("PCD stage cannot access baseline hub body or safe_cut helper.")
        pcd_radius = float(params.get("pcd_radius", 0.0) or 0.0)
        hole_radius = float(params.get("hole_radius", 0.0) or 0.0)
        phase = float(params.get("pcd_phase_angle", 0.0) or 0.0)
        hole_count = max(1, int(params.get("hole_count", params.get("spoke_num", 0)) or 0))
        if pcd_radius <= 0.0 or hole_radius <= 0.0:
            warnings.append("PCD parameters are incomplete; hole cuts were skipped.")
            return body
        for index in range(hole_count):
            angle_deg = phase + (360.0 / hole_count) * index
            angle_rad = angle_deg * 3.141592653589793 / 180.0
            center_x = pcd_radius * namespace["math"].cos(angle_rad)
            center_y = pcd_radius * namespace["math"].sin(angle_rad)
            cutter = (
                cq.Workplane("XY")
                .workplane(offset=float(hub_z_val) - 1.0)
                .center(center_x, center_y)
                .circle(hole_radius)
                .extrude(float(hub_t_val) + 2.0)
            )
            body = safe_cut(body, cutter, f"stage 02 pcd hole {index}")
        return body

    def _apply_hub_grooves_only(self, namespace: dict, body, warnings: list[str]):
        groove_regions = namespace.get("hub_bottom_groove_regions", [])
        params = namespace.get("params", {})
        floor_z = params.get("hub_bottom_groove_floor_z")
        top_z = params.get("hub_bottom_groove_top_z")
        bore_radius = float(params.get("bore_radius", 0.0) or 0.0)
        hub_z_val = float(namespace.get("hub_z_val", 0.0) or 0.0)
        apply_relief = namespace.get("apply_hub_bottom_groove_relief")
        if not groove_regions:
            warnings.append("Groove perception data is empty; groove cuts were skipped.")
            return body
        if floor_z is None or top_z is None:
            warnings.append("Groove Z bounds are incomplete; groove cuts were skipped.")
            return body
        if not callable(apply_relief):
            warnings.append("Groove relief helper is unavailable; groove cuts were skipped.")
            return body
        return apply_relief(body, groove_regions, floor_z, top_z, bore_radius, hub_z_val)

    def _assemble_with_rim(self, namespace: dict, hub_body, label: str):
        rim = namespace.get("rim")
        safe_assemble = namespace.get("safe_assemble")
        if rim is None:
            return hub_body
        if not callable(safe_assemble):
            return hub_body
        return safe_assemble([rim, hub_body], label)

    def _write_features(self, features: dict, stage: BuildStage, path: Path) -> None:
        payload = {
            "stage": stage.value,
            "stage_label": self.STAGE_LABELS[stage],
            "global_params": features.get("global_params", {}),
            "rim_profile": features.get("rim_profile", {}),
            "hub_profile": features.get("hub_profile", {}),
            "rotary_face_profile": features.get("rotary_face_profile", {}),
            "hub_bottom_groove_regions": features.get("hub_bottom_groove_regions", []),
            "spoke_motif_topology": features.get("spoke_motif_topology", {}),
        }
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, default=self._json_default)

    def _write_notes(self, path: Path, manifest: dict, stacktrace: str | None) -> None:
        lines = [
            f"# Stage {manifest['stage']} Notes",
            "",
            f"- Stage label: `{manifest['stage_label']}`",
            f"- Status: `{manifest.get('status', 'unknown')}`",
            f"- STL: `{manifest['stl_path']}`",
            f"- Model: `{manifest['model_path']}`",
            f"- Features: `{manifest['features_path']}`",
            "",
            "## Warnings",
        ]
        warnings = manifest.get("warnings", [])
        if warnings:
            lines.extend([f"- {item}" for item in warnings])
        else:
            lines.append("- none")
        if stacktrace:
            lines.extend([
                "",
                "## Error",
                "```text",
                stacktrace.rstrip(),
                "```",
            ])
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _json_default(self, value):
        try:
            import numpy as np

            if isinstance(value, (np.floating, np.integer)):
                return value.item()
            if isinstance(value, np.ndarray):
                return value.tolist()
        except Exception:
            pass
        if hasattr(value, "tolist"):
            try:
                return value.tolist()
            except Exception:
                pass
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    def _export_body(self, obj, output_path: Path, output_format: str) -> None:
        shapes = self._filter_valid_export_shapes(self._collect_export_shapes(obj), "stage export")
        if not shapes:
            raise ValueError("No exportable CadQuery shapes were produced.")
        export_shape = shapes[0] if len(shapes) == 1 else cq.Compound.makeCompound(shapes)
        if hasattr(export_shape, "isValid") and (not export_shape.isValid()):
            raise ValueError("Export shape is invalid and was rejected before write.")
        if output_format == "step":
            if pipeline.OCP_STEP_EXPORT_AVAILABLE:
                pipeline.Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
                writer = pipeline.STEPControl_Writer()
                writer.Transfer(export_shape.wrapped, pipeline.STEPControl_AsIs)
                status = writer.Write(str(output_path))
                if int(status) != int(pipeline.IFSelect_RetDone):
                    raise RuntimeError(f"OCC STEP export failed with status {int(status)}")
            else:
                cq.exporters.export(export_shape, str(output_path))
        elif output_format == "stl":
            cq.exporters.export(export_shape, str(output_path))
        else:
            raise ValueError(f"Unsupported output format: {output_format}")

    def _collect_export_shapes(self, obj):
        if obj is None:
            return []
        if isinstance(obj, cq.Workplane):
            try:
                values = obj.vals()
            except Exception:
                values = []
            shapes = [value for value in values if hasattr(value, "wrapped")]
            if shapes:
                return shapes
            try:
                value = obj.val()
                if hasattr(value, "wrapped"):
                    return [value]
            except Exception:
                return []
        elif hasattr(obj, "wrapped"):
            return [obj]
        return []

    def _filter_valid_export_shapes(self, shapes, label: str):
        valid_shapes = []
        for index, shape in enumerate(shapes or []):
            try:
                if shape is None or shape.isNull():
                    print(f"[!] {label} shape {index} discarded: null")
                    continue
                if hasattr(shape, "isValid") and (not shape.isValid()):
                    print(f"[!] {label} shape {index} discarded: invalid")
                    continue
                valid_shapes.append(shape)
            except Exception as exc:
                print(f"[!] {label} shape {index} validation failed: {exc}")
        return valid_shapes
