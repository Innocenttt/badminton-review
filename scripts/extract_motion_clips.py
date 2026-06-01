#!/usr/bin/env python3
"""Extract short clips around motion frames."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_manifest(date: str) -> list[dict]:
    manifest_path = PROJECT_ROOT / "outputs" / date / "selected_frames" / "motion_frames_manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"Motion manifest does not exist: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required for clip extraction. Install ffmpeg and try again.")


def probe_duration(video_path: Path) -> Optional[float]:
    if shutil.which("ffprobe") is None:
        return None
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def clip_window(timestamp: float, before: float, after: float, duration: Optional[float]) -> tuple[float, float]:
    target_length = before + after
    start = max(0.0, timestamp - before)

    if duration is None:
        return start, target_length

    if timestamp < before:
        end = min(duration, target_length)
    elif timestamp + after > duration:
        end = duration
        start = max(0.0, end - target_length)
    else:
        end = min(duration, timestamp + after)

    return start, max(0.1, end - start)


def clip_name_from_frame(record: dict) -> str:
    frame_path = Path(record["path"])
    return f"{frame_path.stem}.mp4"


def extract_clip(video_path: Path, output_path: Path, start: float, duration: float, overwrite: bool) -> None:
    if output_path.exists() and not overwrite:
        return

    command = [
        "ffmpeg",
        "-y" if overwrite else "-n",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(video_path),
        "-t",
        f"{duration:.3f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {video_path.name}: {result.stderr.strip()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract 4-second clips around selected motion frames.")
    parser.add_argument("--date", required=True, help="Date folder, for example 2026-05-25")
    parser.add_argument("--before", type=float, default=2.0, help="Seconds before each motion timestamp")
    parser.add_argument("--after", type=float, default=2.0, help="Seconds after each motion timestamp")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing clip files")
    args = parser.parse_args()

    require_ffmpeg()
    records = load_manifest(args.date)
    video_dir = PROJECT_ROOT / "videos" / args.date
    output_dir = PROJECT_ROOT / "outputs" / args.date / "clips"
    output_dir.mkdir(parents=True, exist_ok=True)

    duration_cache: dict[str, Optional[float]] = {}
    clip_records: list[dict] = []

    for record in records:
        video_name = record.get("video")
        timestamp = float(record.get("time_seconds", 0))
        if not video_name:
            print(f"Skip record without video: {record}")
            continue

        video_path = video_dir / video_name
        if not video_path.exists():
            print(f"Skip missing source video: {video_path}")
            continue

        if video_name not in duration_cache:
            duration_cache[video_name] = probe_duration(video_path)

        start, clip_duration = clip_window(timestamp, args.before, args.after, duration_cache[video_name])
        output_path = output_dir / clip_name_from_frame(record)
        extract_clip(video_path, output_path, start, clip_duration, args.overwrite)

        clip_record = {
            "video": video_name,
            "time_seconds": timestamp,
            "clip_start_seconds": round(start, 3),
            "clip_duration_seconds": round(clip_duration, 3),
            "motion_score": record.get("motion_score"),
            "frame_path": record.get("path"),
            "clip_path": str(output_path.relative_to(PROJECT_ROOT)),
        }
        clip_records.append(clip_record)

    manifest_path = output_dir / "clips_manifest.json"
    existing_records = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
    if not clip_records and existing_records:
        print("No clips were written; keeping existing clips_manifest.json unchanged.")
        print(f"Manifest kept: {manifest_path}")
        return 0

    manifest_path.write_text(json.dumps(clip_records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Clips written: {len(clip_records)}")
    print(f"Manifest written: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
