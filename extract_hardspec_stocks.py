import pandas as pd
import numpy as np

def extract_hardspec_stocks():
    """
    alltogether_reordered.csv dosyasından belirtilen hisseleri çıkarır
    ve hardspechistorical.csv dosyasına kaydeder
    """
    print("Hardspec hisseleri çıkarılıyor...")
    
    # Çıkarılacak hisseler listesi
    stocks_to_extract = [
        'BHFAO', 'BHFAP', 'BHFAM', 'BHFAN', 'BHFAL',
        'HFRO PRA', 'SCE PRL', 'SCE PRG', 'SCE PRM', 'SCE PRJ', 
        'SCE PRK', 'SCE PRN', 'UZE', 'UZF', 'UZD',
        'DBRG PRI', 'DBRG PRJ', 'DBRG PRH', 'LBRDP', 'MHLA', 'MHNC',
        'NREF PRA', 'RC PRE', 'RCB', 'RCC', 'RCD',
        'SCCG', 'SCCD', 'SCCE', 'SCCF', 'SCCC',
        'QVCD', 'QVCC'
    ]
    
    try:
        # Dosyayı oku
        df = pd.read_csv('alltogether_reordered.csv')
        print(f"Orijinal dosya: {len(df)} satır, {len(df.columns)} sütun")
        
        # Çıkarılacak hisseleri bul
        extracted_stocks = df[df['PREF IBKR'].isin(stocks_to_extract)].copy()
        remaining_stocks = df[~df['PREF IBKR'].isin(stocks_to_extract)].copy()
        
        print(f"\nÇıkarılan hisseler: {len(extracted_stocks)} adet")
        print(f"Kalan hisseler: {len(remaining_stocks)} adet")
        
        # Çıkarılan hisseleri listele
        print("\nÇıkarılan hisseler:")
        for stock in extracted_stocks['PREF IBKR']:
            print(f"  - {stock}")
        
        # Hardspec dosyasını kaydet
        extracted_stocks.to_csv('hardspechistorical.csv', index=False)
        print(f"\n✅ hardspechistorical.csv dosyası oluşturuldu ({len(extracted_stocks)} satır)")
        
        # Ana dosyayı güncelle
        remaining_stocks.to_csv('alltogether_reordered.csv', index=False)
        print(f"✅ alltogether_reordered.csv dosyası güncellendi ({len(remaining_stocks)} satır)")
        
        # Özet
        print(f"\n📊 ÖZET:")
        print(f"  Orijinal: {len(df)} satır")
        print(f"  Çıkarılan: {len(extracted_stocks)} satır")
        print(f"  Kalan: {len(remaining_stocks)} satır")
        
        return True
        
    except Exception as e:
        print(f"❌ Hata: {e}")
        return False

if __name__ == "__main__":
    extract_hardspec_stocks() 