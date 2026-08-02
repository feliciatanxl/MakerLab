@echo off
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 get_spotify_refresh_token.py
) else (
  python get_spotify_refresh_token.py
)

echo.
pause
