#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TradingView Dividend Calendar Scraper
TradingView'den dividend calendar verilerini çeker
"""

import pandas as pd
import os
import glob
import random
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import json

class TradingViewCalendarScraper:
    def __init__(self, headless=False):
        self.headless = headless
        self.driver = None
        self.corrected_count = 0
        self.total_checked = 0
        
    def setup_driver(self):
        """Chrome driver'ı hazırlar - TradingView için optimize edilmiş"""
        options = Options()
        
        # Headless modu kapat (bot tespit edilir)
        if self.headless:
            options.add_argument('--headless')
        
        # Temel ayarlar
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--start-maximized')
        
        # Anti-detection
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # User-Agent
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36'
        ]
        
        selected_ua = random.choice(user_agents)
        options.add_argument(f'--user-agent={selected_ua}')
        
        # Driver'ı başlat
        self.driver = webdriver.Chrome(options=options)
        
        # JavaScript injection
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return self.driver
    
    def get_dividend_calendar(self, from_date=None, to_date=None):
        """TradingView'den dividend calendar verilerini çeker"""
        try:
            if not self.driver:
                self.setup_driver()
            
            # TradingView dividend calendar sayfasına git
            url = "https://www.tradingview.com/markets/stocks-usa/dividend-calendar/"
            print(f"🔗 TradingView'e gidiliyor: {url}")
            
            self.driver.get(url)
            time.sleep(random.uniform(3, 5))
            
            # Sayfa yüklenmesini bekle
            wait = WebDriverWait(self.driver, 20)
            
            # Tarih filtrelerini ayarla
            if from_date and to_date:
                self._set_date_filters(from_date, to_date)
            
            # Dividend verilerini çek
            dividend_data = self._extract_dividend_data()
            
            return dividend_data
            
        except Exception as e:
            print(f"❌ TradingView'den veri çekilirken hata: {str(e)}")
            return []
    
    def _set_date_filters(self, from_date, to_date):
        """Tarih filtrelerini ayarlar"""
        try:
            print(f"📅 Tarih filtreleri ayarlanıyor: {from_date} - {to_date}")
            
            # Date picker'ları bul ve ayarla
            # Bu kısım TradingView'in UI yapısına göre ayarlanacak
            # Şimdilik basit bir implementasyon
            
        except Exception as e:
            print(f"⚠️ Tarih filtreleri ayarlanamadı: {e}")
    
    def _extract_dividend_data(self):
        """Sayfadan dividend verilerini çeker"""
        try:
            print("🔍 Dividend verileri çekiliyor...")
            
            # JavaScript ile veri çek
            js_script = """
            function extractDividendData() {
                var results = [];
                
                // Dividend tablosunu bul
                var tables = document.querySelectorAll('table');
                var dividendTable = null;
                
                for (var i = 0; i < tables.length; i++) {
                    var table = tables[i];
                    var text = table.textContent || '';
                    if (text.toLowerCase().includes('dividend') || text.toLowerCase().includes('ex-date')) {
                        dividendTable = table;
                        break;
                    }
                }
                
                if (dividendTable) {
                    var rows = dividendTable.querySelectorAll('tr');
                    
                    for (var j = 1; j < rows.length; j++) { // Header'ı atla
                        var row = rows[j];
                        var cells = row.querySelectorAll('td');
                        
                        if (cells.length >= 5) {
                            var symbol = cells[0] ? cells[0].textContent.trim() : '';
                            var exDate = cells[1] ? cells[1].textContent.trim() : '';
                            var amount = cells[2] ? cells[2].textContent.trim() : '';
                            var payDate = cells[3] ? cells[3].textContent.trim() : '';
                            var yield = cells[4] ? cells[4].textContent.trim() : '';
                            
                            if (symbol && exDate) {
                                results.push({
                                    symbol: symbol,
                                    ex_date: exDate,
                                    amount: amount,
                                    pay_date: payDate,
                                    yield: yield
                                });
                            }
                        }
                    }
                }
                
                return results;
            }
            
            return extractDividendData();
            """
            
            dividend_data = self.driver.execute_script(js_script)
            
            if dividend_data and len(dividend_data) > 0:
                print(f"✅ {len(dividend_data)} dividend verisi bulundu")
                return dividend_data
            else:
                print("❌ Dividend verisi bulunamadı")
                return []
                
        except Exception as e:
            print(f"❌ Veri çekme hatası: {e}")
            return []
    
    def get_ex_dividend_date_for_ticker(self, ticker):
        """Belirli bir ticker için ex-dividend date çeker"""
        try:
            if not self.driver:
                self.setup_driver()
            
            # TradingView symbol sayfasına git
            url = f"https://www.tradingview.com/symbols/{ticker}/"
            print(f"🔍 {ticker} için TradingView'e gidiliyor: {url}")
            
            self.driver.get(url)
            time.sleep(random.uniform(3, 5))
            
            # Dividend bilgilerini çek
            js_script = """
            function getDividendInfo() {
                // Dividend bilgilerini bul
                var dividendElements = document.querySelectorAll('[class*="dividend"], [class*="ex-date"]');
                var results = [];
                
                for (var i = 0; i < dividendElements.length; i++) {
                    var el = dividendElements[i];
                    var text = el.textContent || '';
                    
                    if (text.toLowerCase().includes('ex') || text.toLowerCase().includes('dividend')) {
                        results.push({
                            text: text,
                            element: el
                        });
                    }
                }
                
                return results;
            }
            
            return getDividendInfo();
            """
            
            dividend_info = self.driver.execute_script(js_script)
            
            if dividend_info and len(dividend_info) > 0:
                # En uygun bilgiyi bul
                for info in dividend_info:
                    text = info['text']
                    if 'ex' in text.lower() and 'date' in text.lower():
                        # Ex-date'i parse et
                        ex_date = self._parse_ex_date_from_text(text)
                        if ex_date:
                            print(f"✅ {ticker} ex-dividend date bulundu: {ex_date}")
                            return ex_date
            
            print(f"❌ {ticker} için ex-dividend date bulunamadı")
            return None
            
        except Exception as e:
            print(f"❌ {ticker} hatası: {str(e)}")
            return None
    
    def _parse_ex_date_from_text(self, text):
        """Text'ten ex-date'i parse eder"""
        try:
            # Çeşitli tarih formatlarını dene
            date_patterns = [
                r'(\d{1,2})/(\d{1,2})/(\d{4})',  # MM/DD/YYYY
                r'(\d{1,2})-(\d{1,2})-(\d{4})',  # MM-DD-YYYY
                r'(\d{4})-(\d{1,2})-(\d{1,2})',  # YYYY-MM-DD
                r'(\d{1,2})\.(\d{1,2})\.(\d{4})', # MM.DD.YYYY
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, text)
                if match:
                    if len(match.groups()) == 3:
                        if pattern == r'(\d{4})-(\d{1,2})-(\d{1,2})':
                            year, month, day = match.groups()
                        else:
                            month, day, year = match.groups()
                        
                        # CSV formatına çevir: MM/DD/YYYY
                        return f"{int(month):02d}/{int(day):02d}/{year}"
            
            return None
            
        except:
            return None
    
    def close(self):
        """Driver'ı kapat"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

def main():
    """Test fonksiyonu"""
    with TradingViewCalendarScraper(headless=False) as scraper:
        # Dividend calendar'ı çek
        dividend_data = scraper.get_dividend_calendar(from_date="2025-08-01", to_date="2025-08-31")
        
        print(f"\n📊 Bulunan dividend verileri: {len(dividend_data)}")
        
        for event in dividend_data:
            print({
                "Ticker": event["symbol"],
                "Ex-Dividend Date": event["ex_date"],
                "Dividend Amount": event["amount"],
                "Pay Date": event["pay_date"],
                "Yield": event["yield"]
            })

if __name__ == "__main__":
    main()

























