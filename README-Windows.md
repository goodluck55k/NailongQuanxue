# 奶龙劝学 V1.1 Windows 使用说明

1. 从本项目 v1.1.0 Release 下载 `NailongQuanxue-v1.1.0-Windows-x64.zip` 和 `SHA256SUMS.txt`。
2. 在 PowerShell 执行 `Get-FileHash .\NailongQuanxue-v1.1.0-Windows-x64.zip -Algorithm SHA256`，与校验清单比较。
3. 完整解压 ZIP，进入 `NailongQuanxue` 目录，双击 `NailongQuanxue.exe`。保留 `_internal`、许可与说明文件。无需安装 Python 或请求管理员权限。
4. 设置分钟和秒钟，点「开始计时」。使用计时结束后进入五分钟全屏休息；主屏静音循环视频，副屏纯白。
5. 普通停止/解除限制需要输入投降宣言并主动拍照确认；投降书底部「继续坚持 / 取消」返回原计时。紧急退出仅保留托盘入口，确认后停止监督并返回待机；待机时关闭主窗口才退出软件。

独立的 `NailongQuanxue.exe` 下载项仅为主程序，不能代替完整 ZIP；它仍依赖 `_internal`。本版是解压运行包，没有安装程序，也未进行数字签名。

照片、配置及投降档案保存在 `%LOCALAPPDATA%\NailongQuanxue`，不上传。照片只有主动确认后才保存，上限 100 MiB。相机只在进入第二步后开启，不使用麦克风；取消会清除临时照片。

用户已在 Windows 完成总体手动验收；自动化测试及未单项确认的设备环境见 TEST_REPORT.md 和 MANUAL_TESTS.md。适用目标为 Windows 10/11 x64，各设备、相机、显示器和电源场景请按清单复测。

自有代码为 MIT License，Copyright (c) 2026 goodluck55k。内置视频、备用图片及参考图为用户提供的第三方素材，不自动适用 MIT。保留原内容，来源与指纹见 ASSET_MANIFEST.md（源码中为 assets/ASSET_MANIFEST.md）；依赖许可见 THIRD_PARTY_NOTICES.md 和 licenses。
