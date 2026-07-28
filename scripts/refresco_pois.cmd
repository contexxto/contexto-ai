@echo off
REM ============================================================================
REM  Refresco semanal de pois_propios (Contexto) — capa propia de POIs.
REM
REM  Corre foso_pois_spike.py contra Overture + OSM y deja log fechado en logs\.
REM
REM  POR QUE REINTENTA: Overpass (OSM) es inestable — el 2026-07-27 devolvio 504
REM  en sus dos endpoints 2 de 3 veces seguidas. Un fallo NO corrompe nada (el
REM  script deja los POIs de OSM intactos y sale con codigo 2), pero deja la
REM  corrida a medias. Tres intentos espaciados 15 min cubren esa ventana.
REM
REM  CODIGOS DE SALIDA del script:
REM    0 = las dos fuentes respondieron  -> listo
REM    2 = una fuente caida (reintentable, datos viejos intactos)
REM    1 = error duro -> no se reintenta, hay que mirar el log
REM
REM  Uso manual:  scripts\refresco_pois.cmd [ciudad]     (por defecto: quito)
REM ============================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0.."

set "CIUDAD=%~1"
if "%CIUDAD%"=="" set "CIUDAD=quito"

set "LOGDIR=%~dp0..\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

REM La fecha via PowerShell: %date% depende del formato regional de Windows
REM (y en es-ES trae el dia de la semana delante, lo que desplaza los tokens).
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "HOY=%%d"
set "LOG=%LOGDIR%\refresco_pois_%CIUDAD%_%HOY%.log"

set "PY=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

set PYTHONUTF8=1
set "RC=99"

for %%i in (1 2 3) do (
    if not "!RC!"=="0" (
        echo.>> "%LOG%"
        echo [%%~ni] ---- intento %%i de 3 · ciudad: %CIUDAD% ---->> "%LOG%"
        powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'">> "%LOG%"
        "%PY%" "%~dp0foso_pois_spike.py" %CIUDAD% --sin-validacion>> "%LOG%" 2>&1
        set "RC=!ERRORLEVEL!"
        echo    intento %%i termino con codigo !RC!>> "%LOG%"

        if "!RC!"=="0" goto :fin
        REM Codigo 1 = error duro: reintentar no ayuda.
        if "!RC!"=="1" (
            echo    ERROR DURO — no se reintenta. Revisar este log.>> "%LOG%"
            goto :fin
        )
        if not "%%i"=="3" (
            echo    fuente caida — esperando 15 min antes de reintentar...>> "%LOG%"
            REM timeout /t falla sin consola interactiva (tarea programada); ping si funciona.
            ping -n 901 127.0.0.1 >nul 2>&1
        )
    )
)

:fin
echo.>> "%LOG%"
echo ==== FIN · codigo final: !RC! ====>> "%LOG%"
set "FINAL=!RC!"
endlocal & exit /b %FINAL%
