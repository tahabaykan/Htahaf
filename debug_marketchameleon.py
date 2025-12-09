#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Debug MarketChameleon Scraper
Detaylı debug bilgileri ile ex-dividend date çeker
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

def debug_marketchameleon():
    """MarketChameleon'dan debug bilgileri ile veri çeker"""
    ticker = "DCOMP"
    url = f"https://marketchameleon.com/Overview/{ticker}/Dividends/"
    
    # Chrome options
    options = Options()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    
    driver = None
    try:
        print(f"🔍 {ticker} için MarketChameleon debug ediliyor...")
        print(f"📱 URL: {url}")
        
        driver = webdriver.Chrome(options=options)
        driver.get(url)
        
        # Sayfanın yüklenmesini bekle
        print("⏳ Sayfa yükleniyor (30 saniye)...")
        time.sleep(30)
        
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
        tables = driver.find_elements("tag name", "table")
        print(f"✅ {len(tables)} tablo bulundu")
        
        # Her tabloyu detaylı kontrol et
        for i, table in enumerate(tables):
            try:
                print(f"\n📋 Tablo {i+1} detaylı kontrol:")
                
                # Tablo boyutunu al
                table_html = table.get_attribute('outerHTML')
                print(f"   📏 Tablo HTML boyutu: {len(table_html)} karakter")
                
                # Tablo başlığını bul
                headers = table.find_elements("tag name", "th")
                if headers:
                    header_texts = [h.text.strip() for h in headers]
                    print(f"   🏷️ Headers: {header_texts}")
                    
                    # Ex Date header'ı var mı kontrol et
                    if any("ex" in h.lower() and "date" in h.lower() for h in header_texts):
                        print(f"   ✅ Ex Date header bulundu!")
                        
                        # Tablo satırlarını al
                        rows = table.find_elements("tag name", "tr")
                        print(f"   📊 {len(rows)} satır bulundu")
                        
                        if len(rows) > 1:
                            # İlk data row'u al
                            first_data_row = rows[1]
                            cells = first_data_row.find_elements("tag name", "td")
                            
                            print(f"   📝 {len(cells)} hücre bulundu")
                            
                            if len(cells) >= 5:
                                ex_date = cells[0].text.strip()
                                amount = cells[4].text.strip()
                                
                                print(f"   📅 Ex-Date: '{ex_date}'")
                                print(f"   💰 Amount: '{amount}'")
                                
                                if ex_date and amount and ex_date != 'Ex Date':
                                    print(f"   ✅ Veri bulundu!")
                                else:
                                    print(f"   ❌ Veri eksik veya yanlış")
                            else:
                                print(f"   ❌ Yeterli hücre yok")
                        else:
                            print(f"   ❌ Data row yok")
                    else:
                        print(f"   ❌ Ex Date header bulunamadı")
                else:
                    print(f"   ❌ Header bulunamadı")
                    
            except Exception as e:
                print(f"   ❌ Tablo {i+1} hatası: {str(e)}")
                continue
        
        # JavaScript ile veri çek
        print("\n🔍 JavaScript ile veri çekme deneniyor...")
        
        js_script = """
        var tables = document.querySelectorAll('table');
        var results = [];
        
        console.log('Toplam tablo sayısı:', tables.length);
        
        for (var i = 0; i < tables.length; i++) {
            var table = tables[i];
            var rows = table.querySelectorAll('tr');
            
            console.log('Tablo', i, 'satır sayısı:', rows.length);
            
            for (var j = 1; j < rows.length; j++) {
                var row = rows[j];
                var cells = row.querySelectorAll('td');
                
                console.log('Satır', j, 'hücre sayısı:', cells.length);
                
                if (cells.length >= 5) {
                    var exDate = cells[0].textContent.trim();
                    var amount = cells[4].textContent.trim();
                    
                    console.log('Ex-Date:', exDate, 'Amount:', amount);
                    
                    if (exDate && amount && exDate !== 'Ex Date') {
                        results.push({
                            exDate: exDate,
                            amount: amount
                        });
                    }
                }
            }
        }
        
        console.log('Toplam sonuç:', results.length);
        return results;
        """
        
        js_results = driver.execute_script(js_script)
        
        if js_results and len(js_results) > 0:
            print(f"\n🎯 {ticker} Ex-Dividend Bilgileri:")
            print(f"   📅 Son Ex-Date: {js_results[0]['exDate']}")
            print(f"   💰 Amount: ${js_results[0]['amount']}")
            
            print(f"\n📊 Toplam {len(js_results)} dividend bulundu")
            
            # İlk 5'i göster
            print(f"\n📋 İlk 5 Dividend:")
            for i, div in enumerate(js_results[:5]):
                print(f"   {i+1}. {div['exDate']} | ${div['amount']}")
            
            return True
        else:
            print(f"❌ {ticker} için veri bulunamadı")
            print(f"   JavaScript sonucu: {js_results}")
            return False
            
    except Exception as e:
        print(f"❌ Hata: {str(e)}")
        return False
    
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    print("🚀 Debug MarketChameleon Scraper")
    print("=" * 50)
    
    success = debug_marketchameleon()
    
    if success:
        print("\n✅ Debug başarılı!")
    else:
        print("\n❌ Debug başarısız!")

























