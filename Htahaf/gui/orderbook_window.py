from ib_insync import Stock
import tkinter as tk
from tkinter import ttk
import datetime
import threading
import time
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract

def polygon_to_ibkr_ticker(ticker):
    import re
    m = re.match(r'^([A-Z]+)p([A-Z]+)$', ticker)
    if m:
        return f"{m.group(1)} PR{m.group(2)}"
    return ticker

class VenueDataCollector(EWrapper, EClient):
    """Venue bilgilerini toplamak için özel sınıf"""
    def __init__(self):
        EClient.__init__(self, self)
        self.connected = False
        self.venue_data = {}
        self.symbol_map = {}
        
        # Venue mapping - daha kapsamlı
        self.venue_mapping = {
            'SMART': 'SMART',
            'NYSE': 'NYSE',
            'NASDAQ': 'NASDAQ', 
            'NSDQ': 'NASDAQ',
            'ARCA': 'ARCA',
            'ARCX': 'ARCA',
            'EDGX': 'EDGX',
            'EDGA': 'EDGA',
            'IEX': 'IEX',
            'IEXG': 'IEX',
            'BYX': 'BYX',
            'BZX': 'BZX',
            'MEMX': 'MEMX',
            'ADFN': 'ADFN',
            'DRCTEDGE': 'DRCTEDGE',
            'BATS': 'BATS',
            'BEX': 'BEX',
            'PEARL': 'PEARL',
            'CHX': 'CHX',
            'PSX': 'PSX',
            'LTSE': 'LTSE',
            # IBKR internal codes
            'P': 'ARCA',
            'Q': 'NASDAQ', 
            'N': 'NYSE',
            'B': 'BATS',
            'A': 'AMEX',
            'I': 'IEX',
            'Z': 'BATS',
            'Y': 'BATS',
            'C': 'NSX',
            'D': 'FINRA',
            'T': 'NASDAQ',
            'X': 'PHLX',
            'M': 'MEMX',
            'H': 'CHX',
            'L': 'LTSE',
            'J': 'EDGX',
            'K': 'EDGA',
            'U': 'BYX',
            'V': 'BZX',
            '': 'SMART',  # Boş venue için SMART
            None: 'SMART'  # None venue için SMART
        }
        
    def nextValidId(self, orderId):
        self.connected = True
        
    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        if errorCode not in [2104, 2106, 2158, 2119, 10092]:
            print(f"Venue Collector Error [{reqId}] {errorCode}: {errorString}")
    
    def get_venue_name(self, venue_code):
        """Venue kodunu gerçek borsa ismine çevir - her zaman bir venue döndür"""
        if not venue_code or venue_code == '':
            return 'SMART'  # Boş venue için SMART döndür
        return self.venue_mapping.get(venue_code, venue_code if venue_code else 'SMART')
    
    def updateMktDepthL2(self, reqId, position, marketMaker, operation, side, price, size, isSmartDepth):
        """Level 2 Market Depth with REAL venue info - her bid/ask için venue garantisi"""
        symbol = self.symbol_map.get(reqId, f'ReqId_{reqId}')
        
        if symbol not in self.venue_data:
            self.venue_data[symbol] = {
                'bids': {},
                'asks': {},
                'last_trades': []
            }
            
        # Market maker = REAL VENUE! - Boş olsa bile SMART olarak işaretle
        venue = self.get_venue_name(marketMaker)
        
        # Debug: venue bilgisini logla
        side_name = "BID" if side == 1 else "ASK"
        print(f"🏛️ {symbol} {side_name}[{position}]: ${price:.2f} x {size} @ {venue} (MM: '{marketMaker}', Smart: {isSmartDepth})")
        
        if operation == 0:  # Insert
            key = f"{position}_{venue}_{time.time()}"
            self.venue_data[symbol]['bids' if side == 1 else 'asks'][key] = {
                'position': position,
                'price': price,
                'size': size,
                'venue': venue,
                'original_mm': marketMaker if marketMaker else 'SMART',
                'smart_depth': isSmartDepth
            }
        elif operation == 1:  # Update
            for key in list(self.venue_data[symbol]['bids' if side == 1 else 'asks'].keys()):
                if self.venue_data[symbol]['bids' if side == 1 else 'asks'][key]['position'] == position:
                    self.venue_data[symbol]['bids' if side == 1 else 'asks'][key].update({
                        'price': price,
                        'size': size,
                        'venue': venue,
                        'original_mm': marketMaker if marketMaker else 'SMART'
                    })
                    break
        elif operation == 2:  # Delete
            keys_to_delete = []
            for key in self.venue_data[symbol]['bids' if side == 1 else 'asks'].keys():
                if self.venue_data[symbol]['bids' if side == 1 else 'asks'][key]['position'] == position:
                    keys_to_delete.append(key)
            for key in keys_to_delete:
                del self.venue_data[symbol]['bids' if side == 1 else 'asks'][key]
    
    def tickByTickAllLast(self, reqId, tickType, time, price, size, tickAttribLast, exchange, specialConditions):
        """Tick-by-tick LAST trades with REAL exchange info"""
        symbol = self.symbol_map.get(reqId, f'ReqId_{reqId}')
        
        if symbol not in self.venue_data:
            self.venue_data[symbol] = {
                'bids': {},
                'asks': {},
                'last_trades': []
            }
            
        # REAL EXCHANGE from tick-by-tick! - Boş olsa bile SMART
        venue = self.get_venue_name(exchange)
        
        trade_entry = {
            'time': datetime.datetime.now().strftime('%H:%M:%S'),
            'venue': venue,
            'price': price,
            'size': size,
            'conditions': specialConditions
        }
        
        self.venue_data[symbol]['last_trades'].insert(0, trade_entry)
        self.venue_data[symbol]['last_trades'] = self.venue_data[symbol]['last_trades'][:10]
        
        print(f"⚡ {symbol} TRADE: ${price:.2f} x {size} @ {venue} (Exchange: '{exchange}')")

class OrderBookWindow(tk.Toplevel):
    def __init__(self, parent, ticker, ibkr_client):
        super().__init__(parent)
        self.title(f"{ticker} Order Book & Last Print - VENUE BİLGİLERİ")
        self.geometry("900x600")
        self.ticker = ticker
        self.ibkr_client = ibkr_client
        self.venue_collector = None
        self.venue_thread = None
        self._build_ui()
        
        # Otomatik olarak venue data collection başlat
        self.after(100, self._fetch_data)
        self.after(500, self._auto_start_venue_collection)

    def _build_ui(self):
        # Ana frame
        main_frame = ttk.Frame(self)
        main_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Başlık
        title_label = ttk.Label(main_frame, text=f"Order Book (Top 5) - {self.ticker} - VENUE BİLGİLERİ", 
                               font=("Arial", 12, "bold"))
        title_label.pack(pady=5)
        
        # Order Book tablosu (venue'lerle birlikte)
        self.ob_table = ttk.Treeview(main_frame, 
                                    columns=("Bid Price", "Bid Size", "Bid Venue", "Ask Price", "Ask Size", "Ask Venue"), 
                                    show="headings", height=8)
        
        # Sütun başlıkları
        self.ob_table.heading("Bid Price", text="Bid Price")
        self.ob_table.heading("Bid Size", text="Bid Size")
        self.ob_table.heading("Bid Venue", text="Bid Venue")
        self.ob_table.heading("Ask Price", text="Ask Price")
        self.ob_table.heading("Ask Size", text="Ask Size")
        self.ob_table.heading("Ask Venue", text="Ask Venue")
        
        # Sütun genişlikleri
        for col in ["Bid Price", "Ask Price"]:
            self.ob_table.column(col, width=80, anchor='center')
        for col in ["Bid Size", "Ask Size"]:
            self.ob_table.column(col, width=70, anchor='center')
        for col in ["Bid Venue", "Ask Venue"]:
            self.ob_table.column(col, width=100, anchor='center')
            
        self.ob_table.pack(fill="x", pady=5)
        
        # Last Trades başlığı
        ttk.Label(main_frame, text="Last Trades (Venue Bilgili)", font=("Arial", 11, "bold")).pack(pady=(10,5))
        
        # Last Trades tablosu
        self.lt_table = ttk.Treeview(main_frame, 
                                    columns=("Time", "Price", "Size", "Venue", "Conditions"), 
                                    show="headings", height=6)
        
        for col in self.lt_table["columns"]:
            self.lt_table.heading(col, text=col)
            if col == "Time":
                self.lt_table.column(col, width=80, anchor='center')
            elif col == "Price":
                self.lt_table.column(col, width=80, anchor='center')
            elif col == "Size":
                self.lt_table.column(col, width=70, anchor='center')
            elif col == "Venue":
                self.lt_table.column(col, width=100, anchor='center')
            else:
                self.lt_table.column(col, width=120, anchor='center')
                
        self.lt_table.pack(fill="x", pady=5)
        
        # Butonlar frame - sadece yenile butonu
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill='x', pady=5)
        
        # Yenile butonu
        ttk.Button(btn_frame, text="Yenile", command=self._refresh_data).pack(side='left', padx=5)
        
        # Status label
        self.status_label = ttk.Label(main_frame, text="Veriler yükleniyor...", foreground="blue")
        self.status_label.pack(pady=5)

    def _fetch_data(self):
        """Temel orderbook verilerini çek - venue bilgilerini de dahil et"""
        try:
            ibkr_ticker = polygon_to_ibkr_ticker(self.ticker)
            contract = Stock(ibkr_ticker, 'SMART', 'USD')
            self.ibkr_client.qualifyContracts(contract)
            
            # Market data snapshot
            self.ibkr_client.reqMktData(contract, snapshot=True)
            self.ibkr_client.sleep(1)
            ticker = self.ibkr_client.ticker(contract)
            
            # Market depth
            self.ibkr_client.reqMktDepth(contract, numRows=5, isSmartDepth=True)
            self.ibkr_client.sleep(2)
            ticker_depth = self.ibkr_client.ticker(contract)
            
            bids = ticker_depth.domBids[:5] if ticker_depth.domBids else []
            asks = ticker_depth.domAsks[:5] if ticker_depth.domAsks else []
            
            # Tabloyu güncelle - venue bilgilerini de dahil et
            self._update_orderbook_table_with_basic_venues(bids, asks)
            
            self.ibkr_client.cancelMktDepth(contract)
            self.status_label.config(text="Temel veriler yüklendi. Venue bilgileri otomatik olarak başlatılıyor...", foreground="green")
            
        except Exception as e:
            import traceback
            print("[DEBUG] IBKR Orderbook Hatası:", e)
            traceback.print_exc()
            self.status_label.config(text=f"Hata: {e}", foreground="red")
    
    def _update_orderbook_table_with_basic_venues(self, bids, asks):
        """Temel orderbook tablosunu venue bilgileriyle güncelle"""
        self.ob_table.delete(*self.ob_table.get_children())
        
        for i in range(5):
            bid_row = bids[i] if i < len(bids) else None
            ask_row = asks[i] if i < len(asks) else None
            
            # Temel venue bilgilerini al - marketMaker field'ından
            bid_venue = "SMART"  # Default
            ask_venue = "SMART"  # Default
            
            if bid_row and hasattr(bid_row, 'marketMaker') and bid_row.marketMaker:
                bid_venue = self._map_venue_name(bid_row.marketMaker)
                print(f"📊 Basic BID[{i}]: ${bid_row.price:.2f} x {bid_row.size} @ {bid_venue} (MM: {bid_row.marketMaker})")
            elif bid_row:
                bid_venue = "SMART"  # Bid var ama venue yok, SMART olarak işaretle
                print(f"📊 Basic BID[{i}]: ${bid_row.price:.2f} x {bid_row.size} @ {bid_venue} (No MM)")
                
            if ask_row and hasattr(ask_row, 'marketMaker') and ask_row.marketMaker:
                ask_venue = self._map_venue_name(ask_row.marketMaker)
                print(f"📊 Basic ASK[{i}]: ${ask_row.price:.2f} x {ask_row.size} @ {ask_venue} (MM: {ask_row.marketMaker})")
            elif ask_row:
                ask_venue = "SMART"  # Ask var ama venue yok, SMART olarak işaretle
                print(f"📊 Basic ASK[{i}]: ${ask_row.price:.2f} x {ask_row.size} @ {ask_venue} (No MM)")
            
            self.ob_table.insert("", "end", values=(
                f"{bid_row.price:.2f}" if bid_row else "",
                f"{bid_row.size}" if bid_row else "",
                bid_venue if bid_row else "",  # Bid varsa venue göster
                f"{ask_row.price:.2f}" if ask_row else "",
                f"{ask_row.size}" if ask_row else "",
                ask_venue if ask_row else ""   # Ask varsa venue göster
            ))
    
    def _map_venue_name(self, venue_code):
        """Venue kodunu isime çevir - her zaman bir değer döndür"""
        venue_mapping = {
            'SMART': 'SMART',
            'NYSE': 'NYSE',
            'NASDAQ': 'NASDAQ', 
            'NSDQ': 'NASDAQ',
            'ARCA': 'ARCA',
            'ARCX': 'ARCA',
            'EDGX': 'EDGX',
            'EDGA': 'EDGA',
            'IEX': 'IEX',
            'IEXG': 'IEX',
            'BYX': 'BYX',
            'BZX': 'BZX',
            'MEMX': 'MEMX',
            'ADFN': 'ADFN',
            'DRCTEDGE': 'DRCTEDGE',
            'BATS': 'BATS',
            'BEX': 'BEX',
            'PEARL': 'PEARL',
            'CHX': 'CHX',
            'PSX': 'PSX',
            'LTSE': 'LTSE',
            # IBKR internal codes
            'P': 'ARCA',
            'Q': 'NASDAQ', 
            'N': 'NYSE',
            'B': 'BATS',
            'A': 'AMEX',
            'I': 'IEX',
            'Z': 'BATS',
            'Y': 'BATS',
            'C': 'NSX',
            'D': 'FINRA',
            'T': 'NASDAQ',
            'X': 'PHLX',
            'M': 'MEMX',
            'H': 'CHX',
            'L': 'LTSE',
            'J': 'EDGX',
            'K': 'EDGA',
            'U': 'BYX',
            'V': 'BZX'
        }
        
        if not venue_code or venue_code == '':
            return 'SMART'
        return venue_mapping.get(venue_code, venue_code if venue_code else 'SMART')
    
    def _update_orderbook_table(self, bids, asks, venue_bids=None, venue_asks=None):
        """Orderbook tablosunu güncelle"""
        self.ob_table.delete(*self.ob_table.get_children())
        
        for i in range(5):
            bid_row = bids[i] if i < len(bids) else None
            ask_row = asks[i] if i < len(asks) else None
            
            # Venue bilgilerini al
            bid_venue = "SMART"  # Default venue
            ask_venue = "SMART"  # Default venue
            
            if venue_bids and i < len(venue_bids):
                bid_venue = venue_bids[i].get('venue', 'SMART')
            elif bid_row:  # Bid var ama venue bilgisi yok
                bid_venue = "SMART"
                
            if venue_asks and i < len(venue_asks):
                ask_venue = venue_asks[i].get('venue', 'SMART')
            elif ask_row:  # Ask var ama venue bilgisi yok
                ask_venue = "SMART"
            
            self.ob_table.insert("", "end", values=(
                f"{bid_row.price:.2f}" if bid_row else "",
                f"{bid_row.size}" if bid_row else "",
                bid_venue if bid_row else "",  # Sadece bid varsa venue göster
                f"{ask_row.price:.2f}" if ask_row else "",
                f"{ask_row.size}" if ask_row else "",
                ask_venue if ask_row else ""   # Sadece ask varsa venue göster
            ))
    
    def _auto_start_venue_collection(self):
        """Otomatik venue data collection başlat"""
        print(f"🚀 {self.ticker} için otomatik venue data collection başlatılıyor...")
        
        try:
            # Yeni venue collector oluştur
            self.venue_collector = VenueDataCollector()
            
            # Bağlantı thread'i
            def connect_and_collect():
                try:
                    print(f"📡 {self.ticker} venue collector bağlanıyor...")
                    # Bağlan
                    self.venue_collector.connect('127.0.0.1', 4001, clientId=8)
                    
                    # API thread başlat
                    api_thread = threading.Thread(target=self.venue_collector.run, daemon=True)
                    api_thread.start()
                    
                    # Bağlantı bekle
                    timeout = 5
                    while not self.venue_collector.connected and timeout > 0:
                        time.sleep(1)
                        timeout -= 1
                    
                    if self.venue_collector.connected:
                        print(f"✅ {self.ticker} venue collector bağlandı!")
                        
                        # Venue data iste
                        ibkr_ticker = polygon_to_ibkr_ticker(self.ticker)
                        contract = Contract()
                        contract.symbol = ibkr_ticker
                        contract.secType = "STK"
                        contract.exchange = "SMART"
                        contract.currency = "USD"
                        
                        req_id = 8000
                        self.venue_collector.symbol_map[req_id] = ibkr_ticker
                        
                        print(f"📊 {self.ticker} Level 2 market depth isteniyor...")
                        # Level 2 market depth iste
                        self.venue_collector.reqMktDepth(req_id, contract, 10, True, [])
                        
                        print(f"⚡ {self.ticker} Tick-by-tick data isteniyor...")
                        # Tick-by-tick iste
                        self.venue_collector.reqTickByTickData(req_id + 10, contract, "Last", 0, True)
                        self.venue_collector.symbol_map[req_id + 10] = ibkr_ticker
                        
                        self.after(0, lambda: self.status_label.config(text="Venue bilgileri otomatik olarak yükleniyor...", foreground="green"))
                        
                        # Periyodik güncelleme başlat
                        self._schedule_venue_updates()
                        
                    else:
                        print(f"❌ {self.ticker} venue collector bağlantı hatası!")
                        self.after(0, lambda: self.status_label.config(text="Venue collector bağlantı hatası!", foreground="red"))
                        
                except Exception as e:
                    print(f"❌ {self.ticker} venue collection hatası: {e}")
                    import traceback
                    traceback.print_exc()
                    self.after(0, lambda: self.status_label.config(text=f"Venue collection hatası: {e}", foreground="red"))
            
            self.venue_thread = threading.Thread(target=connect_and_collect, daemon=True)
            self.venue_thread.start()
            
        except Exception as e:
            print(f"❌ {self.ticker} venue collection başlatma hatası: {e}")
            self.status_label.config(text=f"Venue collection başlatma hatası: {e}", foreground="red")
    
    def _stop_venue_collection(self):
        """Venue data collection durdur"""
        if self.venue_collector:
            try:
                print(f"🛑 {self.ticker} venue collector durduruluyor...")
                self.venue_collector.disconnect()
                self.venue_collector = None
                self.status_label.config(text="Venue data collection durduruldu.", foreground="orange")
            except:
                pass
    
    def _schedule_venue_updates(self):
        """Venue verilerini periyodik olarak güncelle"""
        if self.venue_collector and self.venue_collector.connected:
            self._update_venue_data()
            self.after(2000, self._schedule_venue_updates)  # 2 saniyede bir güncelle
    
    def _update_venue_data(self):
        """Venue verilerini tablolara yansıt - her bid/ask için venue garantisi"""
        if not self.venue_collector or not self.venue_collector.venue_data:
            return
            
        ibkr_ticker = polygon_to_ibkr_ticker(self.ticker)
        if ibkr_ticker not in self.venue_collector.venue_data:
            return
            
        data = self.venue_collector.venue_data[ibkr_ticker]
        
        # Bids ve asks'i sırala
        sorted_bids = sorted(data['bids'].items(), key=lambda x: x[1]['price'], reverse=True)[:5]
        sorted_asks = sorted(data['asks'].items(), key=lambda x: x[1]['price'])[:5]
        
        # Orderbook tablosunu güncelle
        self.ob_table.delete(*self.ob_table.get_children())
        
        print(f"\n📈 {self.ticker} Venue Data Update:")
        print("=" * 50)
        
        for i in range(5):
            bid_data = sorted_bids[i][1] if i < len(sorted_bids) else {}
            ask_data = sorted_asks[i][1] if i < len(sorted_asks) else {}
            
            # Venue bilgilerini garantile - boş olmasın
            bid_venue = bid_data.get('venue', 'SMART') if bid_data else ""
            ask_venue = ask_data.get('venue', 'SMART') if ask_data else ""
            
            # Console'da venue bilgilerini göster
            if bid_data:
                print(f"BID[{i}]: ${bid_data['price']:.2f} x {bid_data['size']} @ {bid_venue}")
            if ask_data:
                print(f"ASK[{i}]: ${ask_data['price']:.2f} x {ask_data['size']} @ {ask_venue}")
            
            self.ob_table.insert("", "end", values=(
                f"{bid_data.get('price', ''):.2f}" if bid_data.get('price') else "",
                f"{bid_data.get('size', '')}" if bid_data.get('size') else "",
                bid_venue,  # Her zaman bir venue değeri
                f"{ask_data.get('price', ''):.2f}" if ask_data.get('price') else "",
                f"{ask_data.get('size', '')}" if ask_data.get('size') else "",
                ask_venue   # Her zaman bir venue değeri
            ))
        
        # Last trades tablosunu güncelle
        self.lt_table.delete(*self.lt_table.get_children())
        
        print("\n⚡ Last Trades:")
        for trade in data['last_trades'][:6]:
            trade_venue = trade.get('venue', 'SMART')  # Trade için de venue garantisi
            print(f"TRADE: ${trade['price']:.2f} x {trade['size']} @ {trade_venue} ({trade['time']})")
            
            self.lt_table.insert("", "end", values=(
                trade.get('time', ''),
                f"{trade.get('price', ''):.2f}" if trade.get('price') else "",
                f"{trade.get('size', '')}" if trade.get('size') else "",
                trade_venue,  # Her zaman bir venue değeri
                trade.get('conditions', '')
            ))
        
        # Status güncelle
        total_venues = len(set([bid.get('venue', 'SMART') for bid in [b[1] for b in sorted_bids]] + 
                              [ask.get('venue', 'SMART') for ask in [a[1] for a in sorted_asks]]))
        self.status_label.config(text=f"Venue bilgileri aktif - {total_venues} farklı venue görüntüleniyor", foreground="green")
    
    def _refresh_data(self):
        """Verileri yenile"""
        print(f"🔄 {self.ticker} verileri yenileniyor...")
        self._fetch_data()
        if self.venue_collector and self.venue_collector.connected:
            self._update_venue_data()
    
    def destroy(self):
        """Pencere kapatılırken venue collector'ı da kapat"""
        print(f"🗑️ {self.ticker} orderbook penceresi kapatılıyor...")
        self._stop_venue_collection()
        super().destroy() 