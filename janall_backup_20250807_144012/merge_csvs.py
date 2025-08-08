import pandas as pd

# CSV dosyalarının listesi
csv_files = [
    'ssfinekheldcilizyeniyedi.csv',
    'ssfinekheldcommonsuz.csv',
    'ssfinekhelddeznff.csv',
    'ssfinekheldff.csv',
    'ssfinekheldflr.csv',
    'ssfinekheldgarabetaltiyedi.csv',
    'ssfinekheldkuponlu.csv',
    'ssfinekheldkuponlukreciliz.csv',
    'ssfinekheldkuponlukreorta.csv',
    'ssfinekheldnff.csv',
    'ssfinekheldotelremorta.csv',
    'ssfinekheldsolidbig.csv',
    'ssfinekheldtitrekhc.csv',
    'ssfinekhighmatur.csv',
    'ssfineknotbesmaturlu.csv',
    'ssfineknotcefilliquid.csv',
    'ssfineknottitrekhc.csv',
    'ssfinekrumoreddanger.csv',
    'ssfineksalakilliquid.csv',
    'ssfinekshitremhc.csv'
]

# Tüm dataframe'leri bir listede topla
dfs = []
for file in csv_files:
    try:
        df = pd.read_csv(file)
        print(f"✅ {file} okundu: {len(df)} satır")
        dfs.append(df)
    except Exception as e:
        print(f"❌ {file} okunamadı: {e}")

if not dfs:
    print("❌ Hiçbir CSV dosyası okunamadı!")
    exit(1)

# Tüm dataframe'leri birleştir
merged_df = pd.concat(dfs, ignore_index=True)

# Duplicate satırları çıkar ('PREF IBKR' kolonuna göre)
merged_df = merged_df.drop_duplicates(subset=['PREF IBKR'], keep='first')

# Sonucu kaydet
merged_df.to_csv('janalldata.csv', index=False)
print(f"\n✅ Birleştirme tamamlandı!")
print(f"📊 Toplam benzersiz ticker sayısı: {len(merged_df)}")
print(f"📋 Kolonlar: {', '.join(merged_df.columns)}")