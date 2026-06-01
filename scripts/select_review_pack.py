#!/usr/bin/env python3
"""Build a compact review pack for ChatGPT or a vision model."""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MACOS_JUNK_NAMES = {".DS_Store", "__MACOSX"}
VIDEO_EXTENSIONS = {".mp4", ".mov"}


def load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_profile() -> dict:
    path = PROJECT_ROOT / "config" / "player_profile.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def existing_records(records: list[dict], source_key: str) -> list[dict]:
    return [record for record in records if record.get(source_key) and (PROJECT_ROOT / record[source_key]).exists()]


def source_video(record: dict) -> str:
    return record.get("video") or record.get("source_video") or "unknown"


def timestamp(record: dict) -> float:
    return float(record.get("time_seconds", record.get("timestamp", 0)) or 0)


def motion_score(record: dict) -> float:
    return float(record.get("motion_score") or 0)


def stem_from_record(record: dict, key: str) -> str:
    return Path(record.get(key, "")).stem


def raw_video_sources(date: str) -> set[str]:
    video_dir = PROJECT_ROOT / "videos" / date
    if not video_dir.exists():
        return set()
    return {path.name for path in video_dir.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS}


def resolve_manifests(output_root: Path, use_filtered: bool) -> tuple[Path, Path, str]:
    filtered_frames = output_root / "filtered_frames" / "filtered_frames_manifest.json"
    filtered_clips = output_root / "filtered_clips" / "filtered_clips_manifest.json"
    original_frames = output_root / "selected_frames" / "motion_frames_manifest.json"
    original_clips = output_root / "clips" / "clips_manifest.json"

    if use_filtered and filtered_frames.exists() and filtered_clips.exists():
        return filtered_frames, filtered_clips, "filtered"
    if use_filtered:
        print("Filtered manifests not found; falling back to original selected_frames/ and clips/.")
    return original_frames, original_clips, "original"


def original_manifest_paths(output_root: Path) -> tuple[Path, Path]:
    return output_root / "selected_frames" / "motion_frames_manifest.json", output_root / "clips" / "clips_manifest.json"


def filter_to_current_sources(date: str, frames: list[dict], clips: list[dict]) -> tuple[list[dict], list[dict], set[str], str]:
    raw_sources = raw_video_sources(date)
    if raw_sources:
        filtered_frames = [record for record in frames if source_video(record) in raw_sources]
        filtered_clips = [record for record in clips if source_video(record) in raw_sources]
        if filtered_frames or filtered_clips:
            return filtered_frames, filtered_clips, raw_sources, "raw_videos"

    artifact_sources = {source_video(record) for record in frames + clips if source_video(record) != "unknown"}
    return frames, clips, artifact_sources, "artifacts"


def with_record_source(records: list[dict], label: str) -> list[dict]:
    prepared = []
    for record in records:
        copy = dict(record)
        copy.setdefault("source", label)
        copy.setdefault("filter_reasons", record.get("filter_reasons", []))
        prepared.append(copy)
    return prepared


def fallback_records(primary: list[dict], fallback: list[dict], source_key: str, target_count: int, label: str) -> tuple[list[dict], bool]:
    if len(primary) >= target_count:
        return primary, False

    existing = {stem_from_record(record, source_key) for record in primary}
    result = list(primary)
    used_fallback = False
    for record in fallback:
        stem = stem_from_record(record, source_key)
        if not stem or stem in existing:
            continue
        copy = dict(record)
        copy["source"] = label
        copy["filter_reasons"] = ["fallback_unfiltered"]
        result.append(copy)
        existing.add(stem)
        used_fallback = True
        if len(result) >= target_count:
            break
    return result, used_fallback


def previous_score(date: str) -> dict | None:
    outputs_dir = PROJECT_ROOT / "outputs"
    if not outputs_dir.exists():
        return None
    candidates = []
    for path in outputs_dir.iterdir():
        if path.is_dir() and path.name < date and (path / "score.json").exists():
            candidates.append(path)
    if not candidates:
        return None
    latest = sorted(candidates, key=lambda item: item.name)[-1]
    return json.loads((latest / "score.json").read_text(encoding="utf-8"))


def group_by_video(records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[source_video(record)].append(record)
    for values in grouped.values():
        values.sort(key=timestamp)
    return dict(grouped)


def is_far_enough(candidate: dict, selected: list[dict], min_gap_seconds: float) -> bool:
    for item in selected:
        if source_video(item) == source_video(candidate) and abs(timestamp(item) - timestamp(candidate)) < min_gap_seconds:
            return False
    return True


def choose_from_video(records: list[dict], quota: int, min_gap_seconds: float) -> list[dict]:
    if quota <= 0 or not records:
        return []

    selected: list[dict] = []
    start_time = timestamp(records[0])
    end_time = timestamp(records[-1])
    span = max(1.0, end_time - start_time)

    for index in range(quota):
        window_start = start_time + span * index / quota
        window_end = start_time + span * (index + 1) / quota
        candidates = [
            item
            for item in records
            if window_start <= timestamp(item) <= window_end and is_far_enough(item, selected, min_gap_seconds)
        ]
        if candidates:
            selected.append(max(candidates, key=motion_score))

    if len(selected) < quota:
        for item in sorted(records, key=motion_score, reverse=True):
            if item in selected or not is_far_enough(item, selected, min_gap_seconds):
                continue
            selected.append(item)
            if len(selected) >= quota:
                break

    if len(selected) < quota:
        for item in records:
            if item not in selected:
                selected.append(item)
            if len(selected) >= quota:
                break

    return sorted(selected, key=timestamp)


def balanced_select(records: list[dict], total: int, min_gap_seconds: float, min_per_video: int, single_source: bool) -> list[dict]:
    if total <= 0 or not records:
        return []
    grouped = group_by_video(records)
    if single_source or len(grouped) <= 1:
        return choose_from_video(sorted(records, key=timestamp), total, min_gap_seconds)

    videos = sorted(grouped)
    selected: list[dict] = []
    for video in videos:
        quota = min(min_per_video, total - len(selected))
        selected.extend(choose_from_video(grouped[video], quota, min_gap_seconds))
        if len(selected) >= total:
            return selected[:total]

    remaining_slots = total - len(selected)
    if remaining_slots > 0:
        remaining = [item for item in records if item not in selected]
        base_quota = max(1, remaining_slots // len(videos))
        for video in videos:
            if len(selected) >= total:
                break
            video_remaining = [item for item in remaining if source_video(item) == video]
            selected.extend(choose_from_video(video_remaining, min(base_quota, total - len(selected)), min_gap_seconds))

    if len(selected) < total:
        for item in sorted(records, key=motion_score, reverse=True):
            if item not in selected:
                selected.append(item)
            if len(selected) >= total:
                break

    return sorted(selected[:total], key=lambda item: (source_video(item), timestamp(item)))


def add_paired_frames(selected_frames: list[dict], selected_clips: list[dict], frame_by_stem: dict[str, dict], max_frames: int) -> list[dict]:
    result = list(selected_frames)
    for clip in selected_clips:
        paired = frame_by_stem.get(stem_from_record(clip, "clip_path"))
        if paired and paired not in result:
            result.insert(0, paired)
        if len(result) >= max_frames:
            break
    return result[:max_frames]


def add_paired_clips(selected_clips: list[dict], selected_frames: list[dict], clip_by_stem: dict[str, dict], max_clips: int) -> list[dict]:
    result = list(selected_clips)
    for frame in selected_frames:
        paired = clip_by_stem.get(stem_from_record(frame, "path"))
        if paired and paired not in result:
            result.insert(0, paired)
        if len(result) >= max_clips:
            break
    return result[:max_clips]


def select_assets(
    frames: list[dict],
    clips: list[dict],
    max_frames: int,
    max_clips: int,
    min_gap: float,
    single_source: bool,
) -> tuple[list[dict], list[dict], list[str]]:
    notes: list[str] = []
    frame_by_stem = {stem_from_record(record, "path"): record for record in frames}
    clip_by_stem = {stem_from_record(record, "clip_path"): record for record in clips}

    selected_clips = balanced_select(clips, max_clips, min_gap, min_per_video=2, single_source=single_source)
    selected_frames = [frame_by_stem[stem_from_record(clip, "clip_path")] for clip in selected_clips if stem_from_record(clip, "clip_path") in frame_by_stem]
    selected_frames.extend(
        item
        for item in balanced_select(frames, max_frames, min_gap, min_per_video=3, single_source=single_source)
        if item not in selected_frames
    )
    selected_frames = add_paired_frames(selected_frames, selected_clips, frame_by_stem, max_frames)
    selected_clips = add_paired_clips(selected_clips, selected_frames, clip_by_stem, max_clips)

    if len(selected_frames) < max_frames:
        notes.append(f"Frame material is limited: selected {len(selected_frames)} of requested {max_frames}.")
    if len(selected_clips) < max_clips:
        notes.append(f"Clip material is limited: selected {len(selected_clips)} of requested {max_clips}.")
    return selected_frames[:max_frames], selected_clips[:max_clips], notes


def copy_record_file(record: dict, source_key: str, target_dir: Path) -> Optional[str]:
    relative_path = record.get(source_key)
    if not relative_path:
        return None
    source_path = PROJECT_ROOT / relative_path
    if not source_path.exists():
        print(f"Skip missing file: {source_path}")
        return None
    target_path = target_dir / source_path.name
    shutil.copy2(source_path, target_path)
    return target_path.name


def paired_frame_path(clip_record: dict, frame_items: list[tuple[str, dict]]) -> str:
    stem = stem_from_record(clip_record, "clip_path")
    for path, record in frame_items:
        if stem_from_record(record, "path") == stem:
            return path
    return ""


def paired_clip_path(frame_record: dict, clip_items: list[tuple[str, dict]]) -> str:
    stem = stem_from_record(frame_record, "path")
    for path, record in clip_items:
        if stem_from_record(record, "clip_path") == stem:
            return path
    return ""


def why_selected(record: dict, asset_type: str, paired: bool) -> str:
    base = "paired with matching clip/frame" if paired else "selected for time coverage and motion score"
    if asset_type == "clip":
        return f"{base}; useful for checking split step, post-shot recovery, racket height, and doubles positioning"
    return f"{base}; useful as static posture support for the nearby action"


def write_pack_index(
    output_path: Path,
    date: str,
    source_videos: set[str],
    single_source: bool,
    test_single_video_ok: bool,
    frame_items: list[tuple[str, dict]],
    clip_items: list[tuple[str, dict]],
    notes: list[str],
) -> None:
    lines = [
        f"# Review Pack | {date}",
        "",
        "## Summary",
        f"- source_video_count: {len(source_videos)}",
        f"- source_videos: {', '.join(sorted(source_videos)) if source_videos else 'none'}",
        f"- frames: {len(frame_items)}",
        f"- clips: {len(clip_items)}",
        "",
    ]
    if single_source:
        lines.extend(
            [
                "## Note",
                "Only one source video detected. This is acceptable for test mode. Balanced cross-video selection was skipped.",
                f"- test_single_video_ok: {str(test_single_video_ok).lower()}",
                "",
            ]
        )
    if notes:
        lines.extend(["## Warnings", *[f"- {note}" for note in notes], ""])

    lines.append("## Clips")
    for path, record in clip_items:
        paired = paired_frame_path(record, frame_items)
        lines.extend(
            [
                f"- {path}",
                "  asset_type: clip",
                f"  source: {record.get('source', 'unknown')}",
                f"  source_video: {source_video(record)}",
                f"  timestamp: {timestamp(record):g}s",
                f"  motion_score: {motion_score(record):g}",
            ]
        )
        if paired:
            lines.append(f"  paired_frame: {paired}")
        lines.extend(
            [
                f"  filter_reasons: {record.get('filter_reasons', [])}",
                f"  why_selected: {why_selected(record, 'clip', bool(paired))}",
            ]
        )

    lines.extend(["", "## Frames"])
    for path, record in frame_items:
        paired = paired_clip_path(record, clip_items)
        lines.extend(
            [
                f"- {path}",
                "  asset_type: frame",
                f"  source: {record.get('source', 'unknown')}",
                f"  source_video: {source_video(record)}",
                f"  timestamp: {timestamp(record):g}s",
                f"  motion_score: {motion_score(record):g}",
            ]
        )
        if paired:
            lines.append(f"  paired_clip: {paired}")
        lines.extend(
            [
                f"  filter_reasons: {record.get('filter_reasons', [])}",
                f"  why_selected: {why_selected(record, 'frame', bool(paired))}",
            ]
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_review_prompt(
    date: str,
    source_videos: set[str],
    single_source: bool,
    frame_items: list[tuple[str, dict]],
    clip_items: list[tuple[str, dict]],
) -> str:
    profile = load_profile()
    priorities = ", ".join(item.get("label", "") for item in profile.get("training_priorities", [])[:4])
    clips = "\n".join(f"- {path}" for path, _ in clip_items) or "- 暂无 clips，本次只能参考 frames。"
    frames = "\n".join(f"- {path}" for path, _ in frame_items) or "- 暂无 frames。"
    source_lines = "\n".join(f"  - {video}" for video in sorted(source_videos)) or "  - none"
    single_note = (
        "- 当前是测试阶段或素材限制，本次只分析该视频来源，不做整场均匀覆盖判断。"
        if single_source
        else "- 本次素材来自多个 source_video，已尽量均匀覆盖。"
    )
    previous = previous_score(date)
    if previous:
        previous_goal = f"""## 上次复盘目标
- theme: {previous.get('theme', 'not available')}
- observable_standard: {previous.get('next_focus', 'not available')}

## 本次请优先检查
- 上次目标是否改善
- 如果没有改善，指出最典型的 clips/frames
"""
    else:
        previous_goal = """## 上次复盘目标
- no previous score found
- use default focus: split step, post-shot recovery, rear-court arrival, doubles positioning

## 本次请优先检查
- 上次目标是否改善
- 如果没有改善，指出最典型的 clips/frames
"""

    return f"""# 羽毛球双打视频复盘 Prompt | {date}

## 我的背景
- 27岁
- 业余双打，2.x 往 3 级提升
- 工作日 9:00-12:00 晨练双打
- 目前重点：{priorities or '启动步、击球后回位、后场到位、双打站位'}

## 本次素材说明
- 本次上传的是 compact review pack。
- clips 是主要分析对象，用于观察连续动作。
- frames 用于补充静态姿态。
- 不要假装能从单帧判断完整动作，请区分画面事实和推测。
- source_video_count: {len(source_videos)}
- source_videos:
{source_lines}
{single_note}

## 本次复盘包素材

### Clips
{clips}

### Frames
{frames}

{previous_goal}
## 请优先分析
1. 击球后是否 1 秒内恢复准备姿态
2. 对手击球前是否有 split step
3. 拍子是否经常垂下
4. 后场是否到位
5. 左手是否举起后不收，导致右手硬抡
6. 双打站位是否合理
7. 打完高球/挑球后是否退防左右站
8. 下压后是否形成前后进攻站位

## 输出格式
### 画面事实
### 主要问题
### 代表性错误帧/片段
### 六项评分建议
### 下次只练一个主题
"""


def is_macos_junk(path: Path) -> bool:
    return any(part in MACOS_JUNK_NAMES or part.startswith("._") for part in path.parts)


def allowed_in_zip(path: Path, pack_dir: Path) -> bool:
    if not path.is_file() or is_macos_junk(path):
        return False
    relative = path.relative_to(pack_dir)
    if relative.parts[0] in {"frames", "clips"}:
        return len(relative.parts) == 2
    return str(relative) in {"review_prompt.md", "review_pack_index.md", "filter_summary.md"}


def make_zip(pack_dir: Path, zip_path: Path) -> int:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(pack_dir.rglob("*")):
            if allowed_in_zip(path, pack_dir):
                archive.write(path, path.relative_to(pack_dir))
    return zip_path.stat().st_size if zip_path.exists() else 0


def filter_reason_stats(output_root: Path) -> Counter:
    manifest_path = output_root / "filter_manifest.json"
    if not manifest_path.exists():
        return Counter()
    records = load_json(manifest_path)
    return Counter(reason for record in records for reason in record.get("reasons", []))


def write_filter_summary(
    output_path: Path,
    date: str,
    source_videos: set[str],
    test_single_video_ok: bool,
    raw_frame_count: int,
    raw_clip_count: int,
    filtered_frame_count: int,
    filtered_clip_count: int,
    selected_frame_count: int,
    selected_clip_count: int,
    notes: list[str],
    used_fallback: bool,
    single_source: bool,
    reason_counts: Counter,
) -> None:
    keys = [
        "camera_adjustment",
        "rotation_warning",
        "too_close",
        "occlusion_warning",
        "no_full_body",
        "walking_only",
        "not_badminton_action",
        "low_review_value",
    ]
    lines = [
        f"# Filter Summary | {date}",
        "",
        "## Source",
        f"- source_video_count: {len(source_videos)}",
        f"- source_videos: {', '.join(sorted(source_videos)) if source_videos else 'not available'}",
        f"- test_single_video_ok: {str(test_single_video_ok).lower()}",
        "",
        "## Asset counts",
        f"- raw frames count: {raw_frame_count}",
        f"- raw clips count: {raw_clip_count}",
        f"- filtered frames count: {filtered_frame_count if filtered_frame_count >= 0 else 'not available'}",
        f"- filtered clips count: {filtered_clip_count if filtered_clip_count >= 0 else 'not available'}",
        f"- selected frames count: {selected_frame_count}",
        f"- selected clips count: {selected_clip_count}",
        "",
        "## Filter reason stats",
    ]
    for key in keys:
        lines.append(f"- {key}: {reason_counts.get(key, 'not available' if not reason_counts else 0)}")
    lines.extend(
        [
            "",
            "## Notes",
            f"- fallback material used: {str(used_fallback).lower()}",
            f"- material limited: {str(bool(notes)).lower()}",
            f"- single-source test mode: {str(single_source and test_single_video_ok).lower()}",
        ]
    )
    for note in notes:
        lines.append(f"- {note}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_pack(
    date: str,
    output_root: Path,
    frame_records: list[dict],
    clip_records: list[dict],
    source_videos: set[str],
    frame_count: int,
    clip_count: int,
    min_gap: float,
    single_source: bool,
    test_single_video_ok: bool,
    raw_frame_count: int,
    raw_clip_count: int,
    filtered_frame_count: int,
    filtered_clip_count: int,
    used_fallback: bool,
) -> tuple[int, int, int, list[str]]:
    pack_dir = output_root / "review_pack"
    zip_path = output_root / "review_pack.zip"
    selected_frames, selected_clips, notes = select_assets(
        frame_records,
        clip_records,
        frame_count,
        clip_count,
        min_gap,
        single_source,
    )
    notes = list(notes)
    if used_fallback:
        notes.append("Fallback unfiltered material was used because filtered material was limited.")

    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    pack_dir.mkdir(parents=True, exist_ok=True)
    frame_dir = pack_dir / "frames"
    clip_dir = pack_dir / "clips"
    frame_dir.mkdir()
    clip_dir.mkdir()

    frame_items = []
    for record in selected_frames:
        name = copy_record_file(record, "path", frame_dir)
        if name:
            frame_items.append((f"frames/{name}", record))

    clip_items = []
    for record in selected_clips:
        name = copy_record_file(record, "clip_path", clip_dir)
        if name:
            clip_items.append((f"clips/{name}", record))

    index_path = pack_dir / "review_pack_index.md"
    write_pack_index(index_path, date, source_videos, single_source, test_single_video_ok, frame_items, clip_items, notes)
    prompt_text = build_review_prompt(date, source_videos, single_source, frame_items, clip_items)
    (pack_dir / "review_prompt.md").write_text(prompt_text, encoding="utf-8")
    (output_root / "review_prompt.md").write_text(prompt_text, encoding="utf-8")
    write_filter_summary(
        pack_dir / "filter_summary.md",
        date,
        source_videos,
        test_single_video_ok,
        raw_frame_count,
        raw_clip_count,
        filtered_frame_count,
        filtered_clip_count,
        len(frame_items),
        len(clip_items),
        notes,
        used_fallback,
        single_source,
        filter_reason_stats(output_root),
    )
    shutil.copy2(index_path, output_root / "review_pack_index.md")
    zip_size = make_zip(pack_dir, zip_path)
    return len(frame_items), len(clip_items), zip_size, notes


def selection_warning(records: list[dict], selected_count_by_video: Counter, min_expected: int, asset_type: str) -> list[str]:
    warnings = []
    grouped = group_by_video(records)
    if len(grouped) <= 1:
        return warnings
    for video, values in grouped.items():
        if len(values) >= min_expected and selected_count_by_video.get(video, 0) < min_expected:
            warnings.append(f"{asset_type} coverage warning: {video} has material but fewer than {min_expected} selected.")
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a compact review pack from key frames and clips.")
    parser.add_argument("--date", required=True, help="Date folder, for example 2026-05-25")
    parser.add_argument("--frames", "--max-frames", dest="max_frames", type=int, default=20, help="Number of key frames to include")
    parser.add_argument("--clips", "--max-clips", dest="max_clips", type=int, default=10, help="Number of clips to include")
    parser.add_argument("--max-zip-mb", type=float, default=100.0, help="Maximum review_pack.zip size in MB")
    parser.add_argument("--min-gap", type=float, default=8.0, help="Minimum seconds between picks from the same video")
    parser.add_argument("--use-filtered", action="store_true", help="Prefer filtered_frames/ and filtered_clips/ when available")
    parser.add_argument("--test-single-video-ok", action="store_true", help="Allow a single-source test pack without warning")
    args = parser.parse_args()

    output_root = PROJECT_ROOT / "outputs" / args.date
    selected_manifest, clips_manifest, source_mode = resolve_manifests(output_root, args.use_filtered)
    pack_dir = output_root / "review_pack"
    zip_path = output_root / "review_pack.zip"

    original_frame_manifest, original_clip_manifest = original_manifest_paths(output_root)
    original_frames = with_record_source(existing_records(load_json(original_frame_manifest), "path"), "selected_frames")
    original_clips = with_record_source(existing_records(load_json(original_clip_manifest), "clip_path"), "clips")

    frame_source_label = "filtered_frames" if source_mode == "filtered" else "selected_frames"
    clip_source_label = "filtered_clips" if source_mode == "filtered" else "clips"
    frame_records = with_record_source(existing_records(load_json(selected_manifest), "path"), frame_source_label)
    clip_records = with_record_source(existing_records(load_json(clips_manifest), "clip_path"), clip_source_label)
    if source_mode == "filtered" and (not frame_records or (args.max_clips > 0 and not clip_records)):
        print("Filtered manifests exist but filtered files are missing; falling back to original selected_frames/ and clips/.")
        selected_manifest = output_root / "selected_frames" / "motion_frames_manifest.json"
        clips_manifest = output_root / "clips" / "clips_manifest.json"
        source_mode = "original"
        frame_records = with_record_source(existing_records(load_json(selected_manifest), "path"), "selected_frames")
        clip_records = with_record_source(existing_records(load_json(clips_manifest), "clip_path"), "clips")

    frame_records, clip_records, source_videos, source_basis = filter_to_current_sources(args.date, frame_records, clip_records)
    original_frames, original_clips, _, _ = filter_to_current_sources(args.date, original_frames, original_clips)
    raw_frame_count = len(original_frames)
    raw_clip_count = len(original_clips)
    filtered_frame_count = len(frame_records) if source_mode == "filtered" else -1
    filtered_clip_count = len(clip_records) if source_mode == "filtered" else -1

    used_frame_fallback = False
    used_clip_fallback = False
    if source_mode == "filtered":
        frame_records, used_frame_fallback = fallback_records(
            frame_records,
            original_frames,
            "path",
            args.max_frames,
            "selected_frames_fallback",
        )
        clip_records, used_clip_fallback = fallback_records(
            clip_records,
            original_clips,
            "clip_path",
            args.max_clips,
            "clips_fallback",
        )
    used_fallback = used_frame_fallback or used_clip_fallback

    single_source = len(source_videos) == 1
    if single_source:
        print("Only one source video detected; balanced selection across videos is skipped.")
        if args.test_single_video_ok:
            print("Single-source test mode enabled.")
    if used_fallback:
        print("Filtered material was limited; unfiltered fallback assets were added with fallback_unfiltered reasons.")

    frame_count = args.max_frames
    clip_count = args.max_clips
    max_zip_bytes = int(args.max_zip_mb * 1024 * 1024)

    included_frames, included_clips, zip_size, notes = build_pack(
        args.date,
        output_root,
        frame_records,
        clip_records,
        source_videos,
        frame_count,
        clip_count,
        args.min_gap,
        single_source,
        args.test_single_video_ok,
        raw_frame_count,
        raw_clip_count,
        filtered_frame_count,
        filtered_clip_count,
        used_fallback,
    )

    while zip_size > max_zip_bytes and clip_count > 0:
        clip_count -= 1
        included_frames, included_clips, zip_size, notes = build_pack(
            args.date,
            output_root,
            frame_records,
            clip_records,
            source_videos,
            frame_count,
            clip_count,
            args.min_gap,
            single_source,
            args.test_single_video_ok,
            raw_frame_count,
            raw_clip_count,
            filtered_frame_count,
            filtered_clip_count,
            used_fallback,
        )

    while zip_size > max_zip_bytes and frame_count > 1:
        frame_count -= 1
        included_frames, included_clips, zip_size, notes = build_pack(
            args.date,
            output_root,
            frame_records,
            clip_records,
            source_videos,
            frame_count,
            clip_count,
            args.min_gap,
            single_source,
            args.test_single_video_ok,
            raw_frame_count,
            raw_clip_count,
            filtered_frame_count,
            filtered_clip_count,
            used_fallback,
        )

    print(f"Review pack written: {pack_dir}")
    print(f"Zip written: {zip_path}")
    print(f"Source mode: {source_mode}")
    print(f"Source basis: {source_basis}")
    print(f"Source videos: {', '.join(sorted(source_videos)) if source_videos else 'none'}")
    print(f"Included frames: {included_frames}")
    print(f"Included clips: {included_clips}")
    print(f"Zip size: {zip_size / 1024 / 1024:.1f} MB")
    for note in notes:
        print(f"Note: {note}")
    if zip_size > max_zip_bytes:
        print("Warning: review_pack.zip still exceeds size limit. Reduce clip length or handle files manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
