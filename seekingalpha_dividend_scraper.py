#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SeekingAlpha Dividend Scraper
SeekingAlpha'dan ex-dividend date bilgilerini çeker
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import pandas as pd
from datetime import datetime
import re

class SeekingAlphaDividendScraper:
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
        
        # Anti-detection options
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(options=options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return self.driver
    
    def get_ex_dividend_info(self, ticker):
        """SeekingAlpha'dan ex-dividend bilgilerini çeker"""
        url = f"https://seekingalpha.com/symbol/{ticker}/dividends/history"
        
        try:
            print(f"🔍 {ticker} için SeekingAlpha'dan veri çekiliyor...")
            print(f"📱 URL: {url}")
            
            if not self.driver:
                self.setup_driver()
            
            # Sayfayı aç
            self.driver.get(url)
            
            # Sayfanın yüklenmesini bekle
            print("⏳ Sayfa yükleniyor (10 saniye)...")
            time.sleep(10)
            
            # JavaScript ile veri çek
            print("🔍 JavaScript ile veri çekiliyor...")
            
            js_script = """
            var results = [];
            
            // Dividend history tablosunu bul
            var tables = document.querySelectorAll('table');
            console.log('Toplam tablo sayısı:', tables.length);
            
            for (var i = 0; i < tables.length; i++) {
                var table = tables[i];
                var rows = table.querySelectorAll('tr');
                console.log('Tablo', i, 'satır sayısı:', rows.length);
                
                // Header'ı bul
                var headerRow = rows[0];
                var headerCells = headerRow.querySelectorAll('th');
                var headerTexts = [];
                for (var j = 0; j < headerCells.length; j++) {
                    headerTexts.push(headerCells[j].textContent.trim());
                }
                console.log('Headers:', headerTexts);
                
                // Ex-Date kolonunu bul
                var exDateIndex = -1;
                for (var j = 0; j < headerTexts.length; j++) {
                    if (headerTexts[j].toLowerCase().includes('ex') || 
                        headerTexts[j].toLowerCase().includes('date')) {
                        exDateIndex = j;
                        break;
                    }
                }
                
                if (exDateIndex >= 0) {
                    console.log('Ex-Date kolonu bulundu:', exDateIndex);
                    
                    // Data satırlarını işle
                    for (var j = 1; j < rows.length; j++) {
                        var row = rows[j];
                        var cells = row.querySelectorAll('td');
                        
                        if (cells.length > exDateIndex) {
                            var exDate = cells[exDateIndex].textContent.trim();
                            var amount = '';
                            
                            // Amount kolonunu bul
                            for (var k = 0; k < headerTexts.length; k++) {
                                if (headerTexts[k].toLowerCase().includes('amount') || 
                                    headerTexts[k].toLowerCase().includes('dividend')) {
                                    if (cells[k]) {
                                        amount = cells[k].textContent.trim();
                                    }
                                    break;
                                }
                            }
                            
                            if (exDate && exDate !== 'Ex-Date' && exDate !== 'N/A') {
                                results.push({
                                    exDate: exDate,
                                    amount: amount,
                                    tableIndex: i,
                                    rowIndex: j
                                });
                            }
                        }
                    }
                }
            }
            
            console.log('Toplam sonuç:', results.length);
            return results;
            """
            
            js_results = self.driver.execute_script(js_script)
            
            if js_results and len(js_results) > 0:
                # En son ex-dividend (ilk sonuç)
                latest = js_results[0]
                
                print(f"\n🎯 {ticker} Ex-Dividend Bilgileri:")
                print(f"   📅 Son Ex-Date: {latest['exDate']}")
                print(f"   💰 Amount: {latest['amount']}")
                
                return {
                    'ticker': ticker,
                    'success': True,
                    'method': 'seekingalpha',
                    'ex_dividend_date': latest['exDate'],
                    'amount': latest['amount'],
                    'total_dividends_found': len(js_results)
                }
            else:
                print(f"❌ {ticker} için veri bulunamadı")
                return {
                    'ticker': ticker,
                    'success': False,
                    'message': 'Veri bulunamadı'
                }
                
        except Exception as e:
            print(f"❌ {ticker} hatası: {str(e)}")
            return {
                'ticker': ticker,
                'success': False,
                'error': str(e)
            }
    
    def batch_process_tickers(self, tickers, delay_between=3):
        """Birden fazla ticker'ı işler"""
        results = {}
        
        for i, ticker in enumerate(tickers):
            print(f"\n{'='*60}")
            print(f"📊 {ticker} İŞLENİYOR ({i+1}/{len(tickers)})")
            print(f"{'='*60}")
            
            # Ex-dividend bilgilerini çek
            result = self.get_ex_dividend_info(ticker)
            results[ticker] = result
            
            # Ticker'lar arası gecikme
            if i < len(tickers) - 1:
                print(f"⏳ Sonraki ticker için {delay_between} saniye bekleniyor...")
                time.sleep(delay_between)
        
        return results
    
    def save_to_csv(self, results, filename=None):
        """Sonuçları CSV dosyasına kaydeder"""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'seekingalpha_ex_dividend_{timestamp}.csv'
        
        # Sonuçları düzenle
        data_rows = []
        for ticker, result in results.items():
            if result and result.get('success'):
                row = {
                    'Ticker': ticker,
                    'Ex_Dividend_Date': result.get('ex_dividend_date', 'N/A'),
                    'Amount': result.get('amount', 'N/A'),
                    'Method': result.get('method', 'N/A'),
                    'Total_Dividends_Found': result.get('total_dividends_found', 0),
                    'Status': 'Success'
                }
            else:
                row = {
                    'Ticker': ticker,
                    'Ex_Dividend_Date': 'N/A',
                    'Amount': 'N/A',
                    'Method': 'N/A',
                    'Total_Dividends_Found': 0,
                    'Status': f"Error: {result.get('message', result.get('error', 'Unknown error'))}"
                }
            data_rows.append(row)
        
        # DataFrame oluştur ve kaydet
        df = pd.DataFrame(data_rows)
        df.to_csv(filename, index=False, encoding='utf-8')
        print(f"\n💾 Sonuçlar {filename} dosyasına kaydedildi.")
        
        return df
    
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
    """Ana fonksiyon"""
    print("🚀 SeekingAlpha Ex-Dividend Scraper")
    print("=" * 50)
    
    # Test ticker'ları
    test_tickers = ['PRH', 'DCOMP', 'AAPL']
    
    with SeekingAlphaDividendScraper(headless=False) as scraper:  # headless=False ile tarayıcıyı görebilirsiniz
        
        # Batch processing
        results = scraper.batch_process_tickers(test_tickers, delay_between=3)
        
        # Sonuçları göster
        print(f"\n📊 SONUÇ ÖZETİ:")
        print("=" * 60)
        
        success_count = 0
        for ticker, result in results.items():
            if result and result.get('success'):
                success_count += 1
                ex_div_date = result.get('ex_dividend_date', 'N/A')
                amount = result.get('amount', 'N/A')
                print(f"✅ {ticker}: Ex-Div Date={ex_div_date} | Amount={amount}")
            else:
                print(f"❌ {ticker}: {result.get('message', result.get('error', 'Bilinmeyen hata'))}")
        
        print(f"\n📈 Başarı Oranı: {success_count}/{len(test_tickers)} ({success_count/len(test_tickers)*100:.1f}%)")
        
        # CSV'ye kaydet
        scraper.save_to_csv(results)

if __name__ == "__main__":
    main()

























