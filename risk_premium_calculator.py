import pandas as pd
import glob
import os
from datetime import datetime

def calculate_risk_premium_with_adjusted_treasury():
    """
    Treasury yield'ları kaydırıldıktan sonra risk primi hesaplar
    """
    print("=== Treasury Yield'ları Kaydırıldıktan Sonra Risk Primi Hesaplama ===")
    
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
            
            # Gerekli kolonları kontrol et
            required_cols = ['COUPON', 'Treasury', 'Treasury Yield', 'Div adj.price']
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                print(f"  Eksik kolonlar: {missing_cols}")
                continue
            
            # Adjusted Risk Premium kolonu ekle
            if 'Adjusted Risk Premium' not in df.columns:
                df['Adjusted Risk Premium'] = ''
            
            adjusted_count = 0
            
            # Her hisse için adjusted risk premium hesapla
            for idx, row in df.iterrows():
                try:
                    coupon_rate = row['COUPON']
                    treasury = row['Treasury']
                    treasury_yield = row['Treasury Yield']
                    price = row['Div adj.price']
                    
                    if pd.isna(treasury_yield) or treasury_yield == '':
                        continue
                    
                    # Yield to Call değerini al (Treasury'ye göre)
                    ytc_col = None
                    if treasury == 'US2Y':
                        ytc_col = '2Y Cally'
                    elif treasury == 'US5Y':
                        ytc_col = '5Y Cally'
                    elif treasury == 'US7Y':
                        ytc_col = '7Y Cally'
                    elif treasury == 'US10Y':
                        ytc_col = '10Y Cally'
                    elif treasury == 'US20Y':
                        ytc_col = '20Y Cally'
                    elif treasury == 'US30Y':
                        ytc_col = '30Y Cally'
                    
                    if ytc_col and ytc_col in df.columns:
                        ytc_value = row[ytc_col]
                        if pd.notna(ytc_value) and ytc_value != '':
                            # Adjusted risk premium hesapla
                            adjusted_risk_premium = float(ytc_value) - float(treasury_yield)
                            df.at[idx, 'Adjusted Risk Premium'] = adjusted_risk_premium
                            adjusted_count += 1
                            
                            print(f"    {row.get('PREF IBKR', f'Row {idx}')}: {ytc_value} - {treasury_yield} = {adjusted_risk_premium:.4f}")
                
                except Exception as e:
                    print(f"    Hata (Row {idx}): {e}")
            
            # Dosyayı kaydet
            df.to_csv(yek_file, index=False)
            print(f"  {yek_file} güncellendi")
            print(f"  {adjusted_count} hisse için adjusted risk premium hesaplandı")
            total_processed += adjusted_count
            
        except Exception as e:
            print(f"  {yek_file} işlenirken hata: {e}")
    
    print(f"\nToplam {total_processed} hisse için adjusted risk premium hesaplandı")

if __name__ == "__main__":
    calculate_risk_premium_with_adjusted_treasury() 