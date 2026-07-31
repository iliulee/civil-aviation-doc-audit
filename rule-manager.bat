@echo off
chcp 65001 >nul
title 规则管理面板 — 民航施工资料审核

echo ========================================
echo   民航施工资料审核 — 规则管理面板
echo ========================================
echo.
echo 正在启动规则管理 API 服务...
echo.

:: 启动 Python 服务（后台运行，不弹窗）
start /B "" python "%~dp0scripts\rule_admin.py" --port 8765

:: 等待服务启动
echo 等待服务就绪...
timeout /t 3 /nobreak >nul

:: 打开浏览器
echo 正在打开规则管理面板...
start "" http://127.0.0.1:8765/

echo.
echo ========================================
echo   规则管理面板已启动！
echo   浏览器地址：http://127.0.0.1:8765/
echo.
echo   关闭此窗口即可停止服务。
echo ========================================
echo.

pause