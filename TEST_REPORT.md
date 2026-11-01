# 奶龙劝学 V2.0 测试与验收报告

日期：2026-11-01。分支 `main`，**未 push、未建分支、未发布 Release**。本报告只记录真实执行的命令与结果；未执行的项目一律标注"未验证"。

本文件在第二轮审核后更新：数值全部来自本轮重跑（第一轮记录见 git 提交 `8979e16` 时的版本）。

## 环境

Windows x64（NT 10.0 build 26200），Python 3.11.5，PySide6 Essentials/Addons 6.8.3，PyInstaller 6.16.0，pytest 8.4.2。一块显示器，Qt 逻辑几何 1707×1067，125% 缩放。**本机摄像头 0 个**（`QMediaDevices.videoInputs()` 为空），音频输入 1 个（不参与本应用）。**没有真实视觉 API 授权**。

## 自动化测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# 211 passed, 1 skipped in 8.35s
```

跳过项是既有约定：`tests/test_assets.py:41` 私有图片不在公开源码中时跳过。

| 测试文件 | 用例数 | 覆盖内容 |
|---|---|---|
| `tests/test_timer.py` | 32 | 原 V1 计时核心：截止时间、ceil、提醒去重、有效使用时钟 |
| `tests/test_windows.py` | 44 | 主窗口、四设置分页、四页投降对话框、覆盖窗、托盘、紧急退出、档案写入、未配置 AI、无限重试、锁屏取消录制、归档失败仍放行、多轮循环、**归档早于释放设备**、取消后临时件删除 |
| `tests/test_storage.py` | 27 | 档案库 schema 3 迁移（`.pre-v11.sqlite3` / `.pre-v3.sqlite3`）、录像列往返、`delete_video` 置空与后缀校验、照片配额、配置原子保存 |
| `tests/test_supervision.py` | 21 | 四阶段状态机 `writing→video→recording→verified`、跨阶段非法调用、**下一轮开始的旧 token 不能核验**、休息完成与确认竞争、用量到期取消旧流程 |
| `tests/test_public_audit.py` | 20 | 打包/源码审计规则：拒绝个人媒体与运行数据、固定素材指纹 |
| `tests/test_ai_config.py` | 14 | 协议/地址/模型/密钥校验、状态文案不泄露 Key、`settings.json` 往返与清除 |
| `tests/test_action_verdict.py` | 11 | 判定三态：静止不通过、组数不足、缺手位/缺前倾、模型拒绝、证据不足、提示词内容（含帧间隔说明） |
| `tests/test_vision_api.py` | 10 | 三协议 endpoint/headers/payload、10 帧截断、JSON 提取与别名解析、auth/http/timeout/network/bad_response 六类错误 |
| `tests/test_video_archive.py` | 9 | MP4 头校验、复制而非移动、唯一命名、配额与警告阈值、网络路径拒绝、失败不留残件 |
| `tests/test_secure_credentials.py` | 6 | DPAPI 封装往返、密文不含明文、明文兼容、`settings.json` 无明文 Key、旧 Key 一次性重新封装、字段向后兼容 |
| `tests/test_frame_sampler.py` | 6 | 采样节流与缩放、容量上限、等距取帧含首尾、运动量估计、JPEG 编码 |
| `tests/test_assets.py` | 5 | 固定素材存在性与指纹 |
| `tests/test_v11_resources.py` | 4 | 资源解析只允许文件名、防止路径穿越 |
| `tests/test_camera_recorder.py` | 3 | 过期临时片段清理只删本应用命名、目录缺失不报错、临时目录位置 |

判定逻辑的关键回归（对应"静态摆拍不能误判为两组动作"）：

- `test_static_pose_is_rejected_even_when_the_model_claims_success`：模型返回 `pass=true, cycles=2`，但抽帧运动量低于阈值 → **未通过**。
- 缺手位或缺前倾 → 未通过，理由以"模型自述通过，但"开头。
- 接口报错、超时、返回不可解析 → 确认按钮永不启用。
- 帧数不足（<6）或跨度不足 60% → 根本不调用模型。

## 本轮发现并修复的缺陷

1. **归档必然失败**（真实后端）：`confirm_surrender()` 先调用 `cancel_surrender()` 释放对话框，`CameraRecorder.stop()` 会删除临时录像，随后 `VideoArchive.save_confirmed()` 才去复制——真实录像下每次都会记成 `save_failed`。第一轮测试用的是不删文件的替身，因此没有暴露。现在改为**先复制进档案馆、再释放对话框**，并新增 `ReleasingRecorder` 回归用例（`test_clip_is_archived_before_the_recorder_releases_it`）。
2. **取消后临时录像残留**：`SurrenderDialog.cleanup()` 之前只停后端，不删 `clip_path`。现在显式删除（`missing_ok`），并加启动清理：`cleanup_stale_clips()` 删除 `%TEMP%\NailongQuanxue\clips\` 中超过 24 小时的 `clip-*.mp4`。
3. **API Key 明文落盘**：改为 Windows DPAPI（`app/secure_credentials.py`）按当前账户加密存 `api_key_sealed`，旧明文 Key 启动时自动重新封装；DPAPI 不可用时才退回明文。
4. **核验回调空结果**：`answer is None` 时曾抛 `AttributeError`（按钮已启用但状态未更新），现在统一判为"核验没有返回结果，未判定为通过"。

## 编译与依赖

```powershell
.\.venv\Scripts\python.exe -m compileall -q app tests tools main.py   # OK
.\.venv\Scripts\python.exe -m pip check                              # No broken requirements found.
```

## 源码审计与清理

```powershell
.\.venv\Scripts\python.exe tools\scan_public.py --sources . --allow-fixed-assets --report build\source-audit.json
# {"result": "PASS", "checked_entries": 260, ...}
```

旧音频/笑声路线的清理（`build/v2-cleanup/cleanup-manifest.json`）：删除 28 个文件（15 个脚本 + `__pycache__`），删除前用 `build/refcheck.py` 确认 `app/`、`tests/`、`tools/`、`main.py`、`build.ps1` 对它们**零引用**（`checked_files: 57, references: {}`）。用户真实音视频（`build/p1-local/` 等 7 个目录）**只登记、未删除**，标记 `keep_pending` 等待单独授权。

`publication_authorized=false` 是工具对"未获授权发布"的固定输出。不带 `--allow-fixed-assets` 时报 `assets/fallback_overlay.jpg` 为私有素材——V1.1 起既有行为，不是本轮回归。

## Windows 原生冒烟（源码级，真实 Qt 窗口）

```powershell
.\.venv\Scripts\python.exe tools\v2_smoke.py
# result: PASS, 26.281 s
```

检查项（全部通过）：

1. 首次启动弹出「奶龙劝学 — 配置视觉 AI」，选择「稍后配置」后计时不受影响。
2. 最后十秒倒计时逐秒 `00:10 → 00:01`，提醒与覆盖窗到点出现。
3. 真实解码内置视频 305 帧、尺寸 720×1280、循环 2 次，`audioOutput() is None`（静音确认）。
4. 点覆盖窗「解除限制」→ 投降书打开，填宣言后进入第二步，点「开始录制」在**无摄像头**环境下给出"没有可用摄像头"且「确认投降」保持禁用。
5. 取消投降后休息继续，未被误判为结束。
6. 紧急退出两次交互（取消 → 再次确认）后遮挡与媒体资源全部释放。

```powershell
.\.venv\Scripts\python.exe tools\v2_smoke.py --full-break
# result: PASS, 315.141 s
```

真实五分钟休息：`real_break_elapsed_seconds = 300.063`（设定 300 秒），休息期间视频解码 303 帧、播完 59 轮循环，结束后遮挡自动撤除、无残留窗口。这一项不依赖 AI 配置，符合"未配置 API 时五分钟休息仍自动结束"的要求。

## Windows EXE 冒烟（打包产物）

```powershell
.\.venv\Scripts\python.exe tools\exe_smoke.py 'dist\v2.0-local\NailongQuanxue\NailongQuanxue.exe' --report build\exe-smoke-round2.json
# result: PASS, 18.141 s
```

检查项：首次 AI 提醒出现并可关闭 → EXE 从其他工作目录启动并最小化 → 最小化状态下最后十秒提醒仍出现 → 归零后遮挡窗出现 → 覆盖窗「解除限制」打开投降书 → 投降书底部取消后休息继续、无残留窗口。**未在 EXE 上跑通完整动作挑战**（本机无摄像头）；测试结束时由工具终止其自身启动的进程，不记为"软件正常退出"。

## 构建产物

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1 -SkipTests
# exit=0
```

- 目录包：`dist\v2.0-local\NailongQuanxue\NailongQuanxue.exe`（bundle 421 个文件，114,962,789 B）
- ZIP：`dist\v2.0-local\NailongQuanxue-v2.0.0-Windows-local.zip`，48,237,232 B
- SHA-256：`5a1e4564ecfa330f6bcfff3c0cd4c94c467bdcac9c36e585d397981e1ba6a3c0`
- 审计：bundle 748 项 PASS、ZIP 749 项 PASS；包内只有 `assets/default_break.mp4` 与 `assets/fallback_overlay.jpg` 两个固定素材，**没有** `settings.json`、`.sqlite3`、日志或个人媒体。

## 未验证（不得视为通过）

1. **真实摄像头录制**：本机无摄像头，`camera_recorder` 只能靠测试替身验证状态机；MP4 可播放性、曝光、帧率、12 秒时长准确性未实测。
2. **真实视觉 API 的正反例识别**：无授权 Key，只验证了请求构造、响应解析与错误分类。模型能否稳定区分"两组前倾回正"与"摆拍不动"必须在目标模型上实测，并按结果调整 `MIN_MOTION` 与提示词。
3. **EXE 端到端动作挑战**：需要摄像头与 API 才能跑。
4. 多屏热插拔、DPI 150%、锁屏与睡眠在**录制过程中**的真实行为（自动化用替身覆盖了逻辑分支，真机未测）。

以上四项对应 `MANUAL_TESTS.md` 的实机条目，需要在有摄像头与可用 API 的机器上补测。

## 结论

代码、自动化测试、审计与打包在本机全部通过；V2.0 **达到"本地可试跑"状态**，但**未达到"动作识别已验收"**——真实正反例必须由用户在实机上确认。
