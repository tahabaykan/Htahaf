import pandas as pd
import os

# Ana dizin
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# CSV dosyalarının listesi
csv_files = [
    os.path.join(base_dir, 'ssfinekheldcilizyeniyedi.csv'),
    os.path.join(base_dir, 'ssfinekheldcommonsuz.csv'),
    os.path.join(base_dir, 'ssfinekhelddeznff.csv'),
    os.path.join(base_dir, 'ssfinekheldff.csv'),
    os.path.join(base_dir, 'ssfinekheldflr.csv'),
    os.path.join(base_dir, 'ssfinekheldgarabetaltiyedi.csv'),
    os.path.join(base_dir, 'ssfinekheldkuponlu.csv'),
    os.path.join(base_dir, 'ssfinekheldkuponlukreciliz.csv'),
    os.path.join(base_dir, 'ssfinekheldkuponlukreorta.csv'),
    os.path.join(base_dir, 'ssfinekheldnff.csv'),
    os.path.join(base_dir, 'ssfinekheldotelremorta.csv'),
    os.path.join(base_dir, 'ssfinekheldsolidbig.csv'),
    os.path.join(base_dir, 'ssfinekheldtitrekhc.csv'),
    os.path.join(base_dir, 'ssfinekhighmatur.csv'),
    os.path.join(base_dir, 'ssfineknotbesmaturlu.csv'),
    os.path.join(base_dir, 'ssfineknotcefilliquid.csv'),
    os.path.join(base_dir, 'ssfineknottitrekhc.csv'),
    os.path.join(base_dir, 'ssfinekrumoreddanger.csv'),
    os.path.join(base_dir, 'ssfineksalakilliquid.csv'),
    os.path.join(base_dir, 'ssfinekshitremhc.csv')
]

# Tüm dataframe'leri bir listede topla
dfs = []
for file in csv_files:
    try:
        # CSV dosyasını okurken encoding ve diğer önemli parametreleri belirtiyoruz
        df = pd.read_csv(file, encoding='utf-8', low_memory=False, dtype=str)
        
        # Sütun isimlerindeki baştaki ve sondaki boşlukları temizle
        df.columns = df.columns.str.strip()
        
        # 'PREF IBKR' sütunundaki boşlukları temizle
        if 'PREF IBKR' in df.columns:
            df['PREF IBKR'] = df['PREF IBKR'].str.strip()
            
        print(f"✅ {os.path.basename(file)} okundu: {len(df)} satır")
        dfs.append(df)
    except Exception as e:
        print(f"❌ {os.path.basename(file)} okunurken hata: {str(e)}")

if not dfs:
    print("❌ Hiçbir CSV dosyası okunamadı!")
    exit(1)

# Tüm dataframe'leri birleştir
try:
    merged_df = pd.concat(dfs, ignore_index=True)
    
    # 'PREF IBKR' sütunu yoksa hata ver
    if 'PREF IBKR' not in merged_df.columns:
        raise ValueError("'PREF IBKR' sütunu bulunamadı. Mevcut sütunlar: " + ", ".join(merged_df.columns))
    
    # Duplicate satırları çıkar ('PREF IBKR' kolonuna göre)
    merged_df = merged_df.drop_duplicates(subset=['PREF IBKR'], keep='first')
    
    # Boş değerleri temizle
    merged_df = merged_df.dropna(how='all')
    
except Exception as e:
    print(f"❌ Veri birleştirme hatası: {str(e)}")
    exit(1)

# Sonucu kaydet
try:
    output_path = os.path.join(base_dir, 'janalldata.csv')
    
    # Çıktıyı kaydetmeden önce sütun sıralamasını düzenle
    # 'PREF IBKR' sütununu ilk sıraya al
    columns = ['PREF IBKR'] + [col for col in merged_df.columns if col != 'PREF IBKR']
    merged_df = merged_df[columns]
    
    # CSV'yi kaydet (UTF-8 BOM ile)
    merged_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    
    print(f"\n✅ Birleştirme başarıyla tamamlandı!")
    print(f"💾 Kaydedilen dosya: {output_path}")
    print(f"📊 Toplam benzersiz ticker sayısı: {len(merged_df)}")
    print(f"📋 Toplam sütun sayısı: {len(merged_df.columns)}")
    print(f"📋 İlk 10 sütun: {', '.join(merged_df.columns[:10])}...")
    
    # 'CGRUP' sütunu hakkında bilgi ver
    if 'CGRUP' in merged_df.columns:
        print(f"\nℹ️ 'CGRUP' sütunu başarıyla okundu. İlk 5 değer:")
        print(merged_df['CGRUP'].head().to_string(index=False))
    else:
        print("\n❌ 'CGRUP' sütunu bulunamadı! Mevcut sütunlar:")
        print("\n".join([f"- {col}" for col in merged_df.columns]))
        
except Exception as e:
    print(f"\n❌ Dosya kaydedilirken hata oluştu: {str(e)}")
    exit(1)