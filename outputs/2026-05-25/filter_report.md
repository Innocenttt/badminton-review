# Review Assets Filter Report | 2026-05-25

## 总览
- 原始关键帧数量：110
- 原始短片段数量：20
- 保留关键帧数量：72
- 保留短片段数量：18
- 过滤关键帧数量：38
- 过滤短片段数量：2

## 过滤原因统计
- timestamp_too_early: 15
- camera_adjustment: 15
- possible_rotation_error: 30
- rotation_warning: 30
- possible_occlusion_or_too_close: 0
- too_close: 0
- occlusion_warning: 0
- no_full_body: 0
- low_motion: 0
- low_review_value: 0
- walking_only: 0
- not_badminton_action: 0

## 建议
- 保留素材数量足够，可以继续生成 review_pack。

## 说明
- 本过滤器只做简单质量筛选，不判断技术动作对错。
- 原始素材不会被删除；保留素材会复制到 `filtered_frames/` 和 `filtered_clips/`。
- 如果某些规则误伤，可以调低阈值或使用 `--keep-rotation-warning`。
