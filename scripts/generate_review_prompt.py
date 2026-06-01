#!/usr/bin/env python3
"""Generate review prompt, report template, and initial score JSON."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


DEFAULT_VIDEO_NAMES = [
    "DJI_20260525105843_0169_D.MP4",
    "DJI_20260525110830_0170_D.MP4",
    "DJI_20260525113002_0171_D.MP4",
    "DJI_20260525115847_0172_D.MP4",
]

MANUAL_TAGS = [
    "split_step_missing",
    "standing_too_straight",
    "racket_too_low",
    "slow_recovery",
    "watching_after_shot",
    "rear_court_late",
    "contact_point_behind",
    "left_arm_stuck_high",
    "arm_dominant_swing",
    "bad_doubles_positioning",
    "good_defensive_base",
    "good_recovery",
]


def load_profile() -> dict:
    profile_path = PROJECT_ROOT / "config" / "player_profile.json"
    return json.loads(profile_path.read_text(encoding="utf-8"))


def list_videos(date: str) -> list[str]:
    video_dir = PROJECT_ROOT / "videos" / date
    if not video_dir.exists():
        return DEFAULT_VIDEO_NAMES if date == "2026-05-25" else []
    videos = sorted(path.name for path in video_dir.iterdir() if path.is_file() and path.suffix.lower() == ".mp4")
    return videos or (DEFAULT_VIDEO_NAMES if date == "2026-05-25" else [])


def list_key_frames(date: str, limit: int) -> list[str]:
    selected_dir = PROJECT_ROOT / "outputs" / date / "selected_frames"
    frame_dir = PROJECT_ROOT / "outputs" / date / "frames"
    selected = sorted(selected_dir.glob("*.jpg")) if selected_dir.exists() else []
    regular = sorted(frame_dir.glob("*.jpg")) if frame_dir.exists() else []
    frames = selected if selected else regular
    return [str(path.relative_to(PROJECT_ROOT)) for path in frames[:limit]]


def list_selected_frame_files(date: str) -> list[str]:
    selected_dir = PROJECT_ROOT / "outputs" / date / "selected_frames"
    if not selected_dir.exists():
        return []
    return [path.name for path in sorted(selected_dir.glob("*.jpg"))]


def build_review_prompt(date: str, profile: dict, videos: list[str], frame_paths: list[str]) -> str:
    outfit = profile.get("today_outfit", {})
    priorities = ", ".join(item["label"] for item in profile.get("training_priorities", [])[:4])
    frame_lines = "\n".join(f"- `{path}`" for path in frame_paths) if frame_paths else "- 暂无关键帧，请先运行抽帧和运动检测脚本。"
    video_lines = "\n".join(f"- `{name}`" for name in videos) if videos else "- 暂无视频文件"

    return f"""# 羽毛球双打视频复盘 Prompt | {date}

请你作为羽毛球双打视频复盘助手，基于我提供的关键帧或短片段进行观察。不要假装能从单帧完全判断所有技术动作，请明确区分“能从画面看到的事实”和“基于画面的推测”。

## 我的背景
- 年龄：{profile.get("age")}
- 水平：{profile.get("level")}
- 训练时间：{profile.get("training_schedule")}
- 训练方式：工作日晨练双打，当前以长期复盘和人工评分为主。

## 本次视频
- 日期：{date}
- 视频文件：
{video_lines}
- 拍摄设备和角度：{profile.get("camera")}，{profile.get("default_view")}
- 我的穿着：{outfit.get("top", "white T-shirt")}，{outfit.get("bottom", "black shorts")}

## 本次重点
{priorities}

## 关键帧路径
{frame_lines}

## 请重点分析的问题
1. 对手击球前，我有没有启动步？
2. 我是不是经常站死？
3. 我打完球有没有及时回中？
4. 后场击球时，我是否到位？
5. 后场击球点是否偏低或偏后？
6. 我方进攻时，我有没有进入前后站位？
7. 我方防守时，我有没有进入左右防守站位？
8. 我是否有打完一拍就看球的问题？
9. 哪些帧最能代表我的错误？
10. 下一次训练我最应该只注意哪一个点？

## 希望输出格式
请按以下格式回答：

### 画面事实
- 只写从关键帧或短片段中能直接看到的内容。

### 主要问题
- 按严重程度列出 3 个以内。

### 代表性错误帧
- 写出文件名和原因。

### 六项评分建议
- 启动步：/5
- 回中/回位：/5
- 后场到位：/5
- 防守准备：/5
- 双打站位：/5
- 击球后衔接：/5

### 下次只练一个主题
- 只给一个最重要主题，以及一个可观察标准。
"""


def build_report_template(date: str, videos: list[str]) -> str:
    video_lines = "\n".join(f"- 视频{index}：{name}" for index, name in enumerate(videos, start=1))
    return f"""# 羽毛球复盘报告｜{date}

## 今日视频
{video_lines}

## 今日训练主题
例如：启动步

## 总体评价

## 六项评分
- 启动步：/5
- 回中/回位：/5
- 后场到位：/5
- 防守准备：/5
- 双打站位：/5
- 击球后衔接：/5

## 今天最大进步

## 今天最大问题

## 典型错误帧
- frame_xxx.jpg：
- frame_xxx.jpg：
- frame_xxx.jpg：

## 下次只练一个主题

## 下次观察标准
"""


def initial_score(date: str, videos: list[str]) -> dict:
    return {
        "date": date,
        "videos": videos,
        "session_type": "weekday morning doubles training",
        "duration_minutes": None,
        "theme": "split step",
        "scores": {
            "split_step": 2,
            "recovery": 2,
            "rear_court_positioning": 2.5,
            "defensive_preparation": 2,
            "doubles_positioning": 2.5,
            "post_shot_connection": 2,
        },
        "observations": [],
        "main_problem": "opponent hitting moment often standing still",
        "next_focus": "split step before opponent hits",
        "representative_errors": [],
        "representative_good_frames": [],
        "completed_previous_focus": None,
        "notes": "Edit these values after reviewing key frames and clips.",
    }


def upgrade_score(existing: dict, date: str, videos: list[str]) -> dict:
    upgraded = initial_score(date, videos)
    upgraded.update(existing)
    upgraded["scores"] = {**initial_score(date, videos)["scores"], **existing.get("scores", {})}
    upgraded.setdefault("videos", videos)
    upgraded.setdefault("session_type", "weekday morning doubles training")
    upgraded.setdefault("duration_minutes", None)
    upgraded.setdefault("observations", [])
    upgraded.setdefault("representative_errors", [])
    upgraded.setdefault("representative_good_frames", [])
    return upgraded


def write_manual_labels(date: str, output_path: Path) -> None:
    selected_frames = list_selected_frame_files(date)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["filename", "type", "tag", "severity", "note"])
        writer.writeheader()
        for tag in MANUAL_TAGS:
            writer.writerow(
                {
                    "filename": "",
                    "type": "tag_option",
                    "tag": tag,
                    "severity": "",
                    "note": "available manual label",
                }
            )
        for filename in selected_frames:
            writer.writerow(
                {
                    "filename": filename,
                    "type": "frame",
                    "tag": "",
                    "severity": "",
                    "note": "",
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate badminton review files by date.")
    parser.add_argument("--date", required=True, help="Date folder, for example 2026-05-25")
    parser.add_argument("--max-frames", type=int, default=80, help="Maximum key frame paths in prompt")
    parser.add_argument("--overwrite-score", action="store_true", help="Overwrite existing score.json")
    args = parser.parse_args()

    output_dir = PROJECT_ROOT / "outputs" / args.date
    output_dir.mkdir(parents=True, exist_ok=True)

    profile = load_profile()
    videos = list_videos(args.date)
    key_frames = list_key_frames(args.date, args.max_frames)

    review_prompt_path = output_dir / "review_prompt.md"
    report_template_path = output_dir / "report_template.md"
    score_path = output_dir / "score.json"
    manual_labels_path = output_dir / "manual_labels.csv"

    review_prompt_path.write_text(build_review_prompt(args.date, profile, videos, key_frames), encoding="utf-8")
    report_template_path.write_text(build_report_template(args.date, videos), encoding="utf-8")

    if args.overwrite_score or not score_path.exists():
        score = initial_score(args.date, videos)
    else:
        score = upgrade_score(json.loads(score_path.read_text(encoding="utf-8")), args.date, videos)
        print(f"Upgraded existing score file: {score_path}")
    score_path.write_text(json.dumps(score, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_manual_labels(args.date, manual_labels_path)

    print(f"Review prompt written: {review_prompt_path}")
    print(f"Report template written: {report_template_path}")
    print(f"Score file ready: {score_path}")
    print(f"Manual labels written: {manual_labels_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
