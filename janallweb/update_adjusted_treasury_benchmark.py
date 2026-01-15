#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adjusted Treasury Benchmark Güncelleme
Normal Treasury Benchmark'a göre adjusted benchmark atar
"""

import pandas as pd
import glob
import os

def update_adjusted_treasury_benchmark():
    """Adjusted Treasury Benchmark kolonunu güncelle"""
    print("=== Adjusted Treasury Benchmark Güncelleme ===")
    
    # YEK dosyalarını bul
    yek_files = glob.glob('yek*.csv')
    print(f"Bulunan YEK dosyaları: {len(yek_files)}")
    
    for yek_file in yek_files:
        try:
            print(f"\nİşleniyor: {yek_file}")
            
            # YEK dosyasını oku
            df = pd.read_csv(yek_file)
            print(f"  {len(df)} satır okundu")
            
            # Adjusted Treasury Bench kolonu ekle veya güncelle
            df['Adj Treasury Bench'] = ''
            
            # Her hisse için Adjusted Treasury Benchmark belirle
            for index, row in df.iterrows():
                try:
                    # Normal Treasury Bench değerini al
                    normal_bench = row.get('Normal Treasury Bench', 'US30Y')
                    
                    # Adjusted benchmark belirle (bir seviye yukarı)
                    if normal_bench == 'US2Y':
                        adj_bench = 'US5Y'
                    elif normal_bench == 'US5Y':
                        adj_bench = 'US7Y'
                    elif normal_bench == 'US7Y':
                        adj_bench = 'US10Y'
                    elif normal_bench == 'US10Y':
                        adj_bench = 'US15Y'
                    elif normal_bench == 'US15Y':
                        adj_bench = 'US20Y'
                    elif normal_bench == 'US20Y':
                        adj_bench = 'US30Y'
                    else:
                        adj_bench = 'US30Y'
                    
                    df.at[index, 'Adj Treasury Bench'] = adj_bench
                    
                except Exception as e:
                    print(f"  Hisse {index} için hesaplama hatası: {e}")
                    df.at[index, 'Adj Treasury Bench'] = 'US30Y'
            
            # Dosyayı kaydet
            df.to_csv(yek_file, index=False, encoding='utf-8-sig')
            print(f"  [OK] {yek_file} güncellendi")
            
        except Exception as e:
            print(f"  [ERROR] {yek_file} işlenirken hata: {e}")
    
    print(f"\n[OK] Adjusted Treasury Benchmark güncellendi")

if __name__ == "__main__":
    update_adjusted_treasury_benchmark()































