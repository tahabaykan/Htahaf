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
    
    # Çalışma dizinini yazdır
    current_dir = os.getcwd()
    print(f"🔍 Çalışma dizini: {current_dir}")
    
    # Sadece ana dizindeki nek dosyalarını bul (alt dizinlerdeki değil)
    nek_files = []
    for file in os.listdir(current_dir):
        if file.startswith('nek') and file.endswith('.csv'):
            # Dosya ana dizinde mi kontrol et
            file_path = os.path.join(current_dir, file)
            if os.path.isfile(file_path) and not os.path.dirname(file_path).endswith(('janall', 'janallw', 'janall_backup')):
                nek_files.append(file)
    
    # Mevcut dizindeki tüm CSV dosyalarını da listele
    all_csv_files = [f for f in os.listdir(current_dir) if f.endswith('.csv') and not os.path.dirname(os.path.join(current_dir, f)).endswith(('janall', 'janallw', 'janall_backup'))]
    print(f"📁 Mevcut dizindeki tüm CSV dosyaları ({len(all_csv_files)} adet):")
    for file in all_csv_files:
        print(f"  - {file}")
    
    print(f"\n🔍 Bulunan nek dosyaları (sadece ana dizinden): {len(nek_files)} adet")
    for file in nek_files:
        print(f"  - {file}")
    
    for nek_file in nek_files:
        try:
            print(f"\n=== {nek_file} işleniyor ===")
            
            # Dosyayı oku - tırnak işaretlerini koru
            df = pd.read_csv(nek_file, quoting=1)  # QUOTE_ALL
            print(f"✓ {nek_file} yüklendi: {len(df)} satır, {len(df.columns)} kolon")
            
            # Last Price kontrolü
            if 'Last Price' in df.columns:
                print(f"✓ Last Price kolonu mevcut")
                print(f"  Örnek Last Price değerleri: {df['Last Price'].head(3).tolist()}")
            else:
                print(f"! Last Price kolonu bulunamadı!")
            
            # Yeni dosya adını oluştur (nek -> yek)
            yek_file = nek_file.replace('nek', 'yek')
            
            # 7 yeni kolon ekle (15Y Cally dahil)
            new_columns = ['2Y Cally', '5Y Cally', '7Y Cally', '10Y Cally', '15Y Cally', '20Y Cally', '30Y Cally']
            
            for col in new_columns:
                df[col] = ''  # Boş değerlerle başlat
            
            print(f"✓ 6 yeni kolon eklendi: {new_columns}")
            
            # Yeni dosyayı kaydet - tırnak işaretlerini koru
            df.to_csv(yek_file, index=False, encoding='utf-8-sig', quoting=1)  # QUOTE_ALL
            print(f"✓ {yek_file} oluşturuldu: {len(df)} satır, {len(df.columns)} kolon")
            
            # İlk birkaç satırı göster
            print(f"\n{yek_file} - İlk 3 satır:")
            if 'Last Price' in df.columns:
                print(df[['PREF IBKR', 'Last Price']].head(3).to_string())
            else:
                print(df.head(3).to_string())
            
        except Exception as e:
            print(f"! {nek_file} işlenirken hata: {e}")
    
    print(f"\n✓ Tüm yek dosyaları oluşturuldu!")

def main():
    """Ana fonksiyon"""
    try:
        print("=== Yek CSV Dosyaları Oluşturma Scripti ===")
        print("⚠️  SADECE ANA DİZİNDEKİ (StockTracker) NEK DOSYALARI KULLANILACAK!")
        print("⚠️  Alt dizinlerdeki (janall, janallw, vb.) dosyalar kullanılmayacak!")
        create_yek_files()
        
    except Exception as e:
        print(f"Ana hata: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main() 