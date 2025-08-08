import pandas as pd
import os

def merge_historical_data():
    """
    historical_data.csv ve extlthistorical.csv dosyalarını birleştirir
    """
    print("Dosyalar birleştiriliyor...")
    
    # Dosyaları oku
    try:
        # Historical data dosyasını oku
        print("historical_data.csv okunuyor...")
        hist_data = pd.read_csv('historical_data.csv')
        print(f"historical_data.csv: {len(hist_data)} satır, {len(hist_data.columns)} sütun")
        
        # Extlt historical data dosyasını oku
        print("extlthistorical.csv okunuyor...")
        extlt_data = pd.read_csv('extlthistorical.csv')
        print(f"extlthistorical.csv: {len(extlt_data)} satır, {len(extlt_data.columns)} sütun")
        
        # Sütun isimlerini kontrol et ve uyumlu hale getir
        print("\nSütun isimleri:")
        print(f"historical_data.csv sütunları: {list(hist_data.columns)}")
        print(f"extlthistorical.csv sütunları: {list(extlt_data.columns)}")
        
        # Ortak sütunları bul
        common_columns = set(hist_data.columns) & set(extlt_data.columns)
        print(f"\nOrtak sütunlar: {len(common_columns)} adet")
        print(f"Ortak sütunlar: {list(common_columns)}")
        
        # Eksik sütunları ekle
        hist_only_columns = set(hist_data.columns) - set(extlt_data.columns)
        extlt_only_columns = set(extlt_data.columns) - set(hist_data.columns)
        
        print(f"\nhistorical_data.csv'de olup extlthistorical.csv'de olmayan sütunlar: {list(hist_only_columns)}")
        print(f"extlthistorical.csv'de olup historical_data.csv'de olmayan sütunlar: {list(extlt_only_columns)}")
        
        # Eksik sütunları her iki DataFrame'e ekle
        for col in hist_only_columns:
            extlt_data[col] = ''
            print(f"extlthistorical.csv'ye '{col}' sütunu eklendi")
            
        for col in extlt_only_columns:
            hist_data[col] = ''
            print(f"historical_data.csv'ye '{col}' sütunu eklendi")
        
        # Sütun sırasını aynı hale getir
        all_columns = sorted(set(hist_data.columns) | set(extlt_data.columns))
        hist_data = hist_data.reindex(columns=all_columns)
        extlt_data = extlt_data.reindex(columns=all_columns)
        
        # Dosyaları birleştir
        print("\nDosyalar birleştiriliyor...")
        combined_data = pd.concat([hist_data, extlt_data], ignore_index=True)
        
        # Duplicate satırları temizle (aynı PREF IBKR'e sahip olanlar)
        print("Duplicate satırlar temizleniyor...")
        initial_count = len(combined_data)
        combined_data = combined_data.drop_duplicates(subset=['PREF IBKR'], keep='first')
        final_count = len(combined_data)
        removed_count = initial_count - final_count
        print(f"Temizlenen duplicate satır sayısı: {removed_count}")
        
        # Sonucu kaydet
        output_file = 'alltogether.csv'
        combined_data.to_csv(output_file, index=False)
        
        print(f"\n✅ Birleştirme tamamlandı!")
        print(f"📊 Sonuç istatistikleri:")
        print(f"   - Toplam satır sayısı: {len(combined_data)}")
        print(f"   - Toplam sütun sayısı: {len(combined_data.columns)}")
        print(f"   - Dosya adı: {output_file}")
        
        # İlk 5 satırı göster
        print(f"\n📋 İlk 5 satır:")
        print(combined_data.head().to_string())
        
        return True
        
    except FileNotFoundError as e:
        print(f"❌ Dosya bulunamadı: {e}")
        return False
    except Exception as e:
        print(f"❌ Hata oluştu: {e}")
        return False

if __name__ == "__main__":
    merge_historical_data() 