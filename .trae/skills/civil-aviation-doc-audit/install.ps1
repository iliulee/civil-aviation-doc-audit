<#
.SYNOPSIS
    民航建设施工资料合规审核大师 - 一键安装脚本
.DESCRIPTION
    自动完成 Python 依赖、Vision API 配置、RapidOCR 强烈推荐安装。
    PDF 转图片由 PyMuPDF 统一引擎处理（无需 Poppler）。
    RapidOCR（rapidocr>=3.9）为强烈推荐本地引擎，PP-OCRv6 small 模型 + OpenVINO 引擎，零 token 消耗。
    Tesseract 为离线兜底引擎，仅在 RapidOCR 不可用且无 API Key 时需安装。
    支持一键安装、卸载、静默模式。
    安装完成后无需任何手动操作即可使用。
    v9.2 OCR 策略：印刷体→RapidOCR 本地主力（零 token）；手写体→前置路由 VLM（识别率最高）；Tesseract 为离线兜底；AGENT 内置 Vision 模型为复核工具（非批量主力）。原生 PaddleOCR 已彻底移除，无回滚备份。
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
$SKILL_VERSION = "v9.2"

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
# 1. 检查 Python 版本（RapidOCR 跨 Python 版本无上限，无需降级）
#    若缺失，自动尝试用 Windows 包管理器 winget 安装 Python 3.14
# ────────────────────────────────────────────────
Write-Step "1/6 检查 Python 环境"

# 定位可用的 python 调用方式：优先 `py -3.14` launcher，其次裸 `python`
function Get-PyCommand {
    # py launcher 能精确指定版本，且不依赖 PATH 刷新
    try { $v = py -3.14 --version 2>&1; if ($LASTEXITCODE -eq 0) { return "py -3.14" } } catch {}
    try { $v = py --version 2>&1; if ($LASTEXITCODE -eq 0) { return "py" } } catch {}
    try { $v = python --version 2>&1; if ($LASTEXITCODE -eq 0) { return "python" } } catch {}
    return $null
}

$py = Get-PyCommand
if ($py) {
    $pv = Invoke-Expression "$py --version" 2>&1
    Write-Success "Python: $($pv.Trim())  (调用: $py)"
    $verMatch = [regex]::Match($pv, "(\d+)\.(\d+)")
    if ($verMatch.Success) {
        $major = [int]$verMatch.Groups[1].Value
        $minor = [int]$verMatch.Groups[2].Value
        if ($major -ge 3 -and $minor -ge 9) {
            Write-Info "Python $major.$minor 满足要求（RapidOCR/RapidTable 跨版本无上限）"
        } else {
            Write-Warn "Python $major.$minor 版本偏低，建议 Python 3.9+"
        }
    }
} else {
    Write-Warn "未检测到 Python。将尝试自动安装 Python 3.14（需要 winget，Windows 10/11 自带）"
    if ($Silent) {
        $autoInstall = $true
    } else {
        Write-Step "是否用 winget 自动安装 Python 3.14？(y/n，默认 n)"
        $ans = Read-Host
        $autoInstall = ($ans -eq 'y' -or $ans -eq 'Y')
    }
    if ($autoInstall) {
        try {
            Write-Step "winget 安装 Python 3.14 ..."
            winget install --id Python.Python.3.14 -e --accept-source-agreements --accept-package-agreements --disable-interactivity 2>&1 | Out-Null
            # winget 安装后刷新当前会话 PATH，便于同进程内调用
            $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
            $py = Get-PyCommand
            if ($py) {
                $pv = Invoke-Expression "$py --version" 2>&1
                Write-Success "Python 3.14 安装成功: $($pv.Trim())  (调用: $py)"
            } else {
                Write-ErrorMsg "Python 已安装但无法在当前会话调用，请重启终端后重试"
                exit 1
            }
        } catch {
            Write-ErrorMsg "winget 安装失败: $_"
            Write-ErrorMsg "请手动安装 Python 3.9+: https://www.python.org/downloads/"
            Write-ErrorMsg "安装时务必勾选 'Add python.exe to PATH'"
            exit 1
        }
    } else {
        Write-ErrorMsg "未安装 Python。请手动安装后重试: https://www.python.org/downloads/"
        Write-ErrorMsg "或重新运行本脚本并选择 y 自动安装"
        exit 1
    }
}

# ────────────────────────────────────────────────
# 2. Python 依赖（核心 + OCR 引擎）
# ────────────────────────────────────────────────
Write-Step "2/6 安装 Python 核心依赖"
$coreDeps = @("PyMuPDF", "opencv-python", "pytesseract", "Pillow", "python-docx", "openpyxl", "requests", "rapidocr", "onnxruntime", "openvino", "rapid_table", "scikit-image", "imagehash", "jsonschema")
$missing = @()
foreach ($dep in $coreDeps) {
    & $py -m pip show $dep 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { $missing += $dep }
}
if ($missing.Count -gt 0) {
    Write-Warn "缺少 $($missing.Count) 个核心依赖: $($missing -join ", ")"
    Write-Info "pip install $($missing -join " ")"
    $pipArgs = @("-m", "pip", "install") + $missing + @("-i", "https://pypi.tuna.tsinghua.edu.cn/simple")
    & $py $pipArgs 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "核心依赖安装失败，请检查网络连接后重试"
        exit 1
    }
    Write-Success "核心依赖安装完成"
} else {
    Write-Success "全部 $($coreDeps.Count) 个核心依赖已就绪"
}

# RapidOCR 为强烈推荐本地引擎（批量 OCR 主力，零 token 消耗）
Write-Step "2b/6 检查 RapidOCR（强烈推荐本地引擎）"
try {
    & $py -c "from rapidocr import RapidOCR" 2>&1 | Out-Null
    Write-Success "RapidOCR 已安装（本地批量 OCR 引擎可用，零 token 消耗）"
} catch {
    Write-Warn "⚠️ RapidOCR 未安装 — 强烈推荐安装！"
    Write-Warn "   不安装 RapidOCR 的后果："
    Write-Warn "   · 无 Vision API Key 时，多页扫描件将使用 AGENT Vision 逐页读图识别"
    Write-Warn "   · 50 页扫描件可能消耗数万 token，且 AGENT Vision 可能只抽样识别前几页"
    Write-Warn "   · 遗漏的页面中的异常数据将不会被审核发现"
    Write-Info "安装 RapidOCR:"
    Write-Info "  运行: pip install rapidocr"
    Write-Info "  （原生 PaddleOCR 已彻底移除，FORCE_USE_PADDLE 开关已删除，无回滚备份）"
}

# ────────────────────────────────────────────────
# 3. Tesseract OCR（可选兜底引擎，需用户确认）
# ────────────────────────────────────────────────
Write-Step "3/6 检查 Tesseract OCR（可选兜底引擎）"

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
    Write-Info "Tesseract 未安装（可选兜底引擎，仅当 Vision API 和 RapidOCR 都不可用时需要）"
    Write-Info "当前默认 OCR 引擎策略："
    Write-Info "  ① RapidOCR（本地批量主力，零 token，跨 Python 版本无上限）"
    Write-Info "  ② Vision API（手写体前置路由首选，设置环境变量即可）"
    Write-Info "  ③ Tesseract（离线兜底，需下载 ~50MB 安装包）"
    Write-Info "  ④ AGENT 内置 Vision 模型（复核工具，页数不限，零依赖）"
    
    if ($Silent) {
        Write-Info "静默模式：跳过 Tesseract 安装（可通过 Vision API 或 RapidOCR 替代）"
    } else {
        Write-Step "是否需要安装 Tesseract 作为离线兜底？(y/n，默认 n)"
        $userInput = Read-Host
        if ($userInput -eq 'y' -or $userInput -eq 'Y') {
            Write-Info "开始自动下载 Tesseract（~50MB）..."
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
        } else {
            Write-Info "跳过 Tesseract 安装（后续可通过 Vision API 或 RapidOCR 替代）"
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
# 4. 创建输出目录
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

# RapidOCR（强烈推荐本地引擎）
try { python -c "import rapidocr" 2>&1 | Out-Null; $results += "RapidOCR: OK（PP-OCRv6 small + OpenVINO，零 token 消耗）" }
catch { $results += "RapidOCR: ⚠️ 未安装（强烈推荐安装！无 API Key 时多页扫描件将消耗大量 token）" }

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

# Tesseract（可选兜底引擎）
if ($tesseractReady) {
    $results += "Tesseract: OK"
} else {
    $results += "Tesseract: 未安装（可选，Vision API / RapidOCR / AGENT Vision 均可替代）"
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
    Write-Warn "部分核心组件未通过验证，详见上方输出。"
    Write-Warn "核心审核功能（规范对账、逻辑检查）不受影响，仅 OCR 和 PDF 转图片功能可能受限。"
    Write-Info "提示：Vision API 无需额外安装，设置环境变量即可使用。"
    Write-Info "  详情: python scripts/vision_providers.py --list"
}