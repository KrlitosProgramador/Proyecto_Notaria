import argparse
import os
import re
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DEFAULT_EXCEL_PATH = Path(os.getenv("EXCEL_PATH", "../Informe.xlsx"))
DEFAULT_OUTPUT_SQL = Path("supabase_schema_from_excel.sql")

SQL_TYPE_MAP = {
    "int": "bigint",
    "numeric": "numeric",
    "timestamp": "timestamptz",
    "boolean": "boolean",
    "text": "text",
}

TEXT_FAVORITES = [
    "escritura",
    "nir",
    "correo",
    "email",
    "estado",
    "pago",
    "notificacion",
    "devolucion",
    "gobernacion",
    "usuario",
    "nombre",
    "direccion",
    "tipo",
    "documento",
]

DATE_KEYWORDS = ["fecha", "date", "timestamp", "hora", "tiempo"]
NUMERIC_KEYWORDS = ["monto", "valor", "importe", "total", "costo", "precio", "cantidad", "num"]
BOOLEAN_VALUES = {"true", "false", "si", "no", "sí", "0", "1"}


def clean_name(name: str) -> str:
    out = re.sub(r"[^0-9a-zA-Z_]+", "_", name.strip().lower())
    out = re.sub(r"__+", "_", out).strip("_")
    if not out:
        out = "column"
    if re.match(r"^[0-9]", out):
        out = "col_" + out
    return out


def detect_header_row(sheet: pd.DataFrame) -> int:
    for i in range(min(20, len(sheet))):
        row = sheet.iloc[i].astype(str).str.lower().fillna("")
        if row.str.contains("escritura").any() or row.str.contains("correo").any():
            return i
    return 0


def choose_sql_type(column_name: str, values: pd.Series) -> str:
    name = column_name.lower()
    if name.endswith("_str"):
        return SQL_TYPE_MAP["text"]
    if any(keyword in name for keyword in DATE_KEYWORDS):
        return SQL_TYPE_MAP["timestamp"]
    if any(keyword in name for keyword in NUMERIC_KEYWORDS):
        return SQL_TYPE_MAP["numeric"]

    values = values.dropna().astype(str).str.strip()
    if len(values) == 0:
        return SQL_TYPE_MAP["text"]

    if values.str.lower().isin(BOOLEAN_VALUES).all():
        return SQL_TYPE_MAP["boolean"]

    if values.str.match(r"^-?\d+$").all():
        if name not in TEXT_FAVORITES:
            return SQL_TYPE_MAP["int"]
        return SQL_TYPE_MAP["text"]

    if values.str.match(r"^-?\d+\.?\d*$").all():
        if name not in TEXT_FAVORITES:
            return SQL_TYPE_MAP["numeric"]
        return SQL_TYPE_MAP["text"]

    return SQL_TYPE_MAP["text"]


def table_name_from_sheet(sheet_name: str) -> str:
    name = clean_name(sheet_name)
    if not name:
        return "sheet_table"
    return name


def generate_create_table_sql(sheet_name: str, columns: list[tuple[str, str]]) -> str:
    lines = [f"create table if not exists {sheet_name} (",
             "  id uuid primary key default gen_random_uuid(),"]
    for col_name, col_type in columns:
        lines.append(f"  {col_name} {col_type},")
    lines.extend([
        "  created_at timestamptz default now(),",
        "  updated_at timestamptz default now()",
        ");",
        "",
    ])
    return "\n".join(lines)


def parse_sheet(path: Path, sheet_name: str) -> list[tuple[str, str]]:
    xls = pd.ExcelFile(path)
    raw = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=str)
    header_row = detect_header_row(raw)
    df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]

    if df.empty:
        return []

    parsed_columns: list[tuple[str, str]] = []
    for original_name in df.columns:
        if original_name is None or str(original_name).strip() == "":
            continue
        clean = clean_name(str(original_name))
        values = df[original_name]
        sql_type = choose_sql_type(original_name, values)
        parsed_columns.append((clean, sql_type))
    return parsed_columns


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera SQL de tablas Supabase a partir de un Excel.")
    parser.add_argument("--excel", default=os.getenv("EXCEL_PATH", str(DEFAULT_EXCEL_PATH)), help="Ruta al archivo Excel (por defecto: EXCEL_PATH o ../Informe.xlsx)")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT_SQL), help="Archivo SQL de salida")
    parser.add_argument("--sheet", default=None, help="Nombre de la hoja a procesar. Si no se especifica, genera todas las hojas.")
    args = parser.parse_args()

    excel_path = Path(args.excel).expanduser().resolve()
    if not excel_path.exists():
        raise FileNotFoundError(f"No existe el archivo Excel: {excel_path}")

    xls = pd.ExcelFile(excel_path)
    sheets = [args.sheet] if args.sheet else xls.sheet_names
    sql_blocks = []

    for sheet in sheets:
        if sheet not in xls.sheet_names:
            raise ValueError(f"La hoja '{sheet}' no existe en {excel_path}")
        print(f"Procesando hoja: {sheet}")
        columns = parse_sheet(excel_path, sheet)
        if not columns:
            print(f"Advertencia: la hoja '{sheet}' está vacía o no tiene datos válidos. Se omite.")
            continue
        table_name = table_name_from_sheet(sheet)
        if not any(col[0] == "escritura" for col in columns):
            print(f"Advertencia: la hoja '{sheet}' no contiene una columna 'escritura' reconocida.")
        sql_blocks.append(generate_create_table_sql(table_name, columns))

    output_path = Path(args.out).expanduser().resolve()
    output_path.write_text("\n".join(sql_blocks), encoding="utf-8")
    print(f"Archivo SQL generado: {output_path}")


if __name__ == "__main__":
    main()
