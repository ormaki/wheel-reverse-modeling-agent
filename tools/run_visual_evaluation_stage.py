from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import cadquery as cq


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.diagnose_visual_spoke_differences import main as diagnose_visual_main
from tools.run_spoke_extrude_refine_array_model import run_full_visual_evaluation


def export_step_to_stl(step_path: Path, stl_path: Path, tolerance: float, angular_tolerance: float) -> Path:
    stl_path.parent.mkdir(parents=True, exist_ok=True)
    body = cq.importers.importStep(str(step_path))
    cq.exporters.export(body, str(stl_path), tolerance=float(tolerance), angularTolerance=float(angular_tolerance))
    return stl_path


def load_json_if_exists(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def run_visual_diagnostics(
    *,
    features_path: Path,
    reference_stl_path: Path,
    candidate_stl_path: Path,
    output_dir: Path,
    sample_count: int,
    seed: int,
    diff_threshold_mm: float,
) -> Path:
    summary_path = output_dir / "visual_spoke_diagnostics.json"
    old_argv = list(sys.argv)
    try:
        sys.argv = [
            "diagnose_visual_spoke_differences.py",
            "--features",
            str(features_path),
            "--reference-stl",
            str(reference_stl_path),
            "--candidate-stl",
            str(candidate_stl_path),
            "--output-dir",
            str(output_dir),
            "--sample-count",
            str(int(sample_count)),
            "--seed",
            str(int(seed)),
            "--diff-threshold-mm",
            str(float(diff_threshold_mm)),
            "--summary-json",
            str(summary_path),
        ]
        diagnose_visual_main()
    finally:
        sys.argv = old_argv
    return summary_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Standard visual evaluation stage for wheel reverse-modeling outputs."
    )
    parser.add_argument("--features", required=True, help="Features JSON path")
    parser.add_argument("--reference-stl", required=True, help="Reference STL path")
    parser.add_argument("--candidate-step", default=None, help="Candidate STEP path")
    parser.add_argument("--candidate-stl", default=None, help="Candidate STL path; generated from STEP when omitted")
    parser.add_argument("--output-dir", required=True, help="Evaluation output directory")
    parser.add_argument("--metrics-json", default=None, help="Optional metrics JSON path")
    parser.add_argument("--compare-dir", default=None, help="Optional full comparison image directory")
    parser.add_argument("--sample-count", type=int, default=65000, help="Visual diagnostics sample count")
    parser.add_argument("--visual-sample-size", type=int, default=30000, help="Full metric evaluation sample count")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic sampling seed")
    parser.add_argument("--diff-threshold-mm", type=float, default=2.4, help="2D nearest-neighbor visual threshold")
    parser.add_argument("--stl-tolerance", type=float, default=0.8, help="STEP-to-STL export tolerance")
    parser.add_argument("--stl-angular-tolerance", type=float, default=0.8, help="STEP-to-STL export angular tolerance")
    parser.add_argument("--max-eval-stl-bytes", type=int, default=280 * 1024 * 1024, help="Max temporary STL size for metric evaluation")
    parser.add_argument("--skip-metrics", action="store_true", help="Skip STEP metric evaluation")
    parser.add_argument("--skip-visual-diagnostics", action="store_true", help="Skip spoke visual difference diagnostics")
    args = parser.parse_args()

    features_path = Path(args.features).resolve()
    reference_stl_path = Path(args.reference_stl).resolve()
    candidate_step_path = Path(args.candidate_step).resolve() if args.candidate_step else None
    candidate_stl_path = Path(args.candidate_stl).resolve() if args.candidate_stl else None
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if candidate_step_path is None and candidate_stl_path is None:
        raise ValueError("provide --candidate-step, --candidate-stl, or both")
    if candidate_step_path is not None and not candidate_step_path.exists():
        raise FileNotFoundError(candidate_step_path)
    if candidate_stl_path is not None and not candidate_stl_path.exists():
        raise FileNotFoundError(candidate_stl_path)
    if candidate_stl_path is None:
        assert candidate_step_path is not None
        candidate_stl_path = output_dir / f"{candidate_step_path.stem}.candidate.stl"
        export_step_to_stl(
            candidate_step_path,
            candidate_stl_path,
            tolerance=float(args.stl_tolerance),
            angular_tolerance=float(args.stl_angular_tolerance),
        )

    metrics_path: Optional[Path] = None
    compare_dir: Optional[Path] = None
    metrics_payload: Optional[Dict[str, Any]] = None
    if candidate_step_path is not None and not bool(args.skip_metrics):
        metrics_path = (
            Path(args.metrics_json).resolve()
            if args.metrics_json
            else output_dir / f"{candidate_step_path.stem}_seed{int(args.seed)}.metrics.json"
        )
        compare_dir = (
            Path(args.compare_dir).resolve()
            if args.compare_dir
            else output_dir / f"compare_{candidate_step_path.stem}_seed{int(args.seed)}"
        )
        metrics_payload = run_full_visual_evaluation(
            reference_stl_path=reference_stl_path,
            step_path=candidate_step_path,
            features_path=features_path,
            output_metrics_path=metrics_path,
            compare_dir=compare_dir,
            visual_sample_size=int(args.visual_sample_size),
            eval_seed=int(args.seed),
            max_eval_stl_bytes=int(args.max_eval_stl_bytes),
        )

    visual_summary_path: Optional[Path] = None
    visual_payload: Optional[Dict[str, Any]] = None
    visual_dir = output_dir / f"visual_diag_{candidate_stl_path.stem}"
    if not bool(args.skip_visual_diagnostics):
        visual_summary_path = run_visual_diagnostics(
            features_path=features_path,
            reference_stl_path=reference_stl_path,
            candidate_stl_path=candidate_stl_path,
            output_dir=visual_dir,
            sample_count=int(args.sample_count),
            seed=int(args.seed),
            diff_threshold_mm=float(args.diff_threshold_mm),
        )
        visual_payload = load_json_if_exists(visual_summary_path)

    summary = {
        "features": str(features_path),
        "reference_stl": str(reference_stl_path),
        "candidate_step": str(candidate_step_path) if candidate_step_path is not None else None,
        "candidate_stl": str(candidate_stl_path),
        "metrics_json": str(metrics_path) if metrics_path is not None else None,
        "compare_dir": str(compare_dir) if compare_dir is not None else None,
        "visual_dir": str(visual_dir) if visual_summary_path is not None else None,
        "visual_summary_json": str(visual_summary_path) if visual_summary_path is not None else None,
        "metrics": {
            "front_overlap": float(metrics_payload.get("front_overlap")),
            "side_overlap": float(metrics_payload.get("side_overlap")),
            "spoke_overlap": float(metrics_payload.get("spoke_overlap")),
            "nn_mean_fwd_mm": float(metrics_payload.get("nn_mean_fwd_mm")),
            "nn_mean_bwd_mm": float(metrics_payload.get("nn_mean_bwd_mm")),
        }
        if metrics_payload is not None
        else None,
        "worst_members": visual_payload.get("worst_members") if isinstance(visual_payload, dict) else None,
    }
    summary_path = output_dir / "visual_evaluation_stage_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[*] stage summary: {summary_path}")
    if summary["metrics"] is not None:
        metrics = summary["metrics"]
        print(
            "[*] metrics: front={front_overlap:.4f} side={side_overlap:.4f} "
            "spoke={spoke_overlap:.4f} fwd={nn_mean_fwd_mm:.4f} bwd={nn_mean_bwd_mm:.4f}".format(**metrics)
        )
    if summary["worst_members"]:
        print("[*] worst visual members:")
        for row in summary["worst_members"][:6]:
            print(
                "    member={member_index} slot={slot_index} score={visual_error_score:.3f} "
                "unmatched={unmatched_ratio:.3f}".format(**row)
            )


if __name__ == "__main__":
    main()
