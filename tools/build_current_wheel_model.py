from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


CURRENT_FEATURES = ROOT / "output" / "wheel_base_from_features_nospokes_20260422_135255_features.json"
CURRENT_BASE_STEP = ROOT / "output" / "wheel_base_from_features_nospokes_20260422_135255.step"
CURRENT_REFERENCE_STL = ROOT / "input" / "wheel.stl"


def build_command(output_stem: str) -> list[str]:
    output_step = ROOT / "output" / f"{output_stem}.step"
    output_stl = ROOT / "output" / f"{output_stem}.stl"
    meta_out = ROOT / "output" / f"{output_stem}.meta.json"
    return [
        sys.executable,
        str(ROOT / "tools" / "run_spoke_extrude_refine_array_model.py"),
        "--allow-legacy-engine-direct-use",
        "--features",
        str(CURRENT_FEATURES),
        "--base-step",
        str(CURRENT_BASE_STEP),
        "--reference-stl",
        str(CURRENT_REFERENCE_STL),
        "--output-step",
        str(output_step),
        "--output-stl",
        str(output_stl),
        "--meta-out",
        str(meta_out),
        "--template-member-index",
        "2",
        "--base-profile-mode",
        "rectangle",
        "--base-rect-z-margin-mm",
        "0.5",
        "--base-root-pad-mm",
        "18.0",
        "--base-tip-pad-mm",
        "30.0",
        "--face-mode",
        "positive_z",
        "--refine-span-mode",
        "planform_full",
        "--refine-gap-fill-mm",
        "12.0",
        "--refine-dense-spacing-mm",
        "5.0",
        "--refine-dense-min-gap-mm",
        "1.5",
        "--planform-clip",
        "--planform-tip-pad-mm",
        "18.0",
        "--planform-extension-steps",
        "4",
        "--planform-span-mode",
        "full",
        "--planform-span-root-margin-mm",
        "0.0",
        "--planform-span-tip-margin-mm",
        "0.0",
        "--planform-full-span-percentile",
        "0.4",
        "--refine-planform-match",
        "--refine-planform-match-start",
        "0.0",
        "--refine-planform-match-end",
        "1.0",
        "--refine-planform-width-only",
        "--refine-planform-expand-only",
        "--refine-planform-min-expand-mm",
        "0.4",
        "--revolved-boundary-cut",
        "--boundary-outer-mode",
        "none",
        "--post-rim-curve-boundary-cut",
        "--post-rim-curve-boundary-offset-mm",
        "-1.2",
        "--post-rim-curve-boundary-samples",
        "16",
        "--post-rim-curve-boundary-z-margin-mm",
        "2.0",
        "--post-use-production-hub-cuts",
        "--tip-bridge-mode",
        "late",
        "--tip-bridge-ratio",
        "0.94",
        "--trim-mode",
        "root_intersection_replace",
        "--trim-root-intersection-ratio",
        "0.48",
        "--keep-base-outside-refine-sections",
        "--replace-tail-overlap-mm",
        "0.0",
        "--refine-align-mode",
        "original",
        "--refine-lower-mid-start",
        "0.34",
        "--refine-lower-mid-end",
        "0.82",
        "--refine-upper-strength",
        "0.0",
        "--refine-upper-mid-start",
        "0.3",
        "--refine-upper-mid-end",
        "0.92",
        "--repair-tail-z-outliers",
        "--tail-z-drop-threshold-mm",
        "18.0",
        "--prefer-member-submesh-sections",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the current accepted wheel model route.")
    parser.add_argument("--output-stem", default="current_wheel_model", help="Output filename stem under output/.")
    parser.add_argument("--print-command", action="store_true", help="Print the exact command instead of running it.")
    args = parser.parse_args()

    command = build_command(str(args.output_stem))
    if args.print_command:
        print(" ".join(f'"{part}"' if " " in part else part for part in command))
        return
    subprocess.run(command, cwd=str(ROOT), check=True)


if __name__ == "__main__":
    main()
