<#
.SYNOPSIS
    民航建设施工资料合规审核大师 - 全局安装脚本
.DESCRIPTION
    将 Skill 安装到系统中，提供全局命令行入口和桌面快捷方式。
.NOTES
    版本: v1.4
    需要管理员权限
#>

#Requires -Version 5.1

param(
    [switch]$Uninstall,
    [switch]$Silent
)

$SKILL_NAME = "民航建设施工资料合规审核大师"
$SKILL_DIR = "d:\2026年7月22日 民航资料skill\.trae\skills\civil-aviation-doc-audit"
$WORKSPACE = "d:\2026年7月22日 民航资料skill"
$SCRIPTS_DIR = Join-Path $SKILL_DIR "scripts"
$AUDIT_OUT = Join-Path $WORKSPACE "audit_output"
$SKILL_VERSION = "v1.4"
$DESKTOP = [Environment]::GetFolderPath("Desktop")
$STARTMENU = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\民航施工资料审核"
$PROFILE_PATH = $PROFILE.CurrentUserAllHosts

function Write-Step   { param([string]$M, [string]$C = "Cyan"); if (-not $Silent) { Write-Host "-> $M" -ForegroundColor $C } }
function Write-Success { param([string]$M); if (-not $Silent) { Write-Host "  [OK] $M" -ForegroundColor Green } }
function Write-Warn    { param([string]$M); if (-not $Silent) { Write-Host "  [!] $M" -ForegroundColor Yellow } }
function Write-Error   { param([string]$M); if (-not $Silent) { Write-Host "  [X] $M" -ForegroundColor Red } }

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object Security.Principal.WindowsPrincipal($id)
    return $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if ($Uninstall) {
    Write-Host "--- 卸载 $SKILL_NAME ---" -ForegroundColor Yellow
    $cp = [Environment]::GetEnvironmentVariable("Path", "Machine")
    if ($cp -and $cp.Contains($SKILL_DIR)) {
        $np = ($cp -split ";") | Where-Object { $_ -ne $SKILL_DIR -and $_ -ne $SCRIPTS_DIR }
        $np = $np -join ";"
        [Environment]::SetEnvironmentVariable("Path", $np, "Machine")
        Write-Success "已从系统 PATH 移除"
    }
    if (Test-Path $PROFILE_PATH) {
        $pc = Get-Content $PROFILE_PATH -Raw
        if ($pc -match "audit function for civil-aviation") {
            $pc = $pc -replace "(?s)#region audit[\s\S]*?#endregion", ""
            Set-Content $PROFILE_PATH $pc.Trim() -Encoding UTF8
            Write-Success "已从 PowerShell Profile 移除"
        }
    }
    $sc = Join-Path $DESKTOP "民航施工资料审核.lnk"
    if (Test-Path $sc) { Remove-Item $sc -Force; Write-Success "已删除桌面快捷方式" }
    if (Test-Path $STARTMENU) { Remove-Item $STARTMENU -Recurse -Force -ErrorAction SilentlyContinue; Write-Success "已删除开始菜单" }
    $ab = "$env:SystemRoot\audit.bat"
    if (Test-Path $ab) { Remove-Item $ab -Force -ErrorAction SilentlyContinue; Write-Success "已删除 audit.bat" }
    Write-Host "[完成] 卸载成功，请重启 PowerShell" -ForegroundColor Green
    return
}

Write-Host "=== $SKILL_NAME $SKILL_VERSION 全局安装 ===" -ForegroundColor Cyan
Write-Host ""

# 1. 检查目录
Write-Step "检查 Skill 目录"
if (-not (Test-Path $SKILL_DIR)) { Write-Error "目录不存在: $SKILL_DIR"; exit 1 }
Write-Success "Skill 目录: $SKILL_DIR"

# 2. 检查 Python
Write-Step "检查 Python 环境"
try { $pv = python --version 2>&1; Write-Success "Python: $($pv.Trim())" }
catch { Write-Error "Python 未安装"; exit 1 }

# 3. 检查依赖
Write-Step "检查 Python 依赖"
$deps = @("PyMuPDF", "pytesseract", "pdf2image", "Pillow", "python-docx")
$missing = @()
foreach ($dep in $deps) {
    pip show $dep 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { $missing += $dep }
}
if ($missing.Count -gt 0) {
    Write-Warn "缺少依赖: $($missing -join ", ")"
    pip install $missing
    if ($LASTEXITCODE -ne 0) { Write-Error "安装失败"; exit 1 }
    Write-Success "依赖安装完成"
} else {
    foreach ($dep in $deps) {
        $v = pip show $dep 2>&1 | Select-String "^Version:" | ForEach-Object { $_ -replace "Version: ", "" }
        Write-Success "$dep $v"
    }
}

# 4. 检查 Tesseract
Write-Step "检查 Tesseract OCR"
try {
    $tv = tesseract --version 2>&1 | Select-Object -First 1
    Write-Success "Tesseract: $($tv.Trim())"
    $langs = tesseract --list-langs 2>&1
    if ($langs -match "chi_sim") { Write-Success "中文语言包: 已安装" }
    else { Write-Warn "中文语言包未安装" }
} catch {
    Write-Error "Tesseract 未安装，OCR 功能不可用"
    Write-Error "请下载: https://github.com/UB-Mannheim/tesseract/wiki"
}

# 5. 检查 Poppler
Write-Step "检查 Poppler"
$pp = Join-Path $SKILL_DIR "tools\poppler\poppler-26.02.0\Library\bin"
if (Test-Path $pp) { Write-Success "Poppler 已集成" }
else { Write-Warn "Poppler 未集成" }

# 6. 创建输出目录
Write-Step "创建输出目录"
foreach ($sub in @("reports","notices","checklists","logs","intermediate","audit_history")) {
    $d = Join-Path $AUDIT_OUT $sub
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}
Write-Success "输出目录: $AUDIT_OUT"

# 7. 添加系统 PATH
Write-Step "配置系统 PATH"
$isAdmin = Test-Admin
if ($isAdmin) {
    $cp = [Environment]::GetEnvironmentVariable("Path", "Machine")
    if ($cp -notlike "*$SKILL_DIR*") {
        [Environment]::SetEnvironmentVariable("Path", "$cp;$SKILL_DIR", "Machine")
        Write-Success "已添加到系统 PATH"
    } else { Write-Success "系统 PATH 中已存在" }
} else {
    $cp = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($cp -notlike "*$SKILL_DIR*") {
        [Environment]::SetEnvironmentVariable("Path", "$cp;$SKILL_DIR", "User")
        Write-Success "已添加到用户 PATH"
    } else { Write-Success "用户 PATH 中已存在" }
    Write-Warn "非管理员，建议以管理员身份重新运行"
}

# 8. 安装 audit.bat
Write-Step "安装 audit.bat 命令行入口"
$auditBatSrc = Join-Path $SKILL_DIR "audit.bat"
$auditBatDst = "$env:SystemRoot\audit.bat"
try {
    Copy-Item $auditBatSrc $auditBatDst -Force
    Write-Success "audit.bat 已安装到 $auditBatDst"
} catch {
    Write-Warn "无法写入系统目录，复制到桌面"
    Copy-Item $auditBatSrc "$DESKTOP\audit.bat" -Force
    Write-Success "audit.bat 已复制到桌面"
}

# 9. 更新 PowerShell Profile
Write-Step "更新 PowerShell Profile"
$profileDir = Split-Path $PROFILE_PATH -Parent
if (-not (Test-Path $profileDir)) { New-Item -ItemType Directory -Path $profileDir -Force | Out-Null }

# Define the profile function as a here-string
$profileFunc = @'
#region audit function for civil-aviation-doc-audit Skill (v1.4)
function audit {
    param([string]$Command, [string]$FilePath)
    $d = "d:\2026年7月22日 民航资料skill\.trae\skills\civil-aviation-doc-audit"
    $s = "$d\scripts"
    if (-not $Command) {
        Write-Host "=== 民航建设施工资料合规审核大师 v1.4 ===" -ForegroundColor Cyan
        Write-Host "audit <命令> <文件路径>" -ForegroundColor Yellow
        Write-Host "  info   - 查看资料信息"
        Write-Host "  extract- 提取文字"
        Write-Host "  ocr    - 扫描件OCR"
        Write-Host "  quality- 数据质量检测"
        Write-Host "  batch  - 批量审核"
        Write-Host "  install- 运行安装脚本"
        Write-Host "  uninstall- 卸载"
        Write-Host "  clean  - 清理临时文件"
        return
    }
    switch ($Command.ToLower()) {
        "info"     { if (-not $FilePath) { Write-Host "请指定文件路径" -ForegroundColor Red; return }; python "$s\run_audit.py" info $FilePath }
        "extract"  { if (-not $FilePath) { Write-Host "请指定文件路径" -ForegroundColor Red; return }; python "$s\extract_pdf.py" $FilePath }
        "ocr"      { if (-not $FilePath) { Write-Host "请指定文件路径" -ForegroundColor Red; return }; python "$s\ocr_image.py" $FilePath }
        "quality"  { if (-not $FilePath) { Write-Host "请指定 JSON 文件路径" -ForegroundColor Red; return }; python "$s\data_quality_check.py" $FilePath }
        "batch"    { if (-not $FilePath) { Write-Host "请指定目录路径" -ForegroundColor Red; return }; python "$s\run_audit.py" batch $FilePath }
        "install"  { powershell -ExecutionPolicy Bypass -File "$d\install.ps1" }
        "uninstall"{ powershell -ExecutionPolicy Bypass -File "$d\install.ps1" -Uninstall }
        "clean"    { Remove-Item "d:\2026年7月22日 民航资料skill\audit_output\intermediate\*.json" -ErrorAction SilentlyContinue; Write-Host "已清理" -ForegroundColor Green }
        default    { Write-Host "未知命令: $Command" -ForegroundColor Red }
    }
}
#endregion
'@

if (Test-Path $PROFILE_PATH) {
    $ec = Get-Content $PROFILE_PATH -Raw
    if ($ec -match "audit function for civil-aviation") {
        $ec = $ec -replace "(?s)#region audit[\s\S]*?#endregion", ""
        $ec = $ec.Trim()
    }
    $ec + $profileFunc | Set-Content $PROFILE_PATH -Encoding UTF8
} else {
    $profileFunc | Set-Content $PROFILE_PATH -Encoding UTF8
}
Write-Success "PowerShell Profile 已更新: $PROFILE_PATH"

# 10. 桌面快捷方式
Write-Step "配置桌面快捷方式"
$scPath = Join-Path $DESKTOP "民航施工资料审核.lnk"
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($scPath)
$sc.TargetPath = "C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe"
$sc.Arguments = "-NoExit -Command Write-Host === 民航建设施工资料合规审核大师 v1.4 === -ForegroundColor Cyan; Write-Host 输入 audit 查看帮助 -ForegroundColor Yellow; cd $WORKSPACE"
$sc.WorkingDirectory = $WORKSPACE
$sc.Description = "民航建设施工资料合规审核大师"
$sc.Save()
Write-Success "桌面快捷方式已更新"

# 11. 开始菜单
Write-Step "配置开始菜单"
if (-not (Test-Path $STARTMENU)) { New-Item -ItemType Directory -Path $STARTMENU -Force | Out-Null }
$sm = $ws.CreateShortcut((Join-Path $STARTMENU "民航施工资料审核.lnk"))
$sm.TargetPath = "C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe"
$sm.Arguments = "-NoExit -Command cd $WORKSPACE; Write-Host 欢迎使用民航施工资料审核大师 -ForegroundColor Cyan"
$sm.WorkingDirectory = $WORKSPACE
$sm.Save()
Write-Success "开始菜单快捷方式已创建"

# 12. 验证
Write-Step "运行安装验证"
try {
    python "$SCRIPTS_DIR\run_audit.py" info --help 2>&1 | Out-Null
    Write-Success "run_audit.py 正常运行"
} catch { Write-Warn "run_audit.py 验证失败" }
try {
    python -c "import fitz; print(OK)" 2>&1 | Out-Null
    Write-Success "PyMuPDF 导入正常"
} catch { Write-Warn "PyMuPDF 导入失败" }

Write-Host ""
Write-Host "=== 安装完成！===" -ForegroundColor Green
Write-Host ""
Write-Host "使用方法:" -ForegroundColor Yellow
Write-Host "  [PowerShell/CMD] audit info `"d:\资料\检验批.pdf`""
Write-Host "  [Win+R]         audit 回车"
Write-Host "  [桌面]          双击 民航施工资料审核.lnk"
Write-Host "  [立即生效]      在 PowerShell 中执行: . $PROFILE"
Write-Host ""
Write-Host "Skill 目录: $SKILL_DIR"
Write-Host "输出目录:  $AUDIT_OUT"
Write-Host "如需卸载:  audit uninstall"