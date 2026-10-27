# V1 → V1.1 增量迁移

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

新增：`usage_clock.py`、`supervision.py`、`windows_session_events.py`、`timer_ring.py`、`theme.py`、`tray_controller.py`、`video_break.py`、`surrender_dialog.py`、`camera_capture.py`、`config_store.py`、`photo_storage.py`、`records_store.py`、`records_view.py`、`settings_dialog.py`。

原 V1 没有持久化监督配置或历史数据库。V1.1 不删除 V1 日志/目录；若存在兼容的 ScreenBreak settings.json，可读入非运行偏好。档案库采用增量字段迁移，迁移前创建 `.pre-v11.sqlite3` 备份，不清空历史，不恢复运行态。

原 68 项基线先执行；计时、资源与审查测试保留。GUI 的直接解除/关闭确认与 V1.1 新规则冲突，已改为两步投降、托盘和紧急退出测试，旧测试原文在 V1 源码快照中。
