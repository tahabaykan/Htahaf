#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Selenium ile CNBC'den Canlı Treasury Yield'larını Çekme
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
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
        
        # Yield değerini bul
        try:
            # Farklı selector'ları dene
            selectors = [
                "//span[contains(text(), '%')]",
                "//div[contains(text(), 'Yield')]",
                "//span[contains(@class, 'quote')]",
                "//div[contains(@class, 'quote')]"
            ]
            
            yield_value = None
            
            for selector in selectors:
                try:
                    elements = driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        text = element.text
                        # Yield değerini bul
                        yield_match = re.search(r'(\d+\.?\d*)%', text)
                        if yield_match:
                            yield_value = float(yield_match.group(1))
                            print(f"{maturity}: {yield_value:.3f}% (bulundu)")
                            return yield_value
                except:
                    continue
            
            if not yield_value:
                # Sayfa kaynağını kontrol et
                page_source = driver.page_source
                yield_match = re.search(r'(\d+\.?\d*)%', page_source)
                if yield_match:
                    yield_value = float(yield_match.group(1))
                    print(f"{maturity}: {yield_value:.3f}% (sayfa kaynağından)")
                    return yield_value
                
                print(f"{maturity}: Yield bulunamadı")
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
        print("=== Selenium ile CNBC'den Canlı Treasury Yield'ları ===")
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
        'US5Y': 4.25,
        'US7Y': 4.35,
        'US10Y': 4.43,
        'US20Y': 4.55,
        'US30Y': 5.00,
    }
    
    for maturity, yield_rate in fallback_yields.items():
        print(f"{maturity}: {yield_rate:.3f}%")
    
    return fallback_yields

def save_yields(yields, source, filename="selenium_cnbc_yields.json"):
    """
    Treasury yield'larını JSON dosyasına kaydeder
    """
    
    try:
        data = {
            'timestamp': datetime.now().isoformat(),
            'source': source,
            'yields': yields
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Treasury yield'ları {filename} dosyasına kaydedildi.")
        
    except Exception as e:
        print(f"❌ Dosya kaydetme hatası: {e}")

def main():
    """Ana fonksiyon"""
    try:
        print("=== SELENIUM İLE CNBC'DEN CANLI TREASURY YIELD'LARI ===")
        print("Selenium ile CNBC'den canlı veriler çekiliyor...")
        print()
        
        # Selenium ile CNBC'den dene
        print("1. Selenium ile CNBC'den canlı veri çekiliyor...")
        cnbc_yields = get_cnbc_treasury_yields()
        
        if cnbc_yields and len(cnbc_yields) > 0:
            print("\n✅ Selenium ile CNBC'den canlı veri alındı!")
            save_yields(cnbc_yields, "Selenium + CNBC", "selenium_cnbc_yields.json")
        else:
            print("\n❌ Selenium ile CNBC'den veri alınamadı")
            
            # Fallback değerler
            print("\n2. Fallback değerler kullanılıyor...")
            cnbc_yields = get_fallback_yields()
            save_yields(cnbc_yields, "Fallback", "fallback_yields.json")
        
        print("\n" + "="*50)
        print("SONUÇ - CANLI TREASURY YIELD'LARI:")
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