import pandas as pd
import os

print("⚠️  SADECE ANA DİZİNDEKİ (StockTracker) DOSYALAR KULLANILACAK!")
print("⚠️  Alt dizinlerdeki (janall, janallw, vb.) dosyalar kullanılmayacak!")

# CSV dosyalarının listesi (sadece ana dizindeki)
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

# Sadece ana dizindeki dosyaları kontrol et
current_dir = os.getcwd()
available_files = []
for file in csv_files:
    file_path = os.path.join(current_dir, file)
    if os.path.exists(file_path):
        available_files.append(file)
    else:
        print(f"⚠️ {file} bulunamadı (ana dizinde)")

if not available_files:
    print("❌ Hiçbir CSV dosyası ana dizinde bulunamadı!")
    exit(1)

print(f"📁 Ana dizinde bulunan dosyalar: {len(available_files)} adet")

# Tüm dataframe'leri bir listede topla
dfs = []
for file in available_files:
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

# Sonucu ana dizinde kaydet
output_file = 'janalldata.csv'
merged_df.to_csv(output_file, index=False)
print(f"\n✅ Birleştirme tamamlandı!")
print(f"📊 Toplam benzersiz ticker sayısı: {len(merged_df)}")
print(f"📋 Kolonlar: {', '.join(merged_df.columns)}")
print(f"💾 Dosya ana dizinde kaydedildi: {output_file}")