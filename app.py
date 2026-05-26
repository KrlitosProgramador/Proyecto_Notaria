import os
import sys
import uuid
import threading
import subprocess
import io
import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()
from supabase_client import (
    insert_log,
    get_supabase,
    insert_certificado,
    update_certificado_estado,
    get_certificados_por_usuario,
    insert_recibo,
    import_liq_from_rows,
)
from supabase_client import insert_liq_row, update_liq_row, get_pending_liq, update_liq_estado_by_escritura
from supabase_client import get_liq_stats
from supabase_client import get_all_liq, get_processed_liq

APP_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(APP_DIR, "static")

app = FastAPI()

# Servir tu HTML tal cual
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

JOBS = {}  # job_id -> {"status": "running|done|error", "logs": [str], "returncode": int|None}

def _append(job_id: str, line: str):
    JOBS[job_id]["logs"].append(line.rstrip())

def _run_certificados_job(job_id: str):
    """
    Ejecuta certificados.py como subproceso (sin BAT),
    captura stdout/stderr y lo deja en JOBS[job_id]["logs"].
    """
    try:
        JOBS[job_id]["status"] = "running"
        script_path = os.path.join(APP_DIR, "certificados.py")

        # Ejecuta con el mismo Python del entorno
        proc = subprocess.Popen(
            [sys.executable, script_path],
            cwd=APP_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        for line in proc.stdout:
            _append(job_id, line)

        proc.wait()
        JOBS[job_id]["returncode"] = proc.returncode
        if proc.returncode == 0:
            JOBS[job_id]["status"] = "done"
        else:
            JOBS[job_id]["status"] = "error"
            _append(job_id, f"[ERROR] certificados.py terminó con código {proc.returncode}")

    except Exception as e:
        JOBS[job_id]["status"] = "error"
        _append(job_id, f"[EXCEPTION] {type(e).__name__}: {e}")

@app.get("/", response_class=HTMLResponse)
def home():
    # Carga tu UI
    html_path = os.path.join(STATIC_DIR, "notaria_app.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/descargas/certificados/start")
def start_descarga_certificados():
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "queued", "logs": [], "returncode": None}
    t = threading.Thread(target=_run_certificados_job, args=(job_id,), daemon=True)
    t.start()
    # Registrar inicio en logs (si supabase no está configurado, se imprimirá)
    try:
        insert_log("descarga_certificados", f"Job iniciado: {job_id}", "sistema")
    except Exception:
        pass
    return {"job_id": job_id}

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job_id no existe")
    return job

@app.get("/api/liq/pending")
def listar_pending(limit: int = 100, page: int = 1, sort_by: str = 'escritura', desc: bool = False):
    try:
        if not get_supabase():
            raise HTTPException(status_code=503, detail="Supabase no configurado. Verifique SUPABASE_URL y SUPABASE_KEY en .env")
        res = get_pending_liq(limit=limit, page=page, sort_by=sort_by, desc=desc)
        return res.data
    except Exception as e:
        insert_log("consulta_liq", str(e), "sistema", "error")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/liq/stats")
def liq_stats():
    """Devuelve estadísticas agregadas para la UI: total, pendientes y procesados."""
    try:
        if not get_supabase():
            raise HTTPException(status_code=503, detail="Supabase no configurado. Verifique SUPABASE_URL y SUPABASE_KEY en .env")
        stats = get_liq_stats()
        return stats
    except Exception as e:
        try:
            insert_log("stats_liq", str(e), "sistema", "error")
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/liq/all")
def liq_all(limit: int = 1000, page: int = 1, sort_by: str = 'updated_at', desc: bool = True):
    try:
        if not get_supabase():
            raise HTTPException(status_code=503, detail="Supabase no configurado. Verifique SUPABASE_URL y SUPABASE_KEY en .env")
        # Limitar el tamaño de página para evitar rangos excesivos en Supabase.
        max_limit = min(max(limit, 1), 10000)
        res = get_all_liq(limit=max_limit, page=max(page, 1), sort_by=sort_by, desc=desc)
        return res.data
    except Exception as e:
        insert_log("consulta_liq_all", str(e), "sistema", "error")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/liq")
def create_liq_row(body: dict):
    try:
        if not get_supabase():
            raise HTTPException(status_code=503, detail="Supabase no configurado. Verifique SUPABASE_URL y SUPABASE_KEY en .env")
        result = insert_liq_row(body)
        return {"status": "ok", "inserted": result.data}
    except Exception as e:
        insert_log("insert_liq", str(e), "sistema", "error")
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/liq/{escritura}")
def patch_liq_row(escritura: str, body: dict):
    try:
        if not get_supabase():
            raise HTTPException(status_code=503, detail="Supabase no configurado. Verifique SUPABASE_URL y SUPABASE_KEY en .env")
        result = update_liq_row(escritura, body)
        return {"status": "ok", "updated": result.data}
    except Exception as e:
        insert_log("update_liq", str(e), "sistema", "error")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/liq/processed")
def liq_processed(limit: int = 1000, page: int = 1, sort_by: str = 'fecha_proceso', desc: bool = True):
    try:
        if not get_supabase():
            raise HTTPException(status_code=503, detail="Supabase no configurado. Verifique SUPABASE_URL y SUPABASE_KEY en .env")
        res = get_processed_liq(limit=limit, page=page, sort_by=sort_by, desc=desc)
        return res.data
    except Exception as e:
        insert_log("consulta_liq_processed", str(e), "sistema", "error")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/liq/{escritura}/mark")
def mark_escritura(escritura: str, estado: str):
    try:
        res = update_liq_estado_by_escritura(escritura, estado)
        return {"status": "ok", "updated": res.data}
    except Exception as e:
        insert_log("update_liq", str(e), "sistema", "error")
        raise HTTPException(status_code=500, detail=str(e))


# Endpoints para Supabase
@app.get("/api/certificados")
def listar_certificados(usuario: str = None):
    try:
        supabase = get_supabase()
        if usuario:
            result = supabase.table("certificados").select("*").eq("usuario", usuario).execute()
            return result.data
        result = supabase.table("certificados").select("*").execute()
        return result.data
    except Exception as e:
        insert_log("consulta_certificados", str(e), usuario or "sistema", "error")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/certificados/{cert_id}")
def obtener_certificado(cert_id: str):
    try:
        supabase = get_supabase()
        result = supabase.table("certificados").select("*").eq("id", cert_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Certificado no encontrado")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        insert_log("consulta_certificado", str(e), "sistema", "error")
        raise HTTPException(status_code=500, detail=str(e))

# --- agrega estas funciones/endpoint a tu app.py ---

def _run_envio_recibos_job(job_id: str):
    """
    Ejecuta envio_recibos.py como subproceso (sin BAT),
    captura stdout/stderr y lo deja en JOBS[job_id]["logs"].
    """
    try:
        JOBS[job_id]["status"] = "running"
        script_path = os.path.join(APP_DIR, "envio_recibos.py")

        proc = subprocess.Popen(
            [sys.executable, script_path],
            cwd=APP_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        for line in proc.stdout:
            _append(job_id, line)

        proc.wait()
        JOBS[job_id]["returncode"] = proc.returncode
        if proc.returncode == 0:
            JOBS[job_id]["status"] = "done"
        else:
            JOBS[job_id]["status"] = "error"
            _append(job_id, f"[ERROR] envio_recibos.py terminó con código {proc.returncode}")

    except Exception as e:
        JOBS[job_id]["status"] = "error"
        _append(job_id, f"[EXCEPTION] {type(e).__name__}: {e}")

@app.post("/api/envios/recibos/start")
def start_envio_recibos():
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "queued", "logs": [], "returncode": None}
    t = threading.Thread(target=_run_envio_recibos_job, args=(job_id,), daemon=True)
    t.start()
    return {"job_id": job_id}

@app.post("/api/envios/recibos/unico/start")
def start_envio_recibo_unico(body: dict):
    """Recibe un payload JSON para enviar un único recibo.
    Crea un archivo temporal con el payload y lanza envio_recibos.py --single <file> en hilo.
    """
    if not isinstance(body, dict) or not body.get("escritura"):
        raise HTTPException(status_code=400, detail="Escritura es obligatoria")

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "queued", "logs": [], "returncode": None}

    def _run_unico(job_id, payload):
        try:
            JOBS[job_id]["status"] = "running"
            # crear archivo temporal con payload
            import json, tempfile
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=".json", dir=APP_DIR, mode='w', encoding='utf-8')
            json.dump(payload, tf, ensure_ascii=False)
            tf.close()
            script_path = os.path.join(APP_DIR, "envio_recibos.py")
            proc = subprocess.Popen(
                [sys.executable, script_path, "--single", tf.name],
                cwd=APP_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in proc.stdout:
                _append(job_id, line)
            proc.wait()
            JOBS[job_id]["returncode"] = proc.returncode
            JOBS[job_id]["status"] = "done" if proc.returncode == 0 else "error"
        except Exception as e:
            JOBS[job_id]["status"] = "error"
            _append(job_id, f"[EXCEPTION] {type(e).__name__}: {e}")

    t = threading.Thread(target=_run_unico, args=(job_id, body), daemon=True)
    t.start()
    return {"job_id": job_id}


def _run_envio_certificados_job(job_id: str):
    try:
        JOBS[job_id]["status"] = "running"
        script_path = os.path.join(APP_DIR, "envio_certificados.py")

        proc = subprocess.Popen(
            [sys.executable, script_path],
            cwd=APP_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        for line in proc.stdout:
            _append(job_id, line)

        proc.wait()
        JOBS[job_id]["returncode"] = proc.returncode
        if proc.returncode == 0:
            JOBS[job_id]["status"] = "done"
        else:
            JOBS[job_id]["status"] = "error"
            _append(job_id, f"[ERROR] envio_certificados.py terminó con código {proc.returncode}")

    except Exception as e:
        JOBS[job_id]["status"] = "error"
        _append(job_id, f"[EXCEPTION] {type(e).__name__}: {e}")


@app.post("/api/envios/certificados/start")
def start_envio_certificados():
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "queued", "logs": [], "returncode": None}
    t = threading.Thread(target=_run_envio_certificados_job, args=(job_id,), daemon=True)
    t.start()
    return {"job_id": job_id}


@app.post("/api/envios/certificados/unico/start")
def start_envio_certificado_unico(body: dict):
    if not isinstance(body, dict) or not body.get("escritura"):
        raise HTTPException(status_code=400, detail="Escritura es obligatoria")

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "queued", "logs": [], "returncode": None}

    def _run_unico(job_id, payload):
        try:
            JOBS[job_id]["status"] = "running"
            import json, tempfile
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=".json", dir=APP_DIR, mode='w', encoding='utf-8')
            json.dump(payload, tf, ensure_ascii=False)
            tf.close()

            script_path = os.path.join(APP_DIR, "envio_certificados.py")
            proc = subprocess.Popen(
                [sys.executable, script_path, "--single", tf.name],
                cwd=APP_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in proc.stdout:
                _append(job_id, line)

            proc.wait()
            JOBS[job_id]["returncode"] = proc.returncode
            JOBS[job_id]["status"] = "done" if proc.returncode == 0 else "error"
        except Exception as e:
            JOBS[job_id]["status"] = "error"
            _append(job_id, f"[EXCEPTION] {type(e).__name__}: {e}")

    t = threading.Thread(target=_run_unico, args=(job_id, body), daemon=True)
    t.start()
    return {"job_id": job_id}


@app.post("/api/import/excel")
async def import_excel_file(file: UploadFile = File(...), table: str = "liq"):
    """
    Carga un archivo Excel dinámicamente y lo importa en Supabase.
    Solo carga registros nuevos (detecta duplicados por escritura).
    """
    try:
        if not get_supabase():
            raise HTTPException(status_code=503, detail="Supabase no configurado.")
        
        # Validar nombre de tabla
        allowed_tables = ["liq", "pagos"]
        if table not in allowed_tables:
            raise HTTPException(status_code=400, detail=f"Tabla no válida. Permitidas: {allowed_tables}")
        
        # Leer archivo Excel
        contents = await file.read()
        excel_file = io.BytesIO(contents)
        
        # Parsear Excel
        df = pd.read_excel(excel_file, dtype=str)
        df = df.where(pd.notna(df), None)
        
        # Convertir a lista de dicts
        rows = df.to_dict(orient="records")
        
        # Limpiar y validar filas
        cleaned_rows = []
        for row in rows:
            cleaned = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k and v}
            if cleaned:
                cleaned_rows.append(cleaned)
        
        # Importar solo registros nuevos
        if table == "liq":
            result = import_liq_from_rows(cleaned_rows, batch_size=100)
        else:
            # Para otras tablas, puedes agregar lógica similar
            result = {"total": len(cleaned_rows), "nuevos": 0, "duplicados": 0, "errores": 0, "mensaje": f"Tabla {table} no implementada aún"}
        
        # Registrar en logs
        insert_log("import_excel", f"Archivo {file.filename} importado en tabla {table}: {result['nuevos']} nuevos", "sistema")
        
        return {"status": "ok", "import_result": result}
    
    except HTTPException:
        raise
    except Exception as e:
        insert_log("import_excel_error", str(e), "sistema", "error")
        raise HTTPException(status_code=500, detail=f"Error al procesar archivo: {str(e)}")
