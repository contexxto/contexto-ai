@echo off
echo Iniciando Contexto AI...
start "API Backend :8000" cmd /k ".venv\Scripts\python.exe -X utf8 -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak > nul
start "Frontend :3000" cmd /k "cd frontend && npm run dev"
timeout /t 4 /nobreak > nul
start "" "http://localhost:3000"
