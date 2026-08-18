@echo off
chcp 65001 >nul
title 规则管理工具

echo ========================================
echo   民航资料审核 - 规则管理工具
echo ========================================
echo.

:: 自动定位 Skill 安装目录
:: 优先从当前脚本位置向上查找
set "SKILL_DIR=%~dp0"
:: 如果在数据底座目录下，往上找到 skill 根目录
if exist "%SKILL_DIR%scripts\rule_admin.py" goto :found_skill
set "SKILL_DIR=%~dp0..\"
if exist "%SKILL_DIR%scripts\rule_admin.py" goto :found_skill
:: 尝试全局安装路径
set "SKILL_DIR=%USERPROFILE%\.trae-cn\skills\civil-aviation-doc-audit"
if exist "%SKILL_DIR%scripts\rule_admin.py" goto :found_skill

echo [错误] 未找到 Skill 安装目录！
echo 请确认 skill 已正确安装。
echo 尝试过的路径：
echo   %~dp0
echo   %~dp0..\
echo   %USERPROFILE%\.trae-cn\skills\civil-aviation-doc-audit
pause
exit /b 1

:found_skill
echo Skill 目录: %SKILL_DIR%
echo 规则目录:   %SKILL_DIR%rules\
echo.
echo 正在启动规则管理服务...
echo.

:: 启动 Python 服务
start /B "" python "%SKILL_DIR%scripts\rule_admin.py" --port 8765 --rules "%SKILL_DIR%rules"

:: 等待服务启动
echo 等待服务就绪...
timeout /t 3 /nobreak >nul

:: 打开浏览器
echo 正在打开规则管理面板...
start "" http://127.0.0.1:8765/

echo.
echo ========================================
echo   规则管理工具已启动！
echo   地址: http://127.0.0.1:8765/
echo.
echo   修改的规则保存在:
echo   %SKILL_DIR%rules\
echo.
echo   关闭此窗口可停止服务。
echo ========================================
echo.

pause
