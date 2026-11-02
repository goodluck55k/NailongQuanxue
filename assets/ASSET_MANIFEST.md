# V2.0 素材清单

| 文件 | 来源 | 类型 | SHA-256 | 发行包 |
|---|---|---|---|---|
| `default_break.mp4` | 项目作者提供的 MP4 | H.264/AAC，720×1280，30fps，时长 5.085011 秒 | `98a2addcaeef70f58bdc7f36740b813a97cd021fc37141a8c0e53e4407fa6c4c` | 是 |
| `fallback_overlay.jpg` | 项目作者提供的最早黄色角色静态图 | 实际 JPEG，1102×1536（原扩展名 `.png`，只改名不转码） | `0cdd2f63eb0f9e4dc1fe8b5b880dbb54c6a53edc137bfdd6f9704746e7fa3f11` | 是 |
| `ui_reference.png` | 项目作者提供的 UI 参考图 | PNG，1448×1086 | `eeb99288c797822f99e7dc96e9d9f8c55a09fbc8bac3e1bde2272a281a6c5831` | 否 |

## 许可

- 三项登记素材均由项目作者提供，并授权随本项目源码与 Windows 发行包分发；授权仅限本项目，不适用 MIT，也不构成对外再许可。
- MIT 只覆盖原创代码；第三方依赖的许可见 `THIRD_PARTY_NOTICES.md` 与 `licenses/`。
- 未编辑、未转码、未替换、未去除水印。

## 使用规则

1. `default_break.mp4` 是唯一内置视频；不要新增更换视频、管理视频目录或用户上传视频的功能。
2. 永远静音；不得因容器内含 AAC 轨而输出声音。
3. 主屏 9:16 视频等比例完整显示，其余部分纯白；副屏只用纯白遮挡。
4. 播放器异常先回退 `fallback_overlay.jpg`，再失败则白底文字，五分钟计时不中断。
5. `ui_reference.png` 只作审美与布局参考，不照搬参考图的左侧导航栏，也不作为整窗背景。
6. 打包资源必须同时支持源码路径与 PyInstaller 路径，原文件字节不变。
7. 素材字节变化会让 `tools/scan_public.py` 的固定素材白名单校验失败；需要同步更新本文件的哈希，而不是关闭审计。
8. 发行包内不得出现照片、录像、`settings.json`、`records.sqlite3` 或日志；`build.ps1 -Release` 与 `tools/verify_bundle.py` 会强制检查。
