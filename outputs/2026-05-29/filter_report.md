# Review Assets Filter Report | 2026-05-29

## 总览
- 原始关键帧数量：60
- 原始短片段数量：60
- 保留关键帧数量：51
- 保留短片段数量：39
- 过滤关键帧数量：9
- 过滤短片段数量：21

## 过滤原因统计
- timestamp_too_early: 18
- camera_adjustment: 18
- possible_rotation_error: 0
- rotation_warning: 0
- possible_occlusion_or_too_close: 12
- too_close: 12
- occlusion_warning: 12
- no_full_body: 5
- low_motion: 0
- low_review_value: 17
- walking_only: 4
- not_badminton_action: 4

## 建议
- 保留素材数量足够，可以继续生成 review_pack。

## 说明
- 本过滤器只做简单质量筛选，不判断技术动作对错。
- 原始素材不会被删除；保留素材会复制到 `filtered_frames/` 和 `filtered_clips/`。
- 如果某些规则误伤，可以调低阈值或使用 `--keep-rotation-warning`。
