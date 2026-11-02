# 奶龙劝学 V2.0.1 Windows 使用说明

## 一、下载与校验

1. 打开 Release 页面：<https://github.com/goodluck55k/NailongQuanxue/releases/tag/v2.0.1>
2. 下载完整压缩包 `NailongQuanxue-v2.0.1-Windows-x64.zip`（约 48 MB）。**不要单独下载 EXE**——程序还需要同目录的 `_internal` 与 `assets`，缺少它们无法启动。
3. 同页下载 `NailongQuanxue-v2.0.1-Windows-x64.zip.sha256`，然后在 PowerShell 中执行：

```powershell
certutil -hashfile .\NailongQuanxue-v2.0.1-Windows-x64.zip SHA256
Get-Content .\NailongQuanxue-v2.0.1-Windows-x64.zip.sha256
```

两处哈希一致，说明下载完整。

## 二、解压与启动

4. 完整解压 ZIP，进入 `NailongQuanxue` 目录，双击 `NailongQuanxue.exe`。保留 `_internal`、`assets`、许可与说明文件；不要只把 EXE 拖到别处。
5. 无需安装 Python，也不需要管理员权限。EXE **没有数字签名**，也不是安装程序；SmartScreen 提示"未知发布者"时选择「更多信息 → 仍要运行」。
6. 首次启动会弹出视觉 AI 配置窗口，可以先点「稍后配置」——计时与五分钟休息不需要 AI。但**不配置就无法通过动作挑战**。配置项：接口协议（OpenAI 兼容 / Anthropic / Gemini）、Base URL、API Key、模型 ID。
7. 设置分钟和秒钟，点「开始计时」。计时结束后进入五分钟全屏休息：主屏静音循环视频，副屏纯白。
8. 提前停止或解除限制时，依次完成：写投降宣言「我是废物」→ 看完奶龙示范 → 摄像头录制约 12 秒并模仿动作 → 视觉模型判定通过 → 点「确认投降」。判定不通过可无限重录；底部「继续坚持 / 取消」返回原计时。
9. 紧急退出只保留托盘入口，确认后停止监督并返回待机；待机时关闭主窗口才会退出软件。紧急退出与五分钟休息自动结束都不受 AI 配置影响。

## 三、摄像头权限

部分电脑（包括本项目的开发机）会按**程序路径**单独授予摄像头权限，因此可能出现"系统设置里摄像头是开的，程序却提示没有可用摄像头"。处理方式：

1. 打开 设置 → 隐私和安全性 → 摄像头，确认「让桌面应用访问你的相机」为开启状态；
2. 在同一个页面里找到本程序并允许；如果列表里没有，先运行一次程序触发授权记录；
3. 若仍失败，可在源码目录运行 `tools\camera_check.ps1`（会打印设备、隐私键、已授权程序与 FrameServer 状态，并用本机 Python 直接做一次无声录像自检）；加 `-OpenSettings` 可直接跳到摄像头隐私页。

摄像头只在进入「录制」那一步开启，录像结束即关闭，不录麦克风、不提取音频；取消会删除临时录像，也不会写入档案。无声录像已在本机实测通过（`docs\P1-摄像头与录像验证报告.md`）。

## 四、数据与隐私

- 配置、档案、录像保存在 `%LOCALAPPDATA%\NailongQuanxue`（`settings.json`、`records.sqlite3`、`videos\`）。如果该目录不可写，程序会退回到 EXE 同级的 `NailongData`，并在主界面顶部显示提示，可自行选择新的数据目录。
- 录像只有判定通过并确认投降后才保存，上限 512 MiB，可在「设置 → 存储与配额」查看和清理；V1.1 留下的 `photos\` 目录与旧档案仍可读取。
- 动作核验时，从录像里均匀抽取的 10 张画面会发送到**你自己填写的** Base URL；除此之外不上传任何内容。
- API Key 用 Windows DPAPI 加密后写入本机 `settings.json`（`api_key_sealed`），不进入日志、档案或构建产物。**如果系统无法提供 DPAPI，程序会拒绝保存新的 Key 并给出提示，不会退回到明文保存**；旧版本留在文件里的明文 Key 仍可读取，并会在 DPAPI 可用时自动转为加密形式。

## 五、已知限制

- 自动化测试结果与未覆盖的场景见 TEST_REPORT.md 和 MANUAL_TESTS.md。适用目标为 Windows 10/11 x64，各设备、相机、显示器和电源场景请按清单复测。
- **真实视觉 API 未授权、未实测**：动作识别这条路径目前只做了模拟接口测试，正反例的实机判定需要你配置自己的视觉模型后验证。
- EXE 未做代码签名，请只从本仓库的 Release 页面下载。

## 六、许可

自有代码为 MIT License，Copyright (c) 2026 goodluck55k。内置视频、备用图片及参考图由项目作者提供，随本项目源码与发行包分发，不适用 MIT，也不构成对外再许可；来源与指纹见 `assets/ASSET_MANIFEST.md`。依赖许可见 `THIRD_PARTY_NOTICES.md` 与 `licenses\`。
