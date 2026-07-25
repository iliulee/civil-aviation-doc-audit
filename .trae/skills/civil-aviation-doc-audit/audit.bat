@echo off
chcp 65001 >nul
REM ============================================================
REM 民航建设施工资料合规审核大师 — 命令行入口
REM 放置于 PATH 目录中，即可在 CMD / PowerShell / Run 中调用
REM 使用方式: audit <命令> <文件路径>
REM ============================================================

set "SKILL_DIR=d:\2026年7月22日 民航资料skill\.trae\skills\civil-aviation-doc-audit"
set "SCRIPTS_DIR=%SKILL_DIR%\scripts"

if "%1"=="" goto :help
if /I "%1"=="help" goto :help
if /I "%1"=="info" goto :info
if /I "%1"=="extract" goto :extract
if /I "%1"=="ocr" goto :ocr
if /I "%1"=="quality" goto :quality
if /I "%1"=="batch" goto :batch
if /I "%1"=="clean" goto :clean
if /I "%1"=="install" goto :install
if /I "%1"=="uninstall" goto :uninstall
if /I "%1"=="version" goto :version
echo 未知命令: %1
goto :help

:help
echo =============================================
echo  民航建设施工资料合规审核大师 v1.4
echo  civil-aviation-doc-audit Skill
echo =============================================
echo.
echo 使用方法: audit ^<命令^> ^<文件路径^>
echo.
echo   audit info ^<文件^>       查看资料基本信息
echo   audit extract ^<文件^>    提取文字
echo   audit ocr ^<图片^>        扫描件OCR识别
echo   audit quality ^<json^>    数据质量检测
echo   audit batch ^<目录^>      批量审核
echo   audit clean              清理临时文件
echo   audit install            运行全局安装
echo   audit uninstall          卸载
echo   audit version            查看版本
echo.
echo 示例:
echo   audit info "d:\资料\检验批.pdf"
echo   audit batch "d:\资料\4月20日"
goto :end

:info
python "%SCRIPTS_DIR%\run_audit.py" info %2 %3 %4 %5
goto :end

:extract
python "%SCRIPTS_DIR%\extract_pdf.py" %2 %3 %4 %5
goto :end

:ocr
python "%SCRIPTS_DIR%\ocr_image.py" %2 %3 %4 %5
goto :end

:quality
python "%SCRIPTS_DIR%\data_quality_check.py" %2 %3 %4 %5
goto :end

:batch
python "%SCRIPTS_DIR%\run_audit.py" batch %2 %3 %4 %5
goto :end

:clean
if exist "d:\2026年7月22日 民航资料skill\audit_output\intermediate\*.json" del "d:\2026年7月22日 民航资料skill\audit_output\intermediate\*.json"
echo 临时文件已清理
goto :end

:install
powershell.exe -ExecutionPolicy Bypass -File "%SKILL_DIR%\install.ps1"
goto :end

:uninstall
powershell.exe -ExecutionPolicy Bypass -File "%SKILL_DIR%\install.ps1" -Uninstall
goto :end

:version
type "%SKILL_DIR%\README.md" | findstr "v1."
goto :end

:end