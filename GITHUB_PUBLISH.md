# V1.1 正式发布流程

2026-10-27 用户已明确授权在 `goodluck55k` 下创建公开仓库 `NailongQuanxue`，推送完整源码至 `main`，创建 `v1.1.0` Release 并上传经过测试的 Windows EXE/ZIP。无需重复询问发布许可。此授权覆盖保留内置视频和备用图片原始内容的发布；自有代码 MIT 与第三方素材仍分别说明。

用户本轮明确确认已在 Windows 完成手动验收，并更正约 1430 秒记录为本人手动退出，不能归因为程序自动结束延迟。按现有授权执行正式发布；未逐项确认的环境仍不标记通过。新发现的实际测试失败、隐私泄漏或程序不可用问题须先停止并报告。

实际证据见 TEST_REPORT.md；最终测试报告为 `build/publish-v110-final-tests.xml`，包装校验为 `build/publish-v110-package.json`。公开源码按 PUBLIC_FILES.txt 精确清单。第三方素材按 assets/ASSET_MANIFEST.md 保持原字节，不自动获得 MIT 许可。私人照片、投降数据库、配置、缓存、虚拟环境、日志和临时捕获不得公开。

发布从 `build` 下仅包含精确清单文件的独立 checkout 整理初始提交，保留原工作区旧 V1 暂存。使用 GitHub noreply 作者邮箱，不公开本机私人邮箱。不上传旧 V1 工作流，不 force push，不覆盖已有 Release。正式发布先创建草稿 Release，上传资产并校验其大小和 SHA256 后再转为正式版；最终结果写入本地 `build/publish-v110-result.json`。
