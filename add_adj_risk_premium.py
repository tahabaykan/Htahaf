import pandas as pd
import glob
import os

def add_adj_risk_premium():
    """
    Adj Risk Premium kolonu ekler
    Bu kolon Adj Treasury Benchmark'ın Cally değeri - Adj Treasury Benchmark'ın Yield değeri
    """
    print("=== Adj Risk Premium Kolonu Ekleme ===")
    
    # Treasury yield'larını treyield.csv'den oku
    treasury_yields = {}
    try:
        if os.path.exists('treyield.csv'):
            df = pd.read_csv('treyield.csv')
            for _, row in df.iterrows():
                treasury_yields[row['Maturity']] = row['Yield']
            print(f"Treasury yield'ları yüklendi: {treasury_yields}")
        else:
            print("treyield.csv bulunamadı!")
            return
    except Exception as e:
        print(f"Treasury yield yükleme hatası: {e}")
        return
    
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
            
            # Adj Risk Premium kolonu ekle veya güncelle
            df['Adj Risk Premium'] = ''
            
            # Her hisse için Adj Risk Premium hesapla
            for index, row in df.iterrows():
                try:
                    # Adj Treasury Bench kolonunu al
                    adj_bench = row.get('Adj Treasury Bench', 'US30Y')
                    
                    # Adj Treasury Bench'a göre Cally değerini al
                    if adj_bench == 'US2Y':
                        cally_value = row.get('2Y Cally', 0)
                        yield_value = treasury_yields.get('US2Y', 0)
                    elif adj_bench == 'US5Y':
                        cally_value = row.get('5Y Cally', 0)
                        yield_value = treasury_yields.get('US5Y', 0)
                    elif adj_bench == 'US7Y':
                        cally_value = row.get('7Y Cally', 0)
                        yield_value = treasury_yields.get('US7Y', 0)
                    elif adj_bench == 'US10Y':
                        cally_value = row.get('10Y Cally', 0)
                        yield_value = treasury_yields.get('US10Y', 0)
                    elif adj_bench == 'US15Y':
                        cally_value = row.get('15Y Cally', 0)
                        yield_value = treasury_yields.get('US15Y', 0)
                    elif adj_bench == 'US20Y':
                        cally_value = row.get('20Y Cally', 0)
                        yield_value = treasury_yields.get('US20Y', 0)
                    elif adj_bench == 'US30Y':
                        cally_value = row.get('30Y Cally', 0)
                        yield_value = treasury_yields.get('US30Y', 0)
                    else:
                        # Eğer tanınmayan benchmark varsa US30Y kullan
                        cally_value = row.get('30Y Cally', 0)
                        yield_value = treasury_yields.get('US30Y', 0)
                    
                    # Treasury yield'ı float'a çevir
                    if isinstance(yield_value, str):
                        yield_value = float(yield_value.replace('%', '')) / 100
                    else:
                        yield_value = float(yield_value) / 100
                    
                    # Cally değerini float'a çevir
                    if isinstance(cally_value, str):
                        if cally_value == '':
                            cally_value = 0
                        else:
                            cally_value = float(cally_value)
                    else:
                        cally_value = float(cally_value) if cally_value else 0
                    
                    # Adj Risk Premium hesapla: Cally - Treasury Yield
                    if cally_value > 0 and yield_value > 0:
                        adj_risk_premium = cally_value - yield_value
                        df.at[index, 'Adj Risk Premium'] = round(adj_risk_premium, 4)
                    else:
                        df.at[index, 'Adj Risk Premium'] = ''
                except Exception as e:
                    print(f"  Hisse {index} için hesaplama hatası: {e}")
                    df.at[index, 'Adj Risk Premium'] = ''
            
            # Dosyayı kaydet
            df.to_csv(yek_file, index=False, encoding='utf-8-sig')
            print(f"  [OK] {yek_file} güncellendi")
            total_processed += 1
                
        except Exception as e:
            print(f"    HATA: {e}")
    
    print(f"\n=== Adj Risk Premium Ekleme Tamamlandı ===")
    print(f"Toplam işlenen dosya: {total_processed}")

if __name__ == "__main__":
    add_adj_risk_premium() 