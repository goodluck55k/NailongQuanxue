# 奶龙劝学 V1.1 测试与验收报告

日期：2026-10-27。以下分别记录自动测试、Windows 自动冒烟、用户手动验收及未逐项确认的环境。

## 最终发布复核

用户已授权发布到 `goodluck55k/NailongQuanxue`，分支 `main`、Release `v1.1.0`。本轮用户明确声明已亲自在 Windows 完成手动验收，并要求执行正式发布。此项记录为**用户手动验收总体通过**，不是 Codex 新执行的实机测试，也不扩展为每种设备、DPI、电源场景均已逐项验证。

- 本轮重新执行全套自动测试：**136 passed，0 failed，0 skipped，7.06 秒**。命令：`.\.venv\Scripts\python.exe -m pytest -q --junitxml=build/publish-v110-final-tests.xml --basetemp=build/qa-publish-v110-final`。此前发布复核另有 136 passed / 7.24 秒的独立记录，未混用为本轮耗时。
- 最终源码精确清单 **245 个文件**审查通过；正式包装审查合计 2458 条、展开 10 个归档和 3 次 EXE 检查，见 `build/publish-v110-package.json`。此前 243 文件清单及验收候选的单独扫描见 `build/release-check-20261027-*.json`。未发现扫描规则涵盖的密钥、私人照片、投降数据库、缓存、虚拟环境或日志；结论限于精确候选清单和现有扫描规则。
- 验收候选 EXE 为 1,968,779 字节，原候选 ZIP 为 50,789,128 字节，SHA-256 与下文历史记录一致。本轮不重新编译应用；已展开 EXE 并比对 22 个应用模块（app 全部模块及 main），与当前源码编译结果一致。
- 正式 ZIP 只更新说明及发行包装：EXE、运行库与固定素材逐文件保持原字节。ZIP 整体 SHA-256 因说明文件更新而改变，不会将其描述为旧 ZIP 完全相同。最终 SHA256SUMS.txt 随 Release 提供。
- 正式包实际核对 **240 个运行文件全部一致**，应用没有重编译。正式 ZIP：`dist/v1.1.0/NailongQuanxue-v1.1.0-Windows-x64.zip`，50,792,196 字节，SHA256 `bf869a11513bd11c997a9df7a629a0703c60b29f29cdeda0cef4c73ab75db4d5`。
- 本轮对正式包实际执行 Windows 短流程检查：**PASS，18.219 秒**，见 `build/publish-v110-smoke/exe.json`。验证启动、最小化、提示、15 秒归零、全屏休息及打开/取消投降书。未开启相机；结束时由工具终止其自身测试进程，不将其计为正常退出成功。
- 默认视频与备用图 SHA-256 与素材清单完全一致；未编辑、转码或替换。MIT 标准文本与 `2026 goodluck55k` 版权保持，第三方素材与代码许可分开说明。
- Windows 现有结果：最新 EXE 短流程检查通过（17.766 秒），但只覆盖启动、提示、休息遮挡、打开与取消投降书，最终由工具结束测试进程；不能视作正常退出验收。此前无可见遮挡的真实 300 秒视频/计时测试通过（300.094 秒），不能视作完整全屏验收。
- **更正约 1430 秒记录**：用户明确说明该次由本人手动退出，不能归因为程序自动结束延迟。原始日志保留，只更正文档解释；该记录既不作为自动五分钟测试成功，也不作为程序延迟故障。
- 未逐项说明的物理相机保存/重拍、音频听测、多屏/热插拔、125% DPI、锁屏/休眠/唤醒及无 Python 干净 Windows 等，保持“未单项确认”，不补造通过记录。下文保留此前自动化覆盖和设备范围。
- 按 PUBLIC_FILES.txt 精确清单整理 V1.1 初始提交，排除旧 V1 工作流、私人照片及所有运行数据，不直接推送原来的旧暂存区。

扫描工具的 `publication_authorized=false` 为其不授予许可的固定输出，不代表用户未授权。本轮已获得正式 Push / Release 授权。

## 本次变更：移除投降书两步中的紧急退出按钮

按用户截图要求，投降书第一步和拍照第二步均移除「紧急退出」，底部仅保留整行「继续坚持 / 取消」。清除对应信号连接和样式，摄像头错误提示改为重试或取消返回。此前休息全屏的按钮删除保留，紧急退出仅保留托盘入口。视频、五分钟计时和投降规则未变。

- 全套自动测试：**136 passed，0 failed，0 skipped，6.93 秒**，报告 `build/remove-surrender-buttons-all.xml`。覆盖两个步骤均无紧急退出按钮、使用合成帧拍照后点击保留的取消按钮会停止相机、不保存临时照片、继续原计时；相机故障时仍可通过托盘紧急退出。
- 编译检查与依赖检查通过；无依赖冲突。
- Windows 新 EXE 独立进程冒烟：**PASS，17.766 秒**，报告 `build/remove-surrender-buttons-smoke/exe.json`。实际启动、最小化、最后十秒提示、15 秒归零进入休息、点击「解除限制」打开投降书、点击底部居中的取消按钮关闭投降书并继续休息。未开启摄像头，未实测 EXE 的拍照第二步。
- 冒烟结束后由测试工具终止其自身启动的 EXE 进程，清除测试遮挡；**不将此记录为软件正常退出成功或 exit 0**。正常取消、相机清理和托盘紧急退出由上述自动化回归覆盖。
- 新 EXE、Windows ZIP 已重新构建；目录与 ZIP 内容扫描均 PASS。当前产物信息见下方「构建产物与审查」。
- 本次没有重跑完整五分钟测试或进行物理相机、多屏验收；下列长测及早期回归均为此前记录，不能视作本次重新执行。

本次执行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q --junitxml=build/remove-surrender-buttons-all.xml --basetemp=build/qa-remove-surrender-buttons-all
.\.venv\Scripts\python.exe -m compileall -q app tests tools main.py
.\.venv\Scripts\python.exe -m pip check
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1 -SkipTests
.\.venv\Scripts\python.exe tools/exe_smoke.py dist/v1.1-local/NailongQuanxue/NailongQuanxue.exe --report build/remove-surrender-buttons-smoke/exe.json
```

## 环境与此前阶段结果

Windows x64，NT 10.0 build 26200；Python 3.11.5；PySide6 Essentials/Addons 6.8.3；PyInstaller 6.16.0；pytest 8.4.2。一块显示器，Qt 逻辑几何 1707×1067、150% 缩放。受限环境枚举 0 个摄像头，原生环境枚举 2 个；枚举不代表实拍通过。

| 阶段 | 实际执行 | 结果 |
|---|---|---|
| 1 V1 保全 | 原 V1 全测试、源码 ZIP 快照、原 EXE 保留 | 68 passed |
| 2 双时钟/状态机 | 原计时核心与新监督测试 | 52 passed |
| 2 配置/配额/档案 | 包含原子配置保存、100 MB 与迁移 | 73 passed；最初沙箱拒绝原子替换，允许真实文件操作后重跑通过 |
| 3–5 UI/托盘/投降 | Qt 控件与合成相机，非真实照片 | 25 passed |
| 5 核心回归 | 计时、存储、资源与审查 | 90 passed |
| 6 素材/回退/存储 | 指纹、冻结路径、缺视频、持续黑画面、存储切换 | 27 passed |
| 紧急退出复现 | 隐藏确认窗口后再次请求 | 修复前 1 failed，确认复现 |
| 紧急退出修复回归 | 恢复隐藏框、重复取消/确认、关闭行为 | 4 passed |
| 此前全套 | 含相机故障、数据库故障、窗口销毁重建、清理顺序、多轮循环与未列明媒体排除 | **136 passed，0 failed，0 skipped，6.18 秒** |
| 编译/依赖 | compileall、pip check | 通过；无依赖冲突 |

阶段数字存在重叠，不累加为额外测试数量。上表为此前基线，原报告 `build/v11-final-results.xml`；本次结果以 `build/remove-surrender-buttons-all.xml` 为准。此前全屏按钮删除的结果见 `build/remove-overlay-button-all.xml` 和 `build/remove-overlay-button-smoke/exe.json`。V1 计时核心原测试保留；旧 GUI 的直接解除/关闭确认与 V1.1 冻结需求冲突，已更新 GUI 用例，原文在 V1 源码快照中。

## 紧急退出问题及用户验收

用户报告：第一次紧急退出未成功，再点击没有交互界面。复现测试确认旧实现对隐藏确认框仅 `raise_()`，不会重新显示；确认框还依附于可能隐藏或最小化的主窗口。

修复：确认框改成独立置顶窗口，重复请求执行 showNormal/居中/激活，销毁后清除引用并允许重建；确认时先停止刷新并撤下所有遮挡，再停止媒体/相机和保存档案。投降窗口也独立于最小化主窗。数据库写入失败不能保留遮挡。

- 自动复现：修复前失败，修复后通过。
- Windows 原生冒烟：主窗最小化、视频全屏、隐藏确认框→重复点击恢复、取消→再次确认，PASS，26.203 秒。
- **用户实际确认：已反馈“ok了这次可以退出了”。** 这是紧急退出路径的手测确认，不扩大为全部 V1.1 验收通过。
- 新 EXE 独立进程：15 秒归零、紧急退出取消/确认、所有遮挡清理、返回待机、关闭退出，PASS，16.844 秒，exit 0。

## Windows 视频与时长验证

原生短流程已实际解码 720×1280 视频，11 秒内约 309 帧，观察至少 2 次循环；主屏按钮可触发流程。播放器未连接 QAudioOutput，音轨禁用。实际扬声器听测仍需用户确认，不能仅凭设置声称完成听测。

此前由工具发起的可见五分钟测试记录如下；它们与用户本轮声明的总体手动验收分别列示：

1. 第一轮记录约 1430 秒；用户本轮澄清为本人手动退出。撤销此前“程序自动结束延迟”的推断。原始事件日志与手动操作归因分开保留，不据此认定自动结束成功或失败。
2. 第二轮结束观察为 299.485 秒，测试观察起点晚于核心休息起点（包含播放器初始化），严格下界判断失败；已修正工具起点测量，原失败记录保留。
3. 第三轮在约 134 秒时被用户主动结束。核对该进程档案实际类型为 BREAK_SURRENDER，不能将其写成自动休息成功或紧急退出事件；用户另有“这次可以退出”的反馈，紧急退出分支由独立自动冒烟验证。工具已增加主动结束的中断分类。

为避免继续占住用户桌面，另行执行**无可见遮挡**的 Windows 实际 300 秒计时/视频循环长测。它使用真实时钟、不缩短休息，不替代全屏完整五分钟人工验收；最终结果见本报告末尾及 `build/v11-real-duration-final.json`。

## 按 QA 清单分类

| QA 范围 | 此前已验证 | 未单项确认 / 未覆盖的具体环境 |
|---|---|---|
| A 启动/UI | 中文单页、无侧栏、30:00、三个设置栏目、偏好重启、原生 150% 界面检查 | 100%/125%、小屏实际设备、全部键盘操作；无 Python 干净系统 |
| B 输入/提示 | 分秒边界、0 拒绝、15/90/330 秒、120:00、提醒去重、最后十秒、延迟回调 | 06:00 整段普通提醒的 Windows 目测与位置确认 |
| C 视频/休息 | 素材指纹、真实解码循环、Contain/纯白、无音频输出对象、缺图/黑帧回退、单播放器与重复布局 | 完整五分钟可见全屏人工验收、实际听测、物理多屏、热插拔与主屏切换 |
| D 投降/相机 | 空白/错误宣言拦截、第二步才开启、合成帧预览/确认/取消、阶段令牌、相机错误/重试/紧急退出 | 物理相机真实拍照、重拍、权限拒绝/占用、125% 层级；没有伪称实拍通过 |
| E 配额/档案 | 90 MB 边界、新图字节计入 100 MB、超额不写、保存失败、唯一命名、分类、删除/迁移、不连带删照片 | 设置文件夹选择与照片查看的人工操作体验 |
| F 生命周期 | 手动/自动循环、模式锁定、暂停模拟、休息计入睡眠模拟、紧急退出、活动关闭继续计时、异常启动待机 | 真实锁屏/睡眠/唤醒、物理托盘双击、Ctrl+Alt+Del、安全桌面、关机/重启 |
| G 发行 | MIT/隐私/素材清单、固定素材内置、EXE 构建与本机运行、数据规则扫描；用户正式发布授权及 Windows 手动验收总体确认 | 干净 Windows 10/11、签名/杀毒兼容未单项验证；第三方素材权属不因代码 MIT 改变 |

模拟锁屏/休眠测试、会话通知注册成功并不等于进行了真实电源操作。没有修改用户的电源策略、显示缩放或系统安全设置。

## 验收候选产物与历史审查

- EXE：`dist/v1.1-local/NailongQuanxue/NailongQuanxue.exe`，1,968,779 字节。
- EXE SHA-256：`ff26b87f64b9cd24bdd590a54c7552e0bdae4c6b9a798264244da29568e9303c`。
- ZIP：`dist/v1.1-local/NailongQuanxue-v1.1.0-Windows-local.zip`，50,789,128 字节。
- ZIP SHA-256：`917bcee19efaa601f1770d35765faf1ae98af82a3bea31514cc17c64166a6d8f`。
- 本地目录扫描 736 条，ZIP 扫描 737 条（包含内嵌成员），均 PASS；EXE CArchive/PYZ 实际展开审查。
- EXE 包含 `default_break.mp4` 与 `fallback_overlay.jpg`，字节指纹与用户清单一致；不包含 UI 参考 PNG、旧 overlay.jpg、用户照片、数据库、配置或日志。
- 只允许已知固定素材的正确路径及 SHA；扫描报告明确 `publication_authorized=false`。这不是素材权属认定、杀毒认证或依赖漏洞全面审计。
- 正式源码逐行列于 `PUBLIC_FILES.txt`；内置视频、备用图及开发参考图单独列示来源与 SHA，第三方素材不重新许可为 MIT。新增发布包装脚本与 Windows 使用说明后以该清单实际行数为准。
- Git 只纳入精确清单；个人照片、数据库、日志、配置、虚拟环境和旧 V1 工作流不进入提交或 Release。

## 此前阶段执行命令与证据

```powershell
.\.venv\Scripts\python.exe -m pytest -q --junitxml=build/v11-final-results.xml --basetemp=build/qa-final-v11-c
.\.venv\Scripts\python.exe -m compileall -q app main.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe tools/v11_smoke.py --report build/v11-emergency-native.json
.\.venv\Scripts\python.exe tools/real_duration_check.py --report build/v11-real-duration-final.json
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1 -SkipTests
.\.venv\Scripts\python.exe tools/exe_smoke.py dist/v1.1-local/NailongQuanxue/NailongQuanxue.exe --report build/v11-exe-smoke-final.json
.\.venv\Scripts\python.exe tools/prepare_sources.py
```

`-SkipTests` 的构建步骤前后已实际跑全套测试；仅省略重复执行，不跳过产物扫描。最初 EXE 外部点击冒烟等待过短，早于 FFmpeg 初始化完成；增加等待后重跑通过，原失败 JSON 保留。

自动测试使用合成帧，不主动保存真实照片。用户在可见测试进程内的交互可能产生本地照片/档案；它们保留在 `build/full-break-data`，未查看照片内容、未清理或导出。该目录及其他运行数据不进源码候选/ZIP。手测说明见 MANUAL_TESTS。

## 此前基线补充（按钮移除前）

- **真实 300 秒计时/视频长测 PASS**（不显示遮挡）：Windows GetTickCount64 记录 300.094 秒，独立时钟同为 300.094 秒，解码 8990 帧、观察 59 次循环；未连接音频输出。该结果不替代完整可见全屏五分钟的用户验收。
- **最终 ZIP 解压 EXE 冒烟 PASS**，19.062 秒：不同工作目录启动、最小化、提示、遮挡、紧急退出取消/确认、正常退出 exit 0。
- 源码候选、目录/EXE/ZIP 审查通过。新增固定素材只列为本地候选；Git 忽略个人照片及运行数据，未提交或公开。
- **隔离源码包复测：135 passed，1 skipped，0 failed，6.46 秒**。唯一跳过项是刻意排除的旧 V1 overlay.jpg 完整性检查；V1.1 固定素材测试全部通过。已禁用 pytest 缓存，最终无缓存路径警告。
- 最后只刷新发行包 README；新 EXE 的 SHA-256 与已实际测试的 EXE 完全一致，未变更应用代码。新版 ZIP 再次扫描 PASS。
