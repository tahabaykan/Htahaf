import pandas as pd

# CSV dosyalarının listesi
csv_files = [
    'janek_ssfinekheldcilizyeniyedi.csv',
    'janek_ssfinekheldcommonsuz.csv',
    'janek_ssfinekhelddeznff.csv',
    'janek_ssfinekheldff.csv',
    'janek_ssfinekheldflr.csv',
    'janek_ssfinekheldgarabetaltiyedi.csv',
    'janek_ssfinekheldkuponlu.csv',
    'janek_ssfinekheldkuponlukreciliz.csv',
    'janek_ssfinekheldkuponlukreorta.csv',
    'janek_ssfinekheldnff.csv',
    'janek_ssfinekheldotelremorta.csv',
    'janek_ssfinekheldsolidbig.csv',
    'janek_ssfinekheldtitrekhc.csv',
    'janek_ssfinekhighmatur.csv',
    'janek_ssfineknotbesmaturlu.csv',
    'janek_ssfineknotcefilliquid.csv',
    'janek_ssfineknottitrekhc.csv',
    'janek_ssfinekrumoreddanger.csv',
    'janek_ssfineksalakilliquid.csv',
    'janek_ssfinekshitremhc.csv'
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