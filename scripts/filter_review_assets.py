#!/usr/bin/env python3
"""Filter review frames and clips with simple explainable quality rules."""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Optional

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REASON_KEYS = [
    "timestamp_too_early",
    "camera_adjustment",
    "possible_rotation_error",
    "rotation_warning",
    "possible_occlusion_or_too_close",
    "too_close",
    "occlusion_warning",
    "no_full_body",
    "low_motion",
    "low_review_value",
    "walking_only",
    "not_badminton_action",
]


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def safe_float(value, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def relative(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


def read_image(path: Path) -> Optional[np.ndarray]:
    image = cv2.imread(str(path))
    if image is None:
        print(f"Skip unreadable image: {path}")
    return image


def frame_metrics(image: np.ndarray, motion_score: Optional[float]) -> dict:
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized_gray = cv2.resize(gray, (320, 180), interpolation=cv2.INTER_AREA)
    resized_bgr = cv2.resize(image, (320, 180), interpolation=cv2.INTER_AREA)
    edges = cv2.Canny(resized_gray, 60, 160)
    edge_ratio = cv2.countNonZero(edges) / edges.size
    blur_score = float(cv2.Laplacian(resized_gray, cv2.CV_64F).var())
    brightness_mean = float(np.mean(resized_gray))
    brightness_std = float(np.std(resized_gray))
    color_std = float(np.mean(np.std(resized_bgr, axis=(0, 1))))
    foreground_ratio = min(1.0, max(0.0, safe_float(motion_score, 0.0) or 0.0))

    return {
        "width": width,
        "height": height,
        "aspect_ratio": round(width / height, 4) if height else None,
        "motion_score": motion_score,
        "foreground_ratio": round(foreground_ratio, 6),
        "blur_score": round(blur_score, 3),
        "brightness_mean": round(brightness_mean, 3),
        "brightness_std": round(brightness_std, 3),
        "color_std": round(color_std, 3),
        "edge_ratio": round(edge_ratio, 6),
    }


def motion_mask(previous_gray: np.ndarray, current_gray: np.ndarray) -> np.ndarray:
    diff = cv2.absdiff(previous_gray, current_gray)
    _, mask = cv2.threshold(diff, 24, 255, cv2.THRESH_BINARY)
    return mask


def center_and_edge_ratios(mask: np.ndarray) -> tuple[float, float]:
    height, width = mask.shape[:2]
    total_motion = cv2.countNonZero(mask)
    if total_motion == 0:
        return 0.0, 0.0

    center = np.zeros_like(mask)
    y1, y2 = int(height * 0.18), int(height * 0.82)
    x1, x2 = int(width * 0.18), int(width * 0.82)
    center[y1:y2, x1:x2] = 255
    center_motion = cv2.countNonZero(cv2.bitwise_and(mask, center))
    edge_motion = total_motion - center_motion
    return center_motion / total_motion, edge_motion / total_motion


def sample_clip_metrics(path: Path) -> Optional[dict]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        print(f"Skip unreadable clip: {path}")
        return None

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    step = max(1, int(round(fps * 0.5)))

    previous_gray = None
    motion_ratios: list[float] = []
    center_ratios: list[float] = []
    edge_ratios: list[float] = []
    brightness_values: list[float] = []
    blur_values: list[float] = []
    color_std_values: list[float] = []
    edge_density_values: list[float] = []

    index = 0
    sampled = 0
    while frame_count == 0 or index < frame_count:
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = cap.read()
        if not ok:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        resized_gray = cv2.resize(gray, (320, 180), interpolation=cv2.INTER_AREA)
        resized_bgr = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
        brightness_values.append(float(np.mean(resized_gray)))
        blur_values.append(float(cv2.Laplacian(resized_gray, cv2.CV_64F).var()))
        color_std_values.append(float(np.mean(np.std(resized_bgr, axis=(0, 1)))))
        edge_density = cv2.countNonZero(cv2.Canny(resized_gray, 60, 160)) / resized_gray.size
        edge_density_values.append(edge_density)

        if previous_gray is not None:
            mask = motion_mask(previous_gray, resized_gray)
            ratio = cv2.countNonZero(mask) / mask.size
            center_ratio, edge_ratio = center_and_edge_ratios(mask)
            motion_ratios.append(ratio)
            center_ratios.append(center_ratio)
            edge_ratios.append(edge_ratio)

        previous_gray = resized_gray
        sampled += 1
        index += step
        if sampled >= 12:
            break

    cap.release()
    if sampled == 0:
        return None

    average_motion = float(np.mean(motion_ratios)) if motion_ratios else 0.0
    max_motion = float(np.max(motion_ratios)) if motion_ratios else 0.0
    return {
        "width": width,
        "height": height,
        "aspect_ratio": round(width / height, 4) if height else None,
        "motion_score": None,
        "foreground_ratio": round(max_motion, 6),
        "average_motion_ratio": round(average_motion, 6),
        "center_motion_share": round(float(np.mean(center_ratios)) if center_ratios else 0.0, 6),
        "edge_motion_share": round(float(np.mean(edge_ratios)) if edge_ratios else 0.0, 6),
        "blur_score": round(float(np.mean(blur_values)), 3),
        "brightness_mean": round(float(np.mean(brightness_values)), 3),
        "brightness_std": round(float(np.std(brightness_values)), 3),
        "color_std": round(float(np.mean(color_std_values)), 3),
        "edge_ratio": round(float(np.mean(edge_density_values)), 6),
    }


def quality_reasons(
    metrics: dict,
    timestamp: float,
    skip_start_seconds: float,
    min_motion_score: Optional[float],
    max_foreground_ratio: float,
    keep_rotation_warning: bool,
    asset_type: str,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    reject_reasons: list[str] = []

    def add(reason: str, reject: bool = True) -> None:
        reasons.append(reason)
        if reject:
            reject_reasons.append(reason)

    if timestamp < skip_start_seconds:
        add("timestamp_too_early")
        add("camera_adjustment")

    width = metrics.get("width") or 0
    height = metrics.get("height") or 0
    if height > width:
        add("possible_rotation_error", reject=not keep_rotation_warning)
        add("rotation_warning", reject=not keep_rotation_warning)

    foreground_ratio = safe_float(metrics.get("foreground_ratio"), 0.0) or 0.0
    edge_ratio = safe_float(metrics.get("edge_ratio"), 0.0) or 0.0
    color_std = safe_float(metrics.get("color_std"), 0.0) or 0.0
    blur_score = safe_float(metrics.get("blur_score"), 0.0) or 0.0
    brightness_mean = safe_float(metrics.get("brightness_mean"), 128.0) or 128.0

    visually_flat = edge_ratio < 0.006 or color_std < 7 or blur_score < 5
    abnormal_brightness = brightness_mean < 20 or brightness_mean > 238
    if foreground_ratio > max_foreground_ratio or (visually_flat and abnormal_brightness):
        add("possible_occlusion_or_too_close")
        add("occlusion_warning")
    if foreground_ratio > max_foreground_ratio:
        add("too_close")

    motion_floor = min_motion_score
    if motion_floor is None:
        motion_floor = 0.015 if asset_type == "clip" else 0.03

    if asset_type == "frame":
        motion_score = safe_float(metrics.get("motion_score"), 0.0) or 0.0
        if motion_score < motion_floor:
            add("low_motion")
    else:
        average_motion = safe_float(metrics.get("average_motion_ratio"), 0.0) or 0.0
        edge_motion_share = safe_float(metrics.get("edge_motion_share"), 0.0) or 0.0
        center_motion_share = safe_float(metrics.get("center_motion_share"), 0.0) or 0.0
        if average_motion < motion_floor:
            add("low_motion")
            add("low_review_value")
        if center_motion_share < 0.35 and edge_motion_share > 0.65:
            add("no_full_body")
            add("low_review_value")
        if edge_motion_share > 0.72 and average_motion < 0.08:
            add("walking_only")
            add("not_badminton_action")
        if foreground_ratio > max_foreground_ratio:
            add("low_review_value")

    return ("reject" if reject_reasons else "keep"), reasons


def frame_record(record: dict, args: argparse.Namespace) -> Optional[dict]:
    source_path = PROJECT_ROOT / record.get("path", "")
    image = read_image(source_path)
    if image is None:
        return None
    motion_score = safe_float(record.get("motion_score"), 0.0)
    timestamp = safe_float(record.get("time_seconds"), 0.0) or 0.0
    metrics = frame_metrics(image, motion_score)
    decision, reasons = quality_reasons(
        metrics,
        timestamp,
        args.skip_start_seconds,
        args.min_motion_score,
        args.max_foreground_ratio,
        args.keep_rotation_warning,
        "frame",
    )
    return {
        "filename": source_path.name,
        "asset_type": "frame",
        "source_video": record.get("video"),
        "timestamp": timestamp,
        "decision": decision,
        "reasons": reasons,
        "metrics": metrics,
        "source_path": relative(source_path),
        "filtered_path": f"outputs/{args.date}/filtered_frames/{source_path.name}",
    }


def clip_record(record: dict, args: argparse.Namespace) -> Optional[dict]:
    source_path = PROJECT_ROOT / record.get("clip_path", "")
    metrics = sample_clip_metrics(source_path)
    if metrics is None:
        return None
    metrics["motion_score"] = record.get("motion_score")
    timestamp = safe_float(record.get("time_seconds"), 0.0) or 0.0
    decision, reasons = quality_reasons(
        metrics,
        timestamp,
        args.skip_start_seconds,
        args.min_motion_score,
        args.max_foreground_ratio,
        args.keep_rotation_warning,
        "clip",
    )
    return {
        "filename": source_path.name,
        "asset_type": "clip",
        "source_video": record.get("video"),
        "timestamp": timestamp,
        "decision": decision,
        "reasons": reasons,
        "metrics": metrics,
        "source_path": relative(source_path),
        "filtered_path": f"outputs/{args.date}/filtered_clips/{source_path.name}",
        "frame_path": record.get("frame_path"),
    }


def copy_kept_assets(items: list[dict], target_dir: Path, dry_run: bool) -> None:
    if dry_run:
        return
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    for item in items:
        if item["decision"] != "keep":
            continue
        source_path = PROJECT_ROOT / item["source_path"]
        target_path = target_dir / item["filename"]
        if source_path.exists():
            shutil.copy2(source_path, target_path)


def write_filtered_manifests(output_root: Path, items: list[dict], dry_run: bool) -> None:
    if dry_run:
        return

    frame_records = [
        {
            "video": item["source_video"],
            "time_seconds": item["timestamp"],
            "motion_score": item["metrics"].get("motion_score"),
            "path": item["filtered_path"],
            "filter_reasons": item["reasons"],
        }
        for item in items
        if item["asset_type"] == "frame" and item["decision"] == "keep"
    ]
    clip_records = [
        {
            "video": item["source_video"],
            "time_seconds": item["timestamp"],
            "motion_score": item["metrics"].get("motion_score"),
            "frame_path": item.get("frame_path"),
            "clip_path": item["filtered_path"],
            "filter_reasons": item["reasons"],
        }
        for item in items
        if item["asset_type"] == "clip" and item["decision"] == "keep"
    ]

    (output_root / "filtered_frames" / "filtered_frames_manifest.json").write_text(
        json.dumps(frame_records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_root / "filtered_clips" / "filtered_clips_manifest.json").write_text(
        json.dumps(clip_records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def report_lines(date: str, items: list[dict]) -> list[str]:
    frame_items = [item for item in items if item["asset_type"] == "frame"]
    clip_items = [item for item in items if item["asset_type"] == "clip"]
    kept_frames = [item for item in frame_items if item["decision"] == "keep"]
    kept_clips = [item for item in clip_items if item["decision"] == "keep"]
    reason_counts = Counter(reason for item in items for reason in item["reasons"])

    lines = [
        f"# Review Assets Filter Report | {date}",
        "",
        "## 总览",
        f"- 原始关键帧数量：{len(frame_items)}",
        f"- 原始短片段数量：{len(clip_items)}",
        f"- 保留关键帧数量：{len(kept_frames)}",
        f"- 保留短片段数量：{len(kept_clips)}",
        f"- 过滤关键帧数量：{len(frame_items) - len(kept_frames)}",
        f"- 过滤短片段数量：{len(clip_items) - len(kept_clips)}",
        "",
        "## 过滤原因统计",
    ]
    for reason in REASON_KEYS:
        lines.append(f"- {reason}: {reason_counts.get(reason, 0)}")

    lines.extend(["", "## 建议"])
    if len(kept_frames) < 20 or len(kept_clips) < 10:
        lines.extend(
            [
                "- 保留素材偏少，可以降低 `skip-start-seconds`。",
                "- 可以降低 motion threshold 或不传 `--min-motion-score`。",
                "- 检查相机摆放，避免开头调相机、竖屏、遮挡或距离太近。",
                "- 必要时手动把关键帧加入 `review_pack`。",
            ]
        )
    else:
        lines.append("- 保留素材数量足够，可以继续生成 review_pack。")

    lines.extend(
        [
            "",
            "## 说明",
            "- 本过滤器只做简单质量筛选，不判断技术动作对错。",
            "- 原始素材不会被删除；保留素材会复制到 `filtered_frames/` 和 `filtered_clips/`。",
            "- 如果某些规则误伤，可以调低阈值或使用 `--keep-rotation-warning`。",
        ]
    )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Filter review frames and clips before building review_pack.")
    parser.add_argument("--date", required=True, help="Date folder, for example 2026-05-25")
    parser.add_argument("--skip-start-seconds", type=float, default=10.0, help="Reject assets before this timestamp")
    parser.add_argument("--min-motion-score", type=float, help="Minimum frame/clip motion threshold")
    parser.add_argument("--max-foreground-ratio", type=float, default=0.6, help="Reject assets above this motion/foreground ratio")
    parser.add_argument("--keep-rotation-warning", action="store_true", help="Keep portrait assets but record rotation warning")
    parser.add_argument("--dry-run", action="store_true", help="Write no files; only print summary")
    args = parser.parse_args()

    output_root = PROJECT_ROOT / "outputs" / args.date
    frame_manifest_path = output_root / "selected_frames" / "motion_frames_manifest.json"
    clip_manifest_path = output_root / "clips" / "clips_manifest.json"
    session_info = load_json(output_root / "session_info.json", {})
    if session_info.get("skip_start_seconds") is not None and args.skip_start_seconds == 10.0:
        args.skip_start_seconds = float(session_info["skip_start_seconds"])

    frame_manifest = load_json(frame_manifest_path, [])
    clip_manifest = load_json(clip_manifest_path, [])
    if not frame_manifest:
        raise SystemExit(f"No frame manifest found or manifest is empty: {frame_manifest_path}")

    items: list[dict] = []
    for record in frame_manifest:
        item = frame_record(record, args)
        if item:
            items.append(item)
    for record in clip_manifest:
        item = clip_record(record, args)
        if item:
            items.append(item)

    frame_output_dir = output_root / "filtered_frames"
    clip_output_dir = output_root / "filtered_clips"
    copy_kept_assets([item for item in items if item["asset_type"] == "frame"], frame_output_dir, args.dry_run)
    copy_kept_assets([item for item in items if item["asset_type"] == "clip"], clip_output_dir, args.dry_run)
    write_filtered_manifests(output_root, items, args.dry_run)

    if not args.dry_run:
        (output_root / "filter_manifest.json").write_text(
            json.dumps(items, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (output_root / "filter_report.md").write_text("\n".join(report_lines(args.date, items)) + "\n", encoding="utf-8")

    kept_frames = sum(1 for item in items if item["asset_type"] == "frame" and item["decision"] == "keep")
    kept_clips = sum(1 for item in items if item["asset_type"] == "clip" and item["decision"] == "keep")
    print(f"Filtered frames kept: {kept_frames}/{len(frame_manifest)}")
    print(f"Filtered clips kept: {kept_clips}/{len(clip_manifest)}")
    if args.dry_run:
        print("Dry run: no files were written")
    else:
        print(f"Report written: {output_root / 'filter_report.md'}")
        print(f"Manifest written: {output_root / 'filter_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
