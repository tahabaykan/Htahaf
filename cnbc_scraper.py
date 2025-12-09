#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CNBC Ex-Dividend Date Scraper
CNBC'den ex-dividend date verilerini çeker
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

class CNBCExDivScraper:
    def __init__(self, headless=False):
        self.headless = headless
        self.driver = None
        self.corrected_count = 0
        self.total_checked = 0
        
    def setup_driver(self):
        """Chrome driver'ı hazırlar - CNBC için optimize edilmiş"""
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
    
    def _convert_ticker_format(self, ticker):
        """Ticker formatını CNBC formatına çevirir"""
        try:
            # LNC PRD → LNC'D formatına çevir
            # " PR" yerine "'" koy
            if ' PR' in ticker:
                converted = ticker.replace(' PR', "'")
                print(f"   🔄 Ticker formatı çevrildi: {ticker} → {converted}")
                return converted
            else:
                return ticker
        except:
            return ticker
    
    def get_ex_dividend_date(self, ticker, max_retries=3):
        """CNBC'den ex-dividend date bilgisini çeker"""
        # Ticker formatını çevir
        converted_ticker = self._convert_ticker_format(ticker)
        
        for attempt in range(max_retries):
            try:
                print(f"🔍 {ticker} için CNBC'den veri çekiliyor... (Deneme {attempt + 1}/{max_retries})")
                print(f"   🔄 Ticker: {ticker} → {converted_ticker}")
                
                if not self.driver:
                    self.setup_driver()
                
                # CNBC quote sayfasına git
                url = f"https://www.cnbc.com/quotes/{converted_ticker}?qsearchterm="
                print(f"   🔗 URL: {url}")
                
                self.driver.get(url)
                time.sleep(random.uniform(3, 5))
                
                # Sayfa yüklenmesini bekle
                wait = WebDriverWait(self.driver, 20)
                
                # EVENTS bölümünü bul ve ex-dividend date'i çek
                ex_date = self._extract_ex_dividend_date()
                
                if ex_date:
                    print(f"✅ {ticker} ex-dividend date bulundu: {ex_date}")
                    return ex_date
                else:
                    print(f"❌ {ticker} için veri bulunamadı")
                    
                    # Retry için bekleme
                    if attempt < max_retries - 1:
                        print(f"🔄 {attempt + 1}. deneme başarısız, {random.uniform(3, 6):.1f} saniye sonra tekrar deneniyor...")
                        time.sleep(random.uniform(3, 6))
                        continue
                    else:
                        print(f"❌ {max_retries} deneme sonunda veri bulunamadı")
                        return None
                        
            except Exception as e:
                print(f"❌ {ticker} hatası (Deneme {attempt + 1}): {str(e)}")
                
                # Retry için bekleme
                if attempt < max_retries - 1:
                    print(f"🔄 {attempt + 1}. deneme hatası, {random.uniform(3, 6):.1f} saniye sonra tekrar deneniyor...")
                    time.sleep(random.uniform(3, 6))
                    continue
                else:
                    print(f"❌ {max_retries} deneme sonunda başarısız")
                    return None
        
        # Tüm denemeler başarısız
        print(f"❌ {ticker} için tüm denemeler başarısız")
        return None
    
    def _extract_ex_dividend_date(self):
        """Sayfadan ex-dividend date'i çeker"""
        try:
            print("🔍 Ex-dividend date aranıyor...")
            
            # JavaScript ile EVENTS bölümünden ex-dividend date'i çek
            js_script = """
            function findExDividendDate() {
                // EVENTS bölümünü bul
                var eventsSection = null;
                
                // "EVENTS" text'ini içeren elementleri ara
                var allElements = document.querySelectorAll('*');
                for (var i = 0; i < allElements.length; i++) {
                    var el = allElements[i];
                    var text = el.textContent || el.innerText || '';
                    if (text.trim() === 'EVENTS') {
                        eventsSection = el;
                        break;
                    }
                }
                
                if (!eventsSection) {
                    // Alternatif olarak "Ex Div Date" text'ini ara
                    for (var i = 0; i < allElements.length; i++) {
                        var el = allElements[i];
                        var text = el.textContent || el.innerText || '';
                        if (text.includes('Ex Div Date')) {
                            eventsSection = el;
                            break;
                        }
                    }
                }
                
                if (eventsSection) {
                    // Ex Div Date değerini bul
                    var parent = eventsSection.parentElement || eventsSection;
                    var text = parent.textContent || parent.innerText || '';
                    
                    // Ex Div Date pattern'ini ara
                    var exDivPattern = /Ex Div Date\\s*([\\d\\/\\-]+)/i;
                    var match = text.match(exDivPattern);
                    
                    if (match && match[1]) {
                        return match[1].trim();
                    }
                    
                    // Alternatif pattern: "Ex Div Date" sonrası gelen tarih
                    var exDivIndex = text.indexOf('Ex Div Date');
                    if (exDivIndex !== -1) {
                        var afterExDiv = text.substring(exDivIndex);
                        var lines = afterExDiv.split('\\n');
                        for (var j = 0; j < lines.length; j++) {
                            var line = lines[j].trim();
                            if (line && /^[\\d\\/\\-]+$/.test(line)) {
                                return line;
                            }
                        }
                    }
                }
                
                return null;
            }
            
            return findExDividendDate();
            """
            
            ex_date = self.driver.execute_script(js_script)
            
            if ex_date:
                # Tarihi parse et ve formatla
                formatted_date = self._parse_and_format_date(ex_date)
                if formatted_date:
                    return formatted_date
                else:
                    return ex_date
            else:
                print("❌ Ex-dividend date bulunamadı")
                return None
                
        except Exception as e:
            print(f"❌ Veri çekme hatası: {e}")
            return None
    
    def _parse_and_format_date(self, date_str):
        """Tarihi parse eder ve CSV formatına çevirir"""
        try:
            if not date_str:
                return None
            
            # Çeşitli tarih formatlarını dene
            date_patterns = [
                r'(\d{1,2})/(\d{1,2})/(\d{4})',  # MM/DD/YYYY
                r'(\d{1,2})-(\d{1,2})-(\d{4})',  # MM-DD-YYYY
                r'(\d{4})-(\d{1,2})-(\d{1,2})',  # YYYY-MM-DD
                r'(\d{1,2})\.(\d{1,2})\.(\d{4})', # MM.DD.YYYY
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, date_str)
                if match:
                    if len(match.groups()) == 3:
                        if pattern == r'(\d{4})-(\d{1,2})-(\d{1,2})':
                            year, month, day = match.groups()
                        else:
                            month, day, year = match.groups()
                        
                        # CSV formatına çevir: MM/DD/YYYY
                        return f"{int(month):02d}/{int(day):02d}/{year}"
            
            # Eğer pattern bulunamazsa orijinal string'i döndür
            return date_str
            
        except:
            return date_str
    
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
    with CNBCExDivScraper(headless=False) as scraper:
        # Test ticker'ları
        test_tickers = ["NEWTI", "KEY'J", "LNC'D", "SPNT'B"]
        
        for ticker in test_tickers:
            print(f"\n{'='*50}")
            print(f"Test: {ticker}")
            print(f"{'='*50}")
            
            ex_date = scraper.get_ex_dividend_date(ticker)
            if ex_date:
                print(f"✅ {ticker}: {ex_date}")
            else:
                print(f"❌ {ticker}: Veri bulunamadı")
            
            time.sleep(2)

if __name__ == "__main__":
    main()
