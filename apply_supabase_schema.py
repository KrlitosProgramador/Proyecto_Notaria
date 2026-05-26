import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

SQL_PATH = Path("supabase_schema_from_excel.sql")
DB_URL = os.getenv("SUPABASE_DB_URL")

HELPER = """
Este script no crea tablas si no se proporciona SUPABASE_DB_URL.

Opciones:
  - Establece SUPABASE_DB_URL en app_notaria/.env con tu cadena de conexión Postgres.
  - Instala psycopg con `pip install psycopg[binary]`.
  - Ejecuta este script para aplicar el SQL generado.

Si no tienes SUPABASE_DB_URL, copia el SQL de `supabase_schema_from_excel.sql`
al editor SQL de Supabase y ejecútalo manualmente.
"""


def load_sql(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo SQL: {path}")
    return path.read_text(encoding="utf-8")


def apply_sql_with_psycopg(db_url: str, sql: str) -> None:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "Instala psycopg con `pip install psycopg[binary]` para ejecutar SQL directamente."
        ) from exc

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


if __name__ == "__main__":
    sql = load_sql(SQL_PATH)
    print(f"Archivo SQL cargado: {SQL_PATH}")
    print("---\n")
    if DB_URL:
        print("SUPABASE_DB_URL encontrada. Intentando aplicar el SQL directamente...")
        try:
            apply_sql_with_psycopg(DB_URL, sql)
            print("✔ Tablas creadas o actualizadas correctamente en Supabase.")
        except Exception as exc:
            print("✗ Error al aplicar el SQL:")
            print(exc)
            print("\nSi no tienes psycopg instalado, usa `pip install psycopg[binary]`.")
    else:
        print(HELPER)
        print("SQL generado:\n")
        print(sql)
