import os
from dotenv import load_dotenv
from supabase import create_client, Client


load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    # fall back to empty client placeholder to avoid crashes during import
    supabase: Client | None = None
else:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_supabase() -> Client:
    return supabase

def insert_certificado(numero_certificado, usuario, archivo_path, estado="generado"):
    if not supabase:
        raise RuntimeError("Supabase client no configurado. Revisa SUPABASE_URL y SUPABASE_KEY en .env")
    payload = {
        "numero_certificado": numero_certificado,
        "usuario": usuario,
        "archivo_path": archivo_path,
        "estado": estado,
    }
    return supabase.table("certificados").insert(payload).execute()

def update_certificado_estado(cert_id, estado):
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    return supabase.table("certificados").update({"estado": estado}).eq("id", cert_id).execute()

def insert_recibo(numero_recibo, certificado_id, monto=None, email_destinatario=None):
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    payload = {
        "numero_recibo": numero_recibo,
        "certificado_id": certificado_id,
        "monto": monto,
        "email_destinatario": email_destinatario,
    }
    return supabase.table("recibos").insert(payload).execute()

MAX_PAGE_SIZE = 10000
MAX_PAGE_SIZE_WARN = 1000
ALLOWED_SORT_COLUMNS = {
    'escritura', 'nir', 'pago', 'estado_ctl', 'notificacion', 'gobernacion',
    'updated_at', 'created_at', 'id'
}


def insert_liq_row(row: dict):
    """Inserta una fila tal cual en la tabla `liq` (derivada de Informe.xlsx)."""
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    return supabase.table("liq").insert(row).execute()


def _apply_sort(query, sort_by: str | None = None, desc: bool = True):
    if sort_by and sort_by in ALLOWED_SORT_COLUMNS:
        try:
            return query.order(sort_by, desc=desc)
        except Exception:
            return query
    return query


def _apply_pagination(query, page: int = 1, page_size: int = 100):
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    page = max(1, page)
    if page_size and page > 0:
        start = (page - 1) * page_size
        end = start + page_size - 1
        return query.range(start, end)
    return query


def get_pending_liq(limit: int = 100, page: int = 1, sort_by: str = 'escritura', desc: bool = False):
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    page = max(1, page)
    """Obtiene filas pendientes: filtro básico por estado_ctl != 'enviado' y pago=='Ingresado'"""
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    query = (
        supabase.table("liq")
        .select("*")
        .filter("estado_ctl", "neq", "Enviado")
        .filter("pago", "ilike", "Ingresado")
    )
    query = _apply_sort(query, sort_by, desc)
    query = _apply_pagination(query, page, limit)
    return query.execute()

def update_liq_estado_by_escritura(escritura_str: str, nuevo_estado: str):
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    # Intentar actualizar por la columna `escritura` primero, si no afecta filas, intentar `escritura_str`.
    try:
        res = supabase.table("liq").update({"estado_ctl": nuevo_estado}).eq("escritura", escritura_str).execute()
        # Si no actualizó, intentar con escritura_str
        count = getattr(res, 'count', None)
        if (count is None and not (res.data and len(res.data) > 0)) or (count == 0):
            res = supabase.table("liq").update({"estado_ctl": nuevo_estado}).eq("escritura_str", escritura_str).execute()
        return res
    except Exception:
        return supabase.table("liq").update({"estado_ctl": nuevo_estado}).eq("escritura_str", escritura_str).execute()


def update_liq_row(escritura_str: str, data: dict):
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    payload = data.copy()
    payload.pop("id", None)
    payload.pop("fecha_proceso", None)  # Campo de solo lectura
    
    # Intenta actualizar; si falla por columna inexistente, reintenta sin esa columna
    try:
        res = supabase.table("liq").update(payload).eq("escritura", escritura_str).execute()
    except Exception as e:
        error_msg = str(e)
        # Si el error es por columna inexistente (PGRST204), intenta sin ruta_documento
        if "PGRST204" in error_msg and "ruta_documento" in error_msg:
            print(f"[WARNING] Columna 'ruta_documento' no existe en tabla 'liq'. Reintentando sin ella.")
            payload.pop("ruta_documento", None)
            try:
                res = supabase.table("liq").update(payload).eq("escritura", escritura_str).execute()
            except Exception as e2:
                raise RuntimeError(f"Error al actualizar liq: {e2}")
        else:
            raise RuntimeError(f"Error al actualizar liq: {e}")
    
    count = getattr(res, 'count', None)
    if (count is None and not (res.data and len(res.data) > 0)) or (count == 0):
        try:
            res = supabase.table("liq").update(payload).eq("escritura_str", escritura_str).execute()
        except Exception as e:
            if "PGRST204" in str(e) and "ruta_documento" in str(e):
                payload.pop("ruta_documento", None)
                res = supabase.table("liq").update(payload).eq("escritura_str", escritura_str).execute()
            else:
                raise
    return res

def get_certificados_por_usuario(usuario):
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    return supabase.table("certificados").select("*").eq("usuario", usuario).execute()

def insert_log(tipo_operacion, descripcion, usuario=None, resultado="exitoso"):
    if not supabase:
        # si no hay supabase simplemente imprime
        print(f"[LOG] {tipo_operacion} - {descripcion} - {usuario} - {resultado}")
        return None
    payload = {
        "tipo_operacion": tipo_operacion,
        "descripcion": descripcion,
        "usuario": usuario,
        "resultado": resultado,
    }
    try:
        return supabase.table("logs").insert(payload).execute()
    except Exception as e:
        # Evitar que un fallo en la tabla de logs rompa la aplicación.
        message = str(e)
        if "PGRST205" in message or "public.logs" in message:
            print(
                "[LOG-ERROR] No se pudo escribir en la tabla 'logs': tabla 'logs' no existe en el esquema público de Supabase. "
                "Crea la tabla usando `supabase_schema.sql` o en la consola de Supabase."
            )
        else:
            print(f"[LOG-ERROR] No se pudo escribir en la tabla 'logs': {e}")
        return None


def get_liq_stats():
    """Devuelve estadísticas básicas de la tabla `liq`:
    - total: total de filas
    - pago_ingresado: filas con pago == 'Ingresado'
    - pendientes: filas con pago == 'Ingresado' y estado_ctl != 'Enviado'
    - procesados: filas con pago == 'Ingresado' y estado_ctl == 'Enviado'
    """
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")

    # total
    total_res = supabase.table("liq").select("id", count="exact").limit(1).execute()
    total = getattr(total_res, "count", None)
    if total is None:
        # fallback
        total = len(total_res.data or [])

    # pago ingresado (case-insensitive)
    pago_res = (
        supabase.table("liq").select("id", count="exact").filter("pago", "ilike", "Ingresado").limit(1).execute()
    )
    pago_ingresado = getattr(pago_res, "count", None)
    if pago_ingresado is None:
        pago_ingresado = len(pago_res.data or [])

    # pendientes (pago ingresado y estado_ctl != 'Enviado')
    pendientes_res = (
        supabase.table("liq")
        .select("id", count="exact")
        .filter("pago", "ilike", "Ingresado")
        .filter("estado_ctl", "neq", "Enviado")
        .limit(1)
        .execute()
    )
    pendientes = getattr(pendientes_res, "count", None)
    if pendientes is None:
        pendientes = len(pendientes_res.data or [])

    # procesados (pago ingresado y estado_ctl == 'Enviado')
    procesados_res = (
        supabase.table("liq")
        .select("id", count="exact")
        .filter("pago", "ilike", "Ingresado")
        .filter("estado_ctl", "ilike", "Enviado")
        .limit(1)
        .execute()
    )
    procesados = getattr(procesados_res, "count", None)
    if procesados is None:
        procesados = len(procesados_res.data or [])

    return {
        "total": total,
        "pago_ingresado": pago_ingresado,
        "pendientes": pendientes,
        "procesados": procesados,
    }


def get_all_liq(limit: int = 1000, page: int = 1, sort_by: str = 'updated_at', desc: bool = True):
    """Devuelve todas las filas de `liq` con paginación y ordenación opcional."""
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    page = max(1, page)
    query = supabase.table("liq").select("*")
    query = _apply_sort(query, sort_by, desc)
    query = _apply_pagination(query, page, limit)
    return query.execute()


def get_processed_liq(limit: int = 1000, page: int = 1, sort_by: str = 'updated_at', desc: bool = True):
    """Devuelve filas procesadas (pago='Ingresado' y estado_ctl='Enviado')."""
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    page = max(1, page)
    query = (
        supabase.table("liq")
        .select("*")
        .filter("pago", "ilike", "Ingresado")
        .filter("estado_ctl", "ilike", "Enviado")
    )
    query = _apply_sort(query, sort_by, desc)
    query = _apply_pagination(query, page, limit)
    return query.execute()


def get_existing_escrituras(table_name: str = "liq") -> set:
    """Obtiene el conjunto de todas las escrituras existentes en una tabla."""
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    try:
        result = supabase.table(table_name).select("escritura").execute()
        return {row.get("escritura") for row in result.data if row.get("escritura")}
    except Exception as e:
        print(f"[WARNING] No se pudo obtener escrituras de {table_name}: {e}")
        return set()


def import_liq_from_rows(rows: list, batch_size: int = 100) -> dict:
    """
    Importa solo registros nuevos en la tabla liq.
    Retorna estadísticas de la importación.
    """
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    
    if not rows:
        return {"total": 0, "nuevos": 0, "duplicados": 0, "errores": 0, "mensaje": "Sin filas para procesar"}
    
    # Obtener escrituras existentes
    existing = get_existing_escrituras("liq")
    
    # Separar registros nuevos de duplicados
    nuevos = []
    duplicados = 0
    
    for row in rows:
        escritura = row.get("escritura")
        if escritura and escritura in existing:
            duplicados += 1
        else:
            nuevos.append(row)
    
    # Insertar registros nuevos en lotes
    total_insertados = 0
    errores = 0
    
    for start in range(0, len(nuevos), batch_size):
        batch = nuevos[start : start + batch_size]
        try:
            result = supabase.table("liq").insert(batch).execute()
            total_insertados += len(batch)
        except Exception as e:
            print(f"[ERROR] Error al insertar lote: {e}")
            errores += len(batch)
    
    return {
        "total": len(rows),
        "nuevos": total_insertados,
        "duplicados": duplicados,
        "errores": errores,
        "mensaje": f"Importación completada: {total_insertados} nuevos, {duplicados} duplicados, {errores} errores"
    }

