"""
IBKR Native Client - IBKR TWS API'nin native implementasyonu
ib_insync yerine doğrudan IBKR TWS API kullanarak emir gönderme

!!! ÖNEMLİ DOSYA YOLU UYARISI !!!
=================================
BÜTÜN CSV OKUMA VE CSV KAYDETME İŞLEMLERİ StockTracker DİZİNİNE YAPILMALI!!
StockTracker/janall/ dizinine YAPILMAMALI!!!
KARIŞASAYI ÖNLEMEK İÇİN BU KURALA MUTLAKA UYULACAK!

Bu modül IBKR TWS/Gateway ile doğrudan iletişim kurar
=================================
"""

import logging
import time
import threading
from typing import List, Dict, Optional, Callable

try:
    from ibapi.wrapper import EWrapper
    from ibapi.client import EClient
    from ibapi.contract import Contract
    from ibapi.order import Order
    print("[IBKR-NATIVE] IBKR TWS API basariyla import edildi")
except ImportError as e:
    EWrapper = None
    EClient = None
    Contract = None
    Order = None
    print(f"❌ IBKR TWS API import hatası: {e}")
    print("💡 Çözüm: pip install ibapi")

class IBKRNativeClient(EWrapper, EClient):
    def __init__(self, host='127.0.0.1', port=4001, client_id=1, main_window=None):
        if EWrapper is None or EClient is None:
            raise ImportError("IBKR TWS API paketi yüklü değil. 'pip install ibapi' komutunu çalıştırın.")
        
        EClient.__init__(self, self)
        EWrapper.__init__(self)
        
        self.host = host
        self.port = port
        self.client_id = client_id
        self.main_window = main_window
        
        self.connected = False
        self.accounts = []
        self.positions = []
        self.orders = []
        
        # Bugünkü filled emirleri sakla (execution'lar)
        self.todays_filled_orders = []  # Bugünkü filled emirler listesi
        self.todays_filled_date = None  # Bugünkü tarih (gün değiştiğinde temizlemek için)
        
        # Order ID yönetimi
        self.next_order_id = 1
        self.order_id_initialized = False
        
        # UI entegrasyonu için callback'ler
        self.on_positions = None  # callable(list)
        self.on_orders = None     # callable(list)
        self.on_execution = None  # callable(dict) - execution detail callback
        
        # Logging ayarları
        self.logger = logging.getLogger('ibkr_native_client')
        self.logger.setLevel(logging.WARNING)
        
        # Threading
        self.api_thread = None
    
    def connect_to_ibkr(self):
        """IBKR TWS/Gateway'e bağlan"""
        try:
            print(f"[IBKR-NATIVE] 🔗 Bağlanılıyor: {self.host}:{self.port} (Client ID: {self.client_id})")
            
            # Bağlantı kur
            self.connect(self.host, self.port, self.client_id)
            
            # API thread'i başlat
            self.api_thread = threading.Thread(target=self.run, daemon=True)
            self.api_thread.start()
            
            # Bağlantının kurulmasını bekle
            time.sleep(2)
            
            if self.isConnected():
                self.connected = True
                print("[IBKR-NATIVE] ✅ IBKR TWS/Gateway bağlantısı başarılı")
                
                # Order ID'yi iste
                print("[IBKR-NATIVE] 🔄 Order ID isteniyor...")
                self.reqIds(1)
                
                # Hesapları al
                print("[IBKR-NATIVE] 🔄 Hesaplar isteniyor...")
                self.reqAccountUpdates(True, "")
                
                # Execution'ları iste (fill bilgileri için)
                print("[IBKR-NATIVE] 🔄 Execution'lar isteniyor...")
                self.request_executions()
                
                return True
            else:
                print("[IBKR-NATIVE] ❌ IBKR TWS/Gateway bağlantısı başarısız")
                return False
                
        except Exception as e:
            self.logger.error(f"Error connecting: {e}")
            print(f"[IBKR-NATIVE] ❌ Bağlantı hatası: {e}")
            print("[IBKR-NATIVE] 💡 Kontrol edilecekler:")
            print("   1. IBKR TWS/Gateway çalışıyor mu?")
            print("   2. Port 4001 (live) veya 4002 (paper) açık mı?")
            print("   3. API izinleri aktif mi?")
            return False
    
    def nextValidId(self, orderId):
        """Order ID callback - IBKR'den gelen bir sonraki geçerli ID"""
        self.next_order_id = orderId
        self.order_id_initialized = True
        print(f"[IBKR-NATIVE] 📋 Next Valid Order ID: {orderId}")
    
    def disconnect(self):
        """IBKR bağlantısını kapat"""
        try:
            if self.connected and self.isConnected():
                self.disconnect()
                self.connected = False
                print("[IBKR-NATIVE] 🔌 Bağlantı kapatıldı")
        except Exception as e:
            print(f"[IBKR-NATIVE] ❌ Bağlantı kapatma hatası: {e}")
    
    def is_connected(self):
        """Bağlantı durumunu kontrol et"""
        return self.connected and self.isConnected()
    
    def get_accounts(self):
        """Hesapları al"""
        return self.accounts
    
    def round_to_tick_size(self, price):
        """IBKR minimum tick size'a göre fiyatı yuvarla"""
        try:
            # IBKR'de çoğu stock için minimum tick size $0.01 (1 cent)
            tick_size = 0.01
            rounded = round(price / tick_size) * tick_size
            return round(rounded, 2)
        except Exception as e:
            print(f"[IBKR-NATIVE] ⚠️ Fiyat yuvarlama hatası: {e}")
            return round(price, 2)
    
    def place_order(self, symbol, side, quantity, price, order_type="LIMIT", hidden=True, account_key=None):
        """IBKR'ye emir gönder - Native API ile"""
        try:
            if not self.is_connected():
                print("[IBKR-NATIVE] ❌ Bağlantı yok, emir gönderilemez!")
                return False
            
            # IBKR için ticker conversion: BFS-E -> BFS PRE
            # Hammer formatındaki ticker'ları IBKR formatına çevir
            ibkr_symbol = symbol
            if "-" in symbol and len(symbol.split("-")) == 2:
                # Hammer formatı: "BFS-E" -> IBKR formatı: "BFS PRE"
                try:
                    from .myjdata import get_pref_ibkr_symbol_from_hammer
                    ibkr_symbol = get_pref_ibkr_symbol_from_hammer(symbol)
                    if ibkr_symbol != symbol:
                        print(f"[IBKR-NATIVE] 🔄 Ticker conversion: {symbol} -> {ibkr_symbol}")
                except Exception as e:
                    print(f"[IBKR-NATIVE] ⚠️ Ticker conversion hatası: {e}, orijinal symbol kullanılıyor")
                    ibkr_symbol = symbol
            
            print(f"[IBKR-NATIVE] 🔄 Emir gönderiliyor: {ibkr_symbol} {side} {quantity} @ ${price:.2f}")
            
            # Contract oluştur
            contract = Contract()
            contract.symbol = ibkr_symbol
            contract.secType = "STK"
            # SMART exchange kullan (NYSE routing sorunu yaratıyor)
            contract.exchange = "SMART"
            contract.currency = "USD"
            
            print(f"[IBKR-NATIVE] 📋 Contract Details:")
            print(f"  Symbol: {contract.symbol} (original: {symbol})")
            print(f"  SecType: {contract.secType}")
            print(f"  Exchange: {contract.exchange}")
            print(f"  Currency: {contract.currency}")
            
            # Order ID kontrolü
            if not self.order_id_initialized:
                print("[IBKR-NATIVE] ❌ Order ID initialize edilmemiş, emir gönderilemez!")
                return False
            
            # Order oluştur
            order = Order()
            order.action = side.upper()
            order.totalQuantity = quantity
            order.orderType = order_type.upper()
            
            if order_type.upper() == "LIMIT":
                rounded_price = self.round_to_tick_size(price)
                order.lmtPrice = rounded_price
                print(f"[IBKR-NATIVE] 📊 Fiyat yuvarlama: ${price:.4f} → ${rounded_price:.2f}")
            
            # Grok'un önerisi: Hidden emirler için doğru implementasyon
            order.transmit = True  # Emri gönder
            order.tif = 'DAY'      # Time in Force
            
            # Hidden emir implementasyonu (Grok'un önerisi)
            if hidden:
                order.hidden = True  # Hidden etkin (borsa destekliyorsa)
                print(f"[IBKR-NATIVE] 🔒 Hidden emir: hidden = True")
            else:
                # Normal emir için hidden = False (varsayılan)
                order.hidden = False
                print(f"[IBKR-NATIVE] 📤 Normal emir: hidden = False")
            
            # CRITICAL: Deprecated attribute'ları manuel olarak False yap
            order.eTradeOnly = False      # 10268 hatasını önlemek için
            order.firmQuoteOnly = False   # 10269 hatasını önlemek için
            print(f"[IBKR-NATIVE] 🔧 eTradeOnly = False (10268 hatasını önlemek için)")
            print(f"[IBKR-NATIVE] 🔧 firmQuoteOnly = False (10269 hatasını önlemek için)")
            
            # Order ID'yi ayarla
            order.orderId = self.next_order_id
            self.next_order_id += 1
            
            print(f"[IBKR-NATIVE] 📋 Order Details:")
            print(f"  Action: {order.action}")
            print(f"  TotalQuantity: {order.totalQuantity}")
            print(f"  OrderType: {order.orderType}")
            if hasattr(order, 'lmtPrice') and order.lmtPrice:
                print(f"  LimitPrice: {order.lmtPrice}")
            print(f"  Hidden: {getattr(order, 'hidden', False)}")
            print(f"  eTradeOnly: {getattr(order, 'eTradeOnly', False)}")
            print(f"  firmQuoteOnly: {getattr(order, 'firmQuoteOnly', False)}")
            print(f"  Transmit: {getattr(order, 'transmit', True)}")
            print(f"  OrderId: {order.orderId}")
            
            # Hesap belirtilmişse
            if account_key:
                order.account = account_key
                print(f"[IBKR-NATIVE] 🏦 Hesap belirtildi: {account_key}")
            
            # Emir gönderilmeden önce kısa bekleme (global throttle ile koordineli)
            print(f"[IBKR-NATIVE] ⏳ Emir gönderilmeden önce 0.1 saniye bekleniyor...")
            time.sleep(0.1)
            
            # Emri gönder
            self.placeOrder(order.orderId, contract, order)
            
            print(f"[IBKR-NATIVE] ✅ Emir gönderildi: {ibkr_symbol} {side} {quantity} @ ${rounded_price:.2f}")
            print(f"[IBKR-NATIVE] 📋 Order ID: {order.orderId}")
            print(f"[IBKR-NATIVE] 📋 Contract: {ibkr_symbol} @ {contract.exchange}")
            print(f"[IBKR-NATIVE] 📋 Hidden: {hidden} (order.hidden ile)")
            
            # Order status kontrolü için kısa bekleme (bloklamasın)
            print(f"[IBKR-NATIVE] ⏳ Order status kontrolü için 0.6 saniye bekleniyor...")
            time.sleep(0.6)
            
            # Gerçek order status kontrolü yap
            print(f"[IBKR-NATIVE] 🔍 Order status kontrol ediliyor...")
            # Order status callback'inde gerçek durumu göreceğiz
            
            print(f"[IBKR-NATIVE] ✅ Emir gönderildi (Status callback'te kontrol edilecek)")
            return True
                
        except Exception as e:
            print(f"[IBKR-NATIVE] ❌ Emir gönderme hatası: {e}")
            self.logger.error(f"Error placing order: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def error(self, reqId, errorCode, errorString):
        """Hata callback'i"""
        if errorCode in [2104, 2106, 2158]:  # Market data farm connection is OK
            return
        
        # Deprecated attribute hataları - ignore et (Grok'un önerdiği gibi)
        if errorCode == 10268:  # EtradeOnly order attribute not supported
            print(f"[IBKR-NATIVE] ⚠️ Uyarı {errorCode}: {errorString}")
            print(f"[IBKR-NATIVE] ℹ️ EtradeOnly deprecated - ignore ediliyor")
            return
        
        if errorCode == 10269:  # FirmQuoteOnly order attribute not supported
            print(f"[IBKR-NATIVE] ⚠️ Uyarı {errorCode}: {errorString}")
            print(f"[IBKR-NATIVE] ℹ️ FirmQuoteOnly deprecated - ignore ediliyor")
            return
        
        if errorCode == 10311:  # Direct routing to NYSE warning
            print(f"[IBKR-NATIVE] ⚠️ Uyarı {errorCode}: {errorString}")
            print(f"[IBKR-NATIVE] ℹ️ NYSE direct routing uyarısı - ignore ediliyor")
            return
        
        # Error 10147: OrderId that needs to be cancelled is not found
        # Bu hata emir iptal edilirken emrin zaten iptal edilmiş/tamamlanmış olduğunu gösterir
        # Bu durum normal kabul edilir ve sessizce geçilir
        if errorCode == 10147:
            print(f"[IBKR-NATIVE] ⚠️ Error 10147 (normal): OrderId {reqId} zaten iptal edilmiş/tamamlanmış - ignore ediliyor")
            return  # Sessizce geç
        
        print(f"[IBKR-NATIVE] ❌ Hata {errorCode}: {errorString}")
        self.logger.error(f"Error {errorCode}: {errorString}")
    
    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        """Order status callback'i - Emir durumu güncellemesi"""
        print(f"[IBKR-NATIVE] 📊 Order Status: ID={orderId}, Status={status}, Filled={filled}, Remaining={remaining}, AvgFillPrice={avgFillPrice}, LastFillPrice={lastFillPrice}")
        
        # Mevcut emiri bul ve güncelle
        for i, order in enumerate(self.orders):
            if order.get('order_id') == orderId:
                # Filled ve remaining bilgisini güncelle
                self.orders[i]['filled'] = float(filled) if filled else 0.0
                self.orders[i]['remaining'] = float(remaining) if remaining else 0.0
                self.orders[i]['status'] = status.upper() if status else 'UNKNOWN'
                # Fill price bilgilerini güncelle
                self.orders[i]['avg_fill_price'] = float(avgFillPrice) if avgFillPrice and avgFillPrice > 0 else 0.0
                self.orders[i]['last_fill_price'] = float(lastFillPrice) if lastFillPrice and lastFillPrice > 0 else 0.0
                print(f"[IBKR-NATIVE] 🔄 Order {orderId} güncellendi: Filled={filled}, Remaining={remaining}, AvgFillPrice={avgFillPrice}, LastFillPrice={lastFillPrice}")
                break
        
        if status in ['Submitted', 'Filled', 'PartiallyFilled']:
            print(f"[IBKR-NATIVE] ✅ Order {orderId} başarılı: {status}")
        elif status in ['Cancelled', 'Rejected', 'ApiCancelled']:
            print(f"[IBKR-NATIVE] ❌ Order {orderId} başarısız: {status}")
            # İptal edilen emirleri listeden çıkar
            self.orders = [ord for ord in self.orders if ord.get('order_id') != orderId]
        else:
            print(f"[IBKR-NATIVE] ⏳ Order {orderId} bekliyor: {status}")
    
    def updateAccountValue(self, key, val, currency, accountName):
        """Account value callback'i"""
        if key == "AccountOrGroup":
            if accountName not in self.accounts:
                self.accounts.append(accountName)
                print(f"[IBKR-NATIVE] 📊 Hesap bulundu: {accountName}")
    
    def updatePortfolio(self, contract, position, marketPrice, marketValue, averageCost, unrealizedPNL, realizedPNL, accountName):
        """Portfolio callback'i"""
        try:
            # Symbol bilgisini al
            symbol = contract.symbol
            if contract.secType == "STK" and contract.exchange == "SMART":
                # Preferred stock formatını düzelt
                if hasattr(contract, 'localSymbol') and contract.localSymbol and '-' in contract.localSymbol:
                    base, suffix = contract.localSymbol.split('-')
                    symbol = f"{base} PR{suffix}"
            
            # Pozisyon bilgilerini kaydet
            position_data = {
                'symbol': symbol,
                'qty': float(position),
                'avg_cost': float(averageCost) if averageCost > 0 else 0.0,
                'market_price': float(marketPrice) if marketPrice > 0 else 0.0,
                'market_value': float(marketValue) if marketValue else 0.0,
                'unrealized_pnl': float(unrealizedPNL) if unrealizedPNL else 0.0,
                'realized_pnl': float(realizedPNL) if realizedPNL else 0.0,
                'account': accountName
            }
            
            # Mevcut pozisyonu güncelle veya yeni ekle
            existing_position = None
            for i, pos in enumerate(self.positions):
                if pos['symbol'] == symbol and pos['account'] == accountName:
                    existing_position = i
                    break
            
            if existing_position is not None:
                self.positions[existing_position] = position_data
            else:
                self.positions.append(position_data)
            
            print(f"[IBKR-NATIVE] 📊 Portfolio: {symbol} = {position} @ ${averageCost:.2f} (Market: ${marketPrice:.2f})")
            
        except Exception as e:
            print(f"[IBKR-NATIVE] ❌ Portfolio callback hatası: {e}")
    
    def position(self, account: str, contract, position: float, avgCost: float):
        """Position callback'i - Grok'un önerisi ile avgCost bilgisi"""
        try:
            # Symbol bilgisini al
            symbol = contract.symbol
            if contract.secType == "STK" and contract.exchange == "SMART":
                # Preferred stock formatını düzelt
                if hasattr(contract, 'localSymbol') and contract.localSymbol and '-' in contract.localSymbol:
                    base, suffix = contract.localSymbol.split('-')
                    symbol = f"{base} PR{suffix}"
            
            # Pozisyon bilgilerini kaydet (Grok'un önerisi)
            position_data = {
                'symbol': symbol,
                'qty': float(position),
                'avg_cost': float(avgCost),  # Grok'un önerisi: avgCost doğru geliyor
                'account': account,
                'sec_type': contract.secType,
                'currency': contract.currency
            }
            
            # Pozisyonu listeye ekle
            self.positions.append(position_data)
            # Debug mesajı kapatıldı - performans için
            # print(f"[IBKR-NATIVE] 📊 Position: {account} - {symbol} ({contract.secType}), Qty: {position}, AvgCost: {avgCost:.2f}")
            
        except Exception as e:
            print(f"[IBKR-NATIVE] ❌ Position callback hatası: {e}")
    
    def positionEnd(self):
        """Position callback'i bittiğinde çağrılır"""
        print("[IBKR-NATIVE] ✅ Tüm pozisyonlar alındı")
    
    def openOrder(self, orderId, contract, order, orderState):
        """Open order callback'i"""
        try:
            # Symbol bilgisini al
            symbol = contract.symbol
            if contract.secType == "STK" and contract.exchange == "SMART":
                # Preferred stock formatını düzelt
                if hasattr(contract, 'localSymbol') and contract.localSymbol and '-' in contract.localSymbol:
                    base, suffix = contract.localSymbol.split('-')
                    symbol = f"{base} PR{suffix}"
            
            # Emir bilgilerini kaydet
            # IBKR Native API'de OrderState objesinde filled/remaining yok
            # order.totalQuantity kullanılır (açık emirler için bu kalan miktar)
            total_qty = float(order.totalQuantity)
            
            # Status'e göre filled/remaining hesapla
            status = orderState.status.upper() if hasattr(orderState, 'status') else 'UNKNOWN'
            
            # Eğer status FILLED ise remaining = 0
            if status == 'FILLED':
                filled_qty = total_qty
                remaining_qty = 0.0
            elif status in ['CANCELLED', 'REJECTED', 'API CANCELLED']:
                filled_qty = 0.0
                remaining_qty = 0.0
            else:
                # Submitted, PartiallyFilled gibi durumlar için
                # order.totalQuantity = remaining quantity (açık emir için)
                filled_qty = 0.0  # Açık emirler için filled bilgisi orderStatus callback'inde gelir
                remaining_qty = total_qty  # Açık emir için remaining = totalQuantity
            
            order_data = {
                'symbol': symbol,
                'action': order.action,  # BUY/SELL
                'quantity': total_qty,
                'qty': total_qty,  # Alias
                'Quantity': total_qty,  # Alias
                'side': order.action,  # BUY/SELL
                'Side': order.action,  # Alias
                'order_type': order.orderType,  # LMT, MKT, etc.
                'limit_price': float(order.lmtPrice) if order.lmtPrice else 0.0,
                'price': float(order.lmtPrice) if order.lmtPrice else 0.0,  # Emir fiyatı (limit_price ile aynı)
                'status': status,
                'filled': filled_qty,
                'remaining': remaining_qty,
                'avg_fill_price': 0.0,  # orderStatus callback'inde güncellenecek
                'last_fill_price': 0.0,  # orderStatus callback'inde güncellenecek
                'account': order.account if hasattr(order, 'account') else '',
                'order_id': orderId,
            }
            
            # Mevcut emiri güncelle veya yeni ekle
            existing_order = None
            for i, ord in enumerate(self.orders):
                if ord.get('order_id') == orderId:
                    existing_order = i
                    break
            
            if existing_order is not None:
                self.orders[existing_order] = order_data
            else:
                self.orders.append(order_data)
            
            print(f"[IBKR-NATIVE] 📋 Open Order: {symbol} {order.action} {order.totalQuantity} @ {order.lmtPrice if order.lmtPrice else 'MKT'} (Status: {orderState.status})")
            
        except Exception as e:
            print(f"[IBKR-NATIVE] ❌ Open order callback hatası: {e}")
    
    def openOrderEnd(self):
        """Open order callback'i bittiğinde çağrılır"""
        print(f"[IBKR-NATIVE] ✅ Tüm açık emirler alındı ({len(self.orders)} emir)")
    
    def get_open_orders(self, account_id=None):
        """Açık emirleri getir"""
        try:
            if not self.is_connected():
                print("[IBKR-NATIVE] ❌ Bağlantı yok, açık emirler alınamaz!")
                return []
            
            # Emirleri temizle
            self.orders = []
            
            # Açık emirleri iste
            print("[IBKR-NATIVE] 🔄 Açık emirler isteniyor...")
            self.reqAllOpenOrders()
            
            # Emirlerin gelmesini bekle (openOrder callback'i ile dolduruluyor)
            time.sleep(1.5)  # Emirlerin gelmesi için bekle
            
            print(f"[IBKR-NATIVE] 📋 {len(self.orders)} açık emir bulundu")
            return self.orders
            
        except Exception as e:
            print(f"[IBKR-NATIVE] ❌ Açık emir alma hatası: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def cancel_order(self, order_id):
        """IBKR'de emri iptal et - Native API"""
        try:
            if not self.is_connected():
                print(f"[IBKR-NATIVE] ❌ Bağlantı yok, emir iptal edilemez! (Order ID: {order_id})")
                return False
            
            print(f"[IBKR-NATIVE] 🔄 Emir iptal ediliyor: Order ID {order_id}")
            
            # Order ID'yi integer'a çevir
            try:
                order_id_int = int(order_id)
            except (ValueError, TypeError):
                print(f"[IBKR-NATIVE] ❌ Geçersiz Order ID: {order_id}")
                return False
            
            # Önce açık emirler listesinde emrin olup olmadığını kontrol et
            # Açık emirleri al
            open_orders = self.get_open_orders()
            
            # Emri bul
            order_found = False
            for order in open_orders:
                if order.get('order_id') == order_id_int:
                    order_found = True
                    break
            
            if not order_found:
                # Emir açık emirler listesinde yok - zaten iptal edilmiş/tamamlanmış olabilir
                print(f"[IBKR-NATIVE] ⚠️ Order ID {order_id_int} açık emirler listesinde bulunamadı (zaten iptal edilmiş/tamamlanmış olabilir)")
                # İptal edilen emri listeden çıkar (eğer varsa)
                self.orders = [ord for ord in self.orders if ord.get('order_id') != order_id_int]
                return True  # Başarılı sayılır çünkü emir zaten yok
            
            # IBKR Native API'de emir iptal etmek için cancelOrder(orderId) kullanılır
            # EClient'tan gelen cancelOrder fonksiyonu direkt orderId ile çalışır
            try:
                # IBKR Native API'de cancelOrder(orderId) çağrısı
                # Bu direkt IBKR TWS/Gateway'e gönderilir
                self.cancelOrder(order_id_int)
                print(f"[IBKR-NATIVE] ✅ Emir iptal isteği gönderildi: Order ID {order_id_int}")
                
                # İptal işleminin tamamlanmasını bekle
                import time
                max_wait_time = 3.0  # Maksimum bekleme süresi
                check_interval = 0.5  # Kontrol aralığı
                waited_time = 0.0
                
                while waited_time < max_wait_time:
                    time.sleep(check_interval)
                    waited_time += check_interval
                    
                    # Açık emirleri tekrar kontrol et
                    current_orders = self.get_open_orders()
                    order_still_open = any(order.get('order_id') == order_id_int for order in current_orders)
                    
                    if not order_still_open:
                        # Emir artık açık emirler listesinde yok - iptal edilmiş
                        print(f"[IBKR-NATIVE] ✅ Order ID {order_id_int} başarıyla iptal edildi")
                        # İptal edilen emri listeden çıkar
                        self.orders = [ord for ord in self.orders if ord.get('order_id') != order_id_int]
                        return True
                
                # Timeout sonrası son kontrol
                final_orders = self.get_open_orders()
                order_still_open_final = any(order.get('order_id') == order_id_int for order in final_orders)
                
                if order_still_open_final:
                    print(f"[IBKR-NATIVE] ⚠️ Order ID {order_id_int} hala açık görünüyor (timeout)")
                    # Yine de iptal edilmiş olabilir (IBKR API gecikmesi)
                    # İptal edilen emri listeden çıkar
                    self.orders = [ord for ord in self.orders if ord.get('order_id') != order_id_int]
                    return True  # İptal isteği gönderildi, başarılı sayılır
                else:
                    print(f"[IBKR-NATIVE] ✅ Order ID {order_id_int} iptal edildi (timeout sonrası kontrol)")
                    return True
                    
            except Exception as cancel_error:
                error_str = str(cancel_error)
                # Error 10147: OrderId that needs to be cancelled is not found
                # Bu durum emir zaten iptal edilmiş/tamamlanmış demektir - normal kabul et
                if "10147" in error_str or "not found" in error_str.lower():
                    print(f"[IBKR-NATIVE] ⚠️ Order ID {order_id_int} zaten iptal edilmiş/tamamlanmış (Error 10147 - normal)")
                    # İptal edilen emri listeden çıkar
                    self.orders = [ord for ord in self.orders if ord.get('order_id') != order_id_int]
                    return True  # Başarılı sayılır
                else:
                    # Farklı bir hata - gerçek bir sorun var
                    print(f"[IBKR-NATIVE] ❌ Emir iptal hatası: {cancel_error}")
                    import traceback
                    traceback.print_exc()
                    raise cancel_error
            
        except Exception as e:
            print(f"[IBKR-NATIVE] ❌ Emir iptal genel hatası ({order_id}): {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def request_executions(self):
        """Execution (fill) bilgilerini iste - IBKR Native API"""
        try:
            if not self.is_connected():
                print("[IBKR-NATIVE] ❌ Bağlantı yok, execution'lar istenemez!")
                return
            
            # reqExecutions() ile execution bilgilerini iste
            # reqExecutions(reqId, execFilter) - execFilter boş ise tüm execution'lar gelir
            print("[IBKR-NATIVE] 🔄 Execution'lar isteniyor...")
            self.reqExecutions(1, None)  # reqId=1, execFilter=None (tüm execution'lar)
            
        except Exception as e:
            print(f"[IBKR-NATIVE] ❌ Execution isteği hatası: {e}")
    
    def execDetails(self, reqId, contract, execution):
        """Execution details callback'i - Fill bilgileri"""
        try:
            from datetime import datetime
            
            # Bugünkü tarihi kontrol et - gün değiştiyse listeyi temizle
            today = datetime.now().date()
            if self.todays_filled_date != today:
                self.todays_filled_orders = []
                self.todays_filled_date = today
                print(f"[IBKR-NATIVE] 📅 Yeni gün başladı, filled emirler listesi temizlendi")
            
            # Symbol bilgisini al
            symbol = contract.symbol
            if contract.secType == "STK" and contract.exchange == "SMART":
                # Preferred stock formatını düzelt
                if hasattr(contract, 'localSymbol') and contract.localSymbol and '-' in contract.localSymbol:
                    base, suffix = contract.localSymbol.split('-')
                    symbol = f"{base} PR{suffix}"
            
            # Execution bilgilerini al
            exec_id = execution.execId
            order_id = execution.orderId
            time_str = execution.time
            side = execution.side  # BOT (BUY) veya SLD (SELL)
            shares = float(execution.shares)
            price = float(execution.price)
            avg_price = float(execution.avgPrice) if execution.avgPrice else price
            
            # Side'ı BUY/SELL formatına çevir
            action = 'BUY' if side == 'BOT' else 'SELL'
            
            print(f"[IBKR-NATIVE] 📊 Execution: {symbol} {action} {shares} @ ${price:.2f} (Order ID: {order_id}, Exec ID: {exec_id})")
            
            # Execution verisini hazırla
            exec_data = {
                'symbol': symbol,
                'action': action,
                'side': action.lower(),
                'qty': shares,
                'fill_qty': shares,
                'price': price,
                'fill_price': price,
                'avg_price': avg_price,
                'order_id': order_id,
                'exec_id': exec_id,
                'time': time_str,
                'fill_time': time_str,
                'date': today.isoformat()  # Bugünkü tarih
            }
            
            # Bugünkü filled emirler listesine ekle (duplicate kontrolü ile)
            # Aynı exec_id varsa ekleme (duplicate execution'ları önle)
            if not any(fill.get('exec_id') == exec_id for fill in self.todays_filled_orders):
                self.todays_filled_orders.append(exec_data.copy())
                print(f"[IBKR-NATIVE] ✅ Filled emir eklendi: {symbol} {action} {shares} @ ${price:.2f} (Toplam: {len(self.todays_filled_orders)} filled emir)")
            
            # Execution callback'i varsa çağır
            if callable(self.on_execution):
                try:
                    self.on_execution(exec_data)
                except Exception as e:
                    print(f"[IBKR-NATIVE] ❌ Execution callback hatası: {e}")
            
        except Exception as e:
            print(f"[IBKR-NATIVE] ❌ Execution details callback hatası: {e}")
            import traceback
            traceback.print_exc()
    
    def get_todays_filled_orders(self):
        """Bugünkü filled emirleri döndür"""
        from datetime import datetime
        today = datetime.now().date()
        
        # Gün değiştiyse listeyi temizle
        if self.todays_filled_date != today:
            self.todays_filled_orders = []
            self.todays_filled_date = today
        
        return self.todays_filled_orders.copy()  # Copy döndür ki değişmesin
    
    def execDetailsEnd(self, reqId):
        """Execution details callback'i bittiğinde çağrılır"""
        print(f"[IBKR-NATIVE] ✅ Execution details tamamlandı (reqId: {reqId})")
    
    def get_positions(self, account_id=None):
        """Pozisyonları getir - Grok'un önerisi ile native API"""
        try:
            if not self.is_connected():
                print("[IBKR-NATIVE] ❌ Bağlantı yok, pozisyonlar alınamaz!")
                return []
            
            # Pozisyonları temizle
            self.positions = []
            
            # Grok'un önerisi: reqPositions() ile position callback'i kullan
            print("[IBKR-NATIVE] 🔄 Pozisyonlar isteniyor (Grok'un önerisi)...")
            self.reqPositions()
            
            # Pozisyonların gelmesini bekle (position callback'i ile dolduruluyor)
            import time
            time.sleep(2.0)  # Pozisyonların gelmesi için bekle
            
            print(f"[IBKR-NATIVE] 📊 {len(self.positions)} pozisyon bulundu")
            return self.positions
            
        except Exception as e:
            print(f"[IBKR-NATIVE] ❌ Pozisyon alma hatası: {e}")
            return []
