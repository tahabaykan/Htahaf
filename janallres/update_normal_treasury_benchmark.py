#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Normal Treasury Benchmark Güncelleme
Kupon oranlarına göre uygun benchmark atar
"""

import pandas as pd
import glob
import os

def update_normal_treasury_benchmark():
    """Normal Treasury Benchmark kolonunu güncelle"""
    print("=== Normal Treasury Benchmark Güncelleme ===")
    
    # YEK dosyalarını bul
    yek_files = glob.glob('yek*.csv')
    print(f"Bulunan YEK dosyaları: {len(yek_files)}")
    
    for yek_file in yek_files:
        try:
            print(f"\nİşleniyor: {yek_file}")
            
            # YEK dosyasını oku
            df = pd.read_csv(yek_file)
            print(f"  {len(df)} satır okundu")
            
            # Normal Treasury Bench kolonu ekle veya güncelle
            df['Normal Treasury Bench'] = ''
            
            # Her hisse için Normal Treasury Benchmark belirle
            for index, row in df.iterrows():
                try:
                    # COUPON değerini al
                    coupon = row.get('COUPON', '')
                    
                    if isinstance(coupon, str) and '%' in coupon:
                        coupon_rate = float(coupon.replace('%', ''))
                    else:
                        coupon_rate = float(coupon) if coupon else 0
                    
                    # Kupon oranına göre benchmark belirle
                    if coupon_rate >= 8.0:
                        benchmark = 'US2Y'
                    elif coupon_rate >= 7.0:
                        benchmark = 'US5Y'
                    elif coupon_rate >= 6.0:
                        benchmark = 'US7Y'
                    elif coupon_rate >= 5.0:
                        benchmark = 'US10Y'
                    elif coupon_rate >= 4.0:
                        benchmark = 'US15Y'
                    elif coupon_rate >= 3.0:
                        benchmark = 'US20Y'
                    else:
                        benchmark = 'US30Y'
                    
                    df.at[index, 'Normal Treasury Bench'] = benchmark
                    
                except Exception as e:
                    print(f"  Hisse {index} için hesaplama hatası: {e}")
                    df.at[index, 'Normal Treasury Bench'] = 'US30Y'
            
            # Dosyayı kaydet
            df.to_csv(yek_file, index=False, encoding='utf-8-sig')
            print(f"  [OK] {yek_file} güncellendi")
            
        except Exception as e:
            print(f"  [ERROR] {yek_file} işlenirken hata: {e}")
    
    print(f"\n[OK] Normal Treasury Benchmark güncellendi")

if __name__ == "__main__":
    update_normal_treasury_benchmark()





























