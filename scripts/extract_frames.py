#!/usr/bin/env python3
"""Extract one frame every N seconds from all videos in a date folder."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import cv2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}


def compact_video_name(path: Path) -> str:
    match = re.search(r"DJI_\d+_(\d{4})", path.stem, flags=re.IGNORECASE)
    if match:
        return f"DJI_{match.group(1)}"
    return re.sub(r"[^A-Za-z0-9]+", "_", path.stem).strip("_")


def list_videos(video_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in video_dir.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    )


def read_frame_at(cap: cv2.VideoCapture, seconds: float):
    cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
    ok, frame = cap.read()
    if ok:
        return frame
    return None


def extract_for_video(video_path: Path, output_dir: Path, interval_seconds: float) -> list[dict]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"Skip unreadable video: {video_path}")
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration = frame_count / fps if fps > 0 and frame_count > 0 else 0
    prefix = compact_video_name(video_path)
    saved: list[dict] = []
    seconds = interval_seconds
    frame_number = 1

    while duration == 0 or seconds <= duration:
        frame = read_frame_at(cap, seconds)
        if frame is None:
            break

        rounded_seconds = int(round(seconds))
        file_name = f"{prefix}_t{rounded_seconds:04d}_frame{frame_number:03d}.jpg"
        output_path = output_dir / file_name
        cv2.imwrite(str(output_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        saved.append(
            {
                "video": video_path.name,
                "time_seconds": round(seconds, 2),
                "frame_index": frame_number,
                "path": str(output_path.relative_to(PROJECT_ROOT)),
            }
        )

        frame_number += 1
        seconds += interval_seconds

    cap.release()
    print(f"{video_path.name}: saved {len(saved)} frames")
    return saved


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract badminton review frames by date.")
    parser.add_argument("--date", required=True, help="Date folder, for example 2026-05-25")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between frames")
    args = parser.parse_args()

    video_dir = PROJECT_ROOT / "videos" / args.date
    output_dir = PROJECT_ROOT / "outputs" / args.date / "frames"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not video_dir.exists():
        raise SystemExit(f"Video folder does not exist: {video_dir}")

    videos = list_videos(video_dir)
    if not videos:
        raise SystemExit(f"No videos found in: {video_dir}")

    manifest: list[dict] = []
    for video_path in videos:
        manifest.extend(extract_for_video(video_path, output_dir, args.interval))

    manifest_path = output_dir / "frames_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Manifest written: {manifest_path}")
    print(f"Total frames saved: {len(manifest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
