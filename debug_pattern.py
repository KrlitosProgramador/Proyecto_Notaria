import re
import os

test_cases = [
    ('149 Certificado', '149'),
    ('149Certificado', '149'),
    ('1499', '149'),
    ('177 Certificado_1', '177'),
]

print("=== REGEX PATTERN TEST ===")
for filename_base, escritura in test_cases:
    patron = re.compile(rf'^{re.escape(escritura)}(\D|$)', re.IGNORECASE)
    result = patron.search(filename_base)
    status = "MATCH" if result else "NO MATCH"
    print(f'{filename_base:30} + {escritura:5} -> {status}')

print("\n=== REAL FILE TEST ===")
carpeta = 'descargas/certificados'
escritura_test = '149'

archivos_encontrados = []
extensiones_validas = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt', '.jpg', '.png')

for f in os.listdir(carpeta):
    if not f.lower().endswith(extensiones_validas):
        continue
    
    # Mostrar si empieza con 149
    if f.startswith('149'):
        base = os.path.splitext(f)[0]
        patron = re.compile(rf'^{re.escape(escritura_test)}(\D|$)', re.IGNORECASE)
        match = patron.search(base)
        print(f'File: {f:40} -> Base: {base:30} -> Match: {match is not None}')
