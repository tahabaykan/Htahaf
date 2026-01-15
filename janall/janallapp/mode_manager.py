"""
Mode Manager - HAMPRO MOD ve IBKR MOD arasında geçiş yönetimi

!!! ÖNEMLİ DOSYA YOLU UYARISI !!!
=================================
BÜTÜN CSV OKUMA VE CSV KAYDETME İŞLEMLERİ StockTracker DİZİNİNE YAPILMALI!!
StockTracker/janall/ dizinine YAPILMAMALI!!!
KARIŞASAYI ÖNLEMEK İÇİN BU KURALA MUTLAKA UYULACAK!

Bu modül mod değişikliklerini yönetir
=================================
"""

import logging
import time
from typing import Optional, Callable

class ModeManager:
    """HAMPRO MOD, IBKR GUN MOD ve IBKR PED MOD arasında geçiş yönetimi"""
    
    HAMPRO_MODE = "HAMPRO"
    IBKR_GUN_MODE = "IBKR_GUN"
    IBKR_PED_MODE = "IBKR_PED"
    
    def __init__(self, hammer_client=None, ibkr_client=None, ibkr_native_client=None, main_window=None):
        self.current_mode = self.HAMPRO_MODE  # Varsayılan mod
        self.hammer_client = hammer_client
        self.ibkr_client = ibkr_client
        self.ibkr_native_client = ibkr_native_client
        self.main_window = main_window  # Main window referansı (Controller kontrolü için)
        
        # IBKR için global throttle sistemi
        self.last_ibkr_order_time = 0
        self.min_ibkr_order_interval = 0.1  # Minimum 0.1 saniye aralık
        
        # Callback'ler
        self.on_mode_changed = None  # callable(mode)
        self.on_positions_changed = None  # callable(positions)
        self.on_orders_changed = None  # callable(orders)
        
        # Logging
        self.logger = logging.getLogger('mode_manager')
        self.logger.setLevel(logging.INFO)
    
    def set_mode(self, mode: str):
        """Modu değiştir"""
        if mode not in [self.HAMPRO_MODE, self.IBKR_GUN_MODE, self.IBKR_PED_MODE]:
            print(f"[MODE] ❌ Geçersiz mod: {mode}")
            return False
        
        if mode == self.current_mode:
            print(f"[MODE] ⚠️ Mod zaten {mode}")
            return True
        
        old_mode = self.current_mode
        self.current_mode = mode
        
        print(f"[MODE] 🔄 Mod değiştirildi: {old_mode} -> {mode}")
        
        # Callback'i çağır
        if callable(self.on_mode_changed):
            self.on_mode_changed(mode)
        
        return True
    
    def get_current_mode(self) -> str:
        """Mevcut modu döndür"""
        return self.current_mode
    
    def get_active_account(self) -> str:
        """Aktif hesabı döndür"""
        if self.is_hampro_mode():
            return "HAMPRO"
        elif self.is_ibkr_gun_mode():
            return "IBKR_GUN"
        elif self.is_ibkr_ped_mode():
            return "IBKR_PED"
        else:
            return "UNKNOWN"
    
    def is_hampro_mode(self) -> bool:
        """HAMPRO modunda mı?"""
        return self.current_mode == self.HAMPRO_MODE
    
    def is_hammer_mode(self) -> bool:
        """Hammer Pro modunda mı? (is_hampro_mode ile aynı)"""
        return self.current_mode == self.HAMPRO_MODE
    
    def is_ibkr_mode(self) -> bool:
        """IBKR modunda mı? (GUN veya PED)"""
        return self.current_mode in [self.IBKR_GUN_MODE, self.IBKR_PED_MODE]
    
    def is_ibkr_gun_mode(self) -> bool:
        """IBKR GUN modunda mı?"""
        return self.current_mode == self.IBKR_GUN_MODE
    
    def is_ibkr_ped_mode(self) -> bool:
        """IBKR PED modunda mı?"""
        return self.current_mode == self.IBKR_PED_MODE
    
    def get_positions(self):
        """Mevcut moda göre pozisyonları al"""
        try:
            if self.is_hampro_mode():
                if self.hammer_client and self.hammer_client.connected:
                    positions = self.hammer_client.get_positions_direct()
                    print(f"[MODE] 📊 HAMPRO'dan {len(positions)} pozisyon alındı")
                    return positions
                else:
                    print("[MODE] ❌ HAMPRO client bağlı değil")
                    return []
            
            elif self.is_ibkr_mode():
                if self.ibkr_client and self.ibkr_client.is_connected():
                    positions = self.ibkr_client.get_positions_direct()
                    print(f"[MODE] 📊 IBKR'den {len(positions)} pozisyon alındı")
                    return positions
                else:
                    print("[MODE] ❌ IBKR client bağlı değil")
                    return []
            
            return []
        except Exception as e:
            self.logger.error(f"Error getting positions: {e}")
            return []
    
    def get_orders(self):
        """Mevcut moda göre emirleri al"""
        try:
            if self.is_hampro_mode():
                if self.hammer_client and self.hammer_client.connected:
                    orders = self.hammer_client.get_orders()
                    # DEBUG: Log kapatıldı - sürekli terminal loglarını dolduruyordu
                    # print(f"[MODE] 📋 HAMPRO'dan {len(orders)} emir alındı")
                    return orders
                else:
                    print("[MODE] ❌ HAMPRO client bağlı değil")
                    return []
            
            elif self.is_ibkr_mode():
                # Native IBKR client'i öncelikle kullan
                if self.ibkr_native_client and self.ibkr_native_client.is_connected():
                    orders = self.ibkr_native_client.get_open_orders()
                    # DEBUG: Log kapatıldı - sürekli terminal loglarını dolduruyordu
                    # print(f"[MODE] 📋 IBKR Native'dan {len(orders)} emir alındı")
                    return orders
                elif self.ibkr_client and self.ibkr_client.is_connected():
                    orders = self.ibkr_client.get_orders_direct()
                    # DEBUG: Log kapatıldı - sürekli terminal loglarını dolduruyordu
                    # print(f"[MODE] 📋 IBKR Client'dan {len(orders)} emir alındı")
                    return orders
                else:
                    print("[MODE] ❌ IBKR client bağlı değil")
                    return []
            
            return []
        except Exception as e:
            self.logger.error(f"Error getting orders: {e}")
            return []
    
    def get_market_data(self, symbol):
        """Market data her zaman Hammer Pro'dan alınır"""
        if self.hammer_client and self.hammer_client.connected:
            return self.hammer_client.get_market_data(symbol)
        return {}
    
    def get_l2_data(self, symbol):
        """L2 data her zaman Hammer Pro'dan alınır"""
        if self.hammer_client and self.hammer_client.connected:
            return self.hammer_client.get_l2_data(symbol)
        return {}
    
    def place_order(self, symbol, side, quantity, price, order_type="LIMIT", hidden=True):
        """Mevcut moda göre emir gönder - IBKR için global throttle ile - Controller kontrolü ile"""
        try:
            # Aktif modu logla
            active_mode = self.get_current_mode()
            active_account = self.get_active_account()
            print(f"[MODE] 📤 Emir gönderiliyor: {symbol} {side} {quantity} lot @ ${price:.2f} | Mod: {active_mode} ({active_account})")
            
            # Controller kontrolü (eğer main_window varsa ve controller aktifse)
            if self.main_window and hasattr(self.main_window, 'controller_check_order'):
                allowed, adjusted_qty, reason = self.main_window.controller_check_order(symbol, side, quantity)
                
                if not allowed:
                    print(f"[CONTROLLER] ❌ Emir engellendi: {symbol} {side} {quantity} - {reason}")
                    return False
                
                if adjusted_qty != quantity:
                    print(f"[CONTROLLER] ⚠️ Emir ayarlandı: {symbol} {side} {quantity} → {adjusted_qty} - {reason}")
                    quantity = adjusted_qty
            
            if self.is_hampro_mode():
                if self.hammer_client and self.hammer_client.connected:
                    print(f"[MODE] 🔨 HAMPRO modunda emir gönderiliyor: {symbol} {side} {quantity} lot")
                    return self.hammer_client.place_order(symbol, side, quantity, price, order_type, hidden)
                else:
                    print("[MODE] ❌ HAMPRO client bağlı değil, emir gönderilemez")
                    return False
            
            elif self.is_ibkr_mode():
                # IBKR için global throttle kontrolü
                current_time = time.time()
                time_since_last_order = current_time - self.last_ibkr_order_time
                
                if time_since_last_order < self.min_ibkr_order_interval:
                    wait_time = self.min_ibkr_order_interval - time_since_last_order
                    print(f"[MODE] ⏳ IBKR throttle: {wait_time:.2f}s bekleniyor...")
                    time.sleep(wait_time)
                
                # IBKR modunu belirle (GUN veya PED)
                ibkr_mode_detail = "IBKR_GUN" if self.is_ibkr_gun_mode() else "IBKR_PED" if self.is_ibkr_ped_mode() else "IBKR"
                print(f"[MODE] 🔄 {ibkr_mode_detail} modunda emir gönderiliyor: {symbol} {side} {quantity} lot")
                
                # Native IBKR client'i öncelikle kullan (displayQuantity ile hidden emirler)
                if self.ibkr_native_client and self.ibkr_native_client.is_connected():
                    print(f"[MODE] 🔄 {ibkr_mode_detail} Native client ile emir gönderiliyor...")
                    result = self.ibkr_native_client.place_order(symbol, side, quantity, price, order_type, hidden)
                    self.last_ibkr_order_time = time.time()
                    return result
                elif self.ibkr_client and self.ibkr_client.is_connected():
                    print(f"[MODE] 🔄 {ibkr_mode_detail} ib_async client ile emir gönderiliyor...")
                    result = self.ibkr_client.place_order(symbol, side, quantity, price, order_type, hidden)
                    self.last_ibkr_order_time = time.time()
                    return result
                else:
                    print(f"[MODE] ❌ {ibkr_mode_detail} client bağlı değil, emir gönderilemez")
                    return False
            
            return False
        except Exception as e:
            self.logger.error(f"Error placing order: {e}")
            return False
    
    def get_connection_status(self):
        """Bağlantı durumlarını döndür"""
        hampro_status = self.hammer_client.connected if self.hammer_client else False
        ibkr_status = self.ibkr_client.is_connected() if self.ibkr_client else False
        
        return {
            'hampro': hampro_status,
            'ibkr': ibkr_status,
            'current_mode': self.current_mode
        }





