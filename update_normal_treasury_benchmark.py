import pandas as pd
import glob
import os

def update_normal_treasury_benchmark():
    """
    Normal Treasury Benchmark kolonunu günceller
    Mevcut kolonu silip doğru kupon aralıklarıyla yeniden ekler
    """
    print("=== Normal Treasury Benchmark Kolonu Güncelleme ===")
    
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
            
            # Mevcut Normal Treasury Bench kolonunu sil
            if 'Normal Treasury Bench' in df.columns:
                df = df.drop(columns=['Normal Treasury Bench'])
                print(f"    Eski Normal Treasury Bench kolonu silindi")
            
            # Yeni Normal Treasury Benchmark kolonu ekle
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
                        treasury_bench = 'US30Y'
                    elif coupon < 4.66:
                        treasury_bench = 'US30Y'
                    elif coupon < 5.16:
                        treasury_bench = 'US20Y'
                    elif coupon < 5.81:
                        treasury_bench = 'US15Y'
                    elif coupon < 6.26:
                        treasury_bench = 'US10Y'
                    elif coupon < 6.61:
                        treasury_bench = 'US7Y'
                    elif coupon < 7.21:
                        treasury_bench = 'US5Y'
                    else:
                        treasury_bench = 'US2Y'
                    
                    df.at[index, 'Normal Treasury Bench'] = treasury_bench
                except:
                    # Eğer COUPON değeri okunamazsa US30Y varsay
                    df.at[index, 'Normal Treasury Bench'] = 'US30Y'
            
            print(f"    Yeni Normal Treasury Bench kolonu eklendi")
            
            # Dosyayı kaydet
            df.to_csv(yek_file, index=False)
            print(f"    {yek_file} güncellendi")
            total_processed += 1
                
        except Exception as e:
            print(f"    HATA: {e}")
    
    print(f"\n=== Normal Treasury Benchmark Güncelleme Tamamlandı ===")
    print(f"Toplam işlenen dosya: {total_processed}")

if __name__ == "__main__":
    update_normal_treasury_benchmark() 