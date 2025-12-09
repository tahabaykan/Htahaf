#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MarketChameleon Ex-Dividend Scraper
MarketChameleon'dan ex-dividend date bilgilerini çeker
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import pandas as pd
from datetime import datetime
import re

class MarketChameleonScraper:
    def __init__(self, headless=True):
        self.headless = headless
        self.driver = None
    
    def setup_driver(self):
        """Chrome driver'ı hazırlar"""
        options = Options()
        if self.headless:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
        
        self.driver = webdriver.Chrome(options=options)
        return self.driver
    
    def get_ex_dividend_info(self, ticker):
        """MarketChameleon'dan ex-dividend bilgilerini çeker"""
        url = f"https://marketchameleon.com/Overview/{ticker}/Dividends/"
        
        try:
            print(f"🔍 {ticker} için MarketChameleon'dan veri çekiliyor...")
            print(f"📱 URL: {url}")
            
            if not self.driver:
                self.setup_driver()
            
            self.driver.get(url)
            time.sleep(5)  # Sayfanın yüklenmesini bekle
            
            # Historical Dividends tablosunu bul
            historical_data = self._extract_historical_dividends()
            
            # Projected Dividends tablosunu bul
            projected_data = self._extract_projected_dividends()
            
            return {
                'ticker': ticker,
                'historical_dividends': historical_data,
                'projected_dividends': projected_data,
                'success': True
            }
            
        except Exception as e:
            print(f"❌ Hata: {str(e)}")
            return {
                'ticker': ticker,
                'success': False,
                'error': str(e)
            }
    
    def _extract_historical_dividends(self):
        """Historical Dividends tablosundan veri çeker"""
        try:
            # Historical Dividends başlığını bul
            historical_header = self.driver.find_element(By.XPATH, "//div[contains(text(), 'Historical Dividends')]")
            
            # Tabloyu bul (header'dan sonraki tablo)
            table = historical_header.find_element(By.XPATH, "following-sibling::table")
            
            # Tablo verilerini çek
            rows = table.find_elements(By.TAG_NAME, "tr")
            
            historical_data = []
            for row in rows[1:]:  # Header'ı atla
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 5:
                    ex_date = cells[0].text.strip()
                    record_date = cells[1].text.strip()
                    pay_date = cells[2].text.strip()
                    amount = cells[4].text.strip()
                    
                    if ex_date and amount:
                        historical_data.append({
                            'ex_date': ex_date,
                            'record_date': record_date,
                            'pay_date': pay_date,
                            'amount': amount
                        })
            
            print(f"📊 {len(historical_data)} historical dividend bulundu")
            return historical_data
            
        except Exception as e:
            print(f"Historical dividends çekilemedi: {str(e)}")
            return []
    
    def _extract_projected_dividends(self):
        """Projected Dividends tablosundan veri çeker"""
        try:
            # Projected Dividends başlığını bul
            projected_header = self.driver.find_element(By.XPATH, "//div[contains(text(), 'Projected')]")
            
            # Tabloyu bul
            table = projected_header.find_element(By.XPATH, "following-sibling::table")
            
            # Tablo verilerini çek
            rows = table.find_elements(By.TAG_NAME, "tr")
            
            projected_data = []
            for row in rows[1:]:  # Header'ı atla
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 5:
                    ex_date = cells[0].text.strip()
                    amount = cells[5].text.strip()
                    
                    if ex_date and amount:
                        projected_data.append({
                            'ex_date': ex_date,
                            'amount': amount
                        })
            
            print(f"🔮 {len(projected_data)} projected dividend bulundu")
            return projected_data
            
        except Exception as e:
            print(f"Projected dividends çekilemedi: {str(e)}")
            return []
    
    def get_latest_ex_dividend(self, ticker):
        """En son ex-dividend date'i döner"""
        info = self.get_ex_dividend_info(ticker)
        
        if info['success'] and info['historical_dividends']:
            # En son historical dividend'ı al
            latest = info['historical_dividends'][0]  # İlk sırada en son olan var
            return {
                'ticker': ticker,
                'last_ex_date': latest['ex_date'],
                'last_amount': latest['amount'],
                'next_projected': info['projected_dividends'][0] if info['projected_dividends'] else None
            }
        
        return None
    
    def close(self):
        """Driver'ı kapat"""
        if self.driver:
            self.driver.quit()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

def main():
    """Ana fonksiyon"""
    print("🚀 MarketChameleon Ex-Dividend Scraper")
    print("=" * 50)
    
    # Test ticker'ları
    test_tickers = ['DCOMP', 'AAPL', 'MSFT']
    
    with MarketChameleonScraper(headless=False) as scraper:  # headless=False ile tarayıcıyı görebilirsiniz
        
        for ticker in test_tickers:
            print(f"\n{'='*50}")
            print(f"📊 {ticker} İŞLENİYOR")
            print(f"{'='*50}")
            
            # Ex-dividend bilgilerini çek
            info = scraper.get_ex_dividend_info(ticker)
            
            if info['success']:
                print(f"\n✅ {ticker} başarıyla işlendi!")
                
                # Historical dividends
                if info['historical_dividends']:
                    print(f"\n📅 Historical Dividends:")
                    for div in info['historical_dividends'][:3]:  # İlk 3'ü göster
                        print(f"   Ex-Date: {div['ex_date']} | Amount: ${div['amount']}")
                
                # Projected dividends
                if info['projected_dividends']:
                    print(f"\n🔮 Projected Dividends:")
                    for div in info['projected_dividends'][:3]:  # İlk 3'ü göster
                        print(f"   Ex-Date: {div['ex_date']} | Amount: ${div['amount']}")
                
                # En son ex-dividend
                latest = scraper.get_latest_ex_dividend(ticker)
                if latest:
                    print(f"\n🎯 En Son Ex-Dividend:")
                    print(f"   Ticker: {latest['ticker']}")
                    print(f"   Ex-Date: {latest['last_ex_date']}")
                    print(f"   Amount: ${latest['last_amount']}")
                    if latest['next_projected']:
                        print(f"   Sonraki Projeksiyon: {latest['next_projected']['ex_date']}")
            else:
                print(f"❌ {ticker} işlenemedi: {info.get('error', 'Bilinmeyen hata')}")
            
            print(f"\n⏳ Sonraki ticker için 3 saniye bekleniyor...")
            time.sleep(3)

if __name__ == "__main__":
    main()

























