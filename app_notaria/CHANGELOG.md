# Histórico de Cambios
## App Notaria

---

## [1.0.0] - 2026-05-22

### 🎉 Primer Release

#### ✨ Características añadidas
- **Interfaz web completa** con HTML/CSS/JavaScript
  - Panel de estadísticas de liquidación
  - Sistema de carga de certificados
  - Gestor de recibos
  - Dashboard de pagos

- **Backend FastAPI** robusto
  - API REST para operaciones CRUD
  - Sistema de jobs asincronos para tareas largas
  - Integración con Supabase
  - Manejo de archivos Excel

- **Scripts de importación**
  - `import_liq_from_excel.py` - Importar liquidaciones
  - `import_pagos_from_excel.py` - Importar pagos
  - `create_supabase_schema_from_excel.py` - Auto-generar schema

- **Procesamiento de documentos**
  - `certificados.py` - Generar certificados PDF
  - `envio_certificados.py` - Enviar certificados por email
  - `envio_recibos.py` - Enviar recibos

- **Sistema de logs**
  - Registros de todas las operaciones en base de datos
  - Trazabilidad completa

#### 📦 Scripts de despliegue
- **deploy.ps1** - PowerShell para Windows
- **deploy.bat** - Batch para Windows
- **deploy.sh** - Bash para Linux/Mac

#### 📖 Documentación
- **README.md** - Descripción general y setup inicial
- **DEPLOYMENT.md** - Guía completa de despliegue a producción
- **CHANGELOG.md** - Este archivo

#### ⚙️ Configuración
- **requirements.txt** - Dependencias del proyecto
- **.gitignore** - Archivos ignorados
- **production.env** - Template de variables de entorno

#### 🔧 Base de datos
- **supabase_schema.sql** - Schema principal
- **supabase_schema_from_excel.sql** - Schema generado desde Excel

---

## Notas de la versión

### Instalación
```bash
python -m venv .venv
source .venv/bin/activate  # o .venv\Scripts\activate en Windows
pip install -r requirements.txt
```

### Ejecución en desarrollo
```bash
python -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

### Ejecución en producción
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

### Variables de entorno obligatorias
- `SUPABASE_URL` - URL del proyecto Supabase
- `SUPABASE_KEY` - Clave anónima
- `SUPABASE_SERVICE_ROLE_KEY` - Clave de servicio (opcional pero recomendada)

---

## Issues conocidos

- [ ] RLS en Supabase puede bloquear operaciones si no está configurado correctamente
- [ ] Los emails requieren configuración SMTP adicional
- [ ] PDF generation requiere fonts del sistema en el servidor

---

## Roadmap futuro

- [ ] Autenticación de usuarios
- [ ] Interfaz de administrador
- [ ] Reportes personalizados
- [ ] API pública con autenticación
- [ ] Webhook para eventos
- [ ] Sistema de notificaciones push
- [ ] Mobile app

---

**Versión estable:** Sí  
**Recomendado para producción:** Sí  
**Requiere testing adicional:** RLS y emails  

---

*Generado: 2026-05-22*
