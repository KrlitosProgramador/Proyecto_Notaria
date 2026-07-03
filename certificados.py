import os, sys, time, re, subprocess, hashlib
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver import ActionChains
from selenium.common.exceptions import NoSuchElementException, TimeoutException, SessionNotCreatedException, StaleElementReferenceException
from supabase_client import (
    insert_certificado,
    insert_log,
    update_liq_estado_by_escritura,
    guardar_descarga,
    normalize_text,
    normalize_estado_ctl_value,
    is_estado_enviado,
    is_pago_ingresado,
    is_row_pending_for_certificados,
    normalize_escritura,
    extract_escritura_from_filename,
    get_pending_certificados_liq,
)

# --- HELPERS PARA CLIC ROBUSTO ---

def find_in_iframes(driver, by, locator, timeout=2):
    """Intenta localizar elemento en el main document, si falla recorre iframes"""
    try:
        return driver.find_element(by, locator)
    except NoSuchElementException:
        frames = driver.find_elements(By.TAG_NAME, "iframe")
        for i, f in enumerate(frames):
            try:
                driver.switch_to.frame(f)
                try:
                    el = driver.find_element(by, locator)
                    return el
                except NoSuchElementException:
                    driver.switch_to.default_content()
                    continue
            except Exception:
                driver.switch_to.default_content()
                continue
        driver.switch_to.default_content()
        raise NoSuchElementException(f"Elemento no encontrado por {by}={locator}")

def robust_click(driver, wait, by, locator, screenshot_path=None):
    """Intenta click robusto: espera, JS click, ActionChains, busca en iframes o por atributo onclick."""
    # 1) espera clickable
    try:
        el = wait.until(EC.element_to_be_clickable((by, locator)))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        try:
            el.click()
            return True
        except Exception:
            pass
    except TimeoutException:
        pass

    # 2) fallback: localizar incluso dentro de iframes
    try:
        el = find_in_iframes(driver, by, locator)
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        try:
            driver.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            pass
        try:
            ActionChains(driver).move_to_element(el).click().perform()
            return True
        except Exception:
            pass
    except Exception:
        pass

    # 3) fallback por atributo onclick específico
    try:
        css = "[onclick*='formModalFases:j_idt112:0:j_idt113']"
        el2 = driver.find_element(By.CSS_SELECTOR, css)
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el2)
        try:
            driver.execute_script("arguments[0].click();", el2)
            return True
        except Exception:
            pass
        try:
            ActionChains(driver).move_to_element(el2).click().perform()
            return True
        except Exception:
            pass
    except Exception:
        pass

    # 4) si falla, screenshot y retorno False
    if screenshot_path:
        try:
            driver.save_screenshot(screenshot_path)
        except Exception:
            pass
    return False


def obtener_version_edge():
    """Devuelve la versión de Edge instalada, o None si no se puede obtener."""
    posibles_rutas = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for ruta in posibles_rutas:
        if os.path.isfile(ruta):
            try:
                salida = subprocess.check_output([ruta, "--version"], stderr=subprocess.STDOUT, text=True)
                match = re.search(r"(\d+\.\d+\.\d+\.\d+)", salida)
                if match:
                    return match.group(1)
            except Exception:
                continue
    return None

def obtener_version_driver(ruta_driver):
    """Devuelve la versión de msedgedriver si el ejecutable existe."""
    if not os.path.isfile(ruta_driver):
        return None
    try:
        salida = subprocess.check_output([ruta_driver, "--version"], stderr=subprocess.STDOUT, text=True)
        match = re.search(r"(\d+\.\d+\.\d+\.\d+)", salida)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None

def iniciar_edge_driver(ruta_driver, opciones):
    """Crea el driver de Edge, con comprobación de versión y fallback si el driver es incompatible."""
    version_edge = obtener_version_edge()
    version_driver = obtener_version_driver(ruta_driver)

    if version_edge and version_driver:
        if version_edge.split(".")[0] != version_driver.split(".")[0]:
            print(f"Version mismatch: Edge {version_edge} / EdgeDriver {version_driver}")
        else:
            print(f"Versiones compatibles: Edge {version_edge} / EdgeDriver {version_driver}")

    if os.path.isfile(ruta_driver):
        service = Service(ruta_driver)
        try:
            return webdriver.Edge(service=service, options=opciones)
        except SessionNotCreatedException as e:
            print(f"[ERROR] El msedgedriver local no es compatible con el Edge instalado.")
            print(f"[INFO] Intenta actualizar el msedgedriver o usa Selenium Manager para obtener la versión correcta.")
        except Exception as e:
            print(f"[ERROR] Error al iniciar Edge con driver local: {e}")
            print(f"[INFO] Intentando iniciar Edge sin especificar driver local (Selenium Manager)")
        return webdriver.Edge(options=opciones)
    else:
        return webdriver.Edge(options=opciones)

# --- CONFIGURACIÓN INICIAL ---
APP_DIR = os.path.dirname(os.path.abspath(__file__))
download_folder = os.path.join(APP_DIR, "descargas", "certificados")

# Ruta local del driver (si existe)
ruta_edgedriver = os.path.join(APP_DIR, "drivers", "msedgedriver.exe")

# Crear carpeta de descargas si no existe
os.makedirs(download_folder, exist_ok=True)

print(f"[INFO] Carpeta de descargas: {download_folder}")

# --- CONFIGURACIÓN DE EDGE ---
edge_options = Options()
edge_options.use_chromium = True
edge_options.add_argument("--disable-gpu")
edge_options.add_argument("--no-sandbox")
edge_options.add_argument("--headless=new")
edge_options.add_argument("--disable-blink-features=AutomationControlled")
prefs = {
    "download.default_directory": download_folder,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "profile.managed_default_content_settings.pdfs": 2,
    "pdfjs.disabled": True,
    "safebrowsing.enabled": False,
    "profile.default_content_settings.popups": 0,
}
edge_options.add_experimental_option("prefs", prefs)
edge_options.add_experimental_option("useAutomationExtension", False)

service = Service(ruta_edgedriver) if os.path.isfile(ruta_edgedriver) else None
try:
    driver = iniciar_edge_driver(ruta_edgedriver, edge_options)
except Exception as e:
    raise RuntimeError(f"Error al iniciar EdgeDriver: {e}") from e

wait = WebDriverWait(driver, 10)

# --- FUNCIÓN PARA DESCARGAR MÚLTIPLES ARCHIVOS ---
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
                    print(f"[ERROR] Certificado no disponible {idx}")
                
                time.sleep(0.5)  # Pequeña pausa entre descargas
                
            except Exception as e:
                print(f"[ERROR] Sin descarga {idx}: {str(e)[:50]}")
                continue
    
    except Exception as e:
        print(f"[ERROR] Sin botones de descarga: {str(e)[:100]}")
    
    return archivos_descargados

# --- FUNCIÓN PARA DESCARGAR PDF CON CTRL+S (COMPATIBILIDAD) ---
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
        for f in os.listdir(download_folder):
            ruta = os.path.join(download_folder, f)
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
            if not any(x.lower().endswith(".crdownload") for x in os.listdir(download_folder)):
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
    destino = os.path.join(download_folder, nombre_final)
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
        for f in os.listdir(download_folder):
            existing = os.path.join(download_folder, f)
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

# --- FUNCIÓN PARA ESPERAR NUEVA VENTANA ---
def esperar_y_cambiar_ventana(ventana_principal, timeout=20):
    """Espera a que se abra una nueva ventana/pestaña y cambia a ella"""
    tiempo_inicio = time.time()
    
    while time.time() - tiempo_inicio < timeout:
        try:
            todas_ventanas = driver.window_handles
            
            if len(todas_ventanas) > 1:
                ventana_nueva = todas_ventanas[-1]
                if ventana_nueva != ventana_principal:
                    print(f"Cambiando a ventana activa (total: {len(todas_ventanas)})")
                    driver.switch_to.window(ventana_nueva)
                    time.sleep(2)
                    return True
        except:
            pass
        
        time.sleep(0.5)
    
    # Fallback: usar última ventana si existe
    try:
        todas_ventanas = driver.window_handles
        if len(todas_ventanas) > 1:
            ventana_nueva = todas_ventanas[-1]
            print(f"Usando última ventana disponible (total: {len(todas_ventanas)})")
            driver.switch_to.window(ventana_nueva)
            time.sleep(2)
            return True
    except:
        pass
    
    raise TimeoutError(f"No se abrio ninguna ventana después de {timeout} segundos")

# --- FUNCIÓN DE APOYO ---
def obtener_escrituras_descargadas():
    """Obtiene las escrituras ya descargadas"""
    descargadas = set()
    if os.path.exists(download_folder):
        for archivo in os.listdir(download_folder):
            esc = extract_escritura_from_filename(archivo)
            if esc:
                descargadas.add(esc)
    return descargadas

def obtener_escrituras_con_pdf(carpeta):
    s = set()
    for f in os.listdir(carpeta):
        if f.lower().endswith(".pdf"):
            esc = extract_escritura_from_filename(f)
            if esc:
                s.add(esc)
    return s

def preparar_listos_para_enviar(df, carpeta_pdfs):
    if "estado_ctl" in df.columns:
        estados = df["estado_ctl"].apply(normalize_estado_ctl_value)
        pagos = df["pago"].apply(lambda value: "Ingresado" if is_pago_ingresado(value) else str(value).strip())
        mask_pend = (~estados.eq("Enviado")) & pagos.eq("Ingresado")
    else:
        mask_pend = pd.Series([True] * len(df), index=df.index)

    con_pdf = obtener_escrituras_con_pdf(carpeta_pdfs)
    mask_pdf = df["escritura_str"].isin(con_pdf)

    return df[mask_pend & mask_pdf].copy()

def buscar_pdf_en_carpeta(carpeta, escritura):
    escritura_norm = normalize_escritura(escritura)
    if not escritura_norm:
        return None

    for f in os.listdir(carpeta):
        if not f.lower().endswith(".pdf"):
            continue
        base = os.path.splitext(f)[0]
        nombre = normalize_text(base).lower()
        if (
            nombre == escritura_norm
            or nombre.startswith(escritura_norm + " ")
            or nombre.startswith(escritura_norm + "_")
            or nombre.startswith(escritura_norm + "-")
            or re.search(rf"\b{re.escape(escritura_norm)}\b", nombre)
        ):
            return os.path.join(carpeta, f)
    return None    

def normalizar(valor):
    txt = str(valor).strip()
    return txt[:-2] if txt.endswith('.0') else txt

escrituras_descargadas = obtener_escrituras_con_pdf(download_folder)
# --- PROCESO PRINCIPAL ---

pendientes_supabase = get_pending_certificados_liq(limit=10000, page=1, sort_by='escritura', desc=False)
df_pendientes = pd.DataFrame(pendientes_supabase.data or [])

if not df_pendientes.empty:
    if 'escritura_str' not in df_pendientes.columns:
        df_pendientes['escritura_str'] = df_pendientes['escritura'].apply(normalizar)
    if 'nir_str' not in df_pendientes.columns:
        df_pendientes['nir_str'] = df_pendientes['nir'].apply(normalizar)
    if 'estado_ctl' in df_pendientes.columns:
        df_pendientes['estado_ctl'] = df_pendientes['estado_ctl'].fillna("").astype(str).str.strip().apply(normalize_estado_ctl_value)

    df_pendientes = df_pendientes[
        (df_pendientes['escritura_str'] != "") & 
        (df_pendientes['nir_str'] != "")
    ].copy()
else:
    df_pendientes = pd.DataFrame(columns=['escritura_str', 'nir_str', 'estado_ctl', 'pago', 'correo', 'gobernacion', 'nir', 'escritura'])

print(f"Pendientes a procesar: {len(df_pendientes)}\n")

# Excluir escrituras que ya están en la carpeta de descargas para evitar redescargas
escrituras_descargadas = obtener_escrituras_con_pdf(download_folder)
if not isinstance(escrituras_descargadas, set):
    escrituras_descargadas = set(escrituras_descargadas)

# Filtrar pendientes para no procesar escrituras ya descargadas
antes = len(df_pendientes)
df_pendientes = df_pendientes[~df_pendientes['escritura_str'].isin(escrituras_descargadas)].copy()
skipped = antes - len(df_pendientes)
if skipped:
    print(f"[INFO] Se omiten {skipped} escrituras porque ya existen en la carpeta de descargas")
    print("[INFO] Estas escrituras no se marcan como 'Descargado' automáticamente; se marcarán solo después de una descarga real.")

if len(df_pendientes) == 0:
    print(" Todos los certificados ya han sido descargados!")
    print("\n OPCIONES:")
    print("   1. Si necesitas REPROCESAR TODO, descomenta esta línea:")
    print("      # escrituras_descargadas = set()  # Vaciar set")
    print("      # df_pendientes = df.copy()")
    print("   2. O borra archivos de la carpeta de descargas:")
    print(f"      {download_folder}")
    driver.quit()
else:
    procesados = 0
    errores = 0
    
    for index, row in df_pendientes.iterrows():
        nir = str(int(float(row["nir"])))
        escritura = str(int(float(row["escritura"])))

        print(f"\n{'='*60}")
        print(f"Procesando: {escritura}")
        print(f"{'='*60}")

        obs = []
        try:
            
            # Validar que driver esté funcional
            try:
                ventana_principal = driver.current_window_handle
            except:
                print(f"[ERROR] Driver desconectado, reiniciando...")
                if service:
                    driver = webdriver.Edge(service=service, options=edge_options)
                else:
                    driver = webdriver.Edge(options=edge_options)
                wait = WebDriverWait(driver, 10)
                ventana_principal = driver.current_window_handle
            
            try:
                driver.execute_cdp_cmd("Page.setDownloadBehavior", {
                    "behavior": "allow",
                    "downloadPath": download_folder
                })
            except Exception as e:
                print(f"[ERROR] No se pudo aplicar CDP DownloadBehavior:", e)
            
            driver.get("https://radicacion.supernotariado.gov.co/app/inicio.dma")
            
            print(f"[INFO] Buscando 'Certificados'...")
            wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Certificados"))).click()
            time.sleep(2)
            
            print(f"[INFO] Ingresando NIR: {nir}")
            input_nir = wait.until(EC.presence_of_element_located((By.ID, "formSearch:j_idt44")))
            input_nir.clear()
            input_nir.send_keys(nir)
            obs.append("Búsqueda iniciada")
            
            print(f"[INFO] Buscando...")
            boton_buscar = driver.find_element(By.ID, "formSearch:j_idt45")
            boton_buscar.click()
            time.sleep(3)
            
            print(f"[INFO] Buscando botones de descarga...")
            try:
                # Usar la nueva función para descargar MÚLTIPLES archivos
                archivos_descargados = descargar_multiples_archivos(driver, wait, escritura)

                if archivos_descargados:
                    print(f"[INFO] Se descargaron {len(archivos_descargados)} archivo(s)")
                    obs.append(f"Descargados {len(archivos_descargados)} archivos")
                    # Actualizar también en la tabla liq en Supabase - usar activity_type='cert_download'
                    try:
                        update_liq_estado_by_escritura(escritura, "Descargado", activity_type='cert_download')
                        insert_log("descarga_certificado", f"Escritura {escritura} marcada como Descargado", row.get('correo', ''))
                    except Exception as e:
                        print(f"[WARN] No se pudo actualizar Supabase: {e}")
                    # Guardar cada archivo descargado en Supabase (subir bytes)
                    try:
                        for fname in archivos_descargados:
                            ruta_archivo = os.path.join(download_folder, fname)
                            try:
                                with open(ruta_archivo, "rb") as f:
                                    contenido = f.read()
                                try:
                                    guardar_descarga("certificado", escritura, fname, contenido, row.get('correo'))
                                    print(f"[INFO] Guardado en Supabase: {fname}")
                                except Exception as e:
                                    print(f"[WARN] No se pudo guardar en Supabase: {e}")
                            except Exception as e:
                                print(f"[WARN] No se pudo leer archivo {ruta_archivo}: {e}")
                    except Exception:
                        pass
                    print(f"  [INFO] CERTIFICADO(S) OK")
                    procesados += 1
                else:
                    print(f"  [ERROR] No se pudo descargar ningún archivo")
                    print(f"[ERROR] Fallo descarga")
                    obs.append("Fallo descarga")
                    errores += 1
                    # Registrar en logs de Supabase el fallo
                    try:
                        insert_log("descarga_certificado_error", f"Escritura {escritura} - no files downloaded", row.get('correo', ''), "error")
                    except Exception:
                        pass
            except Exception as e:
                print(f"  [ERROR] Error: {str(e)[:100]}")
                errores += 1
                try:
                    insert_log("descarga_certificado_error", f"Escritura {escritura} - exception {str(e)[:200]}", row.get('correo', ''), "error")
                except Exception:
                    pass
            
            # Limpiar ventanas
            try:
                ventanas_ahora = driver.window_handles
                if len(ventanas_ahora) > 1 and ventana_principal in ventanas_ahora:
                    driver.close()
                    time.sleep(1)
                    driver.switch_to.window(ventana_principal)
            except:
                pass

        except Exception as e:
            print(f"\n[ERROR] Error: {str(e)[:100]}")
            errores += 1
            try:
                ventanas = driver.window_handles
                if ventana_principal in ventanas:
                    driver.switch_to.window(ventana_principal)
            except:
                pass
            df_pendientes.at[index, 'Resultado'] = "; ".join(obs)
            continue

        df_pendientes.at[index, 'Resultado'] = "; ".join(obs)

    driver.quit()    
    
    print("\n" + "="*50)
    print("[INFO] RESUMEN DEL PROCESO")
    print("="*50)
    print(f"[OK] Descargados en esta sesión: {procesados}")
    print(f"[ERROR] Con errores: {errores}")
    print(f"[INFO] Total en carpeta: {len(obtener_escrituras_descargadas())}")
    print("="*50)