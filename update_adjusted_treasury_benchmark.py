import pandas as pd
import glob
import os

def update_adjusted_treasury_benchmark():
    """
    Adjusted Treasury Benchmark kolonunu günceller
    Mevcut kolonu silip doğru vade uzatma mantığıyla yeniden ekler
    """
    print("=== Adjusted Treasury Benchmark Kolonu Güncelleme ===")
    
    # YEK dosyalarını bul
    yek_files = glob.glob('yek*.csv')
    print(f"Bulunan YEK dosyaları: {len(yek_files)}")
    
    total_processed = 0
    
    for yek_file in yek_files:
        try:
            print(f"\nİşleniyor: {yek_file}")
            
            # YEK dosyasını oku
            df = pd.read_csv(yek_file)
            print(f"  {len(df)} satır okundu")
            
            # Mevcut Adj Treasury Bench kolonunu sil
            if 'Adj Treasury Bench' in df.columns:
                df = df.drop(columns=['Adj Treasury Bench'])
                print(f"    Eski Adj Treasury Bench kolonu silindi")
            
            # Yeni Adjusted Treasury Benchmark kolonu ekle
            df['Adj Treasury Bench'] = ''
            
            # Her hisse için NCOMP Count'a göre Treasury benchmark kaydır
            for index, row in df.iterrows():
                try:
                    # Normal Treasury Bench kolonunu al
                    normal_bench = row.get('Normal Treasury Bench', 'US30Y')
                    
                    # NCOMP Count değerini al
                    ncomp_count = row.get('NCOMP Count', 0)
                    
                    # NCOMP Count'a göre benchmark kaydır
                    if ncomp_count >= 1:
                        # Vade uzatma mantığı
                        if normal_bench == 'US2Y':
                            adj_bench = 'US5Y'
                        elif normal_bench == 'US5Y':
                            adj_bench = 'US7Y'
                        elif normal_bench == 'US7Y':
                            adj_bench = 'US10Y'
                        elif normal_bench == 'US10Y':
                            adj_bench = 'US15Y'
                        elif normal_bench == 'US15Y':
                            adj_bench = 'US20Y'
                        elif normal_bench == 'US20Y':
                            adj_bench = 'US30Y'
                        elif normal_bench == 'US30Y':
                            adj_bench = 'US30Y'  # Zaten en uzun
                        else:
                            adj_bench = normal_bench
                    else:
                        # NCOMP Count = 0 ise kaydırma yok
                        adj_bench = normal_bench
                    
                    df.at[index, 'Adj Treasury Bench'] = adj_bench
                except:
                    # Eğer hata olursa normal benchmark'ı kullan
                    df.at[index, 'Adj Treasury Bench'] = normal_bench
            
            print(f"    Yeni Adj Treasury Bench kolonu eklendi")
            
            # Dosyayı kaydet
            df.to_csv(yek_file, index=False)
            print(f"    {yek_file} güncellendi")
            total_processed += 1
                
        except Exception as e:
            print(f"    HATA: {e}")
    
    print(f"\n=== Adjusted Treasury Benchmark Güncelleme Tamamlandı ===")
    print(f"Toplam işlenen dosya: {total_processed}")

if __name__ == "__main__":
    update_adjusted_treasury_benchmark() 