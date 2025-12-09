#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Advanced MarketChameleon Scraper
JavaScript ile dinamik yüklenen tabloları çeker
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import re

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
        print("⏳ Sayfa yükleniyor (20 saniye)...")
        time.sleep(20)
        
        # JavaScript'in çalışmasını bekle
        print("⏳ JavaScript çalışıyor...")
        time.sleep(10)
        
        # Sayfa kaynağını kontrol et
        page_source = driver.page_source
        print(f"📄 Sayfa yüklendi. Boyut: {len(page_source)} karakter")
        
        # Historical Dividends tablosunu bekle
        print("📊 Historical Dividends tablosu bekleniyor...")
        try:
            # Historical Dividends başlığını bul
            historical_header = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'Historical Dividends')]"))
            )
            print("✅ Historical Dividends başlığı bulundu")
            
            # Tabloyu bul
            historical_table = historical_header.find_element(By.XPATH, "following-sibling::table")
            print("✅ Historical Dividends tablosu bulundu")
            
            # Tablo satırlarını bekle
            rows = WebDriverWait(historical_table, 20).until(
                EC.presence_of_all_elements_located((By.TAG_NAME, "tr"))
            )
            print(f"📊 {len(rows)} satır bulundu")
            
            if len(rows) > 1:  # Header + en az 1 data row
                # İlk data row'u al (en son ödenen)
                first_data_row = rows[1]
                
                # Hücreleri bekle
                cells = WebDriverWait(first_data_row, 20).until(
                    EC.presence_of_all_elements_located((By.TAG_NAME, "td"))
                )
                print(f"📝 {len(cells)} hücre bulundu")
                
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
                            'success': True,
                            'method': 'table_extraction'
                        }
                    else:
                        print(f"   ❌ Ex-date veya amount boş")
                else:
                    print(f"   ❌ Yeterli hücre yok: {len(cells)}")
            else:
                print(f"   ❌ Data row yok")
                
        except Exception as e:
            print(f"❌ Tablo çekme hatası: {str(e)}")
        
        # Alternatif olarak sayfa kaynağından regex ile ara
        print("\n🔍 Regex ile arama yapılıyor...")
        
        # Ex Date pattern'ı ara (daha spesifik)
        ex_date_pattern = r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})'
        ex_dates = re.findall(ex_date_pattern, page_source)
        
        if ex_dates:
            print(f"✅ {len(ex_dates)} tarih bulundu:")
            for date in ex_dates[:5]:  # İlk 5'i göster
                print(f"   📅 {date}")
            
            # Amount pattern'ı ara (daha spesifik)
            amount_pattern = r'\$(\d+\.\d+)'
            amounts = re.findall(amount_pattern, page_source)
            
            if amounts:
                print(f"✅ {len(amounts)} amount bulundu:")
                for amount in amounts[:5]:  # İlk 5'i göster
                    print(f"   💰 ${amount}")
                
                # En son tarihi ve amount'u bul
                latest_date = ex_dates[0] if ex_dates else 'N/A'
                latest_amount = amounts[0] if amounts else 'N/A'
                
                print(f"\n🎯 {ticker} Ex-Dividend Bilgileri (Regex):")
                print(f"   📅 Son Ex-Date: {latest_date}")
                print(f"   💰 Amount: ${latest_amount}")
                
                return {
                    'ticker': ticker,
                    'last_ex_date': latest_date,
                    'amount': f"${latest_amount}",
                    'success': True,
                    'method': 'regex'
                }
        
        # Son çare: JavaScript ile veri çek
        print("\n🔍 JavaScript ile veri çekme deneniyor...")
        try:
            # JavaScript ile tablo verilerini çek
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
                        
                        if (exDate && amount) {
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
            
            js_results = driver.execute_script(js_script)
            
            if js_results and len(js_results) > 0:
                latest = js_results[0]  # İlk sonuç
                print(f"\n🎯 {ticker} Ex-Dividend Bilgileri (JavaScript):")
                print(f"   📅 Son Ex-Date: {latest['exDate']}")
                print(f"   💰 Amount: {latest['amount']}")
                
                return {
                    'ticker': ticker,
                    'last_ex_date': latest['exDate'],
                    'amount': latest['amount'],
                    'success': True,
                    'method': 'javascript'
                }
            else:
                print("   ❌ JavaScript ile veri çekilemedi")
                
        except Exception as e:
            print(f"   ❌ JavaScript hatası: {str(e)}")
        
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
    print("🚀 Advanced MarketChameleon Scraper")
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
            print(f"   🔧 Kullanılan yöntem: {result['method']}")
        else:
            print(f"❌ {ticker} işlenemedi: {result.get('message', result.get('error', 'Bilinmeyen hata'))}")

if __name__ == "__main__":
    main()

























