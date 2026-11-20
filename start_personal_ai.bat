@echo off
title MY PERSONAL AI Platform
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" launch_app.py
) else (
    python launch_app.py
)
pause
