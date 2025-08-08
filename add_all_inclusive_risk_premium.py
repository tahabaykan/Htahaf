import pandas as pd
import glob
import os

def add_all_inclusive_risk_premium():
    """
    All-Inc Risk Premium kolonu ekler
    Bu kolon adjusted Treasury benchmark ile yield to call arasındaki farkı hesaplar
    """
    print("=== All-Inc Risk Premium Kolonu Ekleme ===")
    
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
            
            # All-Inc Risk Premium kolonu ekle
            if 'All-Inc Risk Prim' not in df.columns:
                df['All-Inc Risk Prim'] = ''
                
                # Her hisse için adjusted Treasury benchmark ile risk premium hesapla
                for index, row in df.iterrows():
                    try:
                        # Adjusted Treasury Benchmark'ı al
                        adj_bench = row.get('Adj Treasury Bench', 'US30Y')
                        
                        # Treasury yield'ını al
                        treasury_yield_col = adj_bench + ' Yield'
                        treasury_yield = row.get(treasury_yield_col, 0)
                        
                        # Yield to call kolonunu belirle
                        yield_col_mapping = {
                            'US2Y': '2Y Cally',
                            'US5Y': '5Y Cally', 
                            'US7Y': '7Y Cally',
                            'US10Y': '10Y Cally',
                            'US20Y': '20Y Cally',
                            'US30Y': '30Y Cally'
                        }
                        
                        yield_col = yield_col_mapping.get(adj_bench, '30Y Cally')
                        yield_to_call = row.get(yield_col, 0)
                        
                        # Risk premium hesapla
                        try:
                            treasury_yield_num = float(str(treasury_yield).replace('%', '').replace(',', ''))
                            yield_to_call_num = float(str(yield_to_call).replace('%', '').replace(',', ''))
                            risk_premium = yield_to_call_num - treasury_yield_num
                        except:
                            risk_premium = 0
                        
                        df.at[index, 'All-Inc Risk Prim'] = risk_premium
                        
                    except Exception as e:
                        # Eğer hata olursa 0 koy
                        df.at[index, 'All-Inc Risk Prim'] = 0
                
                print(f"    All-Inc Risk Prim kolonu eklendi")
                
                # Dosyayı kaydet
                df.to_csv(yek_file, index=False)
                print(f"    {yek_file} güncellendi")
                total_processed += 1
            else:
                print(f"    All-Inc Risk Prim kolonu zaten var")
                
        except Exception as e:
            print(f"    HATA: {e}")
    
    print(f"\n=== All-Inc Risk Premium Ekleme Tamamlandı ===")
    print(f"Toplam işlenen dosya: {total_processed}")

if __name__ == "__main__":
    add_all_inclusive_risk_premium() 