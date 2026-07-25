# 民航施工资料审核 Skill 快捷方式
# 安装方法：在 PowerShell 中执行以下命令，将本文件附加到 profile：
#   notepad $PROFILE
# 然后把下面函数粘贴进去保存

function audit {
    param(
        [Parameter(Position=0)]
        [string]$Command,
        [Parameter(Position=1)]
        [string]$FilePath
    )

    $SKILL_DIR = "d:\2026年7月22日 民航资料skill\.trae\skills\civil-aviation-doc-audit"
    $AUDIT_OUT = "d:\2026年7月22日 民航资料skill\audit_output"

    if (-not $Command) {
        Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
        Write-Host "║     民航建设施工资料合规审核大师 v1           ║" -ForegroundColor Cyan
        Write-Host "║     civil-aviation-doc-audit Skill           ║" -ForegroundColor Cyan
        Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "使用方法: audit <命令> <文件路径>" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "命令列表:" -ForegroundColor Green
        Write-Host "  audit info <文件>       查看资料基本信息"
        Write-Host "  audit extract <文件>    提取文字（PDF/图片）"
        Write-Host "  audit ocr <图片文件>    扫描件 OCR 识别"
        Write-Host "  audit quality <json>    数据质量检测"
        Write-Host "  audit batch <目录>      批量审核资料目录"
        Write-Host "  audit clean             清理临时文件"
        Write-Host ""
        Write-Host "示例:" -ForegroundColor Gray
        Write-Host '  audit info "d:\资料\检验批.pdf"'
        Write-Host '  audit extract "d:\资料\施工日志.pdf"'
        Write-Host '  audit ocr "d:\资料\扫描件.png"'
        Write-Host '  audit quality "c:\temp\data.json"'
        Write-Host '  audit batch "d:\资料\4月20日"'
        return
    }

    switch ($Command.ToLower()) {
        "info" {
            if (-not $FilePath) { Write-Host "请指定文件路径" -ForegroundColor Red; return }
            python "$SKILL_DIR\scripts\run_audit.py" info $FilePath
        }
        "extract" {
            if (-not $FilePath) { Write-Host "请指定文件路径" -ForegroundColor Red; return }
            python "$SKILL_DIR\scripts\extract_pdf.py" $FilePath
        }
        "ocr" {
            if (-not $FilePath) { Write-Host "请指定文件路径" -ForegroundColor Red; return }
            python "$SKILL_DIR\scripts\ocr_image.py" $FilePath
        }
        "quality" {
            if (-not $FilePath) { Write-Host "请指定 JSON 数据文件路径" -ForegroundColor Red; return }
            python "$SKILL_DIR\scripts\data_quality_check.py" $FilePath
        }
        "batch" {
            if (-not $FilePath) { Write-Host "请指定资料目录路径" -ForegroundColor Red; return }
            python "$SKILL_DIR\scripts\run_audit.py" batch $FilePath
        }
        "clean" {
            Remove-Item "$AUDIT_OUT\intermediate\*.json" -ErrorAction SilentlyContinue
            Write-Host "临时文件已清理" -ForegroundColor Green
        }
        default {
            Write-Host "未知命令: $Command" -ForegroundColor Red
            Write-Host "可用命令: info, extract, ocr, quality, batch, clean"
        }
    }
}