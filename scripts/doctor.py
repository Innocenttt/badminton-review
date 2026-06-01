#!/usr/bin/env python3
"""Check badminton-review project health."""

from __future__ import annotations

import argparse
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_SCRIPTS = [
    "extract_frames.py",
    "detect_motion_frames.py",
    "extract_motion_clips.py",
    "filter_review_assets.py",
    "generate_review_prompt.py",
    "select_review_pack.py",
    "compare_scores.py",
    "cleanup_outputs.py",
    "doctor.py",
]
VIDEO_EXTENSIONS = {".mp4", ".mov"}


def format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def size_of(paths: list[Path]) -> int:
    total = 0
    for path in paths:
        if path.is_file():
            total += path.stat().st_size
        elif path.is_dir():
            total += sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    return total


def find_macos_junk() -> list[Path]:
    junk: list[Path] = []
    for pattern in [".DS_Store", "._*"]:
        junk.extend(PROJECT_ROOT.rglob(pattern))
    junk.extend(PROJECT_ROOT.rglob("__MACOSX"))
    return sorted(set(junk))


def status(ok: bool, message: str) -> None:
    print(f"{'OK' if ok else 'WARN'} {message}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check project structure and generated artifacts.")
    parser.add_argument("--date", required=True, help="Date folder, for example 2026-05-25")
    args = parser.parse_args()

    print("Project doctor report:")
    requirements_ok = (PROJECT_ROOT / "requirements.txt").exists()
    config_ok = (PROJECT_ROOT / "config" / "player_profile.json").exists() and (
        PROJECT_ROOT / "config" / "review_metrics.md"
    ).exists()
    scripts_missing = [name for name in CORE_SCRIPTS if not (PROJECT_ROOT / "scripts" / name).exists()]
    scripts_ok = not scripts_missing

    status(requirements_ok, "requirements.txt exists" if requirements_ok else "requirements.txt missing")
    status(config_ok, "config complete" if config_ok else "config missing player_profile.json or review_metrics.md")
    status(scripts_ok, "scripts complete" if scripts_ok else f"missing scripts: {', '.join(scripts_missing)}")

    video_dir = PROJECT_ROOT / "videos" / args.date
    videos = sorted(path for path in video_dir.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS) if video_dir.exists() else []
    status(video_dir.exists(), f"videos/{args.date}/ exists" if video_dir.exists() else f"videos/{args.date}/ missing")
    status(bool(videos), f"videos/{args.date}/ has {len(videos)} MP4/MOV files" if videos else "no MP4/MOV videos found")

    output_dir = PROJECT_ROOT / "outputs" / args.date
    status(output_dir.exists(), f"outputs/{args.date}/ exists" if output_dir.exists() else f"outputs/{args.date}/ missing")
    for name in ["review_pack.zip", "score.json", "manual_labels.csv"]:
        status((output_dir / name).exists(), f"outputs/{args.date}/{name} exists" if (output_dir / name).exists() else f"outputs/{args.date}/{name} missing")

    old_dirs = [PROJECT_ROOT / "outputs" / "frames", PROJECT_ROOT / "outputs" / "clips"]
    found_old_dirs = [path for path in old_dirs if path.exists()]
    status(not found_old_dirs, "no old top-level outputs/frames or outputs/clips" if not found_old_dirs else f"old output dirs found: {', '.join(str(path.relative_to(PROJECT_ROOT)) for path in found_old_dirs)}")

    junk = find_macos_junk()
    status(not junk, "no macOS junk files found" if not junk else f"found macOS junk files: {len(junk)}")

    large_100mb = [path for path in PROJECT_ROOT.rglob("*") if path.is_file() and path.stat().st_size > 100 * 1024 * 1024]
    large_1gb = [path for path in large_100mb if path.stat().st_size > 1024 * 1024 * 1024]
    print(f"Large files >100MB: {len(large_100mb)}")
    for path in large_100mb[:20]:
        print(f"- {path.relative_to(PROJECT_ROOT)} : {format_bytes(path.stat().st_size)}")
    print(f"Large files >1GB: {len(large_1gb)}")
    for path in large_1gb[:20]:
        print(f"- {path.relative_to(PROJECT_ROOT)} : {format_bytes(path.stat().st_size)}")

    raw_video_size = size_of(videos)
    if videos:
        print(f"Raw videos occupy: {format_bytes(raw_video_size)}")

    print("Recommendation:")
    print(f"Run: python3 scripts/cleanup_outputs.py --date {args.date} --dry-run")
    if (output_dir / "review_pack.zip").exists():
        print(f"Then: python3 scripts/cleanup_outputs.py --date {args.date} --archive-mode")
        if videos:
            print("Raw videos can be deleted only after you confirm review_pack.zip is enough for long-term review.")
    else:
        print("Missing review_pack.zip: generate it before archive cleanup or raw video deletion.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
