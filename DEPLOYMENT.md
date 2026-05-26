# Guía de Despliegue a Producción
## App Notaria

---

## 📋 Índice
1. [Requisitos](#requisitos)
2. [Configuración Inicial](#configuración-inicial)
3. [Despliegue en Windows](#despliegue-en-windows)
4. [Despliegue en Linux/Mac](#despliegue-en-linuxmac)
5. [Configuración de Producción](#configuración-de-producción)
6. [Monitoreo y Logs](#monitoreo-y-logs)
7. [Troubleshooting](#troubleshooting)

---

## Requisitos

- **Python 3.8+**
- **pip** (gestor de paquetes de Python)
- **Credenciales de Supabase** (URL, anon key, service role key)
- **Puerto 8000** disponible (o el que configures)

---

## Configuración Inicial

### 1. Crear el entorno virtual (primera vez)

**Windows (CMD):**
```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Linux/Mac:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

Edita `production.env`:

```env
ENVIRONMENT=production
DEBUG=false
HOST=0.0.0.0
PORT=8000
WORKERS=4
RELOAD=false

SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_KEY=tu-anon-key
SUPABASE_SERVICE_ROLE_KEY=tu-service-role-key
LOG_LEVEL=info
```

> ⚠️ **IMPORTANTE**: Nunca comitas credenciales sensibles. Usa variables de entorno del sistema en producción.

---

## Despliegue en Windows

### Opción 1: Script PowerShell (Recomendado)

**Primera vez:**
```powershell
powershell -ExecutionPolicy Bypass -File deploy.ps1 start
```

**Posterior:**
```powershell
powershell -ExecutionPolicy Bypass -File deploy.ps1 start
```

**Detener:**
```powershell
powershell -ExecutionPolicy Bypass -File deploy.ps1 stop
```

**Reiniciar:**
```powershell
powershell -ExecutionPolicy Bypass -File deploy.ps1 restart
```

### Opción 2: Script Batch

**Primera vez:**
```cmd
deploy.bat
```

**Posterior:**
```cmd
deploy.bat
```

### Opción 3: Manual con CMD

```cmd
.venv\Scripts\activate
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## Despliegue en Linux/Mac

### Hacer script ejecutable

```bash
chmod +x deploy.sh
```

### Ejecutar despliegue

**Primera vez:**
```bash
./deploy.sh start
```

**Detener:**
```bash
./deploy.sh stop
```

**Reiniciar:**
```bash
./deploy.sh restart
```

### En segundo plano (con nohup)

```bash
nohup ./deploy.sh start > app.log 2>&1 &
```

### Con supervisor (recomendado para producción)

Crea `/etc/supervisor/conf.d/app_notaria.conf`:

```ini
[program:app_notaria]
directory=/path/to/app_notaria
command=/path/to/app_notaria/.venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4
autostart=true
autorestart=true
stderr_logfile=/var/log/app_notaria.err.log
stdout_logfile=/var/log/app_notaria.out.log
environment=ENVIRONMENT=production,SUPABASE_URL=...,SUPABASE_KEY=...
```

Luego:
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start app_notaria
```

---

## Configuración de Producción

### Archivos importantes

| Archivo | Descripción |
|---------|-------------|
| `production.env` | Variables de entorno (creadas desde el template) |
| `.env` | Variables locales (NO subir a repositorio) |
| `.gitignore` | Archivos ignorados por git |

### Variables de entorno

```env
# Entorno
ENVIRONMENT=production
DEBUG=false

# Servidor
HOST=0.0.0.0          # Escucha en todas las interfaces
PORT=8000             # Puerto (cambia si es necesario)
WORKERS=4             # Procesos uvicorn (ajusta según CPU)
RELOAD=false          # NUNCA en producción

# Supabase
SUPABASE_URL=...      # URL del proyecto
SUPABASE_KEY=...      # Clave anónima
SUPABASE_SERVICE_ROLE_KEY=...  # Clave de servicio

# Logging
LOG_LEVEL=info        # info, warning, error, debug
```

### Consideraciones de seguridad

1. **Nunca comitas `.env` o `production.env` con credenciales reales**
2. **Usa variables de entorno del sistema en producción**
3. **Limita permisos de archivos**: `chmod 600 production.env`
4. **Usa HTTPS en producción** (nginx/Apache reverse proxy)
5. **Configura firewall** para permitir solo puerto 8000 internamente
6. **Monitorea logs** regularmente

---

## Monitoreo y Logs

### Ver logs en tiempo real

**Windows (PowerShell):**
```powershell
Get-Content -Path "app.log" -Wait
```

**Linux/Mac:**
```bash
tail -f app.log
```

### Verificar que la app está corriendo

**Probar endpoint:**
```bash
curl http://localhost:8000/
```

**Ver procesos (Windows):**
```cmd
tasklist | findstr python
```

**Ver procesos (Linux/Mac):**
```bash
ps aux | grep uvicorn
```

---

## Troubleshooting

### El puerto 8000 está en uso

**Windows:**
```cmd
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

**Linux/Mac:**
```bash
lsof -i :8000
kill -9 <PID>
```

### Error: "No module named 'fastapi'"

```bash
# Activar entorno virtual
# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate

# Reinstalar dependencias
pip install -r requirements.txt
```

### Error de conexión a Supabase

1. Verifica que `SUPABASE_URL` y `SUPABASE_KEY` sean correctas
2. Comprueba que la red tiene acceso a Supabase
3. Verifica RLS (Row Level Security) en tablas

### La app se detiene aleatoriamente

1. Aumenta el número de workers: `WORKERS=8`
2. Aumenta timeout de solicitudes
3. Revisa los logs para errores
4. Usa supervisor para reinicio automático

### No puede acceder desde otra máquina

1. Verifica firewall del servidor
2. Comprueba que escuche en `0.0.0.0` (no `localhost`)
3. Usa IP del servidor, no `localhost`
4. Ejemplo: `http://192.168.1.100:8000`

---

## Scripts disponibles

| Script | Uso |
|--------|-----|
| `deploy.ps1` | PowerShell para Windows (recomendado) |
| `deploy.bat` | Batch para Windows |
| `deploy.sh` | Bash para Linux/Mac |

---

## Próximos pasos

- [ ] Configura las credenciales reales en `production.env`
- [ ] Prueba la aplicación en modo producción
- [ ] Configura monitoreo (logs, alerts)
- [ ] Configura SSL/HTTPS con nginx
- [ ] Configura backups automáticos
- [ ] Documenta procedimientos de rollback

---

## Soporte

Para problemas o preguntas:
1. Revisa los logs
2. Consulta la sección Troubleshooting
3. Verifica la conectividad de red
4. Contrata soporte de Supabase si es necesario

---

**Última actualización:** Mayo 2026
**Versión:** 1.0
