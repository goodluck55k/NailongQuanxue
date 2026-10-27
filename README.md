# 奶龙劝学 V1.1

**少玩一会儿，多学一点。** Windows 本地、自行启动的监督与休息工具，基于原 ScreenBreak V1 增量升级。无侧边栏；奶油黄单页、分秒输入、圆环倒计时、右上角设置。

当前版本 **1.1.0**。[下载 Windows 完整 ZIP](https://github.com/goodluck55k/NailongQuanxue/releases/tag/v1.1.0)，解压后运行 `NailongQuanxue.exe`。安装与校验说明见 [README-Windows.md](README-Windows.md)。自动测试及用户 Windows 手动验收记录见 [TEST_REPORT.md](TEST_REPORT.md)；不同设备复测清单见 [MANUAL_TESTS.md](MANUAL_TESTS.md)。

## 使用

1. 设置分钟（0–999）与秒钟（0–59），总时长必须大于零。第一次默认 30:00；以后保留上次设置。
2. 点击「开始计时」。最小化仍计时；计时中关闭主窗口会隐藏到托盘，双击托盘图标恢复。待机时关闭窗口会退出软件。
3. 使用时间归零后，每屏全屏白色遮挡；主屏播放固定内置视频、显示休息倒计时，右下角仅保留「解除限制」按钮；副屏只显示纯白。
4. 五分钟后自动结束休息并显示约五秒通知。设置为自动循环时，接着进入下一轮使用计时。

最后 5/4/3/2/1 分钟各提醒一次，普通提示约四秒，最后十秒持续显示 00:10–00:01。提示静音、不抢焦点、不堆叠。

## 停止、投降与紧急退出

普通停止（使用中「停止计时」、休息中「解除限制」、托盘「申请停止监督」）需要两步：

1. 手动准确输入 `我是废物`，不能有多余空格。
2. 主动进入相机步骤，点击拍照、查看预览，再点击「确认投降」。可以重拍或取消；不做人脸识别。

投降窗口打开期间原计时继续。使用到点或五分钟结束时，旧投降窗口及临时照片立即失效。投降会终止整个自动循环。

**紧急退出**仅保留托盘入口，无需文字或拍照，经过一次确认后立即停止整个监督、撤下全部遮挡并返回待机；不代表关闭软件。随后在待机界面点 `×` 可完全退出。确认框独立于最小化/隐藏的主窗口；重复点击会重新显示并激活确认框。休息全屏、投降书第一步与拍照第二步均已按用户要求移除该按钮；投降书底部仅保留「继续坚持 / 取消」。

## 设置与照片

右上角只有三个设置栏目：监督模式、照片存储、投降档案馆。没有自定义视频、视频预览/更换、开机自启动或额外统计侧栏。

- 手动计时为默认；自动循环也必须点击开始一次。运行中修改偏好只影响下次手动开始，不改变本轮模式。
- 默认数据目录：`%LOCALAPPDATA%\NailongQuanxue`。
- 照片：`photos` 子目录；配置：`settings.json`；档案：`records.sqlite3`；日志：`logs`。
- 相机只在主动进入第二步后开启，不启用麦克风，不录视频。照片先留内存；取消、锁屏、阶段变化或紧急退出会清除。
- 确认后保存 JPG。100 MB 上限按 `100 × 1024 × 1024` 字节计算，包含本次编码后的新照片；90 MB 起显示清理提醒。
- 配额不足仍需拍照，但确认后不写新照片，事件标记 `quota_exceeded`。目录失效时标记 `save_failed`；不会伪称保存成功，也不会阻止紧急退出。
- 切换目录不移动/删除旧照片；旧照片仍可从原档案访问。不能选择 UNC 或映射网络盘，不自动清理。
- 档案默认不加载照片缩略图。只有主动点击查看才打开本地照片。删除照片和删除档案分别确认；清空档案保留照片。

异常退出、断电或系统重启后再次打开，一律待机，不恢复计时、遮挡或相机。数据库迁移使用增量加字段并保留迁移前备份；损坏数据不静默覆盖。写入失败时显示错误，并尽可能保留待保存事件，原档案不丢弃。

## 计时与系统边界

使用计时只累计解锁且未休眠的有效时间，Windows 结合 `QueryUnbiasedInterruptTime` 与会话/电源通知暂停。休息计时使用包含休眠的 `GetTickCount64`，独立计算 300 秒；不会按视频循环次数计时。自动循环在锁屏期间进入下一轮时，使用时钟保持暂停直到解锁。

视频 H.264、720×1280、约 5.085 秒，循环播放且不连接音频输出。画面完整居中等比例适配，余量纯白，不拉伸、不裁切；播放器缺失、错误、持续黑画面或长时间无帧时使用固定备用 JPG，再失败时白底文字。按钮由同一个 Qt 绘制窗口承载，视频不会用原生子窗口遮住控制层。

应用是普通用户会话中的置顶窗口，不是系统安全锁屏。不拦截 Ctrl+Alt+Del、任务管理器、安全桌面、正常关机或重启；不提权、不安装服务、驱动或全局输入钩子。独占全屏或更高权限窗口可能覆盖应用。系统/事件循环长时间暂停后，恢复时立即复查截止时间，不承诺实时系统级响应。

## 源码运行与测试

Windows 10/11 x64、Python 3.11；本地环境为 Python 3.11.5。请在含 `main.py` 的原项目目录打开 PowerShell：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe main.py
# 只缩短使用计时；强制休息仍为真实 300 秒
.\.venv\Scripts\python.exe main.py --test-seconds 15
.\.venv\Scripts\python.exe -m pytest -q
```

PySide6 Essentials 与 Addons 固定 6.8.3；Addons 提供 QtMultimedia 摄像头及视频模块。使用标准库 SQLite，不需要 OpenCV、模型、服务或其他编解码器安装包。

pytest 使用 offscreen 和合成相机帧，不能代替物理摄像头、声音听测、Windows 锁屏/休眠或多屏验收。V1 计时核心测试保留；因 V1.1 改变退出与解除规则，相关 GUI 用例已更新为新需求。

```powershell
# 可见 Windows 测试，会临时出现全屏休息画面并自动解除
.\.venv\Scripts\python.exe tools/v11_smoke.py
# 完整五分钟测试（不缩短休息时钟）
.\.venv\Scripts\python.exe tools/v11_smoke.py --full-break
# 无可见遮挡的真实 300 秒时钟/视频长测，不代替全屏人工验收
.\.venv\Scripts\python.exe tools/real_duration_check.py
```

开发测试可设置 `NAILONG_DATA_DIR` 到项目 `build` 下，隔离数据，避免触碰个人档案。正式使用不要设置该环境变量。V1 源码快照和原 EXE 保留在 `build/backups/v1` 与原 `dist/public`、`dist/private`，未被 V1.1 覆盖。

## Windows EXE 构建

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

脚本先测试，再构建 PyInstaller `--onedir --windowed`。输出：

```text
dist/v1.1-local/NailongQuanxue/NailongQuanxue.exe
dist/v1.1-local/NailongQuanxue-v1.1.0-Windows-local.zip
```

必须完整解压并保留 `_internal`、许可证和依赖说明，不能只复制 EXE。固定 MP4 和备用 JPG 内置；`ui_reference.png` 只作开发参考，不进入 EXE 包。脚本扫描目录、EXE 内嵌归档和 ZIP，拒绝照片/数据库/配置/日志，只允许清单中指纹一致的固定素材；生成 SHA-256。扫描不是防病毒认证。

`-Python` 可指定解释器，`-SkipTests` 仅适合已经通过测试后重复打包。脚本不签名、不提权、不自动发布；包内有本地候选标识。

正式发行包装复用已验收程序，不重新编译 EXE：

```powershell
.\.venv\Scripts\python.exe tools/prepare_release.py
```

脚本核对原验收 ZIP/EXE、内嵌应用源码及全部运行文件，只更新说明并输出 `dist/v1.1.0/NailongQuanxue-v1.1.0-Windows-x64.zip`。独立下载的 EXE 仍需 ZIP 内 `_internal` 目录。

## 模块与迁移

保留 `app/timer_controller.py` 及其测试，继续用于阈值和截止时间；`usage_clock.py`、`supervision.py` 为其增加有效时间、休息和投降令牌。原 `main_window.py`、`reminder_window.py`、`overlay_window.py`、`screen_manager.py` 增量升级为新 UI 和视频覆盖；新增托盘、会话桥、相机、存储及档案模块。模块详情见 [MIGRATION_V1_1.md](MIGRATION_V1_1.md)。

## 许可与发布

代码沿用 [MIT License](LICENSE)，Copyright (c) 2026 goodluck55k。**MIT 不自动授权第三方图片、视频和参考图**。素材原字节与来源见 [assets/ASSET_MANIFEST.md](assets/ASSET_MANIFEST.md)；用户已授权保留内置 MP4 和 JPG 原始内容进行发布，这不改变第三方素材权属，也不将素材重新许可为 MIT。依赖各有许可，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

公开源码清单和素材状态见 `PUBLIC_FILES.txt`、`RELEASE_CHECKLIST.md`。Release 同时提供源码 ZIP、Windows 完整 ZIP、主程序、使用说明与 SHA256SUMS.txt。
