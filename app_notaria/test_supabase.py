from supabase_client import get_supabase

def test_conexion():
    supabase = get_supabase()
    if not supabase:
        print("Supabase no está configurado. Añade SUPABASE_URL y SUPABASE_KEY en .env para pruebas.")
        return False
    try:
        res = supabase.table("certificados").select("*").limit(1).execute()
        print("✓ Conexión a Supabase OK")
        return True
    except Exception as e:
        print(f"✗ Error de conexión: {e}")
        return False

if __name__ == '__main__':
    test_conexion()
