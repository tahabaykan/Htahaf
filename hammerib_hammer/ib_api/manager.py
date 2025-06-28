from ib_insync import IB, Stock
import threading
import time

ETF_SYMBOLS = ['PFF', 'TLT', 'SPY', 'IWM', 'KRE']

class IBKRManager:
    def __init__(self):
        self.ib = IB()
        self.connected = False
        self.tickers = {}  # symbol -> {'contract': ..., 'ticker': ...}
        self.lock = threading.Lock()
        self.prev_closes = {}  # symbol -> previous close

    def connect(self):
        self.ib.connect('127.0.0.1', 4001, clientId=1)
        self.ib.reqMarketDataType(3)
        time.sleep(0.2)
        self.ib.reqMarketDataType(1)
        self.connected = True
        self.subscribe_etfs()

    def subscribe_etfs(self):
        with self.lock:
            for symbol in ETF_SYMBOLS:
                if symbol not in self.tickers:
                    contract = Stock(symbol, 'SMART', 'USD')
                    self.ib.qualifyContracts(contract)
                    ticker = self.ib.reqMktData(contract, '', False, False, [])
                    self.tickers[symbol] = {'contract': contract, 'ticker': ticker}
                    # Previous close için historical data iste
                    bars = self.ib.reqHistoricalData(contract, endDateTime='', durationStr='2 D', barSizeSetting='1 day', whatToShow='TRADES', useRTH=True)
                    if bars and len(bars) >= 2:
                        self.prev_closes[symbol] = bars[-2].close
                    else:
                        self.prev_closes[symbol] = None
                    time.sleep(0.05)

    def get_etf_data(self):
        with self.lock:
            data = {}
            for symbol in ETF_SYMBOLS:
                if symbol in self.tickers:
                    t = self.tickers[symbol]['ticker']
                    last = t.last
                    prev_close = self.prev_closes.get(symbol)
                    if last is not None and prev_close is not None:
                        change = round(last - prev_close, 3)
                        change_pct = round(100 * (last - prev_close) / prev_close, 3) if prev_close != 0 else 0
                    else:
                        change = 'N/A'
                        change_pct = 'N/A'
                    data[symbol] = {
                        'last': last,
                        'change': change,
                        'change_pct': change_pct
                    }
            return data

    def clear_subscriptions(self):
        with self.lock:
            for symbol in list(self.tickers.keys()):
                try:
                    contract = self.tickers[symbol]['contract']
                    self.ib.cancelMktData(contract)
                    del self.tickers[symbol]
                except Exception as e:
                    print(f"! Abonelik iptal hatası ({symbol}): {e}")
            # Market data tipi sıfırla
            self.ib.reqMarketDataType(3)
            time.sleep(0.2)
            self.ib.reqMarketDataType(1)

    def subscribe_tickers(self, symbols):
        with self.lock:
            for symbol in symbols:
                if symbol not in self.tickers:
                    contract = Stock(symbol, 'SMART', 'USD')
                    self.ib.qualifyContracts(contract)
                    ticker = self.ib.reqMktData(contract)
                    self.tickers[symbol] = {'contract': contract, 'ticker': ticker}
                    time.sleep(0.05)
            # Eski abonelikleri iptal et
            to_cancel = [t for t in self.tickers if t not in symbols]
            for symbol in to_cancel:
                self.ib.cancelMktData(self.tickers[symbol]['contract'])
                del self.tickers[symbol]

    def get_market_data(self, symbols):
        with self.lock:
            data = {}
            for symbol in symbols:
                if symbol in self.tickers:
                    t = self.tickers[symbol]['ticker']
                    data[symbol] = {
                        'bid': t.bid, 'ask': t.ask, 'last': t.last, 'volume': t.volume
                    }
            return data

    def calculate_benchmarks(self):
        with self.lock:
            pff_data = self.tickers.get('PFF', {}).get('ticker')
            tlt_data = self.tickers.get('TLT', {}).get('ticker')
            if pff_data and tlt_data:
                pff_change = pff_data.last - self.prev_closes.get('PFF', 0) if pff_data.last is not None and self.prev_closes.get('PFF') is not None else 0
                tlt_change = tlt_data.last - self.prev_closes.get('TLT', 0) if tlt_data.last is not None and self.prev_closes.get('TLT') is not None else 0
                t_benchmark = round(pff_change * 0.7 + tlt_change * 0.1, 3)
                c_benchmark = round(pff_change * 1.3 - tlt_change * 0.1, 3)
                return {'T-Benchmark': t_benchmark, 'C-Benchmark': c_benchmark}
            return {'T-Benchmark': 'N/A', 'C-Benchmark': 'N/A'} 