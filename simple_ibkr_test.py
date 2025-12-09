#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple IBKR Test
IBKR Gateway bağlantısı ve ex-dividend date testi
"""

from ib_insync import IB, Stock
import time

def test_ibkr_connection():
    """IBKR bağlantısını test eder"""
    print("🔌 IBKR bağlantısı test ediliyor...")
    
    ib = IB()
    
    try:
        # Gateway portlarını dene
        ports = [4001, 7496]  # Gateway, TWS
        
        for port in ports:
            try:
                print(f"📡 {port} portuna bağlanılıyor...")
                ib.connect('127.0.0.1', port, clientId=30, readonly=True)
                print(f"✅ {port} portu ile bağlantı başarılı!")
                
                # Delayed data
                ib.reqMarketDataType(3)
                
                return ib, port
                
            except Exception as e:
                print(f"❌ {port} portu hatası: {e}")
                continue
        
        print("❌ Hiçbir porta bağlanılamadı!")
        return None, None
        
    except Exception as e:
        print(f"❌ Genel bağlantı hatası: {e}")
        return None, None

def test_dividend_info(ib, ticker):
    """Ticker için dividend bilgilerini test eder"""
    try:
        print(f"\n💰 {ticker} için dividend bilgileri test ediliyor...")
        
        # Stock contract oluştur
        contract = Stock(ticker, exchange='SMART', currency='USD')
        
        # Contract detaylarını al
        print(f"🔍 Contract detayları alınıyor...")
        details = ib.reqContractDetails(contract)
        
        if details:
            print(f"✅ Contract bulundu!")
            
            detail = details[0]
            contract_obj = detail.contract
            
            print(f"   📊 Exchange: {contract_obj.exchange}")
            print(f"   💱 Currency: {contract_obj.currency}")
            print(f"   📝 Symbol: {contract_obj.symbol}")
            
            # Long name
            if hasattr(detail, 'longName'):
                print(f"   🏷️ Long Name: {detail.longName}")
            
            # Yield bilgisi
            if hasattr(detail, 'yield_') and detail.yield_:
                print(f"   💰 Yield: {detail.yield_}")
            
            # Market name
            if hasattr(detail, 'marketName'):
                print(f"   🏪 Market Name: {detail.marketName}")
            
            # Category
            if hasattr(detail, 'category'):
                print(f"   📂 Category: {detail.category}")
            
            return True
            
        else:
            print(f"❌ Contract bulunamadı")
            return False
            
    except Exception as e:
        print(f"❌ {ticker} test hatası: {e}")
        return False

def main():
    """Ana fonksiyon"""
    print("🚀 Simple IBKR Test")
    print("=" * 40)
    
    # IBKR'ye bağlan
    ib, port = test_ibkr_connection()
    
    if ib and port:
        print(f"\n✅ IBKR {port} portu ile bağlantı kuruldu!")
        
        # Test ticker'ları
        test_tickers = ['DCOMP', 'AAPL']
        
        success_count = 0
        for ticker in test_tickers:
            if test_dividend_info(ib, ticker):
                success_count += 1
        
        print(f"\n📊 Test Sonucu: {success_count}/{len(test_tickers)} başarılı")
        
        # Bağlantıyı kapat
        try:
            ib.disconnect()
            print("🔌 IBKR bağlantısı kapatıldı.")
        except:
            pass
    
    else:
        print("❌ IBKR bağlantısı kurulamadı!")

if __name__ == "__main__":
    main()

























