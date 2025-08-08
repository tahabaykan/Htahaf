import pandas as pd
import numpy as np
from datetime import datetime, date
import glob

def calculate_ytc(row):
    """Yield to Call hesapla"""
    try:
        # Gerekli değerleri al
        coupon = float(row['COUPON'].replace('%', '')) if pd.notna(row['COUPON']) else 0
        current_price = float(row['Div adj.price']) if pd.notna(row['Div adj.price']) else 0
        par_value = 25.0  # Preferred stock için standart değer
        
        # Call date'i parse et
        if pd.notna(row['CALL DATE']):
            try:
                call_date = pd.to_datetime(row['CALL DATE'])
                today = pd.to_datetime(datetime.now())
                days_to_call = (call_date - today).days
                years_to_call = days_to_call / 365.25
            except:
                years_to_call = 2.0  # Varsayılan değer (2 yıl)
        else:
            years_to_call = 2.0  # Varsayılan değer
        
        # YTC hesapla
        if current_price > 0 and years_to_call > 0:
            # Yıllık kupon ödemesi
            annual_coupon = (coupon / 100) * par_value
            
            # YTC formülü: (Kupon + (Call Price - Fiyat) / Süre) / Fiyat
            # Call price genellikle par value'dur (25.00)
            call_price = par_value
            ytc = (annual_coupon + (call_price - current_price) / years_to_call) / current_price
            return ytc * 100  # Yüzde olarak döndür
        else:
            return np.nan
            
    except Exception as e:
        print(f"YTC hesaplama hatası ({row.get('PREF IBKR', 'Bilinmeyen')}): {e}")
        return np.nan

def calculate_expected_annual_return(row):
    """
    Her hisse için beklenen yıllık getiri hesapla
    
    Formül:
    - Expected sale price = SMA63 - (div_amount / 2)
    - Total days = time_to_div + 3
    - Final value = expected_sale_price + div_amount
    - Ratio = final_value / last_price
    - Expected annual return = ratio^(365/total_days) - 1
    """
    try:
        # Değerleri al
        sma63 = row['SMA63']
        last_price = row['Last Price']
        time_to_div = row['TIME TO DIV']
        div_amount = row['DIV AMOUNT']
        
        # NaN kontrolü
        if pd.isna(sma63) or pd.isna(last_price) or pd.isna(time_to_div) or pd.isna(div_amount):
            return np.nan
        
        # Sıfır kontrolü
        if last_price == 0 or time_to_div == 0:
            return np.nan
        
        # Formülü uygula
        expected_sale_price = sma63 - (div_amount / 2)
        total_days = time_to_div + 3
        final_value = expected_sale_price + div_amount
        ratio = final_value / last_price
        
        # Yıllık getiri hesapla
        exp_ann_return = ratio ** (365 / total_days) - 1
        
        # Yüzdeye çevir
        exp_ann_return_percent = exp_ann_return * 100
        
        return exp_ann_return_percent
        
    except Exception as e:
        print(f"Expected Return hesaplama hatası ({row.get('PREF IBKR', 'Bilinmeyen')}): {e}")
        return np.nan

def calculate_final_thg_callable(df):
    """Callable preferred stock'lar için özel FINAL THG hesaplama"""
    print("\n=== CALLABLE PREFERRED STOCK'LAR İÇİN FINAL THG HESAPLAMA ===")
    
    # YTC hesapla
    print("1. Yield to Call (YTC) hesaplanıyor...")
    df['YTC'] = df.apply(calculate_ytc, axis=1)
    
    # Expected Annual Return hesapla
    print("2. Expected Annual Return hesaplanıyor...")
    df['EXP_ANN_RETURN'] = df.apply(calculate_expected_annual_return, axis=1)
    
    # Solidity skorunu al
    print("3. Solidity skorları alınıyor...")
    try:
        solidity_df = pd.read_csv('allcomek_sldf.csv')
        df = df.merge(
            solidity_df[['PREF IBKR', 'SOLIDITY_SCORE_NORM']], 
            on='PREF IBKR', 
            how='left'
        )
        print(f"Solidity skorları birleştirildi: {df['SOLIDITY_SCORE_NORM'].notna().sum()}/{len(df)} hisse")
    except Exception as e:
        print(f"Solidity skorları alınamadı: {e}")
        df['SOLIDITY_SCORE_NORM'] = 50  # Varsayılan değer
    
    # CALLABLE için özel FINAL THG formülü
    print("4. CALLABLE FINAL THG hesaplanıyor...")
    
    # Final THG formülü: Exp ann return * 20 + Solidity score norm * 2 + YTC * 8
    df['FINAL_THG_CALLABLE'] = (
        df['EXP_ANN_RETURN'].fillna(0) * 20 +
        df['SOLIDITY_SCORE_NORM'].fillna(50) * 2 +
        df['YTC'].fillna(0) * 8
    ).round(2)
    
    print(f"FINAL THG hesaplama tamamlandı")
    print(f"Kullanılan formül: Exp ann return * 20 + Solidity score norm * 2 + YTC * 8")
    
    return df

def process_callable_groups():
    """Callable preferred stock gruplarını işle"""
    callable_files = ['advekheldnff.csv', 'advekhelddeznff.csv']
    
    for adv_file in callable_files:
        try:
            print(f"\n{adv_file} dosyası işleniyor...")
            
            df = pd.read_csv(adv_file, encoding='utf-8-sig')
            print(f"Yüklenen satır sayısı: {len(df)}")
            
            # CALLABLE için özel hesaplama
            result_df = calculate_final_thg_callable(df)
            
            # Sonuçları kaydet
            output_file = adv_file.replace('advek', 'finek').replace('.csv', '_ytc.csv')
            result_df.to_csv(output_file, index=False, encoding='utf-8-sig')
            print(f"\nSonuçlar '{output_file}' dosyasına kaydedildi")
            
            # Top 10 sonuçları göster
            print(f"\n=== {adv_file} - Top 10 FINAL THG Skorları ===")
            print("PREF IBKR  | YTC   | EXP_RETURN | SOLIDITY | FINAL_THG")
            print("-" * 60)
            
            top_10 = result_df.nlargest(10, 'FINAL_THG_CALLABLE')[
                ['PREF IBKR', 'YTC', 'EXP_ANN_RETURN', 'SOLIDITY_SCORE_NORM', 'FINAL_THG_CALLABLE']
            ]
            
            for _, row in top_10.iterrows():
                print(f"{row['PREF IBKR']:<10} | {row['YTC']:>5.2f} | {row['EXP_ANN_RETURN']:>10.2f} | {row['SOLIDITY_SCORE_NORM']:>8.2f} | {row['FINAL_THG_CALLABLE']:>9.2f}")
            
            # İstatistikler
            print(f"\n=== {adv_file} İstatistikleri ===")
            print(f"Ortalama YTC: {result_df['YTC'].mean():.2f}%")
            print(f"Ortalama Expected Return: {result_df['EXP_ANN_RETURN'].mean():.2f}%")
            print(f"Ortalama Solidity: {result_df['SOLIDITY_SCORE_NORM'].mean():.2f}")
            print(f"Ortalama FINAL THG: {result_df['FINAL_THG_CALLABLE'].mean():.2f}")
            
        except Exception as e:
            print(f"Hata ({adv_file}): {e}")

def main():
    """Ana işlem akışı"""
    print("=== CALLABLE PREFERRED STOCK FINAL THG HESAPLAMA ===")
    
    # Callable gruplarını işle
    process_callable_groups()
    
    print("\n=== İŞLEM TAMAMLANDI ===")

if __name__ == "__main__":
    main() 