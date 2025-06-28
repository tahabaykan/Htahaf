from ib_insync import IB, Stock
import threading
import time

ETF_SYMBOLS = ['PFF', 'TLT', 'SPY', 'IWM', 'KRE']

class MarketDataSnapshot:
    def __init__(self):
        self.snapshots = {}  # symbol -> {bid, ask, last, prev_close, timestamp}
        self.lock = threading.Lock()
    def update(self, symbol, data):
        with self.lock:
            self.snapshots[symbol] = {
                'bid': data.get('bid'),
                'ask': data.get('ask'),
                'last': data.get('last'),
                'prev_close': data.get('prev_close'),
                'timestamp': time.time()
            }
    def get(self, symbol):
        with self.lock:
            return self.snapshots.get(symbol)
    def get_all(self):
        with self.lock:
            return self.snapshots.copy()

class IBKRManager:
    def __init__(self):
        self.ib = IB()
        self.connected = False
        self.tickers = {}  # symbol -> {'contract': ..., 'ticker': ...}
        self.lock = threading.Lock()
        self.prev_closes = {}  # symbol -> previous close
        self.filled_trades = []  # Her fill burada tutulacak
        self.last_data = {}  # symbol -> {bid, ask, last, prev_close, timestamp}
        self.snapshot = MarketDataSnapshot()  # Snapshot manager
        self.ticker_handlers = {}  # symbol -> handler
        self.subscribed_tickers = set()  # Şu anda abone olunan tickerlar
        self.ib.execDetailsEvent += self.on_fill  # Fill event handler

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
        """Tüm abonelikleri temizle"""
        for symbol, handler in self.ticker_handlers.items():
            if hasattr(handler, 'ticker'):
                handler.ticker.updateEvent -= handler
            self.ib.cancelMktData(handler.contract)
        
        self.ticker_handlers.clear()
        self.tickers.clear()
        self.subscribed_tickers.clear()

    def clean_symbol(self, symbol):
        return str(symbol).strip().replace('.', '').replace('/', '')

    def subscribe_tickers(self, tickers):
        """Yeni tickerlar için abonelik başlat ve eski abonelikleri temizle"""
        if not self.connected:
            return

        # Eski abonelikleri temizle
        self.clear_subscriptions()

        self.missing_data_tickers = set()

        # Yeni tickerlar için abonelik başlat
        for i, symbol in enumerate(tickers):
            if symbol in self.subscribed_tickers:
                continue

            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            time.sleep(0.1)  # Her abonelik arasında daha uzun bir gecikme
            if (i+1) % 16 == 0:
                time.sleep(1)  # Her 16 tickerdan sonra 1 saniye bekle
            print(f"[IBKR] Abone olundu: {symbol}")

            # Eski handler'ı kaldır
            if symbol in self.ticker_handlers:
                old_handler = self.ticker_handlers[symbol]
                if hasattr(old_handler, 'ticker'):
                    old_handler.ticker.updateEvent -= old_handler

            handler = self.ib.reqMktData(contract, '', False, False)

            def on_update(ticker, symbol=symbol):
                with self.lock:
                    first = symbol not in self.last_data
                    self.last_data[symbol] = {
                        'bid': ticker.bid,
                        'ask': ticker.ask,
                        'last': ticker.last,
                        'prev_close': self.prev_closes.get(symbol),
                        'timestamp': time.time()
                    }
                    if first:
                        print(f"[IBKR] İlk veri geldi: {symbol} -> {self.last_data[symbol]}")
                    if symbol in self.missing_data_tickers:
                        self.missing_data_tickers.remove(symbol)

            handler.updateEvent += on_update
            self.ticker_handlers[symbol] = handler
            self.tickers[symbol] = {'contract': contract, 'ticker': handler}
            self.subscribed_tickers.add(symbol)
            self.missing_data_tickers.add(symbol)

        # 5 saniye sonra hiç veri gelmeyenleri bildir
        def log_missing():
            time.sleep(5)
            if self.missing_data_tickers:
                print(f"[IBKR] Hiç veri gelmeyen tickerlar: {sorted(self.missing_data_tickers)}")
        threading.Thread(target=log_missing, daemon=True).start()

    def get_market_data(self, symbols):
        """Cache'deki son verileri döndür"""
        with self.lock:
            return {symbol: self.last_data.get(symbol, {}) for symbol in symbols}

    def get_all_market_data(self):
        """Tüm cache'deki verileri döndür"""
        with self.lock:
            return self.last_data.copy()

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

    def get_positions(self):
        with self.lock:
            positions = self.ib.positions()
            result = []
            for pos in positions:
                result.append({
                    'symbol': pos.contract.symbol,
                    'quantity': pos.position,
                    'avgCost': pos.avgCost,
                    'account': pos.account
                })
            return result

    def get_open_orders(self):
        with self.lock:
            orders = self.ib.openOrders()
            result = []
            for o in orders:
                result.append({
                    'symbol': getattr(o.contract, 'symbol', ''),
                    'action': getattr(o.order, 'action', ''),
                    'quantity': getattr(o.order, 'totalQuantity', ''),
                    'price': getattr(o.order, 'lmtPrice', ''),
                    'status': getattr(o, 'status', ''),
                    'orderId': getattr(o.order, 'orderId', '')
                })
            return result

    def on_fill(self, trade, fill):
        symbol = fill.contract.symbol
        qty = fill.execution.shares
        price = fill.execution.price
        time_str = fill.execution.time  # '20240607  19:00:00'
        # O anki ETF fiyatları
        etf_data = self.get_etf_data()
        pff = etf_data.get('PFF', {}).get('last', None)
        tlt = etf_data.get('TLT', {}).get('last', None)
        # Benchmark formülü (ör: T için)
        fill_benchmark = None
        if pff is not None and tlt is not None:
            fill_benchmark = pff * 0.7 + tlt * 0.1
        self.filled_trades.append({
            'symbol': symbol,
            'qty': qty,
            'price': price,
            'time': time_str,
            'pff': pff,
            'tlt': tlt,
            'fill_benchmark': fill_benchmark
        })

    def get_fills_for_symbol(self, symbol):
        return [f for f in self.filled_trades if f['symbol'] == symbol]

    def get_position_avg_benchmark(self, symbol):
        fills = self.get_fills_for_symbol(symbol)
        total_qty = sum(f['qty'] for f in fills)
        if total_qty == 0:
            return None
        avg_benchmark = sum(f['qty'] * f['fill_benchmark'] for f in fills if f['fill_benchmark'] is not None) / total_qty
        return avg_benchmark

    def get_benchmark_change_since_fill(self, symbol):
        fills = self.get_fills_for_symbol(symbol)
        total_qty = sum(f['qty'] for f in fills)
        if total_qty == 0:
            return None
        avg_cost = sum(f['qty'] * f['price'] for f in fills) / total_qty
        avg_pff = sum(f['qty'] * f['pff'] for f in fills if f['pff'] is not None) / total_qty
        avg_tlt = sum(f['qty'] * f['tlt'] for f in fills if f['tlt'] is not None) / total_qty
        fill_benchmark = avg_pff * 0.7 + avg_tlt * 0.1
        # Şu anki fiyat ve benchmark
        ticker = self.tickers.get(symbol, {}).get('ticker')
        current_price = ticker.last if ticker and ticker.last is not None else None
        etf_data = self.get_etf_data()
        pff = etf_data.get('PFF', {}).get('last', None)
        tlt = etf_data.get('TLT', {}).get('last', None)
        if current_price is None or pff is None or tlt is None:
            return None
        current_benchmark = pff * 0.7 + tlt * 0.1
        # Hisse getirisi - benchmark getirisi
        return (current_price - avg_cost) - (current_benchmark - fill_benchmark) 