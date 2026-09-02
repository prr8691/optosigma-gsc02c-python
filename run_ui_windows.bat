@echo off
cd /d "%~dp0"
uv run gsc02c-ui
if errorlevel 1 pause
