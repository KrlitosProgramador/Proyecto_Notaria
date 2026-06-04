import argparse
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "Debe definir SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY o SUPABASE_KEY en el archivo .env."
    )

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def normalize_value(value):
    if pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        return value if value != "" else None
    return value


def load_excel_rows(path: Path):
    df = pd.read_excel(path, dtype=str)
    df = df.rename(
        columns={
            "escritura": "escritura",
            "correo": "correo",
            "gobernacion": "gobernacion",
            "nir": "nir",
            "notificacion": "notificacion",
            "pago": "pago",
            "estado_ctl": "estado_ctl",
            "devolucion": "devolucion",
            "escritura_str": "escritura_str",
        }
    )
    df = df.where(pd.notna(df), None)

    rows = []
    for row in df.to_dict(orient="records"):
        cleaned = {k: normalize_value(v) for k, v in row.items() if k is not None}
        if cleaned:
            rows.append(cleaned)
    return rows


def insert_rows(supabase, rows, batch_size=100):
    if not rows:
        print("No hay filas para insertar.")
        return 0

    total_inserted = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        try:
            result = supabase.table("liq").insert(batch).execute()
        except Exception as exc:
            raise RuntimeError(
                "Error al insertar datos en Supabase. Verifica que la tabla liq exista y que la clave usada tenga permisos de inserción."
            ) from exc

        if getattr(result, "error", None):
            raise RuntimeError(
                f"Error al insertar lote: {result.error}. "
                "Si estás usando la llave pública anon, puede que la política de seguridad (RLS) impida insertar datos. "
                "Usa SUPABASE_SERVICE_ROLE_KEY o carga los datos desde el SQL editor de Supabase."
            )

        total_inserted += len(batch)
        print(f"Insertadas {total_inserted}/{len(rows)} filas...")

    return total_inserted


def main():
    parser = argparse.ArgumentParser(description="Importa Informe.xlsx a la tabla Supabase liq.")
    parser.add_argument(
        "--excel",
        default="Informe.xlsx",
        help="Ruta al archivo Excel que contiene los registros (por defecto: Informe.xlsx)",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=100,
        help="Tamaño de lote para inserciones en Supabase",
    )
    args = parser.parse_args()

    excel_path = Path(args.excel).expanduser().resolve()
    if not excel_path.exists():
        raise FileNotFoundError(f"No existe el archivo Excel: {excel_path}")

    if supabase is None:
        raise RuntimeError(
            "Supabase no está configurado. Revisa SUPABASE_URL y SUPABASE_KEY en el archivo .env."
        )

    rows = load_excel_rows(excel_path)
    print(f"Filas leídas desde {excel_path}: {len(rows)}")

    if len(rows) == 0:
        print("No se encontraron filas válidas en el Excel.")
        return

    inserted = insert_rows(supabase, rows, batch_size=args.batch)
    print(f"Importación completada. Filas insertadas: {inserted}")


if __name__ == "__main__":
    main()
