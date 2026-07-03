import os
import re
import unicodedata
from types import SimpleNamespace
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


def check_table_exists(table_name: str) -> bool:
    """Verifica si una tabla existe en Supabase."""
    if not supabase:
        raise RuntimeError("Supabase client no configurado. Revisa SUPABASE_URL y SUPABASE_KEY en .env")
    try:
        supabase.table(table_name).select("id").limit(1).execute()
        return True
    except Exception as e:
        error_text = str(e).lower()
        if "does not exist" in error_text or "pgrst205" in error_text or "relation" in error_text:
            return False
        raise


def normalize_text(value):
    """Normaliza texto para comparaciones de forma consistente."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def normalize_escritura(escritura):
    """Normaliza valores de escritura para comparación y deduplicación."""
    valor = normalize_text(escritura)
    if not valor:
        return None
    value_without_separators = valor.replace(' ', '').replace('-', '').lower()
    if not value_without_separators:
        return None
    match = re.fullmatch(r"(?P<int_part>\d+)(?:\.(?P<decimal_part>0+))?", value_without_separators)
    if match:
        return str(int(match.group("int_part")))
    if value_without_separators.isdigit():
        return str(int(value_without_separators))
    return value_without_separators.replace('.', '')


def extract_escritura_from_filename(filename):
    """Extrae la escritura normalizada de un nombre de archivo."""
    if not filename:
        return None
    base = os.path.splitext(str(filename))[0]
    base = normalize_text(base).lower()
    match = re.match(r"^0*([0-9]+)", base)
    if match:
        return str(int(match.group(1)))
    return None


def normalize_estado_ctl_value(value):
    """Normaliza estados de estado_ctl para comparaciones exactas."""
    text = normalize_text(value)
    if not text:
        return ""
    lowered = text.lower()
    mapping = {
        "enviado": "Enviado",
        "send": "Enviado",
        "sent": "Enviado",
        "descargado": "Descargado",
        "downloaded": "Descargado",
        "pendiente": "Pendiente",
        "pending": "Pendiente",
        "notificado": "Notificado",
        "notificacion": "Notificado",
        "ingreso": "Ingreso",
        "ingresado": "Ingresado",
    }
    return mapping.get(lowered, text)


def normalize_notificacion_value(value):
    """Normaliza estados de notificación para comparaciones exactas."""
    text = normalize_text(value)
    if not text:
        return ""
    lowered = text.lower()
    mapping = {
        "enviado": "Enviado",
        "send": "Enviado",
        "sent": "Enviado",
        "notificado": "Enviado",
        "notificacion": "Enviado",
        "pendiente": "Pendiente",
        "pending": "Pendiente",
        "sin enviar": "Pendiente",
        "sin_enviar": "Pendiente",
        "no enviado": "Pendiente",
        "no_enviado": "Pendiente",
        "por enviar": "Pendiente",
        "por_enviar": "Pendiente",
        "pendiente por enviar": "Pendiente",
        "pendiente_por_enviar": "Pendiente",
    }
    return mapping.get(lowered, text)


def is_estado_enviado(value) -> bool:
    return normalize_estado_ctl_value(value) == "Enviado"


def is_row_pending_for_recibos(row: dict | None) -> bool:
    if not row:
        return False
    value = row.get("notificacion")
    if value is None:
        return True
    normalized = normalize_notificacion_value(value)
    if not normalized:
        return True
    return normalized == "Pendiente"


def is_row_pending_for_certificados(row: dict | None) -> bool:
    if not row:
        return False
    if not is_pago_ingresado(row.get("pago")):
        return False
    estado = normalize_estado_ctl_value(row.get("estado_ctl"))
    return estado not in {"Enviado", "Descargado"}


def is_notificacion_pendiente(value) -> bool:
    normalized = normalize_notificacion_value(value)
    if not normalized:
        return True
    return normalized == "Pendiente"


def is_pago_ingresado(value) -> bool:
    text = normalize_text(value).lower()
    return text in {"ingresado", "ingreso", "pagado", "yes", "si"}


MAX_PAGE_SIZE = 10000
MAX_PAGE_SIZE_WARN = 10000
ALLOWED_SORT_COLUMNS = {
    'escritura', 'nir', 'notificacion', 'pago', 'estado_ctl', 'gobernacion',
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


def _apply_pagination(query, page: int = 1, page_size: int = 10000):
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    page = max(1, page)
    if page_size and page > 0:
        start = (page - 1) * page_size
        end = start + page_size - 1
        return query.range(start, end)
    return query


def get_pending_liq(limit: int = 10000, page: int = 1, sort_by: str = 'escritura', desc: bool = False, require_estado_ctl_pending: bool = True):
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    page = max(1, page)
    """Obtiene filas pendientes usando una comparación robusta de estado y pago."""
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")

    res = supabase.table("liq").select("*").filter("notificacion", "ilike", "Pendiente").execute()
    rows = res.data or []
    if require_estado_ctl_pending:
        rows = [row for row in rows if not is_estado_enviado(row.get("estado_ctl"))]
    else:
        rows = [row for row in rows if is_row_pending_for_recibos(row)]

    if sort_by and sort_by in ALLOWED_SORT_COLUMNS:
        rows = sorted(rows, key=lambda row: row.get(sort_by) or "", reverse=desc)

    start = (page - 1) * limit
    end = start + limit
    return SimpleNamespace(data=rows[start:end], count=len(rows))


def get_pending_certificados_liq(limit: int = 10000, page: int = 1, sort_by: str = 'escritura', desc: bool = False):
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    page = max(1, page)
    """Obtiene filas pendientes de certificados usando Supabase como fuente principal."""
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")

    res = supabase.table("liq").select("*").execute()
    rows = res.data or []
    rows = [row for row in rows if is_row_pending_for_certificados(row)]

    if sort_by and sort_by in ALLOWED_SORT_COLUMNS:
        rows = sorted(rows, key=lambda row: row.get(sort_by) or "", reverse=desc)

    start = (page - 1) * limit
    end = start + limit
    return SimpleNamespace(data=rows[start:end], count=len(rows))

def update_liq_estado_by_escritura(escritura_str: str, nuevo_estado: str, activity_type: str = None):
    """
    Actualiza el estado de un registro en la tabla 'liq'.
    
    Args:
        escritura_str: Número de escritura
        nuevo_estado: Estado a asignar (usado si activity_type es None)
        activity_type: Tipo de actividad que determina qué estado asignar:
            - 'recibos': Cambia estado_ctl a 'Notificado'
            - 'pagos': Cambia estado_ctl a 'Ingreso'
            - 'cert_download': Cambia estado_ctl a 'Descargado'
            - 'cert_send': Mantiene estado (para envío de certificados)
            - None: Usa 'nuevo_estado' proporcionado
    """
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    
    estado_final = nuevo_estado
    
    if activity_type == 'notificacion':
        estado_final = 'Enviado'
    elif activity_type == 'pagos':
        estado_final = 'Ingreso'
    elif activity_type == 'cert_download':
        estado_final = 'Descargado'
    elif activity_type == 'cert_send':
        estado_final = 'Enviado'
    
    if activity_type == 'notificacion':
        field = 'notificacion'
        estado_final = 'Enviado'
    elif activity_type == 'pagos':
        field = 'pago'
        estado_final = 'Ingresado'
    elif activity_type == 'cert_download':
        field = 'estado_ctl'
        estado_final = 'Descargado'
    elif activity_type == 'cert_send':
        field = 'estado_ctl'
        estado_final = 'Enviado'
    else:
        field = 'notificacion'

    update_payload = {field: normalize_estado_ctl_value(estado_final) or estado_final}

    values_to_try = []
    normalized_escritura = normalize_escritura(escritura_str)
    if escritura_str is not None:
        values_to_try.append(escritura_str)
    if normalized_escritura is not None:
        values_to_try.append(normalized_escritura)
        try:
            values_to_try.append(int(normalized_escritura))
        except Exception:
            pass

    res = None
    for value in dict.fromkeys(values_to_try):
        for field_name in ("escritura", "escritura_str"):
            try:
                res = supabase.table("liq").update(update_payload).eq(field_name, value).execute()
                count = getattr(res, 'count', None)
                if (count is not None and count > 0) or (res.data and len(res.data) > 0):
                    break
            except Exception:
                continue
        if res and ((getattr(res, 'count', None) or 0) > 0 or (res.data and len(res.data) > 0)):
            break

    if res is None:
        res = supabase.table("liq").update(update_payload).eq("escritura_str", escritura_str).execute()

    if activity_type != 'cert_download':
        try:
            _check_and_move_if_complete(escritura_str)
        except Exception:
            pass
    return res


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

    skip_move = False
    if 'estado_ctl' in payload and normalize_estado_ctl_value(payload.get('estado_ctl')).lower() == 'descargado':
        skip_move = True

    if not skip_move:
        try:
            _check_and_move_if_complete(escritura_str)
        except Exception:
            pass
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
    total_res = supabase.table("liq").select("*", count="exact").execute()
    total = getattr(total_res, "count", None)
    if total is None:
        total = len(total_res.data or [])

    # pago ingresado (case-insensitive)
    pago_res = (
        supabase.table("liq").select("*", count="exact").filter("pago", "ilike", "Ingresado").execute()
    )
    pago_ingresado = getattr(pago_res, "count", None)
    if pago_ingresado is None:
        pago_ingresado = len(pago_res.data or [])

    pendientes_res = (
        supabase.table("liq")
        .select("*", count="exact")
        .filter("pago", "ilike", "Ingresado")
        .execute()
    )
    pendientes_rows = [row for row in (pendientes_res.data or []) if not is_estado_enviado(row.get("estado_ctl"))]
    pendientes = len(pendientes_rows)

    procesados_res = (
        supabase.table("liq")
        .select("*", count="exact")
        .filter("pago", "ilike", "Ingresado")
        .execute()
    )
    procesados = len([row for row in (procesados_res.data or []) if is_estado_enviado(row.get("estado_ctl"))])

    table_counts = {}
    for table_name in ['liq', 'liq_2025', 'liq_2026']:
        try:
            if check_table_exists(table_name):
                count_res = supabase.table(table_name).select('*', count='exact').execute()
                count = getattr(count_res, 'count', None)
                table_counts[table_name] = count if count is not None else len(count_res.data or [])
            else:
                table_counts[table_name] = 0
        except Exception:
            table_counts[table_name] = 0

    return {
        "total": total,
        "pago_ingresado": pago_ingresado,
        "pendientes": pendientes,
        "procesados": procesados,
        "table_counts": table_counts,
    }


def get_all_liq(limit: int = 10000, page: int = 1, sort_by: str = 'updated_at', desc: bool = True):
    """Devuelve todas las filas de `liq` con paginación y ordenación opcional."""
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    page = max(1, page)
    query = supabase.table("liq").select("*")
    query = _apply_sort(query, sort_by, desc)
    query = _apply_pagination(query, page, limit)
    return query.execute()


def get_processed_liq(limit: int = 10000, page: int = 1, sort_by: str = 'updated_at', desc: bool = True):
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


def get_existing_escrituras(table_name: str = "liq", select_cols: tuple = ("escritura", "escritura_str")) -> set:
    """Obtiene un conjunto de escrituras normalizadas para evitar duplicados por escritura."""
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    try:
        result = supabase.table(table_name).select(",".join(select_cols)).execute()
        existing = set()
        for row in result.data or []:
            for col in select_cols:
                if col in row and row[col] is not None:
                    norm = normalize_escritura(row[col])
                    if norm:
                        existing.add(norm)
        return existing
    except Exception as e:
        print(f"[WARNING] No se pudo obtener escrituras de {table_name}: {e}")
        return set()


def import_rows(rows: list, table_name: str, batch_size: int = 100, unique_cols: tuple = ("escritura", "escritura_str")) -> dict:
    """
    Función genérica para importar registros nuevos en cualquier tabla.
    Detecta duplicados usando normalización de escritura.
    Retorna estadísticas de la importación.
    """
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    
    if not rows:
        return {"total": 0, "nuevos": 0, "duplicados": 0, "errores": 0, "mensaje": "Sin filas para procesar"}

    # Obtener escrituras existentes con normalización
    existing = get_existing_escrituras(table_name, select_cols=unique_cols)
    
    # Separar registros nuevos de duplicados
    nuevos = []
    duplicados = 0
    
    for row in rows:
        escritura = row.get("escritura") or row.get("escritura_str")
        escritura_norm = normalize_escritura(escritura)
        if escritura_norm:
            row["escritura_str"] = escritura_norm
        if escritura_norm and escritura_norm in existing:
            duplicados += 1
            continue
        nuevos.append(row)

    # Insertar registros nuevos en lotes
    total_insertados = 0
    errores = 0
    
    for start in range(0, len(nuevos), batch_size):
        batch = nuevos[start : start + batch_size]
        try:
            supabase.table(table_name).insert(batch).execute()
            total_insertados += len(batch)
        except Exception as e:
            print(f"[ERROR] Error al insertar lote en {table_name}: {e}")
            errores += len(batch)

    return {
        "total": len(rows),
        "nuevos": total_insertados,
        "duplicados": duplicados,
        "errores": errores,
        "mensaje": f"Importación completada en {table_name}: {total_insertados} nuevos, {duplicados} duplicados, {errores} errores"
    }


def import_liq_from_rows(rows: list, batch_size: int = 100) -> dict:
    """
    Importa solo registros nuevos en la tabla liq.
    Retorna estadísticas de la importación.
    """
    return import_rows(rows, "liq", batch_size=batch_size)


def import_pagos_from_rows(rows: list, batch_size: int = 100) -> dict:
    """Importa solo registros nuevos en la tabla pagos_2026."""
    return import_rows(rows, "pagos_2026", batch_size=batch_size)


def import_pagos_consolidado_from_rows(rows: list, batch_size: int = 100) -> dict:
    """Importa solo registros nuevos en la tabla pagos_consolidado."""
    return import_rows(rows, "pagos_consolidado", batch_size=batch_size)


# ========================
# FUNCIONES PARA DESCARGAS
# ========================

def guardar_descarga(tipo: str, escritura: str, archivo_nombre: str, archivo_contenido: bytes, email: str = None):
    """
    Guarda un archivo descargado (certificado o recibo) en la tabla descargas.
    
    Args:
        tipo: 'recibo' o 'certificado'
        escritura: número de escritura
        archivo_nombre: nombre del archivo (ej: '12345.pdf')
        archivo_contenido: contenido del archivo en bytes
        email: email del destinatario (opcional)
    
    Returns:
        Resultado de la inserción
    """
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    
    if tipo not in ['recibo', 'certificado']:
        raise ValueError(f"Tipo inválido: {tipo}. Debe ser 'recibo' o 'certificado'")
    
    payload = {
        "tipo": tipo,
        "escritura": escritura,
        "archivo_nombre": archivo_nombre,
        "archivo_contenido": archivo_contenido,
        "email": email,
        "enviado": False,
    }
    
    return supabase.table("descargas").insert(payload).execute()


def obtener_descargas_por_escritura(escritura: str, tipo: str = None):
    """
    Obtiene todas las descargas para una escritura específica.
    
    Args:
        escritura: número de escritura
        tipo: 'recibo', 'certificado' o None (ambas)
    
    Returns:
        Lista de descargas
    """
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    
    query = supabase.table("descargas").select("*").eq("escritura", escritura)
    
    if tipo:
        query = query.eq("tipo", tipo)
    
    return query.execute()


def obtener_descargas_pendientes_de_envio(tipo: str = None, limit: int = 100):
    """
    Obtiene descargas que aún no han sido enviadas.
    
    Args:
        tipo: 'recibo', 'certificado' o None (ambas)
        limit: límite de resultados
    
    Returns:
        Lista de descargas pendientes
    """
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    
    query = supabase.table("descargas").select("*").eq("enviado", False).limit(limit)
    
    if tipo:
        query = query.eq("tipo", tipo)
    
    return query.execute()


def marcar_descarga_como_enviada(descarga_id: str):
    """
    Marca una descarga como enviada por correo.
    
    Args:
        descarga_id: UUID de la descarga
    
    Returns:
        Resultado de la actualización
    """
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    
    import datetime
    return supabase.table("descargas").update({
        "enviado": True,
        "fecha_envio": datetime.datetime.utcnow().isoformat()
    }).eq("id", descarga_id).execute()


def _get_row_by_escritura(table_name: str, escritura: str):
    """Obtiene una fila por `escritura` o `escritura_str` normalizada."""
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    escritura_norm = normalize_escritura(escritura)
    query = supabase.table(table_name).select("*")
    # Primero intenta por la columna original
    res = query.eq("escritura", escritura).limit(1).execute()
    if res.data:
        return res.data[0]
    # Luego por escritura_str normalizada
    if escritura_norm:
        res2 = supabase.table(table_name).select("*").eq("escritura_str", escritura_norm).limit(1).execute()
        if res2.data:
            return res2.data[0]
    return None


def _is_liq_row_complete(row: dict) -> bool:
    """Determina heurísticamente si una fila de `liq` está completa.

    Criterio (configurable aquí):
    - `notificacion` contiene 'enviado' o 'notificado'
    - `pago` contiene 'ingresado' o 'pagado'
    - `estado_ctl` es exactamente 'Enviado'
    """
    if not row:
        return False
    def _val(k):
        v = row.get(k)
        return (str(v).lower() if v is not None else "")

    notif = _val('notificacion')
    pago = _val('pago')
    estado_ctl = normalize_estado_ctl_value(row.get('estado_ctl')).lower()

    if 'enviado' not in notif and 'notificado' not in notif:
        return False
    if 'ingresado' not in pago and 'pagado' not in pago:
        return False
    if estado_ctl != 'enviado':
        return False
    return True


def move_liq_to_table(escritura: str, target_table: str):
    """Mueve (copia y borra) un registro de `liq` a `target_table`.

    Retorna el resultado de la inserción en la tabla destino.
    """
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    # verificar tabla destino
    if not check_table_exists(target_table):
        raise RuntimeError(f"Tabla destino no existe: {target_table}")

    row = _get_row_by_escritura('liq', escritura)
    if not row:
        raise RuntimeError(f"Registro con escritura {escritura} no encontrado en tabla liq")

    # Preparar payload para insertar (eliminar id si existe)
    payload = row.copy()
    payload.pop('id', None)

    # Añadir fecha_proceso si no existe
    import datetime
    payload.setdefault('fecha_proceso', datetime.datetime.utcnow().isoformat())

    # Insertar en la tabla destino
    res = supabase.table(target_table).insert(payload).execute()

    # Si se insertó correctamente, eliminar el original
    try:
        # obtener id original si quedó
        original_id = row.get('id')
        if original_id:
            supabase.table('liq').delete().eq('id', original_id).execute()
        else:
            # intentar borrar por escritura
            supabase.table('liq').delete().eq('escritura', escritura).execute()
    except Exception as e:
        print(f"[WARNING] No se pudo borrar registro original en liq: {e}")

    return res


def _check_and_move_if_complete(escritura: str, target_table: str = 'liq_2026'):
    """Chequea si un registro está completo y lo mueve a `target_table` si aplica."""
    try:
        row = _get_row_by_escritura('liq', escritura)
        if not row:
            return None
        if _is_liq_row_complete(row):
            return move_liq_to_table(escritura, target_table)
    except Exception as e:
        print(f"[WARNING] Error al verificar/mover escritura {escritura}: {e}")
    return None


def export_liq_to_excel(out_dir: str = None) -> str:
    """Exporta las tablas `liq`, `liq_2025` y `liq_2026` a un archivo Excel con varias hojas."""
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    try:
        import pandas as pd
        import tempfile
        from pathlib import Path

        def _fetch_table_df(name: str):
            if not check_table_exists(name):
                return pd.DataFrame()
            res = supabase.table(name).select('*').execute()
            rows = res.data or []
            df = pd.DataFrame(rows)
            if df.empty:
                return pd.DataFrame({'message': [f'No hay filas en tabla {name}']})
            return df

        sheets = {
            'liq': _fetch_table_df('liq'),
            'liq_2025': _fetch_table_df('liq_2025'),
            'liq_2026': _fetch_table_df('liq_2026'),
        }

        if out_dir:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx', dir=(out_dir or None))
        tmp.close()

        with pd.ExcelWriter(tmp.name, engine='openpyxl') as writer:
            for sheet_name, df in sheets.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)

        return tmp.name
    except Exception as e:
        raise RuntimeError(f"Error exportando las tablas liq a Excel: {e}")


def get_table_rows(table_name: str, limit: int = 1000, page: int = 1, sort_by: str = None, desc: bool = True):
    """Obtiene filas de cualquier tabla permitida con paginación mínima."""
    if not supabase:
        raise RuntimeError("Supabase client no configurado.")
    if not check_table_exists(table_name):
        raise RuntimeError(f"Tabla no existe: {table_name}")
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    page = max(1, page)
    query = supabase.table(table_name).select("*")
    if sort_by:
        try:
            query = query.order(sort_by, desc=desc)
        except Exception:
            pass
    start = (page - 1) * limit
    end = start + limit - 1
    query = query.range(start, end)
    return query.execute()


