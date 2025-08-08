import pandas as pd
import numpy as np
from datetime import datetime, date
import glob

def calculate_ytm(row):
    """Yield to Maturity hesapla"""
    try:
        # Gerekli değerleri al
        coupon = float(row['COUPON'].replace('%', '')) if pd.notna(row['COUPON']) else 0
        current_price = float(row['Div adj.price']) if pd.notna(row['Div adj.price']) else 0
        par_value = 25.0  # Preferred stock için standart değer
        
        # Maturity date'i parse et
        if pd.notna(row['MATUR DATE']):
            try:
                maturity_date = pd.to_datetime(row['MATUR DATE'])
                today = pd.to_datetime(datetime.now())
                days_to_maturity = (maturity_date - today).days
                years_to_maturity = days_to_maturity / 365.25
            except:
                years_to_maturity = 5.0  # Varsayılan değer
        else:
            years_to_maturity = 5.0  # Varsayılan değer
        
        # YTM hesapla
        if current_price > 0 and years_to_maturity > 0:
            # Yıllık kupon ödemesi
            annual_coupon = (coupon / 100) * par_value
            
            # YTM formülü: (Kupon + (Par - Fiyat) / Süre) / Fiyat
            ytm = (annual_coupon + (par_value - current_price) / years_to_maturity) / current_price
            return ytm * 100  # Yüzde olarak döndür
        else:
            return np.nan
            
    except Exception as e:
        print(f"YTM hesaplama hatası ({row.get('PREF IBKR', 'Bilinmeyen')}): {e}")
        return np.nan

def calculate_expected_annual_return(row):
    """
    Her hisse için beklenen yıllık getiri hesapla
    
    Formül:
    - Expected sale price = SMA63 - (div_amount / 2)
    - Total days = time_to_div + 10
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

def calculate_final_thg_heldbesmaturlu(df):
    """heldbesmaturlu grubu için özel FINAL THG hesaplama"""
    print("\n=== HELDBESMATURLU GRUBU İÇİN FINAL THG HESAPLAMA ===")
    
    # YTM hesapla
    print("1. Yield to Maturity (YTM) hesaplanıyor...")
    df['YTM'] = df.apply(calculate_ytm, axis=1)
    
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
    
    # HELDBESMATURLU için özel FINAL THG formülü
    print("4. HELDBESMATURLU FINAL THG hesaplanıyor...")
    
    # Final THG formülü: Exp ann return * 20 + Solidity score norm * 2 + YTM * 8
    df['FINAL_THG_HELDBESMATURLU'] = (
        df['EXP_ANN_RETURN'].fillna(0) * 20 +
        df['SOLIDITY_SCORE_NORM'].fillna(50) * 2 +
        df['YTM'].fillna(0) * 8
    ).round(2)
    
    print(f"FINAL THG hesaplama tamamlandı")
    print(f"Kullanılan formül: Exp ann return * 20 + Solidity score norm * 2 + YTM * 8")
    
    return df

def process_heldbesmaturlu_group():
    """heldbesmaturlu grubunu işle"""
    try:
        # ADV dosyasını yükle
        adv_file = 'advekheldbesmaturlu.csv'
        print(f"\n{adv_file} dosyası işleniyor...")
        
        df = pd.read_csv(adv_file, encoding='utf-8-sig')
        print(f"Yüklenen satır sayısı: {len(df)}")
        
        # HELDBESMATURLU için özel hesaplama
        result_df = calculate_final_thg_heldbesmaturlu(df)
        
        # Sonuçları kaydet
        output_file = 'finekheldbesmaturlu.csv'
        result_df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"\nSonuçlar '{output_file}' dosyasına kaydedildi")
        
        # Top 10 sonuçları göster
        print(f"\n=== HELDBESMATURLU - Top 10 FINAL THG Skorları ===")
        print("PREF IBKR  | YTM   | EXP_RETURN | SOLIDITY | FINAL_THG")
        print("-" * 60)
        
        top_10 = result_df.nlargest(10, 'FINAL_THG_HELDBESMATURLU')[
            ['PREF IBKR', 'YTM', 'EXP_ANN_RETURN', 'SOLIDITY_SCORE_NORM', 'FINAL_THG_HELDBESMATURLU']
        ]
        
        for _, row in top_10.iterrows():
            print(f"{row['PREF IBKR']:<10} | {row['YTM']:>5.2f} | {row['EXP_ANN_RETURN']:>10.2f} | {row['SOLIDITY_SCORE_NORM']:>8.2f} | {row['FINAL_THG_HELDBESMATURLU']:>9.2f}")
        
        # İstatistikler
        print(f"\n=== HELDBESMATURLU İstatistikleri ===")
        print(f"Ortalama YTM: {result_df['YTM'].mean():.2f}%")
        print(f"Ortalama Expected Return: {result_df['EXP_ANN_RETURN'].mean():.2f}%")
        print(f"Ortalama Solidity: {result_df['SOLIDITY_SCORE_NORM'].mean():.2f}")
        print(f"Ortalama FINAL THG: {result_df['FINAL_THG_HELDBESMATURLU'].mean():.2f}")
        
        return result_df
        
    except Exception as e:
        print(f"Hata: {e}")
        return None

def main():
    """Ana işlem akışı"""
    print("=== GRUP BAZLI FINAL THG HESAPLAMA ===")
    
    # HELDBESMATURLU grubunu işle
    result = process_heldbesmaturlu_group()
    
    if result is not None:
        print("\n=== İŞLEM TAMAMLANDI ===")
    else:
        print("\n=== İŞLEM BAŞARISIZ ===")

if __name__ == "__main__":
    main() 