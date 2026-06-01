# envio_recibos main script
from csv import writer
from operator import le
import re
import os
import time
import pandas as pd
import warnings
from urllib.parse import quote_plus
import unicodedata
import tempfile
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import sys
from supabase_client import insert_recibo, update_certificado_estado, insert_log, get_supabase, update_liq_estado_by_escritura, guardar_descarga

warnings.filterwarnings("ignore")

# =========================
# CONFIG
# =========================
APP_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_XLSX = os.path.join(APP_DIR, "Informe.xlsx")
CARPETA_PDFS = os.path.join(APP_DIR, "descargas", "recibos")

# Crear carpeta de descargas si no existe
os.makedirs(CARPETA_PDFS, exist_ok=True)

EDGE_USER_DATA_DIR = os.path.expanduser(r"~\AppData\Local\Microsoft\Edge\User Data")
EDGE_PROFILE_DIR = "Default"
REL = r"https://radicacion.supernotariado.gov.co/app/inicio.dma"
DESTINATARIO_DEFAULT = "pruebas@ejemplo.com"
WAIT_SECONDS = 25

# =========================
# EDGE (Jupyter-safe)
# =========================
_DRIVER = None

def crear_edge_sin_sesion(download_path: str, headless: bool, wait_seconds: int):
    os.makedirs(download_path, exist_ok=True)

    options = EdgeOptions()
    options.use_chromium = True

    tmp_profile = tempfile.mkdtemp(prefix="edge_streamlit_")
    options.add_argument(f"--user-data-dir={tmp_profile}")    

    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
    else:
        options.add_argument("--start-maximized")

    options.add_argument("--disable-notifications")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    prefs = {
        "download.default_directory": download_path,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "profile.default_content_settings.popups": 0,
        "plugins.always_open_pdf_externally": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)

    service = EdgeService()
    driver = webdriver.Edge(service=service, options=options)

    try:
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": download_path
        })
    except Exception:
        pass

    wait = WebDriverWait(driver, wait_seconds)
    return driver, wait

def _kill_edge_processes():
    os.system("taskkill /F /IM msedge.exe >nul 2>&1")
    os.system("taskkill /F /IM msedgedriver.exe >nul 2>&1")

def get_edge_driver(carpeta_pdfs, user_data_dir, profile_dir="Default"):
    global _DRIVER
    try:
        if _DRIVER is not None:
            _DRIVER.quit()
    except Exception:
        pass
    _DRIVER = None

    _kill_edge_processes()
    time.sleep(1)

    options = EdgeOptions()
    options.use_chromium = True
    options.add_argument("--disable-notifications")
    options.add_argument("--no-first-run")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    options.add_argument("--log-level=3")
    options.add_argument("--headless=new")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--remote-debugging-port=0")
    options.add_argument(f"--user-data-dir={user_data_dir}")
    options.add_argument(f"--profile-directory={profile_dir}")

    prefs = {
        "download.default_directory": carpeta_pdfs,
        "download.prompt_for_download": False,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)

    service = EdgeService()
    _DRIVER = webdriver.Edge(service=service, options=options)
    return _DRIVER

# =========================
# EXCEL
# =========================
def preparar_excel(df):
    df.columns = (
        df.columns.astype(str).str.strip().str.lower()
        .str.replace("á", "a").str.replace("é", "e").str.replace("í", "i")
        .str.replace("ó", "o").str.replace("ú", "u").str.replace("\n", " ").str.replace("\r", "")
    )

    col_correo = next((c for c in df.columns if "correo" in c or "email" in c or "e-mail" in c), None)
    if col_correo and col_correo != "correo":
        df.rename(columns={col_correo: "correo"}, inplace=True)
    elif "correo" not in df.columns:
        df["correo"] = ""

    col_gob = next((c for c in df.columns if "gobernacion" in c or "gobern" in c or "entidad" in c), None)
    if col_gob and col_gob != "gobernacion":
        df.rename(columns={col_gob: "gobernacion"}, inplace=True)
    elif "gobernacion" not in df.columns:
        df["gobernacion"] = ""       

    if "gobernacion" in df.columns:
        df["gobernacion"] = df["gobernacion"].fillna("").astype(str).str.strip()
    if "correo" in df.columns:
        df["correo"] = df["correo"].fillna("").astype(str).str.strip()
    if "gobernacion" in df.columns:
        df["gobernacion"] = df["gobernacion"].fillna("").astype(str).str.strip()
    
    return df

def cargar_excel(ruta_xlsx):
    xls = pd.ExcelFile(ruta_xlsx)
    hoja = "Liq." if "Liq." in xls.sheet_names else xls.sheet_names[0]

    raw = pd.read_excel(xls, sheet_name=hoja, header=None, dtype=str)

    header_row = None
    for i in range(len(raw)):
        if raw.iloc[i].astype(str).str.contains("Escritura", case=False, na=False).any():
            header_row = i
            break
    if header_row is None:
        raise KeyError("No se encontró la fila de encabezados con 'Escritura'")

    df = pd.read_excel(xls, sheet_name=hoja, header=header_row, dtype=str)
    df.columns = df.columns.astype(str).str.strip()

    col_escritura = next(c for c in df.columns if "escritura" in c.lower().replace(" ", ""))
    df["escritura_str"] = (
        pd.to_numeric(df[col_escritura], errors="coerce")
        .fillna(0).astype(int).astype(str)
    )
    return df, hoja

def obtener_escrituras_con_pdf(carpeta):
    s = set()
    for f in os.listdir(carpeta):
        if f.lower().endswith(".pdf"):
            base = os.path.splitext(f)[0]
            esc = base.split("_")[0].split(" ")[0]
            if esc.isdigit():
                s.add(esc)
    return s

def preparar_listos_para_enviar(df, carpeta_pdfs):
    if "notificacion" in df.columns:
        mask_pend = df["notificacion"].astype(str).str.strip().str.lower() == "pendiente"
    else:
        mask_pend = pd.Series([True] * len(df), index=df.index)

    con_pdf = obtener_escrituras_con_pdf(carpeta_pdfs)
    mask_pdf = df["escritura_str"].isin(con_pdf)

    return df[mask_pend & mask_pdf].copy()

def buscar_pdf_en_carpeta(carpeta, escritura):
    """Busca el primer PDF asociado a una escritura (compatibilidad hacia atrás)"""
    pdfs = buscar_pdfs_en_carpeta(carpeta, escritura)
    return pdfs[0] if pdfs else None


def buscar_pdfs_en_carpeta(carpeta, escritura):
    """Busca TODOS los archivos (PDF, DOC, DOCX) asociados a una escritura"""
    escritura = str(escritura).strip()
    patron = re.compile(rf"^{re.escape(escritura)}(\D|$)", re.IGNORECASE)
    
    archivos = []
    extensiones_validas = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".jpg", ".png")

    for f in os.listdir(carpeta):
        if not f.lower().endswith(extensiones_validas):
            continue
        base = os.path.splitext(f)[0]
        if patron.search(base):
            archivos.append(os.path.join(carpeta, f))
    
    return sorted(archivos)  # Ordenar para consistencia

# =========================
# GMAIL
# =========================
def abrir_compose_prefill(driver, correo, asunto, cuerpo):
    url = (
        "https://mail.google.com/mail/u/0/?tf=cm"
        f"&to={quote_plus(correo)}"
        f"&su={quote_plus(asunto)}"
        f"&body={quote_plus(cuerpo)}"
    )
    driver.get(url)

def adjuntar_pdf_en_compose(driver, wait, ruta_pdf):
    """Adjunta un ÚNICO archivo (compatibilidad hacia atrás)"""
    adjuntar_multiples_pdfs_en_compose(driver, wait, [ruta_pdf])


def adjuntar_multiples_pdfs_en_compose(driver, wait, rutas_archivos):
    """Adjunta MÚLTIPLES archivos en el compose de Gmail"""
    if not rutas_archivos:
        return
    
    # Buscar el input de archivo
    file_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']")))
    
    # Adjuntar cada archivo
    for ruta_archivo in rutas_archivos:
        try:
            nombre = os.path.basename(ruta_archivo)
            file_input.send_keys(ruta_archivo)
            
            # Esperar a que aparezca en el DOM
            try:
                wait.until(lambda d: nombre in d.page_source, timeout=10)
            except:
                pass
            
            print(f"[INFO] Adjuntado: {nombre}")
            time.sleep(0.5)  # Pequeña pausa entre adjuntos
        except Exception as e:
            print(f"[WARNING] No se pudo adjuntar {os.path.basename(ruta_archivo)}: {e}")

def cerrar_borrador(driver, wait):
    try:
        btn = WebDriverWait(driver, 6).until(
            EC.presence_of_element_located(
                (By.XPATH, "//*[@aria-label='Guardar y cerrar' or @aria-label='Save & close']")
            )
        )
        driver.execute_script("arguments[0].click();", btn)
        return True
    except Exception:
        driver.get("https://mail.google.com/mail/u/0/#inbox")
        return False

def crear_borrador_con_adjunto(driver, wait, correo, asunto, cuerpo, ruta_pdf):
    """Crea borrador con UN único archivo (compatibilidad hacia atrás)"""
    crear_borrador_con_multiples_adjuntos(driver, wait, correo, asunto, cuerpo, [ruta_pdf])

def crear_borrador_con_multiples_adjuntos(driver, wait, correo, asunto, cuerpo, rutas_archivos):
    """Crea borrador con MÚLTIPLES archivos adjuntos"""
    abrir_compose_prefill(driver, correo, asunto, cuerpo)
    adjuntar_multiples_pdfs_en_compose(driver, wait, rutas_archivos)
    time.sleep(1.2)
    cerrar_borrador(driver, wait)

def process_single_recibo(payload: dict):
    """Crea un borrador para un único recibo a partir de payload JSON.
    payload keys: escritura, nir, correo, gobernacion, documentos (list of filenames), asunto, cuerpo
    """
    escritura = str(payload.get('escritura') or '')
    correo = payload.get('correo') or DESTINATARIO_DEFAULT
    asunto = payload.get('asunto') or f"Escritura {escritura}"
    cuerpo = payload.get('cuerpo') or f"Adjunto recibo para la Escritura {escritura}."
    docs = payload.get('documentos') or []

    # localizar rutas completas de los documentos en CARPETA_PDFS
    rutas = []
    for name in docs:
        # buscar coincidencias por nombre exacto o por inicio del nombre
        for f in os.listdir(CARPETA_PDFS):
            if f == name or f.startswith(name):
                rutas.append(os.path.join(CARPETA_PDFS, f))
                break

    print(f"[INFO] Procesando único: escritura={escritura} correo={correo} archivos={len(rutas)}")
    driver, wait = None, None
    try:
        driver, wait = crear_edge_sin_sesion(CARPETA_PDFS, headless=True, wait_seconds=WAIT_SECONDS)
        crear_borrador_con_multiples_adjuntos(driver, wait, correo, asunto, cuerpo, rutas)
        print("[INFO] Borrador creado correctamente")
        return 0
    except Exception as e:
        print(f"[ERROR] Error creando borrador: {e}")
        return 2
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass

if __name__ == '__main__':
    # permitimos pasar --single <jsonfile> para crear un borrador único
    if '--single' in sys.argv:
        try:
            idx = sys.argv.index('--single')
            jsonfile = sys.argv[idx+1]
            with open(jsonfile, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            rc = process_single_recibo(payload)
            sys.exit(rc)
        except Exception as e:
            print(f"[EXCEPTION] {type(e).__name__}: {e}")
            sys.exit(3)

# ====================
# PLANTILLAS
# ====================
PLANTILLAS = {
    "cundinamarca": {
        "asunto": "Proceso de registro Escritura {escritura} – NIR: {nir}",
        "cuerpo": (
            "Buen día,\n\n"
            "Espero que se encuentre muy bien.\n\n"
            "De manera atenta remitimos el recibo de pago correspondiente a la Escritura N.º {escritura}. de la Gobernación de {gobernacion}.\n\n"            
            "⚠️ Información Importante: Plazos y Pagos de Registro\n\n"
            "Para que el trámite de su escritura sea exitoso y evitar sobrecostos legales, por favor lea atentamente las siguientes condiciones de cumplimiento obligatorio:\n\n"
            "1. Plazo Perentorio de Radicación:\n"
            "Usted cuenta con un plazo máximo de dos (2) meses calendario, contados a partir de la fecha de otorgamiento (firma) de la escritura, para radicar el documento ante la Oficina de Registro de Instrumentos Públicos.\n"
            "Consecuencias del incumplimiento: Superar este plazo genera automáticamente intereses de mora y posibles sanciones administrativas según la normativa registral vigente.\n\n"
            "- Número de Liquidación: Para cualquier trámite o verificación, puede encontrar el número de liquidación en la parte superior derecha del recibo adjunto debe digitar sin los Ceros al principio.\n"
            "2. Requisito de Doble Pago:\n"
            "La radicación solo es válida si se completan satisfactoriamente los dos (2) pagos obligatorios:\n"
            "​Impuesto de Registro (Gobernación de Cundinamarca): Pago de la boleta fiscal.\n"
            "Derechos de Registro (Vur / Notariado): Pago de los derechos registrales propiamente dichos.\n"
            "Nota Crítica: El trámite no se iniciará si falta cualquiera de estos dos pagos o si estos se realizan fuera de las fechas de vencimiento de los recibos. La fecha efectiva de registro depende de la validación del recaudo ante la Gobernación.\n\n"
            "3. Instrucciones para la Liquidación y Pago:\n"
            "Para consultar el estado de su liquidación o realizar el pago en línea:\n"
            "Número de Liquidación: Lo encontrará en la parte superior derecha de su recibo.\n"
            "Formato de búsqueda: Al digitar el número en el portal de la Gobernación, debe omitir los ceros iniciales. (Ejemplo: Si el número es 000012345, digite solo 12345).\n\n"
            "¿Por qué esto es vital?\n\n"
            "Muchos usuarios asumen que el plazo comienza cuando reciben el recibo, pero la ley es clara: el tiempo corre desde que se firmó la escritura en la Notaría. Le recomendamos realizar ambos pagos de manera inmediata para evitar que el sistema bloquee el trámite por extemporaneidad.\n\n"
            "1. En línea: Puede realizar el pago a través del portal de Trámites de {gobernacion} en el siguiente enlace: https://gevir.cundinamarca.gov.co/consultas.php, utilizando el número de liquidación mencionado.\n"
            "2. Presencial: Si prefiere realizar el pago de manera presencial, puede dirigirse a cualquier oficina de la Gobernación de {gobernacion} o a los bancos autorizados, presentando el recibo adjunto en el banco correspondiente.\n\n"
            "Le solicitamos validar que toda la información en la liquidación sea correcta. En caso de encontrar alguna inconsistencia, por favor contáctenos inmediatamente antes de efectuar el pago.\n\n"
            "Una vez realizado el pago, le agradecemos notificarnos para continuar con el trámite. Puede hacerlo respondiendo a este correo, llamando al 601 8088139 ext. 106.\n\n"
            "Cordialmente,\n"
            "Beneficencia y Registro\n"
            "NOTARÍA 48 DEL CÍRCULO DE BOGOTÁ D.C"
        )
    },
    "bolivar": {
        "asunto": "Proceso de registro Escritura {escritura} - NIR: {nir}",
        "cuerpo": (
            "Buen día,\n\n"
            "Espero que se encuentre muy bien.\n\n"
            "De manera atenta remitimos el recibo de pago correspondiente a la Escritura N.º {escritura}.\n\n"            
            "⚠️ Información Importante: Plazos y Pagos de Registro\n\n"
            "Para que el trámite de su escritura sea exitoso y evitar sobrecostos legales, por favor lea atentamente las siguientes condiciones de cumplimiento obligatorio:\n\n"
            "1. Plazo Perentorio de Radicación:\n"
            "Usted cuenta con un plazo máximo de dos (2) meses calendario, contados a partir de la fecha de OTORGAMIENTO (firma) de la escritura, para radicar el documento ante la Oficina de Registro de Instrumentos Públicos.\n"
            "Consecuencias del incumplimiento: Superar este plazo genera automáticamente intereses de mora y posibles sanciones administrativas según la normativa registral vigente.\n\n"
            "- Número de Liquidación: Para cualquier trámite o verificación, puede encontrar el número de liquidación en la parte superior derecha del recibo adjunto debe digitar sin los Ceros al principio.\n"
            "2. Requisito de Doble Pago:\n"
            "La radicación solo es válida si se completan satisfactoriamente los dos (2) pagos obligatorios:\n"
            "​Impuesto de Registro (Gobernación de {gobernacion}): Pago de la boleta fiscal.\n"
            "Derechos de Registro (Vur / Notariado): Pago de los derechos registrales propiamente dichos.\n\n"
            "Nota Crítica: El trámite no se iniciará si falta cualquiera de estos dos pagos o si estos se realizan fuera de las fechas de vencimiento de los recibos. La fecha efectiva de registro depende de la validación del recaudo ante la Gobernación.\n\n"
            "3. Instrucciones para la Liquidación y Pago:\n"
            "Para consultar el estado de su liquidación o realizar el pago en línea:\n"
            "Número de Liquidación y/o Recibo: Lo encontrará en la parte superior derecha de su recibo.\n"
            "Formato de búsqueda: Al digitar el número en el portal de la Gobernación, debe omitir los ceros iniciales. (Ejemplo: Si el número es 000012345, digite solo 12345).\n\n"
            "¿Por qué esto es vital?\n\n"
            "Muchos usuarios asumen que el plazo comienza cuando reciben el recibo, pero la ley es clara: el tiempo corre desde que se firmó la escritura en la Notaría. Le recomendamos realizar ambos pagos de manera inmediata para evitar que el sistema bloquee el trámite por extemporaneidad.\n\n"
            "1. En línea: Puede realizar el pago a través del portal de Trámites de {gobernacion} en el siguiente enlace: https://impuestos.bolivar.gov.co/gobol_web/pagos-recibos, utilizando el número de liquidación mencionado.\n"
            "2. Presencial: Si prefiere realizar el pago de manera presencial, puede dirigirse a cualquier oficina de la Gobernación de {gobernacion} o a los bancos autorizados, presentando el recibo adjunto en el banco correspondiente.\n\n"
            "Le solicitamos validar que toda la información en la liquidación sea correcta. En caso de encontrar alguna inconsistencia, por favor contáctenos inmediatamente antes de efectuar el pago.\n\n"
            "Una vez realizado el pago, le agradecemos notificarnos para continuar con el trámite. Puede hacerlo respondiendo a este correo, llamando al 601 8088139 ext. 106.\n\n"
            "Cordialmente,\n"
            "Beneficencia y Registro\n"
            "NOTARÍA 48 DEL CÍRCULO DE BOGOTÁ D.C"
        )
    },
    "tolima": {
        "asunto": "Proceso de registro Escritura {escritura} - NIR: {nir}",
        "cuerpo": (
            "Buen día,\n\n"
            "Espero que se encuentre muy bien.\n\n"
            "De manera atenta remitimos el recibo de pago correspondiente a la Escritura N.º {escritura}.\n\n"            
            "⚠️ Información Importante: Plazos y Pagos de Registro\n\n"
            "Para que el trámite de su escritura sea exitoso y evitar sobrecostos legales, por favor lea atentamente las siguientes condiciones de cumplimiento obligatorio:\n\n"
            "1. Plazo Perentorio de Radicación:\n"
            "Usted cuenta con un plazo máximo de dos (2) meses calendario, contados a partir de la fecha de OTORGAMIENTO (firma) de la escritura, para radicar el documento ante la Oficina de Registro de Instrumentos Públicos.\n"
            "Consecuencias del incumplimiento: Superar este plazo genera automáticamente intereses de mora y posibles sanciones administrativas según la normativa registral vigente.\n\n"
            "- Número de Liquidación: Para cualquier trámite o verificación, puede encontrar el número de liquidación en la parte superior derecha del recibo adjunto debe digitar sin los Ceros al principio.\n"
            "2. Requisito de Doble Pago:\n"
            "La radicación solo es válida si se completan satisfactoriamente los dos (2) pagos obligatorios:\n"
            "​Impuesto de Registro (Gobernación de {gobernacion}): Pago de la boleta fiscal.\n"
            "Derechos de Registro (Vur / Notariado): Pago de los derechos registrales propiamente dichos.\n\n"
            "Nota Crítica: El trámite no se iniciará si falta cualquiera de estos dos pagos o si estos se realizan fuera de las fechas de vencimiento de los recibos. La fecha efectiva de registro depende de la validación del recaudo ante la Gobernación.\n\n"
            "3. Instrucciones para la Liquidación y Pago:\n"
            "Para consultar el estado de su liquidación o realizar el pago en línea:\n"
            "Número de Liquidación y/o Recibo: Lo encontrará en la parte superior derecha de su recibo.\n"
            "Formato de búsqueda: Al digitar el número en el portal de la Gobernación, debe omitir los ceros iniciales. (Ejemplo: Si el número es 000012345, digite solo 12345).\n\n"
            "¿Por qué esto es vital?\n\n"
            "Muchos usuarios asumen que el plazo comienza cuando reciben el recibo, pero la ley es clara: el tiempo corre desde que se firmó la escritura en la Notaría. Le recomendamos realizar ambos pagos de manera inmediata para evitar que el sistema bloquee el trámite por extemporaneidad.\n\n"
            "1. En línea: Puede realizar el pago a través del portal de Trámites de {gobernacion} en el siguiente enlace: https://aplicativosenlinea.net/siverrtolima2/pagoweb/consulta_boleta_contri.php, utilizando el número de liquidación mencionado.\n"
            "2. Presencial: Si prefiere realizar el pago de manera presencial, puede dirigirse a cualquier oficina de la Gobernación de {gobernacion} o a los bancos autorizados, presentando el recibo adjunto en el banco correspondiente.\n\n"
            "Le solicitamos validar que toda la información en la liquidación sea correcta. En caso de encontrar alguna inconsistencia, por favor contáctenos inmediatamente antes de efectuar el pago.\n\n"
            "Una vez realizado el pago, le agradecemos notificarnos para continuar con el trámite. Puede hacerlo respondiendo a este correo, llamando al 601 8088139 ext. 106.\n\n"
            "Cordialmente,\n"
            "Beneficencia y Registro\n"
            "NOTARÍA 48 DEL CÍRCULO DE BOGOTÁ D.C"
        )
    },
    "boyaca": {
        "asunto": "Proceso de registro Escritura {escritura} - NIR: {nir}",
        "cuerpo": (
            "Buen día,\n\n"
            "Espero que se encuentre muy bien.\n\n"
            "De manera atenta remitimos el recibo de pago correspondiente a la Escritura N.º {escritura}.\n\n"
            "⚠️ Información Importante: Plazos y Pagos de Registro\n\n"
            "Para que el trámite de su escritura sea exitoso y evitar sobrecostos legales, por favor lea atentamente las siguientes condiciones de cumplimiento obligatorio:\n\n"
            "1. Plazo Perentorio de Radicación:\n"
            "Usted cuenta con un plazo máximo de dos (2) meses calendario, contados a partir de la fecha de OTORGAMIENTO (firma) de la escritura, para radicar el documento ante la Oficina de Registro de Instrumentos Públicos.\n"
            "Consecuencias del incumplimiento: Superar este plazo genera automáticamente intereses de mora y posibles sanciones administrativas según la normativa registral vigente.\n\n"
            "- Número de Liquidación: Para cualquier trámite o verificación, puede encontrar el número de liquidación en la parte superior derecha del recibo adjunto debe digitar sin los Ceros al principio.\n"
            "2. Requisito de Doble Pago:\n"
            "La radicación solo es válida si se completan satisfactoriamente los dos (2) pagos obligatorios:\n"
            "​Impuesto de Registro (Gobernación de {gobernacion}): Pago de la boleta fiscal.\n"
            "Derechos de Registro (Vur / Notariado): Pago de los derechos registrales propiamente dichos.\n\n"
            "Nota Crítica: El trámite no se iniciará si falta cualquiera de estos dos pagos o si estos se realizan fuera de las fechas de vencimiento de los recibos. La fecha efectiva de registro depende de la validación del recaudo ante la Gobernación.\n\n"
            "3. Instrucciones para la Liquidación y Pago:\n"
            "Para consultar el estado de su liquidación o realizar el pago en línea:\n"
            "Número de Liquidación y/o Recibo: Lo encontrará en la parte superior derecha de su recibo.\n"
            "Formato de búsqueda: Al digitar el número en el portal de la Gobernación, debe omitir los ceros iniciales. (Ejemplo: Si el número es 000012345, digite solo 12345).\n\n"
            "¿Por qué esto es vital?\n\n"
            "Muchos usuarios asumen que el plazo comienza cuando reciben el recibo, pero la ley es clara: el tiempo corre desde que se firmó la escritura en la Notaría. Le recomendamos realizar ambos pagos de manera inmediata para evitar que el sistema bloquee el trámite por extemporaneidad.\n\n"
            "1. En línea: Puede realizar el pago a través del portal de Trámites de {gobernacion} en el siguiente enlace: https://gestionaonline.co/siverrboyaca/pagoweb/consulta_boleta_contri.php, utilizando el número de liquidación mencionado.\n"
            "2. Presencial: Si prefiere realizar el pago de manera presencial, puede dirigirse a cualquier oficina de la Gobernación de {gobernacion} o a los bancos autorizados, presentando el recibo adjunto en el banco correspondiente.\n\n"
            "Le solicitamos validar que toda la información en la liquidación sea correcta. En caso de encontrar alguna inconsistencia, por favor contáctenos inmediatamente antes de efectuar el pago.\n\n"
            "Una vez realizado el pago, le agradecemos notificarnos para continuar con el trámite. Puede hacerlo respondiendo a este correo, llamando al 601 8088139 ext. 106.\n\n"
            "Cordialmente,\n"
            "Beneficencia y Registro\n"
            "NOTARÍA 48 DEL CÍRCULO DE BOGOTÁ D.C"
        )
    },
    "santander": {
        "asunto": "Proceso de registro Escritura {escritura} - NIR: {nir}",
        "cuerpo": (
            "Buen día,\n\n"
            "Espero que se encuentre muy bien.\n\n"
            "De manera atenta remitimos el recibo de pago correspondiente a la Escritura N.º {escritura}.\n\n"
            "⚠️ Información Importante: Plazos y Pagos de Registro\n\n"
            "Para que el trámite de su escritura sea exitoso y evitar sobrecostos legales, por favor lea atentamente las siguientes condiciones de cumplimiento obligatorio:\n\n"
            "1. Plazo Perentorio de Radicación:\n"
            "Usted cuenta con un plazo máximo de dos (2) meses calendario, contados a partir de la fecha de OTORGAMIENTO (firma) de la escritura, para radicar el documento ante la Oficina de Registro de Instrumentos Públicos.\n"
            "Consecuencias del incumplimiento: Superar este plazo genera automáticamente intereses de mora y posibles sanciones administrativas según la normativa registral vigente.\n\n"
            "- Número de Liquidación: Para cualquier trámite o verificación, puede encontrar el número de liquidación en la parte superior derecha del recibo adjunto debe digitar sin los Ceros al principio.\n"
            "2. Requisito de Doble Pago:\n"
            "La radicación solo es válida si se completan satisfactoriamente los dos (2) pagos obligatorios:\n"
            "​Impuesto de Registro (Gobernación de {gobernacion}): Pago de la boleta fiscal.\n"
            "Derechos de Registro (Vur / Notariado): Pago de los derechos registrales propiamente dichos.\n\n"
            "Nota Crítica: El trámite no se iniciará si falta cualquiera de estos dos pagos o si estos se realizan fuera de las fechas de vencimiento de los recibos. La fecha efectiva de registro depende de la validación del recaudo ante la Gobernación.\n\n"
            "3. Instrucciones para la Liquidación y Pago:\n"
            "Para consultar el estado de su liquidación o realizar el pago en línea:\n"
            "Número de Liquidación y/o Recibo: Lo encontrará en la parte superior derecha de su recibo.\n"
            "Formato de búsqueda: Al digitar el número en el portal de la Gobernación, debe omitir los ceros iniciales. (Ejemplo: Si el número es 000012345, digite solo 12345).\n\n"
            "¿Por qué esto es vital?\n\n"
            "Muchos usuarios asumen que el plazo comienza cuando reciben el recibo, pero la ley es clara: el tiempo corre desde que se firmó la escritura en la Notaría. Le recomendamos realizar ambos pagos de manera inmediata para evitar que el sistema bloquee el trámite por extemporaneidad.\n\n"
            "1. En línea: Puede realizar el pago a través del portal de Trámites de {gobernacion} en el siguiente enlace: https://impuestos.gobernaciondelmagdalena.gov.co/pse-autoservicio-ref, utilizando el número de liquidación mencionado.\n"
            "2. Presencial: Si prefiere realizar el pago de manera presencial, puede dirigirse a cualquier oficina de la Gobernación de {gobernacion} o a los bancos autorizados, presentando el recibo adjunto en el banco correspondiente.\n\n"
            "Le solicitamos validar que toda la información en la liquidación sea correcta. En caso de encontrar alguna inconsistencia, por favor contáctenos inmediatamente antes de efectuar el pago.\n\n"
            "Una vez realizado el pago, le agradecemos notificarnos para continuar con el trámite. Puede hacerlo respondiendo a este correo, llamando al 601 8088139 ext. 106.\n\n"
            "Cordialmente,\n"
            "Beneficencia y Registro\n"
            "NOTARÍA 48 DEL CÍRCULO DE BOGOTÁ D.C"
        )
    },
    "atlantico": {
        "asunto": "Proceso de registro Escritura {escritura} - NIR: {nir}",
        "cuerpo": (
            "Buen día,\n\n"
            "Espero que se encuentre muy bien.\n\n"
            "De manera atenta remitimos el recibo de pago correspondiente a la Escritura N.º {escritura}.\n\n"
            "⚠️ Información Importante: Plazos y Pagos de Registro\n\n"
            "Para que el trámite de su escritura sea exitoso y evitar sobrecostos legales, por favor lea atentamente las siguientes condiciones de cumplimiento obligatorio:\n\n"
            "1. Plazo Perentorio de Radicación:\n"
            "Usted cuenta con un plazo máximo de dos (2) meses calendario, contados a partir de la fecha de OTORGAMIENTO (firma) de la escritura, para radicar el documento ante la Oficina de Registro de Instrumentos Públicos.\n"
            "Consecuencias del incumplimiento: Superar este plazo genera automáticamente intereses de mora y posibles sanciones administrativas según la normativa registral vigente.\n\n"
            "- Número de Liquidación: Para cualquier trámite o verificación, puede encontrar el número de liquidación en la parte superior derecha del recibo adjunto debe digitar sin los Ceros al principio.\n"
            "2. Requisito de Doble Pago:\n"
            "La radicación solo es válida si se completan satisfactoriamente los dos (2) pagos obligatorios:\n"
            "​Impuesto de Registro (Gobernación de {gobernacion}): Pago de la boleta fiscal.\n"
            "Derechos de Registro (Vur / Notariado): Pago de los derechos registrales propiamente dichos.\n\n"
            "Nota Crítica: El trámite no se iniciará si falta cualquiera de estos dos pagos o si estos se realizan fuera de las fechas de vencimiento de los recibos. La fecha efectiva de registro depende de la validación del recaudo ante la Gobernación.\n\n"
            "3. Instrucciones para la Liquidación y Pago:\n"
            "Para consultar el estado de su liquidación o realizar el pago en línea:\n"
            "Número de Liquidación y/o Recibo: Lo encontrará en la parte superior derecha de su recibo.\n"
            "Formato de búsqueda: Al digitar el número en el portal de la Gobernación, debe omitir los ceros iniciales. (Ejemplo: Si el número es 000012345, digite solo 12345).\n\n"
            "¿Por qué esto es vital?\n\n"
            "Muchos usuarios asumen que el plazo comienza cuando reciben el recibo, pero la ley es clara: el tiempo corre desde que se firmó la escritura en la Notaría. Le recomendamos realizar ambos pagos de manera inmediata para evitar que el sistema bloquee el trámite por extemporaneidad.\n\n"
            "1. En línea: Puede realizar el pago a través del portal de Trámites de Cundinamarca en el siguiente enlace: https://www.abcpagos.com/vur_atlantico/documentos.recibo_pago.0012545288774838.pdf, utilizando el número de liquidación mencionado.\n"
            "2. Presencial: Si prefiere realizar el pago de manera presencial, puede dirigirse a cualquier oficina de la Gobernación de {gobernacion} o a los bancos autorizados, presentando el recibo adjunto en el banco correspondiente.\n\n"
            "Le solicitamos validar que toda la información en la liquidación sea correcta. En caso de encontrar alguna inconsistencia, por favor contáctenos inmediatamente antes de efectuar el pago.\n\n"
            "Una vez realizado el pago, le agradecemos notificarnos para continuar con el trámite. Puede hacerlo respondiendo a este correo, llamando al 601 8088139 ext. 106.\n\n"
            "Cordialmente,\n"
            "Beneficencia y Registro\n"
            "NOTARÍA 48 DEL CÍRCULO DE BOGOTÁ D.C"
        )
    },
    "antioquia": {
        "asunto": "Proceso de registro Escritura {escritura} - {nir}",
        "cuerpo": (
            "Buen día,\n\n"
            "Espero que se encuentre muy bien.\n\n"
            "De manera atenta remitimos el recibo de pago correspondiente a la Escritura N.º {escritura}.\n\n"
            "⚠️ Información Importante: Plazos y Pagos de Registro\n\n"
            "Para que el trámite de su escritura sea exitoso y evitar sobrecostos legales, por favor lea atentamente las siguientes condiciones de cumplimiento obligatorio:\n\n"
            "1. Plazo Perentorio de Radicación:\n"
            "Usted cuenta con un plazo máximo de dos (2) meses calendario, contados a partir de la fecha de OTORGAMIENTO (firma) de la escritura, para radicar el documento ante la Oficina de Registro de Instrumentos Públicos.\n"
            "Consecuencias del incumplimiento: Superar este plazo genera automáticamente intereses de mora y posibles sanciones administrativas según la normativa registral vigente.\n\n"
            "- Número de Liquidación: Para cualquier trámite o verificación, puede encontrar el número de liquidación en la parte superior derecha del recibo adjunto debe digitar sin los Ceros al principio.\n"
            "2. Requisito de Doble Pago:\n"
            "La radicación solo es válida si se completan satisfactoriamente los dos (2) pagos obligatorios:\n"
            "​Impuesto de Registro (Gobernación de {gobernacion}): Pago de la boleta fiscal.\n"
            "Derechos de Registro (Vur / Notariado): Pago de los derechos registrales propiamente dichos.\n\n"
            "Nota Crítica: El trámite no se iniciará si falta cualquiera de estos dos pagos o si estos se realizan fuera de las fechas de vencimiento de los recibos. La fecha efectiva de registro depende de la validación del recaudo ante la Gobernación.\n\n"
            "3. Instrucciones para la Liquidación y Pago:\n"
            "Para consultar el estado de su liquidación o realizar el pago en línea:\n"
            "Número de Liquidación y/o Recibo: Lo encontrará en la parte superior derecha de su recibo.\n"
            "Formato de búsqueda: Al digitar el número en el portal de la Gobernación, debe omitir los ceros iniciales. (Ejemplo: Si el número es 000012345, digite solo 12345).\n\n"
            "¿Por qué esto es vital?\n\n"
            "Muchos usuarios asumen que el plazo comienza cuando reciben el recibo, pero la ley es clara: el tiempo corre desde que se firmó la escritura en la Notaría. Le recomendamos realizar ambos pagos de manera inmediata para evitar que el sistema bloquee el trámite por extemporaneidad.\n\n"
            "Presencial: Para realizar el pago de manera presencial, puede dirigirse a cualquier oficina de la Gobernación de {gobernacion} o a los bancos autorizados, presentando el recibo adjunto en el banco correspondiente.\n\n"
            "Link para pago en línea: Puede realizar el pago a través del portal de Trámites de {gobernacion} en el siguiente enlace: https://vurantioquia.placetopay.com/people, utilizando el número de liquidación mencionado.\n\n"
            "Le solicitamos validar que toda la información en la liquidación sea correcta. En caso de encontrar alguna inconsistencia, por favor contáctenos inmediatamente antes de efectuar el pago.\n\n"
            "Una vez realizado el pago, le agradecemos notificarnos para continuar con el trámite. Puede hacerlo respondiendo a este correo, llamando al 601 8088139 ext. 106.\n\n"
            "Cordialmente,\n"
            "Beneficencia y Registro\n"
            "NOTARÍA 48 DEL CÍRCULO DE BOGOTÁ D.C"
        )
    },
    "magdalena": {
        "asunto": "Proceso de registro Escritura {escritura} - NIR: {nir}",
        "cuerpo": (
            "Buen día,\n\n"
            "Espero que se encuentre muy bien.\n\n"
            "De manera atenta remitimos el recibo de pago correspondiente a la Escritura N.º {escritura}.\n\n"
            "⚠️ Información Importante: Plazos y Pagos de Registro\n\n"
            "Para que el trámite de su escritura sea exitoso y evitar sobrecostos legales, por favor lea atentamente las siguientes condiciones de cumplimiento obligatorio:\n\n"
            "1. Plazo Perentorio de Radicación:\n"
            "Usted cuenta con un plazo máximo de dos (2) meses calendario, contados a partir de la fecha de OTORGAMIENTO (firma) de la escritura, para radicar el documento ante la Oficina de Registro de Instrumentos Públicos.\n"
            "Consecuencias del incumplimiento: Superar este plazo genera automáticamente intereses de mora y posibles sanciones administrativas según la normativa registral vigente.\n\n"
            "- Número de Liquidación: Para cualquier trámite o verificación, puede encontrar el número de liquidación en la parte superior derecha del recibo adjunto debe digitar sin los Ceros al principio.\n"
            "2. Requisito de Doble Pago:\n"
            "La radicación solo es válida si se completan satisfactoriamente los dos (2) pagos obligatorios:\n"
            "​Impuesto de Registro (Gobernación de {gobernacion}): Pago de la boleta fiscal.\n"
            "Derechos de Registro (Vur / Notariado): Pago de los derechos registrales propiamente dichos.\n\n"
            "Nota Crítica: El trámite no se iniciará si falta cualquiera de estos dos pagos o si estos se realizan fuera de las fechas de vencimiento de los recibos. La fecha efectiva de registro depende de la validación del recaudo ante la Gobernación.\n\n"
            "3. Instrucciones para la Liquidación y Pago:\n"
            "Para consultar el estado de su liquidación o realizar el pago en línea:\n"
            "Número de Liquidación y/o Recibo: Lo encontrará en la parte superior derecha de su recibo.\n"
            "Formato de búsqueda: Al digitar el número en el portal de la Gobernación, debe omitir los ceros iniciales. (Ejemplo: Si el número es 000012345, digite solo 12345).\n\n"
            "¿Por qué esto es vital?\n\n"
            "Muchos usuarios asumen que el plazo comienza cuando reciben el recibo, pero la ley es clara: el tiempo corre desde que se firmó la escritura en la Notaría. Le recomendamos realizar ambos pagos de manera inmediata para evitar que el sistema bloquee el trámite por extemporaneidad.\n\n"
            "1. Este recibo lo puede pagar en linea, en el siguiente link encuentra las instrucciones para hacerlo: https://impuestos.gobernaciondelmagdalena.gov.co/api/declaraciones/instructivos/public/instructivo-pago-pse-rentas-varias, utilizando el número de recibo asociado.\n"
            "2. Presencial: Si prefiere realizar el pago de manera presencial, puede dirigirse a cualquier oficina de la Gobernación de {gobernacion} o a los bancos autorizados, presentando el recibo adjunto en el banco correspondiente.\n\n"
            "Le solicitamos validar que toda la información en la liquidación sea correcta. En caso de encontrar alguna inconsistencia, por favor contáctenos inmediatamente antes de efectuar el pago.\n\n"
            "Una vez realizado el pago, le agradecemos notificarnos para continuar con el trámite. Puede hacerlo respondiendo a este correo, llamando al 601 8088139 ext. 106.\n\n"
            "Cordialmente,\n"
            "Beneficencia y Registro\n"
            "NOTARÍA 48 DEL CÍRCULO DE BOGOTÁ D.C"
        )
    }   
}

def normalizar(texto):
    if texto is None:
        return ""
    texto = str(texto).strip().lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return texto

def construir_mensaje(row):
    gob_raw = str(row.get("gobernacion", "") or "").strip().lower()
    if gob_raw == "nan" or not gob_raw:
        gob_raw = ""
    gob = normalizar(gob_raw)

    correo_raw = str(row.get("correo", "") or "").strip().lower()
    if not correo_raw or correo_raw.lower() == "nan":
        correo = DESTINATARIO_DEFAULT
    else:
        correo = correo_raw

    plantilla = PLANTILLAS.get(gob, {
        "asunto": "Proceso de registro Escritura {escritura} - Nir {nir}".capitalize(),
        "cuerpo": (
            "Buen día,\n\n"
            "Espero que se encuentre muy bien.\n\n"
            "De manera atenta remitimos el recibo de pago correspondiente a la Escritura N.º {escritura} - NIR: {nir}.\n\n"
            "⚠️ Información Importante: Plazos y Pagos de Registro\n\n"
            "Para que el trámite de su escritura sea exitoso y evitar sobrecostos legales, por favor lea atentamente las siguientes condiciones de cumplimiento obligatorio:\n\n"
            "1. Plazo Perentorio de Radicación:\n"
            "Usted cuenta con un plazo máximo de dos (2) meses calendario, contados a partir de la fecha de OTORGAMIENTO (firma) de la escritura, para radicar el documento ante la Oficina de Registro de Instrumentos Públicos.\n"
            "Consecuencias del incumplimiento: Superar este plazo genera automáticamente intereses de mora y posibles sanciones administrativas según la normativa registral vigente.\n\n"
            "- Número de Liquidación: Para cualquier trámite o verificación, puede encontrar el número de liquidación en la parte superior derecha del recibo adjunto debe digitar sin los Ceros al principio.\n"
            "2. Requisito de Doble Pago:\n"
            "La radicación solo es válida si se completan satisfactoriamente los dos (2) pagos obligatorios:\n"
            "​Impuesto de Registro (Gobernación de {gobernacion}): Pago de la boleta fiscal.\n"
            "Derechos de Registro (Vur / Notariado): Pago de los derechos registrales propiamente dichos.\n\n"
            "Nota Crítica: El trámite no se iniciará si falta cualquiera de estos dos pagos o si estos se realizan fuera de las fechas de vencimiento de los recibos. La fecha efectiva de registro depende de la validación del recaudo ante la Gobernación.\n\n"
            "3. Instrucciones para la Liquidación y Pago:\n"
            "Para consultar el estado de su liquidación o realizar el pago en línea:\n"
            "Número de Liquidación y/o Recibo: Lo encontrará en la parte superior derecha de su recibo.\n"
            "Formato de búsqueda: Al digitar el número en el portal de la Gobernación, debe omitir los ceros iniciales. (Ejemplo: Si el número es 000012345, digite solo 12345).\n\n"
            "¿Por qué esto es vital?\n\n"
            "Muchos usuarios asumen que el plazo comienza cuando reciben el recibo, pero la ley es clara: el tiempo corre desde que se firmó la escritura en la Notaría. Le recomendamos realizar ambos pagos de manera inmediata para evitar que el sistema bloquee el trámite por extemporaneidad.\n\n"
            "1. En línea: Puede realizar el pago a través del portal de Trámites de {gobernacion} en el siguiente enlace: https://gevir.cundinamarca.gov.co/consultas.php, utilizando el número de liquidación mencionado.\n"
            "2. Presencial: Si prefiere realizar el pago de manera presencial, puede dirigirse a cualquier oficina de la Gobernación de {gobernacion} o a los bancos autorizados, presentando el recibo adjunto en el banco correspondiente.\n\n"
            "Le solicitamos validar que toda la información en la liquidación sea correcta. En caso de encontrar alguna inconsistencia, por favor contáctenos inmediatamente antes de efectuar el pago.\n\n"
            "Una vez realizado el pago, le agradecemos notificarnos para continuar con el trámite. Puede hacerlo respondiendo a este correo, llamando al 601 8088139 ext. 106.\n\n"
            "Cordialmente,\n"
            "Beneficencia y Registro\n"
            "NOTARÍA 48 DEL CÍRCULO DE BOGOTÁ D.C"
        )
    })

    escritura = str(row.get("escritura_str", "") or "")
    nir = str(row.get("nir", "") or "").strip()
    if nir.lower() == "nan" or not nir:
        nir = "No especificado"

    gobernacion = gob_raw if gob_raw else ""

    asunto = plantilla["asunto"].format(escritura=escritura, nir=nir, gobernacion=gobernacion.capitalize())
    cuerpo = plantilla["cuerpo"].format(escritura=escritura, nir=nir, gobernacion=gobernacion.capitalize())

    return correo, asunto, cuerpo

def actualizar_estado_excel(ruta_xlsx, hoja, escritura_str, nuevo_estado):
    df_excel = pd.read_excel(ruta_xlsx, sheet_name=hoja, dtype=str)

    col_notf = next(c for c in df_excel.columns if "notificacion" in c.lower().replace(" ", ""))
    col_escritura = next(c for c in df_excel.columns if "escritura" in c.lower().replace(" ", ""))
    df_excel["escritura_str"] = (
        pd.to_numeric(df_excel[col_escritura], errors="coerce")
        .fillna(0).astype(int).astype(str)
    )

    mask = df_excel["escritura_str"] == escritura_str
    df_excel.loc[mask, col_notf] = nuevo_estado

    with pd.ExcelWriter(ruta_xlsx, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        df_excel.to_excel(writer, sheet_name=hoja, index=False)

# =========================
# RUN
# =========================
df, hoja = cargar_excel(RUTA_XLSX)
df = preparar_excel(df)

df_listo = preparar_listos_para_enviar(df, CARPETA_PDFS)

driver = get_edge_driver(CARPETA_PDFS, EDGE_USER_DATA_DIR, EDGE_PROFILE_DIR)
wait = WebDriverWait(driver, WAIT_SECONDS)
driver.get("https://mail.google.com/mail/u/0/#inbox")

procesadas = set()

print("=========================================")
if "correo" in df_listo.columns:
    print(f"Pendientes: {len(df_listo)}")
else:
    print("ALERTA CRÍTICA: La columna 'correo' NO existe en el DataFrame. Por eso usa el valor por defecto.")
print("=========================================")
for _, row in df_listo.iterrows():
    escritura = row["escritura_str"]
    if escritura in procesadas:
        continue

    # Buscar TODOS los archivos asociados a esta escritura
    rutas_archivos = buscar_pdfs_en_carpeta(CARPETA_PDFS, escritura)
    if not rutas_archivos:
        print("[ERROR] Sin archivos:", escritura)
        continue

    correo, asunto, cuerpo = construir_mensaje(row)

    try:
        crear_borrador_con_multiples_adjuntos(driver, wait, correo, asunto, cuerpo, rutas_archivos)
        nombres_archivos = ", ".join([os.path.basename(r) for r in rutas_archivos])
        print(f"[INFO] Escritura: {escritura} -> Adjuntando {len(rutas_archivos)} archivo(s): {nombres_archivos}")
        actualizar_estado_excel(RUTA_XLSX, hoja, escritura, "Enviado")
        # Actualizar estado en Supabase
        try:
            update_liq_estado_by_escritura(escritura, "Enviado")
            insert_log("envio_recibo", f"Escritura {escritura} marcada como Enviado", correo)
        except Exception as e:
            print(f"[WARN] No se pudo actualizar Supabase: {e}")
        # Subir cada archivo a Supabase (guardar en tabla 'descargas')
        try:
            for ruta_archivo in rutas_archivos:
                try:
                    nombre = os.path.basename(ruta_archivo)
                    with open(ruta_archivo, "rb") as f:
                        contenido = f.read()
                    try:
                        guardar_descarga("recibo", escritura, nombre, contenido, correo)
                        print(f"[INFO] Guardado en Supabase: {nombre}")
                    except Exception as e:
                        print(f"[WARN] No se pudo guardar en Supabase: {e}")
                except Exception as e:
                    print(f"[WARN] No se pudo leer archivo {ruta_archivo}: {e}")
        except Exception:
            pass
        procesadas.add(escritura)
        print(f"[SUCCESS] Enviado: {escritura} | {correo}")
    except Exception as e:
        print(f"[ERROR] Error: {escritura} | {type(e).__name__}: {e}")
    # Intento de registrar recibo si hay datos disponibles
    try:
        numero_recibo = row.get("numero_recibo") if "numero_recibo" in row.index else None
        certificado_id = row.get("certificado_id") if "certificado_id" in row.index else None
        monto = row.get("monto") if "monto" in row.index else None
        email_destino = row.get("correo") if "correo" in row.index else None
        if numero_recibo or certificado_id:
            try:
                insert_recibo(numero_recibo, certificado_id, monto, email_destino)
                if certificado_id:
                    update_certificado_estado(certificado_id, "enviado")
                insert_log("envio_recibo", f"Recibo {numero_recibo or certificado_id} registrado", correo)
            except Exception as e:
                insert_log("envio_recibo", f"Error al registrar recibo: {str(e)}", correo, "error")
    except Exception:
        pass
print("=========================================")
print("Proceso finalizado. Total procesados:", len(procesadas))
if driver is not None:
    driver.quit()

# test de conexión a Supabase — usa la tabla `liq` (la que contiene el Excel cargado)
from supabase_client import get_supabase

def test_conexion():
    try:
        supabase = get_supabase()
        if not supabase:
            print("Supabase no configurado (SUPABASE_URL/SUPABASE_KEY en .env)")
            return False
        # Consultar la tabla 'liq' (tabla creada desde Informe.xlsx)
        result = supabase.table("liq").select("*").limit(1).execute()
        print("Conexión a Supabase OK")
        return True
    except Exception as e:
        print("Error de conexión:", e)
        return False

if __name__ == "__main__":
    test_conexion()
