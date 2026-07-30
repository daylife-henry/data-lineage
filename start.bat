@echo off
title DB Lineage
cd /d "%~dp0"

REM ── 使用内置 Python（无需安装，免联网）─────────────────
set PYTHON=%~dp0python\python.exe

if not exist "%PYTHON%" (
    echo [ERROR] 内置 Python 未找到：%PYTHON%
    echo 请确认 python\ 目录完整。
    pause
    exit /b 1
)

echo [INFO] 使用内置 Python：%PYTHON%

REM ── 删除旧的 lineage.db（如果存在）────────────────────
if exist lineage.db (
    echo Deleting old lineage.db...
    del /f /q lineage.db
)

REM ── 执行扫描 ───────────────────────────────────────────
echo.
echo ===================================================
echo   Scanning SQL repositories...
echo ===================================================
"%PYTHON%" scan.py
if errorlevel 1 (
    echo.
    echo ERROR: scan.py failed, check messages above.
    pause
    exit /b 1
)

REM ── 启动 Web 服务器 ───────────────────────────────────
echo.
echo Starting web server...
start /min cmd /c ""%PYTHON%" -m uvicorn api.main:app --reload --port 8765 --host 127.0.0.1"

echo Waiting for server...
ping -n 4 127.0.0.1 >nul 2>&1

echo Opening browser...
start http://localhost:8765

echo.
echo ===================================================
echo   Server running: http://localhost:8765
echo   Press any key to close this window
echo ===================================================
pause >nul
