@echo off
rem One-time setup: installs the Playwright library that lets the script drive Chrome.
rem Uses your installed Google Chrome, so no extra browser is downloaded.
cd /d "%~dp0"
set "PY=python"
where py >nul 2>nul
if not errorlevel 1 set "PY=py"
%PY% -m pip install --upgrade playwright
if errorlevel 1 (
  echo.
  echo Setup failed. Is Python installed with "Add Python to PATH" ticked?
) else (
  echo.
  echo Setup complete. Now edit "Run Cardiology.bat" and paste your project address.
)
pause
