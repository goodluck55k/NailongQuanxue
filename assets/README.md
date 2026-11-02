# V2.0 内置素材说明

本目录的素材随「奶龙劝学」源码与 Windows 发行包（`NailongQuanxue-v2.0.1-Windows-x64.zip`）一起分发。

| 文件 | 用途 | 是否进入发行包 |
|---|---|---|
| `default_break.mp4` | 唯一内置的休息示范视频；主屏完整等比例、静音循环 | 是（`assets/`，打包后位于 `_internal/assets/`） |
| `fallback_overlay.jpg` | 视频失败时的备用画面，主界面右侧装饰也用它 | 是（同上） |
| `ui_reference.png` | 开发时的界面视觉参考 | 否，只留在源码仓库 |
| `overlay.jpg` | V1 遗留的本地图片，V2 不加载也不打包 | 否 |

## 许可状态

- 上面的视频、图片与参考图由项目作者提供，并授权随本项目源码与发行包分发。该授权只覆盖本项目，**不适用 MIT**，也不构成对外再许可；引用本项目时请保留来源记录。
- `MIT License`（见仓库根目录 `LICENSE`）只覆盖本项目原创代码，不改变第三方素材的权属。
- 素材未编辑、未转码、未替换，也未去除水印；项目不提供更换或自定义休息视频的入口。

## 打包与审计

- `build.ps1` 只用 `--add-data` 打入 `default_break.mp4` 与 `fallback_overlay.jpg`；`ui_reference.png`、`overlay.jpg` 不会进入 EXE 或 ZIP。
- `tools/scan_public.py` 维护固定素材白名单（文件名 + SHA-256）。素材字节一旦变化，审计会失败，必须同步更新 `ASSET_MANIFEST.md`。这是发行前必须通过的检查，不要在素材改动后直接关闭审计。
- 发行包同样不允许出现任何用户数据（照片、录像、`settings.json`、`records.sqlite3`、日志）；`build.ps1 -Release` 与 `tools/verify_bundle.py` 会逐项检查。

## 播放行为（保持不变）

主屏按 Contain 完整显示视频、不裁切不拉伸，空余部分是纯白；副屏只有纯白遮挡；视频始终静音（即使容器里有音轨也不输出）。播放器异常时先回退到 `fallback_overlay.jpg`，再失败则白底文字，且不会中断五分钟计时与「解除限制」入口。

用户自己的照片与录像保存在独立的数据目录（默认 `%LOCALAPPDATA%\NailongQuanxue`），不得放入 `assets/` 或发行候选。
