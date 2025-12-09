"""
CSV Merge modülü - Tüm ssfinek CSV dosyalarını birleştirip janalldata.csv oluşturur

!!! ÖNEMLİ DOSYA YOLU UYARISI !!!
=================================
BÜTÜN CSV OKUMA VE CSV KAYDETME İŞLEMLERİ StockTracker DİZİNİNE YAPILMALI!!
StockTracker/janallres/ dizinine YAPILMAMALI!!!
KARIŞASAYI ÖNLEMEK İÇİN BU KURALA MUTLAKA UYULACAK!

Bu modül CSV birleştirme işlemi yapar:
✅ DOĞRU: "janalldata.csv" (StockTracker dizininde)
❌ YANLIŞ: "janallresres/janalldata.csv"
=================================
"""

import pandas as pd
import os

# Ana dizin
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# CSV dosyalarının listesi ve grup bilgileri (janek_ssfinek dosyaları)
csv_files_with_groups = [
    (os.path.join(base_dir, 'janek_ssfinekheldcilizyeniyedi.csv'), 'heldcilizyeniyedi'),
    (os.path.join(base_dir, 'janek_ssfinekheldcommonsuz.csv'), 'heldcommonsuz'),
    (os.path.join(base_dir, 'janek_ssfinekhelddeznff.csv'), 'helddeznff'),
    (os.path.join(base_dir, 'janek_ssfinekheldff.csv'), 'heldff'),
    (os.path.join(base_dir, 'janek_ssfinekheldflr.csv'), 'heldflr'),
    (os.path.join(base_dir, 'janek_ssfinekheldgarabetaltiyedi.csv'), 'heldgarabetaltiyedi'),
    (os.path.join(base_dir, 'janek_ssfinekheldkuponlu.csv'), 'heldkuponlu'),
    (os.path.join(base_dir, 'janek_ssfinekheldkuponlukreciliz.csv'), 'heldkuponlukreciliz'),
    (os.path.join(base_dir, 'janek_ssfinekheldkuponlukreorta.csv'), 'heldkuponlukreorta'),
    (os.path.join(base_dir, 'janek_ssfinekheldnff.csv'), 'heldnff'),
    (os.path.join(base_dir, 'janek_ssfinekheldotelremorta.csv'), 'heldotelremorta'),
    (os.path.join(base_dir, 'janek_ssfinekheldsolidbig.csv'), 'heldsolidbig'),
    (os.path.join(base_dir, 'janek_ssfinekheldtitrekhc.csv'), 'heldtitrekhc'),
    (os.path.join(base_dir, 'janek_ssfinekhighmatur.csv'), 'highmatur'),
    (os.path.join(base_dir, 'janek_ssfineknotbesmaturlu.csv'), 'notbesmaturlu'),
    (os.path.join(base_dir, 'janek_ssfineknotcefilliquid.csv'), 'notcefilliquid'),
    (os.path.join(base_dir, 'janek_ssfineknottitrekhc.csv'), 'nottitrekhc'),
    (os.path.join(base_dir, 'janek_ssfinekrumoreddanger.csv'), 'rumoreddanger'),
    (os.path.join(base_dir, 'janek_ssfineksalakilliquid.csv'), 'sakilliquid'),
    (os.path.join(base_dir, 'janek_ssfinekshitremhc.csv'), 'shitremhc')
]

# Tüm dataframe'leri bir listede topla
dfs = []
for file_path, group_name in csv_files_with_groups:
    try:
        # CSV dosyasını okurken encoding ve diğer önemli parametreleri belirtiyoruz
        df = pd.read_csv(file_path, encoding='utf-8', low_memory=False, dtype=str)
        
        # Sütun isimlerindeki baştaki ve sondaki boşlukları temizle
        df.columns = df.columns.str.strip()
        
        # 'PREF IBKR' sütunundaki boşlukları temizle
        if 'PREF IBKR' in df.columns:
            df['PREF IBKR'] = df['PREF IBKR'].str.strip()
        
        # Grup bilgisini ekle
        df['GROUP'] = group_name
            
        print(f"✅ {os.path.basename(file_path)} ({group_name}) okundu: {len(df)} satır")
        dfs.append(df)
    except Exception as e:
        print(f"❌ {os.path.basename(file_path)} okunurken hata: {str(e)}")

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
    # 'PREF IBKR' ve 'GROUP' sütunlarını ilk sıraya al
    columns = ['PREF IBKR', 'GROUP'] + [col for col in merged_df.columns if col not in ['PREF IBKR', 'GROUP']]
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