import pandas as pd
p='Informe.xlsx'
xls=pd.ExcelFile(p)
sheet='Liq.' if 'Liq.' in xls.sheet_names else xls.sheet_names[0]
df=pd.read_excel(xls, sheet_name=sheet, dtype=str)
df.columns=df.columns.astype(str).str.strip()
print(df.columns.tolist())
print('---')
for col in df.columns:
    if 'not' in col.lower() or 'escrit' in col.lower() or 'pago' in col.lower() or 'correo' in col.lower():
        print(col)
print('---')
cols=[c for c in df.columns if 'escrit' in c.lower() or 'nir' in c.lower() or 'not' in c.lower() or 'pago' in c.lower() or 'correo' in c.lower()]
mask=df.astype(str).apply(lambda r:r.str.contains('1028', case=False, na=False)).any(axis=1)
print(df.loc[mask, cols].to_string(index=False))
