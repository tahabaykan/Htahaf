import pandas as pd
from ib_insync import IB, util, Stock
import logging
import time
from datetime import datetime, timedelta

def try_connect_ibkr(host='127.0.0.1', client_id=1, timeout=20, readonly=True):
    util.logToConsole(logging.WARNING)
    ib = IB()
    ports = [7497, 7496, 4001]  # TWS ve Gateway portları
    connected = False
    for port in ports:
        try:
            print(f"Port {port} ile bağlantı deneniyor...")
            ib.connect(host, port, clientId=client_id, readonly=readonly, timeout=timeout)
            if ib.isConnected():
                print(f"IBKR bağlantısı başarılı! Port: {port}")
                connected = True
                break
        except Exception as e:
            print(f"Port {port} bağlantı hatası: {e}")
    if not connected:
        print("Hiçbir IBKR portuna bağlanılamadı! TWS/Gateway açık mı?")
    return ib, connected

class MarketDataManager:
    def __init__(self, connect_on_init=False):
        self.ib = None
        self.connected = False
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        if connect_on_init:
            self.connect()
        self.historical_data = pd.read_csv('historical_data.csv')
        self.extended_data = pd.read_csv('extlthistorical.csv')
        self.active_contracts = {}
        self.market_data = {}
        
        # ✅ PSFAlgo fill tracking
        self.psf_algo = None
        self.last_fill_check = datetime.now()
        self.processed_fill_ids = set()  # İşlenmiş fill ID'leri
    
    def connect(self):
        """Connect to Interactive Brokers API."""
        try:
            print("[IBKR] 🔗 IBKR'a bağlanılıyor...")
            
            # ✅ Hızlı bağlantı için timeout
            self.ib.connect('127.0.0.1', 4001, clientId=1, timeout=10)
            
            # ✅ Market data type ayarla (hızlı)
            self.ib.reqMarketDataType(3)  # Delayed market data
            time.sleep(0.1)  # Kısa bekleme
            self.ib.reqMarketDataType(1)  # Live market data (if available)
            
            self.connected = True
            print("[IBKR] ✅ IBKR bağlantısı başarılı")
            self.logger.info("Connected to IB")
            
        except Exception as e:
            self.connected = False
            print(f"[IBKR] ❌ IBKR bağlantı hatası: {e}")
            self.logger.error(f"Failed to connect to IB: {str(e)}")
            raise

    def connect_ibkr(self):
        """IBKR'ye bağlan (main window için wrapper)"""
        try:
            self.connect()
            return True
        except Exception as e:
            print(f"[IBKR] ❌ connect_ibkr hatası: {e}")
            return False
    
    def get_historical_tickers(self, start_idx, end_idx):
        """Get tickers from historical data for the given page range."""
        return self.historical_data['PREF IBKR'].dropna().iloc[start_idx:end_idx].tolist()
    
    def get_extended_tickers(self, start_idx, end_idx):
        """Get tickers from extended data for the given page range."""
        return self.extended_data['PREF IBKR'].dropna().iloc[start_idx:end_idx].tolist()
    
    def get_max_pages(self, items_per_page):
        """Calculate maximum number of pages based on data size."""
        return max(
            len(self.historical_data) // items_per_page,
            len(self.extended_data) // items_per_page
        )
    
    def subscribe_page_tickers(self, tickers):
        """Subscribe only to tickers on the current page."""
        self.cancel_unsubscribed_tickers(tickers)
        for ticker in tickers:
            if not self.connected:
                continue
            if ticker not in self.active_contracts:
                try:
                    contract = Stock(ticker, 'SMART', 'USD')
                    self.ib.qualifyContracts(contract)
                    self.active_contracts[ticker] = contract
                    self.ib.reqMktData(contract)
                    self.logger.info(f"Subscribed to {ticker}")
                    time.sleep(0.05)  # Flood koruması için kısa bekleme
                except Exception as e:
                    self.logger.error(f"Error subscribing to {ticker}: {str(e)}")
    
    def cancel_unsubscribed_tickers(self, page_tickers):
        """Cancel subscriptions for tickers not on the current page."""
        to_cancel = [t for t in self.active_contracts if t not in page_tickers]
        for ticker in to_cancel:
            try:
                contract = self.active_contracts[ticker]
                self.ib.cancelMktData(contract)
                self.logger.info(f"Unsubscribed from {ticker}")
            except Exception as e:
                self.logger.error(f"Error unsubscribing from {ticker}: {str(e)}")
            del self.active_contracts[ticker]
    
    def get_market_data(self):
        """Get current market data for all active contracts."""
        if not self.connected:
            return {}
        for ticker, contract in self.active_contracts.items():
            ticker_data = self.ib.ticker(contract)
            if ticker_data:
                self.market_data[ticker] = {
                    'bid': ticker_data.bid,
                    'ask': ticker_data.ask,
                    'last': ticker_data.last,
                    'volume': ticker_data.volume
                }
        return self.market_data
    
    def disconnect(self):
        """Disconnect from IB and clean up."""
        if not self.connected or not self.ib:
            return
        try:
            # Cancel all market data subscriptions
            for contract in self.active_contracts.values():
                self.ib.cancelMktData(contract)
            
            # Disconnect from IB
            self.ib.disconnect()
            self.connected = False
            self.logger.info("Disconnected from IB")
        except Exception as e:
            self.logger.error(f"Error during disconnect: {str(e)}")

    def disconnect_ibkr(self):
        """IBKR bağlantısını kapat (main window için wrapper)"""
        try:
            self.disconnect()
            print("[IBKR] ✅ IBKR bağlantısı kapatıldı")
        except Exception as e:
            print(f"[IBKR] ❌ disconnect_ibkr hatası: {e}")

    def set_psf_algo(self, psf_algo):
        """PSFAlgo referansını ayarla"""
        self.psf_algo = psf_algo
        self.logger.info("PSFAlgo market data'ya bağlandı")

    def get_recent_fills(self, minutes=60):
        """IBKR'den son dakikalardaki fill'leri al"""
        try:
            if not self.connected or not self.ib:
                return []
                
            # IBKR'den fill'leri al
            fills = self.ib.fills()
            
            # Son X dakikadaki fill'leri filtrele
            cutoff_time = datetime.now() - timedelta(minutes=minutes)
            recent_fills = []
            
            for fill in fills:
                fill_time = fill.time
                if isinstance(fill_time, str):
                    # String ise datetime'a çevir
                    try:
                        fill_time = datetime.fromisoformat(fill_time.replace('Z', '+00:00'))
                    except:
                        continue
                        
                # Fill ID oluştur
                fill_id = f"{fill.contract.symbol}_{fill.execution.execId}"
                
                # Son dakikalarda ve daha önce işlenmemiş
                if fill_time >= cutoff_time and fill_id not in self.processed_fill_ids:
                    recent_fills.append({
                        'symbol': fill.contract.symbol,
                        'side': fill.execution.side,
                        'price': fill.execution.price,
                        'quantity': fill.execution.shares,
                        'time': fill_time,
                        'fill_id': fill_id
                    })
                    
                    # İşlenmiş olarak işaretle
                    self.processed_fill_ids.add(fill_id)
            
            return recent_fills
            
        except Exception as e:
            self.logger.error(f"get_recent_fills hatası: {e}")
            return []

    def get_historical_fills(self, start_time, end_time):
        """IBKR'den belirli zaman aralığındaki fill'leri al"""
        try:
            if not self.connected or not self.ib:
                return []
                
            # IBKR'den tüm fill'leri al
            fills = self.ib.fills()
            
            historical_fills = []
            for fill in fills:
                fill_time = fill.time
                if isinstance(fill_time, str):
                    try:
                        fill_time = datetime.fromisoformat(fill_time.replace('Z', '+00:00'))
                    except:
                        continue
                
                # Zaman aralığında mı?
                if start_time <= fill_time <= end_time:
                    historical_fills.append({
                        'symbol': fill.contract.symbol,
                        'side': fill.execution.side,
                        'price': fill.execution.price,
                        'quantity': fill.execution.shares,
                        'time': fill_time
                    })
            
            return historical_fills
            
        except Exception as e:
            self.logger.error(f"get_historical_fills hatası: {e}")
            return []

    def get_etf_data(self):
        """ETF verilerini al (PFF, TLT için benchmark hesaplama) - Previous close ile"""
        try:
            if not self.connected or not self.ib:
                return {}
                
            etf_data = {}
            etf_tickers = ['PFF', 'TLT', 'SPY', 'IWM', 'KRE']
            
            print("[ETF UPDATE] 📊 ETF'ler IBKR'den güncelleniyor...")
            
            for ticker in etf_tickers:
                try:
                    # ✅ ETF'ler için farklı exchange'ler dene
                    contract = None
                    exchanges = ['ARCA', 'NASDAQ', 'NYSE', 'SMART']
                    
                    for exchange in exchanges:
                        try:
                            test_contract = Stock(ticker, exchange, 'USD')
                            qualified = self.ib.qualifyContracts(test_contract)
                            if qualified:
                                contract = qualified[0]
                                break
                        except Exception as e:
                            continue
                    
                    if not contract:
                        print(f"[ETF UPDATE] ❌ {ticker} contract bulunamadı")
                        etf_data[ticker] = {
                            'last': 'N/A', 'bid': 'N/A', 'ask': 'N/A', 'volume': 'N/A',
                            'prev_close': 'N/A', 'change': 'N/A', 'change_pct': 'N/A'
                        }
                        continue
                    
                    # ✅ Timeout ile market data al
                    import time
                    start_time = time.time()
                    ticker_data = self.ib.ticker(contract)
                    
                    # 2 saniye timeout
                    while (not ticker_data.last or ticker_data.last == 0) and (time.time() - start_time) < 2:
                        self.ib.sleep(0.1)
                        ticker_data = self.ib.ticker(contract)
                    
                    if ticker_data and ticker_data.last and ticker_data.last > 0:
                        last = ticker_data.last
                        prev_close = ticker_data.close  # Previous close
                        
                        # Change hesapla
                        if prev_close and prev_close > 0:
                            change = round(last - prev_close, 3)
                            change_pct = round(100 * (last - prev_close) / prev_close, 2)
                        else:
                            change = 'N/A'
                            change_pct = 'N/A'
                        
                        etf_data[ticker] = {
                            'last': last,
                            'bid': ticker_data.bid or 'N/A',
                            'ask': ticker_data.ask or 'N/A',
                            'volume': ticker_data.volume or 'N/A',
                            'prev_close': prev_close or 'N/A',
                            'change': change,
                            'change_pct': change_pct
                        }
                        
                        print(f"[ETF UPDATE] {ticker}: Last={last}, PrevClose={prev_close}, Change={change} ({change_pct}%)")
                    else:
                        print(f"[ETF UPDATE] ⚠️ {ticker} market data alınamadı")
                        etf_data[ticker] = {
                            'last': 'N/A', 'bid': 'N/A', 'ask': 'N/A', 'volume': 'N/A',
                            'prev_close': 'N/A', 'change': 'N/A', 'change_pct': 'N/A'
                        }
                        
                except Exception as e:
                    print(f"[ETF UPDATE] ❌ {ticker} hatası: {e}")
                    etf_data[ticker] = {
                        'last': 'N/A', 'bid': 'N/A', 'ask': 'N/A', 'volume': 'N/A',
                        'prev_close': 'N/A', 'change': 'N/A', 'change_pct': 'N/A'
                    }
            
            print(f"[ETF UPDATE] ✅ {len([k for k, v in etf_data.items() if v['last'] != 'N/A'])} ETF güncellendi")
            return etf_data
            
        except Exception as e:
            self.logger.error(f"get_etf_data hatası: {e}")
            return {}

    def get_positions(self):
        """IBKR'den pozisyonları al"""
        try:
            if not self.connected or not self.ib:
                return []
                
            positions = []
            for position in self.ib.positions():
                positions.append({
                    'symbol': position.contract.symbol,
                    'quantity': position.position,
                    'avgCost': position.avgCost
                })
                
            return positions
            
        except Exception as e:
            self.logger.error(f"get_positions hatası: {e}")
            return [] 
