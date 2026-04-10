@echo off
setlocal enabledelayedexpansion

:: 檢查管理員權限
net session >nul 2>&1
if %errorLevel% == 0 (
    goto :admin_start
) else (
    echo --------------------------------------------------
    echo [!] 偵測到權限不足，正在請求系統管理員權限...
    echo --------------------------------------------------
    powershell -Command "Start-Process cmd -ArgumentList '/c %~f0' -Verb RunAs"
    exit /b
)

:admin_start
echo --------------------------------------------------
echo [+] 已進入管理員模式，啟動 McpProxy...
echo --------------------------------------------------
python main.py

echo.
echo --------------------------------------------------
echo 程序已結束，請按任意鍵關閉視窗...
pause
