import pandas as pd
import glob
import os

def determine_treasury_by_coupon(coupon_rate):
    """
    Kupon oranına göre hangi Treasury'nin kullanılacağını belirler
    """
    if isinstance(coupon_rate, str):
        coupon_rate = float(coupon_rate.replace('%', ''))
    else:
        coupon_rate = float(coupon_rate)
    
    if 3.75 <= coupon_rate <= 4.75:
        return 'US30Y'
    elif 4.75 < coupon_rate <= 5.25:
        return 'US20Y'
    elif 5.25 < coupon_rate <= 5.70:
        return 'US10Y'
    elif 5.70 < coupon_rate <= 6.25:
        return 'US7Y'
    elif 6.25 < coupon_rate <= 6.75:
        return 'US5Y'
    elif coupon_rate > 6.75:
        return 'US2Y'
    else:
        return 'US10Y'  # Default

def adjust_benchmarks_by_ncomp():
    """
    NCOMP Count'a göre Treasury benchmark'lerini ayarlar
    """
    print("=== NCOMP Count'a Göre Treasury Benchmark Ayarlama ===")
    
    # YEK dosyalarını bul
    yek_files = glob.glob('yek*.csv')
    print(f"Bulunan YEK dosyaları: {len(yek_files)}")
    
    total_adjusted = 0
    
    for yek_file in yek_files:
        try:
            print(f"\nİşleniyor: {yek_file}")
            
            # YEK dosyasını oku
            df = pd.read_csv(yek_file)
            print(f"  {len(df)} satır okundu")
            
            # NCOMP Count kolonunu kontrol et
            if 'NCOMP Count' not in df.columns:
                print(f"  {yek_file} dosyasında NCOMP Count kolonu yok!")
                continue
            
            # COUPON kolonunu kontrol et
            coupon_col = None
            for col in df.columns:
                if 'COUPON' in col.upper() or 'KUPON' in col.upper():
                    coupon_col = col
                    break
            
            if not coupon_col:
                print(f"  {yek_file} dosyasında COUPON kolonu yok!")
                continue
            
            adjusted_count = 0
            
            # Her hisse için benchmark ayarla
            for idx, row in df.iterrows():
                try:
                    ncomp_count = row['NCOMP Count']
                    coupon_rate = row[coupon_col]
                    
                    # NCOMP Count >= 1 ise benchmark'i kaydır
                    if ncomp_count >= 1:
                        # Mevcut Treasury'yi belirle
                        current_treasury = determine_treasury_by_coupon(coupon_rate)
                        
                        # Yeni Treasury'yi belirle (bir adım uzun)
                        new_treasury = shift_treasury_maturity(current_treasury)
                        
                        # Treasury ve Treasury Yield kolonlarını güncelle
                        df.at[idx, 'Treasury'] = new_treasury
                        
                        # Treasury Yield değerini al
                        treasury_yields = load_treasury_yields()
                        if treasury_yields and new_treasury in treasury_yields:
                            df.at[idx, 'Treasury Yield'] = treasury_yields[new_treasury]
                        
                        adjusted_count += 1
                        print(f"    {row.get('PREF IBKR', f'Row {idx}')}: NCOMP={ncomp_count}, {current_treasury} -> {new_treasury}")
                    
                except Exception as e:
                    print(f"    Hata (Row {idx}): {e}")
            
            # Dosyayı kaydet
            df.to_csv(yek_file, index=False)
            print(f"  {yek_file} güncellendi")
            print(f"  {adjusted_count} hisse için benchmark ayarlandı")
            total_adjusted += adjusted_count
            
        except Exception as e:
            print(f"  {yek_file} işlenirken hata: {e}")
    
    print(f"\nToplam {total_adjusted} hisse için benchmark ayarlandı")

if __name__ == "__main__":
    adjust_benchmarks_by_ncomp() 