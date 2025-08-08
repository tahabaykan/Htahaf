import pandas as pd
import glob

# ADV dosyasını yükle
adv_df = pd.read_csv('advekheldkuponlu.csv', encoding='utf-8-sig')
print(f"ADV dosyası: {len(adv_df)} satır")
print(f"ADV kolonları: {[col for col in adv_df.columns if 'Adj' in col]}")

# YEK dosyalarını yükle
yek_files = [f for f in glob.glob('*.csv') if 'yek' in f.lower()]
print(f"YEK dosyaları: {len(yek_files)}")

# YEK verilerini birleştir
yek_data = []
for file in yek_files:
    df = pd.read_csv(file, encoding='utf-8-sig')
    df['source_file'] = file
    yek_data.append(df)
    print(f"✓ {file}: {len(df)} satır")

if yek_data:
    ibkr_df = pd.concat(yek_data, ignore_index=True)
    print(f"Toplam YEK verisi: {len(ibkr_df)} satır")
    print(f"YEK kolonları: {[col for col in ibkr_df.columns if 'Adj' in col]}")
    
    # YEK dosyalarından sadece Adj Risk Premium kolonunu al
    yek_data_filtered = ibkr_df[ibkr_df['source_file'].str.contains('yek', case=False, na=False)].copy()
    print(f"YEK dosyalarından veri: {len(yek_data_filtered)} satır")
    
    # Geçerli Adj Risk Premium değerleri olan satırları filtrele
    clean_yek_data = yek_data_filtered[yek_data_filtered['Adj Risk Premium'].notna()].copy()
    print(f"YEK verilerinde geçerli Adj Risk Premium değeri: {len(clean_yek_data)} satır")
    
    # Duplicate'leri kaldır
    clean_yek_data = clean_yek_data.sort_values('Adj Risk Premium', ascending=False).drop_duplicates(subset=['PREF IBKR'], keep='first')
    print(f"Duplicate'ler kaldırıldıktan sonra: {len(clean_yek_data)} satır")
    
    # Merge yap
    result_df = adv_df.merge(
        clean_yek_data[['PREF IBKR', 'Adj Risk Premium']], 
        on='PREF IBKR',
        how='left'
    )
    
    print(f"Merge sonrası: {len(result_df)} satır")
    print(f"Adj Risk Premium birleştirildi: {result_df['Adj Risk Premium'].notna().sum()}/{len(result_df)} hisse")
    
    # GPJA kontrol
    gpja_data = result_df[result_df['PREF IBKR'] == 'GPJA']
    if len(gpja_data) > 0:
        print(f"GPJA Adj Risk Premium: {gpja_data['Adj Risk Premium'].iloc[0]}")
    else:
        print("GPJA bulunamadı!")
else:
    print("YEK verisi bulunamadı!") 