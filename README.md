# Badminton Review

本项目用于建立羽毛球双打视频复盘闭环：整理视频、抽帧、切短片段、过滤低价值素材、生成小而精的 review pack，然后由视觉模型辅助分析，你自己完成标签和评分。

项目不追求全自动判断技术动作。`clips` 比 `frames` 更重要，`frames` 主要用于补充静态姿态。

## 项目结构

```text
badminton-review/
  README.md
  requirements.txt
  .gitignore
  config/
    player_profile.json
    review_metrics.md
  scripts/
    extract_frames.py
    detect_motion_frames.py
    extract_motion_clips.py
    filter_review_assets.py
    generate_review_prompt.py
    select_review_pack.py
    compare_scores.py
    cleanup_outputs.py
    doctor.py
  videos/
    {date}/
  outputs/
    {date}/
```

约定：

- `videos/{date}/` 只放原始 MP4/MOV。
- `outputs/{date}/` 只放该日期的输出结果。
- `outputs/` 顶层不应该直接有 `frames/` 或 `clips/`。
- `.DS_Store`、`__MACOSX/`、`._*` 不会进入 `review_pack.zip`。

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 完整流程

### 一键流程

测试模式，适合只保留一个视频测试流程：

```bash
python3 scripts/run_pipeline.py --date 2026-05-25 --test-single-video-ok
```

正式模式，适合保留当天多个视频做完整复盘：

```bash
python3 scripts/run_pipeline.py --date 2026-05-25
```

然后上传：

```text
outputs/2026-05-25/review_pack.zip
```

复盘完成后：

```bash
python3 scripts/cleanup_outputs.py --date 2026-05-25 --dry-run
python3 scripts/cleanup_outputs.py --date 2026-05-25 --archive-mode
```

### 分步流程

```bash
python3 scripts/doctor.py --date 2026-05-25
python3 scripts/extract_frames.py --date 2026-05-25
python3 scripts/detect_motion_frames.py --date 2026-05-25
python3 scripts/extract_motion_clips.py --date 2026-05-25
python3 scripts/filter_review_assets.py --date 2026-05-25 --skip-start-seconds 10
python3 scripts/generate_review_prompt.py --date 2026-05-25
python3 scripts/select_review_pack.py --date 2026-05-25 --use-filtered --test-single-video-ok --max-frames 20 --max-clips 10 --max-zip-mb 100
python3 scripts/compare_scores.py --current 2026-05-25
```

`select_review_pack.py` 会在生成 pack 后重写 `review_prompt.md`，确保 prompt 只列出 zip 内部真实存在的素材路径，例如 `clips/xxx.mp4` 和 `frames/xxx.jpg`。

## 测试模式

适合只保留一个原始视频来测试流程：

```bash
python3 scripts/select_review_pack.py --date 2026-05-25 --use-filtered --test-single-video-ok --max-frames 20 --max-clips 10 --max-zip-mb 100
```

说明：

- 可以只有一个 `source_video`。
- 不要求跨视频均匀覆盖。
- `review_pack_index.md` 会写明：`Only one source video detected; balanced selection across videos is skipped.`
- 重点检查过滤效果、prompt 是否一致、zip 是否能上传。

## 正式模式

适合当天多个视频都还在时做完整复盘：

```bash
python3 scripts/select_review_pack.py --date 2026-05-25 --use-filtered --max-frames 20 --max-clips 10 --max-zip-mb 100
```

说明：

- 如果有多个 `source_video`，frames 和 clips 会尽量均匀覆盖。
- 每个视频优先至少选 3 张 frames、2 个 clips；素材不足时由其他视频补足。
- 不会因为某个视频 motion score 更高，就把所有 clips 都集中到它。

## Review Pack

`review_pack.zip` 只包含：

```text
review_prompt.md
review_pack_index.md
filter_summary.md
frames/
clips/
```

不会打包全部 `selected_frames/` 或全部 `clips/`。默认上限 100MB；如果超限，会先减少 clips，再减少 frames。

`review_pack_index.md` 会记录：

- path in zip
- asset_type
- source_video
- timestamp
- motion_score
- paired_frame
- paired_clip
- filter_reasons
- why_selected

如果 filtered 素材不足，脚本会从原始 `selected_frames/` 或 `clips/` 补齐，并在 index 中标记：

```text
source: selected_frames_fallback
filter_reasons: ['fallback_unfiltered']
```

或：

```text
source: clips_fallback
filter_reasons: ['fallback_unfiltered']
```

`filter_summary.md` 是随 zip 附带的短摘要，记录 source、数量、过滤原因统计、是否使用 fallback、是否单视频测试。

frames 和 clips 会尽量按同名文件配对，例如：

```text
frames/DJI_0170_motion_t0062_frame014.jpg
clips/DJI_0170_motion_t0062_frame014.mp4
```

## 过滤规则

`filter_review_assets.py` 使用简单可解释规则，不做复杂 AI 识别。常见过滤原因包括：

- `camera_adjustment`
- `rotation_warning`
- `too_close`
- `occlusion_warning`
- `no_full_body`
- `walking_only`
- `not_badminton_action`
- `low_review_value`

过滤结果写入：

```text
outputs/{date}/filter_manifest.json
outputs/{date}/filter_report.md
```

原始素材不会被删除，只会把保留素材复制到：

```text
outputs/{date}/filtered_frames/
outputs/{date}/filtered_clips/
```

## 复盘后节省空间

先 dry-run：

```bash
python3 scripts/cleanup_outputs.py --date 2026-05-25 --dry-run
```

确认后归档：

```bash
python3 scripts/cleanup_outputs.py --date 2026-05-25 --archive-mode
```

归档后只保留：

```text
outputs/{date}/review_pack.zip
outputs/{date}/review_prompt.md
outputs/{date}/review_pack_index.md
outputs/{date}/report_template.md
outputs/{date}/score.json
outputs/{date}/progress.md
outputs/{date}/filter_report.md
outputs/{date}/filter_manifest.json
outputs/{date}/manual_labels.csv
```

会删除：

```text
outputs/{date}/frames/
outputs/{date}/selected_frames/
outputs/{date}/clips/
outputs/{date}/filtered_frames/
outputs/{date}/filtered_clips/
outputs/{date}/review_pack/
outputs/{date}/selected_frames.zip
```

如果确认不需要原始视频：

```bash
python3 scripts/cleanup_outputs.py --date 2026-05-25 --archive-mode --delete-raw-videos
```

删除原始视频后，不能重新抽帧或重新生成 clips。删除原始视频前脚本会确认 `review_pack.zip` 存在。

## 人工复盘

1. 上传 `outputs/{date}/review_pack.zip`。
2. 让视觉模型优先看 clips，再用 frames 辅助姿态判断。
3. 填写 `manual_labels.csv` 和 `report_template.md`。
4. 修改 `score.json`。
5. 下次训练后运行 `compare_scores.py` 对比进步。

## 设计原则

- 不推倒重来。
- 不追求全自动判断羽毛球技术。
- review_pack 小而精。
- 如果只有一个 `source_video`，测试阶段允许。
- 如果有多个 `source_video`，才要求均匀覆盖。
- frames 和 clips 尽量配对。
- review_prompt 必须和实际 review_pack 内容一致。
- 所有过滤必须可解释。
- 清理操作必须支持 `--dry-run`。
