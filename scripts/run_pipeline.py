#!/usr/bin/env python3
"""Run the badminton review pipeline for one date."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def cv2_capable_python() -> str:
    candidates = [
        sys.executable,
        "python3",
        "/Library/Developer/CommandLineTools/usr/bin/python3",
        "/usr/bin/python3",
        "/opt/homebrew/bin/python3",
    ]
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        result = subprocess.run(
            [candidate, "-c", "import cv2"],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
        )
        if result.returncode == 0:
            return candidate
    return sys.executable


def run_step(name: str, command: list[str]) -> None:
    print(f"\n==> Starting: {name}")
    print(" ".join(command))
    result = subprocess.run(command, cwd=PROJECT_ROOT, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())
    if result.returncode != 0:
        print(f"\nFAILED: {name}")
        print(f"Command: {' '.join(command)}")
        raise SystemExit(result.returncode)
    print(f"<== Finished: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full badminton review pipeline.")
    parser.add_argument("--date", required=True, help="Date folder, for example 2026-05-25")
    parser.add_argument("--test-single-video-ok", action="store_true", help="Allow a single-source test pack")
    parser.add_argument("--use-filtered", action="store_true", default=True, help="Use filtered assets for review pack")
    parser.add_argument("--skip-start-seconds", type=float, default=10.0)
    parser.add_argument("--max-frames", type=int, default=20)
    parser.add_argument("--max-clips", type=int, default=10)
    parser.add_argument("--max-zip-mb", type=float, default=100.0)
    parser.add_argument("--skip-cleanup-suggestion", action="store_true")
    args = parser.parse_args()

    py = cv2_capable_python()
    print(f"Using Python: {py}")
    steps = [
        ("doctor", [py, "scripts/doctor.py", "--date", args.date]),
        ("extract frames", [py, "scripts/extract_frames.py", "--date", args.date]),
        ("detect motion frames", [py, "scripts/detect_motion_frames.py", "--date", args.date]),
        ("extract motion clips", [py, "scripts/extract_motion_clips.py", "--date", args.date]),
        (
            "filter review assets",
            [
                py,
                "scripts/filter_review_assets.py",
                "--date",
                args.date,
                "--skip-start-seconds",
                str(args.skip_start_seconds),
            ],
        ),
        ("generate review prompt/template", [py, "scripts/generate_review_prompt.py", "--date", args.date]),
    ]

    pack_command = [
        py,
        "scripts/select_review_pack.py",
        "--date",
        args.date,
        "--max-frames",
        str(args.max_frames),
        "--max-clips",
        str(args.max_clips),
        "--max-zip-mb",
        str(args.max_zip_mb),
    ]
    if args.use_filtered:
        pack_command.append("--use-filtered")
    if args.test_single_video_ok:
        pack_command.append("--test-single-video-ok")
    steps.append(("select review pack", pack_command))
    steps.append(("compare scores", [py, "scripts/compare_scores.py", "--current", args.date]))

    for name, command in steps:
        run_step(name, command)

    zip_path = PROJECT_ROOT / "outputs" / args.date / "review_pack.zip"
    print(f"\nReview pack ready: {zip_path}")
    if not args.skip_cleanup_suggestion:
        print("\nAfter reviewing/uploading, consider:")
        print(f"python3 scripts/cleanup_outputs.py --date {args.date} --dry-run")
        print(f"python3 scripts/cleanup_outputs.py --date {args.date} --archive-mode")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
