#!/usr/bin/env python3
"""Compare current badminton review scores with the previous session."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]

METRIC_LABELS = {
    "split_step": "启动步",
    "recovery": "回中/回位",
    "rear_court_positioning": "后场到位",
    "defensive_preparation": "防守准备",
    "doubles_positioning": "双打站位",
    "post_shot_connection": "击球后衔接",
}


def load_score(date: str) -> dict:
    path = PROJECT_ROOT / "outputs" / date / "score.json"
    if not path.exists():
        raise SystemExit(f"Score file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def bullet_for_delta(key: str, current_value: float, previous_value: float) -> str:
    label = METRIC_LABELS.get(key, key)
    delta = current_value - previous_value
    sign = "+" if delta > 0 else ""
    return f"- {label}: {previous_value:g} -> {current_value:g} ({sign}{delta:g})"


def compare(current: dict, previous: Optional[dict]) -> str:
    current_date = current.get("date", "current")
    lines = [f"# 训练进步对比｜{current_date}", ""]

    if previous is None:
        lines.extend(
            [
                "这是第一次记录，暂无上一场可对比。",
                "",
                "## 本次基线",
            ]
        )
        for key, value in current.get("scores", {}).items():
            lines.append(f"- {METRIC_LABELS.get(key, key)}: {value:g}/5")
        lines.extend(
            [
                "",
                "## 下次建议",
                f"- 继续围绕 `{current.get('next_focus', 'split step before opponent hits')}` 建立可观察标准。",
            ]
        )
        return "\n".join(lines) + "\n"

    previous_scores = previous.get("scores", {})
    current_scores = current.get("scores", {})
    improved = []
    declined = []
    unchanged = []

    for key, current_value in current_scores.items():
        if key not in previous_scores:
            continue
        previous_value = previous_scores[key]
        delta = current_value - previous_value
        item = (key, current_value, previous_value, delta)
        if delta > 0:
            improved.append(item)
        elif delta < 0:
            declined.append(item)
        else:
            unchanged.append(item)

    improved_sorted = sorted(improved, key=lambda item: item[3], reverse=True)
    declined_sorted = sorted(declined, key=lambda item: item[3])
    biggest_improvement = improved_sorted[0] if improved_sorted else None
    biggest_decline = declined_sorted[0] if declined_sorted else None

    lines.extend(
        [
            f"- 当前日期：{current.get('date')}",
            f"- 对比日期：{previous.get('date')}",
            "",
            "## 提升的分数",
        ]
    )
    lines.extend([bullet_for_delta(*item[:3]) for item in improved_sorted] or ["- 暂无提升项"])

    lines.append("")
    lines.append("## 下降的分数")
    lines.extend([bullet_for_delta(*item[:3]) for item in declined_sorted] or ["- 暂无下降项"])

    lines.append("")
    lines.append("## 持平的分数")
    lines.extend([bullet_for_delta(*item[:3]) for item in unchanged] or ["- 暂无持平项"])

    lines.append("")
    lines.append("## 本次最大进步")
    if biggest_improvement:
        key, current_value, previous_value, _ = biggest_improvement
        lines.append(bullet_for_delta(key, current_value, previous_value))
    else:
        lines.append("- 暂无明显进步")

    lines.append("")
    lines.append("## 本次最大退步")
    if biggest_decline:
        key, current_value, previous_value, _ = biggest_decline
        lines.append(bullet_for_delta(key, current_value, previous_value))
    else:
        lines.append("- 暂无明显退步")

    previous_focus = previous.get("next_focus")
    completed = current.get("completed_previous_focus")
    if completed is True:
        completed_text = "是"
    elif completed is False:
        completed_text = "否"
    else:
        completed_text = "未填写，请复盘后在当前 score.json 中设置 completed_previous_focus 为 true 或 false"

    lines.extend(
        [
            "",
            "## 是否完成上次训练目标",
            f"- 上次目标：{previous_focus or '未填写'}",
            f"- 是否完成：{completed_text}",
            "",
            "## 下次建议继续练什么",
            f"- 当前最大问题：{current.get('main_problem', '未填写')}",
            f"- 建议下一主题：{current.get('next_focus', '未填写')}",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two badminton score.json files.")
    parser.add_argument("--current", required=True, help="Current date, for example 2026-05-25")
    parser.add_argument("--previous", help="Previous date, for example 2026-05-24")
    args = parser.parse_args()

    current = load_score(args.current)
    previous = load_score(args.previous) if args.previous else None
    report = compare(current, previous)

    output_dir = PROJECT_ROOT / "outputs" / args.current
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "progress.md"
    output_path.write_text(report, encoding="utf-8")
    print(f"Progress report written: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
