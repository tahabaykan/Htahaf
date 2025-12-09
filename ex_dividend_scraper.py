#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ex-Dividend Date Scraper
Herhangi bir ticker için güncel ex-dividend date bilgilerini çeker
"""

import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json
import os

class ExDividendScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_from_yahoo_finance(self, ticker):
        """Yahoo Finance'dan ex-dividend date bilgisini çeker"""
        try:
            print(f"Yahoo Finance'dan {ticker} için veri çekiliyor...")
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
            return {
                'source': 'Yahoo Finance',
                'ticker': ticker,
                'success': False,
                'message': f'Hata: {str(e)}'
            }
    
    def get_from_marketchameleon(self, ticker):
        """MarketChameleon'dan ex-dividend date bilgisini çeker"""
        url = f"https://marketchameleon.com/Overview/{ticker}/Dividends/"
        
        try:
            print(f"MarketChameleon'dan {ticker} için veri çekiliyor...")
            
            # Chrome driver'ı başlat
            options = webdriver.ChromeOptions()
            options.add_argument('--headless')  # Arka planda çalıştır
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            
            driver = webdriver.Chrome(options=options)
            driver.get(url)
            
            # Sayfanın yüklenmesini bekle
            time.sleep(5)
            
            # Ex-dividend date elementini bul
            try:
                ex_div_element = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, "//td[contains(text(), 'Ex-Dividend')]"))
                )
                
                # Ex-dividend date'i al
                ex_div_date = ex_div_element.find_element(By.XPATH, "following-sibling::td").text
                
                driver.quit()
                
                return {
                    'source': 'MarketChameleon',
                    'ticker': ticker,
                    'ex_dividend_date': ex_div_date,
                    'success': True
                }
                
            except Exception as e:
                driver.quit()
                return {
                    'source': 'MarketChameleon',
                    'ticker': ticker,
                    'success': False,
                    'message': f'Ex-dividend date bulunamadı: {str(e)}'
                }
                
        except Exception as e:
            if 'driver' in locals():
                driver.quit()
            return {
                'source': 'MarketChameleon',
                'ticker': ticker,
                'success': False,
                'message': f'Hata: {str(e)}'
            }
    
    def get_from_alphavantage(self, ticker, api_key):
        """Alpha Vantage API'dan ex-dividend date bilgisini çeker"""
        url = f"https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_MONTHLY_ADJUSTED",
            "symbol": ticker,
            "apikey": api_key
        }
        
        try:
            print(f"Alpha Vantage'dan {ticker} için veri çekiliyor...")
            response = self.session.get(url, params=params)
            data = response.json()
            
            if "Monthly Adjusted Time Series" in data:
                # En son ayın verilerini al
                latest_month = list(data["Monthly Adjusted Time Series"].keys())[0]
                dividend_amount = float(data["Monthly Adjusted Time Series"][latest_month]["7. dividend amount"])
                
                if dividend_amount > 0:
                    return {
                        'source': 'Alpha Vantage',
                        'ticker': ticker,
                        'ex_dividend_date': latest_month,
                        'dividend_amount': dividend_amount,
                        'success': True
                    }
                else:
                    return {
                        'source': 'Alpha Vantage',
                        'ticker': ticker,
                        'success': False,
                        'message': 'Temettü yok'
                    }
            else:
                return {
                    'source': 'Alpha Vantage',
                    'ticker': ticker,
                    'success': False,
                    'message': 'Veri bulunamadı'
                }
                
        except Exception as e:
            return {
                'source': 'Alpha Vantage',
                'ticker': ticker,
                'success': False,
                'message': f'Hata: {str(e)}'
            }
    
    def get_all_sources(self, ticker, alpha_vantage_key=None):
        """Tüm kaynaklardan ex-dividend date bilgisini çeker"""
        results = {}
        
        # Yahoo Finance
        results['yahoo'] = self.get_from_yahoo_finance(ticker)
        
        # MarketChameleon
        results['marketchameleon'] = self.get_from_marketchameleon(ticker)
        
        # Alpha Vantage (API key varsa)
        if alpha_vantage_key:
            results['alphavantage'] = self.get_from_alphavantage(ticker, alpha_vantage_key)
        
        return results
    
    def save_to_csv(self, results, filename=None):
        """Sonuçları CSV dosyasına kaydeder"""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'ex_dividend_data_{timestamp}.csv'
        
        # Sonuçları düzenle
        data_rows = []
        for source, result in results.items():
            if result['success']:
                row = {
                    'Ticker': result['ticker'],
                    'Source': result['source'],
                    'Ex_Dividend_Date': result.get('ex_dividend_date', result.get('last_ex_dividend', 'N/A')),
                    'Next_Ex_Dividend': result.get('next_ex_dividend', 'N/A'),
                    'Dividend_Amount': result.get('last_dividend_amount', result.get('dividend_amount', 'N/A')),
                    'Status': 'Success'
                }
            else:
                row = {
                    'Ticker': result['ticker'],
                    'Source': result['source'],
                    'Ex_Dividend_Date': 'N/A',
                    'Next_Ex_Dividend': 'N/A',
                    'Dividend_Amount': 'N/A',
                    'Status': f"Error: {result.get('message', 'Unknown error')}"
                }
            data_rows.append(row)
        
        # DataFrame oluştur ve kaydet
        df = pd.DataFrame(data_rows)
        df.to_csv(filename, index=False, encoding='utf-8')
        print(f"Sonuçlar {filename} dosyasına kaydedildi.")
        
        return df

def main():
    """Ana fonksiyon"""
    scraper = ExDividendScraper()
    
    # Test ticker'ları
    test_tickers = ['DCOMP', 'AAPL', 'MSFT', 'JNJ']
    
    print("Ex-Dividend Date Scraper")
    print("=" * 50)
    
    for ticker in test_tickers:
        print(f"\n{ticker} için veri çekiliyor...")
        print("-" * 30)
        
        # Tüm kaynaklardan veri çek
        results = scraper.get_all_sources(ticker)
        
        # Sonuçları göster
        for source, result in results.items():
            print(f"{source.upper()}:")
            if result['success']:
                if 'ex_dividend_date' in result:
                    print(f"  Ex-Dividend Date: {result['ex_dividend_date']}")
                if 'last_ex_dividend' in result:
                    print(f"  Son Ex-Dividend: {result['last_ex_dividend']}")
                if 'next_ex_dividend' in result:
                    print(f"  Sonraki Ex-Dividend: {result['next_ex_dividend']}")
                if 'dividend_amount' in result:
                    print(f"  Temettü Miktarı: ${result['dividend_amount']:.2f}")
            else:
                print(f"  Hata: {result.get('message', 'Bilinmeyen hata')}")
        
        print()
    
    # Sonuçları CSV'ye kaydet
    all_results = {}
    for ticker in test_tickers:
        all_results[ticker] = scraper.get_all_sources(ticker)
    
    # CSV'ye kaydet
    scraper.save_to_csv(all_results)

if __name__ == "__main__":
    main()

























