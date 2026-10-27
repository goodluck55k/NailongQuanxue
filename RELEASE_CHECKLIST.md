# V1.1 发布前核查清单

**2026-10-27 已获得发布授权与用户 Windows 手动验收总体确认**：公开仓库 `goodluck55k/NailongQuanxue`、`main` 分支、`v1.1.0` Release 及测试过的 Windows EXE/ZIP，无需再次确认发布许可。约 1430 秒记录按用户说明更正为手动退出。新发现实际阻塞问题时先报告；未单项确认的环境不标通过。MIT 代码许可已确认（2026 goodluck55k）；第三方素材不自动适用 MIT。

## 交付候选

- 验收基线目录：`dist/v1.1-local/NailongQuanxue/`，其程序和依赖原样复用。
- 正式应用目录：`dist/v1.1.0/NailongQuanxue/`，必须完整保留 `_internal`。
- Windows 完整 ZIP：`NailongQuanxue-v1.1.0-Windows-x64.zip`；另附原始主程序 NailongQuanxue.exe、使用说明及 SHA256SUMS.txt。
- 正式源码 ZIP：`NailongQuanxue-v1.1.0-source.zip`，从最终提交导出，严格对应 PUBLIC_FILES.txt。

## 素材与代码许可区分

| 素材 | 本地 EXE 包 | 本地源码候选 | 公开授权 |
|---|---|---|---|
| assets/default_break.mp4 | 包含 | 包含 | 用户已授权保留原内容发布；第三方素材不改为 MIT |
| assets/fallback_overlay.jpg | 包含 | 包含 | 用户已授权保留原内容发布；第三方素材不改为 MIT |
| assets/ui_reference.png | 不包含 | 包含，供开发参考 | 用户提供的开发参考，单独列示来源；不自动获得 MIT 许可 |
| assets/overlay.jpg（旧 V1） | 不包含 | 不包含 | 保持本地忽略 |
| 用户照片/数据库/配置/日志 | 不包含 | 不包含 | 私人数据，禁止随包公开 |

`scan_public.py --allow-fixed-assets` 只允许上述固定素材在正确路径且指纹完全一致；它是本地候选数据审查开关，**不授予再分发许可**。源代码中的个人路径/常见密钥规则、EXE CArchive/PYZ 及 ZIP 内容同时检查。扫描不是通用安全认证。

`.gitignore` 继续忽略用户 assets、照片、数据库、配置、环境、build/dist 和日志。`PUBLIC_FILES.txt` 是 V1.1 精确候选；恢复发布时应只纳入已列明的固定素材，不放开忽略整个素材目录。当前 Git 暂存保留旧 V1 基线，不能直接作为 V1.1 推送。

## 发布核对规则

- 按 TEST_REPORT 区分用户总体手动验收、Codex 实际自动测试及未单项确认的设备组合；不补造实机记录。
- 保持第三方素材来源与许可独立说明，不将用户的发布授权描述成素材权属证明或 MIT 素材授权。
- 重新检查实际 Git 暂存、历史、发布 ZIP 和用户数据排除。
- 仓库名称、所有者、可见性及 Push/Release 范围已经明确授权；使用独立精确 checkout，不重复询问发布许可。

原 V1 的 GitHub Actions 仅作历史参考，正式初始提交不启用或上传该工作流。最终以 GitHub 返回的 main Commit、v1.1.0 标签及 Release 资产大小/摘要为准，不提前宣称已发布。
