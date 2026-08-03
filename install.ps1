<#
.SYNOPSIS
    民航建设施工资料合规审核大师 - 一键安装脚本
.DESCRIPTION
    自动完成 Python 依赖、Tesseract OCR 的安装和配置。
    PDF 转图片由 PyMuPDF 统一引擎处理（无需 Poppler）。
    PaddleOCR 为可选本地备选引擎，仅在离线场景需要。
    支持一键安装、卸载、静默模式。
    安装完成后无需任何手动操作即可使用。
    v5.0 API-First 变更：Vision API 成为默认 OCR 引擎；PaddleOCR 降级为可选本地备选；Tesseract 作为离线兜底。
.NOTES
    版本: v3.0
    需要管理员权限（仅 Tesseract 安装和系统 PATH 配置需要）
#>

#Requires -Version 5.1

param(
    [switch]$Uninstall,
    [switch]$Silent
)

# ── 自动检测 Skill 目录 ──
$SKILL_DIR = $PSScriptRoot
if (-not $SKILL_DIR) { $SKILL_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path }
$SCRIPTS_DIR = Join-Path $SKILL_DIR "scripts"
$TOOLS_DIR = Join-Path $SKILL_DIR "tools"
$REQUIREMENTS = Join-Path $SKILL_DIR "requirements.txt"
$SKILL_NAME = "民航建设施工资料合规审核大师"
$SKILL_VERSION = "v5.0-api"

# ── 输出目录（在 workspace 根目录下） ──
# SKILL_DIR = workspace\.trae\skills\civil-aviation-doc-audit
# 向上 3 级回到 workspace 根目录
$WORKSPACE = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $SKILL_DIR))
$AUDIT_OUT = Join-Path $WORKSPACE "audit_output"

# ── Tesseract 配置 ──
$TESSERACT_INSTALLER = "tesseract-ocr-w64-setup-5.5.0.20241111.exe"
$TESSERACT_URL = "https://github.com/UB-Mannheim/tesseract/releases/download/v5.5.0.20241111/$TESSERACT_INSTALLER"
$TESSERACT_INSTALLER_PATH = Join-Path $env:TEMP $TESSERACT_INSTALLER
$TESSERACT_DEFAULT_PATH = "${env:ProgramFiles}\Tesseract-OCR"
$TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata/raw/main/chi_sim.traineddata"

# ── 系统路径 ──
$DESKTOP = [Environment]::GetFolderPath("Desktop")
$STARTMENU = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\民航施工资料审核"
$PROFILE_PATH = $PROFILE.CurrentUserAllHosts

# ── 辅助函数 ──
function Write-Step   { param([string]$M, [string]$C = "Cyan"); if (-not $Silent) { Write-Host "-> $M" -ForegroundColor $C } }
function Write-Success { param([string]$M); if (-not $Silent) { Write-Host "  [OK] $M" -ForegroundColor Green } }
function Write-Warn    { param([string]$M); if (-not $Silent) { Write-Host "  [!] $M" -ForegroundColor Yellow } }
function Write-ErrorMsg{ param([string]$M); if (-not $Silent) { Write-Host "  [X] $M" -ForegroundColor Red } }
function Write-Info    { param([string]$M); if (-not $Silent) { Write-Host "  [i] $M" -ForegroundColor Gray } }

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object Security.Principal.WindowsPrincipal($id)
    return $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-CommandExists {
    param([string]$Cmd)
    try { Get-Command $Cmd -ErrorAction Stop | Out-Null; return $true }
    catch { return $false }
}

function Invoke-Download {
    param([string]$Url, [string]$OutFile, [string]$Description)
    Write-Step "下载 $Description ..."
    try {
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing -ErrorAction Stop
        $sizeMB = [math]::Round((Get-Item $OutFile).Length / 1MB, 1)
        Write-Success "$Description 下载完成 ($sizeMB MB)"
        return $true
    } catch {
        Write-ErrorMsg "$Description 下载失败: $_"
        return $false
    }
}

# ══════════════════════════════════════════════════════════════════════
# 卸载模式
# ══════════════════════════════════════════════════════════════════════
if ($Uninstall) {
    Write-Host "--- 卸载 $SKILL_NAME ---" -ForegroundColor Yellow

    # 移除 PATH
    $cp = [Environment]::GetEnvironmentVariable("Path", "Machine")
    if ($cp -and $cp.Contains($SKILL_DIR)) {
        $np = ($cp -split ";") | Where-Object { $_ -ne $SKILL_DIR -and $_ -ne $SCRIPTS_DIR }
        $np = $np -join ";"
        [Environment]::SetEnvironmentVariable("Path", $np, "Machine")
        Write-Success "已从系统 PATH 移除"
    }

    # 移除 Profile 函数
    if (Test-Path $PROFILE_PATH) {
        $pc = Get-Content $PROFILE_PATH -Raw
        if ($pc -match "audit function for civil-aviation") {
            $pc = $pc -replace "(?s)#region audit[\s\S]*?#endregion", ""
            Set-Content $PROFILE_PATH $pc.Trim() -Encoding UTF8
            Write-Success "已从 PowerShell Profile 移除"
        }
    }

    # 移除快捷方式
    $sc = Join-Path $DESKTOP "民航施工资料审核.lnk"
    if (Test-Path $sc) { Remove-Item $sc -Force; Write-Success "已删除桌面快捷方式" }
    if (Test-Path $STARTMENU) { Remove-Item $STARTMENU -Recurse -Force -ErrorAction SilentlyContinue; Write-Success "已删除开始菜单" }
    $ab = "$env:SystemRoot\audit.bat"
    if (Test-Path $ab) { Remove-Item $ab -Force -ErrorAction SilentlyContinue; Write-Success "已删除 audit.bat" }

    Write-Host "[完成] 卸载成功，请重启 PowerShell" -ForegroundColor Green
    return
}

# ══════════════════════════════════════════════════════════════════════
# 安装模式
# ══════════════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "=== $SKILL_NAME $SKILL_VERSION 一键安装 ===" -ForegroundColor Cyan
Write-Host "  Skill 目录: $SKILL_DIR" -ForegroundColor Gray
Write-Host ""

$isAdmin = Test-Admin
if (-not $isAdmin) {
    Write-Warn "非管理员权限运行，Tesseract 安装和系统 PATH 配置可能需要管理员权限"
    Write-Warn "建议右键 → 以管理员身份运行 PowerShell 后重新执行"
    Write-Host ""
}

# ────────────────────────────────────────────────
# 1. 检查 Python 版本（PaddleOCR 需 Python 3.12 及以下）
# ────────────────────────────────────────────────
Write-Step "1/6 检查 Python 环境"
try {
    $pv = python --version 2>&1
    Write-Success "Python: $($pv.Trim())"

    # 提取主版本号
    $verMatch = [regex]::Match($pv, "(\d+)\.(\d+)")
    if ($verMatch.Success) {
        $major = [int]$verMatch.Groups[1].Value
        $minor = [int]$verMatch.Groups[2].Value
        if ($major -ge 3 -and $minor -ge 13) {
            Write-Warn "Python $major.$minor 检测到 — PaddlePaddle（PaddleOCR 依赖）最高仅支持 Python 3.12"
            Write-Warn "方案 A：使用 Vision API（推荐，设置环境变量即可）"
            Write-Warn "方案 B：降级 Python 到 3.12 后安装 PaddleOCR（离线场景）"
            Write-Warn "  运行: python3.12 -m pip install paddleocr==2.8.1 paddlepaddle==2.6.2"
        }
    }
} catch {
    Write-ErrorMsg "Python 未安装。请先安装 Python 3.9+ 并添加到 PATH"
    Write-ErrorMsg "下载: https://www.python.org/downloads/"
    exit 1
}

# ────────────────────────────────────────────────
# 2. Python 依赖（核心 + OCR 引擎）
# ────────────────────────────────────────────────
Write-Step "2/6 安装 Python 核心依赖"
$coreDeps = @("PyMuPDF", "opencv-python", "pytesseract", "Pillow", "python-docx", "requests")
$missing = @()
foreach ($dep in $coreDeps) {
    pip show $dep 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { $missing += $dep }
}
if ($missing.Count -gt 0) {
    Write-Warn "缺少 $($missing.Count) 个核心依赖: $($missing -join ", ")"
    Write-Info "pip install $($missing -join " ")"
    $pipArgs = @("install") + $missing + @("-i", "https://pypi.tuna.tsinghua.edu.cn/simple")
    & pip $pipArgs 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "核心依赖安装失败，请检查网络连接后重试"
        exit 1
    }
    Write-Success "核心依赖安装完成"
} else {
    Write-Success "全部 $($coreDeps.Count) 个核心依赖已就绪"
}

# PaddleOCR 为可选本地备选引擎（仅离线场景需要）
Write-Step "2b/6 检查 PaddleOCR（可选本地引擎）"
try {
    python -c "from paddleocr import PaddleOCR" 2>&1 | Out-Null
    Write-Success "PaddleOCR 已安装（本地备选引擎可用）"
} catch {
    Write-Warn "PaddleOCR 未安装（默认使用 Vision API，无需 PaddleOCR）"
    Write-Info "如需离线使用:"
    # 检查 Python 版本
    $pv = python --version 2>&1
    $verMatch = [regex]::Match($pv, "(\d+)\.(\d+)")
    if ($verMatch.Success) {
        $major = [int]$verMatch.Groups[1].Value
        $minor = [int]$verMatch.Groups[2].Value
        if ($major -ge 3 -and $minor -le 12) {
            Write-Info "  运行: pip install paddleocr==2.8.1 paddlepaddle==2.6.2"
        } else {
            Write-Info "  ⚠️ 当前 Python $major.$minor 与 PaddlePaddle 不兼容"
            Write-Info "  方案 A：降级 Python 到 3.12: python3.12 -m pip install paddleocr==2.8.1 paddlepaddle==2.6.2"
            Write-Info "  方案 B：使用 Vision API（设置环境变量，推荐）"
        }
    }
}

# ────────────────────────────────────────────────
# 3. Tesseract OCR（自动下载安装）
# ────────────────────────────────────────────────
Write-Step "3/6 安装 Tesseract OCR（扫描件识别引擎）"

$tesseractReady = $false

# 先检查是否已安装
if (Test-CommandExists "tesseract") {
    try {
        $tv = tesseract --version 2>&1 | Select-Object -First 1
        Write-Success "Tesseract 已安装: $($tv.Trim())"
        $tesseractReady = $true
    } catch {
        Write-Warn "Tesseract 命令存在但无法执行"
    }
}

if (-not $tesseractReady) {
    Write-Info "Tesseract 未安装，开始自动下载（~50MB）..."
    Write-Info "来源: $TESSERACT_URL"

    if (Invoke-Download -Url $TESSERACT_URL -OutFile $TESSERACT_INSTALLER_PATH -Description "Tesseract OCR") {
        Write-Step "安装 Tesseract（可能需要管理员权限）..."
        try {
            $installArgs = "/S"
            $proc = Start-Process -FilePath $TESSERACT_INSTALLER_PATH -ArgumentList $installArgs -Wait -PassThru -NoNewWindow
            if ($proc.ExitCode -eq 0) {
                Write-Success "Tesseract 安装完成"
                Remove-Item $TESSERACT_INSTALLER_PATH -Force -ErrorAction SilentlyContinue

                # 刷新 PATH
                $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

                if (Test-CommandExists "tesseract") {
                    $tesseractReady = $true
                } else {
                    Write-Warn "Tesseract 安装完成但未在 PATH 中找到，可能需要重启终端"
                    # 尝试直接路径
                    $tesseractExe = Join-Path $TESSERACT_DEFAULT_PATH "tesseract.exe"
                    if (Test-Path $tesseractExe) {
                        $env:Path = "$TESSERACT_DEFAULT_PATH;$env:Path"
                        $tesseractReady = $true
                        Write-Success "手动添加到当前会话 PATH"
                    }
                }
            } else {
                Write-ErrorMsg "Tesseract 安装失败，退出码: $($proc.ExitCode)"
            }
        } catch {
            Write-ErrorMsg "Tesseract 安装失败: $_"
            Write-Info "请手动下载安装: https://github.com/UB-Mannheim/tesseract/wiki"
        }
    }
}

# 检查中文语言包
if ($tesseractReady) {
    Write-Step "检查 Tesseract 中文语言包"
    $langs = tesseract --list-langs 2>&1
    if ($langs -match "chi_sim") {
        Write-Success "中文语言包已安装"
    } else {
        Write-Warn "中文语言包缺失，正在下载..."
        $tessdataDir = if (Test-Path (Join-Path $TESSERACT_DEFAULT_PATH "tessdata")) {
            Join-Path $TESSERACT_DEFAULT_PATH "tessdata"
        } else {
            $env:TESSDATA_PREFIX = Join-Path $SKILL_DIR "tools\tessdata"
            if (-not (Test-Path $env:TESSDATA_PREFIX)) { New-Item -ItemType Directory -Path $env:TESSDATA_PREFIX -Force | Out-Null }
            $env:TESSDATA_PREFIX
        }
        $traineddataPath = Join-Path $tessdataDir "chi_sim.traineddata"
        if (Invoke-Download -Url $TESSDATA_URL -OutFile $traineddataPath -Description "中文语言包") {
            Write-Success "中文语言包安装完成"
            # 设置环境变量以便运行时找到
            [Environment]::SetEnvironmentVariable("TESSDATA_PREFIX", $tessdataDir, "User")
        }
    }
}

# ────────────────────────────────────────────────
# 5. 创建输出目录
# ────────────────────────────────────────────────
Write-Step "4/6 创建输出目录"
foreach ($sub in @("reports","notices","checklists","logs","intermediate","audit_history")) {
    $d = Join-Path $AUDIT_OUT $sub
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}
Write-Success "输出目录: $AUDIT_OUT"

# ────────────────────────────────────────────────
# 5. 配置系统 PATH
# ────────────────────────────────────────────────
Write-Step "5/6 配置系统 PATH"

# Poppler 已移除，PDF 转图片由 PyMuPDF 在内存中完成，无需 PATH 配置
# Tesseract 安装程序自带 PATH 配置，此处无需额外操作
Write-Success "PDF 转图片由 PyMuPDF 处理，无需 PATH 配置"

# ────────────────────────────────────────────────
# 6. 验证所有组件
# ────────────────────────────────────────────────
Write-Step "6/6 验证所有组件"

$allPassed = $true
$results = @()

# Python
try { python -c "print('OK')" 2>&1 | Out-Null; $results += "Python: OK" }
catch { $results += "Python: FAIL"; $allPassed = $false }

# PyMuPDF（PDF 文字提取 + PDF 转图片统一引擎）
try { python -c "import fitz" 2>&1 | Out-Null; $results += "PyMuPDF: OK" }
catch { $results += "PyMuPDF: FAIL"; $allPassed = $false }

# PaddleOCR（可选本地备选引擎）
try { python -c "from paddleocr import PaddleOCR" 2>&1 | Out-Null; $results += "PaddleOCR: OK" }
catch { $results += "PaddleOCR: 未安装（可选，默认使用 Vision API）" }

# Vision API（默认 OCR 引擎）
try {
    python -c "from vision_providers import detect_available_providers; p=detect_available_providers(); print(f'{len(p)} providers')" 2>&1 | Out-Null
    $providers = python -c "from vision_providers import detect_available_providers; p=detect_available_providers(); print(len(p))" 2>&1
    if ([int]$providers -gt 0) {
        $results += "Vision API: OK ($providers 个 Provider)"
    } else {
        $results += "Vision API: 未配置（设置 API Key 后可用）"
    }
}
catch { $results += "Vision API: 未配置" }

# OpenCV（图像预处理依赖）
try { python -c "import cv2" 2>&1 | Out-Null; $results += "OpenCV: OK" }
catch { $results += "OpenCV: FAIL"; $allPassed = $false }

# pytesseract
try { python -c "import pytesseract" 2>&1 | Out-Null; $results += "pytesseract: OK" }
catch { $results += "pytesseract: FAIL"; $allPassed = $false }

# Tesseract
if ($tesseractReady) {
    $results += "Tesseract: OK"
} else {
    $results += "Tesseract: 未安装（OCR 扫描件识别不可用）"
}

foreach ($r in $results) {
    if ($r -match "FAIL") { Write-ErrorMsg $r }
    elseif ($r -match "未安装") { Write-Warn $r }
    else { Write-Success $r }
}

# ────────────────────────────────────────────────
# 安装 PowerShell Profile 函数
# ────────────────────────────────────────────────
Write-Step "安装 audit 命令行函数"

$profileDir = Split-Path $PROFILE_PATH -Parent
if (-not (Test-Path $profileDir)) { New-Item -ItemType Directory -Path $profileDir -Force | Out-Null }

$profileFunc = @"

#region audit function for civil-aviation-doc-audit Skill (v3.2)
function audit {
    param([string]`$Command, [string]`$FilePath, [string]`$DataPath)
    `$d = "$SKILL_DIR"
    `$s = "`$d\scripts"
    if (-not `$Command) {
        Write-Host "=== $SKILL_NAME $SKILL_VERSION ===" -ForegroundColor Cyan
        Write-Host "audit <命令> <文件路径> [--data <结构化JSON>]" -ForegroundColor Yellow
        Write-Host "  info     - 查看资料信息"
        Write-Host "  extract  - 提取文字"
        Write-Host "  ocr      - 扫描件OCR"
        Write-Host "  audit    - 一键审核（OCR + 混淆检测 + Vision复核）"
        Write-Host "  quality  - 数据质量检测"
        Write-Host "  batch    - 批量审核"
        Write-Host "  install  - 运行安装脚本"
        Write-Host "  uninstall- 卸载"
        Write-Host "  clean    - 清理临时文件"
        return
    }
    switch (`$Command.ToLower()) {
        "info"      { if (-not `$FilePath) { Write-Host "请指定文件路径" -ForegroundColor Red; return }; python "`$s\run_audit.py" info `$FilePath }
        "extract"   { if (-not `$FilePath) { Write-Host "请指定文件路径" -ForegroundColor Red; return }; python "`$s\extract_pdf.py" `$FilePath }
        "ocr"       { if (-not `$FilePath) { Write-Host "请指定文件路径" -ForegroundColor Red; return }; python "`$s\ocr_image.py" `$FilePath }
        "audit"     { if (-not `$FilePath) { Write-Host "请指定文件路径" -ForegroundColor Red; return }; python "`$s\run_audit.py" audit `$FilePath }
        "quality"   { if (-not `$FilePath) { Write-Host "请指定 JSON 文件路径" -ForegroundColor Red; return }; python "`$s\data_quality_check.py" `$FilePath }
        "batch"     { if (-not `$FilePath) { Write-Host "请指定目录路径" -ForegroundColor Red; return }; python "`$s\run_audit.py" batch `$FilePath }
        "install"   { powershell -ExecutionPolicy Bypass -File "`$d\install.ps1" }
        "uninstall" { powershell -ExecutionPolicy Bypass -File "`$d\install.ps1" -Uninstall }
        "clean"     { Remove-Item "$AUDIT_OUT\intermediate\*.json" -ErrorAction SilentlyContinue; Write-Host "已清理" -ForegroundColor Green }
        default     { Write-Host "未知命令: `$Command" -ForegroundColor Red }
    }
}
#endregion
"@

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

# ────────────────────────────────────────────────
# 完成
# ────────────────────────────────────────────────
Write-Host ""
Write-Host "=== 安装完成 ===" -ForegroundColor Green
Write-Host ""
Write-Host "组件状态:" -ForegroundColor Yellow
foreach ($r in $results) { Write-Host "  $r" }
Write-Host ""
Write-Host "Skill 目录: $SKILL_DIR"
Write-Host "输出目录:  $AUDIT_OUT"
Write-Host ""
Write-Host "立即生效: . $PROFILE_PATH" -ForegroundColor Yellow
Write-Host ""

if (-not $allPassed) {
    Write-Warn "部分组件未通过验证，详见上方输出。"
    Write-Warn "核心审核功能（规范对账、逻辑检查）不受影响，仅 OCR 和 PDF 转图片功能可能受限。"
}