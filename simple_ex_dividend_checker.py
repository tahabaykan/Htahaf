#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Basit Ex-Dividend Date Checker
Tek bir ticker için hızlı ex-dividend date kontrolü
"""

import yfinance as yf
from datetime import datetime
import pandas as pd

def check_ex_dividend_date(ticker):
    """Tek bir ticker için ex-dividend date kontrolü"""
    try:
        print(f"🔍 {ticker} için ex-dividend date kontrol ediliyor...")
        
        # Yahoo Finance'dan veri çek
        stock = yf.Ticker(ticker)
        dividends = stock.dividends
        
        if not dividends.empty:
            # En son ex-dividend date
            last_ex_div = dividends.index[-1]
            
            # Bir sonraki ex-dividend date (genellikle 3 ay sonra)
            next_ex_div = last_ex_div + pd.DateOffset(months=3)
            
            # Bugünün tarihi
            today = datetime.now()
            
            # Sonraki ex-dividend'e kalan gün
            days_until_next = (next_ex_div - today).days
            
            print(f"\n✅ {ticker} Ex-Dividend Bilgileri:")
            print(f"   📅 Son Ex-Dividend: {last_ex_div.strftime('%d/%m/%Y')}")
            print(f"   📅 Sonraki Ex-Dividend: {next_ex_div.strftime('%d/%m/%Y')}")
            print(f"   💰 Son Temettü: ${dividends.iloc[-1]:.2f}")
            print(f"   ⏰ Sonraki Ex-Dividend'e: {days_until_next} gün")
            
            # Son 5 temettü
            print(f"\n📊 Son 5 Temettü:")
            for date, amount in dividends.tail(5).items():
                print(f"   {date.strftime('%d/%m/%Y')}: ${amount:.2f}")
                
        else:
            print(f"❌ {ticker} için temettü bilgisi bulunamadı.")
            
    except Exception as e:
        print(f"❌ Hata: {str(e)}")

def main():
    """Ana fonksiyon"""
    print("🎯 Ex-Dividend Date Checker")
    print("=" * 40)
    
    while True:
        ticker = input("\n📝 Ticker girin (çıkmak için 'q'): ").strip().upper()
        
        if ticker.lower() == 'q':
            print("👋 Görüşürüz!")
            break
            
        if ticker:
            check_ex_dividend_date(ticker)
        else:
            print("❌ Lütfen geçerli bir ticker girin.")

if __name__ == "__main__":
    main()

























