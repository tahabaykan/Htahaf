import pandas as pd

# Dosyaları oku
main_df = pd.read_csv('nnotheldpff.csv', dtype=str)
cur_df = pd.read_csv('ekcurdata.csv', dtype=str)

# Merge için sadece gerekli kolonlar
merge_cols = ['PREF IBKR', 'QDI', 'Type', 'Sector', 'IG']
cur_df_sub = cur_df[merge_cols].copy()

# Merge işlemi (QDI, Type, Sector, IG ekle)
merged = main_df.merge(cur_df_sub, on='PREF IBKR', how='left', suffixes=('', '_ekcur'))

# QDI, Type, Sector, IG kolonlarını sona ekle (veya varsa güncelle)
for col in ['QDI', 'Type', 'Sector', 'IG']:
    col_ekcur = col + '_ekcur'
    if col_ekcur in merged.columns:
        merged[col] = merged[col_ekcur]
        merged = merged.drop(columns=[col_ekcur])

# BOND_ kolonunu sil
if 'BOND_' in merged.columns:
    merged = merged.drop(columns=['BOND_'])

# CRDT_SCORE kolonunda NR olanları 8 ile değiştir
if 'CRDT_SCORE' in merged.columns:
    merged['CRDT_SCORE'] = merged['CRDT_SCORE'].replace('NR', '8')

# Sonucu kaydet
merged.to_csv('nnotheldpff.csv', index=False)
print('nnotheldpff.csv güncellendi (QDI, Type, Sector, IG eklendi; BOND_ silindi; CRDT_SCORE NR->8).') 