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
import shutil
import json
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from supabase_client import update_liq_estado_by_escritura, insert_log

warnings.filterwarnings("ignore")

# =========================
# CONFIG
# =========================
RUTA_XLSX = r"C:\Users\EQUIPO 25\Desktop\Beneficencia\Informe.xlsx"
CARPETA_PDFS = r"C:\Users\EQUIPO 25\Desktop\Beneficencia\Certificados"

EDGE_USER_DATA_DIR = r"C:\Users\EQUIPO 25\AppData\Local\Microsoft\Edge\User Data"
EDGE_PROFILE_DIR = "Default"
DESTINATARIO_DEFAULT = ""
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
    options.add_argument("--headless=new")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    options.add_argument("--log-level=3")
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
    
    col_ctl = next((c for c in df.columns if "estado" in c and "ctl" in c), None)
    if col_ctl and col_ctl != "estado_ctl":
        df.rename(columns={col_ctl: "estado_ctl"}, inplace=True)
    elif "estado_ctl" not in df.columns:
        df["estado_ctl"] = ""    

    if "gobernacion" in df.columns:
        df["gobernacion"] = df["gobernacion"].fillna("").astype(str).str.strip()
    if "correo" in df.columns:
        df["correo"] = df["correo"].fillna("").astype(str).str.strip()
    if "estado_ctl" in df.columns:
        df["estado_ctl"] = df["estado_ctl"].fillna("").astype(str).str.strip()
    
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
    if "estado_ctl" in df.columns:
        mask_pend = (df["estado_ctl"].astype(str).str.strip().str.lower() != "enviado") & (df['pago'].astype(str).str.strip().str.lower() == "ingresado")
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
    
    # Usar los nombres originales de los archivos (preservan número de escritura)
    temp_files = []
    for ruta_archivo in rutas_archivos:
        # Mantener el nombre original del archivo
        nombre_original = os.path.basename(ruta_archivo)
        temp_path = os.path.join(tempfile.gettempdir(), nombre_original)
        shutil.copy2(ruta_archivo, temp_path)
        temp_files.append(temp_path)
    
    # Adjuntar cada archivo
    for i, temp_path in enumerate(temp_files, start=1):
        try:
            # Re-localizar el input de archivo cada vez para evitar StaleElementReferenceException
            file_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']")))
            
            nombre = os.path.basename(temp_path)
            file_input.send_keys(temp_path)
            
            # Esperar a que aparezca en el DOM
            try:
                wait.until(lambda d: nombre in d.page_source, timeout=10)
            except:
                pass
            
            print(f"  ✓ Adjuntado: {nombre}")
            time.sleep(0.5)  # Pequeña pausa entre adjuntos
        except Exception as e:
            print(f"  ⚠ No se pudo adjuntar {os.path.basename(temp_path)}: {e}")
    
    # Limpiar archivos temporales
    for temp_path in temp_files:
        try:
            os.remove(temp_path)
        except:
            pass

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

# ====================
# PLANTILLAS
# ====================
PLANTILLA = {
    "certificado":{
        "asunto": "Escritura {escritura} del Nir {nir} - Certificado de Tradición y Libertad",
        "cuerpo": (
            "Estimado/a usuario/a, \n\n Buen día,\n\n"
            "Me dirijo a usted para informarle que se adjunta a la presente comunicación el Certificado de Tradición y Libertad. Con la expedición de este documento, se da por terminada formalmente la gestión de su escritura con nosotros..\n\n"
            "Es de suma importancia que realice una revisión exhaustiva del contenido del certificado, validando que todos los datos coincidan exactamente con la escritura pública firmada..\n\n"
            + "⚠️ Protocolo de subsanación de inconsistencias: {nir}\n\n"
            "Errores de Registro: De encontrar inconsistencias, estas deberán subsanarse directamente ante la ORIP correspondiente, ya que ellos emiten el concepto y son los únicos facultados para modificar el documento.\n"
            "Errores de Notaría: Si el error es por causa de la Notaría, deberá notificarnos de inmediato para revisar el caso y proceder con la subsanación correspondiente.\n\n"
            "Reclamación de copias y Atención al Cliente: Las copias pueden ser reclamadas de manera presencial presentando la factura original o la cédula de ciudadanía de los intervinientes.\n\n"
            "Contamos con un horario de atención de lunes a viernes, de 8:00 a.m. a 5:30 p.m. en jornada continua.\n\n"
            "Consecuencias del incumplimiento: Superar este plazo genera automáticamente intereses de mora y posibles sanciones administrativas según la normativa registral vigente.\n\n"
            "- Número de Liquidación: Para cualquier trámite o verificación, puede encontrar el número de liquidación en la parte superior derecha del recibo adjunto debe digitar sin los Ceros al principio.\n"
            "Agradecemos la confianza depositada en nuestro despacho.\n"
            
            "Cordialmente,\n"
            "Beneficencia y Registro\n"
            "NOTARÍA 48 DEL CÍRCULO DE BOGOTÁ D.C"
        )
    }}

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

    correo_raw = str(row.get("correo", "") or "").strip()
    if not correo_raw or correo_raw.lower() == "nan":
        correo = DESTINATARIO_DEFAULT
    else:
        correo = correo_raw

    plantilla = PLANTILLA.get(gob, {        
        "certificado":{
            "asunto": "Escritura {escritura} del Nir {nir} - Certificado de Tradición y Libertad",
        "cuerpo": (
            "Estimado/a usuario/a, \n\n Buen día,\n\n"
            "Me dirijo a usted para informarle que se adjunta a la presente comunicación el Certificado de Tradición y Libertad. Con la expedición de este documento, se da por terminada formalmente la gestión de su escritura con nosotros..\n\n"
            "Es de suma importancia que realice una revisión exhaustiva del contenido del certificado, validando que todos los datos coincidan exactamente con la escritura pública firmada..\n\n"
            + "⚠️ Protocolo de subsanación de inconsistencias: {nir}\n\n"
            "Errores de Registro: De encontrar inconsistencias, estas deberán subsanarse directamente ante la ORIP correspondiente, ya que ellos emiten el concepto y son los únicos facultados para modificar el documento.\n"
            "Errores de Notaría: Si el error es por causa de la Notaría, deberá notificarnos de inmediato para revisar el caso y proceder con la subsanación correspondiente.\n\n"
            "Reclamación de copias y Atención al Cliente: Las copias pueden ser reclamadas de manera presencial presentando la factura original o la cédula de ciudadanía de los intervinientes.\n\n"
            "Contamos con un horario de atención de lunes a viernes, de 8:00 a.m. a 5:30 p.m. en jornada continua.\n\n"
            "Consecuencias del incumplimiento: Superar este plazo genera automáticamente intereses de mora y posibles sanciones administrativas según la normativa registral vigente.\n\n"
            "- Número de Liquidación: Para cualquier trámite o verificación, puede encontrar el número de liquidación en la parte superior derecha del recibo adjunto debe digitar sin los Ceros al principio.\n"
            "Agradecemos la confianza depositada en nuestro despacho.\n"
            
            "Cordialmente,\n"
            "Beneficencia y Registro\n"
            "NOTARÍA 48 DEL CÍRCULO DE BOGOTÁ D.C"
            )
        }}  ).get("certificado")

    escritura = str(row.get("escritura_str", "") or "")
    nir = str(row.get("nir", "") or "").strip()
    if nir.lower() == "nan" or not nir:
        nir = "No especificado"

    gobernacion = gob_raw if gob_raw else ""

    asunto = plantilla["asunto"].format(escritura=escritura, nir=nir, gobernacion=gobernacion.capitalize())
    cuerpo = plantilla["cuerpo"].format(escritura=escritura, nir=nir, gobernacion=gobernacion.capitalize())

    return correo, asunto, cuerpo


def enviar_certificado_unico(payload):
    escritura = str(payload.get("escritura") or "").strip()
    if not escritura:
        raise ValueError("La escritura es obligatoria para enviar el certificado")

    correo = str(payload.get("correo") or DESTINATARIO_DEFAULT).strip()
    nir = str(payload.get("nir") or "").strip()
    gobernacion = str(payload.get("gobernacion") or "").strip()
    asunto = payload.get("asunto")
    cuerpo = payload.get("cuerpo")

    if not asunto or not cuerpo:
        correo, asunto, cuerpo = construir_mensaje({
            "escritura_str": escritura,
            "nir": nir,
            "gobernacion": gobernacion,
            "correo": correo,
        })

    rutas_archivos = buscar_pdfs_en_carpeta(CARPETA_PDFS, escritura)
    if not rutas_archivos:
        raise FileNotFoundError(f"No se encontró ningún archivo para escritura {escritura}")

    driver = get_edge_driver(CARPETA_PDFS, EDGE_USER_DATA_DIR, EDGE_PROFILE_DIR)
    wait = WebDriverWait(driver, WAIT_SECONDS)
    driver.get("https://mail.google.com/mail/u/0/#inbox")

    try:
        crear_borrador_con_multiples_adjuntos(driver, wait, correo, asunto, cuerpo, rutas_archivos)
        df, hoja = cargar_excel(RUTA_XLSX)
        try:
            actualizar_estado_excel(RUTA_XLSX, hoja, escritura, "Enviado")
        except Exception:
            pass
        try:
            update_liq_estado_by_escritura(escritura, "Enviado")
            insert_log("envio_certificado", f"Escritura {escritura} marcada como Enviado", correo)
        except Exception:
            pass
    finally:
        if driver is not None:
            driver.quit()


def actualizar_estado_excel(ruta_xlsx, hoja, escritura_str, nuevo_estado):
    df_excel = pd.read_excel(ruta_xlsx, sheet_name=hoja, dtype=str)

    col_notf = next(c for c in df_excel.columns if "estado_ctl" in c.lower().replace(" ", ""))
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
if __name__ == "__main__":
    if "--single" in sys.argv:
        idx = sys.argv.index("--single")
        if idx + 1 >= len(sys.argv):
            raise ValueError("Debe proveer el archivo JSON después de --single")
        jsonfile = sys.argv[idx + 1]
        with open(jsonfile, encoding="utf-8") as rf:
            payload = json.load(rf)
        enviar_certificado_unico(payload)
        sys.exit(0)

    df, hoja = cargar_excel(RUTA_XLSX)
    df = preparar_excel(df)

    df_listo = preparar_listos_para_enviar(df, CARPETA_PDFS)

    driver = get_edge_driver(CARPETA_PDFS, EDGE_USER_DATA_DIR, EDGE_PROFILE_DIR)
    wait = WebDriverWait(driver, WAIT_SECONDS)
    driver.get("https://mail.google.com/mail/u/0/#inbox")

procesadas = set()

print("=========================================")
if "correo" in df_listo.columns:
    print(f"🔍🚀 Pendientes: {len(df_listo)}")
else:
    print("⚠️ ALERTA CRÍTICA: La columna 'correo' NO existe en el DataFrame. Por eso usa el valor por defecto.")
print("=========================================")
for _, row in df_listo.iterrows():
    escritura = row["escritura_str"]
    if escritura in procesadas:
        continue
    
    # Buscar TODOS los archivos asociados a esta escritura
    rutas_archivos = buscar_pdfs_en_carpeta(CARPETA_PDFS, escritura)
    if not rutas_archivos:
        print("❌ Sin archivos:", escritura)
        continue

    correo, asunto, cuerpo = construir_mensaje(row)

    try:
        crear_borrador_con_multiples_adjuntos(driver, wait, correo, asunto, cuerpo, rutas_archivos)
        nombres_archivos = ", ".join([f"{escritura} certificado {i+1}{os.path.splitext(r)[1]}" for i, r in enumerate(rutas_archivos)])
        print("📎 Escritura:", escritura, f"-> Adjuntando {len(rutas_archivos)} archivo(s): {nombres_archivos}")
        actualizar_estado_excel(RUTA_XLSX, hoja, escritura, "Enviado")
        try:
            update_liq_estado_by_escritura(escritura, "Enviado")
            insert_log("envio_certificado", f"Escritura {escritura} marcada como Enviado", correo)
        except Exception as e:
            print(f"[WARN] No se pudo actualizar Supabase a Enviado para {escritura}: {e}")
        procesadas.add(escritura)
        print("✅ Enviado:", escritura, "|", correo)
    except Exception as e:
        print("❌ Error:", escritura, "|", type(e).__name__)

if driver is not None:
    driver.quit()

print(f"✅ Proceso finalizado. Total escrituras procesadas: {len(procesadas)}")
print("=========================================")
