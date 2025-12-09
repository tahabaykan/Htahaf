#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Improved MarketChameleon Scraper
Sayfa yüklenme sorunlarını çözer
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time

def get_ex_dividend_date(ticker):
    """Tek bir ticker için ex-dividend date çeker"""
    url = f"https://marketchameleon.com/Overview/{ticker}/Dividends/"
    
    # Chrome options
    options = Options()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-web-security')
    options.add_argument('--allow-running-insecure-content')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    driver = None
    try:
        print(f"🔍 {ticker} için MarketChameleon açılıyor...")
        print(f"📱 URL: {url}")
        
        driver = webdriver.Chrome(options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Sayfayı aç
        driver.get(url)
        
        # Sayfanın tamamen yüklenmesini bekle
        print("⏳ Sayfa yükleniyor (15 saniye)...")
        time.sleep(15)
        
        # JavaScript'in çalışmasını bekle
        print("⏳ JavaScript çalışıyor...")
        time.sleep(5)
        
        # Sayfa kaynağını kontrol et
        page_source = driver.page_source
        print(f"📄 Sayfa yüklendi. Boyut: {len(page_source)} karakter")
        
        # "Historical Dividends" metnini ara
        if "Historical Dividends" in page_source:
            print("✅ Historical Dividends metni bulundu")
        else:
            print("❌ Historical Dividends metni bulunamadı")
        
        # "Ex Date" metnini ara
        if "Ex Date" in page_source:
            print("✅ Ex Date metni bulundu")
        else:
            print("❌ Ex Date metni bulunamadı")
        
        # Tüm tabloları bul
        print("📊 Tablolar aranıyor...")
        tables = driver.find_elements(By.TAG_NAME, "table")
        print(f"✅ {len(tables)} tablo bulundu")
        
        # Her tabloyu kontrol et
        for i, table in enumerate(tables):
            try:
                print(f"\n📋 Tablo {i+1} kontrol ediliyor...")
                
                # Tablo başlığını bul
                headers = table.find_elements(By.TAG_NAME, "th")
                if headers:
                    header_texts = [h.text.strip() for h in headers]
                    print(f"   Headers: {header_texts}")
                    
                    # Ex Date header'ı var mı kontrol et
                    if any("ex" in h.lower() and "date" in h.lower() for h in header_texts):
                        print(f"   ✅ Ex Date header bulundu!")
                        
                        # Tablo satırlarını al
                        rows = table.find_elements(By.TAG_NAME, "tr")
                        print(f"   📊 {len(rows)} satır bulundu")
                        
                        if len(rows) > 1:  # Header + en az 1 data row
                            # İlk data row'u al
                            first_data_row = rows[1]
                            cells = first_data_row.find_elements(By.TAG_NAME, "td")
                            
                            print(f"   📝 {len(cells)} hücre bulundu")
                            
                            if len(cells) >= 5:
                                ex_date = cells[0].text.strip()
                                amount = cells[4].text.strip()
                                
                                if ex_date and amount:
                                    print(f"\n🎯 {ticker} Ex-Dividend Bilgileri:")
                                    print(f"   📅 Son Ex-Date: {ex_date}")
                                    print(f"   💰 Amount: ${amount}")
                                    
                                    return {
                                        'ticker': ticker,
                                        'last_ex_date': ex_date,
                                        'amount': amount,
                                        'success': True
                                    }
                                else:
                                    print(f"   ❌ Ex-date veya amount boş")
                            else:
                                print(f"   ❌ Yeterli hücre yok: {len(cells)}")
                        else:
                            print(f"   ❌ Data row yok")
                    else:
                        print(f"   ❌ Ex Date header bulunamadı")
                else:
                    print(f"   ❌ Header bulunamadı")
                    
            except Exception as e:
                print(f"   ❌ Tablo {i+1} hatası: {str(e)}")
                continue
        
        # Alternatif olarak sayfa kaynağından regex ile ara
        print("\n🔍 Regex ile arama yapılıyor...")
        import re
        
        # Ex Date pattern'ı ara
        ex_date_pattern = r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})'
        ex_dates = re.findall(ex_date_pattern, page_source)
        
        if ex_dates:
            print(f"✅ {len(ex_dates)} tarih bulundu:")
            for date in ex_dates[:5]:  # İlk 5'i göster
                print(f"   📅 {date}")
            
            # Amount pattern'ı ara
            amount_pattern = r'\$(\d+\.\d+)'
            amounts = re.findall(amount_pattern, page_source)
            
            if amounts:
                print(f"✅ {len(amounts)} amount bulundu:")
                for amount in amounts[:5]:  # İlk 5'i göster
                    print(f"   💰 ${amount}")
                
                return {
                    'ticker': ticker,
                    'last_ex_date': ex_dates[0] if ex_dates else 'N/A',
                    'amount': f"${amounts[0]}" if amounts else 'N/A',
                    'success': True,
                    'method': 'regex'
                }
        
        return {
            'ticker': ticker,
            'success': False,
            'message': 'Veri çekilemedi'
        }
        
    except Exception as e:
        print(f"❌ Hata: {str(e)}")
        return {
            'ticker': ticker,
            'success': False,
            'error': str(e)
        }
    
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

def main():
    """Ana fonksiyon"""
    print("🚀 Improved MarketChameleon Scraper")
    print("=" * 50)
    
    # Test ticker'ları
    tickers = ['DCOMP']
    
    for ticker in tickers:
        print(f"\n{'='*50}")
        print(f"📊 {ticker} İŞLENİYOR")
        print(f"{'='*50}")
        
        result = get_ex_dividend_date(ticker)
        
        if result['success']:
            print(f"✅ {ticker} başarıyla işlendi!")
            if 'method' in result:
                print(f"   🔧 Kullanılan yöntem: {result['method']}")
        else:
            print(f"❌ {ticker} işlenemedi: {result.get('message', result.get('error', 'Bilinmeyen hata'))}")

if __name__ == "__main__":
    main()

























