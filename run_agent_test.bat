@echo off
chcp 65001 > nul
echo.
echo ============================================================
echo   CONTEXTO AI V2 -- Verificacion del Sistema
echo ============================================================
echo.

cd /d "%~dp0"

echo [1/3] Verificando contenedor PostGIS...
docker ps --filter "name=contexto_db" --format "  Estado: {{.Status}}" 2>nul || echo   AVISO: Docker no encontrado en PATH
echo.

echo [2/3] Ejecutando test del agente...
echo.
.venv\Scripts\python.exe -X utf8 test_agent.py

echo.
echo [3/3] Listo.
pause
