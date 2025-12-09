#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Yek CSV Dosyaları Oluşturma Scripti
nek*.csv dosyalarını okuyup yek*.csv dosyaları oluşturur
7 yeni kolon ekler: 2Y Cally, 5Y Cally, 7Y Cally, 10Y Cally, 15Y Cally, 20Y Cally, 30Y Cally
"""

import pandas as pd
import glob
import os
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

def create_yek_files():
    """nek*.csv dosyalarını okuyup yek*.csv dosyaları oluştur"""
    
    # nek ile başlayan tüm CSV dosyalarını bul
    nek_files = glob.glob('nek*.csv')
    
    print(f"Bulunan nek dosyaları: {len(nek_files)} adet")
    for file in nek_files:
        print(f"  - {file}")
    
    for nek_file in nek_files:
        try:
            print(f"\n=== {nek_file} işleniyor ===")
            
            # Dosyayı oku - tırnak işaretlerini koru
            df = pd.read_csv(nek_file, quoting=1)  # QUOTE_ALL
            print(f"[OK] {nek_file} yüklendi: {len(df)} satır, {len(df.columns)} kolon")
            
            # Last Price kontrolü
            if 'Last Price' in df.columns:
                print(f"[OK] Last Price kolonu mevcut")
                print(f"  Örnek Last Price değerleri: {df['Last Price'].head(3).tolist()}")
            else:
                print(f"! Last Price kolonu bulunamadı!")
            
            # Yeni dosya adını oluştur (nek -> yek)
            yek_file = nek_file.replace('nek', 'yek')
            
            # 7 yeni kolon ekle (15Y Cally dahil)
            new_columns = ['2Y Cally', '5Y Cally', '7Y Cally', '10Y Cally', '15Y Cally', '20Y Cally', '30Y Cally']
            
            for col in new_columns:
                df[col] = ''  # Boş değerlerle başlat
            
            print(f"[OK] 7 yeni kolon eklendi: {new_columns}")
            
            # Yeni dosyayı kaydet - tırnak işaretlerini koru
            df.to_csv(yek_file, index=False, encoding='utf-8-sig', quoting=1)  # QUOTE_ALL
            print(f"[OK] {yek_file} oluşturuldu: {len(df)} satır, {len(df.columns)} kolon")
            
        except Exception as e:
            print(f"! {nek_file} işlenirken hata: {e}")
    
    print(f"\n=== YEK DOSYALARI OLUŞTURULDU ===")

if __name__ == "__main__":
    create_yek_files()





























