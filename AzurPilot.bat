@rem AzurPilot WebUI launcher (source checkout + uv .venv).
@rem Double-click, or pin the Start Menu shortcut. ALAS stays on 22267; this is 25548.
@echo off
setlocal EnableExtensions

set "_root=%~dp0"
set "_root=%_root:~0,-1%"
cd /d "%_root%"

set "_py=%_root%\.venv\Scripts\python.exe"
set "_url=http://127.0.0.1:25548"

title AzurPilot WebUI
color 1F

if not exist "%_py%" (
    echo [ERROR] .venv not found:
    echo   %_py%
    echo Run:  uv sync
    echo from: %_root%
    pause
    exit /b 1
)

rem Second click: if WebUI is already up, just open the browser.
powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient('127.0.0.1', 25548); $c.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo AzurPilot already listening on 25548.
    start "" "%_url%"
    exit /b 0
)

echo Starting AzurPilot WebUI
echo   %_url%
echo Keep ALAS on 22267 for accounts 1-5. Use 6_margaret here only.
echo Leave this window open. Close it to stop AzurPilot.
echo.
start "" "%_url%"
"%_py%" "%_root%\gui.py" --host 127.0.0.1 --port 25548
set "_rc=%errorlevel%"
if not "%_rc%"=="0" (
    echo.
    echo gui.py exited with code %_rc%.
    pause
)
exit /b %_rc%
