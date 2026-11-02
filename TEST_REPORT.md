# 奶龙劝学 V2.0 测试与验收报告

日期：2026-11-01。分支 `main`，**未 push、未建分支、未发布 Release**。本报告只记录真实执行的命令与结果；未执行的项目一律标注"未验证"。

本文件在第二轮审核后更新：数值全部来自本轮重跑（第一轮记录见 git 提交 `8979e16` 时的版本）。

## 环境

Windows x64（NT 10.0 build 26200），Python 3.11.5，PySide6 Essentials/Addons 6.8.3，PyInstaller 6.16.0，pytest 8.4.2。一块显示器，Qt 逻辑几何 1707×1067，125% 缩放。**本机摄像头 0 个**（`QMediaDevices.videoInputs()` 为空），音频输入 1 个（不参与本应用）。**没有真实视觉 API 授权**。

## 自动化测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# 221 passed, 1 skipped in 8.05s
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
| `tests/test_camera_access.py` | 6 | 摄像头诊断三态文案、阻止时给出授权步骤、设置页 URI |
| `tests/test_camera_recorder.py` | 5 | 过期临时片段清理只删本应用命名、目录缺失不报错、临时目录位置、**编码器占用时延迟删除并重试**、自由文件立即删除 |

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
# result: PASS, 26.296 s
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
# result: PASS, 17.5 s
```

检查项：首次 AI 提醒出现并可关闭 → EXE 从其他工作目录启动并最小化 → 最小化状态下最后十秒提醒仍出现 → 归零后遮挡窗出现 → 覆盖窗「解除限制」打开投降书 → 投降书底部取消后休息继续、无残留窗口。**未在 EXE 上跑通完整动作挑战**（本机无摄像头）；测试结束时由工具终止其自身启动的进程，不记为"软件正常退出"。

## 摄像头与无声录像（真机实测）

```powershell
powershell -ExecutionPolicy Bypass -File tools\camera_check.ps1
# 结果：7/7 通过（枚举、启动、预览、无声录像、取消清理、重新录制、释放）
```

复用正式实现 `app/camera_recorder.py` 的自检工具实测：枚举到 `ASUS FHD webcam` 与 `AvStream Media Device`（IR）；预览 1.2 秒内 9 帧；录像 8.0–9.2 MB、采样 26 帧、跨度 6.69–6.75 秒；`ffmpeg` 探针显示唯一流为 `Video: h264 (Constrained Baseline) 1920x1080 29.63 fps`，**没有音频流**；取消后无残留临时文件；可连续重录；停止后可立刻重新激活设备。

过程中发现并修复：取消录制时编码器仍占用文件导致 `unlink()` 失败、临时 mp4 残留 —— 改为 `_discard()` 延迟重试（250 ms）并在 `_teardown()` 前先 `recorder.stop()`。

打包后的 EXE 也做了同样的诊断（`NailongQuanxue.exe --self-check <json>`），结果：

```json
{"frozen": true, "qt": "6.8.3", "camera": {"state": "blocked", "names": ["ASUS FHD webcam"], "activation_hr": "0x80070005"}}
```

这说明 EXE 里的摄像头诊断链路（Qt + Media Foundation）可以正常工作，能分辨"系统拒绝了本程序"和"没有摄像头"，并给出授权引导；只差用户在 Windows 设置里给这个 EXE 授权一次。
本机限制（重要）：Windows 按"可执行文件路径"单独授权摄像头，未获授权的 python.exe/EXE 会被静默拒绝（`E_ACCESSDENIED`），Qt 因此枚举为 0。用户需在 设置 → 隐私和安全性 → 摄像头 里为本程序授权一次。详见 `docs/P1-摄像头与录像验证报告.md`。

## 构建产物

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1 -SkipTests
# exit=0
```

- 目录包：`dist\v2.0-local\NailongQuanxue\NailongQuanxue.exe`（bundle 423 个文件，114,984,758 B）
- ZIP：`dist\v2.0-local\NailongQuanxue-v2.0.0-Windows-local.zip`，48,254,541 B
- SHA-256：随产物生成，见 `dist\v2.0-local\NailongQuanxue-v2.0.0-Windows-local.zip.sha256`（本机构建记录：`build\build-round3b.log`）
- 审计：bundle 748 项 PASS、ZIP 749 项 PASS；包内只有 `assets/default_break.mp4` 与 `assets/fallback_overlay.jpg` 两个固定素材，**没有** `settings.json`、`.sqlite3`、日志或个人媒体。

## 未验证（不得视为通过）

1. **EXE 内的真实摄像头录制**：源码级实测已通过（见上节），但打包 EXE 的路径未获 Windows 摄像头授权，EXE 内录像仍需用户授权后补测；曝光、画质与 12 秒时长的多机型表现未测。
2. **真实视觉 API 的正反例识别**：无授权 Key，只验证了请求构造、响应解析与错误分类。模型能否稳定区分"两组前倾回正"与"摆拍不动"必须在目标模型上实测，并按结果调整 `MIN_MOTION` 与提示词。
3. **EXE 端到端动作挑战**：需要摄像头与 API 才能跑。
4. 多屏热插拔、DPI 150%、锁屏与睡眠在**录制过程中**的真实行为（自动化用替身覆盖了逻辑分支，真机未测）。

以上四项对应 `MANUAL_TESTS.md` 的实机条目，需要在有摄像头与可用 API 的机器上补测。

## 结论

代码、自动化测试、审计与打包在本机全部通过；V2.0 **达到"本地可试跑"状态**，但**未达到"动作识别已验收"**——真实正反例必须由用户在实机上确认。

## 2.0.1 修复记录（配置无法保存）

- 现象：填写视觉 AI 配置后点「保存配置」，界面显示「未保存：13」，配置未写入。
- 定位：`app/ai_panel.py` 把 `OSError.args[0]` 直接显示出来，13 是 `EACCES`（`PermissionError`）的错误码；
  真实失败点是 `ConfigStore.save()` 写 `settings.json.tmp` 时被系统拒绝（Windows 返回 `errno 13`）。
  代码本身没有问题——是目标目录对当前进程不可写。
- 修复：
  1. `app/config_store.py` 新增 `describe_os_error()` / `ConfigWriteError`，把错误码翻成可操作的中文说明；
     `writable()` 用于目录可写性预检。
  2. `ConfigStore.save()` 对瞬时占用重试 3 次（120/240 ms），失败时保留原文件、清理半成品临时文件，
     并记录完整原因到日志（不含密钥）。
  3. `app/ai_panel.py` 保存/测试/清空全部改为显示真实原因，不再出现裸数字。
  4. `app/main_window.py` 启动时预检数据目录，不可写则弹出说明，并提供「选择新的数据目录」
     （复制现有数据后切换，原目录不删除）与「打开数据目录」两个操作。
  5. `app/settings_dialog.py`「存储与配额」显示当前数据目录与「恢复默认数据目录」。
  6. 自定义数据目录记录在 `HKCU\Software\NailongQuanxue\DataDirectory`，同时写入指针文件作为备份。
- 验证（本机、离线、未调用付费 API）：
  - 用不可写目录复现原缺陷：修改前界面显示「未保存: 13」；修改后显示
    「无法写入配置文件 …\settings.json：Windows 拒绝访问 … 请把本程序加入安全软件的信任列表后重试。」
  - 用可写临时目录验证保存成功：`settings.json` 中存的是 `dpapi:` 密文，不含明文 Key；
    重新读取后协议/Base URL/模型 ID 一致，Key 能被当前 Windows 用户解密（`sk-roundtrip-secret-…` → 校验通过）。
  - `pytest tests/test_storage.py -q` → 31 passed；`tests/test_windows.py -q` → 44 passed。
### 2.0.1 追加：`--self-check` 写不进去时的处理

- 观察：`NailongQuanxue.exe --self-check D:\NailongProbe\self.json` 曾直接抛出
  `PermissionError: [Errno 13] Permission denied`，调用栈是 `main.write_self_check() -> Path.write_text()`。
- 排查结论：
  - `D:\NailongProbe` 的 ACL 对 `Authenticated Users` 是「修改」，路径本身可写；`D:` 为固定磁盘、有 150 GB 可用空间。
  - 同一 EXE 换到不带中文的路径（`C:\NailongTest`、桌面下另一个纯英文目录）后，
    通过计划任务以普通用户身份启动，写 `D:\NailongProbe\*.json` 与
    `%LOCALAPPDATA%\NailongQuanxue\*.json` 均成功（`state=ok`，两个摄像头）。
  - 在受限的调试沙箱里（工作目录内的 Python/EXE）任何用户目录写入都会得到 `EACCES`，
    说明该报错是「运行环境/进程没有写权限」，不是 JSON 内容、路径长度或 Key 的问题。
- 修复：
  1. `--self-check` 的 `PATH` 变为可选；省略时写入
     `%LOCALAPPDATA%\NailongQuanxue\diagnostics\self-check.json`（自动建目录）。
  2. 目标是目录、父目录建不出来、写入被拒，都打印一句中文原因并以退出码 2 结束，
     不再出现未处理的 Traceback；成功时打印实际写入路径。
  3. 版本号统一为 `main.APP_VERSION`，自检 JSON 内 `version` 随之为 `2.0.1`。
  4. `camera_access.Diagnosis.message()/title()` 补上 `OK` 分支，不再把「摄像头可用」写成「状态不明」。
- 关于「未保存: 13」的独立结论（按实际调用栈核对，不因为错误码相同就合并）：
  - 两条路径是**不同的代码位置**：自检失败在 `main.py` 的 `write_self_check()`；
    AI 配置保存失败在 `config_store.py:252` 的 `temporary.write_text()`（写 `settings.json.tmp`）。
  - 相同点只是异常类型：都是 `PermissionError(errno 13, 'Permission denied')`，即目标位置对当前进程不可写。
  - 因此不是 API Key 校验、JSON 结构或 DPAPI 的问题；DPAPI 加解密另行验证通过（见上）。
### 2.0.1 追加：启动不再依赖临时目录

- 现象（用户现场）：EXE 启动即崩，栈为
  `main_window.__init__ → ConfigStore.__init__ → data_directory() → remembered_data_directory() → _pointer_files() → tempfile.gettempdir() → FileNotFoundError: No usable temporary directory found`。
- 根因：上一版为了"默认目录写不进去也有落点"，把 `%TEMP%\NailongQuanxue-location.txt` 放进了指针文件列表，
  而 `tempfile.gettempdir()` 在 TEMP/TMP 缺失、无权限或全部候选都不可用时**会抛异常**；
  这个调用发生在启动链路上，于是整窗初始化失败。
- 修复：
  1. `_pointer_files()` 不再调用 `tempfile`：只用 `%LOCALAPPDATA%\NailongQuanxue\location.txt`
     与 `%APPDATA%\NailongQuanxue\location.txt`；旧版放在 `%TEMP%` 的指针仅作**只读兼容**，
     用 `os.environ["TEMP"/"TMP"] + Path.is_dir()` 判断，取不到就跳过。
  2. `remembered_data_directory()` / `data_directory()` / `ConfigStore._resolve_root()` 三层兜底，
     任何一步抛 `OSError` 都退回默认目录，绝不让异常冒到主窗口。
  3. `ConfigStore.__init__` 把读配置的细节抽到 `_load()`，整体再包一层，读失败只置 `config.error`。
  4. `camera_recorder.clip_directory()` 不再用 `tempfile`：TEMP/TMP 目录存在且可写才用，
     否则退到 `<数据目录>\clips`；建目录失败也不抛异常，由录制流程给出提示。
  5. `MainWindow` 读 `pending-events.json` 的 `exists()` 也加了 `OSError` 保护。
- 验证（模拟"临时目录不可用"）：
  - TEMP/TMP 指向不存在的目录：`data_directory()` = 默认目录、`ConfigStore` 正常读到原 `settings.json`
    （minutes=0/seconds=8）、`clip_directory()` 退到 `<数据目录>\clips`。
  - 把 `tempfile.gettempdir` 替换成直接抛 `FileNotFoundError`：同样不崩溃。
  - 旧版临时目录指针仍被正确读取（兼容）。
  - `pytest tests/test_config_paths.py tests/test_storage.py tests/test_self_check.py tests/test_windows.py -q` → 86 passed。
## 2.0.1 追加：UI 卡死排查与修复

### 现象与证据

用窗口探针（`build/ui_probe.py`，枚举顶层窗口 + WM_NULL 往返）对比两种数据目录状态：

| 数据目录 | 启动后主窗口 `enabled` | 模态窗口 | 额外窗口 |
|---|---|---|---|
| 不可写（用户现场） | **false（点击无响应）** | `#32770` 对话框 | `奶龙劝学 — 数据目录无法写入` + `配置视觉 AI` |
| 可写 | true | 无 | 只有 AI 提醒 |

`WM_CLOSE` 打在模态框上也不会关闭它（Qt 的 QMessageBox 没有默认按钮处理关闭），
主窗口和 AI 窗口都被 `enabled=false` 挡住，看起来就是"整个界面卡死"。

### 根因

上一版（2.0.1 第一轮）在 `MainWindow.__init__` 里用
`QTimer.singleShot(0, self.warn_if_data_unwritable)` 弹出一个 `QMessageBox.exec()`。
`exec()` 会进入嵌套事件循环并把**其他所有窗口**设为不可用；用户的默认数据目录不可写
（此前的 `未保存：13` 即由此而来），所以每次启动都会命中这条路径。
两个单发定时器（AI 提醒 + 数据目录提醒）还会叠加成两层窗口。

### 修复

1. 启动路径上不再有任何 `exec()` 模态框：数据目录问题改为主界面内的
   **内联横幅**（`QFrame#dataBanner`），带「选择新的数据目录 / 打开数据目录 / 关闭提示」，
   主窗口始终保持 `enabled`。
2. 启动回调增加 `isValid()` 与 `RuntimeError` 保护，窗口销毁后到达的定时器不会抛异常
   （测试 teardown 曾经因此报错）。
3. 迁移数据目录后不再立即退出程序，而是更新横幅提示"重启后生效"。
4. 新增 `app/diagnostics.py`：
   - `faulthandler` 把崩溃栈写进 `<数据目录>\logs\crash.log`；
   - 看门狗线程监听主线程心跳（QTimer 250 ms），超过 5 秒没跳动就 dump 所有线程的 Python 栈；
   - 主窗口构建耗时、界面显示耗时写入 `screenbreak.log`。
5. 投降核验增加代次（generation）：重试/取消后到达的旧结果直接丢弃，不会污染下一轮。

### 验证

- 完整 `pytest -q`：**241 passed, 1 skipped**。
- 真实窗口响应性（`tools/ui_responsiveness.py`，windows 平台插件 + QTest 点击）：
  18 项全过，交互阶段事件循环最大停顿 **83.8 ms**（首帧绘制约 1.7 s，属启动成本）。
- 打包 EXE 启动探针（不可写目录）：无模态窗口，主窗口 `enabled=true`。
- `tools/exe_smoke.py`：PASS（17.1 s）。