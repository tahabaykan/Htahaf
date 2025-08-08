import pandas as pd
import glob
import os

def add_normal_treasury_benchmark():
    """
    Normal Treasury Benchmark kolonu ekler
    Bu kolon kupon süresine göre Treasury benchmark'ını belirler
    """
    print("=== Normal Treasury Benchmark Kolonu Ekleme ===")
    
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
            
            # Normal Treasury Benchmark kolonu ekle
            if 'Normal Treasury Bench' not in df.columns:
                df['Normal Treasury Bench'] = ''
                
                # Her hisse için kupon süresine göre Treasury benchmark belirle
                for index, row in df.iterrows():
                    try:
                        # COUPON kolonunu numeric olarak al
                        coupon_str = str(row.get('COUPON', 0))
                        # String'den sayısal değere çevir
                        coupon = float(coupon_str.replace(',', '').replace('%', ''))
                        
                        # Kupon süresine göre Treasury benchmark belirle
                        if coupon < 3.75:
                            treasury_bench = 'US2Y'
                        elif coupon < 4.75:
                            treasury_bench = 'US5Y'
                        elif coupon < 5.75:
                            treasury_bench = 'US7Y'
                        elif coupon < 6.75:
                            treasury_bench = 'US10Y'
                        elif coupon < 7.75:
                            treasury_bench = 'US20Y'
                        else:
                            treasury_bench = 'US30Y'
                        
                        df.at[index, 'Normal Treasury Bench'] = treasury_bench
                    except:
                        # Eğer COUPON değeri okunamazsa US30Y varsay
                        df.at[index, 'Normal Treasury Bench'] = 'US30Y'
                
                print(f"    Normal Treasury Bench kolonu eklendi")
                
                # Dosyayı kaydet
                df.to_csv(yek_file, index=False)
                print(f"    {yek_file} güncellendi")
                total_processed += 1
            else:
                print(f"    Normal Treasury Bench kolonu zaten var")
                
        except Exception as e:
            print(f"    HATA: {e}")
    
    print(f"\n=== Normal Treasury Benchmark Ekleme Tamamlandı ===")
    print(f"Toplam işlenen dosya: {total_processed}")

if __name__ == "__main__":
    add_normal_treasury_benchmark() 