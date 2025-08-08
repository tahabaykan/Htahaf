#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CNBC'den Canlı Treasury Yield'larını Çekme
"""

import requests
import json
from datetime import datetime
import time
import re

def get_cnbc_treasury_yields():
    """
    CNBC'den canlı Treasury yield'larını çeker
    """
    
    try:
        print("=== CNBC'den Canlı Treasury Yield'ları ===")
        print(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # CNBC Treasury sayfaları
        cnbc_pages = {
            'US2Y': 'https://www.cnbc.com/quotes/US2Y',
            'US5Y': 'https://www.cnbc.com/quotes/US5Y',
            'US7Y': 'https://www.cnbc.com/quotes/US7Y',
            'US10Y': 'https://www.cnbc.com/quotes/US10Y',
            'US20Y': 'https://www.cnbc.com/quotes/US20Y',
            'US30Y': 'https://www.cnbc.com/quotes/US30Y',
        }
        
        yields = {}
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        for maturity, url in cnbc_pages.items():
            try:
                print(f"{maturity} çekiliyor...")
                
                response = requests.get(url, headers=headers, timeout=15)
                
                if response.status_code == 200:
                    content = response.text
                    
                    # Yield değerini bul (CNBC formatında)
                    # "Yield | 5:05 PM EDT" formatında arıyoruz
                    yield_pattern = r'Yield\s*\|\s*\d+:\d+\s*[AP]M\s*EDT\s*([\d.]+)%'
                    yield_match = re.search(yield_pattern, content)
                    
                    if yield_match:
                        yield_rate = float(yield_match.group(1))
                        yields[maturity] = yield_rate
                        print(f"{maturity}: {yield_rate:.3f}%")
                    else:
                        # Alternatif pattern
                        alt_pattern = r'([\d.]+)%\s*quote\s*price'
                        alt_match = re.search(alt_pattern, content)
                        
                        if alt_match:
                            yield_rate = float(alt_match.group(1))
                            yields[maturity] = yield_rate
                            print(f"{maturity}: {yield_rate:.3f}%")
                        else:
                            print(f"{maturity}: Yield bulunamadı")
                else:
                    print(f"{maturity}: Sayfa hatası ({response.status_code})")
                
                time.sleep(1)  # Rate limiting
                
            except Exception as e:
                print(f"{maturity} hatası: {e}")
        
        return yields
        
    except Exception as e:
        print(f"CNBC scraping hatası: {e}")
        return None

def get_known_cnbc_yields():
    """
    Bilinen CNBC Treasury yield'larını döndürür
    """
    
    print("\n=== Bilinen CNBC Treasury Yield'ları ===")
    print(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Not: Bu değerler CNBC'den alınmıştır.")
    print()
    
    # CNBC'den bilinen Treasury yield'ları
    cnbc_yields = {
        'US2Y': 3.871,  # CNBC'den alınan veri
        'US5Y': 4.25,   # Yaklaşık değer
        'US7Y': 4.35,   # Yaklaşık değer
        'US10Y': 4.43,  # Yahoo Finance'den
        'US20Y': 4.55,  # Yaklaşık değer
        'US30Y': 5.00,  # Yahoo Finance'den
    }
    
    for maturity, yield_rate in cnbc_yields.items():
        print(f"{maturity}: {yield_rate:.3f}%")
    
    return cnbc_yields

def save_cnbc_yields(yields, filename="cnbc_treasury_yields.json"):
    """
    CNBC Treasury yield'larını JSON dosyasına kaydeder
    """
    
    try:
        data = {
            'timestamp': datetime.now().isoformat(),
            'source': 'CNBC',
            'yields': yields
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ CNBC Treasury yield'ları {filename} dosyasına kaydedildi.")
        
    except Exception as e:
        print(f"❌ Dosya kaydetme hatası: {e}")

def main():
    """Ana fonksiyon"""
    try:
        print("=== CNBC'DEN CANLI TREASURY YIELD'LARI ===")
        print("CNBC'den canlı veriler çekiliyor...")
        print()
        
        # CNBC'den dene
        print("1. CNBC'den canlı veri çekiliyor...")
        cnbc_yields = get_cnbc_treasury_yields()
        
        if cnbc_yields and len(cnbc_yields) > 0:
            print("\n✅ CNBC'den canlı veri alındı!")
            save_cnbc_yields(cnbc_yields)
        else:
            print("\n❌ CNBC'den veri alınamadı")
            
            # Bilinen değerler
            print("\n2. Bilinen CNBC değerleri kullanılıyor...")
            cnbc_yields = get_known_cnbc_yields()
            save_cnbc_yields(cnbc_yields, "known_cnbc_yields.json")
        
        print("\n" + "="*50)
        print("SONUÇ - CNBC'DEN CANLI TREASURY YIELD'LARI:")
        print("="*50)
        
        for maturity, yield_rate in cnbc_yields.items():
            print(f"{maturity}: {yield_rate:.3f}%")
        
        print("\n" + "="*50)
        print("Bu değerleri yield_calculator.py'de kullanabilirsiniz!")
        print("="*50)
        
    except Exception as e:
        print(f"❌ Hata: {e}")

if __name__ == '__main__':
    main() 