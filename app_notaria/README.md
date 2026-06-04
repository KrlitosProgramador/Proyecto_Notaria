# App Notaria

Sistema integral de gestión de notaría con interfaz web, integración con Supabase y herramientas de administración.

**Versión:** 1.0.0  
**Última actualización:** Mayo 2026

---

## 📋 Tabla de contenidos

1. [Características](#características)
2. [Requisitos](#requisitos)
3. [Instalación](#instalación)
4. [Ejecución](#ejecución)
5. [Configuración de datos](#configuración-de-datos)
6. [Despliegue a producción](#despliegue-a-producción)
7. [API Endpoints](#api-endpoints)
8. [Scripts auxiliares](#scripts-auxiliares)
9. [Documentación adicional](#documentación-adicional)

---

## ✨ Características

### 🎨 Interfaz Web
- Dashboard completo con estadísticas
- Panel de liquidaciones
- Gestor de certificados
- Sistema de recibos
- Interfaz responsiva y moderna

### 🔧 Backend FastAPI
- API REST completamente documentada (Swagger/OpenAPI)
- Integración nativa con Supabase
- Sistema de jobs asincronos para operaciones largas
- Manejo de archivos Excel
- Sistema de logs integrado

### 📊 Funcionalidades
- Importación de liquidaciones desde Excel
- Generación de certificados en PDF
- Envío automático de emails
- Gestión de pagos
- Estadísticas en tiempo real
- Trazabilidad completa de operaciones

### 🚀 Despliegue
- Scripts de despliegue para Windows (PowerShell/Batch)
- Scripts de despliegue para Linux/Mac (Bash)
- Configuración por entorno (desarrollo/producción)
- Documentación completa de deployment

---

## 📦 Requisitos

- **Python 3.8 o superior**
- **pip** (gestor de paquetes)
- **Cuenta de Supabase** con credenciales
- **Git** (para versionamiento)
- **Puerto 8000** disponible (o configurable)

**Dependencias principales:**
- FastAPI
- Uvicorn
- Pandas
- Supabase
- ReportLab (PDF)
- Selenium (automatización)

---

## 🚀 Instalación

### 1. Clonar o descargar el proyecto

```bash
git clone <URL-repositorio>
cd app_notaria
```

### 2. Crear entorno virtual

**Windows (CMD):**
```cmd
python -m venv .venv
.venv\Scripts\activate
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Linux/Mac:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

Crea un archivo `.env` (NO en repositorio):

```env
ENVIRONMENT=development
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_KEY=tu-anon-key
SUPABASE_SERVICE_ROLE_KEY=tu-service-role-key
DEBUG=true
```

---

## ▶️ Ejecución

### Modo desarrollo (con auto-recarga)

```bash
python -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Accede a: http://localhost:8000

### Modo producción

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -File deploy.ps1 start
```

**Windows (Batch):**
```cmd
deploy.bat
```

**Linux/Mac:**
```bash
./deploy.sh start
```

Accede a: http://localhost:8000 (o tu servidor)

---

## 🗄️ Configuración de datos

### 1. Crear tabla en Supabase

Usa el editor SQL de Supabase y ejecuta:

```bash
# Opción 1: Desde archivo
cat supabase_schema_from_excel.sql | # copiar y pegar en editor SQL

# O simplemente usa:
# supabase_schema.sql
```

### 2. Importar datos desde Excel

```bash
python import_liq_from_excel.py --excel tu_archivo.xlsx --batch 200
```

### 3. Importar pagos desde Excel

```bash
python import_pagos_from_excel.py --excel tu_archivo.xlsx
```

### 4. Verificar datos

```bash
python -c "from supabase_client import get_supabase; 
supabase=get_supabase()
rows = supabase.table('liq').select('*').limit(5).execute()
print(f'Total registros: {len(rows.data)}')"
```

---

## 🌐 Despliegue a producción

**Versión corta:**

1. Edita `production.env` con credenciales reales
2. En Windows: `powershell -ExecutionPolicy Bypass -File deploy.ps1 start`
3. En Linux/Mac: `./deploy.sh start`

**Versión detallada:** Ver [DEPLOYMENT.md](DEPLOYMENT.md)

---

## 📡 API Endpoints

### Estadísticas

```http
GET /api/liq/stats
GET /api/liq/all
GET /api/liq/pending
GET /api/liq/processed
```

### Operaciones

```http
POST /api/descargas/certificados/start
GET /api/jobs/{job_id}
```

### Documentación interactiva

Accede a: `http://localhost:8000/docs` (Swagger UI)

---

## 🛠️ Scripts auxiliares

### Primer commit con Git

**Windows:**
```powershell
powershell -ExecutionPolicy Bypass -File first-commit.ps1
```

**Linux/Mac:**
```bash
chmod +x first-commit.sh
./first-commit.sh
```

### Generación de schema desde Excel

```bash
python create_supabase_schema_from_excel.py --excel tu_archivo.xlsx
```

### Envío de certificados

```bash
python envio_certificados.py
```

### Envío de recibos

```bash
python envio_recibos.py
```

---

## 📖 Documentación adicional

| Documento | Descripción |
|-----------|-------------|
| [DEPLOYMENT.md](DEPLOYMENT.md) | Guía completa de despliegue a producción |
| [GIT_WORKFLOW.md](GIT_WORKFLOW.md) | Convenciones de commits y workflow de git |
| [CHANGELOG.md](CHANGELOG.md) | Histórico de cambios y releases |

---

## 🔐 Seguridad

- ⚠️ **NUNCA** subas archivos `.env` con credenciales reales
- ⚠️ Usa `SUPABASE_SERVICE_ROLE_KEY` solo en servidor, no en cliente
- ⚠️ En producción, usa HTTPS y firewall
- ✓ Configura RLS (Row Level Security) en Supabase
- ✓ Revisa los logs regularmente

---

## 🐛 Solución de problemas

### "No module named 'fastapi'"

```bash
# Activa el entorno virtual
source .venv/bin/activate  # Linux/Mac
# o
.venv\Scripts\activate     # Windows

# Reinstala
pip install -r requirements.txt
```

### "Port 8000 is already in use"

```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux/Mac
lsof -i :8000
kill -9 <PID>
```

### "Supabase connection refused"

1. Verifica que `SUPABASE_URL` y credenciales sean correctas
2. Confirma que tienes acceso a internet
3. Revisa que RLS no bloquee operaciones

### "No data showing in UI"

1. Verifica que la tabla `liq` exista en Supabase
2. Confirma que hay datos: `SELECT COUNT(*) FROM liq;`
3. Revisa que uses `SUPABASE_SERVICE_ROLE_KEY` para lecturas

---

## 📞 Soporte

Para problemas:
1. Revisa [DEPLOYMENT.md](DEPLOYMENT.md) sección Troubleshooting
2. Verifica que todas las dependencias están instaladas
3. Comprueba credenciales de Supabase
4. Revisa los logs de la aplicación

---

## 📝 Notas importantes

- La tabla `liq` debe existir en Supabase (ver configuración de datos)
- Para importar datos, necesitas `SUPABASE_SERVICE_ROLE_KEY`
- En producción, cambia `DEBUG=false` en `production.env`
- Los logs se guardan en la base de datos (tabla `logs`)
- El servidor escucha en `0.0.0.0` en producción (acepta conexiones remotas)

---

**Estado:** ✅ Listo para producción  
**Versión:** 1.0.0  
**Última actualización:** 2026-05-22
