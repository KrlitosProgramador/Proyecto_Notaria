from supabase_client import get_pending_certificados_liq, normalize_escritura
import os

result = get_pending_certificados_liq(limit=10)
print(f"Total pendientes: {len(result.data) if result.data else 0}\n")

if result.data:
    print("Registros pendientes vs archivos disponibles:\n")
    for row in result.data[:8]:
        escritura = row.get('escritura')
        escritura_str = normalize_escritura(escritura)
        estado_ctl = row.get('estado_ctl')
        
        # Buscar archivos
        carpeta = 'descargas/certificados'
        archivos = []
        for f in os.listdir(carpeta):
            if f.lower().endswith(('.pdf', '.doc', '.docx')):
                if f.startswith(str(escritura_str)):
                    archivos.append(f)
        
        tiene_archivo = "SÍ" if archivos else "NO"
        print(f"Escritura: {escritura:5} (norm: {escritura_str:5}) | Estado: {estado_ctl:20} | Archivo: {tiene_archivo}")
        if archivos:
            print(f"  -> {archivos[0][:60]}")
