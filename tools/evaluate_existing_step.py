from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.evaluation_agent import EvaluationAgent
from tools.run_modelonly_patch_eval import build_spoke_zoom, compute_metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate an existing STEP artifact against the reference STL.")
    parser.add_argument("--step", required=True, help="STEP path")
    parser.add_argument("--features", required=True, help="Features JSON path")
    parser.add_argument("--stl", default=str(ROOT / "input" / "wheel.stl"), help="Reference STL path")
    parser.add_argument("--compare-stl", default=None, help="Optional fallback STL exported from STEP")
    parser.add_argument("--output-dir", required=True, help="Comparison bundle output directory")
    parser.add_argument("--metrics-out", required=True, help="Metrics JSON output path")
    parser.add_argument("--visual-sample-size", type=int, default=30000, help="Visualization and metrics sample count")
    parser.add_argument("--eval-seed", type=int, default=42, help="Deterministic sampling seed for visual/metric evaluation")
    parser.add_argument("--max-eval-stl-bytes", type=int, default=280 * 1024 * 1024, help="Max temporary STL size for evaluation")
    args = parser.parse_args()

    step_path = str(Path(args.step).resolve())
    features_path = str(Path(args.features).resolve())
    stl_path = str(Path(args.stl).resolve())
    output_dir = Path(args.output_dir).resolve()
    metrics_out = Path(args.metrics_out).resolve()
    compare_stl = str(Path(args.compare_stl).resolve()) if args.compare_stl else None

    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_out.parent.mkdir(parents=True, exist_ok=True)

    agent = EvaluationAgent(
        stl_path=stl_path,
        step_path=step_path,
        features_path=features_path,
        config={
            "visual_sample_size": int(args.visual_sample_size),
            "eval_seed": int(args.eval_seed),
            "step_mesh_fallback_path": compare_stl,
            "max_eval_stl_bytes": int(args.max_eval_stl_bytes),
        },
    )

    comparison_path = output_dir / "evaluation_comparison.png"
    agent.visualize_comparison(str(comparison_path))
    build_spoke_zoom(agent, output_dir / "evaluation_comparison_spoke_zoom.png")

    metrics = compute_metrics(agent)
    metrics["step_path"] = step_path
    metrics["features_path"] = features_path
    metrics["compare_dir"] = str(output_dir)
    metrics["compare_stl_path"] = compare_stl

    metrics_out.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[*] Comparison image: {comparison_path}")
    print(f"[*] Spoke zoom image: {output_dir / 'evaluation_comparison_spoke_zoom.png'}")
    print(f"[*] Metrics saved: {metrics_out}")
    print("[*] Metrics summary:")
    for key in (
        "front_overlap",
        "side_overlap",
        "spoke_overlap",
        "nn_mean_fwd_mm",
        "nn_mean_bwd_mm",
        "nn_p95_fwd_mm",
        "nn_p95_bwd_mm",
    ):
        if key in metrics:
            print(f"    {key}={metrics[key]}")


if __name__ == "__main__":
    main()
