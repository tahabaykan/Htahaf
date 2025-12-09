#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AFGB Özel Düzeltme Scripti
AFGB için ex-dividend date ve Div adj.price düzeltmesi yapar
"""

import pandas as pd
import os
from datetime import datetime, timedelta
from cnbc_scraper import CNBCExDivScraper

class AFGBFixer:
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
    
    def get_ex_dividend_date_from_cnbc(self, ticker):
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
    
    def calculate_div_adj_price(self, last_price, time_to_div, div_amount):
        """Div adj.price hesaplar - DOĞRU FORMÜL"""
        if pd.isna(last_price) or pd.isna(time_to_div) or pd.isna(div_amount):
            return None
            
        try:
            # DOĞRU FORMÜL: Div adj.price = Last price - (((90-Time to Div)/90)*DIV AMOUNT)
            div_adj_price = last_price - (((90 - time_to_div) / 90) * div_amount)
            
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
        """Teknik göstergeleri yeniden hesaplar"""
        try:
            # SMA değerlerini al
            sma20 = pd.to_numeric(df.at[idx, 'SMA20'], errors='coerce')
            sma63 = pd.to_numeric(df.at[idx, 'SMA63'], errors='coerce')
            sma246 = pd.to_numeric(df.at[idx, 'SMA246'], errors='coerce')
            
            if pd.notna(sma20) and pd.notna(div_adj_price):
                sma20_chg = ((div_adj_price - sma20) / sma20) * 100
                df.at[idx, 'SMA20 chg'] = f"{sma20_chg:.2f}"
                print(f"   ✅ Yeni SMA20 CHG: {sma20_chg:.2f}%")
            
            if pd.notna(sma63) and pd.notna(div_adj_price):
                sma63_chg = ((div_adj_price - sma63) / sma63) * 100
                df.at[idx, 'SMA63 chg'] = f"{sma63_chg:.2f}"
                print(f"   ✅ Yeni SMA63 CHG: {sma63_chg:.2f}%")
            
            if pd.notna(sma246) and pd.notna(div_adj_price):
                sma246_chg = ((div_adj_price - sma246) / sma246) * 100
                df.at[idx, 'SMA246 chg'] = f"{sma246_chg:.2f}"
                print(f"   ✅ Yeni SMA246 CHG: {sma246_chg:.2f}%")
            
            return True
            
        except Exception as e:
            print(f"   ❌ Teknik gösterge hesaplama hatası: {str(e)}")
            return False
    
    def fix_afgb_in_file(self, csv_file):
        """Belirtilen CSV dosyasında AFGB'yi düzeltir"""
        print(f"\n🔧 {csv_file} dosyasında AFGB düzeltiliyor...")
        
        try:
            # CSV'yi oku
            df = pd.read_csv(csv_file)
            
            # AFGB'yi bul
            afgb_mask = df['PREF IBKR'] == 'AFGB'
            afgb_indices = df[afgb_mask].index
            
            if len(afgb_indices) == 0:
                print(f"❌ {csv_file} dosyasında AFGB bulunamadı!")
                return False
            
            print(f"✅ {len(afgb_indices)} AFGB kaydı bulundu")
            
            # Her AFGB kaydını düzelt
            for idx in afgb_indices:
                row = df.iloc[idx]
                
                print(f"\n🔍 AFGB (Index {idx}) düzeltiliyor...")
                print(f"   Mevcut EX-DIV DATE: {row['EX-DIV DATE']}")
                print(f"   Mevcut TIME TO DIV: {row['TIME TO DIV']}")
                print(f"   Mevcut Div adj.price: {row['Div adj.price']}")
                
                # CNBC'den güncel ex-dividend date çek
                print(f"   🌐 CNBC'den güncel ex-dividend date çekiliyor...")
                new_ex_div_date = self.get_ex_dividend_date_from_cnbc('AFGB')
                
                if new_ex_div_date:
                    print(f"   ✅ CNBC'den ex-dividend date: {new_ex_div_date}")
                    
                    # EX-DIV DATE'i güncelle
                    df.at[idx, 'EX-DIV DATE'] = new_ex_div_date
                    
                    # TIME TO DIV'i yeniden hesapla
                    new_time_to_div = self.calculate_time_to_div(new_ex_div_date)
                    
                    if new_time_to_div is not None:
                        print(f"   ✅ Yeni TIME TO DIV: {new_time_to_div}")
                        df.at[idx, 'TIME TO DIV'] = new_time_to_div
                        
                        # Div adj.price'i yeniden hesapla
                        last_price = row['Last Price']
                        div_amount = row['DIV AMOUNT']
                        
                        if not pd.isna(last_price) and not pd.isna(div_amount):
                            new_div_adj_price = self.calculate_div_adj_price(last_price, new_time_to_div, div_amount)
                            
                            if new_div_adj_price is not None:
                                print(f"   ✅ Yeni Div adj.price: {new_div_adj_price}")
                                df.at[idx, 'Div adj.price'] = new_div_adj_price
                                
                                # Teknik göstergeleri yeniden hesapla
                                print(f"   🔄 Teknik göstergeler yeniden hesaplanıyor...")
                                self.recalculate_technical_indicators(df, idx, last_price, new_div_adj_price)
                            else:
                                print(f"   ❌ Div adj.price hesaplanamadı")
                        else:
                            print(f"   ❌ Last Price veya DIV AMOUNT eksik")
                    else:
                        print(f"   ❌ TIME TO DIV hesaplanamadı")
                else:
                    print(f"   ❌ CNBC'den ex-dividend date çekilemedi")
            
            # CSV'yi kaydet
            print(f"\n💾 {csv_file} kaydediliyor...")
            df.to_csv(csv_file, index=False, encoding='utf-8')
            print(f"✅ {csv_file} güncellendi!")
            
            return True
            
        except Exception as e:
            print(f"❌ {csv_file} işlenirken hata: {str(e)}")
            return False
    
    def fix_afgb_all_files(self):
        """Tüm CSV dosyalarında AFGB'yi düzeltir"""
        print("🚀 AFGB Özel Düzeltme Scripti")
        print("=" * 50)
        
        # İşlenecek dosyalar
        target_files = [
            'janalldata.csv',
            'ekheldff.csv',
            'sekheldff.csv'
        ]
        
        # Mevcut dosyaları bul
        existing_files = []
        for target_file in target_files:
            if os.path.exists(target_file):
                existing_files.append(target_file)
            else:
                print(f"⚠️ {target_file} bulunamadı, atlanıyor...")
        
        if not existing_files:
            print("❌ Hiçbir hedef dosya bulunamadı!")
            return
        
        print(f"📁 İşlenecek dosyalar: {len(existing_files)}")
        for file in existing_files:
            print(f"   - {file}")
        
        # Her dosyayı işle
        success_count = 0
        for csv_file in existing_files:
            if self.fix_afgb_in_file(csv_file):
                success_count += 1
        
        # Özet
        print(f"\n{'='*50}")
        print(f"📊 İŞLEM ÖZETİ")
        print(f"{'='*50}")
        print(f"✅ Başarılı dosya: {success_count}/{len(existing_files)}")
        print(f"🎯 AFGB düzeltmeleri tamamlandı!")
    
    def close(self):
        """Scraper'ı kapat"""
        if self.cnbc_scraper:
            try:
                self.cnbc_scraper.close()
            except:
                pass

def main():
    """Ana fonksiyon"""
    print("🚀 AFGB Özel Düzeltme Scripti")
    print("=" * 40)
    
    fixer = AFGBFixer()
    try:
        fixer.fix_afgb_all_files()
    finally:
        fixer.close()
    
    print("\n🎯 AFGB düzeltmeleri tamamlandı!")

if __name__ == "__main__":
    main()
