import os
import re
import pandas as pd

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib import colors


REPORTE_XLSX = r"C:\Users\EQUIPO 25\Desktop\Beneficencia\2025_pendientes.xlsx"
SALIDA_DIR = r"C:\Users\EQUIPO 25\Desktop\Beneficencia\Devolucion\pdf_devolucion"


def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")


def draw_field(c: canvas.Canvas, label: str, value, x: float, y: float,
               w: float = 17 * cm, h: float = 0.7 * cm):
    """Dibuja un campo tipo 'formato' (caja + etiqueta + valor)."""
    c.setStrokeColor(colors.black)
    c.rect(x, y - h, w, h, stroke=1, fill=0)

    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + 0.15 * cm, y - 0.5 * cm, label)

    c.setFont("Helvetica", 9)
    txt = "" if value is None else str(value)
    c.drawRightString(x + w - 0.15 * cm, y - 0.5 * cm, txt[:120])


def wrap_lines(text: str, max_len: int = 110, max_lines: int = 10):
    """Parte texto largo en líneas (útil para rutas)."""
    if text is None:
        return [""]

    lines_out = []
    for ln in str(text).splitlines():
        ln = ln.strip()
        if not ln:
            continue
        while len(ln) > max_len:
            lines_out.append(ln[:max_len])
            ln = ln[max_len:]
        lines_out.append(ln)

    if not lines_out:
        lines_out = [""]

    return lines_out[:max_lines]


def main():
    os.makedirs(SALIDA_DIR, exist_ok=True)

    # 1) Leer reporte
    df = pd.read_excel(REPORTE_XLSX, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]

    # Mapeo case-insensitive de columnas
    colmap = {c.lower(): c for c in df.columns}

    def col(name: str) -> str:
        return colmap.get(name, name)

    # 2) Filtrar solo estado OK (si existe columna)
    if col("estado") in df.columns:
        df_ok = df[df[col("estado")].astype(str).str.upper().str.contains("OK", na=False)].copy()
    else:
        df_ok = df.copy()

    # 3) Generar un PDF por fila
    for _, r in df_ok.iterrows():
        escritura = r.get(col("escritura"), "")
        nir = r.get(col("nir"), "")
        sobrante = r.get(col("sobrante_num"), "")
        pdfs = r.get(col("pdf_encontrados"), "")
        rutas = r.get(col("rutas_destino"), "")

        filename = safe_filename(f"Devolucion_Escritura_{escritura}_NIR_{nir}.pdf")
        out_path = os.path.join(SALIDA_DIR, filename)

        c = canvas.Canvas(out_path, pagesize=letter)
        width, height = letter

        # Encabezado (similar al formato)
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(width / 2, height - 1.7 * cm, "DEVOLUCIÓN")

        c.setFont("Helvetica", 10)
        c.drawCentredString(width / 2, height - 2.4 * cm, "PROCESO DE PAGO BENEFICENCIA Y REGISTRO 2025")

        x = 2.0 * cm
        y = height - 3.4 * cm

        # Campos principales (mapeados desde el reporte)
        draw_field(c, "ACTA DE DEPOSITO No.", escritura, x, y); y -= 1.0 * cm
        draw_field(c, "NIR", nir, x, y); y -= 1.0 * cm
        draw_field(c, "OBSERVACIONES: SOBRANTE", sobrante, x, y); y -= 1.0 * cm
        draw_field(c, "PDF ENCONTRADOS", pdfs, x, y); y -= 1.0 * cm

        # Caja de rutas destino
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y, "RUTAS DESTINO (según reporte):")
        y -= 0.4 * cm

        box_h = 4.0 * cm
        c.rect(x, y - box_h, 17 * cm, box_h, stroke=1, fill=0)

        c.setFont("Helvetica", 8)
        lines = wrap_lines(rutas, max_len=110, max_lines=10)
        ty = y - 0.3 * cm
        for ln in lines:
            c.drawString(x + 0.2 * cm, ty, ln)
            ty -= 0.35 * cm

        y = y - box_h - 0.8 * cm

        # Pie (firma / datos)
        c.setFont("Helvetica", 9)
        c.drawString(x, y, "FIRMA: ____________________________     NOMBRE CLARO: ____________________________")
        y -= 0.8 * cm
        c.drawString(x, y, "CÉDULA No.: ________________________     FECHA: _________________________________")

        c.showPage()
        c.save()

    print(f"Listo. PDFs generados en: {SALIDA_DIR}")


if __name__ == "__main__":
    main()