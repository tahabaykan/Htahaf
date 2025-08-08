#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
15 Aralık 2024 Simülasyonu - Tüm scriptleri o tarihte çalıştırılmış gibi simüle eder
"""

import subprocess
import sys
import os
from datetime import datetime, date
import pandas as pd

# Simülasyon tarihi
SIMULATION_DATE = "2024-12-15"
print(f"SIMULATION 15 Aralık 2024 Simülasyonu Başlıyor...")
print(f"DATE Simülasyon Tarihi: {SIMULATION_DATE}")

# Tarih ayarlarını değiştirmek için environment variable
os.environ['SIMULATION_DATE'] = SIMULATION_DATE
os.environ['SIMULATION_MODE'] = 'true'

scripts = [
    "decnibkrtry.py",
    "decnnormalize_data.py", 
    "decnmaster_processor.py",  # Yek dosyalarını oluşturur
    "decnbefore_common_adv.py",
    "decncommon_stocks.py",
    "decncalculate_scores.py",
    "decnfill_missing_solidity_data.py",
    "decnmarket_risk_analyzer.py",
    "decncalculate_thebest.py",
]

print("\nINFO Çalıştırılacak Scriptler:")
for i, script in enumerate(scripts, 1):
    print(f"  {i}. {script}")

print(f"\nSTART Simülasyon başlıyor...")
print("="*60)

for i, script in enumerate(scripts, 1):
    print(f"\nINFO [{i}/{len(scripts)}] Çalıştırılıyor: {script}")
    print("-" * 40)
    
    try:
        result = subprocess.run([sys.executable, script], 
                              env=os.environ.copy(),
                              capture_output=True,
                              text=True)
        
        if result.returncode != 0:
            print(f"ERROR Hata oluştu: {script}")
            print(f"Hata mesajı: {result.stderr}")
            print(f"Çıktı: {result.stdout}")
            break
        else:
            print(f"OK Başarılı: {script}")
            if result.stdout:
                print(f"Çıktı: {result.stdout[:200]}...")
                
    except Exception as e:
        print(f"ERROR Script çalıştırma hatası: {e}")
        break

print("\n" + "="*60)
print("SIMULATION Tamamlandı!")
print("INFO 15 Aralık 2024 FINAL_THG sonuçları hazır.")

# Sonuçları göster
print("\nINFO FINAL_THG Sonuçları (15 Aralık 2024):")
try:
    # FINE dosyalarını bul ve en yüksek FINAL_THG'leri göster
    fine_files = [f for f in os.listdir('.') if f.startswith('decfinek') and f.endswith('.csv')]
    
    for fine_file in fine_files:
        print(f"\nINFO {fine_file}:")
        df = pd.read_csv(fine_file)
        if 'FINAL_THG' in df.columns:
            top_5 = df.nlargest(5, 'FINAL_THG')[['PREF IBKR', 'FINAL_THG']]
            print(top_5.to_string(index=False))
        else:
            print("FINAL_THG kolonu bulunamadı")
            
except Exception as e:
    print(f"Sonuç gösterme hatası: {e}")

print(f"\nSUCCESS 15 Aralık 2024 Simülasyonu Tamamlandı!") 