# -*- coding: utf-8 -*-
"""
certificados_supabase.py

Conversión de certificados.py para usar Supabase como fuente principal de datos.

CAMBIO PRINCIPAL:
- ANTES: leía Informe.xlsx y filtraba localmente.
- AHORA: consulta la tabla `liq` en Supabase y usa esa data como verdad.
- EXTRA: puede exportar una copia de respaldo a Excel al final del día.

Uso:
    python certificados_supabase.py
    python certificados_supabase.py --exportar-excel
    python certificados_supabase.py --solo-listar

Requisitos:
    - .env configurado con SUPABASE_URL y SUPABASE_KEY (usado por supabase_client.get_supabase)
    - Tabla 'liq' en Supabase con columnas mínimas: escritura, nir, estado_ctl, pago
    - (Opcional) funciones del módulo supabase_client para registrar descargas o logs

NOTA IMPORTANTE:
Este archivo migra COMPLETAMENTE la capa de lectura/validación desde Excel hacia Supabase.
La automatización Selenium se deja lista para integrarse en `procesar_una_escritura()`.
Si ya tienes selectores y lógica de descarga en tu certificados.py original, puedes pegarlos ahí.
"""
import os, subprocess, re, time, hashlib, sys
import argparse
import pandas as pd

from urllib.parse import quote_plus
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver import ActionChains
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    SessionNotCreatedException,
    StaleElementReferenceException,
)
from supabase_client import (
    insert_certificado,
    insert_log,
    update_liq_estado_by_escritura,
    guardar_descarga,
    normalize_estado_ctl_value,
    is_estado_enviado,
    is_pago_ingresado,
    is_row_pending_for_certificados,
    get_pending_certificados_liq,
)


# Selenium

from supabase import ClientOptions, create_client, Client

# =========================
# CONFIG
# =========================
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_FOLDER = os.path.join(APP_DIR, "descargas", "certificados")
DRIVER_PATH = os.path.join(APP_DIR, "drivers", "msedgedriver.exe")
BACKUP_DIR = os.path.join(APP_DIR, "backups")
TABLE_NAME = "liq"
WAIT_SECONDS = 20

os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    # fall back to empty client placeholder to avoid crashes during import
    supabase: Client | None = None
else:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_supabase() -> Client:
    return supabase

def create_client(
    supabase_url: str,
    supabase_key: str,
    options: Optional[ClientOptions] = None,
) -> Client:
    """Create client function to instantiate supabase client like JS runtime.

    Parameters
    ----------
    supabase_url: str
        The URL to the Supabase instance that should be connected to.
    supabase_key: str
        The API key to the Supabase instance that should be connected to.
    **options
        Any extra settings to be optionally specified - also see the
        `DEFAULT_OPTIONS` dict.

    Examples
    --------
    Instantiating the client.
    >>> import os
    >>> from supabase import create_client, Client
    >>>
    >>> url: str = os.environ.get("SUPABASE_TEST_URL")
    >>> key: str = os.environ.get("SUPABASE_TEST_KEY")
    >>> supabase: Client = create_client(url, key)

    Returns
    -------
    Client
    """
    return Client.create(
        supabase_url=supabase_url, supabase_key=supabase_key, options=options
    )
# =========================
# HELPERS GENERALES
# =========================
def log(msg: str) -> None:
    print(msg, flush=True)


def normalizar_texto(valor: Any) -> str:
    if valor is None:
        return ""
    txt = str(valor).strip()
    if txt.lower() == "nan":
        return ""
    return txt


def normalizar_numero_excel(valor: Any) -> str:
    txt = normalizar_texto(valor)
    return txt[:-2] if txt.endswith(".0") else txt


def preparar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace("á", "a")
        .str.replace("é", "e")
        .str.replace("í", "i")
        .str.replace("ó", "o")
        .str.replace("ú", "u")
        .str.replace("\n", " ")
        .str.replace("\r", "")
    )

    # Normalizaciones defensivas
    for col in ["estado_ctl", "pago", "escritura", "nir", "notificacion"]:
        if col not in df.columns:
            df[col] = ""

    df["estado_ctl"] = df["estado_ctl"].fillna("").astype(str).str.strip().str.lower()
    df["notificacion"] = df["notificacion"].fillna("").astype(str).str.strip().str.lower()
    df["pago"] = df["pago"].fillna("").astype(str).str.strip().str.lower()
    df["escritura_str"] = df["escritura"].apply(normalizar_numero_excel)
    df["nir_str"] = df["nir"].apply(normalizar_numero_excel)
    return df


# =========================
# SUPABASE
# =========================
def get_supabase_client():
    supabase = get_supabase()
    if not supabase:
        raise RuntimeError(
            "No se pudo crear el cliente de Supabase. Revisa SUPABASE_URL y SUPABASE_KEY en tu .env"
        )
    return supabase


def obtener_registros_desde_supabase() -> pd.DataFrame:
    """
    Trae datos desde Supabase y hace el filtro en pandas para ser más robusto
    frente a mayúsculas/minúsculas y valores inconsistentes.
    """
    supabase = get_supabase_client()
    result = supabase.table(TABLE_NAME).select("*").execute()
    data = result.data or []
    df = pd.DataFrame(data)
    df = preparar_dataframe(df)
    return df


def obtener_pendientes_desde_supabase() -> pd.DataFrame:
    """
    Reemplaza completamente el viejo filtro desde Excel.
    ANTES:
        (estado_ctl != 'enviado') and (pago == 'ingresado')
    AHORA:
        mismo criterio pero leyendo desde Supabase.
    """
    df = obtener_registros_desde_supabase()
    if df.empty:
        return df

    filtro = (
        (df["estado_ctl"] != "enviado")
        & (df["pago"] == "ingresado")
        & (df["escritura_str"] != "")
        & (df["nir_str"] != "")
    )
    return df.loc[filtro].copy()


def actualizar_estado_liq(escritura: str, nuevo_estado: str) -> None:
    supabase = get_supabase_client()
    supabase.table(TABLE_NAME).update({"estado_ctl": nuevo_estado}).eq("escritura", escritura).execute()


def registrar_error_liq(escritura: str, mensaje_error: str) -> None:
    """
    Si tu tabla tiene columna error_detalle, la llena.
    Si no existe, el try evita romper el proceso.
    """
    try:
        supabase = get_supabase_client()
        supabase.table(TABLE_NAME).update({
            "estado_ctl": "error",
            "error_detalle": mensaje_error[:400],
        }).eq("escritura", escritura).execute()
    except Exception:
        pass


def registrar_descarga(escritura: str, nir: str, nombre_archivo: str, ruta_archivo: str) -> None:
    """
    Registra metadatos en una tabla de descargas si existe.
    Si la tabla/columnas no existen, no rompe el flujo.
    """
    try:
        supabase = get_supabase_client()
        payload = {
            "escritura": escritura,
            "nir": nir,
            "archivo": nombre_archivo,
            "ruta_local": ruta_archivo,
            "tipo": "certificado",
            "fecha_registro": datetime.now().isoformat(),
        }
        supabase.table("descargas").insert(payload).execute()
    except Exception:
        pass


def exportar_backup_excel(nombre_archivo: Optional[str] = None) -> str:
    df = obtener_registros_desde_supabase()
    if nombre_archivo is None:
        fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_archivo = f"backup_liq_{fecha}.xlsx"
    output_path = os.path.join(BACKUP_DIR, nombre_archivo)
    df.to_excel(output_path, index=False, engine="openpyxl")
    return output_path


# =========================
# ARCHIVOS LOCALES
# =========================
def obtener_escrituras_descargadas(carpeta: str) -> set:
    descargadas = set()
    if not os.path.exists(carpeta):
        return descargadas

    for archivo in os.listdir(carpeta):
        nombre_sin_ext = os.path.splitext(archivo)[0]
        escritura = nombre_sin_ext.split('_')[0] if '_' in nombre_sin_ext else nombre_sin_ext.split(' ')[0]
        if escritura:
            descargadas.add(escritura)
    return descargadas


def esperar_descarga_pdf(carpeta: str, started_at: float, timeout: int = 120) -> Optional[str]:
    """Espera un PDF nuevo/actualizado después de started_at."""
    fin = time.time() + timeout
    while time.time() < fin:
        candidatos = []
        for f in os.listdir(carpeta):
            path = os.path.join(carpeta, f)
            if not os.path.isfile(path):
                continue
            if not f.lower().endswith(".pdf"):
                continue
            if os.path.getmtime(path) >= started_at:
                candidatos.append(path)
        if candidatos:
            candidatos.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            return candidatos[0]
        time.sleep(1)
    return None


# =========================
# SELENIUM / EDGE
# =========================
def obtener_version_edge() -> Optional[str]:
    posibles_rutas = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for ruta in posibles_rutas:
        if os.path.isfile(ruta):
            return ruta
    return None


def crear_driver() -> webdriver.Edge:
    edge_options = Options()
    edge_options.use_chromium = True
    edge_options.add_argument("--disable-gpu")
    edge_options.add_argument("--no-sandbox")
    edge_options.add_argument("--headless=new")
    edge_options.add_argument("--disable-blink-features=AutomationControlled")
    prefs = {
        "download.default_directory": DOWNLOAD_FOLDER,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "profile.managed_default_content_settings.pdfs": 2,
        "pdfjs.disabled": True,
        "safebrowsing.enabled": False,
        "profile.default_content_settings.popups": 0,
    }
    edge_options.add_experimental_option("prefs", prefs)
    edge_options.add_experimental_option("useAutomationExtension", False)

    service = Service(DRIVER_PATH) if os.path.isfile(DRIVER_PATH) else None
    if service:
        driver = webdriver.Edge(service=service, options=edge_options)
    else:
        driver = webdriver.Edge(options=edge_options)
    return driver


# =========================
# PROCESO DE DESCARGA
# =========================
def buscar_y_descargar_certificado(driver: webdriver.Edge, wait: WebDriverWait, escritura: str, nir: str) -> List[str]:
    """
    Aquí debes conservar o pegar la lógica Selenium específica de tu portal.

    Este método devuelve la lista de archivos descargados para una escritura.
    Para no romper tu aprendizaje, te dejo una versión-base segura:
    - abre el portal que ya uses
    - espera descarga
    - renombra archivo si quieres

    Si ya tenías selectores funcionando en certificados.py, pégalos aquí.
    """

    # ===== EJEMPLO BASE / PLANTILLA =====
    # Reemplaza esta URL por la del portal donde consultas certificados.
    # driver.get("https://TU_PORTAL_CERTIFICADOS")
    # ... aquí irían tus send_keys / clicks / búsqueda por escritura o NIR ...
    
    """
    Busca certificados por NIR y descarga los archivos asociados.
    Regresa una lista con las rutas completas descargadas.
    """

    log(f"[INFO] Abriendo portal de radicación...")
    driver.get("https://radicacion.supernotariado.gov.co/app/inicio.dma")

    log("[INFO] Buscando menú 'Certificados'...")
    wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Certificados"))).click()
    time.sleep(2)

    log(f"[INFO] Ingresando NIR: {nir}")
    input_nir = wait.until(EC.presence_of_element_located((By.ID, "formSearch:j_idt44")))
    input_nir.clear()
    input_nir.send_keys(nir)

    log("[INFO] Ejecutando búsqueda...")
    boton_buscar = wait.until(EC.element_to_be_clickable((By.ID, "formSearch:j_idt45")))
    boton_buscar.click()
    time.sleep(3)

    log("[INFO] Descargando archivos...")
    archivos_descargados = descargar_multiples_archivos(driver, wait, escritura)

    if not archivos_descargados:
        raise RuntimeError(f"No se descargó ningún archivo para la escritura {escritura}")

    rutas_finales = []

    for fname in archivos_descargados:
        # Si descargar_multiples_archivos ya regresa ruta completa, úsala tal cual
        if os.path.isabs(fname):
            ruta_archivo = fname
        else:
            ruta_archivo = os.path.join(DOWNLOAD_FOLDER, fname)

        if not os.path.exists(ruta_archivo):
            log(f"[WARN] El archivo reportado no existe: {ruta_archivo}")
            continue

        rutas_finales.append(ruta_archivo)

    if not rutas_finales:
        raise RuntimeError(f"Se reportaron descargas, pero no se encontraron archivos válidos para {escritura}")

    log(f"[OK] Se descargaron {len(rutas_finales)} archivo(s) para escritura {escritura}")
    return rutas_finales


    # =====================================================
    # IMPORTANTE:
    # Si pegas tu lógica original, asegúrate de dejar `started_at = time.time()`
    # justo antes del clic que dispara la descarga.
    # =====================================================

    archivo_descargado = esperar_descarga_pdf(DOWNLOAD_FOLDER, started_at, timeout=120)
    if not archivo_descargado:
        raise RuntimeError("No se detectó ninguna descarga PDF para esta escritura")

    nombre_final = f"{escritura}_{nir}.pdf"
    destino = os.path.join(DOWNLOAD_FOLDER, nombre_final)

    # Si el nombre final ya existe, genera sufijo para no pisarlo
    if os.path.exists(destino):
        base, ext = os.path.splitext(destino)
        i = 2
        while os.path.exists(f"{base}_{i}{ext}"):
            i += 1
        destino = f"{base}_{i}{ext}"

    if os.path.abspath(archivo_descargado) != os.path.abspath(destino):
        os.replace(archivo_descargado, destino)

    return [destino]


def procesar_una_escritura(driver: webdriver.Edge, wait: WebDriverWait, row: pd.Series) -> bool:
    escritura = normalizar_numero_excel(row.get("escritura"))
    nir = normalizar_numero_excel(row.get("nir"))

    if not escritura or not nir:
        log(f"[SKIP] Registro inválido. escritura='{escritura}' nir='{nir}'")
        return False

    try:
        log(f"[INFO] Procesando escritura={escritura} | nir={nir}")

        archivos_generados = buscar_y_descargar_certificado(driver, wait, escritura, nir)

        for archivo in archivos_generados:
            registrar_descarga(
                escritura=escritura,
                nir=nir,
                nombre_archivo=os.path.basename(archivo),
                ruta_archivo=archivo,
            )

        actualizar_estado_liq(escritura, "descargado")
        log(f"[OK] Escritura {escritura} marcada como descargado en Supabase")

        return True

    except Exception as e:
        msg = str(e)
        registrar_error_liq(escritura, msg)
        log(f"[ERROR] Escritura {escritura}: {msg}")
        return False

def descargar_multiples_archivos(driver, wait, escritura, timeout=120):
    """
    Busca y descarga TODOS los archivos disponibles para una escritura.
    Retorna una lista con los nombres de archivos descargados.
    """
    archivos_descargados = []
    
    print(f"[INFO] Buscando botones de descarga...")
    time.sleep(1)
    
    # Buscar todos los links de descarga (puede haber varios)
    try:
        botones_descarga = driver.find_elements(By.LINK_TEXT, "Descargar")
        if not botones_descarga:
            print(f"[INFO] Saltando")
            return archivos_descargados
        
        print(f"[INFO] Se encontraron {len(botones_descarga)} archivo(s) para descargar")
        
        # Procesar cada botón de descarga
        for idx, boton in enumerate(botones_descarga, 1):
            try:
                print(f"[INFO] Descargando archivo {idx}/{len(botones_descarga)}...")
                
                # Hacer scroll al botón para asegurarse que está visible
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", boton)
                time.sleep(0.5)
                
                # Registrar tiempo para detectar archivo nuevo
                click_time = time.time()
                
                # Intentar click robusto
                try:
                    driver.execute_script("arguments[0].click();", boton)
                except StaleElementReferenceException:
                    botones_descarga = driver.find_elements(By.LINK_TEXT, "Descargar")
                    if len(botones_descarga) > idx:
                        boton = botones_descarga[idx]
                        driver.execute_script("arguments[0].click();", boton)
                    else:
                        raise
                except Exception:
                    try:
                        boton.click()
                    except StaleElementReferenceException:
                        botones_descarga = driver.find_elements(By.LINK_TEXT, "Descargar")
                        if len(botones_descarga) > idx:
                            boton = botones_descarga[idx]
                            boton.click()
                        else:
                            raise
                        ActionChains(driver).move_to_element(boton).click().perform()
                
                time.sleep(1)
                
                # Esperar descarga y renombrar
                archivo_final = f"{escritura} Certificado_{idx}.pdf"
                exito = esperar_descarga_y_renombrar(archivo_final, started_at=click_time, timeout=60)
                
                if exito:
                    archivos_descargados.append(archivo_final)
                    print(f"[INFO] Descargado: {archivo_final}")
                else:
                    print(f"[ERROR] Error descargando archivo {idx}")
                
                time.sleep(0.5)  # Pequeña pausa entre descargas
                
            except Exception as e:
                print(f"[ERROR] Error en descarga {idx}: {str(e)[:50]}")
                continue
    
    except Exception as e:
        print(f"[ERROR] Error buscando botones de descarga: {str(e)[:100]}")
    
    return archivos_descargados

def esperar_descarga_y_renombrar(nombre_final, started_at, timeout=60):
    """
    Espera un archivo descargado (pdf o crdownload) creado/modificado después de started_at,
    espera a que termine y lo renombra con retry.
    """
    if not nombre_final.lower().endswith(".pdf"):
        nombre_final += ".pdf"

    t0 = time.time()
    candidato = None

    # 1) Esperar a que aparezca algo nuevo/modificado tras started_at
    while time.time() - t0 < timeout:
        archivos = []
        for f in os.listdir(DOWNLOAD_FOLDER):
            ruta = os.path.join(DOWNLOAD_FOLDER, f)
            if not os.path.isfile(ruta):
                continue
            try:
                m = os.path.getmtime(ruta)
            except OSError:
                continue

            # Archivos tocados después del click
            if m >= started_at - 0.2:  # pequeño margen
                archivos.append(ruta)

        if archivos:
            # el más reciente por mtime
            candidato = max(archivos, key=lambda p: os.path.getmtime(p))
            break

        time.sleep(0.2)

    if not candidato:
        print("[ERROR] No apareció ningún archivo nuevo/modificado tras el click.")
        return False

    # 2) Si es crdownload, esperar a que desaparezca y exista el final
    t1 = time.time()
    while time.time() - t1 < timeout:
        if candidato.lower().endswith(".crdownload"):
            posible_final = candidato[:-11]  # quita ".crdownload"
            if os.path.exists(posible_final) and not os.path.exists(candidato):
                candidato = posible_final
                break
        else:
            # esperar a que no haya crdownload en la carpeta
            if not any(x.lower().endswith(".crdownload") for x in os.listdir(DOWNLOAD_FOLDER)):
                break
        time.sleep(0.3)

    # 3) Esperar estabilidad de tamaño
    last = -1
    estable = 0
    t2 = time.time()
    while time.time() - t2 < timeout:
        if not os.path.exists(candidato):
            time.sleep(0.2)
            continue
        try:
            s = os.path.getsize(candidato)
        except OSError:
            time.sleep(0.2)
            continue

        if s == last and s > 1000:
            estable += 1
        else:
            estable = 0
            last = s

        if estable >= 4:  # ~0.8s estable
            break

        time.sleep(0.2)

    if estable < 4:
        print("[ERROR] El archivo no estabilizó tamaño; puede seguir escribiéndose.")
        return False

    # 4) Renombrar con retry (por bloqueo)
    destino = os.path.join(DOWNLOAD_FOLDER, nombre_final)
    if os.path.abspath(candidato) == os.path.abspath(destino):
        print(f"[INFO] Ya estaba con el nombre: {nombre_final}")
        return True

    # Calcular hash del candidato para deduplicación
    def file_hash(path, block_size=65536):
        h = hashlib.sha256()
        try:
            with open(path, 'rb') as f:
                for block in iter(lambda: f.read(block_size), b''):
                    h.update(block)
            return h.hexdigest()
        except Exception:
            return None

    candidato_hash = file_hash(candidato)
    if candidato_hash:
        # Buscar si ya existe un archivo con mismo hash en la carpeta
        for f in os.listdir(DOWNLOAD_FOLDER):
            existing = os.path.join(DOWNLOAD_FOLDER, f)
            if os.path.abspath(existing) == os.path.abspath(candidato):
                continue
            if not os.path.isfile(existing):
                continue
            # Sólo comparar con PDF (u otros) que puedan ser equivalentes
            if existing.lower().endswith(('.pdf', '.txt', '.doc', '.docx')):
                h2 = file_hash(existing)
                if h2 and h2 == candidato_hash:
                    print(f"[INFO] Archivo duplicado detectado (hash): {os.path.basename(existing)} == {os.path.basename(candidato)}")
                    # Eliminar candidato temporal y reportar éxito
                    try:
                        os.remove(candidato)
                    except Exception:
                        pass
                    return True

    # si destino existe, comparar hashes

    # si existe, comparar hashes con el destino actual
    if os.path.exists(destino):
        try:
            dest_hash = None
            try:
                with open(destino, 'rb') as f:
                    d_h = hashlib.sha256()
                    for block in iter(lambda: f.read(65536), b''):
                        d_h.update(block)
                    dest_hash = d_h.hexdigest()
            except Exception:
                dest_hash = None

            if candidato_hash and dest_hash and candidato_hash == dest_hash:
                print(f"[INFO] El archivo destino ya existe y tiene mismo contenido: {os.path.basename(destino)}")
                try:
                    os.remove(candidato)
                except Exception:
                    pass
                return True
        except Exception:
            pass

        # mantener sufijo si no son iguales
        base, ext = os.path.splitext(destino)
        i = 1
        while os.path.exists(f"{base}_{i}{ext}"):
            i += 1
        destino = f"{base}_{i}{ext}"

    for _ in range(15):
        try:
            os.replace(candidato, destino)  # mejor que os.rename en Windows
            print(f"[INFO] Renombrado a: {os.path.basename(destino)} ({os.path.getsize(destino)} bytes)")
            return True
        except PermissionError:
            time.sleep(0.2)
        except Exception as e:
            print(f"[ERROR] Error renombrando: {e}")
            return False

    print("[ERROR] No se pudo renombrar por bloqueo del archivo (PermissionError).")
    return False
# =========================
# MAIN
# =========================
def main():
    parser = argparse.ArgumentParser(description="Descarga certificados usando Supabase como fuente principal")
    parser.add_argument("--solo-listar", action="store_true", help="Solo muestra pendientes y no descarga")
    parser.add_argument("--exportar-excel", action="store_true", help="Exporta un backup Excel desde Supabase y termina")
    args = parser.parse_args()

    if args.exportar_excel:
        ruta = exportar_backup_excel()
        log(f"[OK] Backup Excel generado: {ruta}")
        return

    # 1) Traer pendientes solo desde Supabase
    df_pendientes = obtener_pendientes_desde_supabase()

    if df_pendientes.empty:
        log("[INFO] No hay pendientes en Supabase")
        return

    # 2) Excluir lo que ya existe en carpeta local para evitar redescargas accidentales
    escrituras_descargadas = obtener_escrituras_descargadas(DOWNLOAD_FOLDER)
    antes = len(df_pendientes)
    df_pendientes = df_pendientes[~df_pendientes["escritura_str"].isin(escrituras_descargadas)].copy()
    omitidas = antes - len(df_pendientes)
    if omitidas:
        log(f"[INFO] Se omitieron {omitidas} escrituras porque ya hay PDFs en la carpeta local")

    if df_pendientes.empty:
        log("[INFO] No hay pendientes nuevos por procesar")
        return

    log("=========================================")
    log(f"[READY] Pendientes desde Supabase: {len(df_pendientes)}")
    log("=========================================")

    if args.solo_listar:
        columnas = [c for c in ["escritura", "nir", "estado_ctl", "pago"] if c in df_pendientes.columns]
        print(df_pendientes[columnas].head(50).to_string(index=False))
        return

    # 3) Driver / Selenium
    driver = None
    procesados = 0
    errores = 0

    try:
        driver = crear_driver()
        wait = WebDriverWait(driver, WAIT_SECONDS)

        for _, row in df_pendientes.iterrows():
            ok = procesar_una_escritura(driver, wait, row)
            if ok:
                procesados += 1
            else:
                errores += 1

    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    log("=========================================")
    log(f"[FIN] Procesados OK: {procesados}")
    log(f"[FIN] Con error    : {errores}")
    log("=========================================")


if __name__ == "__main__":
    main()
