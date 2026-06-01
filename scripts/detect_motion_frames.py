#!/usr/bin/env python3
"""Select representative frames with obvious visual motion changes."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import cv2
import numpy as np


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


def preprocess(frame: np.ndarray) -> np.ndarray:
    resized = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(gray, (5, 5), 0)


def motion_score(previous: np.ndarray, current: np.ndarray) -> float:
    diff = cv2.absdiff(previous, current)
    _, threshold = cv2.threshold(diff, 24, 255, cv2.THRESH_BINARY)
    changed_ratio = cv2.countNonZero(threshold) / threshold.size
    mean_delta = float(np.mean(diff)) / 255.0
    return round(changed_ratio * 0.75 + mean_delta * 0.25, 6)


def video_duration(cap: cv2.VideoCapture) -> float:
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    return frame_count / fps if fps > 0 and frame_count > 0 else 0


def select_motion_frames(
    video_path: Path,
    output_dir: Path,
    sample_seconds: float,
    threshold: float,
    cooldown_seconds: float,
    max_frames: int,
) -> list[dict]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"Skip unreadable video: {video_path}")
        return []

    duration = video_duration(cap)
    prefix = compact_video_name(video_path)
    previous_processed = None
    candidates: list[tuple[float, float, np.ndarray]] = []
    seconds = 0.0

    while duration == 0 or seconds <= duration:
        frame = read_frame_at(cap, seconds)
        if frame is None:
            break

        processed = preprocess(frame)
        if previous_processed is not None:
            score = motion_score(previous_processed, processed)
            candidates.append((score, seconds, frame.copy()))

        previous_processed = processed
        seconds += sample_seconds

    cap.release()
    if not candidates:
        print(f"{video_path.name}: no motion candidates")
        return []

    selected: list[tuple[float, float, np.ndarray]] = []
    last_saved_time = -cooldown_seconds
    for score, seconds, frame in candidates:
        if score >= threshold and seconds - last_saved_time >= cooldown_seconds:
            selected.append((score, seconds, frame))
            last_saved_time = seconds
        if len(selected) >= max_frames:
            break

    if not selected:
        selected = sorted(candidates, key=lambda item: item[0], reverse=True)[: min(max_frames, 8)]
        selected = sorted(selected, key=lambda item: item[1])

    records: list[dict] = []
    for index, (score, seconds, frame) in enumerate(selected, start=1):
        rounded_seconds = int(round(seconds))
        file_name = f"{prefix}_motion_t{rounded_seconds:04d}_frame{index:03d}.jpg"
        output_path = output_dir / file_name
        cv2.imwrite(str(output_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        records.append(
            {
                "video": video_path.name,
                "time_seconds": round(seconds, 2),
                "motion_score": score,
                "path": str(output_path.relative_to(PROJECT_ROOT)),
            }
        )

    print(f"{video_path.name}: selected {len(records)} motion frames")
    return records


def write_markdown_index(records: list[dict], output_path: Path, date: str) -> None:
    lines = [
        f"# Motion Frames Index | {date}",
        "",
        "These frames are selected by simple frame-difference motion detection.",
        "Use them as candidates for manual review, not as automatic technique judgments.",
        "",
    ]
    for item in records:
        lines.append(
            f"- `{item['path']}` | video: `{item['video']}` | t={item['time_seconds']}s | score={item['motion_score']}"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect simple motion-change frames by date.")
    parser.add_argument("--date", required=True, help="Date folder, for example 2026-05-25")
    parser.add_argument("--sample-seconds", type=float, default=0.5, help="Sampling interval for motion scan")
    parser.add_argument("--threshold", type=float, default=0.035, help="Motion score threshold")
    parser.add_argument("--cooldown", type=float, default=2.0, help="Minimum seconds between selected frames")
    parser.add_argument("--max-per-video", type=int, default=30, help="Maximum selected frames per video")
    args = parser.parse_args()

    video_dir = PROJECT_ROOT / "videos" / args.date
    output_dir = PROJECT_ROOT / "outputs" / args.date / "selected_frames"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not video_dir.exists():
        raise SystemExit(f"Video folder does not exist: {video_dir}")

    videos = list_videos(video_dir)
    if not videos:
        raise SystemExit(f"No videos found in: {video_dir}")

    records: list[dict] = []
    for video_path in videos:
        records.extend(
            select_motion_frames(
                video_path,
                output_dir,
                args.sample_seconds,
                args.threshold,
                args.cooldown,
                args.max_per_video,
            )
        )

    json_path = output_dir / "motion_frames_manifest.json"
    json_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown_index(records, output_dir / "motion_frames_index.md", args.date)
    print(f"Manifest written: {json_path}")
    print(f"Total selected motion frames: {len(records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
