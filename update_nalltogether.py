import pandas as pd

# Dosyayı oku
main_df = pd.read_csv('nalltogether.csv', dtype=str)

# BOND_ kolonunu sil
if 'BOND_' in main_df.columns:
    main_df = main_df.drop(columns=['BOND_'])

# CRDT_SCORE kolonunda NR olanları 8 ile değiştir
if 'CRDT_SCORE' in main_df.columns:
    main_df['CRDT_SCORE'] = main_df['CRDT_SCORE'].replace('NR', '8')

# Sonucu kaydet
main_df.to_csv('nalltogether.csv', index=False)
print('nalltogether.csv güncellendi (BOND_ silindi, CRDT_SCORE NR->8).') 