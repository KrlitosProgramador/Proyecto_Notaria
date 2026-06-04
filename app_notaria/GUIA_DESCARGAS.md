# Guía: Sistema de Descargas y Envíos Integrado con Supabase

## 📋 Configuración

### Paso 1: Crear tabla en Supabase

1. Ve a tu proyecto en https://app.supabase.com
2. Ve a **SQL Editor** (lado izquierdo)
3. Click en **New Query**
4. Copia y pega el contenido de `supabase_descargas_schema.sql`
5. Click en **Run** (arriba a la derecha)

### Paso 2: Actualizar scripts locales

Los scripts `certificados.py` y `envio_recibos.py` deben guardar archivos en Supabase.

Después de generar un PDF, agrega:

```python
from supabase_client import guardar_descarga

# Después de generar el PDF
with open(ruta_archivo_pdf, 'rb') as f:
    contenido = f.read()

guardar_descarga(
    tipo='certificado',  # o 'recibo'
    escritura='123456',  # número de escritura
    archivo_nombre='123456.pdf',
    archivo_contenido=contenido,
    email='usuario@ejemplo.com'
)
```

---

## 🌐 API Endpoints

### Guardar descarga
```
POST /api/descargas/guardar
Content-Type: multipart/form-data

Parámetros:
- tipo (requerido): 'recibo' o 'certificado'
- escritura (requerido): número de escritura
- email (opcional): correo del destinatario
- file (requerido): archivo PDF

Respuesta:
{
  "status": "ok",
  "descarga_id": "uuid",
  "mensaje": "Recibo guardado exitosamente"
}
```

### Obtener descargas de una escritura
```
GET /api/descargas/{escritura}?tipo=recibo

Respuesta:
{
  "status": "ok",
  "descargas": [
    {
      "id": "uuid",
      "tipo": "recibo",
      "escritura": "123456",
      "archivo_nombre": "123456.pdf",
      "email": "usuario@ejemplo.com",
      "enviado": false,
      "archivo_base64": "base64_encoded_content"
    }
  ]
}
```

### Descargar archivo
```
GET /api/descargas/download/{descarga_id}

Respuesta: Archivo PDF descargable
```

### Enviar descarga por correo
```
POST /api/descargas/{descarga_id}/enviar-correo

Body:
{
  "email": "nuevo@ejemplo.com"  // opcional, usa el del registro si no se especifica
}

Respuesta:
{
  "status": "ok",
  "mensaje": "Recibo enviado a usuario@ejemplo.com",
  "email": "usuario@ejemplo.com",
  "archivo": "123456.pdf"
}
```

### Obtener descargas pendientes
```
GET /api/descargas/pendientes?tipo=certificado&limit=50

Respuesta:
{
  "status": "ok",
  "total": 5,
  "descargas": [...]
}
```

---

## 🔧 Implementación en Frontend

### Ejemplo: Descargar y guardar en BD

```javascript
async function guardarYDescargarPDF(escritura, email) {
  // 1. Generar o descargar PDF (desde local o API)
  const pdfBlob = await generarPDF(escritura);  // Tu función
  
  // 2. Guardar en BD
  const formData = new FormData();
  formData.append('tipo', 'certificado');
  formData.append('escritura', escritura);
  formData.append('email', email);
  formData.append('file', pdfBlob, `${escritura}.pdf`);
  
  const resp = await fetch('/api/descargas/guardar', {
    method: 'POST',
    body: formData
  });
  
  const result = await resp.json();
  return result.descarga_id;
}

// 3. Enviar por correo
async function enviarPorCorreo(descargaId, email) {
  const resp = await fetch(`/api/descargas/${descargaId}/enviar-correo`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email })
  });
  
  return await resp.json();
}
```

---

## 📊 Base de datos

Tabla `descargas`:
- `id`: UUID (primary key)
- `tipo`: 'recibo' | 'certificado'
- `escritura`: número de escritura
- `archivo_nombre`: nombre del archivo
- `archivo_contenido`: contenido en bytes
- `email`: email del destinatario
- `enviado`: boolean
- `fecha_descarga`: timestamp
- `fecha_envio`: timestamp
- `creado_at`: timestamp

---

## ✅ Flujo completo

1. **Local (tu máquina):**
   - Ejecuta `certificados.py` o `envio_recibos.py`
   - Genera PDFs con Selenium/ReportLab
   - Llama `guardar_descarga()` para guardar en BD

2. **Web (Render):**
   - API lista PDFs disponibles
   - Usuario descarga o envía por correo
   - Se marca como "enviado" en BD

3. **BD centralizada (Supabase):**
   - Almacena archivos y referencias
   - Accesible desde cualquier lugar
   - Histórico de descargas y envíos

