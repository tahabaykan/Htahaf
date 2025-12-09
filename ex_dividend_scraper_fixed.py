#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ex-Dividend Date Scraper - Rate Limiting Fixed
Herhangi bir ticker için güncel ex-dividend date bilgilerini çeker
Rate limiting sorunlarını çözer
"""

import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
import random
import json
import os

class ExDividendScraperFixed:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.request_count = 0
        self.last_request_time = 0
    
    def _rate_limit_delay(self):
        """Rate limiting için gecikme ekler"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        # Minimum 2 saniye gecikme
        if time_since_last < 2:
            sleep_time = 2 - time_since_last
            print(f"⏳ Rate limiting için {sleep_time:.1f} saniye bekleniyor...")
            time.sleep(sleep_time)
        
        # Rastgele ek gecikme (0.5 - 1.5 saniye)
        random_delay = random.uniform(0.5, 1.5)
        time.sleep(random_delay)
        
        self.last_request_time = time.time()
        self.request_count += 1
    
    def get_from_yahoo_finance(self, ticker, max_retries=3):
        """Yahoo Finance'dan ex-dividend date bilgisini çeker (retry ile)"""
        for attempt in range(max_retries):
            try:
                self._rate_limit_delay()
                print(f"Yahoo Finance'dan {ticker} için veri çekiliyor... (Deneme {attempt + 1}/{max_retries})")
                
                stock = yf.Ticker(ticker)
                dividends = stock.dividends
                
                if not dividends.empty:
                    # En son ex-dividend date
                    last_ex_div = dividends.index[-1]
                    # Bir sonraki ex-dividend date (genellikle 3 ay sonra)
                    next_ex_div = last_ex_div + pd.DateOffset(months=3)
                    
                    # Temettü geçmişi
                    dividend_history = dividends.tail(5).to_dict()
                    
                    return {
                        'source': 'Yahoo Finance',
                        'ticker': ticker,
                        'last_ex_dividend': last_ex_div.strftime('%Y-%m-%d'),
                        'next_ex_dividend': next_ex_div.strftime('%Y-%m-%d'),
                        'last_dividend_amount': dividends.iloc[-1],
                        'dividend_history': dividend_history,
                        'success': True
                    }
                else:
                    return {
                        'source': 'Yahoo Finance',
                        'ticker': ticker,
                        'success': False,
                        'message': 'Temettü bilgisi bulunamadı'
                    }
                    
            except Exception as e:
                error_msg = str(e)
                print(f"Deneme {attempt + 1} başarısız: {error_msg}")
                
                if "too many requests" in error_msg.lower() or "rate limit" in error_msg.lower():
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 10  # Her denemede daha uzun bekle
                        print(f"Rate limiting tespit edildi. {wait_time} saniye bekleniyor...")
                        time.sleep(wait_time)
                        continue
                    else:
                        return {
                            'source': 'Yahoo Finance',
                            'ticker': ticker,
                            'success': False,
                            'message': f'Rate limiting: {error_msg}'
                        }
                else:
                    return {
                        'source': 'Yahoo Finance',
                        'ticker': ticker,
                        'success': False,
                        'message': f'Hata: {error_msg}'
                    }
        
        return {
            'source': 'Yahoo Finance',
            'ticker': ticker,
            'success': False,
            'message': 'Maksimum deneme sayısı aşıldı'
        }
    
    def get_from_alternative_api(self, ticker):
        """Alternatif API'dan veri çekmeye çalışır"""
        try:
            self._rate_limit_delay()
            print(f"Alternatif API'dan {ticker} için veri çekiliyor...")
            
            # Finnhub API (ücretsiz tier)
            url = f"https://finnhub.io/api/v1/quote?symbol={ticker}&token=demo"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if 'c' in data and data['c'] > 0:
                    return {
                        'source': 'Alternative API',
                        'ticker': ticker,
                        'current_price': data['c'],
                        'success': True
                    }
            
            return {
                'source': 'Alternative API',
                'ticker': ticker,
                'success': False,
                'message': 'Veri bulunamadı'
            }
            
        except Exception as e:
            return {
                'source': 'Alternative API',
                'ticker': ticker,
                'success': False,
                'message': f'Hata: {str(e)}'
            }
    
    def get_ex_dividend_info(self, ticker):
        """Ana fonksiyon - ex-dividend bilgisini çeker"""
        print(f"\n🔍 {ticker} için ex-dividend bilgisi aranıyor...")
        print("=" * 50)
        
        # Önce Yahoo Finance'dan dene
        yahoo_result = self.get_from_yahoo_finance(ticker)
        
        if yahoo_result['success']:
            print("✅ Yahoo Finance'dan başarıyla veri alındı!")
            return yahoo_result
        else:
            print(f"❌ Yahoo Finance hatası: {yahoo_result['message']}")
            
            # Alternatif API'dan dene
            alt_result = self.get_from_alternative_api(ticker)
            if alt_result['success']:
                print("✅ Alternatif API'dan veri alındı!")
                return alt_result
            else:
                print(f"❌ Alternatif API hatası: {alt_result['message']}")
                
                return {
                    'source': 'Combined',
                    'ticker': ticker,
                    'success': False,
                    'message': 'Tüm kaynaklardan veri alınamadı'
                }
    
    def batch_process_tickers(self, tickers, delay_between=5):
        """Birden fazla ticker'ı işler"""
        results = {}
        
        for i, ticker in enumerate(tickers):
            print(f"\n📊 İşleniyor: {ticker} ({i+1}/{len(tickers)})")
            
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
            filename = f'ex_dividend_data_fixed_{timestamp}.csv'
        
        # Sonuçları düzenle
        data_rows = []
        for ticker, result in results.items():
            if result['success']:
                row = {
                    'Ticker': ticker,
                    'Source': result['source'],
                    'Ex_Dividend_Date': result.get('last_ex_dividend', 'N/A'),
                    'Next_Ex_Dividend': result.get('next_ex_dividend', 'N/A'),
                    'Dividend_Amount': result.get('last_dividend_amount', 'N/A'),
                    'Current_Price': result.get('current_price', 'N/A'),
                    'Status': 'Success'
                }
            else:
                row = {
                    'Ticker': ticker,
                    'Source': result['source'],
                    'Ex_Dividend_Date': 'N/A',
                    'Next_Ex_Dividend': 'N/A',
                    'Dividend_Amount': 'N/A',
                    'Current_Price': 'N/A',
                    'Status': f"Error: {result.get('message', 'Unknown error')}"
                }
            data_rows.append(row)
        
        # DataFrame oluştur ve kaydet
        df = pd.DataFrame(data_rows)
        df.to_csv(filename, index=False, encoding='utf-8')
        print(f"\n💾 Sonuçlar {filename} dosyasına kaydedildi.")
        
        return df

def main():
    """Ana fonksiyon"""
    scraper = ExDividendScraperFixed()
    
    print("🚀 Ex-Dividend Date Scraper - Rate Limiting Fixed")
    print("=" * 60)
    
    # Test ticker'ları
    test_tickers = ['DCOMP', 'AAPL', 'MSFT']
    
    print(f"📋 Test edilecek ticker'lar: {', '.join(test_tickers)}")
    
    # Batch processing
    results = scraper.batch_process_tickers(test_tickers, delay_between=3)
    
    # Sonuçları göster
    print("\n📊 SONUÇLAR:")
    print("=" * 60)
    
    for ticker, result in results.items():
        print(f"\n{ticker}:")
        if result['success']:
            if 'last_ex_dividend' in result:
                print(f"  📅 Son Ex-Dividend: {result['last_ex_dividend']}")
            if 'next_ex_dividend' in result:
                print(f"  📅 Sonraki Ex-Dividend: {result['next_ex_dividend']}")
            if 'last_dividend_amount' in result:
                print(f"  💰 Son Temettü: ${result['last_dividend_amount']:.2f}")
            if 'current_price' in result:
                print(f"  💵 Güncel Fiyat: ${result['current_price']:.2f}")
        else:
            print(f"  ❌ Hata: {result.get('message', 'Bilinmeyen hata')}")
    
    # CSV'ye kaydet
    scraper.save_to_csv(results)

if __name__ == "__main__":
    main()

























