import pandas as pd
import glob

# FINEK dosyalarını bul
finek_files = glob.glob('finek*.csv')
print(f'Bulunan FINEK dosyaları: {len(finek_files)}')

# Her dosyadan 'Adj risk premium' kolonunu sil
for file in finek_files:
    df = pd.read_csv(file, encoding='utf-8-sig')
    
    if 'Adj risk premium' in df.columns:
        df = df.drop(columns=['Adj risk premium'])
        df.to_csv(file, index=False, encoding='utf-8-sig')
        print(f'✓ {file}: Adj risk premium kolonu silindi')
    else:
        print(f'  {file}: Adj risk premium kolonu yoktu')

print('\n✓ Tüm FINEK dosyalarından Adj risk premium kolonu silindi!') 