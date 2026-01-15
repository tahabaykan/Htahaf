"""
Market Data Service - Market data yönetimi ve WebSocket streaming
Supabase caching ile optimize edilmiş
"""

import sys
import os
from pathlib import Path

# janallapp modüllerini import etmek için path ekle
janallapp_path = Path(__file__).parent.parent / 'janallapp'
sys.path.insert(0, str(janallapp_path))

from hammer_client import HammerClient

# Supabase client (opsiyonel - credentials yoksa çalışmaya devam eder)
try:
    from supabase_setup import supabase_client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    supabase_client = None

# Circular import'u önlemek için lazy import
def broadcast_market_data(symbol, data):
    """Market data güncellemesini tüm subscriber'lara gönder"""
    try:
        from app import socketio
        socketio.emit('market_data_update', {
            'symbol': symbol,
            'data': data
        })
    except Exception as e:
        print(f"Broadcast market data hatası: {e}")

def broadcast_positions_update(positions):
    """Pozisyon güncellemelerini tüm client'lara gönder"""
    try:
        from app import socketio
        socketio.emit('positions_update', {'positions': positions})
    except Exception as e:
        print(f"Broadcast positions hatası: {e}")

class MarketDataService:
    """Market data yönetimi için service"""
    
    def __init__(self):
        self.hammer_client = None
        self.subscribed_symbols = set()
        self.market_data_cache = {}
    
    def connect_hammer(self, host='127.0.0.1', port=16400, password=None):
        """Hammer Pro'ya bağlan"""
        try:
            if self.hammer_client:
                # Mevcut bağlantıyı kapat
                self.hammer_client.disconnect()
            
            # Yeni client oluştur
            self.hammer_client = HammerClient(
                host=host,
                port=port,
                password=password,
                main_window=None  # Web uygulamasında main_window yok
            )
            
            # Callback'leri ayarla
            self.hammer_client.on_positions = self._on_positions_update
            self.hammer_client.on_fill = self._on_fill_update
            
            # Market data güncellemelerini dinle
            # Hammer client'ın market_data dict'ini periyodik olarak kontrol et
            import threading
            if hasattr(self, '_market_data_thread') and self._market_data_thread.is_alive():
                # Eski thread varsa durdur
                pass
            self._market_data_thread = threading.Thread(target=self._monitor_market_data, daemon=True)
            self._market_data_thread.start()
            
            # Bağlan
            if self.hammer_client.connect():
                print("[MarketDataService] ✅ Hammer Pro bağlantısı başarılı")
                return {'success': True, 'message': 'Hammer Pro bağlantısı başarılı'}
            else:
                print("[MarketDataService] ❌ Hammer Pro bağlantısı başarısız")
                return {'success': False, 'error': 'Bağlantı başarısız'}
        except Exception as e:
            print(f"[MarketDataService] ❌ Hammer bağlantı hatası: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    def disconnect_hammer(self):
        """Hammer Pro bağlantısını kes"""
        try:
            if self.hammer_client:
                self.hammer_client.disconnect()
                self.hammer_client = None
                self.subscribed_symbols.clear()
                self.market_data_cache.clear()
                print("[MarketDataService] ✅ Hammer Pro bağlantısı kesildi")
                return {'success': True, 'message': 'Hammer Pro bağlantısı kesildi'}
            else:
                return {'success': False, 'error': 'Aktif bağlantı yok'}
        except Exception as e:
            print(f"[MarketDataService] ❌ Disconnect hatası: {e}")
            return {'success': False, 'error': str(e)}
    
    def _on_positions_update(self, positions):
        """Pozisyon güncellemeleri geldiğinde"""
        try:
            # Formatla
            formatted_positions = []
            for pos in positions:
                symbol = pos.get('Symbol') or pos.get('sym')
                if symbol and '-' in symbol:
                    base, suffix = symbol.split('-')
                    display_symbol = f"{base} PR{suffix}"
                else:
                    display_symbol = symbol
                
                formatted_positions.append({
                    'symbol': display_symbol,
                    'qty': self.hammer_client._extract_position_qty(pos),
                    'avg_cost': self.hammer_client._extract_position_avg_cost(pos)
                })
            
            # WebSocket ile broadcast et
            broadcast_positions_update(formatted_positions)
        except Exception as e:
            print(f"Pozisyon güncelleme hatası: {e}")
    
    def _on_fill_update(self, fill_data):
        """Fill güncellemeleri geldiğinde"""
        try:
            # WebSocket ile broadcast et
            from flask_socketio import emit
            from app import socketio
            
            socketio.emit('fill_update', {'fill': fill_data})
        except Exception as e:
            print(f"Fill güncelleme hatası: {e}")
    
    def subscribe_symbols(self, symbols):
        """Sembollere subscribe ol - Tkinter'daki gibi"""
        try:
            if not self.hammer_client or not self.hammer_client.is_connected():
                print(f"[MarketDataService] ⚠️ Hammer Pro bağlantısı yok, subscribe edilemedi")
                return []
            
            subscribed = []
            print(f"[MarketDataService] 🔄 {len(symbols)} sembol için Hammer Pro'ya subscribe olunuyor...")
            
            for i, symbol in enumerate(symbols):
                try:
                    # L2 verisi için include_l2=True
                    result = self.hammer_client.subscribe_symbol(symbol, include_l2=True)
                    if result:
                        self.subscribed_symbols.add(symbol)
                        subscribed.append(symbol)
                    
                    # Her 50 sembolda bir log
                    if (i + 1) % 50 == 0:
                        print(f"[MarketDataService] ✅ {i + 1}/{len(symbols)} sembol subscribe edildi...")
                except Exception as e:
                    print(f"[MarketDataService] ⚠️ {symbol} subscribe hatası: {e}")
                    continue
            
            print(f"[MarketDataService] ✅ Toplam {len(subscribed)}/{len(symbols)} sembol subscribe edildi")
            return subscribed
        except Exception as e:
            print(f"[MarketDataService] ❌ Subscribe hatası: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_market_data(self, symbol):
        """Sembol için market data getir - Tkinter'daki gibi Hammer'dan direkt al"""
        try:
            if not self.hammer_client or not self.hammer_client.is_connected():
                return None
            
            # Hammer'dan direkt al (cache'i bypass et, her zaman güncel veri al)
            data = self.hammer_client.get_market_data(symbol)
            
            if data:
                # Cache'e kaydet (güncel veri için)
                self.market_data_cache[symbol] = data
                
                # WebSocket ile broadcast et
                broadcast_market_data(symbol, data)
            
            return data
        except Exception as e:
            print(f"Market data getirme hatası: {e}")
            # Hata durumunda cache'den döndür
            return self.market_data_cache.get(symbol)
    
    def update_market_data(self, symbol, data):
        """Market data'yı güncelle (Hammer'dan gelen güncellemeler için)"""
        try:
            # Cache'i güncelle
            self.market_data_cache[symbol] = data
            
            # Supabase'e cache'le (hızlı erişim için)
            if SUPABASE_AVAILABLE and supabase_client and supabase_client.is_available():
                try:
                    supabase_client.cache_market_data(symbol, data)
                except Exception as e:
                    # Supabase hatası uygulamayı durdurmamalı
                    pass
            
            # WebSocket ile broadcast et
            broadcast_market_data(symbol, data)
        except Exception as e:
            print(f"Market data güncelleme hatası: {e}")
    
    def _monitor_market_data(self):
        """Hammer client'ın market_data dict'ini periyodik olarak kontrol et ve güncellemeleri broadcast et"""
        import time
        last_broadcast = {}
        last_log_time = 0
        
        while True:
            try:
                if self.hammer_client and self.hammer_client.is_connected():
                    # Hammer client'ın market_data dict'ini kontrol et
                    current_time = time.time()
                    data_count = len(self.hammer_client.market_data)
                    
                    # Her 10 saniyede bir log (debug için)
                    if current_time - last_log_time > 10:
                        print(f"[MarketDataService] 📊 Market data monitoring: {data_count} sembol için data var")
                        last_log_time = current_time
                    
                    # Batch olarak Supabase'e cache'lemek için dict oluştur
                    batch_cache = {}
                    
                    for symbol, data in self.hammer_client.market_data.items():
                        # Değişiklik var mı kontrol et
                        if symbol not in last_broadcast or last_broadcast[symbol] != data:
                            # Cache'i güncelle
                            self.market_data_cache[symbol] = data
                            
                            # Batch cache için ekle
                            batch_cache[symbol] = data
                            
                            # WebSocket ile broadcast et
                            broadcast_market_data(symbol, data)
                            
                            # Son broadcast'i kaydet
                            last_broadcast[symbol] = data
                    
                    # Batch olarak Supabase'e cache'le (daha hızlı)
                    if batch_cache and SUPABASE_AVAILABLE and supabase_client and supabase_client.is_available():
                        try:
                            supabase_client.batch_cache_market_data(batch_cache)
                        except Exception as e:
                            # Supabase hatası uygulamayı durdurmamalı
                            pass
                else:
                    # Bağlantı yoksa bekle
                    time.sleep(2)
                
                time.sleep(0.5)  # 500ms'de bir kontrol et
            except Exception as e:
                print(f"[MarketDataService] ❌ Market data monitoring hatası: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)

