#!/usr/bin/env python3
"""Clean generated intermediate files for one badminton review date."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRS = {
    "frames": "frames",
    "selected_frames": "selected_frames",
    "clips": "clips",
    "filtered_frames": "filtered_frames",
    "filtered_clips": "filtered_clips",
    "review_pack": "review_pack",
}
KEEP_FILES = [
    "review_pack.zip",
    "review_prompt.md",
    "report_template.md",
    "score.json",
    "progress.md",
    "filter_report.md",
    "filter_manifest.json",
    "manual_labels.csv",
    "review_pack_index.md",
]
VIDEO_EXTENSIONS = {".mp4", ".mov"}
MACOS_PATTERNS = [".DS_Store", "._*"]


def format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def path_stats(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    if path.is_file():
        return 1, path.stat().st_size
    files = [item for item in path.rglob("*") if item.is_file()]
    return len(files), sum(item.stat().st_size for item in files)


def remove_path(path: Path, dry_run: bool) -> tuple[int, int]:
    count, size = path_stats(path)
    if count == 0 and not path.exists():
        return 0, 0
    if not dry_run:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    return count, size


def remove_macos_junk(root: Path, dry_run: bool) -> tuple[int, int]:
    total_count = 0
    total_size = 0
    for pattern in MACOS_PATTERNS:
        for path in root.rglob(pattern):
            count, size = remove_path(path, dry_run)
            total_count += count
            total_size += size
    for path in root.rglob("__MACOSX"):
        count, size = remove_path(path, dry_run)
        total_count += count
        total_size += size
    return total_count, total_size


def collect_raw_videos(date: str) -> list[Path]:
    video_dir = PROJECT_ROOT / "videos" / date
    if not video_dir.exists():
        return []
    return sorted(path for path in video_dir.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS)


def print_item(action: str, path: Path, count: int, size: int) -> None:
    relative = path.relative_to(PROJECT_ROOT) if path.is_absolute() else path
    print(f"- {action} {relative} : {count} files, {format_bytes(size)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean generated outputs for a review date.")
    parser.add_argument("--date", required=True, help="Date folder, for example 2026-05-25")
    parser.add_argument("--keep-frames", action="store_true")
    parser.add_argument("--keep-selected-frames", action="store_true")
    parser.add_argument("--keep-clips", action="store_true")
    parser.add_argument("--keep-filtered", action="store_true")
    parser.add_argument("--keep-review-pack-folder", action="store_true")
    parser.add_argument("--delete-review-pack-zip", action="store_true")
    parser.add_argument("--delete-raw-videos", action="store_true")
    parser.add_argument("--archive-mode", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    output_root = PROJECT_ROOT / "outputs" / args.date
    review_zip = output_root / "review_pack.zip"
    review_zip_exists_before = review_zip.exists()
    before_count, before_size = path_stats(output_root)
    total_freed = 0
    print(f"Cleanup summary for {args.date}:")
    if args.dry_run:
        print("(dry-run: no files will be deleted)")
    print(f"- Before cleanup outputs/{args.date}/ : {before_count} files, {format_bytes(before_size)}")

    mac_count, mac_size = remove_macos_junk(PROJECT_ROOT, args.dry_run)
    if mac_count:
        print(f"- Deleted macOS junk : {mac_count} files, {format_bytes(mac_size)}")
        total_freed += mac_size

    targets: list[Path] = []
    if not args.keep_frames:
        targets.append(output_root / OUTPUT_DIRS["frames"])
    if not args.keep_selected_frames:
        targets.append(output_root / OUTPUT_DIRS["selected_frames"])
        targets.append(output_root / "selected_frames.zip")
    if not args.keep_clips:
        targets.append(output_root / OUTPUT_DIRS["clips"])
    if not args.keep_filtered:
        targets.extend([output_root / OUTPUT_DIRS["filtered_frames"], output_root / OUTPUT_DIRS["filtered_clips"]])
    if not args.keep_review_pack_folder:
        targets.append(output_root / OUTPUT_DIRS["review_pack"])
    if args.delete_review_pack_zip:
        targets.append(review_zip)
    targets.extend([PROJECT_ROOT / "outputs" / "frames", PROJECT_ROOT / "outputs" / "clips"])

    for path in targets:
        if not path.exists():
            continue
        count, size = remove_path(path, args.dry_run)
        print_item("Deleted", path, count, size)
        total_freed += size

    if args.delete_raw_videos:
        if not review_zip_exists_before:
            print("- Skipped raw videos: review_pack.zip does not exist")
        else:
            for video_path in collect_raw_videos(args.date):
                count, size = remove_path(video_path, args.dry_run)
                print_item("Deleted", video_path, count, size)
                total_freed += size

    if review_zip.exists() and not args.delete_review_pack_zip:
        count, size = path_stats(review_zip)
        print_item("Kept", review_zip, count, size)

    kept_names = [name for name in KEEP_FILES if (output_root / name).exists()]
    if kept_names:
        print(f"- Kept {', '.join(kept_names)}")
    after_count, after_size = path_stats(output_root) if not args.dry_run else (before_count, before_size)
    print(f"- After cleanup outputs/{args.date}/ : {after_count} files, {format_bytes(after_size)}")
    print(f"- Total freed: {format_bytes(total_freed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
