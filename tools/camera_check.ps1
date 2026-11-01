# 摄像头自检（本地运行，不上传任何画面）
#
# 用法（在项目根目录打开 PowerShell，直接运行）：
#     powershell -ExecutionPolicy Bypass -File tools\camera_check.ps1
#     powershell -ExecutionPolicy Bypass -File tools\camera_check.ps1 -Seconds 12 -Keep
#     powershell -ExecutionPolicy Bypass -File tools\camera_check.ps1 -DevicesOnly
#     powershell -ExecutionPolicy Bypass -File tools\camera_check.ps1 -OpenSettings
#
# 它会先打印 Windows 摄像头权限与设备状态，再用项目自带的 Python 跑
# tools\camera_check.py，检查：枚举、预览、无声录像、取消清理、重新录制、释放。
# 检查过程中录到的画面只写在本机临时目录，脚本默认在结束时删除。

param(
    [double]$Seconds = 7,
    [switch]$Keep,
    [switch]$DevicesOnly,
    [switch]$Gui,
    [switch]$OpenSettings
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# 让 Python 的中文输出在控制台里正常显示
$env:PYTHONIOENCODING = 'utf-8'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

function Write-Head($text) {
    Write-Host ''
    Write-Host "== $text ==" -ForegroundColor Cyan
}

Write-Head 'Windows 摄像头设备'
$devices = Get-PnpDevice -Class Camera -ErrorAction SilentlyContinue
if ($devices) {
    $devices | Select-Object Status, FriendlyName, InstanceId | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
} else {
    Write-Host '没有查到 Camera 类设备。' -ForegroundColor Yellow
}

Write-Head 'Windows 摄像头隐私开关'
$base = 'SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam'
foreach ($hive in 'HKCU:', 'HKLM:') {
    try {
        $item = Get-ItemProperty -Path "$hive\$base" -ErrorAction Stop
        Write-Host ("{0}\{1} = {2}" -f $hive, $base, $item.Value)
    } catch {
        Write-Host ("{0}\{1} = <未设置>" -f $hive, $base) -ForegroundColor Yellow
    }
}
try {
    $np = Get-ItemProperty -Path "HKCU:\$base\NonPackaged" -ErrorAction Stop
    Write-Host ("允许桌面应用访问摄像头（NonPackaged） = {0}" -f $np.Value)
} catch {
    Write-Host '允许桌面应用访问摄像头（NonPackaged） = <未设置>' -ForegroundColor Yellow
}

Write-Head '已被 Windows 授权访问摄像头的程序'
$list = Get-ChildItem "HKCU:\$base\NonPackaged" -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty PSChildName
if ($list) {
    $list | ForEach-Object { Write-Host ('  ' + ($_ -replace '#', '\')) }
} else {
    Write-Host '  （还没有任何程序获得授权）' -ForegroundColor Yellow
}

Write-Head '帧服务器服务'
Get-Service FrameServer, FrameServerMonitor -ErrorAction SilentlyContinue |
    Select-Object Name, Status, StartType | Format-Table -AutoSize | Out-String -Width 120 | Write-Host

Write-Head '运行奶龙劝学自检'
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "找不到 $python，请先创建虚拟环境并安装 requirements。" -ForegroundColor Red
    exit 1
}

$arguments = @('tools\camera_check.py', '--seconds', $Seconds)
if ($Keep) { $arguments += '--keep' }
if ($DevicesOnly) { $arguments += '--devices-only' }
if ($Gui) { $arguments += '--gui' }

& $python @arguments
$code = $LASTEXITCODE

if ($code -ne 0) {
    Write-Head '如果提示“没有枚举到摄像头”'
    Write-Host '本机 Windows 会按“程序路径”单独授权摄像头。请依次尝试：' -ForegroundColor Yellow
    Write-Host '  1. 打开 设置 → 隐私和安全性 → 摄像头，确认“摄像头访问”“允许桌面应用访问你的摄像头”都为开；'
    Write-Host '  2. 在同一页的“最近活动”里找到 python.exe / NailongQuanxue.exe，把开关打开；'
    Write-Host '  3. 笔记本确认摄像头物理开关/热键（如 Fn+F10）和 MyASUS 的摄像头开关没有关闭；'
    Write-Host '  4. 关掉正在占用摄像头的其他程序（会议软件、相机应用等）后重跑本脚本。'
    Write-Host ''
    Write-Host '需要我直接打开设置页吗？运行： powershell -ExecutionPolicy Bypass -File tools\camera_check.ps1 -OpenSettings'
}

if ($OpenSettings) {
    Write-Host '正在打开 设置 → 隐私和安全性 → 摄像头 ...'
    Start-Process 'ms-settings:privacy-webcam'
}

Write-Host ''
Write-Host ("自检退出码：{0}（0 = 全部通过）" -f $code)
exit $code
