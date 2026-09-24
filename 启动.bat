@echo off
chcp 936 >nul
cd /d "%~dp0"
title 足球大小球分析系统

echo ========================================
echo   足球大小球赔率分析系统
echo   正在启动...
echo ========================================
echo.
echo 请勿关闭此窗口，关闭即停止服务
echo.

if not exist "app.py" (
    echo [错误] 找不到 app.py 文件
    echo 请确认此文件与 app.py 在同一目录
    pause
    exit /b 1
)

echo [1/2] 清理旧进程...
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8501" ^| find "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo [2/2] 启动 Streamlit...
echo.
echo 浏览器将自动打开，请稍候...
echo.

streamlit run app.py --server.port 8501 --browser.gatherUsageStats false

echo.
echo [提示] 服务已停止
pause
