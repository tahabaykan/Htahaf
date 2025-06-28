"""
StockTracker için Interactive Brokers bağlantı ve veri işleme fonksiyonları
"""
from ib_insync import IB, util
import time
import threading
import queue
import datetime
import math

def connect_to_ibkr(host='127.0.0.1', client_id=87, timeout=20, readonly=True):
    """
    Interactive Brokers TWS veya IB Gateway'e bağlan
    
    Args:
        host (str): Sunucu adresi
        client_id (int): Müşteri ID'si
        timeout (int): Bağlantı zaman aşımı (saniye)
        readonly (bool): Salt okunur mod (emirler gönderilmez)
        
    Returns:
        tuple: (IB, is_connected) IB nesnesi ve bağlantı durumu
    """
    try:
        print("IBKR bağlantısı kuruluyor...")
        
        # TWS/Gateway ayarları için öneriler
        print("\nÖNEMLİ TWS/GATEWAY KONTROL NOKTALARI:")
        print("1. TWS/Gateway'in açık olduğundan emin olun")
        print("2. TWS/Gateway -> File -> Global Configuration -> API -> Settings")
        print("   a. 'Enable ActiveX and Socket Clients' seçili olmalı")
        print("   b. 'Socket port' 7496 (TWS) veya 4001 (Gateway) olmalı")
        print("   c. 'Trust TWS...unencrypted' seçili olabilir")
        print("   d. 'Trusted IP Addresses' 127.0.0.1 içermeli\n")
        
        # IB nesnesi oluştur
        ib = IB()
        
        # API yapılandırma seçenekleri
        import logging
        util.logToConsole(logging.DEBUG)
        
        # TWS ve Gateway portlarını dene
        ports = [7496, 4001]  # TWS ve Gateway portları
        connected = False
        
        for port in ports:
            try:
                # Bağlantı kur - IB'ye özel parametreleri ayarla
                print(f"Port {port} ile bağlantı deneniyor...")
                
                # IPT6 sorunlarını önlemek için özel seçenekler
                opt_params = {}
                
                # Bağlantı timeout süresi
                if timeout > 0:
                    opt_params['timeout'] = timeout
                
                # Bağlantıyı kur
                ib.connect(host, port, clientId=client_id, readonly=readonly, **opt_params)
                connected = True
                print(f"Port {port} ile bağlantı başarılı!")
                
                # API sürüm kontrolü
                if hasattr(ib, 'reqCurrentTime'):
                    server_time = ib.reqCurrentTime()
                    print(f"TWS/Gateway sunucu saati: {server_time}")
                
                # API özelliklerini kontrol et
                if hasattr(ib, 'isConnected') and ib.isConnected():
                    print("Bağlantı durumu: Aktif")
                else:
                    print("Bağlantı durumu: İNAKTİF!")
                
                break
            except Exception as e:
                print(f"Port {port} bağlantı hatası: {e}")
        
        if not connected:
            print("Hiçbir porta bağlanılamadı! TWS veya Gateway çalışıyor mu?")
            print("TWS/Gateway'i başlatın ve API ayarlarını kontrol edin")
            return IB(), False
        
        # Bağlantı tamamlandı, şimdi verileri talep et
        try:
            # Önemli: API ayarlarını yap - Önce Delayed sonra Live
            print("Market veri tipi ayarlanıyor...")
            
            # Hem normal hem de after-hours veriler için
            ib.reqMarketDataType(3)  # Önce delayed talep edelim
            time.sleep(0.5)
            ib.reqMarketDataType(1)  # Sonra live talep edelim
            
            # IBKR API Ayarlarını Kontrol et
            print("\nMARKET VERİ TÜRLERİ (Test):")
            
            # Benchmark sembolleri için veri talep et (test amaçlı)
            spy_contract = Stock('SPY', 'SMART', 'USD')
            qqq_contract = Stock('QQQ', 'SMART', 'USD')
            
            # SPY ve QQQ için data talep et (test)
            print("API test: SPY ve QQQ verileri")
            generic_tick_list = "100,101,104,105,106,107,165,221,225,233,234,29,375,377,381,384,387,388"
            
            # SPY için test
            try:
                spy_ticker = ib.reqMktData(spy_contract, generic_tick_list, False, False)
                time.sleep(1)
                ib.sleep(0.5)
                print(f"SPY Test: bid={spy_ticker.bid}, ask={spy_ticker.ask}, last={spy_ticker.last}")
                
                # Test tamamlandı, aboneliği iptal et
                ib.cancelMktData(spy_contract)
            except Exception as e:
                print(f"SPY Test Hatası: {e}")
            
            # QQQ için test
            try:
                qqq_ticker = ib.reqMktData(qqq_contract, generic_tick_list, False, False)
                time.sleep(1)
                ib.sleep(0.5)
                print(f"QQQ Test: bid={qqq_ticker.bid}, ask={qqq_ticker.ask}, last={qqq_ticker.last}")
                
                # Test tamamlandı, aboneliği iptal et
                ib.cancelMktData(qqq_contract)
            except Exception as e:
                print(f"QQQ Test Hatası: {e}")
            
            # TWS/Gateway'i ping et
            server_time = ib.reqCurrentTime()
            print(f"TWS/Gateway sunucu saati: {server_time}")
            
            print("TWS/Gateway bağlantısı tam olarak kuruldu")
        except Exception as e:
            print(f"TWS/Gateway ayarları yapılandırılırken hata: {e}")
        
        return ib, ib.isConnected()
    except Exception as e:
        print(f"IBKR bağlantı hatası: {e}")
        return IB(), False

def disconnect_from_ibkr(ib):
    """
    Interactive Brokers bağlantısını kapat
    
    Args:
        ib: IB nesnesi
        
    Returns:
        bool: Başarılı şekilde kapatıldıysa True
    """
    try:
        if ib and ib.isConnected():
            ib.disconnect()
            return True
        return False
    except Exception as e:
        print(f"IBKR bağlantı kapatma hatası: {e}")
        return False

def subscribe_to_market_data(ib, contract, cancel_existing=True):
    """
    Belirli bir kontrat için piyasa verilerine abone ol
    
    Args:
        ib: IB nesnesi
        contract: Abone olunacak kontrat
        cancel_existing (bool): Varolan abonelik varsa iptal et
        
    Returns:
        int: Abonelik ID'si, başarısız olursa -1
    """
    try:
        if not ib or not ib.isConnected():
            print("IB bağlantısı yok.")
            return -1
            
        # Varolan aboneliği iptal et
        if cancel_existing:
            # Find all matching contracts for this symbol
            symbol = contract.symbol
            for ticker in ib.tickers():
                if (ticker.contract and ticker.contract.symbol == symbol and 
                    ticker.contract.secType == contract.secType):
                    try:
                        ib.cancelMktData(ticker.contract)
                        print(f"Canceled existing subscription for {symbol}")
                    except Exception as e:
                        print(f"Error canceling existing subscription: {e}")
        
        # Yeni abonelik oluştur - after-hours ve snapshot verilerini dahil et
        print(f"Requesting market data for {contract.symbol}...")
        
        # Market veri tipini ayarla - önce delayed sonra live data
        ib.reqMarketDataType(3)  # Önce delayed data
        time.sleep(0.2)
        ib.reqMarketDataType(1)  # Sonra live data
        
        # "After Hours" için özel tick türleri - working configuration from original file
        generic_tick_list = "233,165,221,225,234,29"
        
        # Direct market data request - using the exact approach from the original version
        ticker = ib.reqMktData(
            contract,
            genericTickList=generic_tick_list,
            snapshot=False,  # Continuous updates, not snapshot
            regulatorySnapshot=False
        )
        
        # Process a few IB message loop iterations immediately to get initial data
        for _ in range(5):
            ib.sleep(0.1)
            
        # Verify we got some data
        if hasattr(ticker, 'bid') and ticker.bid is not None and not math.isnan(ticker.bid):
            print(f"✓ Initial data received for {contract.symbol}: bid={ticker.bid}, ask={ticker.ask}")
        else:
            print(f"! No initial data for {contract.symbol}, will wait for updates")
        
        return ticker
    except Exception as e:
        print(f"Market data subscription error for {contract.symbol}: {e}")
        return None

def cancel_market_data_subscription(ib, contract):
    """
    Bir piyasa verisi aboneliğini iptal et
    
    Args:
        ib: IB nesnesi
        contract: İptal edilecek kontrat
        
    Returns:
        bool: Başarılı olduysa True
    """
    try:
        if not ib or not ib.isConnected():
            print("IB bağlantısı yok.")
            return False
            
        ib.cancelMktData(contract)
        return True
    except Exception as e:
        print(f"Piyasa verisi abonelik iptali hatası: {e}")
        return False

def create_api_call_processor(api_queue, max_calls_per_second=40):
    """
    API çağrı işleyicisi oluştur
    
    Args:
        api_queue: API çağrıları için kuyruk
        max_calls_per_second (int): Saniyedeki maksimum çağrı sayısı
        
    Returns:
        function: İşleme döngüsü fonksiyonu
    """
    def process_api_calls():
        """IB API çağrılarını işleyen thread fonksiyonu"""
        call_times = []  # Son çağrıların zamanlarını tut
        
        while True:
            try:
                # API çağrı hızını kontrol et
                now = time.time()
                # 1 saniye içinde yapılan çağrıları say
                call_times = [t for t in call_times if now - t < 1.0]
                
                # Eğer saniyedeki çağrı limiti aşılmışsa bekle
                if len(call_times) >= max_calls_per_second:
                    time.sleep(0.05)  # 50ms bekle
                    continue
                
                # Kuyruktan bir çağrı al
                try:
                    func, args, kwargs = api_queue.get(block=True, timeout=0.1)
                    # Çağrıyı yap
                    func(*args, **kwargs)
                    # Çağrı zamanını kaydet
                    call_times.append(time.time())
                    # Kuyruk task'ını tamamlandı işaretle
                    api_queue.task_done()
                except queue.Empty:
                    # Kuyruk boşsa biraz bekle
                    time.sleep(0.1)
                    
            except Exception as e:
                print(f"API çağrı işleme hatası: {e}")
                time.sleep(0.5)  # Hata durumunda biraz bekle
    
    return process_api_calls

def queue_api_call(api_queue, func, *args, **kwargs):
    """
    Bir API çağrısını kuyruğa ekle
    
    Args:
        api_queue: API çağrıları için kuyruk
        func: Çağrılacak fonksiyon
        *args, **kwargs: Fonksiyon parametreleri
    """
    api_queue.put((func, args, kwargs))

def handle_ib_error(req_id, error_code, error_string, contract=None):
    """
    IB hata işleyici
    
    Args:
        req_id (int): İstek ID'si
        error_code (int): Hata kodu
        error_string (str): Hata açıklaması
        contract: İlgili kontrat (varsa)
        
    Returns:
        tuple: (is_serious, message) ciddi hata mı ve hata mesajı
    """
    # Ciddi olmayan hata kodları
    non_serious_error_codes = [2104, 2106, 2158]  # Örnek kodlar
    
    contract_info = f" - {contract.symbol}" if contract else ""
    message = f"IB Hatası {error_code}: {error_string}{contract_info}"
    
    # Ciddi bir hata mı kontrol et
    is_serious = error_code not in non_serious_error_codes
    
    return is_serious, message

def on_position_update(position, account_summary_callback=None):
    """
    Pozisyon güncellemesi işleyici
    
    Args:
        position: IB position nesnesi
        account_summary_callback: Hesap özeti güncellemesi için callback
    """
    if not position:
        return
        
    # Pozisyon bilgilerini çıkar
    symbol = position.contract.symbol if position.contract else "Unknown"
    position_size = position.position
    avg_cost = position.avgCost
    
    print(f"Pozisyon güncellendi: {symbol}, Miktar: {position_size}, Ortalama Maliyet: {avg_cost}")
    
    # Hesap özeti güncellemesi için callback varsa çağır
    if account_summary_callback:
        account_summary_callback()

def parse_ticker_data(ticker):
    """
    IB ticker verisini işle ve daha kullanışlı bir formata dönüştür
    
    Args:
        ticker: IB ticker nesnesi
        
    Returns:
        dict: İşlenmiş ticker verisi
    """
    if not ticker or not ticker.contract:
        return {}
        
    try:
        symbol = ticker.contract.symbol
        
        # Temel veriyi çıkar
        data = {
            'symbol': symbol,
            'last': ticker.last if hasattr(ticker, 'last') else None,
            'bid': ticker.bid if hasattr(ticker, 'bid') else None,
            'ask': ticker.ask if hasattr(ticker, 'ask') else None,
            'close': ticker.close if hasattr(ticker, 'close') else None,
            'open': ticker.open if hasattr(ticker, 'open') else None,
            'high': ticker.high if hasattr(ticker, 'high') else None,
            'low': ticker.low if hasattr(ticker, 'low') else None,
            'volume': ticker.volume if hasattr(ticker, 'volume') else None,
            'bid_size': ticker.bidSize if hasattr(ticker, 'bidSize') else None,
            'ask_size': ticker.askSize if hasattr(ticker, 'askSize') else None,
            'last_size': ticker.lastSize if hasattr(ticker, 'lastSize') else None,
            'time': datetime.datetime.now()
        }
        
        # Değişim yüzdesini hesapla
        if data['last'] is not None and data['close'] is not None and data['close'] != 0:
            data['change_percent'] = ((data['last'] - data['close']) / data['close']) * 100
        else:
            data['change_percent'] = None
            
        # Spread hesapla
        if data['bid'] is not None and data['ask'] is not None and data['bid'] > 0:
            data['spread'] = (data['ask'] - data['bid']) / data['bid'] * 100
        else:
            data['spread'] = None
        
        return data
    except Exception as e:
        print(f"Ticker veri işleme hatası ({symbol if 'symbol' in locals() else 'unknown'}): {e}")
        return {'symbol': symbol if 'symbol' in locals() else 'unknown', 'error': str(e)}

def check_ticker_market_data(ticker):
    """
    Bir ticker'ın gerçek zamanlı market verisi olup olmadığını kontrol et
    
    Args:
        ticker: IB ticker nesnesi
        
    Returns:
        dict: Veri kullanılabilirlik bilgisi
    """
    if not ticker or not ticker.contract:
        return {'has_data': False, 'reason': 'Geçersiz ticker'}
    
    try:
        # NaN kontrolü için
        import math
        
        # Temel kontroller
        has_last = hasattr(ticker, 'last') and ticker.last is not None and not math.isnan(ticker.last)
        has_bid = hasattr(ticker, 'bid') and ticker.bid is not None and not math.isnan(ticker.bid)
        has_ask = hasattr(ticker, 'ask') and ticker.ask is not None and not math.isnan(ticker.ask)
        
        # Boyut kontrolleri
        has_last_size = hasattr(ticker, 'lastSize') and ticker.lastSize > 0
        has_bid_size = hasattr(ticker, 'bidSize') and ticker.bidSize > 0
        has_ask_size = hasattr(ticker, 'askSize') and ticker.askSize > 0
        
        # Veri var mı karar ver
        has_price_data = has_last or has_bid or has_ask
        has_size_data = has_last_size or has_bid_size or has_ask_size
        
        # Sonuç hazırla
        result = {
            'symbol': ticker.contract.symbol,
            'has_data': has_price_data,
            'has_size_only': has_size_data and not has_price_data,
            'has_last': has_last,
            'has_bid': has_bid,
            'has_ask': has_ask,
            'needs_subscription': has_size_data and not has_price_data
        }
        
        return result
    except Exception as e:
        print(f"Ticker veri kontrolü hatası: {e}")
        return {'has_data': False, 'reason': str(e)} 