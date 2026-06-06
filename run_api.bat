@echo off
chcp 65001 > nul
echo.
echo ============================================================
echo   CONTEXTO AI V2 -- API Server
echo   http://localhost:8000/docs
echo ============================================================
echo.

cd /d "%~dp0"
.venv\Scripts\python.exe -X utf8 -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
