import pandas as pd
import glob
import os

def check_missing_final_thg():
    """Hangi gruplarda FINAL_THG hesaplanmadığını ve neden olduğunu kontrol et"""
    
    # finek*.csv dosyalarını bul
    finek_files = glob.glob("finek*.csv")
    
    print("=== FINAL_THG HESAPLANMAYAN GRUPLAR ANALİZİ ===\n")
    
    for file in finek_files:
        try:
            # Dosyayı oku
            df = pd.read_csv(file)
            
            print(f"📊 {file} ({len(df)} hisse)")
            print("=" * 60)
            
            # FINAL_THG kolonu var mı kontrol et
            if 'FINAL_THG' in df.columns:
                final_thg_values = df['FINAL_THG'].dropna()
                if len(final_thg_values) > 0:
                    print(f"✅ FINAL_THG hesaplanmış: {len(final_thg_values)} değer")
                    print(f"   Ortalama: {final_thg_values.mean():.2f}")
                    print(f"   Min: {final_thg_values.min():.2f}, Max: {final_thg_values.max():.2f}")
                else:
                    print("❌ FINAL_THG kolonu var ama tüm değerler NaN")
            else:
                print("❌ FINAL_THG kolonu yok")
            
            # Gerekli kolonları kontrol et
            required_cols = [
                'SMA20_chg_norm', 'SMA63_chg_norm', 'SMA246_chg_norm',
                '6M_High_diff_norm', '6M_Low_diff_norm', '3M_High_diff_norm', 
                '3M_Low_diff_norm', '1Y_High_diff_norm', '1Y_Low_diff_norm',
                'Aug4_chg_norm', 'Oct19_chg_norm', 'SOLIDITY_SCORE_NORM', 'CUR_YIELD_NORM'
            ]
            
            missing_cols = []
            for col in required_cols:
                if col not in df.columns:
                    missing_cols.append(col)
            
            if missing_cols:
                print(f"❌ Eksik kolonlar: {missing_cols}")
            else:
                print("✅ Tüm gerekli kolonlar mevcut")
            
            # PREF IBKR kolonu var mı kontrol et
            if 'PREF IBKR' in df.columns:
                print(f"✅ PREF IBKR kolonu mevcut: {len(df['PREF IBKR'].dropna())} hisse")
            else:
                print("❌ PREF IBKR kolonu yok")
            
            # İlk 5 hisseyi göster
            if 'PREF IBKR' in df.columns:
                print("\n📋 İlk 5 hisse:")
                for i, row in df.head().iterrows():
                    ticker = row['PREF IBKR']
                    print(f"   {ticker}")
            
            print("\n" + "-"*80 + "\n")
            
        except Exception as e:
            print(f"❌ {file} dosyası okunamadı: {e}")
            print()

if __name__ == "__main__":
    check_missing_final_thg() 