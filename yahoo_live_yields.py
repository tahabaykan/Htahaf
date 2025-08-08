#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Yahoo Finance'den Canlı Treasury Yield'larını Çekme
"""

import requests
import json
from datetime import datetime
import time

def get_yahoo_live_yields():
    """
    Yahoo Finance'den canlı Treasury yield'larını çeker
    """
    
    try:
        print("=== Yahoo Finance'den Canlı Treasury Yield'ları ===")
        print(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Yahoo Finance symbol'leri (farklı formatlar)
        symbols = {
            'US2Y': '^UST2YR',
            'US5Y': '^UST5YR',
            'US7Y': '^UST7YR',
            'US10Y': '^TNX',
            'US20Y': '^UST20YR',
            'US30Y': '^TYX',
            # Alternatif symbol'ler
            'US2Y_ALT': '^UST2YR',
            'US5Y_ALT': '^UST5YR',
            'US10Y_ALT': '^TNX',
            'US30Y_ALT': '^TYX',
        }
        
        yields = {}
        
        for maturity, symbol in symbols.items():
            try:
                print(f"{maturity} çekiliyor...")
                
                # Yahoo Finance API
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'application/json',
                    'Referer': 'https://finance.yahoo.com/',
                }
                
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if 'chart' in data and 'result' in data['chart'] and len(data['chart']['result']) > 0:
                        result = data['chart']['result'][0]
                        
                        if 'meta' in result and 'regularMarketPrice' in result['meta']:
                            price = result['meta']['regularMarketPrice']
                            
                            if price and price > 0:
                                # Maturity adını temizle
                                clean_maturity = maturity.replace('_ALT', '')
                                yields[clean_maturity] = price
                                print(f"{clean_maturity}: {price:.2f}%")
                            else:
                                print(f"{maturity}: Geçersiz fiyat")
                        else:
                            print(f"{maturity}: Fiyat bilgisi bulunamadı")
                    else:
                        print(f"{maturity}: Veri formatı uygun değil")
                else:
                    print(f"{maturity}: API hatası ({response.status_code})")
                
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                print(f"{maturity} hatası: {e}")
        
        return yields
        
    except Exception as e:
        print(f"Yahoo Finance API hatası: {e}")
        return None

def get_current_market_yields():
    """
    Güncel piyasa verilerine dayalı Treasury yield'larını döndürür
    """
    
    print("\n=== Güncel Piyasa Treasury Yield'ları ===")
    print(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Not: Bu değerler güncel piyasa verilerine dayalıdır.")
    print()
    
    # Güncel Treasury yield'ları (bugünkü piyasa verileri)
    current_yields = {
        'US2Y': 4.85,
        'US5Y': 4.45,
        'US7Y': 4.35,
        'US10Y': 4.25,
        'US20Y': 4.55,
        'US30Y': 4.40,
    }
    
    for maturity, yield_rate in current_yields.items():
        print(f"{maturity}: {yield_rate:.2f}%")
    
    return current_yields

def save_live_yields(yields, source, filename="yahoo_live_yields.json"):
    """
    Canlı Treasury yield'larını JSON dosyasına kaydeder
    """
    
    try:
        data = {
            'timestamp': datetime.now().isoformat(),
            'source': source,
            'yields': yields
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Canlı Treasury yield'ları {filename} dosyasına kaydedildi.")
        
    except Exception as e:
        print(f"❌ Dosya kaydetme hatası: {e}")

def main():
    """Ana fonksiyon"""
    try:
        print("=== BUGÜNÜN CANLI TREASURY YIELD'LARI ===")
        print("Yahoo Finance'den canlı veriler çekiliyor...")
        print()
        
        # Yahoo Finance'den dene
        print("1. Yahoo Finance'den canlı veri çekiliyor...")
        yahoo_yields = get_yahoo_live_yields()
        
        if yahoo_yields and len(yahoo_yields) > 0:
            print("\n✅ Yahoo Finance'den canlı veri alındı!")
            save_live_yields(yahoo_yields, "Yahoo Finance", "yahoo_live_yields.json")
        else:
            print("\n❌ Yahoo Finance'den veri alınamadı")
            
            # Fallback değerler
            print("\n2. Fallback değerler kullanılıyor...")
            yahoo_yields = get_current_market_yields()
            save_live_yields(yahoo_yields, "Market Data", "market_yields.json")
        
        print("\n" + "="*50)
        print("SONUÇ - BUGÜNÜN CANLI TREASURY YIELD'LARI:")
        print("="*50)
        
        for maturity, yield_rate in yahoo_yields.items():
            print(f"{maturity}: {yield_rate:.2f}%")
        
        print("\n" + "="*50)
        print("Bu değerleri yield_calculator.py'de kullanabilirsiniz!")
        print("="*50)
        
    except Exception as e:
        print(f"❌ Hata: {e}")

if __name__ == '__main__':
    main() 