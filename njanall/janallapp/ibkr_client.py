"""
IBKR Client - Interactive Brokers API entegrasyonu (ib_insync kullanarak)
Bu modül IBKR TWS/Gateway ile bağlantı kurar ve pozisyon/emir verilerini alır

!!! ÖNEMLİ DOSYA YOLU UYARISI !!!
=================================
BÜTÜN CSV OKUMA VE CSV KAYDETME İŞLEMLERİ StockTracker DİZİNİNE YAPILMALI!!
StockTracker/janall/ dizinine YAPILMAMALI!!!
KARIŞASAYI ÖNLEMEK İÇİN BU KURALA MUTLAKA UYULACAK!

Bu modül IBKR TWS/Gateway ile iletişim kurar
=================================
"""

import logging
import time
from typing import List, Dict, Optional, Callable

try:
    import ib_async
    from ib_async import IB, util
    from ib_async.contract import Stock
    from ib_async.objects import Position
    from ib_async.order import LimitOrder, MarketOrder
    # Order'ı farklı yerden import etmeye çalış
    try:
        from ib_async.objects import Order
    except ImportError:
        from ib_async.order import Order
    print("[IBKR] ib_async basariyla import edildi")
except ImportError as e:
    IB = None
    util = None
    Stock = None
    Position = None
    Order = None
    LimitOrder = None
    MarketOrder = None
    print(f"❌ ib_async import hatası: {e}")
    print("💡 Çözüm: pip install ib_async")

class IBKRClient:
    def __init__(self, host='127.0.0.1', port=4001, client_id=1, main_window=None):
        if IB is None:
            raise ImportError("ib_async paketi yüklü değil. 'pip install ib_async' komutunu çalıştırın.")
        
        self.host = host
        self.port = port
        self.client_id = client_id
        self.main_window = main_window
        
        self.ib = IB()
        self.connected = False
        self.accounts = []
        self.positions = []
        self.orders = []
        
        # Order ID yönetimi
        self.next_order_id = 1
        self.order_id_initialized = False
        
        # UI entegrasyonu için callback'ler
        self.on_positions = None  # callable(list)
        self.on_orders = None     # callable(list)
        
        # Logging ayarları
        self.logger = logging.getLogger('ibkr_client')
        self.logger.setLevel(logging.WARNING)
    
    def connect_to_ibkr(self):
        """IBKR TWS/Gateway'e bağlan"""
        try:
            print(f"[IBKR] 🔗 Bağlanılıyor: {self.host}:{self.port} (Client ID: {self.client_id})")
            
            # Bağlantı kur
            self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=15)
            
            if self.ib.isConnected():
                self.connected = True
                print("[IBKR] ✅ IBKR TWS/Gateway bağlantısı başarılı")
                
                # Order ID callback'i ayarla
                self.ib.nextValidIdEvent += self.on_next_valid_id
                
                # Hesapları al
                print("[IBKR] 🔄 Hesaplar isteniyor...")
                account_values = self.ib.accountValues()
                self.accounts = list(set([av.account for av in account_values]))
                print(f"[IBKR] 📊 Hesaplar alındı: {self.accounts}")
                
                # Order ID'yi otomatik olarak başlat (ib_insync otomatik yönetir)
                print("[IBKR] 🔄 Order ID otomatik olarak başlatılıyor...")
                self.next_order_id = 1  # Başlangıç değeri
                self.order_id_initialized = True
                print(f"[IBKR] ✅ Order ID başlatıldı: {self.next_order_id}")
                
                return True
            else:
                print("[IBKR] ❌ IBKR TWS/Gateway bağlantısı başarısız")
                return False
                
        except Exception as e:
            self.logger.error(f"Error connecting: {e}")
            print(f"[IBKR] ❌ Bağlantı hatası: {e}")
            print("[IBKR] 💡 Kontrol edilecekler:")
            print("   1. IBKR TWS/Gateway çalışıyor mu?")
            print("   2. Port 4001 (live) veya 4002 (paper) açık mı?")
            print("   3. API izinleri aktif mi?")
            return False
    
    def on_next_valid_id(self, order_id):
        """Order ID callback - IBKR'den gelen bir sonraki geçerli ID"""
        # IBKR Gateway'den gelen gerçek Order ID'yi kullan
        self.next_order_id = order_id
        self.order_id_initialized = True
        print(f"[IBKR] 📋 Next Valid Order ID: {order_id} (Set as current)")
    
    def disconnect(self):
        """IBKR bağlantısını kapat"""
        try:
            if self.connected and self.ib.isConnected():
                self.ib.disconnect()
                self.connected = False
                print("[IBKR] 🔌 Bağlantı kapatıldı")
        except Exception as e:
            print(f"[IBKR] ❌ Bağlantı kapatma hatası: {e}")
    
    def is_connected(self):
        """Bağlantı durumunu kontrol et"""
        connected = self.connected and self.ib.isConnected()
        if connected and not self.order_id_initialized:
            print("[IBKR] ⚠️ Bağlantı var ama Order ID initialize edilmemiş!")
            # Order ID'yi hemen başlat
            self.next_order_id = 1
            self.order_id_initialized = True
            print(f"[IBKR] ✅ Order ID acil başlatıldı: {self.next_order_id}")
        return connected
    
    def get_accounts(self):
        """Hesapları al"""
        return self.accounts
    
    def get_positions(self, account_id=None):
        """Pozisyonları al"""
        try:
            if not self.is_connected():
                print("[IBKR] ❌ Bağlantı yok")
                return []
            
            print("[IBKR] 🔄 Pozisyonlar isteniyor...")
            
            # Pozisyonları al
            positions = self.ib.positions()
            
            # Pozisyon listesini temizle
            self.positions = []
            
            # Portfolio bilgilerini de iste (averageCost için)
            print("[IBKR] 🔄 Portfolio bilgileri isteniyor...")
            self.ib.reqPositions()
            
            for pos in positions:
                try:
                    # Contract bilgilerini al
                    symbol = pos.contract.symbol
                    if pos.contract.secType == "STK" and pos.contract.exchange == "SMART":
                        # Preferred stock formatını düzelt
                        if hasattr(pos.contract, 'localSymbol') and pos.contract.localSymbol and '-' in pos.contract.localSymbol:
                            base, suffix = pos.contract.localSymbol.split('-')
                            symbol = f"{base} PR{suffix}"
                    
                    # ib_insync Position objesinin doğru attribute'larını kullan
                    position_data = {
                        'symbol': symbol,
                        'qty': float(pos.position),
                        'avg_cost': float(getattr(pos, 'averageCost', 0)) if getattr(pos, 'averageCost', 0) > 0 else 0.0,
                        'account': pos.account,
                        'market_price': float(getattr(pos, 'marketPrice', 0)) if getattr(pos, 'marketPrice', 0) > 0 else 0.0,
                        'market_value': float(getattr(pos, 'marketValue', 0)) if getattr(pos, 'marketValue', 0) else 0.0,
                        'unrealized_pnl': float(getattr(pos, 'unrealizedPNL', 0)) if getattr(pos, 'unrealizedPNL', 0) else 0.0,
                        'realized_pnl': float(getattr(pos, 'realizedPNL', 0)) if getattr(pos, 'realizedPNL', 0) else 0.0,
                        'raw_data': {
                            'contract': pos.contract,
                            'position': pos.position,
                            'averageCost': getattr(pos, 'averageCost', 0),
                            'marketPrice': getattr(pos, 'marketPrice', 0),
                            'marketValue': getattr(pos, 'marketValue', 0),
                            'unrealizedPNL': getattr(pos, 'unrealizedPNL', 0),
                            'realizedPNL': getattr(pos, 'realizedPNL', 0)
                        }
                    }
                    
                    # Pozisyonu listeye ekle
                    self.positions.append(position_data)
                    avg_cost = getattr(pos, 'averageCost', 0)
                    # print(f"[IBKR] ✅ Position added: {symbol} = {pos.position} @ ${avg_cost}")
                    
                except Exception as e:
                    print(f"[IBKR] ❌ Error processing position: {e}")
                    self.logger.error(f"Error processing position: {e}")
            
            print(f"[IBKR] 📊 Toplam {len(self.positions)} pozisyon bulundu")
            
            # Callback'i çağır
            if callable(self.on_positions):
                self.on_positions(self.positions)
            
            return self.positions
            
        except Exception as e:
            print(f"[IBKR] ❌ Error getting positions: {e}")
            self.logger.error(f"Error getting positions: {e}")
            return []
    
    def get_orders(self, account_id=None):
        """Emirleri al"""
        try:
            if not self.is_connected():
                print("[IBKR] ❌ Bağlantı yok")
                return []
            
            print("[IBKR] 🔄 Emirler isteniyor...")
            
            # Açık emirleri al
            open_orders = self.ib.reqAllOpenOrders()
            
            # Emir listesini temizle
            self.orders = []
            
            for order in open_orders:
                try:
                    # Contract bilgilerini al
                    symbol = order.contract.symbol
                    if order.contract.secType == "STK" and order.contract.exchange == "SMART":
                        # Preferred stock formatını düzelt
                        if hasattr(order.contract, 'localSymbol') and order.contract.localSymbol and '-' in order.contract.localSymbol:
                            base, suffix = order.contract.localSymbol.split('-')
                            symbol = f"{base} PR{suffix}"
                    
                    order_data = {
                        'symbol': symbol,
                        'action': order.order.action,  # BUY/SELL
                        'quantity': float(order.order.totalQuantity),
                        'order_type': order.order.orderType,  # LMT, MKT, etc.
                        'limit_price': float(order.order.lmtPrice) if order.order.lmtPrice else 0.0,
                        'status': order.orderStatus.status,  # Submitted, Filled, etc.
                        'filled': float(order.orderStatus.filled),
                        'remaining': float(order.orderStatus.remaining),
                        'account': order.order.account,
                        'order_id': order.order.orderId,
                        'raw_data': {
                            'contract': order.contract,
                            'order': order.order,
                            'orderStatus': order.orderStatus
                        }
                    }
                    
                    # Emiri listeye ekle
                    self.orders.append(order_data)
                    print(f"[IBKR] ✅ Order added: {symbol} {order.order.action} {order.order.totalQuantity} @ {order.order.lmtPrice}")
                    
                except Exception as e:
                    print(f"[IBKR] ❌ Error processing order: {e}")
                    self.logger.error(f"Error processing order: {e}")
            
            print(f"[IBKR] 📊 Toplam {len(self.orders)} emir bulundu")
            
            # Callback'i çağır
            if callable(self.on_orders):
                self.on_orders(self.orders)
            
            return self.orders
            
        except Exception as e:
            print(f"[IBKR] ❌ Error getting orders: {e}")
            self.logger.error(f"Error getting orders: {e}")
            return []
    
    def get_positions_direct(self):
        """Pozisyonları doğrudan al (callback olmadan)"""
        return self.get_positions()
    
    def get_orders_direct(self):
        """Emirleri doğrudan al (callback olmadan)"""
        return self.get_orders()
    
    def set_positions_callback(self, callback):
        """Pozisyon callback'ini ayarla"""
        self.on_positions = callback
    
    def round_to_tick_size(self, price):
        """IBKR minimum tick size'a göre fiyatı yuvarla"""
        try:
            # IBKR'de çoğu stock için minimum tick size $0.01 (1 cent)
            # Preferred stock'lar için genellikle $0.01
            tick_size = 0.01
            
            # Fiyatı tick size'a göre yuvarla
            rounded = round(price / tick_size) * tick_size
            
            # En az 2 ondalık basamak göster
            return round(rounded, 2)
            
        except Exception as e:
            print(f"[IBKR] ⚠️ Fiyat yuvarlama hatası: {e}")
            # Hata durumunda orijinal fiyatı 2 ondalık basamakla döndür
            return round(price, 2)
    
    def place_order(self, symbol, side, quantity, price, order_type="LIMIT", hidden=True, account_key=None):
        """IBKR'ye emir gönder - PMT PRC formatında"""
        try:
            if not self.is_connected():
                print("[IBKR] ❌ Bağlantı yok, emir gönderilemez!")
                return False
            
            print(f"[IBKR] 🔄 Emir gönderiliyor: {symbol} {side} {quantity} @ ${price:.2f}")
            
            # Symbol'ü olduğu gibi kullan (PMT PRC formatında)
            # IBKR'de preferred stock'lar için doğru format
            ibkr_symbol = symbol  # PMT PRC olarak kalacak
            
            # Contract oluştur - IBKR'ye özel ayarlar (daha detaylı)
            contract = Stock(ibkr_symbol, 'SMART', 'USD')
            
            # Contract detaylarını yazdır
            print(f"[IBKR] 📋 Contract Details:")
            print(f"  Symbol: {contract.symbol}")
            print(f"  SecType: {contract.secType}")
            print(f"  Exchange: {contract.exchange}")
            print(f"  Currency: {contract.currency}")
            
            # Contract'ı IBKR'de doğrula (geçici olarak devre dışı - ard arda emir gönderme sorunu için)
            print(f"[IBKR] ⚠️ Contract doğrulama geçici olarak devre dışı (ard arda emir gönderme sorunu için)")
            # Contract doğrulama kısmı geçici olarak kaldırıldı
            
            # Order ID kontrolü (Otahaf'ta yok, kaldırıldı)
            # Otahaf'ta Order ID kontrolü yok, ib_insync otomatik yönetiyor
            
            # Order oluştur - ib_async ile hidden emirler destekleniyor!
            if order_type.upper() == "LIMIT":
                # IBKR minimum tick size'a göre fiyatı yuvarla
                rounded_price = self.round_to_tick_size(price)
                # IBKR'de hidden emirler için displayQuantity kullanılıyor
                if hidden:
                    # Hidden emir: displayQuantity = 0 (görünmez)
                    order = LimitOrder(side.upper(), quantity, rounded_price, tif='DAY')
                    order.displayQuantity = 0  # Hidden emir!
                    print(f"[IBKR] 📊 Fiyat yuvarlama: ${price:.4f} → ${rounded_price:.2f}")
                    print(f"[IBKR] 🔒 Hidden emir: displayQuantity = 0")
                else:
                    # Normal emir: displayQuantity = quantity (görünür)
                    order = LimitOrder(side.upper(), quantity, rounded_price, tif='DAY')
                    order.displayQuantity = quantity  # Normal emir
                    print(f"[IBKR] 📊 Fiyat yuvarlama: ${price:.4f} → ${rounded_price:.2f}")
                    print(f"[IBKR] 📤 Normal emir: displayQuantity = {quantity}")
            elif order_type.upper() == "MARKET":
                order = MarketOrder(side.upper(), quantity)
            else:
                print(f"[IBKR] ❌ Desteklenmeyen emir türü: {order_type}")
                return False
            
            # Otahaf'ta Order ID yönetimi yok, ib_insync otomatik yönetiyor
            
            # Otahaf'taki gibi basit gönderim
            self.ib.placeOrder(contract, order)
            print(f"[IBKR] ✅ Emir gönderildi: {symbol} {side} {quantity} @ ${rounded_price:.2f}")
            print(f"[IBKR] 📋 Hidden: {hidden} (displayQuantity ile)")
            
            return True
                
        except Exception as e:
            print(f"[IBKR] ❌ Emir gönderme hatası: {e}")
            self.logger.error(f"Error placing order: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def updatePortfolio(self, contract, position, marketPrice, marketValue, averageCost, unrealizedPNL, realizedPNL, accountName):
        """Portfolio callback'i - averageCost bilgisi için"""
        try:
            # Symbol bilgisini al
            symbol = contract.symbol
            if contract.secType == "STK" and contract.exchange == "SMART":
                # Preferred stock formatını düzelt
                if hasattr(contract, 'localSymbol') and contract.localSymbol and '-' in contract.localSymbol:
                    base, suffix = contract.localSymbol.split('-')
                    symbol = f"{base} PR{suffix}"
            
            # Mevcut pozisyonu güncelle
            for pos in self.positions:
                if pos['symbol'] == symbol and pos['account'] == accountName:
                    pos['avg_cost'] = float(averageCost) if averageCost > 0 else 0.0
                    pos['market_price'] = float(marketPrice) if marketPrice > 0 else 0.0
                    pos['market_value'] = float(marketValue) if marketValue else 0.0
                    pos['unrealized_pnl'] = float(unrealizedPNL) if unrealizedPNL else 0.0
                    pos['realized_pnl'] = float(realizedPNL) if realizedPNL else 0.0
                    print(f"[IBKR] 📊 Portfolio updated: {symbol} = {position} @ ${averageCost:.2f} (Market: ${marketPrice:.2f})")
                    break
            
        except Exception as e:
            print(f"[IBKR] ❌ Portfolio callback hatası: {e}")
            self.logger.error(f"Portfolio callback error: {e}")
    
    def cancel_order(self, order_id):
        """IBKR'de emri iptal et - ib_insync"""
        try:
            if not self.is_connected():
                print(f"[IBKR] ❌ Bağlantı yok, emir iptal edilemez! (Order ID: {order_id})")
                return False
            
            print(f"[IBKR] 🔄 Emir iptal ediliyor: Order ID {order_id}")
            
            # ib_insync'te açık emirleri al - openTrades() kullan (reqAllOpenOrders yerine)
            # openTrades() mevcut açık emirleri döndürür
            try:
                open_trades = self.ib.openTrades()
            except Exception as e:
                print(f"[IBKR] ⚠️ Açık emirler alınamadı: {e}")
                open_trades = []
            
            # Order ID'ye göre emri bul
            target_trade = None
            for trade in open_trades:
                if trade.order.orderId == int(order_id):
                    target_trade = trade
                    break
            
            if target_trade is None:
                # Emir bulunamadı - zaten iptal edilmiş veya tamamlanmış olabilir
                print(f"[IBKR] ⚠️ Order ID {order_id} açık emirler listesinde bulunamadı (zaten iptal edilmiş/tamamlanmış olabilir)")
                # Ama emir hala hesapta görünüyorsa, direkt cancelOrder dene
                # IBKR API'de direkt cancelOrder(orderId) çağrısı yapılabilir
                try:
                    # Order objesi oluştur ve iptal et
                    from ibapi.order import Order
                    cancel_order = Order()
                    cancel_order.orderId = int(order_id)
                    self.ib.cancelOrder(cancel_order)
                    print(f"[IBKR] ✅ Emir iptal isteği gönderildi (emir listede yok ama direkt iptal denendi): Order ID {order_id}")
                    return True
                except Exception as direct_cancel_error:
                    error_str = str(direct_cancel_error)
                    if "10147" in error_str or "not found" in error_str.lower():
                        print(f"[IBKR] ⚠️ Order ID {order_id} zaten iptal edilmiş/tamamlanmış (Error 10147)")
                        return True  # Başarılı sayılır
                    else:
                        print(f"[IBKR] ❌ Direkt iptal hatası: {direct_cancel_error}")
                        return False
            
            # Emri iptal et - ib_insync'te Trade objesi ile iptal edilir
            # ib_insync'te cancelOrder asenkron çalışır, Trade objesinin status'unu kontrol et
            try:
                # İptal işlemini başlat
                self.ib.cancelOrder(target_trade.order)
                print(f"[IBKR] ✅ Emir iptal isteği gönderildi: Order ID {order_id} ({target_trade.contract.symbol})")
                
                # ib_insync'te cancelOrder asenkron çalışır
                # Trade objesinin status'unu kontrol ederek iptal işleminin tamamlanmasını bekle
                max_wait_time = 5.0  # Maksimum bekleme süresi (saniye)
                check_interval = 0.3  # Kontrol aralığı (saniye)
                waited_time = 0.0
                
                while waited_time < max_wait_time:
                    time.sleep(check_interval)
                    waited_time += check_interval
                    
                    # Trade objesinin güncel durumunu kontrol et
                    # openTrades() ile güncel trade listesini al
                    try:
                        current_trades = self.ib.openTrades()
                        current_trade = None
                        for trade in current_trades:
                            if trade.order.orderId == int(order_id):
                                current_trade = trade
                                break
                        
                        if current_trade is None:
                            # Emir artık açık emirler listesinde yok - iptal edilmiş
                            print(f"[IBKR] ✅ Order ID {order_id} başarıyla iptal edildi (açık emirler listesinden çıktı)")
                            return True
                        
                        # Trade objesinin status'unu kontrol et
                        # ib_async.objects.OrderStatus kullan
                        try:
                            from ib_async.objects import OrderStatus
                            status = current_trade.orderStatus.status
                            
                            if status == OrderStatus.Cancelled:
                                print(f"[IBKR] ✅ Order ID {order_id} başarıyla iptal edildi (status: Cancelled)")
                                return True
                            elif status in [OrderStatus.PendingCancel]:
                                # Hala iptal bekleniyor
                                print(f"[IBKR] ⏳ Order ID {order_id} iptal bekleniyor (status: PendingCancel)...")
                                continue
                            elif status in [OrderStatus.Submitted, OrderStatus.PreSubmitted]:
                                # Hala aktif - tekrar iptal dene
                                print(f"[IBKR] ⚠️ Order ID {order_id} hala aktif (status: {status}), tekrar iptal deneniyor...")
                                self.ib.cancelOrder(current_trade.order)
                                continue
                            else:
                                # Farklı bir durum
                                print(f"[IBKR] ⚠️ Order ID {order_id} durumu: {status}")
                                continue
                        except ImportError:
                            # OrderStatus import edilemedi, sadece açık emirler listesini kontrol et
                            continue
                            
                    except Exception as check_error:
                        print(f"[IBKR] ⚠️ Durum kontrolü hatası: {check_error}")
                        continue
                
                # Maksimum bekleme süresi doldu, son kontrol
                final_trades = self.ib.openTrades()
                still_open = any(trade.order.orderId == int(order_id) for trade in final_trades)
                
                if still_open:
                    print(f"[IBKR] ❌ Order ID {order_id} hala açık, iptal edilemedi (timeout)")
                    return False
                else:
                    print(f"[IBKR] ✅ Order ID {order_id} iptal edildi (timeout sonrası kontrol)")
                    return True
            except Exception as cancel_error:
                error_str = str(cancel_error)
                # Error 10147: OrderId that needs to be cancelled is not found
                # Bu durum emir zaten iptal edilmiş/tamamlanmış demektir
                if "10147" in error_str or "not found" in error_str.lower():
                    print(f"[IBKR] ⚠️ Order ID {order_id} zaten iptal edilmiş/tamamlanmış (Error 10147)")
                    return True  # Başarılı sayılır
                else:
                    # Farklı bir hata - gerçek bir sorun var
                    print(f"[IBKR] ❌ Emir iptal hatası: {cancel_error}")
                    raise cancel_error
            
        except Exception as e:
            error_str = str(e)
            # Error 10147 hatası ise sessizce geç (emir zaten iptal edilmiş)
            if "10147" in error_str or "not found" in error_str.lower():
                print(f"[IBKR] ⚠️ Order ID {order_id} zaten iptal edilmiş/tamamlanmış (Error 10147)")
                return True  # Başarılı sayılır
            else:
                print(f"[IBKR] ❌ Emir iptal hatası (Order ID {order_id}): {e}")
                import traceback
                traceback.print_exc()
                return False