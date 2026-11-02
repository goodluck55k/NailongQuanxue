# 奶龙劝学 V2.0 Windows 使用说明

1. 目前尚未发布 Release 附件：请在本地运行 `build.ps1` 生成 `dist\v2.0-local\NailongQuanxue-v2.0.1-Windows-local.zip` 与同名 `.sha256` 文件（源码见 GitHub 仓库）。
2. 在 PowerShell 执行 `Get-FileHash .\NailongQuanxue-v2.0.1-Windows-local.zip -Algorithm SHA256`，与同目录的 `.sha256` 文件比较。
3. 完整解压 ZIP，进入 `NailongQuanxue` 目录，双击 `NailongQuanxue.exe`。保留 `_internal`、许可与说明文件。无需安装 Python 或请求管理员权限。
4. 首次启动会弹出视觉 AI 配置窗口。可以点「稍后配置」先只是计时；但**不配置就无法通过动作挑战**。配置项：接口协议（OpenAI 兼容 / Anthropic / Gemini）、Base URL、API Key、模型 ID。
5. 设置分钟和秒钟，点「开始计时」。使用计时结束后进入五分钟全屏休息；主屏静音循环视频，副屏纯白。
6. 提前停止或解除限制时，依次完成：写投降宣言「我是废物」→ 看完奶龙示范 → 摄像头录制约 12 秒并模仿动作 → 视觉模型判定通过 → 点「确认投降」。判定不通过可无限重录；底部「继续坚持 / 取消」返回原计时。
7. 紧急退出只保留托盘入口，确认后停止监督并返回待机；待机时关闭主窗口才退出软件。紧急退出与五分钟休息自动结束都不受 AI 配置影响。

独立的 `NailongQuanxue.exe` 下载项仅为主程序，不能代替完整 ZIP；它仍依赖 `_internal`。本版是解压运行包，没有安装程序，也未进行数字签名。

配置、档案、录像保存在 `%LOCALAPPDATA%\NailongQuanxue`（`settings.json`、`records.sqlite3`、`videos\`）。录像只有判定通过并确认投降后才保存，上限 512 MiB，可在「设置 → 存储与配额」查看和清理；V1.1 留下的 `photos\` 目录与旧档案仍可读取。相机只在进入录制步骤后开启，不使用麦克风；取消会删除临时录像，也不会写入档案。

动作核验时，从录像里均匀抽取的 10 张画面会发送到**你自己填写的** Base URL；除此之外不上传任何内容。API Key 只写在本机 `settings.json`，不进入日志、档案或构建产物。

自动化测试结果与未覆盖的场景见 TEST_REPORT.md 和 MANUAL_TESTS.md。适用目标为 Windows 10/11 x64，各设备、相机、显示器和电源场景请按清单复测。摄像头与无声录像已在本机实测通过（`tools\camera_check.ps1`，详见 `docs/P1-摄像头与录像验证报告.md`）；真实视觉 API 仍未授权，动作识别这条路径目前只做了模拟测试。

自有代码为 MIT License，Copyright (c) 2026 goodluck55k。内置视频、备用图片及参考图为用户提供的第三方素材，不自动适用 MIT。保留原内容，来源与指纹见 ASSET_MANIFEST.md（源码中为 assets/ASSET_MANIFEST.md）；依赖许可见 THIRD_PARTY_NOTICES.md 和 licenses。
