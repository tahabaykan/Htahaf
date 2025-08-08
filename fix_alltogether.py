import pandas as pd
import numpy as np

def fix_alltogether_csv():
    """
    alltogether.csv dosyasındaki sütun kayması sorununu düzeltir
    """
    print("alltogether.csv dosyası düzeltiliyor...")
    
    try:
        # Dosyayı oku
        df = pd.read_csv('alltogether.csv')
        print(f"Orijinal dosya: {len(df)} satır, {len(df.columns)} sütun")
        
        # Sütun isimlerini kontrol et
        print("Mevcut sütun isimleri:")
        for i, col in enumerate(df.columns):
            print(f"{i+1:2d}. {col}")
        
        # PREF IBKR sütununu bul
        if 'PREF IBKR' in df.columns:
            pref_ibkr_col = df.columns.get_loc('PREF IBKR')
            print(f"\nPREF IBKR sütunu {pref_ibkr_col+1}. pozisyonda")
        else:
            print("❌ PREF IBKR sütunu bulunamadı!")
            return False
        
        # Veri temizleme
        print("\nVeri temizleniyor...")
        
        # Boş satırları temizle
        df = df.dropna(subset=['PREF IBKR'])
        df = df[df['PREF IBKR'].str.strip() != '']
        
        # PREF IBKR sütunundaki boşlukları temizle
        df['PREF IBKR'] = df['PREF IBKR'].str.strip()
        
        # Kaymış verileri düzelt
        # Eğer PREF IBKR sütunu boşsa ama başka bir sütunda veri varsa, o veriyi PREF IBKR'e taşı
        for idx, row in df.iterrows():
            if pd.isna(row['PREF IBKR']) or row['PREF IBKR'] == '':
                # Boş olmayan ilk sütunu bul
                for col in df.columns:
                    if not pd.isna(row[col]) and str(row[col]).strip() != '':
                        # Bu veriyi PREF IBKR sütununa taşı
                        df.at[idx, 'PREF IBKR'] = str(row[col]).strip()
                        # Diğer sütunları bir sola kaydır
                        for i in range(df.columns.get_loc(col), len(df.columns)-1):
                            df.iloc[idx, i] = df.iloc[idx, i+1]
                        df.iloc[idx, -1] = ''
                        break
        
        # Gereksiz sütunları temizle (Unnamed sütunları)
        unnamed_cols = [col for col in df.columns if 'Unnamed' in col]
        if unnamed_cols:
            print(f"Temizlenen gereksiz sütunlar: {unnamed_cols}")
            df = df.drop(columns=unnamed_cols)
        
        # Boş sütunları temizle
        empty_cols = []
        for col in df.columns:
            if df[col].isna().all() or (df[col] == '').all():
                empty_cols.append(col)
        
        if empty_cols:
            print(f"Temizlenen boş sütunlar: {empty_cols}")
            df = df.drop(columns=empty_cols)
        
        # Sonucu kaydet
        output_file = 'alltogether_fixed.csv'
        df.to_csv(output_file, index=False)
        
        print(f"\n✅ Düzeltme tamamlandı!")
        print(f"📊 Sonuç istatistikleri:")
        print(f"   - Toplam satır sayısı: {len(df)}")
        print(f"   - Toplam sütun sayısı: {len(df.columns)}")
        print(f"   - Dosya adı: {output_file}")
        
        # Düzeltilmiş sütun isimlerini göster
        print(f"\nDüzeltilmiş sütun isimleri:")
        for i, col in enumerate(df.columns):
            print(f"{i+1:2d}. {col}")
        
        # İlk 5 satırı göster
        print(f"\n📋 İlk 5 satır:")
        print(df.head().to_string())
        
        return True
        
    except Exception as e:
        print(f"❌ Hata oluştu: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    fix_alltogether_csv() 