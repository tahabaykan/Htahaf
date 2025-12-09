#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple MarketChameleon Scraper
DCOMP gibi ticker'lar için ex-dividend date çeker
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
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
    
    driver = None
    try:
        print(f"🔍 {ticker} için MarketChameleon açılıyor...")
        print(f"📱 URL: {url}")
        
        driver = webdriver.Chrome(options=options)
        driver.get(url)
        
        # Sayfanın yüklenmesini bekle
        print("⏳ Sayfa yükleniyor...")
        time.sleep(8)
        
        # Historical Dividends tablosundan en son ex-date'i bul
        print("📊 Historical dividends tablosu aranıyor...")
        
        # Tüm tabloları bul
        tables = driver.find_elements(By.TAG_NAME, "table")
        
        if tables:
            print(f"✅ {len(tables)} tablo bulundu")
            
            # İkinci tablo genellikle Historical Dividends
            if len(tables) >= 2:
                historical_table = tables[1]  # İkinci tablo
                
                # Tablo satırlarını al
                rows = historical_table.find_elements(By.TAG_NAME, "tr")
                
                if len(rows) > 1:  # Header + en az 1 data row
                    # İlk data row'u al (en son ödenen)
                    first_data_row = rows[1]
                    cells = first_data_row.find_elements(By.TAG_NAME, "td")
                    
                    if len(cells) >= 5:
                        ex_date = cells[0].text.strip()
                        amount = cells[4].text.strip()
                        
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
                        print(f"❌ Yeterli hücre bulunamadı: {len(cells)} hücre")
                else:
                    print(f"❌ Data row bulunamadı: {len(rows)} row")
            else:
                print(f"❌ Historical dividends tablosu bulunamadı")
        else:
            print(f"❌ Hiç tablo bulunamadı")
        
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
            driver.quit()

def main():
    """Ana fonksiyon"""
    print("🚀 Simple MarketChameleon Scraper")
    print("=" * 40)
    
    # Test ticker'ları
    tickers = ['DCOMP', 'AAPL']
    
    for ticker in tickers:
        print(f"\n{'='*40}")
        print(f"📊 {ticker} İŞLENİYOR")
        print(f"{'='*40}")
        
        result = get_ex_dividend_date(ticker)
        
        if result['success']:
            print(f"✅ {ticker} başarıyla işlendi!")
        else:
            print(f"❌ {ticker} işlenemedi: {result.get('message', result.get('error', 'Bilinmeyen hata'))}")
        
        print(f"\n⏳ Sonraki ticker için 5 saniye bekleniyor...")
        time.sleep(5)

if __name__ == "__main__":
    main()

























