#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AFGB Özel Test Scripti
AFGB için Div adj.price hesaplama sorununu analiz eder ve düzeltir
"""

import pandas as pd
import os
from datetime import datetime, timedelta
from cnbc_scraper import CNBCExDivScraper

class AFGBTester:
    def __init__(self):
        self.cnbc_scraper = None
        
    def setup_cnbc_scraper(self):
        """CNBC scraper'ını başlatır"""
        if not self.cnbc_scraper:
            self.cnbc_scraper = CNBCExDivScraper(headless=False)
        return self.cnbc_scraper
    
    def _convert_ticker_format(self, ticker):
        """Ticker formatını CNBC formatına çevirir"""
        try:
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
        converted_ticker = self._convert_ticker_format(ticker)
        scraper = self.setup_cnbc_scraper()
        ex_date = scraper.get_ex_dividend_date(converted_ticker)
        return ex_date
    
    def calculate_time_to_div(self, ex_div_date_str, current_date=None):
        """Ex-dividend date'den TIME TO DIV hesaplar - MOD CİNSİNDEN"""
        if not ex_div_date_str or pd.isna(ex_div_date_str):
            return None
            
        try:
            if '/' in str(ex_div_date_str):
                parts = str(ex_div_date_str).split('/')
                if len(parts) == 3:
                    month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
                    ex_div_date = datetime(year, month, day)
                    
                    if current_date is None:
                        current_date = datetime.now()
                    
                    days_diff = (ex_div_date - current_date).days
                    
                    # 90'lık MOD cinsinden TIME TO DIV hesapla
                    if days_diff <= 0:
                        time_to_div = 90 + days_diff
                    else:
                        time_to_div = days_diff
                    
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
    
    def calculate_div_adj_price_original(self, last_price, time_to_div, div_amount):
        """Orijinal Div adj.price hesaplama formülü"""
        if pd.isna(last_price) or pd.isna(time_to_div) or pd.isna(div_amount):
            return None
            
        try:
            # Orijinal formül: Div adj.price = Last price - (((90-Time to Div)/90)*DIV AMOUNT)
            div_adj_price = last_price - (((90 - time_to_div) / 90) * div_amount)
            
            print(f"      📊 ORİJİNAL Div adj.price hesaplama:")
            print(f"      📊 Last Price: {last_price}")
            print(f"      📊 TIME TO DIV: {time_to_div}")
            print(f"      📊 DIV AMOUNT: {div_amount}")
            print(f"      📊 Formül: {last_price} - (((90-{time_to_div})/90) * {div_amount})")
            print(f"      📊 Sonuç: {div_adj_price}")
            
            return round(div_adj_price, 2)
        except Exception as e:
            print(f"      ❌ Div adj.price hesaplama hatası: {str(e)}")
            return None
    
    def calculate_div_adj_price_corrected(self, last_price, time_to_div, div_amount):
        """Düzeltilmiş Div adj.price hesaplama formülü"""
        if pd.isna(last_price) or pd.isna(time_to_div) or pd.isna(div_amount):
            return None
            
        try:
            # Düzeltilmiş formül: Div adj.price = Last price - ((time_to_div/90)*DIV AMOUNT)
            # TIME TO DIV ne kadar büyükse, o kadar az düşülür
            div_adj_price = last_price - ((time_to_div / 90) * div_amount)
            
            print(f"      📊 DÜZELTİLMİŞ Div adj.price hesaplama:")
            print(f"      📊 Last Price: {last_price}")
            print(f"      📊 TIME TO DIV: {time_to_div}")
            print(f"      📊 DIV AMOUNT: {div_amount}")
            print(f"      📊 Formül: {last_price} - (({time_to_div}/90) * {div_amount})")
            print(f"      📊 Sonuç: {div_adj_price}")
            
            return round(div_adj_price, 2)
        except Exception as e:
            print(f"      ❌ Div adj.price hesaplama hatası: {str(e)}")
            return None
    
    def test_afgb_calculation(self):
        """AFGB için hesaplama testi yapar"""
        print("🔍 AFGB Div adj.price Hesaplama Testi")
        print("=" * 50)
        
        # AFGB verilerini bul
        afgb_data = None
        csv_files = ['janalldata.csv', 'ekheldff.csv', 'sekheldff.csv']
        
        for csv_file in csv_files:
            if os.path.exists(csv_file):
                print(f"📁 {csv_file} dosyası kontrol ediliyor...")
                df = pd.read_csv(csv_file)
                
                if 'PREF IBKR' in df.columns:
                    afgb_row = df[df['PREF IBKR'] == 'AFGB']
                    if not afgb_row.empty:
                        afgb_data = afgb_row.iloc[0]
                        print(f"✅ AFGB verisi {csv_file} dosyasında bulundu!")
                        break
        
        if afgb_data is None:
            print("❌ AFGB verisi hiçbir dosyada bulunamadı!")
            return
        
        # Mevcut verileri göster
        print(f"\n📊 AFGB Mevcut Veriler:")
        print(f"   PREF IBKR: {afgb_data.get('PREF IBKR', 'N/A')}")
        print(f"   Last Price: {afgb_data.get('Last Price', 'N/A')}")
        print(f"   DIV AMOUNT: {afgb_data.get('DIV AMOUNT', 'N/A')}")
        print(f"   EX-DIV DATE: {afgb_data.get('EX-DIV DATE', 'N/A')}")
        print(f"   TIME TO DIV: {afgb_data.get('TIME TO DIV', 'N/A')}")
        print(f"   Div adj.price (mevcut): {afgb_data.get('Div adj.price', 'N/A')}")
        
        # CNBC'den güncel ex-dividend date çek
        print(f"\n🌐 CNBC'den güncel ex-dividend date çekiliyor...")
        new_ex_div_date = self.get_ex_dividend_date_from_cnbc('AFGB')
        
        if new_ex_div_date:
            print(f"✅ CNBC'den ex-dividend date: {new_ex_div_date}")
            
            # TIME TO DIV hesapla
            time_to_div = self.calculate_time_to_div(new_ex_div_date)
            
            if time_to_div is not None:
                print(f"\n🧮 Hesaplama Karşılaştırması:")
                print(f"{'='*60}")
                
                last_price = afgb_data.get('Last Price')
                div_amount = afgb_data.get('DIV AMOUNT')
                
                if pd.notna(last_price) and pd.notna(div_amount):
                    # Orijinal formül
                    original_result = self.calculate_div_adj_price_original(last_price, time_to_div, div_amount)
                    
                    # Düzeltilmiş formül
                    corrected_result = self.calculate_div_adj_price_corrected(last_price, time_to_div, div_amount)
                    
                    print(f"\n📊 SONUÇ KARŞILAŞTIRMASI:")
                    print(f"   Hedeflenen Div adj.price: ~22.90")
                    print(f"   Orijinal formül sonucu: {original_result}")
                    print(f"   Düzeltilmiş formül sonucu: {corrected_result}")
                    print(f"   Mevcut Div adj.price: {afgb_data.get('Div adj.price', 'N/A')}")
                    
                    # Hangi formül daha doğru?
                    target_price = 22.90
                    if original_result:
                        original_diff = abs(original_result - target_price)
                        print(f"   Orijinal formül farkı: {original_diff:.2f}")
                    
                    if corrected_result:
                        corrected_diff = abs(corrected_result - target_price)
                        print(f"   Düzeltilmiş formül farkı: {corrected_diff:.2f}")
                        
                        if corrected_diff < original_diff:
                            print(f"   ✅ Düzeltilmiş formül daha doğru!")
                        else:
                            print(f"   ⚠️ Orijinal formül daha doğru olabilir")
                else:
                    print(f"❌ Last Price veya DIV AMOUNT eksik!")
            else:
                print(f"❌ TIME TO DIV hesaplanamadı!")
        else:
            print(f"❌ CNBC'den ex-dividend date çekilemedi!")
    
    def close(self):
        """Scraper'ı kapat"""
        if self.cnbc_scraper:
            try:
                self.cnbc_scraper.close()
            except:
                pass

def main():
    """Ana fonksiyon"""
    print("🚀 AFGB Özel Test Scripti")
    print("=" * 40)
    
    tester = AFGBTester()
    try:
        tester.test_afgb_calculation()
    finally:
        tester.close()
    
    print("\n🎯 Test tamamlandı!")

if __name__ == "__main__":
    main()
