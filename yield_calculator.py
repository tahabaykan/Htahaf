#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Excel YIELD Fonksiyonu Python Implementation
YIELD(settlement, maturity, rate, pr, redemption, frequency, [basis])
"""

import pandas as pd
import numpy as np
import glob
from datetime import datetime, date
import warnings
warnings.filterwarnings('ignore')

def calculate_yield(settlement_date, maturity_date, coupon_rate, price, redemption=100, frequency=2, basis=0):
    """
    Excel YIELD fonksiyonunu Python'da implement eder
    
    Parameters:
    settlement_date: Tahvilin alım-satım tarihi
    maturity_date: Tahvilin vade tarihi
    coupon_rate: Yıllık kupon oranı (decimal)
    price: Tahvilin fiyatı ($100 nominal değer başına)
    redemption: Tahvilin nominal değeri (default: 100)
    frequency: Yıllık kupon ödeme sayısı (default: 2 = yarıyıllık)
    basis: Gün sayım yöntemi (default: 0 = US 30/360)
    
    Returns:
    float: Yield oranı (decimal)
    """
    
    try:
        # Tarihleri datetime objesine çevir
        if isinstance(settlement_date, str):
            settlement_date = pd.to_datetime(settlement_date)
        if isinstance(maturity_date, str):
            maturity_date = pd.to_datetime(maturity_date)
        
        # Kupon oranını decimal'a çevir
        if isinstance(coupon_rate, str):
            coupon_rate = float(coupon_rate.replace('%', '')) / 100
        
        # Fiyatı float'a çevir
        price = float(price)
        
        # Basit yield hesaplama (Excel YIELD fonksiyonunun basitleştirilmiş versiyonu)
        # YIELD = (Coupon Payment + (Redemption - Price) / Years to Maturity) / Price
        
        # Yıl sayısını hesapla
        years_to_maturity = (maturity_date - settlement_date).days / 365.25
        
        if years_to_maturity <= 0:
            return np.nan
        
        # Yıllık kupon ödemesi
        annual_coupon = redemption * coupon_rate
        
        # Yield hesaplama
        yield_rate = (annual_coupon + (redemption - price) / years_to_maturity) / price
        
        return yield_rate
        
    except Exception as e:
        return np.nan

def process_yek_files():
    """Yek dosyalarını okuyup YIELD hesaplamalarını yap"""
    
    # Yek dosyalarını bul
    yek_files = glob.glob('yek*.csv')
    
    print(f"Bulunan yek dosyaları: {len(yek_files)} adet")
    
    for yek_file in yek_files:
        try:
            print(f"\n=== {yek_file} işleniyor ===")
            
            # Dosyayı oku
            df = pd.read_csv(yek_file)
            print(f"✓ {yek_file} yüklendi: {len(df)} satır")
            
            # Kolon isimlerini kontrol et
            print(f"Mevcut kolonlar: {list(df.columns)}")
            
            # Gerekli kolonları bul
            maturity_col = None
            coupon_col = None
            
            # Maturity kolonunu bul
            for col in df.columns:
                if 'matur' in col.lower() or 'date' in col.lower():
                    maturity_col = col
                    break
            
            # Coupon kolonunu bul
            for col in df.columns:
                if 'coupon' in col.lower():
                    coupon_col = col
                    break
            
            print(f"Maturity kolonu: {maturity_col}")
            print(f"Coupon kolonu: {coupon_col}")
            
            if maturity_col and coupon_col:
                # Settlement date olarak bugün kullan, maturity date olarak farklı vadeler
                settlement_date = datetime.now()
                maturity_date_2y = settlement_date.replace(year=settlement_date.year + 2)
                maturity_date_5y = settlement_date.replace(year=settlement_date.year + 5)
                maturity_date_7y = settlement_date.replace(year=settlement_date.year + 7)
                maturity_date_10y = settlement_date.replace(year=settlement_date.year + 10)
                maturity_date_15y = settlement_date.replace(year=settlement_date.year + 15)
                maturity_date_20y = settlement_date.replace(year=settlement_date.year + 20)
                maturity_date_30y = settlement_date.replace(year=settlement_date.year + 30)
                
                print(f"Settlement date (bugün): {settlement_date.strftime('%Y-%m-%d')}")
                print(f"Maturity dates: 2Y={maturity_date_2y.strftime('%Y-%m-%d')}, 5Y={maturity_date_5y.strftime('%Y-%m-%d')}, 7Y={maturity_date_7y.strftime('%Y-%m-%d')}, 10Y={maturity_date_10y.strftime('%Y-%m-%d')}, 15Y={maturity_date_15y.strftime('%Y-%m-%d')}, 20Y={maturity_date_20y.strftime('%Y-%m-%d')}, 30Y={maturity_date_30y.strftime('%Y-%m-%d')}")
                
                # Her hisse için YIELD hesapla
                for idx, row in df.iterrows():
                    try:
                        coupon_rate = row[coupon_col]
                        
                        # 2Y Cally hesapla
                        yield_2y = calculate_yield(settlement_date, maturity_date_2y, coupon_rate, 25)
                        df.at[idx, '2Y Cally'] = yield_2y * 4 if not pd.isna(yield_2y) else ''
                        
                        # 5Y Cally hesapla
                        yield_5y = calculate_yield(settlement_date, maturity_date_5y, coupon_rate, 25)
                        df.at[idx, '5Y Cally'] = yield_5y * 4 if not pd.isna(yield_5y) else ''
                        
                        # 7Y Cally hesapla
                        yield_7y = calculate_yield(settlement_date, maturity_date_7y, coupon_rate, 25)
                        df.at[idx, '7Y Cally'] = yield_7y * 4 if not pd.isna(yield_7y) else ''
                        
                        # 10Y Cally hesapla
                        yield_10y = calculate_yield(settlement_date, maturity_date_10y, coupon_rate, 25)
                        df.at[idx, '10Y Cally'] = yield_10y * 4 if not pd.isna(yield_10y) else ''
                        
                        # 15Y Cally hesapla
                        yield_15y = calculate_yield(settlement_date, maturity_date_15y, coupon_rate, 25)
                        df.at[idx, '15Y Cally'] = yield_15y * 4 if not pd.isna(yield_15y) else ''
                        
                        # 20Y Cally hesapla
                        yield_20y = calculate_yield(settlement_date, maturity_date_20y, coupon_rate, 25)
                        df.at[idx, '20Y Cally'] = yield_20y * 4 if not pd.isna(yield_20y) else ''
                        
                        # 30Y Cally hesapla
                        yield_30y = calculate_yield(settlement_date, maturity_date_30y, coupon_rate, 25)
                        df.at[idx, '30Y Cally'] = yield_30y * 4 if not pd.isna(yield_30y) else ''
                        
                        print(f"  {row.get('PREF IBKR', f'Row {idx}')}: 2Y={yield_2y * 4 if not pd.isna(yield_2y) else 'N/A'}, 5Y={yield_5y * 4 if not pd.isna(yield_5y) else 'N/A'}, 7Y={yield_7y * 4 if not pd.isna(yield_7y) else 'N/A'}, 10Y={yield_10y * 4 if not pd.isna(yield_10y) else 'N/A'}, 15Y={yield_15y * 4 if not pd.isna(yield_15y) else 'N/A'}, 20Y={yield_20y * 4 if not pd.isna(yield_20y) else 'N/A'}, 30Y={yield_30y * 4 if not pd.isna(yield_30y) else 'N/A'}")
                        
                    except Exception as e:
                        print(f"  Hata (Row {idx}): {e}")
                
                # Dosyayı kaydet
                df.to_csv(yek_file, index=False, encoding='utf-8-sig')
                print(f"✓ {yek_file} güncellendi")
                
            else:
                print(f"! Gerekli kolonlar bulunamadı")
            
        except Exception as e:
            print(f"! {yek_file} işlenirken hata: {e}")
    
    print(f"\n✓ Tüm yek dosyaları işlendi!")

def main():
    """Ana fonksiyon"""
    try:
        print("=== YIELD Hesaplama Scripti ===")
        process_yek_files()
        
    except Exception as e:
        print(f"Ana hata: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main() 