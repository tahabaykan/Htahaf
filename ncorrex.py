#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NCorrEx - CSV Ex-Dividend Date Düzeltici (CNBC)
sek ile başlayan CSV dosyalarında TIME TO DIV değerlerini kontrol eder
ve CNBC'den ex-div date bilgilerini çekerek düzeltir
AYRICA: Güncel EX-DIV DATE bilgilerini kaynak ek* dosyalarına da yazar
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
from cnbc_scraper import CNBCExDivScraper

# sek/ekheld dosyalarından kaynak ek* dosyalarına eşleme
# Bu mapping nibkrtry.py'deki girdi dosyalarına göre oluşturuldu
SEK_TO_EK_MAPPING = {
    'sekheldcilizyeniyedi.csv': 'ekheldcilizyeniyedi.csv',
    'sekheldcommonsuz.csv': 'ekheldcommonsuz.csv',
    'sekhelddeznff.csv': 'ekhelddeznff.csv',
    'sekheldff.csv': 'ekheldff.csv',
    'sekheldflr.csv': 'ekheldflr.csv',
    'sekheldgarabetaltiyedi.csv': 'ekheldgarabetaltiyedi.csv',
    'sekheldkuponlu.csv': 'ekheldkuponlu.csv',
    'sekheldkuponlukreciliz.csv': 'ekheldkuponlukreciliz.csv',
    'sekheldkuponlukreorta.csv': 'ekheldkuponlukreorta.csv',
    'sekheldnff.csv': 'ekheldnff.csv',
    'sekheldotelremorta.csv': 'ekheldotelremorta.csv',
    'sekheldsolidbig.csv': 'ekheldsolidbig.csv',
    'sekheldtitrekhc.csv': 'ekheldtitrekhc.csv',
    'sekhighmatur.csv': 'ekhighmatur.csv',
    'seknotbesmaturlu.csv': 'eknotbesmaturlu.csv',
    'seknotcefilliquid.csv': 'eknotcefilliquid.csv',
    'seknottitrekhc.csv': 'eknottitrekhc.csv',
    'sekrumoreddanger.csv': 'ekrumoreddanger.csv',
    'seksalakilliquid.csv': 'eksalakilliquid.csv',
    'sekshitremhc.csv': 'ekshitremhc.csv',
    # ekheld dosyaları zaten kaynak dosya
    'ekheldcilizyeniyedi.csv': 'ekheldcilizyeniyedi.csv',
    'ekheldcommonsuz.csv': 'ekheldcommonsuz.csv',
    'ekhelddeznff.csv': 'ekhelddeznff.csv',
    'ekheldff.csv': 'ekheldff.csv',
    'ekheldflr.csv': 'ekheldflr.csv',
    'ekheldgarabetaltiyedi.csv': 'ekheldgarabetaltiyedi.csv',
    'ekheldkuponlu.csv': 'ekheldkuponlu.csv',
    'ekheldkuponlukreciliz.csv': 'ekheldkuponlukreciliz.csv',
    'ekheldkuponlukreorta.csv': 'ekheldkuponlukreorta.csv',
    'ekheldnff.csv': 'ekheldnff.csv',
    'ekheldotelremorta.csv': 'ekheldotelremorta.csv',
    'ekheldsolidbig.csv': 'ekheldsolidbig.csv',
    'ekheldtitrekhc.csv': 'ekheldtitrekhc.csv',
    'ekhighmatur.csv': 'ekhighmatur.csv',
    'eknotbesmaturlu.csv': 'eknotbesmaturlu.csv',
    'eknotcefilliquid.csv': 'eknotcefilliquid.csv',
    'eknottitrekhc.csv': 'eknottitrekhc.csv',
    'ekrumoreddanger.csv': 'ekrumoreddanger.csv',
    'eksalakilliquid.csv': 'eksalakilliquid.csv',
    'ekshitremhc.csv': 'ekshitremhc.csv',
    # Eksik olanlar için besmaturlu
    'sekheldbesmaturlu.csv': 'ekheldbesmaturlu.csv',
    'ekheldbesmaturlu.csv': 'ekheldbesmaturlu.csv',
}

class ExDivDateCorrector:
    def __init__(self, headless=True):
        self.headless = headless
        self.driver = None
        self.corrected_count = 0
        self.total_checked = 0
        self.cnbc_scraper = None
        
    def get_source_ek_file(self, csv_file):
        """
        Verilen sek/ekheld dosyası için kaynak ek* dosyasını döndürür
        Bu dosya nibkrtry.py'nin girdi olarak kullandığı dosyadır
        """
        basename = os.path.basename(csv_file)
        
        # Önce mapping'de ara
        if basename in SEK_TO_EK_MAPPING:
            return SEK_TO_EK_MAPPING[basename]
        
        # Mapping'de yoksa, 's' prefix'ini kaldırarak dene
        if basename.startswith('sek'):
            # sekheldff.csv → ekheldff.csv
            return 'ek' + basename[3:]
        
        # Zaten ek* dosyası ise kendisini döndür
        if basename.startswith('ek'):
            return basename
        
        return None
    
    def update_source_ek_file(self, csv_file, ticker, new_ex_div_date):
        """
        Kaynak ek* dosyasında ilgili hissenin EX-DIV DATE'ini günceller
        Bu sayede nibkrtry.py bir sonraki çalıştırıldığında güncel tarih kullanılır
        """
        try:
            # Kaynak dosyayı bul
            source_file = self.get_source_ek_file(csv_file)
            if not source_file:
                print(f"   ⚠️ {csv_file} için kaynak ek* dosyası bulunamadı")
                return False
            
            # Kaynak dosya mevcut mu kontrol et
            if not os.path.exists(source_file):
                print(f"   ⚠️ Kaynak dosya mevcut değil: {source_file}")
                return False
            
            # Kaynak dosyayı oku
            source_df = pd.read_csv(source_file)
            
            # EX-DIV DATE kolonu var mı kontrol et
            if 'EX-DIV DATE' not in source_df.columns:
                print(f"   ⚠️ {source_file} dosyasında EX-DIV DATE kolonu yok")
                return False
            
            # PREF IBKR kolonu var mı kontrol et
            if 'PREF IBKR' not in source_df.columns:
                print(f"   ⚠️ {source_file} dosyasında PREF IBKR kolonu yok")
                return False
            
            # Ticker'ı bul ve güncelle
            ticker_mask = source_df['PREF IBKR'] == ticker
            if not ticker_mask.any():
                print(f"   ⚠️ {ticker} ticker'ı {source_file} dosyasında bulunamadı")
                return False
            
            # Mevcut tarihi al
            old_date = source_df.loc[ticker_mask, 'EX-DIV DATE'].iloc[0]
            
            # Tarihi güncelle
            source_df.loc[ticker_mask, 'EX-DIV DATE'] = new_ex_div_date
            
            # Dosyayı kaydet
            source_df.to_csv(source_file, index=False, encoding='utf-8')
            
            print(f"   ✅ KAYNAK DOSYA GÜNCELLENDİ: {source_file}")
            print(f"      {ticker}: {old_date} → {new_ex_div_date}")
            
            return True
            
        except Exception as e:
            print(f"   ❌ Kaynak dosya güncelleme hatası: {str(e)}")
            return False
    
    def setup_driver(self):
        """Chrome driver'ı hazırlar - Gelişmiş Anti-Detection"""
        options = Options()
        
        # Headless modu kapat (bot tespit edilir)
        # if self.headless:
        #     options.add_argument('--headless')
        
        # Temel ayarlar
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--start-maximized')
        
        # Gelişmiş anti-detection
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_experimental_option("detach", True)
        
        # Ek anti-detection
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-plugins')
        options.add_argument('--disable-images')  # Hızlı yükleme için
        
        # User-Agent rotasyonu
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0'
        ]
        
        selected_ua = random.choice(user_agents)
        options.add_argument(f'--user-agent={selected_ua}')
        
        # Driver'ı başlat
        self.driver = webdriver.Chrome(options=options)
        
        # Gelişmiş JavaScript injection
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
        self.driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")
        
        # Ek stealth
        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });
                window.chrome = {
                    runtime: {},
                };
            '''
        })
        
        return self.driver
    
    def setup_cnbc_scraper(self):
        """CNBC scraper'ını başlatır"""
        if not self.cnbc_scraper:
            self.cnbc_scraper = CNBCExDivScraper(headless=self.headless)
        return self.cnbc_scraper
    
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
    
    def get_ex_dividend_date_from_cnbc(self, ticker, max_retries=3):
        """CNBC'den ex-dividend date bilgisini çeker"""
        # Ticker formatını çevir
        converted_ticker = self._convert_ticker_format(ticker)
        
        # CNBC scraper'ı başlat
        scraper = self.setup_cnbc_scraper()
        
        # Ex-dividend date'i çek
        ex_date = scraper.get_ex_dividend_date(converted_ticker)
        
        return ex_date
    
    def calculate_time_to_div(self, ex_div_date_str, current_date=None):
        """Ex-dividend date'den TIME TO DIV hesaplar - MOD CİNSİNDEN DÜZELTİLDİ"""
        if not ex_div_date_str or pd.isna(ex_div_date_str):
            return None
            
        try:
            # Ex-div date'i parse et
            if '/' in str(ex_div_date_str):
                parts = str(ex_div_date_str).split('/')
                if len(parts) == 3:
                    month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
                    ex_div_date = datetime(year, month, day)
                    
                    # Bugünün tarihi
                    if current_date is None:
                        current_date = datetime.now()
                    
                    # Gün farkını hesapla
                    days_diff = (ex_div_date - current_date).days
                    
                    # TIME TO DIV mantığı: 90 günlük döngülerle bir sonraki temettüye kaç gün kaldığını bul
                    # Ex-div date geçmişse, 90'ar gün ekleyerek bir sonrakini bul
                    
                    # 90 günlük döngülerle bir sonraki ex-div tarihini bul
                    next_div_date = ex_div_date
                    while next_div_date <= current_date:
                        next_div_date += timedelta(days=90)
                    
                    # Bir sonraki temettüye kaç gün kaldı
                    time_to_div = (next_div_date - current_date).days
                    
                    # 90'lık mod sistemi ile normalize et (0 yerine 90 yap)
                    time_to_div = time_to_div % 90
                    if time_to_div == 0:
                        time_to_div = 90
                    
                    print(f"      📊 TIME TO DIV hesaplama:")
                    print(f"      📊 Ex-Div Date: {ex_div_date_str}")
                    print(f"      📊 Bugün: {current_date.strftime('%m/%d/%Y')}")
                    print(f"      📊 Gün farkı: {days_diff}")
                    print(f"      📊 TIME TO DIV (90'lık MOD): {time_to_div}")
                    
                    return time_to_div
        except Exception as e:
            print(f"      ❌ TIME TO DIV hesaplama hatası: {str(e)}")
            pass
        
        return None
    
    def calculate_div_adj_price(self, last_price, time_to_div, div_amount):
        """Div adj.price hesaplar"""
        if pd.isna(last_price) or pd.isna(time_to_div) or pd.isna(div_amount):
            return None
            
        try:
            # Div adj.price = Last price - (((90-Time to Div)/90)*DIV AMOUNT)
            div_adj_price = last_price - (((90 - time_to_div) / 90) * div_amount)
            
            # Debug bilgisi
            print(f"      📊 Div adj.price hesaplama:")
            print(f"      📊 Last Price: {last_price}")
            print(f"      📊 TIME TO DIV: {time_to_div}")
            print(f"      📊 DIV AMOUNT: {div_amount}")
            print(f"      📊 Formül: {last_price} - (((90-{time_to_div})/90) * {div_amount})")
            print(f"      📊 Sonuç: {div_adj_price}")
            
            return round(div_adj_price, 2)
        except Exception as e:
            print(f"      ❌ Div adj.price hesaplama hatası: {str(e)}")
            return None
    
    def recalculate_technical_indicators(self, df, idx, last_price, div_adj_price):
        """Teknik göstergeleri yeniden hesaplar (SMA CHG, High, Low)"""
        try:
            # SMA değerlerini al
            sma20 = pd.to_numeric(df.at[idx, 'SMA20'], errors='coerce')
            sma63 = pd.to_numeric(df.at[idx, 'SMA63'], errors='coerce')
            sma246 = pd.to_numeric(df.at[idx, 'SMA246'], errors='coerce')
            
            if pd.notna(sma20) and pd.notna(div_adj_price):
                # SMA20 CHG hesapla
                sma20_chg = ((div_adj_price - sma20) / sma20) * 100
                df.at[idx, 'SMA20 chg'] = f"{sma20_chg:.2f}"
                print(f"   ✅ Yeni SMA20 CHG: {sma20_chg:.2f}%")
            
            if pd.notna(sma63) and pd.notna(div_adj_price):
                # SMA63 CHG hesapla
                sma63_chg = ((div_adj_price - sma63) / sma63) * 100
                df.at[idx, 'SMA63 chg'] = f"{sma63_chg:.2f}"
                print(f"   ✅ Yeni SMA63 CHG: {sma63_chg:.2f}%")
            
            if pd.notna(sma246) and pd.notna(div_adj_price):
                # SMA246 CHG hesapla
                sma246_chg = ((div_adj_price - sma246) / sma246) * 100
                df.at[idx, 'SMA246 chg'] = f"{sma246_chg:.2f}"
                print(f"   ✅ Yeni SMA246 CHG: {sma246_chg:.2f}%")
            
            # High/Low değerlerini güncelle (eğer mevcutsa)
            if '3M High' in df.columns and '3M Low' in df.columns:
                # 3M High/Low - div adj.price ile karşılaştır
                three_month_high = pd.to_numeric(df.at[idx, '3M High'], errors='coerce')
                three_month_low = pd.to_numeric(df.at[idx, '3M Low'], errors='coerce')
                
                if pd.notna(three_month_high) and div_adj_price > three_month_high:
                    df.at[idx, '3M High'] = f"{div_adj_price:.2f}"
                    print(f"   ✅ 3M High güncellendi: {div_adj_price:.2f}")
                
                if pd.notna(three_month_low) and div_adj_price < three_month_low:
                    df.at[idx, '3M Low'] = f"{div_adj_price:.2f}"
                    print(f"   ✅ 3M Low güncellendi: {div_adj_price:.2f}")
            
            if '6M High' in df.columns and '6M Low' in df.columns:
                # 6M High/Low - div adj.price ile karşılaştır
                six_month_high = pd.to_numeric(df.at[idx, '6M High'], errors='coerce')
                six_month_low = pd.to_numeric(df.at[idx, '6M Low'], errors='coerce')
                
                if pd.notna(six_month_high) and div_adj_price > six_month_high:
                    df.at[idx, '6M High'] = f"{div_adj_price:.2f}"
                    print(f"   ✅ 6M High güncellendi: {div_adj_price:.2f}")
                
                if pd.notna(six_month_low) and div_adj_price < six_month_low:
                    df.at[idx, '6M Low'] = f"{div_adj_price:.2f}"
                    print(f"   ✅ 6M Low güncellendi: {div_adj_price:.2f}")
            
            if '1Y High' in df.columns and '1Y Low' in df.columns:
                # 1Y High/Low - div adj.price ile karşılaştır
                year_high = pd.to_numeric(df.at[idx, '1Y High'], errors='coerce')
                year_low = pd.to_numeric(df.at[idx, '1Y Low'], errors='coerce')
                
                if pd.notna(year_high) and div_adj_price > year_high:
                    df.at[idx, '1Y High'] = f"{div_adj_price:.2f}"
                    print(f"   ✅ 1Y High güncellendi: {div_adj_price:.2f}")
                
                if pd.notna(year_low) and div_adj_price < year_low:
                    df.at[idx, '1Y Low'] = f"{div_adj_price:.2f}"
                    print(f"   ✅ 1Y Low güncellendi: {div_adj_price:.2f}")
            
            return True
            
        except Exception as e:
            print(f"   ❌ Teknik gösterge hesaplama hatası: {str(e)}")
            return False
    
    def process_csv_file(self, csv_file):
        """Tek bir CSV dosyasını işler"""
        print(f"\n{'='*80}")
        print(f"📁 İŞLENİYOR: {csv_file}")
        print(f"{'='*80}")
        
        try:
            # CSV'yi oku
            df = pd.read_csv(csv_file)
            original_rows = len(df)
            
            print(f"📊 Toplam satır: {original_rows}")
            
            # TIME TO DIV kolonunu kontrol et
            if 'TIME TO DIV' not in df.columns:
                print(f"❌ {csv_file} dosyasında 'TIME TO DIV' kolonu bulunamadı!")
                return False
            
            # TIME TO DIV değerlerini numeric yap
            df['TIME TO DIV'] = pd.to_numeric(df['TIME TO DIV'], errors='coerce')
            
            # Kontrol edilecek TIME TO DIV değerleri
            # 0-15 arası (temettü yeni ödendi) ve 75-90 arası (temettüye yakın)
            target_values = list(range(0, 16)) + list(range(75, 91))  # [0-15] + [75-90]
            
            # Bu değerlere sahip hisseleri bul
            target_mask = df['TIME TO DIV'].isin(target_values)
            target_stocks = df[target_mask]
            
            if len(target_stocks) == 0:
                print(f"✅ {csv_file} dosyasında kontrol edilecek TIME TO DIV değeri bulunamadı.")
                return True
            
            print(f"🎯 Kontrol edilecek hisse sayısı: {len(target_stocks)}")
            
            # Her hisse için ex-dividend date kontrol et
            corrections_made = 0
            technical_updates_made = 0
             
            for idx, row in target_stocks.iterrows():
                ticker = row['PREF IBKR']
                current_time_to_div = row['TIME TO DIV']
                current_ex_div_date = row['EX-DIV DATE']
                
                print(f"\n🔍 {ticker} kontrol ediliyor...")
                print(f"   Mevcut TIME TO DIV: {current_time_to_div}")
                print(f"   Mevcut EX-DIV DATE: {current_ex_div_date}")
                
                # CNBC'den ex-dividend date çek
                new_ex_div_date = self.get_ex_dividend_date_from_cnbc(ticker)
                
                # TIME TO DIV ve Div adj.price için kullanılacak değerler
                final_time_to_div = current_time_to_div
                final_div_adj_price = row.get('Div adj.price', row['Last Price'])
                
                if new_ex_div_date and new_ex_div_date != current_ex_div_date:
                    print(f"   ✅ Yeni EX-DIV DATE: {new_ex_div_date}")
                    
                    # EX-DIV DATE'i güncelle (mevcut dosyada)
                    df.at[idx, 'EX-DIV DATE'] = new_ex_div_date
                    
                    # KAYNAK EK* DOSYASINI DA GÜNCELLE
                    # Bu sayede nibkrtry.py bir sonraki çalıştırıldığında güncel tarih kullanılır
                    self.update_source_ek_file(csv_file, ticker, new_ex_div_date)
                    
                    # TIME TO DIV'i yeniden hesapla
                    new_time_to_div = self.calculate_time_to_div(new_ex_div_date)
                    
                    if new_time_to_div is not None:
                        print(f"   ✅ Yeni TIME TO DIV: {new_time_to_div}")
                        df.at[idx, 'TIME TO DIV'] = new_time_to_div
                        final_time_to_div = new_time_to_div
                        
                        # Div adj.price'i yeniden hesapla
                        last_price = row['Last Price']
                        div_amount = row['DIV AMOUNT']
                        
                        if not pd.isna(last_price) and not pd.isna(div_amount):
                            new_div_adj_price = self.calculate_div_adj_price(last_price, new_time_to_div, div_amount)
                            
                            if new_div_adj_price is not None:
                                print(f"   ✅ Yeni Div adj.price: {new_div_adj_price}")
                                df.at[idx, 'Div adj.price'] = new_div_adj_price
                                final_div_adj_price = new_div_adj_price
                            else:
                                # Div adj.price hesaplanamadıysa mevcut değeri kullan
                                final_div_adj_price = row.get('Div adj.price', last_price)
                                print(f"   ⚠️ Div adj.price hesaplanamadı, mevcut değer kullanılıyor: {final_div_adj_price}")
                        else:
                            # Last Price veya DIV AMOUNT yoksa mevcut div adj.price'i kullan
                            final_div_adj_price = row.get('Div adj.price', last_price)
                            print(f"   ⚠️ Last Price veya DIV AMOUNT eksik, mevcut div adj.price kullanılıyor: {final_div_adj_price}")
                        
                        corrections_made += 1
                        self.corrected_count += 1
                    else:
                        print(f"   ❌ TIME TO DIV hesaplanamadı")
                else:
                    print(f"   ⚠️ EX-DIV DATE değişmedi, mevcut değerler kullanılıyor")
                
                # TIME TO DIV aramasına giren TÜM hisselerde TIME TO DIV ve Div adj.price yeniden hesapla
                print(f"   🔄 TIME TO DIV aramasına girdi, TIME TO DIV ve Div adj.price yeniden hesaplanıyor...")
                
                # Mevcut EX-DIV DATE'den TIME TO DIV'i yeniden hesapla
                current_ex_div_date = row['EX-DIV DATE']
                if pd.notna(current_ex_div_date) and current_ex_div_date != '':
                    recalculated_time_to_div = self.calculate_time_to_div(current_ex_div_date)
                    if recalculated_time_to_div is not None:
                        old_time_to_div = row['TIME TO DIV']
                        df.at[idx, 'TIME TO DIV'] = recalculated_time_to_div
                        if old_time_to_div != recalculated_time_to_div:
                            print(f"   ✅ TIME TO DIV yeniden hesaplandı: {old_time_to_div} → {recalculated_time_to_div}")
                            final_time_to_div = recalculated_time_to_div
                        else:
                            print(f"   ✅ TIME TO DIV aynı kaldı: {recalculated_time_to_div}")
                        
                        # Div adj.price'i HER ZAMAN yeniden hesapla (TIME TO DIV aynı olsa bile!)
                        last_price = row['Last Price']
                        div_amount = row['DIV AMOUNT']
                        
                        if not pd.isna(last_price) and not pd.isna(div_amount):
                            new_div_adj_price = self.calculate_div_adj_price(last_price, recalculated_time_to_div, div_amount)
                            
                            if new_div_adj_price is not None:
                                print(f"   ✅ Div adj.price yeniden hesaplandı: {new_div_adj_price}")
                                df.at[idx, 'Div adj.price'] = new_div_adj_price
                                final_div_adj_price = new_div_adj_price
                            else:
                                print(f"   ⚠️ Div adj.price hesaplanamadı")
                        else:
                            print(f"   ⚠️ Last Price veya DIV AMOUNT eksik")
                    else:
                        print(f"   ❌ TIME TO DIV hesaplanamadı")
                
                # Teknik göstergeleri yeni Div adj.price ile yeniden hesapla
                print(f"   🔄 Teknik göstergeler yeni Div adj.price ile yeniden hesaplanıyor...")
                last_price = row['Last Price']
                technical_updated = self.recalculate_technical_indicators(df, idx, last_price, final_div_adj_price)
                
                if technical_updated:
                    technical_updates_made += 1
                
                # Ticker'lar arası gecikme
                time.sleep(random.uniform(3, 6))
            
            # Düzeltmeler veya teknik güncellemeler yapıldıysa CSV'yi kaydet
            if corrections_made > 0 or technical_updates_made > 0:
                print(f"\n💾 {corrections_made} düzeltme + {technical_updates_made} teknik güncelleme yapıldı, CSV kaydediliyor...")
                df.to_csv(csv_file, index=False, encoding='utf-8')
                print(f"✅ {csv_file} güncellendi!")
            else:
                print(f"\n✅ {csv_file} için düzeltme gerekmiyor.")
            
            self.total_checked += len(target_stocks)
            return True
            
        except Exception as e:
            print(f"❌ {csv_file} işlenirken hata: {str(e)}")
            return False
    
    def process_all_csv_files(self):
        """Tüm CSV dosyalarını işler (sek ve ekheld)"""
        print("🚀 NCorrEx - CSV Ex-Dividend Date Düzeltici (CNBC)")
        print("=" * 60)
        
        # İşlenecek CSV dosyalarını tanımla
        target_files = [
            # sek ile başlayan dosyalar
            'sekheldcilizyeniyedi.csv',
            'sekheldcommonsuz.csv',
            'sekhelddeznff.csv',
            'sekheldff.csv',
            'sekheldflr.csv',
            'sekheldgarabetaltiyedi.csv',
            'sekheldkuponlu.csv',
            'sekheldkuponlukreciliz.csv',
            'sekheldkuponlukreorta.csv',
            'sekheldnff.csv',
            'sekheldotelremorta.csv',
            'sekheldsolidbig.csv',
            'sekheldtitrekhc.csv',
            'sekhighmatur.csv',
            'seknotbesmaturlu.csv',
            'seknotcefilliquid.csv',
            'seknottitrekhc.csv',
            'sekrumoreddanger.csv',
            'seksalakilliquid.csv',
            'sekshitremhc.csv',
            'sekhelddeznff.csv',
            
            # ekheld ile başlayan dosyalar
            'ekheldcilizyeniyedi.csv',
            'ekheldcommonsuz.csv',
            'ekhelddeznff.csv',
            'ekheldff.csv',
            'ekheldflr.csv',
            'ekheldgarabetaltiyedi.csv',
            'ekheldkuponlu.csv',
            'ekheldkuponlukreciliz.csv',
            'ekheldkuponlukreorta.csv',
            'ekheldnff.csv',
            'ekheldotelremorta.csv',
            'ekheldsolidbig.csv',
            'ekheldtitrekhc.csv',
            'ekhighmatur.csv',
            'eknotbesmaturlu.csv',
            'eknotcefilliquid.csv',
            'eknottitrekhc.csv',
            'ekrumoreddanger.csv',
            'eksalakilliquid.csv',
            'ekshitremhc.csv'
        ]
        
        # Mevcut dosyaları bul
        existing_files = []
        for target_file in target_files:
            if os.path.exists(target_file):
                existing_files.append(target_file)
            else:
                print(f"⚠️ {target_file} bulunamadı, atlanıyor...")
        
        if not existing_files:
            print("❌ Hiçbir hedef CSV dosyası bulunamadı!")
            return
        
        print(f"📁 İşlenecek CSV dosyaları: {len(existing_files)}")
        for file in existing_files:
            print(f"   - {file}")
        
        print(f"\n🎯 Kontrol edilecek TIME TO DIV değerleri: 0-15 ve 75-90 arası")
        
        # Her dosyayı işle
        success_count = 0
        for csv_file in existing_files:
            if self.process_csv_file(csv_file):
                success_count += 1
        
        # Özet
        print(f"\n{'='*80}")
        print(f"📊 İŞLEM ÖZETİ")
        print(f"{'='*80}")
        print(f"✅ Başarılı dosya: {success_count}/{len(existing_files)}")
        print(f"🔍 Kontrol edilen hisse: {self.total_checked}")
        print(f"✏️ Düzeltilen hisse: {self.corrected_count}")
        
        if self.corrected_count > 0:
            print(f"\n🎉 {self.corrected_count} hisse için ex-dividend date bilgileri düzeltildi!")
            print(f"   - EX-DIV DATE kolonları güncellendi")
            print(f"   - TIME TO DIV değerleri yeniden hesaplandı")
            print(f"   - Div adj.price değerleri güncellendi")
        else:
            print(f"\n✅ Hiçbir düzeltme gerekmiyor.")
    
    def close(self):
        """Driver'ı kapat"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        
        if self.cnbc_scraper:
            try:
                self.cnbc_scraper.close()
            except:
                pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

def synchronize_time_to_div_across_csvs(main_data_file='janalldata.csv'):
    """Tüm CSV dosyalarındaki TIME TO DIV değerlerini ana veri dosyası ile senkronize eder"""
    try:
        print("\n🔄 CSV dosyaları arasında TIME TO DIV senkronizasyonu yapılıyor...")
        
        # Ana veri dosyasını yükle
        if not os.path.exists(main_data_file):
            print(f"❌ Ana veri dosyası bulunamadı: {main_data_file}")
            return False
        
        main_df = pd.read_csv(main_data_file)
        print(f"✅ Ana veri dosyası yüklendi: {main_data_file} ({len(main_df)} satır)")
        
        # Gerekli kolonları kontrol et
        required_columns = ['PREF IBKR', 'TIME TO DIV', 'DIV AMOUNT']
        missing_columns = [col for col in required_columns if col not in main_df.columns]
        
        if missing_columns:
            print(f"❌ Ana veri dosyasında gerekli kolonlar bulunamadı: {missing_columns}")
            return False
        
        # Tüm CSV dosyalarını bul
        all_csv_files = glob.glob("*.csv")
        ssfinek_files = [f for f in all_csv_files if 'ssfinek' in f.lower() and not f.startswith('janek_')]
        sek_files = [f for f in all_csv_files if f.startswith('sek')]
        
        print(f"📁 {len(ssfinek_files)} SSFINEK dosyası bulundu")
        print(f"📁 {len(sek_files)} SEK dosyası bulundu")
        
        total_updated = 0
        
        # SSFINEK dosyalarını güncelle
        for csv_file in ssfinek_files:
            try:
                print(f"\n📋 {csv_file} güncelleniyor...")
                
                df = pd.read_csv(csv_file)
                
                if 'PREF IBKR' not in df.columns:
                    print(f"⚠️ {csv_file} dosyasında 'PREF IBKR' kolonu bulunamadı!")
                    continue
                
                # TIME TO DIV kolonu ekle (yoksa)
                if 'TIME TO DIV' not in df.columns:
                    df['TIME TO DIV'] = None
                    print(f"   ➕ TIME TO DIV kolonu eklendi")
                
                # DIV AMOUNT kolonu ekle (yoksa)
                if 'DIV AMOUNT' not in df.columns:
                    df['DIV AMOUNT'] = None
                    print(f"   ➕ DIV AMOUNT kolonu eklendi")
                
                updated_count = 0
                
                for idx, row in df.iterrows():
                    symbol = row['PREF IBKR']
                    
                    if pd.isna(symbol) or symbol == '':
                        continue
                    
                    # Ana veri dosyasında bu hisseyi bul
                    main_data_row = main_df[main_df['PREF IBKR'] == symbol]
                    
                    if not main_data_row.empty:
                        main_time_to_div = main_data_row.iloc[0]['TIME TO DIV']
                        main_div_amount = main_data_row.iloc[0]['DIV AMOUNT']
                        
                        # TIME TO DIV güncelle
                        if pd.notna(main_time_to_div):
                            current_time_to_div = df.at[idx, 'TIME TO DIV']
                            if current_time_to_div != main_time_to_div:
                                df.at[idx, 'TIME TO DIV'] = main_time_to_div
                                print(f"   ✅ {symbol}: TIME TO DIV {current_time_to_div} → {main_time_to_div}")
                                updated_count += 1
                        
                        # DIV AMOUNT güncelle
                        if pd.notna(main_div_amount):
                            current_div_amount = df.at[idx, 'DIV AMOUNT']
                            if current_div_amount != main_div_amount:
                                df.at[idx, 'DIV AMOUNT'] = main_div_amount
                                print(f"   ✅ {symbol}: DIV AMOUNT {current_div_amount} → {main_div_amount}")
                                updated_count += 1
                
                if updated_count > 0:
                    # CSV'yi kaydet
                    df.to_csv(csv_file, index=False, encoding='utf-8')
                    print(f"   💾 {updated_count} güncelleme yapıldı, {csv_file} kaydedildi")
                    total_updated += updated_count
                else:
                    print(f"   ✅ Güncelleme gerekmiyor")
                
            except Exception as e:
                print(f"❌ {csv_file} işlenirken hata: {e}")
                continue
        
        # SEK dosyalarını güncelle
        for csv_file in sek_files:
            try:
                print(f"\n📋 {csv_file} güncelleniyor...")
                
                df = pd.read_csv(csv_file)
                
                if 'PREF IBKR' not in df.columns:
                    print(f"⚠️ {csv_file} dosyasında 'PREF IBKR' kolonu bulunamadı!")
                    continue
                
                # TIME TO DIV kolonu ekle (yoksa)
                if 'TIME TO DIV' not in df.columns:
                    df['TIME TO DIV'] = None
                    print(f"   ➕ TIME TO DIV kolonu eklendi")
                
                # DIV AMOUNT kolonu ekle (yoksa)
                if 'DIV AMOUNT' not in df.columns:
                    df['DIV AMOUNT'] = None
                    print(f"   ➕ DIV AMOUNT kolonu eklendi")
                
                updated_count = 0
                
                for idx, row in df.iterrows():
                    symbol = row['PREF IBKR']
                    
                    if pd.isna(symbol) or symbol == '':
                        continue
                    
                    # Ana veri dosyasında bu hisseyi bul
                    main_data_row = main_df[main_df['PREF IBKR'] == symbol]
                    
                    if not main_data_row.empty:
                        main_time_to_div = main_data_row.iloc[0]['TIME TO DIV']
                        main_div_amount = main_data_row.iloc[0]['DIV AMOUNT']
                        
                        # TIME TO DIV güncelle
                        if pd.notna(main_time_to_div):
                            current_time_to_div = df.at[idx, 'TIME TO DIV']
                            if current_time_to_div != main_time_to_div:
                                df.at[idx, 'TIME TO DIV'] = main_time_to_div
                                print(f"   ✅ {symbol}: TIME TO DIV {current_time_to_div} → {main_time_to_div}")
                                updated_count += 1
                        
                        # DIV AMOUNT güncelle
                        if pd.notna(main_div_amount):
                            current_div_amount = df.at[idx, 'DIV AMOUNT']
                            if current_div_amount != main_div_amount:
                                df.at[idx, 'DIV AMOUNT'] = main_div_amount
                                print(f"   ✅ {symbol}: DIV AMOUNT {current_div_amount} → {main_div_amount}")
                                updated_count += 1
                
                if updated_count > 0:
                    # CSV'yi kaydet
                    df.to_csv(csv_file, index=False, encoding='utf-8')
                    print(f"   💾 {updated_count} güncelleme yapıldı, {csv_file} kaydedildi")
                    total_updated += updated_count
                else:
                    print(f"   ✅ Güncelleme gerekmiyor")
                
            except Exception as e:
                print(f"❌ {csv_file} işlenirken hata: {e}")
                continue
        
        print(f"\n✅ Senkronizasyon tamamlandı! Toplam {total_updated} güncelleme yapıldı")
        return True
        
    except Exception as e:
        print(f"❌ Senkronizasyon hatası: {e}")
        return False

def main():
    """Ana fonksiyon"""
    print("🚀 NCorrEx - CSV Ex-Dividend Date Düzeltici (CNBC)")
    print("=" * 60)
    
    # Önce CSV dosyaları arasında TIME TO DIV senkronizasyonu yap
    print("\n🔄 1. Adım: CSV dosyaları arasında TIME TO DIV senkronizasyonu...")
    sync_success = synchronize_time_to_div_across_csvs()
    
    if sync_success:
        print("✅ Senkronizasyon başarılı!")
    else:
        print("⚠️ Senkronizasyon sırasında sorun oluştu, devam ediliyor...")
    
    # Sonra ana işlemi yap
    print("\n🔄 2. Adım: Ex-dividend date düzeltmeleri...")
    with ExDivDateCorrector(headless=False) as corrector:  # headless=False ile tarayıcıyı görebilirsiniz
        corrector.process_all_csv_files()
    
    print("\n🎯 Tüm işlemler tamamlandı!")
    print("📊 TIME TO DIV değerleri tüm CSV dosyalarında senkronize edildi")
    print("🔍 Ex-dividend date'ler CNBC'den kontrol edildi ve düzeltildi")

if __name__ == "__main__":
    main()
