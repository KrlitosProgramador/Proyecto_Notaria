#!/bin/bash
# Script para hacer el primer commit
# ==================================
# Uso: bash first-commit.sh [URL-repositorio]

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_URL="${1:-}"

echo ""
echo "========================================"
echo "App Notaria - First Commit Setup"
echo "========================================"
echo ""

# Verificar si git está disponible
echo "[1/5] Verificando Git..."

if ! command -v git &> /dev/null; then
    echo "[ERROR] Git no está instalado"
    echo ""
    echo "Por favor instala Git:"
    echo "  Mac: brew install git"
    echo "  Linux: sudo apt-get install git"
    echo ""
    exit 1
fi

echo "✓ Git disponible: $(git --version)"
echo ""

# Verificar si ya existe .git
echo "[2/5] Verificando repositorio..."

if [ -d "$PROJECT_ROOT/.git" ]; then
    echo "⚠ Repositorio git ya inicializado"
    read -p "¿Deseas reinicializarlo? (s/n): " -r response
    if [[ $response == "s" ]]; then
        rm -rf "$PROJECT_ROOT/.git"
        echo "✓ Repositorio anterior eliminado"
    else
        echo "[ABORTADO]"
        exit 0
    fi
else
    echo "✓ Nuevo repositorio (sin .git)"
fi

echo ""

# Configurar usuario git
echo "[3/5] Configurando usuario de Git..."

GIT_NAME=$(git config --global user.name 2>/dev/null || echo "")
GIT_EMAIL=$(git config --global user.email 2>/dev/null || echo "")

if [ -z "$GIT_NAME" ]; then
    echo ""
    read -p "¿Cuál es tu nombre? (para los commits): " -r name
    git config --global user.name "$name"
    echo "✓ Nombre configurado: $name"
else
    echo "✓ Usuario: $GIT_NAME <$GIT_EMAIL>"
fi

if [ -z "$GIT_EMAIL" ]; then
    echo ""
    read -p "¿Cuál es tu email? (para los commits): " -r email
    git config --global user.email "$email"
    echo "✓ Email configurado: $email"
fi

echo ""

# Inicializar repositorio
echo "[4/5] Inicializando repositorio..."

cd "$PROJECT_ROOT"

# Inicializar git
git init
git symbolic-ref HEAD refs/heads/main 2>/dev/null || true

# Agregar archivos
git add .

echo "✓ Repositorio inicializado"
echo ""

# Hacer el primer commit
echo "[5/5] Haciendo el primer commit..."

git commit -m "Initial commit: App Notaria v1.0.0

- Complete FastAPI backend with Supabase integration
- Web UI with statistics dashboard
- Certificate generation and email sending
- Data import scripts from Excel
- Deployment scripts for Windows/Linux/Mac
- Complete documentation and changelog"

if [ $? -eq 0 ]; then
    echo "✓ Primer commit completado exitosamente"
    echo ""
    echo "========================================"
    echo "✓ SETUP COMPLETADO"
    echo "========================================"
    echo ""
    
    git log --oneline -1
    
    echo ""
    echo "Próximos pasos:"
    echo "  1. git remote add origin <URL-del-repositorio>"
    echo "  2. git push -u origin main"
    echo ""
    
    if [ -n "$REPO_URL" ]; then
        echo "¿Agregar remoto? (s/n)"
        read -r add_remote
        if [ "$add_remote" = "s" ]; then
            git remote add origin "$REPO_URL"
            echo "✓ Remoto agregado: $REPO_URL"
            
            echo ""
            echo "¿Hacer push a repositorio remoto? (s/n)"
            read -r do_push
            if [ "$do_push" = "s" ]; then
                echo "Subiendo repositorio..."
                git push -u origin main
                if [ $? -eq 0 ]; then
                    echo "✓ Código subido a: $REPO_URL"
                else
                    echo "[ERROR] No se pudo hacer push"
                fi
            fi
        fi
    fi
    
else
    echo "[ERROR] No se pudo hacer el commit"
    exit 1
fi

echo ""
echo "Para desplegar a producción, ejecuta:"
echo "  ./deploy.sh start"
echo ""
