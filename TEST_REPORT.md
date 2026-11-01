# 奶龙劝学 V2.0 测试与验收报告

日期：2026-11-01。分支 `main`，**未 push、未建分支、未发布 Release**。本报告只记录本轮真实执行的命令与结果；未执行的项目一律标注"未验证"。

## 环境

Windows x64（NT 10.0 build 26200），Python 3.11.5，PySide6 Essentials/Addons 6.8.3，PyInstaller 6.16.0，pytest 8.4.2。一块显示器，Qt 逻辑几何 1707×1067，125% 缩放。**本机摄像头 0 个**（`QMediaDevices.videoInputs()` 为空），音频输入 1 个（不参与本应用）。**没有真实视觉 API 授权**。

## 自动化测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# 200 passed, 1 skipped in 8.08s
```

跳过项是既有约定：`tests/test_assets.py:41` 私有图片不在公开源码中时跳过。

| 测试文件 | 用例数 | 覆盖内容 |
|---|---|---|
| `tests/test_timer.py` | 32 | 原 V1 计时核心：截止时间、ceil、提醒去重、有效使用时钟 |
| `tests/test_windows.py` | 43 | 主窗口、四设置分页、四页投降对话框、覆盖窗、托盘、紧急退出、档案写入、未配置 AI、无限重试、锁屏取消录制、归档失败仍放行、多轮循环 |
| `tests/test_storage.py` | 27 | 档案库 schema 3 迁移（`.pre-v11.sqlite3` / `.pre-v3.sqlite3`）、录像列往返、`delete_video` 置空与后缀校验、照片配额、配置原子保存 |
| `tests/test_supervision.py` | 20 | 四阶段状态机 `writing→video→recording→verified`、跨阶段非法调用、休息完成与确认竞争、用量到期取消旧流程 |
| `tests/test_public_audit.py` | 20 | 打包/源码审计规则：拒绝个人媒体与运行数据、固定素材指纹 |
| `tests/test_ai_config.py` | 14 | 协议/地址/模型/密钥校验、状态文案不泄露 Key、`settings.json` 往返与清除 |
| `tests/test_action_verdict.py` | 11 | 判定三态：静止不通过、组数不足、缺手位/缺前倾、模型拒绝、证据不足、提示词内容 |
| `tests/test_vision_api.py` | 10 | 三协议 endpoint/headers/payload、10 帧截断、JSON 提取与别名解析、auth/http/timeout/network/bad_response 六类错误 |
| `tests/test_video_archive.py` | 9 | MP4 头校验、复制而非移动、唯一命名、配额与警告阈值、网络路径拒绝、失败不留残件 |
| `tests/test_frame_sampler.py` | 6 | 采样节流与缩放、容量上限、等距取帧含首尾、运动量估计、JPEG 编码 |
| `tests/test_assets.py` | 5 | 固定素材存在性与指纹 |
| `tests/test_v11_resources.py` | 4 | 资源解析只允许文件名、防止路径穿越 |

判定逻辑的关键回归（对应验收要求"静态摆拍不能误判为两组动作"）：

- `test_static_pose_is_rejected_even_if_model_claims_pass`：模型返回 `pass=true, cycles=2`，但抽帧运动量低于阈值 → 结论为**未通过**。
- `test_missing_hand_or_lean_blocks_pass`：模型自述通过但缺手位或缺前倾 → 未通过，理由以"模型自述通过，但"开头。
- `test_technical_failure_never_enables_confirm`：接口报错、超时、返回不可解析 → 确认按钮永不启用。
- `test_too_few_frames_never_reaches_model`：帧数不足时根本不会调用模型。

## 编译与依赖

```powershell
.\.venv\Scripts\python.exe -m compileall -q app tests tools main.py   # OK
.\.venv\Scripts\python.exe -m pip check                              # No broken requirements found.
```

## 源码审计

```powershell
.\.venv\Scripts\python.exe tools\scan_public.py --sources . --allow-fixed-assets --report build\source-audit.json
# {"result": "PASS", "checked_entries": 257, ...}
```

`publication_authorized=false` 是工具对"未获授权发布"的固定输出，与本轮不推送的约定一致。不带 `--allow-fixed-assets` 时报 `assets/fallback_overlay.jpg` 为私有素材——这是 V1.1 起就存在的已知行为，不是本轮回归。

## Windows 原生冒烟（源码级，真实 Qt 窗口）

```powershell
.\.venv\Scripts\python.exe tools\v2_smoke.py
# result: PASS, 26.343 s
```

检查项（全部通过）：

1. 首次启动弹出「奶龙劝学 — 配置视觉 AI」，选择「稍后配置」后计时不受影响。
2. 最后十秒倒计时逐秒 `00:10 → 00:01`，提醒与覆盖窗到点出现。
3. 真实解码内置视频 306 帧、尺寸 720×1280、循环 2 次，`audioOutput() is None`（静音确认）。
4. 点覆盖窗「解除限制」→ 投降书打开，填宣言后进入第二步，点「开始录制」在**无摄像头**环境下给出"没有可用摄像头"且「确认投降」保持禁用。
5. 取消投降后休息继续，未被误判为结束。
6. 紧急退出两次交互（取消 → 再次确认）后遮挡与媒体资源全部释放。

```powershell
.\.venv\Scripts\python.exe tools\v2_smoke.py --full-break
# result: PASS, 315.141 s
```

真实五分钟休息：`real_break_elapsed_seconds = 300.078`（设定 300 秒），休息期间视频解码 308 帧、播完 59 轮循环，结束后遮挡自动撤除、无残留窗口。这一项不依赖 AI 配置，符合"未配置 API 时五分钟休息仍自动结束"的要求。

## Windows EXE 冒烟（打包产物）

```powershell
.\.venv\Scripts\python.exe tools\exe_smoke.py 'dist\v2.0-local\NailongQuanxue\NailongQuanxue.exe' --report build\v2-exe-smoke\exe.json
# result: PASS, 18.156 s
```

检查项：首次 AI 提醒出现并可关闭 → EXE 从其他工作目录启动并最小化 → 最小化状态下最后十秒提醒仍出现 → 归零后遮挡窗出现 → 覆盖窗「解除限制」打开投降书 → 投降书底部取消后休息继续、无残留窗口。**未在 EXE 上跑通完整动作挑战**（本机无摄像头）；测试结束时由工具终止其自身启动的进程，不记为"软件正常退出"。

## 构建产物

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1 -SkipTests
```

- 目录包：`dist\v2.0-local\NailongQuanxue\NailongQuanxue.exe`（bundle 合计 114,956,176 B）
- ZIP：`dist\v2.0-local\NailongQuanxue-v2.0.0-Windows-local.zip`，48,228,461 B
- SHA-256：`05b5ed6ed39dbeb37ce80b2ba2ff12d3533460e8d503a86361c23c031461fac6`
- 审计：bundle 747 项 PASS、ZIP 748 项 PASS；`prune_bundle.py` 移除未用图像插件；文档与 `licenses\` 一并入包；`LOCAL-ONLY-NOT-PUBLISHED.txt` 标注"Local V2.0 candidate"。

## 未验证（不得视为通过）

1. **真实摄像头录制**：本机无摄像头，`camera_recorder` 只能靠测试替身验证状态机；MP4 可播放性、曝光、帧率、12 秒时长准确性未实测。
2. **真实视觉 API 的正反例识别**：无授权 Key，只验证了请求构造、响应解析与错误分类。模型能否稳定区分"两组前倾回正"与"摆拍不动"需要在目标模型上实测，并按结果调整 `MIN_MOTION` 与提示词。
3. **EXE 端到端动作挑战**：需要摄像头与 API 才能跑。
4. 多屏热插拔、DPI 125%/150%、锁屏与睡眠在**录制过程中**的真实行为（自动化用替身覆盖了逻辑分支，真机未测）。

以上四项对应 `MANUAL_TESTS.md` 第 5–10 条与第 15–16 条，需要在有摄像头与可用 API 的机器上补测。

## 结论

代码、自动化测试、审计与打包在本机全部通过；V2.0 **达到"本地可试跑"状态**，但**未达到"动作识别已验收"**——真实正反例必须由用户在实机上确认。
