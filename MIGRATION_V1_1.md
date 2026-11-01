# 版本迁移记录（V1 → V1.1 → V2.0）

## V1.1 → V2.0（2026-11-01）

| V1.1 模块 | V2.0 处理 |
|---|---|
| `camera_capture.py` | 删除。静态拍照被连续录像取代，全仓已无引用 |
| `surrender_dialog.py` | 重写为四页：写宣言 → 看示范 → 录制 → 结果；`confirm_requested` 改为 `(token, clip_path, verdict)` |
| `supervision.py` | 阶段由 `writing → camera → preview` 改为 `writing → video → recording → verified`；`confirm_surrender` 要求 `verified`；新增 `mark_video_watched / mark_verified / retake / stage` |
| `records_store.py` | schema 2 → 3：新增 `video_status / video_path / ai_cycles / ai_reason`；迁移前按来源版本备份 `.pre-v11.sqlite3`（v1）或 `.pre-v3.sqlite3`（v2） |
| `records_view.py` | 5 列（时间/事件/轮次/录像/照片），新增查看与删除录像；旧照片仍可查看 |
| `settings_dialog.py` | 3 页 → 4 页：监督模式 / 存储与配额 / AI 接入 / 投降档案馆 |
| `main_window.py` | 新增 AI 状态行、首次提醒、录像归档；`confirm_surrender` 增加 `clip_path` 与判定结果 |
| `photo_storage.py` | 原样保留，用于读取 V1.1 旧照片 |
| `video_break.py` | 原样保留（静音循环播放示范视频） |
| `build.ps1` / `tools` | 产物改为 `dist/v2.0-local`、`NailongQuanxue-v2.0.0-Windows-local.zip`；`v11_smoke.py` 由 `v2_smoke.py` 取代；`exe_smoke.py` 增加首次 AI 提醒的处理 |

新增：`ai_config.py`、`vision_api.py`、`ai_panel.py`、`async_task.py`、`camera_recorder.py`、`frame_sampler.py`、`action_verdict.py`、`video_archive.py`。

数据兼容：

- `settings.json` 新增 `ai{protocol, base_url, api_key, model, verified, verified_at}` 与 `video_directory`，`schema_version` 升为 3；旧文件缺失这些键时按默认补全，未知键保留。
- `records.sqlite3` 增量加列，旧行 `video_status` 回落为 `not_applicable`；历史事件、旧照片路径不变。
- 旧照片目录 `photos\` 与 V1.1 配额（100 MiB）继续有效；新增 `videos\`（512 MiB）。
- 迁移只做加法，不清空历史、不恢复运行态；迁移失败时保留原库并给出提示。

声音路线（V1.1 期间的 P1 实验）在 V2.0 被彻底放弃：不录麦克风、不提取 WAV、不做笑声判定。相关代码已删除（清单见 `build/v2-cleanup/cleanup-manifest.json`），报告归档在 `docs/archive/`。

## V1 → V1.1

| V1 模块 | V1.1 处理 |
|---|---|
| timer_controller.py / test_timer.py | 保留截止时间、ceil、提醒去重与原测试；由新 ActiveClock 提供有效使用时间 |
| main_window.py | 原窗口升级为单页分秒计时、圆环、右上角设置；关闭行为改为活动时托盘、待机时退出 |
| reminder_window.py | 保留单窗口、不抢焦点和四秒提醒；增加五秒休息完成提示 |
| overlay_window.py | 保留纯白与 Contain 绘制；主屏增加视频帧、剩余时间，右下角仅保留解除限制；副屏只画白色 |
| screen_manager.py | 保留屏幕信号与去重；新增唯一播放器、主屏切换和优先撤下遮挡的清理顺序 |
| resources.py | 保留 V1 路径测试；新增固定 V1.1 打包资源解析，不提供自定义视频入口 |
| main.py | 保留调试计时、错误释放与日志；新增会话/电源桥，去除旧预览参数 |
| build.ps1 | 新产物隔离到 dist/v1.1-local，旧 V1 EXE 不覆盖；默认固定 MP4/JPG 本地包 |

新增：`usage_clock.py`、`supervision.py`、`windows_session_events.py`、`timer_ring.py`、`theme.py`、`tray_controller.py`、`video_break.py`、`surrender_dialog.py`、`camera_capture.py`（V2.0 已删除）、`config_store.py`、`photo_storage.py`、`records_store.py`、`records_view.py`、`settings_dialog.py`。

原 V1 没有持久化监督配置或历史数据库。V1.1 不删除 V1 日志/目录；若存在兼容的 ScreenBreak settings.json，可读入非运行偏好。档案库采用增量字段迁移，迁移前创建 `.pre-v11.sqlite3` 备份，不清空历史，不恢复运行态。

原 68 项基线先执行；计时、资源与审查测试保留。GUI 的直接解除/关闭确认与 V1.1 新规则冲突，已改为两步投降、托盘和紧急退出测试，旧测试原文在 V1 源码快照中。
