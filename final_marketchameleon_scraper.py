#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Final MarketChameleon Scraper
JavaScript yöntemi ile ex-dividend date bilgilerini çeker
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
import pandas as pd
from datetime import datetime

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
        options.add_argument('--disable-web-security')
        options.add_argument('--allow-running-insecure-content')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(options=options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return self.driver
    
    def get_ex_dividend_info(self, ticker):
        """Tek bir ticker için ex-dividend bilgilerini çeker"""
        url = f"https://marketchameleon.com/Overview/{ticker}/Dividends/"
        
        try:
            print(f"🔍 {ticker} için MarketChameleon'dan veri çekiliyor...")
            print(f"📱 URL: {url}")
            
            if not self.driver:
                self.setup_driver()
            
            # Sayfayı aç
            self.driver.get(url)
            
            # Sayfanın yüklenmesini bekle
            print("⏳ Sayfa yükleniyor (25 saniye)...")
            time.sleep(25)
            
            # JavaScript ile veri çek
            print("🔍 JavaScript ile veri çekiliyor...")
            
            js_script = """
            var tables = document.querySelectorAll('table');
            var results = [];
            
            for (var i = 0; i < tables.length; i++) {
                var table = tables[i];
                var rows = table.querySelectorAll('tr');
                
                for (var j = 1; j < rows.length; j++) {  // Header'ı atla
                    var row = rows[j];
                    var cells = row.querySelectorAll('td');
                    
                    if (cells.length >= 5) {
                        var exDate = cells[0].textContent.trim();
                        var amount = cells[4].textContent.trim();
                        
                        if (exDate && amount && exDate !== 'Ex Date') {
                            results.push({
                                exDate: exDate,
                                amount: amount
                            });
                        }
                    }
                }
            }
            
            return results;
            """
            
            js_results = self.driver.execute_script(js_script)
            
            if js_results and len(js_results) > 0:
                # En son ex-dividend (ilk sonuç)
                latest = js_results[0]
                
                # Sonraki ex-dividend (ikinci sonuç, eğer varsa)
                next_div = js_results[1] if len(js_results) > 1 else None
                
                print(f"\n🎯 {ticker} Ex-Dividend Bilgileri:")
                print(f"   📅 Son Ex-Date: {latest['exDate']}")
                print(f"   💰 Amount: ${latest['amount']}")
                
                if next_div:
                    print(f"   📅 Sonraki Ex-Date: {next_div['exDate']}")
                    print(f"   💰 Sonraki Amount: ${next_div['amount']}")
                
                return {
                    'ticker': ticker,
                    'last_ex_date': latest['exDate'],
                    'last_amount': latest['amount'],
                    'next_ex_date': next_div['exDate'] if next_div else None,
                    'next_amount': next_div['amount'] if next_div else None,
                    'all_dividends': js_results,
                    'success': True
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
    
    def batch_process(self, tickers, delay_between=3):
        """Birden fazla ticker'ı işler"""
        results = {}
        
        for i, ticker in enumerate(tickers):
            print(f"\n{'='*60}")
            print(f"📊 {ticker} İŞLENİYOR ({i+1}/{len(tickers)})")
            print(f"{'='*60}")
            
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
            filename = f'marketchameleon_ex_dividend_{timestamp}.csv'
        
        # Sonuçları düzenle
        data_rows = []
        for ticker, result in results.items():
            if result['success']:
                row = {
                    'Ticker': ticker,
                    'Last_Ex_Date': result['last_ex_date'],
                    'Last_Amount': result['last_amount'],
                    'Next_Ex_Date': result.get('next_ex_date', 'N/A'),
                    'Next_Amount': result.get('next_amount', 'N/A'),
                    'Total_Dividends_Found': len(result.get('all_dividends', [])),
                    'Status': 'Success'
                }
            else:
                row = {
                    'Ticker': ticker,
                    'Last_Ex_Date': 'N/A',
                    'Last_Amount': 'N/A',
                    'Next_Ex_Date': 'N/A',
                    'Next_Amount': 'N/A',
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
            self.driver.quit()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

def main():
    """Ana fonksiyon"""
    print("🚀 Final MarketChameleon Ex-Dividend Scraper")
    print("=" * 60)
    
    # Test ticker'ları
    test_tickers = ['DCOMP', 'AAPL', 'MSFT', 'JNJ']
    
    with MarketChameleonScraper(headless=False) as scraper:  # headless=False ile tarayıcıyı görebilirsiniz
        
        # Batch processing
        results = scraper.batch_process(test_tickers, delay_between=3)
        
        # Sonuçları göster
        print(f"\n📊 SONUÇ ÖZETİ:")
        print("=" * 60)
        
        success_count = 0
        for ticker, result in results.items():
            if result['success']:
                success_count += 1
                print(f"✅ {ticker}: {result['last_ex_date']} | ${result['last_amount']}")
            else:
                print(f"❌ {ticker}: {result.get('message', result.get('error', 'Bilinmeyen hata'))}")
        
        print(f"\n📈 Başarı Oranı: {success_count}/{len(test_tickers)} ({success_count/len(test_tickers)*100:.1f}%)")
        
        # CSV'ye kaydet
        scraper.save_to_csv(results)

if __name__ == "__main__":
    main()

























