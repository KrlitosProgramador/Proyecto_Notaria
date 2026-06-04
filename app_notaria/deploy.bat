@echo off
REM Script de Despliegue para Producción (Windows CMD)
REM ====================================================
REM Uso: deploy.bat [start|stop|restart]

setlocal enabledelayedexpansion

set "PROJECT_ROOT=%~dp0"
set "VENV_PATH=%PROJECT_ROOT%.venv"
set "ACTIVATE_SCRIPT=%VENV_PATH%\Scripts\activate.bat"
set "ENV_FILE=%PROJECT_ROOT%production.env"

echo.
echo ========================================
echo App Notaria - Production Deployment
echo ========================================
echo.

REM Verificar si existe el entorno virtual
if not exist "%ACTIVATE_SCRIPT%" (
    echo [ERROR] Entorno virtual no encontrado en: %VENV_PATH%
    echo Por favor ejecuta primero: python -m venv .venv
    exit /b 1
)

REM Activar entorno virtual
echo [1/4] Activando entorno virtual...
call "%ACTIVATE_SCRIPT%"
if %errorlevel% neq 0 (
    echo [ERROR] No se pudo activar el entorno virtual
    exit /b 1
)
echo [OK] Entorno virtual activado
echo.

REM Instalar dependencias
echo [2/4] Instalando dependencias...
if exist "%PROJECT_ROOT%requirements.txt" (
    pip install -q -r "%PROJECT_ROOT%requirements.txt"
    if %errorlevel% neq 0 (
        echo [ERROR] Error al instalar dependencias
        exit /b 1
    )
    echo [OK] Dependencias instaladas
) else (
    echo [WARNING] requirements.txt no encontrado
)
echo.

REM Cargar archivo de entorno
echo [3/4] Cargando configuración...
if exist "%ENV_FILE%" (
    for /f "usebackq delims==" %%A in ("%ENV_FILE%") do (
        if not "%%A"=="" if not "%%A:~0,1%"=="#" (
            for /f "tokens=1,2 delims==" %%B in ("%%A") do (
                set "%%B=%%C"
            )
        )
    )
    echo [OK] Configuración cargada desde: %ENV_FILE%
) else (
    echo [WARNING] %ENV_FILE% no encontrado
)
echo.

REM Iniciar aplicación
echo [4/4] Iniciando aplicación...
echo.
echo ========================================
echo Servidor iniciando en:
echo   URL: http://0.0.0.0:8000
echo   Docs: http://localhost:8000/docs
echo ========================================
echo.

python -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4 --log-level info

endlocal
