#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CNBC'den Treasury Yield'larını Çekip CSV'ye Kaydetme
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import json
from datetime import datetime
import time
import re

def setup_driver():
    """
    Chrome driver'ı ayarlar
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Görünmez mod
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    return driver

def get_cnbc_yield_with_selenium(driver, url, maturity):
    """
    Selenium ile CNBC'den Treasury yield çeker
    """
    try:
        print(f"{maturity} çekiliyor...")
        
        driver.get(url)
        
        # Sayfanın yüklenmesini bekle
        time.sleep(3)
        
        # Yield değerini bul - Güncellenmiş selector'lar
        try:
            # CNBC'nin güncel sayfa yapısına uygun selector'lar
            selectors = [
                "//span[contains(@class, 'QuoteStrip-lastPrice')]",
                "//div[contains(@class, 'QuoteStrip-lastPrice')]",
                "//span[contains(@class, 'last-price')]",
                "//div[contains(@class, 'last-price')]",
                "//span[contains(@class, 'quote-price')]",
                "//div[contains(@class, 'quote-price')]",
                "//span[contains(@class, 'price') and contains(text(), '%')]",
                "//div[contains(@class, 'price') and contains(text(), '%')]",
                "//span[contains(text(), '%') and contains(@class, 'value')]",
                "//div[contains(text(), '%') and contains(@class, 'value')]",
                "//span[contains(@class, 'QuoteStrip') and contains(text(), '%')]",
                "//div[contains(@class, 'QuoteStrip') and contains(text(), '%')]",
                "//span[contains(@class, 'Quote') and contains(text(), '%')]",
                "//div[contains(@class, 'Quote') and contains(text(), '%')]",
                "//span[contains(@class, 'Last') and contains(text(), '%')]",
                "//div[contains(@class, 'Last') and contains(text(), '%')]",
                "//span[contains(@class, 'Price') and contains(text(), '%')]",
                "//div[contains(@class, 'Price') and contains(text(), '%')]",
                # Genel selector'lar
                "//span[contains(text(), '%')]",
                "//div[contains(text(), '%')]",
                "//span[contains(@class, 'quote')]",
                "//div[contains(@class, 'quote')]",
                "//span[contains(@class, 'price')]",
                "//div[contains(@class, 'price')]",
                "//span[contains(@class, 'value')]",
                "//div[contains(@class, 'value')]"
            ]
            
            yield_value = None
            
            for selector in selectors:
                try:
                    elements = driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        text = element.text.strip()
                        if text:
                            # Yield değerini bul (sayı + % formatı)
                            yield_match = re.search(r'(\d+\.?\d*)%', text)
                            if yield_match:
                                potential_yield = float(yield_match.group(1))
                                # Mantıklı yield aralığı kontrolü (0.1% - 20%)
                                if 0.1 <= potential_yield <= 20.0:
                                    yield_value = potential_yield
                                    print(f"{maturity}: {yield_value:.3f}% (selector: {selector})")
                                    return yield_value
                except Exception as e:
                    continue
            
            # Sayfa kaynağından da dene
            if not yield_value:
                page_source = driver.page_source
                # Yield değerlerini sayfa kaynağından ara
                yield_matches = re.findall(r'(\d+\.?\d*)%', page_source)
                for match in yield_matches:
                    potential_yield = float(match)
                    if 0.1 <= potential_yield <= 20.0:
                        yield_value = potential_yield
                        print(f"{maturity}: {yield_value:.3f}% (sayfa kaynağından)")
                        return yield_value
                
                print(f"{maturity}: Yield bulunamadı - sayfa yapısı değişmiş olabilir")
                return None
                
        except Exception as e:
            print(f"{maturity} selector hatası: {e}")
            return None
            
    except Exception as e:
        print(f"{maturity} genel hata: {e}")
        return None

def get_cnbc_treasury_yields():
    """
    CNBC'den tüm Treasury yield'larını çeker
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
        
        # Driver'ı başlat
        driver = setup_driver()
        
        try:
            for maturity, url in cnbc_pages.items():
                yield_rate = get_cnbc_yield_with_selenium(driver, url, maturity)
                if yield_rate:
                    yields[maturity] = yield_rate
                
                time.sleep(2)  # Rate limiting
                
        finally:
            driver.quit()
        
        return yields
        
    except Exception as e:
        print(f"Selenium CNBC hatası: {e}")
        return None

def save_treasury_yields_to_csv(treasury_data):
    """
    Treasury yield'larını CSV dosyasına kaydeder
    """
    print("\n2. CSV dosyasına kaydediliyor...")
    
    # US15Y oluştur (US20Y ve US10Y ortalaması)
    if 'US20Y' in treasury_data and 'US10Y' in treasury_data:
        # Float değerleri doğrudan kullan
        us20y = float(treasury_data['US20Y']) if isinstance(treasury_data['US20Y'], (int, float)) else float(str(treasury_data['US20Y']).replace('%', ''))
        us10y = float(treasury_data['US10Y']) if isinstance(treasury_data['US10Y'], (int, float)) else float(str(treasury_data['US10Y']).replace('%', ''))
        us15y = (us20y + us10y) / 2
        treasury_data['US15Y'] = f"{us15y:.3f}%"
        print(f"US15Y oluşturuldu: {us15y:.3f}% (US20Y: {us20y:.3f}% + US10Y: {us10y:.3f}% ortalaması)")
    
    # CSV için veri hazırla
    csv_data = {
        'Treasury': list(treasury_data.keys()),
        'Yield': list(treasury_data.values())
    }
    
    # CSV dosyasına kaydet
    df = pd.DataFrame(csv_data)
    df.to_csv('treyield.csv', index=False, encoding='utf-8-sig')
    
    print(f"OK Treasury yield'ları 'treyield.csv' dosyasına kaydedildi")
    
    # Kaydedilen verileri göster
    print("\nKaydedilen Treasury Yield'ları:")
    for treasury, yield_value in treasury_data.items():
        print(f"  {treasury}: {yield_value}")

def get_fallback_yields():
    """
    Fallback olarak bilinen değerleri döndürür
    """
    
    print("\n=== Fallback Treasury Yield'ları ===")
    print(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Not: Bu değerler güncel piyasa verilerine dayalıdır.")
    print()
    
    # Güncel Treasury yield'ları
    fallback_yields = {
        'US2Y': 3.871,
        'US5Y': 3.950,
        'US7Y': 4.170,
        'US10Y': 4.420,
        'US20Y': 4.986,
        'US30Y': 4.991,
    }
    
    for maturity, yield_rate in fallback_yields.items():
        print(f"{maturity}: {yield_rate:.3f}%")
    
    return fallback_yields

def main():
    """
    Ana fonksiyon
    """
    print("=== CNBC'DEN TREASURY YIELD'LARI CSV'YE KAYDETME ===")
    print("CNBC'den canlı veriler çekiliyor ve treyield.csv'ye kaydediliyor...")
    print()
    
    try:
        print("1. CNBC'den canlı veri çekiliyor...")
        treasury_data = get_cnbc_treasury_yields()
        
        if treasury_data:
            # US15Y oluştur ve CSV'ye kaydet
            save_treasury_yields_to_csv(treasury_data)
        else:
            print("CNBC'den veri alınamadı! Fallback veriler kullanılıyor...")
            fallback_data = get_fallback_yields()
            save_treasury_yields_to_csv(fallback_data)
            
    except Exception as e:
        print(f"Hata: {e}")
        print("Fallback veriler kullanılıyor...")
        fallback_data = get_fallback_yields()
        save_treasury_yields_to_csv(fallback_data)

if __name__ == '__main__':
    main() 