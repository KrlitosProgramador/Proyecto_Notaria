# Script de Despliegue para Producción
# ====================================
# Uso: powershell -ExecutionPolicy Bypass -File deploy.ps1

param(
    [string]$action = "start",
    [string]$envFile = "production.env"
)

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPath = Join-Path $ProjectRoot ".venv"
$ActivateScript = Join-Path $VenvPath "Scripts\Activate.ps1"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "App Notaria - Production Deployment" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Función para activar el entorno virtual
function Activate-VirtualEnv {
    if (-not (Test-Path $ActivateScript)) {
        Write-Host "[ERROR] Entorno virtual no encontrado en: $VenvPath" -ForegroundColor Red
        Write-Host "Por favor ejecuta primero: python -m venv .venv" -ForegroundColor Yellow
        exit 1
    }
    
    Write-Host "[1/4] Activando entorno virtual..." -ForegroundColor Green
    & $ActivateScript
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] No se pudo activar el entorno virtual" -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ Entorno virtual activado" -ForegroundColor Green
}

# Función para instalar dependencias
function Install-Dependencies {
    Write-Host "[2/4] Instalando dependencias..." -ForegroundColor Green
    $reqFile = Join-Path $ProjectRoot "requirements.txt"
    if (Test-Path $reqFile) {
        pip install -r $reqFile -q
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] Error al instalar dependencias" -ForegroundColor Red
            exit 1
        }
        Write-Host "✓ Dependencias instaladas" -ForegroundColor Green
    } else {
        Write-Host "[WARNING] requirements.txt no encontrado" -ForegroundColor Yellow
    }
}

# Función para cargar variables de entorno
function Load-Environment {
    Write-Host "[3/4] Cargando configuración de entorno..." -ForegroundColor Green
    $envPath = Join-Path $ProjectRoot $envFile
    
    if (-not (Test-Path $envPath)) {
        Write-Host "[WARNING] Archivo $envFile no encontrado" -ForegroundColor Yellow
        Write-Host "Usando variables de entorno del sistema" -ForegroundColor Yellow
        return
    }
    
    $envContent = Get-Content $envPath
    foreach ($line in $envContent) {
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line -split "=", 2
            if ($parts.Count -eq 2) {
                [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
            }
        }
    }
    Write-Host "✓ Configuración cargada desde: $envFile" -ForegroundColor Green
}

# Función para iniciar la aplicación
function Start-Application {
    Write-Host "[4/4] Iniciando aplicación..." -ForegroundColor Green
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Servidor iniciando en:" -ForegroundColor Cyan
    Write-Host "  URL: http://0.0.0.0:8000" -ForegroundColor Yellow
    Write-Host "  Docs: http://localhost:8000/docs" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    # Ejecutar con gunicorn o uvicorn según disponibilidad
    $workers = 4
    if ($env:WORKERS) {
        $workers = $env:WORKERS
    }
    
    $host_addr = "0.0.0.0"
    if ($env:HOST) {
        $host_addr = $env:HOST
    }
    
    $port = "8000"
    if ($env:PORT) {
        $port = $env:PORT
    }
    
    # Ejecutar uvicorn
    python -m uvicorn app:app `
        --host $host_addr `
        --port $port `
        --workers $workers `
        --log-level info
}

# Función para detener la aplicación
function Stop-Application {
    Write-Host "[!] Deteniendo aplicación..." -ForegroundColor Yellow
    # Buscar procesos de Python/uvicorn y terminarlos
    Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match "uvicorn|app.py" } | Stop-Process -Force
    Write-Host "✓ Aplicación detenida" -ForegroundColor Green
}

# Flujo principal
try {
    switch ($action) {
        "start" {
            Activate-VirtualEnv
            Install-Dependencies
            Load-Environment
            Start-Application
        }
        "stop" {
            Stop-Application
        }
        "restart" {
            Stop-Application
            Start-Sleep -Seconds 2
            Activate-VirtualEnv
            Install-Dependencies
            Load-Environment
            Start-Application
        }
        default {
            Write-Host "Uso: powershell -ExecutionPolicy Bypass -File deploy.ps1 [start|stop|restart] [envFile]" -ForegroundColor Yellow
            Write-Host ""
            Write-Host "Ejemplos:" -ForegroundColor Cyan
            Write-Host "  deploy.ps1 start              # Inicia en modo producción" -ForegroundColor White
            Write-Host "  deploy.ps1 start production.env" -ForegroundColor White
            Write-Host "  deploy.ps1 stop               # Detiene la aplicación" -ForegroundColor White
            Write-Host "  deploy.ps1 restart            # Reinicia la aplicación" -ForegroundColor White
            exit 1
        }
    }
} catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
