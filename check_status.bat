@echo off
cd /d "%~dp0"
if "%1"=="quick" (
    python status.py quick
) else (
    python status.py
)
