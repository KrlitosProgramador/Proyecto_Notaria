import os
import sys
import importlib.util

# Cargar app_notaria/app.py como módulo y obtener el objeto `app`
APP_DIR = os.path.join(os.path.dirname(__file__), "app_notaria")
APP_PATH = os.path.join(APP_DIR, "app.py")

spec = importlib.util.spec_from_file_location("app_module", APP_PATH)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
# Asegurar que los imports absolutos dentro de app.py (p.ej. supabase_client)
# puedan resolverse añadiendo la carpeta app_notaria al sys.path
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

spec.loader.exec_module(module)
app = getattr(module, "app")

if __name__ == "__main__":
    try:
        import uvicorn
        uvicorn.run(app, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", 8000)))
    except Exception as e:
        print("Error arrancando servidor:", e)
