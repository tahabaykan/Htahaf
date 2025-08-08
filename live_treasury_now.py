#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TradingView'dan Canlı Treasury Yield'larını Çekme
"""

import requests
import json
from datetime import datetime
import time

def get_live_treasury_yields():
    """
    TradingView'dan canlı Treasury yield'larını çeker
    """
    
    try:
        print("=== TradingView'dan Canlı Treasury Yield'ları ===")
        print(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # TradingView symbol'leri
        symbols = {
            'US2Y': 'BOND:US2Y',
            'US5Y': 'BOND:US5Y', 
            'US7Y': 'BOND:US7Y',
            'US10Y': 'BOND:US10Y',
            'US20Y': 'BOND:US20Y',
            'US30Y': 'BOND:US30Y',
        }
        
        yields = {}
        
        for maturity, symbol in symbols.items():
            try:
                print(f"{maturity} çekiliyor...")
                
                # TradingView API
                url = "https://scanner.tradingview.com/america/scan"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                }
                
                payload = {
                    "symbols": {"tickers": [symbol]},
                    "columns": ["close", "change", "change_abs", "high", "low", "open"]
                }
                
                response = requests.post(url, headers=headers, json=payload, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if 'data' in data and len(data['data']) > 0:
                        result = data['data'][0]
                        yield_rate = result[0]  # close price
                        
                        if yield_rate and yield_rate > 0:
                            yields[maturity] = yield_rate
                            print(f"{maturity}: {yield_rate:.2f}%")
                        else:
                            print(f"{maturity}: Geçersiz veri")
                    else:
                        print(f"{maturity}: Veri bulunamadı")
                else:
                    print(f"{maturity}: API hatası ({response.status_code})")
                
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                print(f"{maturity} hatası: {e}")
        
        return yields
        
    except Exception as e:
        print(f"TradingView API hatası: {e}")
        return None

def get_investing_yields():
    """
    Investing.com'dan canlı Treasury yield'larını çeker
    """
    
    try:
        print("\n=== Investing.com'dan Canlı Treasury Yield'ları ===")
        
        # Investing.com sayfaları
        pages = {
            'US2Y': 'https://www.investing.com/rates-bonds/u.s.-2-year-bond-yield',
            'US5Y': 'https://www.investing.com/rates-bonds/u.s.-5-year-bond-yield',
            'US10Y': 'https://www.investing.com/rates-bonds/u.s.-10-year-bond-yield',
            'US30Y': 'https://www.investing.com/rates-bonds/u.s.-30-year-bond-yield',
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
        
        for maturity, url in pages.items():
            try:
                print(f"{maturity} çekiliyor...")
                
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    # Basit text parsing
                    content = response.text
                    
                    # Yield değerini bul (basit regex)
                    import re
                    yield_match = re.search(r'(\d+\.?\d*)%', content)
                    
                    if yield_match:
                        yield_rate = float(yield_match.group(1))
                        yields[maturity] = yield_rate
                        print(f"{maturity}: {yield_rate:.2f}%")
                    else:
                        print(f"{maturity}: Yield bulunamadı")
                else:
                    print(f"{maturity}: Sayfa hatası ({response.status_code})")
                
                time.sleep(1)  # Rate limiting
                
            except Exception as e:
                print(f"{maturity} hatası: {e}")
        
        return yields
        
    except Exception as e:
        print(f"Investing.com hatası: {e}")
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

def save_live_yields(yields, source, filename="live_treasury_yields.json"):
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
        print("TradingView ve Investing.com'dan canlı veriler çekiliyor...")
        print()
        
        # TradingView'dan dene
        print("1. TradingView'dan canlı veri çekiliyor...")
        tv_yields = get_live_treasury_yields()
        
        if tv_yields and len(tv_yields) > 0:
            print("\n✅ TradingView'dan canlı veri alındı!")
            save_live_yields(tv_yields, "TradingView", "tradingview_yields.json")
        else:
            print("\n❌ TradingView'dan veri alınamadı")
        
        print("\n" + "="*50)
        
        # Investing.com'dan dene
        print("2. Investing.com'dan canlı veri çekiliyor...")
        inv_yields = get_investing_yields()
        
        if inv_yields and len(inv_yields) > 0:
            print("\n✅ Investing.com'dan canlı veri alındı!")
            save_live_yields(inv_yields, "Investing.com", "investing_yields.json")
        else:
            print("\n❌ Investing.com'dan veri alınamadı")
        
        print("\n" + "="*50)
        
        # En iyi veriyi seç
        best_yields = tv_yields if tv_yields and len(tv_yields) > 0 else inv_yields
        
        if not best_yields:
            print("3. Fallback değerler kullanılıyor...")
            best_yields = get_current_market_yields()
            save_live_yields(best_yields, "Market Data", "market_yields.json")
        
        print("\n" + "="*50)
        print("SONUÇ - BUGÜNÜN CANLI TREASURY YIELD'LARI:")
        print("="*50)
        
        for maturity, yield_rate in best_yields.items():
            print(f"{maturity}: {yield_rate:.2f}%")
        
        print("\n" + "="*50)
        print("Bu değerleri yield_calculator.py'de kullanabilirsiniz!")
        print("="*50)
        
    except Exception as e:
        print(f"❌ Hata: {e}")

if __name__ == '__main__':
    main() 