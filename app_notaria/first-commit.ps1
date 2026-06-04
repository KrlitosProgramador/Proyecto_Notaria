# Script para hacer el primer commit
# ==================================
# Uso: powershell -ExecutionPolicy Bypass -File first-commit.ps1

param(
    [string]$repoUrl = ""
)

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "App Notaria - First Commit Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# Verificar si git está disponible
Write-Host "[1/5] Verificando Git..." -ForegroundColor Green

$gitCheck = & {
    try {
        git --version 2>$null
        return $true
    } catch {
        return $false
    }
}

if (-not $gitCheck) {
    Write-Host "[ERROR] Git no está instalado o no está en el PATH" -ForegroundColor Red
    Write-Host ""
    Write-Host "Por favor instala Git desde: https://git-scm.com/download/win" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Después de instalar, cierra y reabre PowerShell." -ForegroundColor Yellow
    exit 1
}

Write-Host "✓ Git disponible" -ForegroundColor Green
Write-Host ""

# Verificar si ya existe .git
Write-Host "[2/5] Verificando repositorio..." -ForegroundColor Green

$gitDir = Join-Path $ProjectRoot ".git"
$isGitRepo = Test-Path $gitDir

if ($isGitRepo) {
    Write-Host "⚠ Repositorio git ya inicializado" -ForegroundColor Yellow
    $response = Read-Host "¿Deseas reinicializarlo? (s/n)"
    if ($response -eq "s") {
        Remove-Item $gitDir -Recurse -Force
        Write-Host "✓ Repositorio anterior eliminado" -ForegroundColor Green
    } else {
        Write-Host "[ABORTADO]" -ForegroundColor Yellow
        exit 0
    }
} else {
    Write-Host "✓ Nuevo repositorio (sin .git)" -ForegroundColor Green
}

Write-Host ""

# Configurar usuario git
Write-Host "[3/5] Configurando usuario de Git..." -ForegroundColor Green

$gitName = git config --global user.name 2>$null
$gitEmail = git config --global user.email 2>$null

if (-not $gitName) {
    Write-Host ""
    Write-Host "¿Cuál es tu nombre? (para los commits)" -ForegroundColor Yellow
    $name = Read-Host "Nombre"
    git config --global user.name $name
    Write-Host "✓ Nombre configurado: $name" -ForegroundColor Green
} else {
    Write-Host "✓ Usuario: $gitName ($gitEmail)" -ForegroundColor Green
}

if (-not $gitEmail) {
    Write-Host ""
    Write-Host "¿Cuál es tu email? (para los commits)" -ForegroundColor Yellow
    $email = Read-Host "Email"
    git config --global user.email $email
    Write-Host "✓ Email configurado: $email" -ForegroundColor Green
}

Write-Host ""

# Inicializar repositorio
Write-Host "[4/5] Inicializando repositorio..." -ForegroundColor Green

cd $ProjectRoot

# Inicializar git
git init
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] No se pudo inicializar git" -ForegroundColor Red
    exit 1
}

# Crear rama main si no existe
git symbolic-ref HEAD refs/heads/main 2>$null

# Agregar archivos
git add .
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] No se pudieron agregar los archivos" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Repositorio inicializado" -ForegroundColor Green
Write-Host ""

# Hacer el primer commit
Write-Host "[5/5] Haciendo el primer commit..." -ForegroundColor Green

git commit -m "Initial commit: App Notaria v1.0.0

- Complete FastAPI backend with Supabase integration
- Web UI with statistics dashboard
- Certificate generation and email sending
- Data import scripts from Excel
- Deployment scripts for Windows/Linux/Mac
- Complete documentation and changelog"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Primer commit completado exitosamente" -ForegroundColor Green
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "✓ SETUP COMPLETADO" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    git log --oneline -1
    
    Write-Host ""
    Write-Host "Próximos pasos:" -ForegroundColor Cyan
    Write-Host "  1. git remote add origin <URL-del-repositorio>" -ForegroundColor White
    Write-Host "  2. git push -u origin main" -ForegroundColor White
    Write-Host ""
    
    if ($repoUrl) {
        Write-Host "¿Agregar remoto? (s/n)" -ForegroundColor Yellow
        $addRemote = Read-Host ""
        if ($addRemote -eq "s") {
            git remote add origin $repoUrl
            Write-Host "✓ Remoto agregado: $repoUrl" -ForegroundColor Green
            
            Write-Host ""
            Write-Host "¿Hacer push a repositorio remoto? (s/n)" -ForegroundColor Yellow
            $doPush = Read-Host ""
            if ($doPush -eq "s") {
                Write-Host "Subiendo repositorio..." -ForegroundColor Yellow
                git push -u origin main
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "✓ Código subido a: $repoUrl" -ForegroundColor Green
                } else {
                    Write-Host "[ERROR] No se pudo hacer push" -ForegroundColor Red
                }
            }
        }
    }
    
} else {
    Write-Host "[ERROR] No se pudo hacer el commit" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Para desplegar a producción, ejecuta:" -ForegroundColor Cyan
Write-Host "  powershell -ExecutionPolicy Bypass -File deploy.ps1 start" -ForegroundColor Yellow
Write-Host ""
