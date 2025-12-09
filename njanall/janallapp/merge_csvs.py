"""
CSV Merge modülü - Tüm ssfinek CSV dosyalarını birleştirip janalldata.csv oluşturur

!!! ÖNEMLİ DOSYA YOLU UYARISI !!!
=================================
BÜTÜN CSV OKUMA VE CSV KAYDETME İŞLEMLERİ njanall DİZİNİNE YAPILMALI!!
njanall dizininde çalışması için path_helper kullanılmalı!

Bu modül CSV birleştirme işlemi yapar:
✅ DOĞRU: get_csv_path("janalldata.csv") (njanall dizininde)
❌ YANLIŞ: "janalldata.csv" (StockTracker dizininde)
=================================
"""

import pandas as pd
import os
from .path_helper import NJANALL_BASE_DIR, get_csv_path

# Ana dizin - njanall dizini
base_dir = NJANALL_BASE_DIR

# CSV dosyalarının listesi ve grup bilgileri (janek_ssfinek dosyaları)
csv_files_with_groups = [
    (get_csv_path('janek_ssfinekheldcilizyeniyedi.csv'), 'heldcilizyeniyedi'),
    (get_csv_path('janek_ssfinekheldcommonsuz.csv'), 'heldcommonsuz'),
    (get_csv_path('janek_ssfinekhelddeznff.csv'), 'helddeznff'),
    (get_csv_path('janek_ssfinekheldff.csv'), 'heldff'),
    (get_csv_path('janek_ssfinekheldflr.csv'), 'heldflr'),
    (get_csv_path('janek_ssfinekheldgarabetaltiyedi.csv'), 'heldgarabetaltiyedi'),
    (get_csv_path('janek_ssfinekheldkuponlu.csv'), 'heldkuponlu'),
    (get_csv_path('janek_ssfinekheldkuponlukreciliz.csv'), 'heldkuponlukreciliz'),
    (get_csv_path('janek_ssfinekheldkuponlukreorta.csv'), 'heldkuponlukreorta'),
    (get_csv_path('janek_ssfinekheldnff.csv'), 'heldnff'),
    (get_csv_path('janek_ssfinekheldotelremorta.csv'), 'heldotelremorta'),
    (get_csv_path('janek_ssfinekheldsolidbig.csv'), 'heldsolidbig'),
    (get_csv_path('janek_ssfinekheldtitrekhc.csv'), 'heldtitrekhc'),
    (get_csv_path('janek_ssfinekhighmatur.csv'), 'highmatur'),
    (get_csv_path('janek_ssfineknotbesmaturlu.csv'), 'notbesmaturlu'),
    (get_csv_path('janek_ssfineknotcefilliquid.csv'), 'notcefilliquid'),
    (get_csv_path('janek_ssfineknottitrekhc.csv'), 'nottitrekhc'),
    (get_csv_path('janek_ssfinekrumoreddanger.csv'), 'rumoreddanger'),
    (get_csv_path('janek_ssfineksalakilliquid.csv'), 'sakilliquid'),
    (get_csv_path('janek_ssfinekshitremhc.csv'), 'shitremhc')
]

def merge_all_csvs():
    """
    Tüm ssfinek CSV dosyalarını birleştirip janalldata.csv oluşturur.
    
    Returns:
        tuple: (success: bool, merged_df: DataFrame or None, message: str)
    """
    try:
        # Tüm dataframe'leri bir listede topla
        dfs = []
        for file_path, group_name in csv_files_with_groups:
            try:
                if not os.path.exists(file_path):
                    continue
                    
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
            return False, None, "❌ Hiçbir CSV dosyası okunamadı!"
        
        # Tüm dataframe'leri birleştir
        merged_df = pd.concat(dfs, ignore_index=True)
        
        # 'PREF IBKR' sütunu yoksa hata ver
        if 'PREF IBKR' not in merged_df.columns:
            raise ValueError("'PREF IBKR' sütunu bulunamadı. Mevcut sütunlar: " + ", ".join(merged_df.columns))
        
        # Duplicate satırları çıkar ('PREF IBKR' kolonuna göre)
        merged_df = merged_df.drop_duplicates(subset=['PREF IBKR'], keep='first')
        
        # Boş değerleri temizle
        merged_df = merged_df.dropna(how='all')
        
        # Sonucu kaydet
        output_path = get_csv_path('janalldata.csv')
        
        # Çıktıyı kaydetmeden önce sütun sıralamasını düzenle
        # 'PREF IBKR' ve 'GROUP' sütunlarını ilk sıraya al
        columns = ['PREF IBKR', 'GROUP'] + [col for col in merged_df.columns if col not in ['PREF IBKR', 'GROUP']]
        merged_df = merged_df[columns]
        
        # CSV'yi kaydet (UTF-8 BOM ile)
        merged_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        
        message = f"✅ Birleştirme başarıyla tamamlandı!\n💾 Kaydedilen dosya: {output_path}\n📊 Toplam benzersiz ticker sayısı: {len(merged_df)}"
        print(message)
        
        return True, merged_df, message
        
    except Exception as e:
        error_msg = f"❌ Hata: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return False, None, error_msg

# Script olarak çalıştırıldığında
if __name__ == '__main__':
    success, df, message = merge_all_csvs()
    if not success:
        exit(1)
