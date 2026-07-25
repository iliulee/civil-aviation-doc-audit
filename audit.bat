@echo off
chcp 65001 >nul
title 民航施工资料审核 Skill

echo ╔══════════════════════════════════════════════╗
echo ║     民航建设施工资料合规审核大师 v1           ║
echo ║     civil-aviation-doc-audit Skill           ║
echo ╚══════════════════════════════════════════════╝
echo.

set SKILL_DIR=d:\2026年7月22日 民航资料skill\.trae\skills\civil-aviation-doc-audit
set AUDIT_OUT=d:\2026年7月22日 民航资料skill\audit_output

if "%1"=="" goto help
if "%1"=="info" goto info
if "%1"=="extract" goto extract
if "%1"=="ocr" goto ocr
if "%1"=="quality" goto quality
if "%1"=="batch" goto batch
if "%1"=="clean" goto clean
if "%1"=="help" goto help

:help
echo 使用方法: audit ^<命令^> ^<文件路径^>
echo.
echo 命令列表:
echo   audit info ^<文件^>       查看资料基本信息
echo   audit extract ^<文件^>    提取文字（PDF/图片）
echo   audit ocr ^<图片文件^>    扫描件 OCR 识别
echo   audit quality ^<json^>    数据质量检测
echo   audit batch ^<目录^>      批量审核资料目录
echo   audit clean               清理临时文件
echo.
echo 示例:
echo   audit info "d:\资料\检验批.pdf"
echo   audit extract "d:\资料\施工日志.pdf"
echo   audit ocr "d:\资料\扫描件.png"
echo   audit quality "c:\temp\data.json"
echo   audit batch "d:\资料\4月20日"
echo.
goto end

:info
python "%SKILL_DIR%\scripts\run_audit.py" info "%~2"
goto end

:extract
python "%SKILL_DIR%\scripts\extract_pdf.py" "%~2"
goto end

:ocr
python "%SKILL_DIR%\scripts\ocr_image.py" "%~2"
goto end

:quality
python "%SKILL_DIR%\scripts\data_quality_check.py" "%~2"
goto end

:batch
python "%SKILL_DIR%\scripts\run_audit.py" batch "%~2"
goto end

:clean
if exist "%AUDIT_OUT%\intermediate\*.json" del "%AUDIT_OUT%\intermediate\*.json"
echo 临时文件已清理
goto end

:end
echo.