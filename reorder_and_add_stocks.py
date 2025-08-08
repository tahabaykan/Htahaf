import pandas as pd
import numpy as np

def reorder_columns_and_add_stocks():
    """
    alltogether.csv dosyasının sütun sıralamasını düzenler ve yeni hisseleri ekler
    """
    print("Sütun sıralaması düzenleniyor ve yeni hisseler ekleniyor...")
    
    try:
        # Dosyayı oku
        df = pd.read_csv('alltogether.csv')
        print(f"Mevcut dosya: {len(df)} satır, {len(df.columns)} sütun")
        
        # İstenen sütun sıralaması
        desired_order = [
            'PREF IBKR',
            'CMON', 
            'BOND_',
            'CRDT_SCORE',
            'EX-DIV DATE',
            'CALL DATE',
            'MATUR DATE',
            'DIV AMOUNT',
            'COUPON',
            'Aug2022_Price',
            'Oct19_Price',
            'CGRUP'
        ]
        
        # Mevcut sütunları kontrol et
        missing_cols = [col for col in desired_order if col not in df.columns]
        if missing_cols:
            print(f"❌ Eksik sütunlar: {missing_cols}")
            return False
        
        # Sütunları yeniden sırala
        print("Sütunlar yeniden sıralanıyor...")
        df_reordered = df[desired_order]
        
        # Yeni hisseleri ekle
        new_stocks = [
            {
                'PREF IBKR': 'TWOD',
                'CMON': 'TWOD',
                'BOND_': '',
                'CRDT_SCORE': '',
                'EX-DIV DATE': '',
                'CALL DATE': '',
                'MATUR DATE': '',
                'DIV AMOUNT': '',
                'COUPON': '',
                'Aug2022_Price': '',
                'Oct19_Price': '',
                'CGRUP': ''
            },
            {
                'PREF IBKR': 'WTFCN',
                'CMON': 'WTFC',
                'BOND_': '',
                'CRDT_SCORE': '',
                'EX-DIV DATE': '',
                'CALL DATE': '',
                'MATUR DATE': '',
                'DIV AMOUNT': '',
                'COUPON': '',
                'Aug2022_Price': '',
                'Oct19_Price': '',
                'CGRUP': ''
            },
            {
                'PREF IBKR': 'NEE PRU',
                'CMON': 'NEE',
                'BOND_': '',
                'CRDT_SCORE': '',
                'EX-DIV DATE': '',
                'CALL DATE': '',
                'MATUR DATE': '',
                'DIV AMOUNT': '',
                'COUPON': '',
                'Aug2022_Price': '',
                'Oct19_Price': '',
                'CGRUP': ''
            },
            {
                'PREF IBKR': 'KKRT',
                'CMON': 'KKR',
                'BOND_': '',
                'CRDT_SCORE': '',
                'EX-DIV DATE': '',
                'CALL DATE': '',
                'MATUR DATE': '',
                'DIV AMOUNT': '',
                'COUPON': '',
                'Aug2022_Price': '',
                'Oct19_Price': '',
                'CGRUP': ''
            },
            {
                'PREF IBKR': 'AOMD',
                'CMON': 'AOM',
                'BOND_': '',
                'CRDT_SCORE': '',
                'EX-DIV DATE': '',
                'CALL DATE': '',
                'MATUR DATE': '',
                'DIV AMOUNT': '',
                'COUPON': '',
                'Aug2022_Price': '',
                'Oct19_Price': '',
                'CGRUP': ''
            },
            {
                'PREF IBKR': 'MBNKO',
                'CMON': 'MBNK',
                'BOND_': '',
                'CRDT_SCORE': '',
                'EX-DIV DATE': '',
                'CALL DATE': '',
                'MATUR DATE': '',
                'DIV AMOUNT': '',
                'COUPON': '',
                'Aug2022_Price': '',
                'Oct19_Price': '',
                'CGRUP': ''
            },
            {
                'PREF IBKR': 'BUSEP',
                'CMON': 'BUSE',
                'BOND_': '',
                'CRDT_SCORE': '',
                'EX-DIV DATE': '',
                'CALL DATE': '',
                'MATUR DATE': '',
                'DIV AMOUNT': '',
                'COUPON': '',
                'Aug2022_Price': '',
                'Oct19_Price': '',
                'CGRUP': ''
            },
            {
                'PREF IBKR': 'PMTW',
                'CMON': 'PMT',
                'BOND_': '',
                'CRDT_SCORE': '',
                'EX-DIV DATE': '',
                'CALL DATE': '',
                'MATUR DATE': '',
                'DIV AMOUNT': '',
                'COUPON': '',
                'Aug2022_Price': '',
                'Oct19_Price': '',
                'CGRUP': ''
            }
        ]
        
        print(f"Yeni hisseler ekleniyor: {[stock['PREF IBKR'] for stock in new_stocks]}")
        
        # Yeni hisseleri DataFrame'e ekle
        new_df = pd.DataFrame(new_stocks)
        df_final = pd.concat([df_reordered, new_df], ignore_index=True)
        
        # Sonucu kaydet
        output_file = 'alltogether_reordered.csv'
        df_final.to_csv(output_file, index=False)
        
        print(f"\n✅ İşlem tamamlandı!")
        print(f"📊 Sonuç istatistikleri:")
        print(f"   - Toplam satır sayısı: {len(df_final)}")
        print(f"   - Toplam sütun sayısı: {len(df_final.columns)}")
        print(f"   - Dosya adı: {output_file}")
        
        # Yeni sütun sıralamasını göster
        print(f"\nYeni sütun sıralaması:")
        for i, col in enumerate(df_final.columns):
            print(f"{i+1:2d}. {col}")
        
        # İlk 5 satırı göster
        print(f"\n📋 İlk 5 satır:")
        print(df_final.head().to_string())
        
        # Yeni eklenen hisseleri göster
        print(f"\n🆕 Yeni eklenen hisseler:")
        for stock in new_stocks:
            print(f"   - {stock['PREF IBKR']} ({stock['CMON']})")
        
        return True
        
    except Exception as e:
        print(f"❌ Hata oluştu: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    reorder_columns_and_add_stocks() 