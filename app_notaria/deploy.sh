#!/bin/bash
# Script de Despliegue para Producción (Linux/Mac)
# ================================================
# Uso: bash deploy.sh [start|stop|restart]

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$PROJECT_ROOT/.venv"
ACTIVATE_SCRIPT="$VENV_PATH/bin/activate"
ENV_FILE="$PROJECT_ROOT/production.env"
PID_FILE="$PROJECT_ROOT/.app.pid"

echo ""
echo "========================================"
echo "App Notaria - Production Deployment"
echo "========================================"
echo ""

# Función para activar el entorno virtual
activate_venv() {
    if [ ! -f "$ACTIVATE_SCRIPT" ]; then
        echo "[ERROR] Entorno virtual no encontrado en: $VENV_PATH"
        echo "Por favor ejecuta primero: python -m venv .venv"
        exit 1
    fi
    
    echo "[1/4] Activando entorno virtual..."
    source "$ACTIVATE_SCRIPT"
    echo "✓ Entorno virtual activado"
}

# Función para instalar dependencias
install_dependencies() {
    echo "[2/4] Instalando dependencias..."
    if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
        pip install -q -r "$PROJECT_ROOT/requirements.txt"
        echo "✓ Dependencias instaladas"
    else
        echo "[WARNING] requirements.txt no encontrado"
    fi
}

# Función para cargar variables de entorno
load_environment() {
    echo "[3/4] Cargando configuración..."
    if [ -f "$ENV_FILE" ]; then
        set -a
        source "$ENV_FILE"
        set +a
        echo "✓ Configuración cargada desde: $ENV_FILE"
    else
        echo "[WARNING] $ENV_FILE no encontrado"
    fi
}

# Función para iniciar la aplicación
start_application() {
    echo "[4/4] Iniciando aplicación..."
    echo ""
    echo "========================================"
    echo "Servidor iniciando en:"
    echo "  URL: http://0.0.0.0:8000"
    echo "  Docs: http://localhost:8000/docs"
    echo "========================================"
    echo ""
    
    # Configurar variables por defecto
    HOST="${HOST:-0.0.0.0}"
    PORT="${PORT:-8000}"
    WORKERS="${WORKERS:-4}"
    
    # Ejecutar uvicorn
    python -m uvicorn app:app \
        --host "$HOST" \
        --port "$PORT" \
        --workers "$WORKERS" \
        --log-level info
}

# Función para detener la aplicación
stop_application() {
    echo "[!] Deteniendo aplicación..."
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        kill $PID 2>/dev/null || true
        rm "$PID_FILE"
    fi
    pkill -f "uvicorn app:app" || true
    echo "✓ Aplicación detenida"
}

# Flujo principal
case "${1:-start}" in
    start)
        activate_venv
        install_dependencies
        load_environment
        start_application
        ;;
    stop)
        stop_application
        ;;
    restart)
        stop_application
        sleep 2
        activate_venv
        install_dependencies
        load_environment
        start_application
        ;;
    *)
        echo "Uso: bash deploy.sh [start|stop|restart]"
        echo ""
        echo "Ejemplos:"
        echo "  ./deploy.sh start    # Inicia en modo producción"
        echo "  ./deploy.sh stop     # Detiene la aplicación"
        echo "  ./deploy.sh restart  # Reinicia la aplicación"
        exit 1
        ;;
esac
