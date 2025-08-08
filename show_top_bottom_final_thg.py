import pandas as pd
import glob
import os

def show_top_bottom_final_thg():
    """Her grubun en iyi ve en kötü 10 FINAL_THG'li hissesini göster"""
    
    # finek*.csv dosyalarını bul
    finek_files = glob.glob("finek*.csv")
    
    print("=== HER GRUBUN EN İYİ VE EN KÖTÜ 10 FINAL THG'Lİ HİSSESİ ===\n")
    
    for file in finek_files:
        try:
            # Dosyayı oku
            df = pd.read_csv(file)
            
            # FINAL_THG kolonu var mı kontrol et
            if 'FINAL_THG' not in df.columns:
                print(f"❌ {file}: FINAL_THG kolonu bulunamadı")
                continue
            
            # PREF IBKR kolonu var mı kontrol et
            if 'PREF IBKR' not in df.columns:
                print(f"❌ {file}: PREF IBKR kolonu bulunamadı")
                continue
            
            # FINAL_THG'ye göre sırala
            df_sorted = df.sort_values('FINAL_THG', ascending=False)
            
            # En iyi 10
            top_10 = df_sorted.head(10)
            
            # En kötü 10
            bottom_10 = df_sorted.tail(10)
            
            print(f"📊 {file} ({len(df)} hisse)")
            print("=" * 60)
            
            # En iyi 10
            print("🏆 EN İYİ 10 FINAL THG:")
            print("PREF IBKR\t\tFINAL_THG")
            print("-" * 40)
            for _, row in top_10.iterrows():
                ticker = row['PREF IBKR']
                final_thg = row['FINAL_THG']
                print(f"{ticker:<20}\t{final_thg:.2f}")
            
            print()
            
            # En kötü 10
            print("🔻 EN KÖTÜ 10 FINAL THG:")
            print("PREF IBKR\t\tFINAL_THG")
            print("-" * 40)
            for _, row in bottom_10.iterrows():
                ticker = row['PREF IBKR']
                final_thg = row['FINAL_THG']
                print(f"{ticker:<20}\t{final_thg:.2f}")
            
            # İstatistikler
            print()
            print("📈 İSTATİSTİKLER:")
            print(f"  Ortalama FINAL_THG: {df['FINAL_THG'].mean():.2f}")
            print(f"  Medyan FINAL_THG: {df['FINAL_THG'].median():.2f}")
            print(f"  En yüksek FINAL_THG: {df['FINAL_THG'].max():.2f}")
            print(f"  En düşük FINAL_THG: {df['FINAL_THG'].min():.2f}")
            print(f"  Standart sapma: {df['FINAL_THG'].std():.2f}")
            
            print("\n" + "="*80 + "\n")
            
        except Exception as e:
            print(f"❌ {file} dosyası okunamadı: {e}")
            print()

if __name__ == "__main__":
    show_top_bottom_final_thg() 