import pandas as pd
from Htahaf.utils.order_management import OrderManager, log_reasoning
import time
import logging
import os
import tkinter as tk
from tkinter import messagebox
import threading
import json
from datetime import datetime, timedelta, date
import sys

# BDATA entegrasyonu için import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Htahaf.utils.bdata_storage import BDataStorage

# Logging ayarları
logger = logging.getLogger('PsfAlgo2')
logger.setLevel(logging.INFO)

# Log dosyası için dizin oluştur
log_dir = 'logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Log dosyası handler'ı
log_file = os.path.join(log_dir, 'psf_reasoning.log')
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Konsola log yazdırmak için handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

class PsfAlgo2:
    def __init__(self, market_data, exclude_list=None, order_manager=None):
        self.logger = logging.getLogger('PsfAlgo2')
        self.logger.info("PsfAlgo2 initialized - ESKİ 6 ADIMLI SİSTEM (9-14) - INACTIVE by default")
        
        # Temel değişkenler
        self.market_data = market_data
        self.order_manager = order_manager
        self.main_window = None
        self.current_window = None
        self.is_active = False
        self.data_ready = False
        
        # BDATA entegrasyonu
        self.bdata_storage = BDataStorage('Htahaf/data/bdata_fills.json')
        
        # BEFDAY pozisyonları (PSFAlgo1'den alınacak)
        self.befday_positions = {}
        
        self.exclude_list = exclude_list or set()
        self.filled_sizes = {}  # Her hisse için toplam fill miktarı
        
        # ✅ Günlük fill takibi (PSFAlgo1'den alınacak)
        self.today = date.today()
        self.daily_fills = {}  # {ticker: {'long': total_size, 'short': total_size, 'date': date}}
        
        # ✅ PISDoNGU sistemi
        self.pisdongu_active = False
        self.pisdongu_timer = None
        self.pisdongu_cycle_count = 0
        
        # ✅ BEFDAY pozisyon limitleri (PSFAlgo1'den alınacak)
        self.daily_position_limits = {}  # Her hisse için ±600 limit
        
        # ✅ Chain yönetimi - ESKİ 6 ADIM (9-14)
        self.chain_state = 'T_LOSERS_OLD'  # T_LOSERS_OLD, T_GAINERS_OLD, LONG_TP_ASK, LONG_TP_FRONT, SHORT_TP_BID, SHORT_TP_FRONT, FINISHED
        self.waiting_for_approval = False  # Onay bekleme kontrolü
        
        # ✅ PSFAlgo1 referansı (geri devir için)
        self.psfalgo1 = None
        
        logger.info("PsfAlgo2 initialized - ESKİ 6 ADIMLI SİSTEM (9-14) - INACTIVE by default")

    def set_main_window(self, main_window):
        """Ana pencere referansını ayarla"""
        self.main_window = main_window
        print("[PSFAlgo2] Ana pencere referansı ayarlandı")

    def set_psfalgo1(self, psfalgo1):
        """PSFAlgo1 referansını ayarla (geri devir için)"""
        self.psfalgo1 = psfalgo1
        print("[PSFAlgo2] PSFAlgo1 referansı ayarlandı")

    def activate(self):
        """PSFAlgo2'yi aktif hale getir"""
        self.is_active = True
        self.pisdongu_active = True
        
        logger.info("PsfAlgo2 ACTIVATED - ESKİ 6 ADIMLI SİSTEM başlatılıyor")
        print("[PSFAlgo2] ✅ PSFAlgo2 aktif hale getirildi!")
        print("[PISDoNGU] 🔄 ESKİ 6 ADIMLI SİSTEM (9-14) başlatılıyor...")
        
        # ESKİ 6 ADIMLI SİSTEMİ başlat
        self.chain_state = 'T_LOSERS_OLD'
        self.start_chain()

    def activate_from_psfalgo1(self, cycle_count, daily_fills, befday_positions, daily_position_limits):
        """PSFAlgo1'den devir alındığında aktif et"""
        print(f"[PSFAlgo2] 🔄 PSFAlgo1'den devir alındı - Cycle: {cycle_count}")
        
        # Veri senkronizasyonu
        self.pisdongu_cycle_count = cycle_count
        self.daily_fills = daily_fills
        self.befday_positions = befday_positions
        self.daily_position_limits = daily_position_limits
        
        # PSFAlgo2'yi aktif et
        self.is_active = True
        print("🟢 PSFAlgo2 AÇIK - ESKİ 6 ADIMLI SİSTEM (9-14) devam ediyor")
        
        # Chain'i başlangıç durumuna getir
        self.chain_state = 'T_LOSERS_OLD'  # PSFAlgo2'nin ilk adımı
        self.waiting_for_approval = False
        
        # İlk adımı başlat
        self.start_chain()

    def deactivate(self):
        """PSFAlgo2'yi pasif hale getir"""
        self.is_active = False
        self.pisdongu_active = False
        self.chain_state = 'T_LOSERS_OLD'
        
        # Timer'ı durdur
        if self.pisdongu_timer:
            self.pisdongu_timer.cancel()
            self.pisdongu_timer = None
        
        # Ana penceredeki buton durumunu güncelle
        if self.main_window and hasattr(self.main_window, 'btn_psf_algo2'):
            self.main_window.btn_psf_algo2.config(text="PsfAlgo2 OFF", style='TButton')
        
        logger.info("PsfAlgo2 DEACTIVATED - ESKİ 6 ADIMLI SİSTEM durduruldu")
        print("[PSFAlgo2] ❌ PSFAlgo2 pasif hale getirildi!")
        print("[PISDoNGU] ⏹️ ESKİ 6 ADIMLI SİSTEM durduruldu!")

    def start_chain(self):
        """PSFAlgo2 chain'ini başlat - ESKİ 6 ADIMLI SİSTEM (9-14)"""
        if not self.is_active or self.chain_state == 'FINISHED':
            return
            
        print(f"[PSFAlgo2 CHAIN] Başlatılıyor - Durum: {self.chain_state}")
        
        # ESKİ 6 ADIMLI SİSTEM (9-14)
        if self.chain_state == 'T_LOSERS_OLD':
            self.run_t_top_losers_old()  # 9. ESKİ T-Losers
        elif self.chain_state == 'T_GAINERS_OLD':
            self.run_t_top_gainers_old()  # 10. ESKİ T-Gainers
        elif self.chain_state == 'LONG_TP_ASK':
            self.run_long_tp_ask_sell()  # 11. ESKİ Long TP ask sell
        elif self.chain_state == 'LONG_TP_FRONT':
            self.run_long_tp_front_sell()  # 12. ESKİ Long TP front sell
        elif self.chain_state == 'SHORT_TP_BID':
            self.run_short_tp_bid_buy()  # 13. ESKİ Short TP bid buy
        elif self.chain_state == 'SHORT_TP_FRONT':
            self.run_short_tp_front_buy()  # 14. ESKİ Short TP front buy
        elif self.chain_state == 'FINISHED':
            self.finish_chain()

    def advance_chain(self):
        """Chain'i bir sonraki aşamaya ilerlet"""
        print(f"[PSFAlgo2 CHAIN] 🔄 Chain ilerliyor: {self.chain_state} → ", end="")
        
        # Onay bekleme durumunu sıfırla
        self.waiting_for_approval = False
        
        # Chain durumunu ilerlet
        if self.chain_state == 'T_LOSERS_OLD':
            self.chain_state = 'T_GAINERS_OLD'
            print(f"T_GAINERS_OLD")
        elif self.chain_state == 'T_GAINERS_OLD':
            self.chain_state = 'LONG_TP_ASK'
            print(f"LONG_TP_ASK")
        elif self.chain_state == 'LONG_TP_ASK':
            self.chain_state = 'LONG_TP_FRONT'
            print(f"LONG_TP_FRONT")
            # Aynı pencerede devam et, yeni pencere açma
            self.continue_current_window_next_step()
            return
        elif self.chain_state == 'LONG_TP_FRONT':
            self.chain_state = 'SHORT_TP_BID'
            print(f"SHORT_TP_BID")
        elif self.chain_state == 'SHORT_TP_BID':
            self.chain_state = 'SHORT_TP_FRONT'
            print(f"SHORT_TP_FRONT")
            # Aynı pencerede devam et, yeni pencere açma
            self.continue_current_window_next_step()
            return
        elif self.chain_state == 'SHORT_TP_FRONT':
            self.chain_state = 'FINISHED'
            print(f"FINISHED")
            print(f"[PSFAlgo2 CHAIN] 14→FINISHED: SHORT_TP_FRONT tamamlandı, PSFAlgo1'e geri devrediliyor...")
        elif self.chain_state == 'FINISHED':
            self.finish_chain()
            return  # finish_chain çağrıldığında start_chain çağrılmamalı
        else:
            # Bilinmeyen state
            print(f"[PSFAlgo2 CHAIN] ❌ Bilinmeyen chain_state: {self.chain_state}")
            return
        
        # Sonraki aşamayı başlat (sadece yeni pencere gerektiğinde)
        print(f"[PSFAlgo2 CHAIN] Yeni state: {self.chain_state}, pencere açılıyor...")
        self.start_chain()

    def continue_current_window_next_step(self):
        """Mevcut pencerede sonraki adımı çalıştır (onay alındıktan sonra)"""
        if not self.current_window:
            print("[PSFAlgo2 CHAIN] ❌ Mevcut pencere yok, sonraki adım çalıştırılamıyor")
            self.advance_chain()
            return
        
        window_title = self.current_window.title().lower()
        
        # LONG TP penceresi için 2. adım
        if "long take profit" in window_title and self.chain_state == 'LONG_TP_FRONT':
            print("[PSFAlgo2 CHAIN] 🚀 Long TP 2. adım başlatılıyor (Front Sell)")
            self.run_long_tp_front_sell_data_ready()
            
        # SHORT TP penceresi için 2. adım
        elif "short take profit" in window_title and self.chain_state == 'SHORT_TP_FRONT':
            print("[PSFAlgo2 CHAIN] 🚀 Short TP 2. adım başlatılıyor (Front Buy)")
            self.run_short_tp_front_buy_data_ready()
            
        else:
            # Mevcut pencerede başka adım yok, sonraki pencereye geç
            print(f"[PSFAlgo2 CHAIN] Mevcut pencerede ({window_title}) başka adım yok, sonraki aşamaya geçiliyor")
            self.advance_chain()

    def finish_chain(self):
        """ESKİ 6 adımı bitir ve PSFAlgo1'e geri devret"""
        print(f"[PSFAlgo2 CHAIN] ✅ ESKİ 6 adımlı sistem tamamlandı - Cycle #{self.pisdongu_cycle_count}")
        
        # Mevcut pencereleri kapat
        self.close_current_windows()
        
        # PSFAlgo2'yi deaktive et
        self.is_active = False
        
        # PSFAlgo1'e geri devret
        if hasattr(self, 'psfalgo1') and self.psfalgo1:
            print("[PSFAlgo2 CHAIN] 🔄 PSFAlgo1'e geri devrediliyor...")
            # 3 dakika bekleyip yeni döngü başlat
            self.psfalgo1.schedule_next_pisdongu_cycle()
        else:
            print("[PSFAlgo2 CHAIN] ⚠️ PSFAlgo1 referansı yok - sistem durduruluyor")
            self.is_active = False

    def close_current_windows(self):
        """Mevcut pencereleri kapat"""
        if self.main_window:
            # T-top losers/gainers pencerelerini kapat
            for window in list(self.main_window.children.values()):
                if hasattr(window, 'title') and ('losers' in window.title().lower() or 'gainers' in window.title().lower()):
                    window.destroy()
            
            # Long/Short TP pencerelerini kapat
            for window in list(self.main_window.children.values()):
                if hasattr(window, 'title') and ('take profit' in window.title().lower()):
                    window.destroy()

    def check_and_prevent_position_reversal(self):
        """
        Pozisyon kontrolü yaparak ters pozisyona geçmeyi önler
        """
        print("[PSFAlgo2 POSITION CONTROL] 📊 Pozisyon tersine geçme kontrolü başlatılıyor...")
        
        if not self.is_active:
            print("[PSFAlgo2] ⏸️ PSFAlgo2 pasif - pozisyon kontrolü yapılmadı")
            return
            
        # Ana thread'de çalıştır (event loop sorunu için)
        if hasattr(self.main_window, 'after'):
            self.main_window.after(0, self._position_control_main_thread)
        else:
            self._position_control_main_thread()

    def _position_control_main_thread(self):
        """Ana thread'de pozisyon kontrolü yap"""
        # 3 saniye bekle ki emirler sisteme girsin
        import time
        time.sleep(3)
        
        try:
            # Mevcut pozisyonları al
            current_positions = {}
            if hasattr(self.market_data, 'get_positions'):
                positions = self.market_data.get_positions()
                for pos in positions:
                    current_positions[pos['symbol']] = pos['quantity']
                    print(f"[POSITION] {pos['symbol']}: {pos['quantity']} lot")
            
            print(f"[PSFAlgo2 POSITION CONTROL] ✅ Pozisyon kontrolü tamamlandı")
            
        except Exception as e:
            print(f"[PSFAlgo2 POSITION CONTROL] ❌ Genel hata: {e}")
            import traceback
            traceback.print_exc()

    # ================== ESKİ 6 ADIMLI SİSTEM FONKSİYONLARI (9-14) ==================

    def run_t_top_losers_old(self):
        """9. ADIM: ESKİ T-top losers sistemi"""
        print("[PSFAlgo2 CHAIN 9/14] 📈 T-top Losers (Eski Sistem)")
        
        if not self.is_active:
            print("[PSFAlgo2] ⏸️ PSFAlgo2 pasif - T-top losers işlenmedi")
            return
            
        # T-top losers penceresini aç
        if self.main_window and hasattr(self.main_window, 'open_t_top_losers_maltopla'):
            self.main_window.open_t_top_losers_maltopla()
            print("[PSFAlgo2 CHAIN 9] T-top losers penceresi açılıyor...")
        else:
            print("[PSFAlgo2 CHAIN 9] ❌ T-top losers penceresi açılamadı")
            self.advance_chain()

    def run_t_top_gainers_old(self):
        """10. ADIM: ESKİ T-top gainers sistemi"""
        print("[PSFAlgo2 CHAIN 10/14] 📉 T-top Gainers (Eski Sistem)")
        
        if not self.is_active:
            print("[PSFAlgo2] ⏸️ PSFAlgo2 pasif - T-top gainers işlenmedi")
            return
            
        # T-top gainers penceresini aç
        if self.main_window and hasattr(self.main_window, 'open_t_top_gainers_maltopla'):
            self.main_window.open_t_top_gainers_maltopla()
            print("[PSFAlgo2 CHAIN 10] T-top gainers penceresi açılıyor...")
        else:
            print("[PSFAlgo2 CHAIN 10] ❌ T-top gainers penceresi açılamadı")
            self.advance_chain()

    def run_long_tp_ask_sell(self):
        """11. ADIM: Long TP Ask Sell işlemlerini yap"""
        print("[PSFAlgo2 CHAIN 11/14] 💰 Long TP Ask Sell (Eski Sistem)")
        
        if not self.is_active:
            print("[PSFAlgo2] ⏸️ PSFAlgo2 pasif - Long TP Ask Sell işlenmedi")
            return
            
        # Long Take Profit penceresini aç
        if self.main_window and hasattr(self.main_window, 'open_long_take_profit_window'):
            self.main_window.open_long_take_profit_window()
            print("[PSFAlgo2 CHAIN 11] Long Take Profit penceresi açılıyor...")
        else:
            print("[PSFAlgo2 CHAIN 11] ❌ Long Take Profit penceresi açılamadı")
            self.advance_chain()

    def run_long_tp_front_sell(self):
        """12. ADIM: Long TP Front Sell işlemlerini yap"""
        print("[PSFAlgo2 CHAIN 12/14] 🎯 Long TP Front Sell (Eski Sistem)")
        
        if not self.is_active or not self.current_window:
            print("[PSFAlgo2 CHAIN 12] ❌ Pencere bulunamadı veya PSFAlgo2 pasif")
            self.advance_chain()
            return
        
        # Mevcut long pozisyonları al
        positions = self.get_long_positions()
        
        if not positions:
            print("[PSFAlgo2 CHAIN 12] ❌ Long pozisyon bulunamadı")
            self.advance_chain()
            return
        
        print("[PSFAlgo2 CHAIN 12] Long TP Front Sell için mevcut pencere kullanılıyor...")
        
        # Mevcut pencerede front sell işlemini tetikle
        if self.current_window and "long take profit" in self.current_window.title().lower():
            self.run_long_tp_front_sell_logic()
        else:
            print("[PSFAlgo2 CHAIN 12] ❌ Long TP penceresi bulunamadı")
            self.advance_chain()

    def run_short_tp_bid_buy(self):
        """13. ADIM: Short TP Bid Buy işlemlerini yap"""
        print("[PSFAlgo2 CHAIN 13/14] 💰 Short TP Bid Buy (Eski Sistem)")
        
        if not self.is_active:
            print("[PSFAlgo2] ⏸️ PSFAlgo2 pasif - Short TP Bid Buy işlenmedi")
            return
            
        # Short Take Profit penceresini aç
        if self.main_window and hasattr(self.main_window, 'open_short_take_profit_window'):
            self.main_window.open_short_take_profit_window()
            print("[PSFAlgo2 CHAIN 13] Short Take Profit penceresi açılıyor...")
        else:
            print("[PSFAlgo2 CHAIN 13] ❌ Short Take Profit penceresi açılamadı")
            self.advance_chain()

    def run_short_tp_front_buy(self):
        """14. ADIM: Short TP Front Buy işlemlerini yap"""
        print("[PSFAlgo2 CHAIN 14/14] 🎯 Short TP Front Buy (Eski Sistem)")
        
        if not self.is_active or not self.current_window:
            print("[PSFAlgo2 CHAIN 14] ❌ Pencere bulunamadı veya PSFAlgo2 pasif")
            self.advance_chain()
            return
        
        # Mevcut short pozisyonları al
        positions = self.get_short_positions()
        
        if not positions:
            print("[PSFAlgo2 CHAIN 14] ❌ Short pozisyon bulunamadı")
            self.advance_chain()
            return
        
        print("[PSFAlgo2 CHAIN 14] Short TP Front Buy için mevcut pencere kullanılıyor...")
        
        # Mevcut pencerede front buy işlemini tetikle
        if self.current_window and "short take profit" in self.current_window.title().lower():
            self.run_short_tp_front_buy_logic()
        else:
            print("[PSFAlgo2 CHAIN 14] ❌ Short TP penceresi bulunamadı")
            self.advance_chain()

    # ================== HELPER FONKSİYONLAR ==================

    def get_long_positions(self):
        """Mevcut long pozisyonları döndür"""
        if hasattr(self.market_data, 'get_positions'):
            positions = self.market_data.get_positions()
            return [pos for pos in positions if pos['quantity'] > 0]
        return []

    def get_short_positions(self):
        """Mevcut short pozisyonları döndür"""
        if hasattr(self.market_data, 'get_positions'):
            positions = self.market_data.get_positions()
            return [pos for pos in positions if pos['quantity'] < 0]
        return []

    def run_long_tp_front_sell_logic(self):
        """Long TP Front Sell mantığı"""
        print("[PSFAlgo2] Long TP Front Sell mantığı çalıştırılıyor...")
        # Bu fonksiyonu daha sonra detaylandıracağız
        self.advance_chain()

    def run_short_tp_front_buy_logic(self):
        """Short TP Front Buy mantığı"""
        print("[PSFAlgo2] Short TP Front Buy mantığı çalıştırılıyor...")
        # Bu fonksiyonu daha sonra detaylandıracağız
        self.advance_chain()

    def on_window_opened(self, window):
        """Pencere açıldığında çağrılır"""
        print("[PSFAlgo2] on_window_opened çağrıldı")
        
        # ✅ PSFAlgo2 aktif değilse hiçbir şey yapma
        if not self.is_active:
            print("[PSFAlgo2] ⏸️ PSFAlgo2 pasif - pencere açılması işlenmedi")
            return
            
        self.current_window = window
        self.data_ready = False

    def on_data_ready(self, window):
        """Pencere verisi hazır olduğunda çağrılır - otomatik hisse seçimi ve onay penceresi"""
        print(f"[PSFAlgo2] on_data_ready çağrıldı: {window.title()}")
        
        # Eğer onay bekliyorsak, otomatik işlem yapma
        if hasattr(self, 'waiting_for_approval') and self.waiting_for_approval:
            print("[PSFAlgo2] ⏸️ Onay bekleniyor, otomatik işlem yapılmıyor")
            return
        
        window_title = window.title().lower()
        
        # T-TOP LOSERS (OLD) penceresi için - sadece ilk adım otomatik
        if "t-top losers" in window_title:
            if self.chain_state == 'T_LOSERS_OLD':
                print("[PSFAlgo2 CHAIN 9] T-top losers veri hazır, ESKİ mantık çalıştırılıyor...")
                self.run_t_top_losers_data_ready()
            else:
                print(f"[PSFAlgo2] ⏸️ T-Losers penceresi açıldı ama chain_state={self.chain_state}, otomatik işlem yok")
                
        # T-TOP GAINERS (OLD) penceresi için - sadece ilk adım otomatik  
        elif "t-top gainers" in window_title:
            if self.chain_state == 'T_GAINERS_OLD':
                print("[PSFAlgo2 CHAIN 10] T-top gainers veri hazır, ESKİ mantık çalıştırılıyor...")
                self.run_t_top_gainers_data_ready()
            else:
                print(f"[PSFAlgo2] ⏸️ T-Gainers penceresi açıldı ama chain_state={self.chain_state}, otomatik işlem yok")
                
        # LONG TAKE PROFIT penceresi için - sadece ilk adım otomatik
        elif "long take profit" in window_title:
            if self.chain_state == 'LONG_TP_ASK':
                print("[PSFAlgo2 CHAIN 11] Long TP veri hazır, ask sell mantığı çalıştırılıyor...")
                self.run_long_tp_ask_sell_data_ready()
            elif self.chain_state == 'LONG_TP_FRONT':
                print("[PSFAlgo2 CHAIN 12] Long TP veri hazır, front sell mantığı çalıştırılıyor...")
                self.run_long_tp_front_sell_data_ready()
            else:
                print(f"[PSFAlgo2] ⏸️ Long TP penceresi açıldı ama chain_state={self.chain_state}, otomatik işlem yok")
                
        # SHORT TAKE PROFIT penceresi için - sadece ilk adım otomatik
        elif "short take profit" in window_title:
            if self.chain_state == 'SHORT_TP_BID':
                print("[PSFAlgo2 CHAIN 13] Short TP veri hazır, bid buy mantığı çalıştırılıyor...")
                self.run_short_tp_bid_buy_data_ready()
            elif self.chain_state == 'SHORT_TP_FRONT':
                print("[PSFAlgo2 CHAIN 14] Short TP veri hazır, front buy mantığı çalıştırılıyor...")
                self.run_short_tp_front_buy_data_ready()
            else:
                print(f"[PSFAlgo2] ⏸️ Short TP penceresi açıldı ama chain_state={self.chain_state}, otomatik işlem yok")
                
        else:
            print(f"[PSFAlgo2] ⏸️ Pencere '{window.title()}' için otomatik işlem yapılmıyor (chain_state: {self.chain_state})")

    def run_t_top_losers_data_ready(self):
        """9. ADIM DATA READY: T-top losers akıllı seçim mantığı"""
        print("[PSFAlgo2 CHAIN 9] T-top losers veri hazır, akıllı seçim başlatılıyor...")
        
        # Eğer onay bekliyorsak, otomatik işlem yapma
        if self.waiting_for_approval:
            print("[PSFAlgo2 CHAIN] ⏸️ Onay bekleniyor, otomatik işlem yapılmıyor")
            return
        
        if not self.current_window:
            print("[PSFAlgo2 CHAIN 9] ❌ Mevcut pencere yok")
            self.advance_chain()
            return
        
        # AKILLI SEÇİM: Final BB skor'una göre en yüksek 5 hisse seç
        try:
            rows = self.current_window.rows
            columns = self.current_window.COLUMNS
            
            if not rows:
                print("[PSFAlgo2 CHAIN 9] ❌ Veri yok")
                self.advance_chain()
                return
            
            # Final BB skor kolonunu bul
            try:
                bb_score_index = columns.index('Final BB skor')
            except ValueError:
                print("[PSFAlgo2 CHAIN 9] ❌ Final BB skor kolonu bulunamadı")
                self.advance_chain()
                return
            
            # Geçerli skorları olan hisseleri topla
            valid_stocks = []
            for row in rows:
                try:
                    if len(row) <= max(1, bb_score_index):
                        continue
                        
                    ticker = row[1] if len(row) > 1 else ""
                    score_str = row[bb_score_index] if len(row) > bb_score_index else ""
                    
                    if not ticker or not score_str:
                        continue
                    
                    # ✅ EXCLUDE LIST kontrolü
                    if ticker in self.exclude_list:
                        print(f"[PSFAlgo2 CHAIN 9] ⏭️ {ticker} exclude listesinde, atlanıyor")
                        continue
                    
                    # Score'u float'a çevir
                    try:
                        score = float(score_str)
                    except (ValueError, TypeError):
                        continue
                    
                    # Skor > 0 olanları al (geçerli skorlar)
                    if score > 0:
                        valid_stocks.append((ticker, score))
                        
                except Exception as e:
                    continue
            
            if not valid_stocks:
                print("[PSFAlgo2 CHAIN 9] ❌ Final BB skor için geçerli hisse bulunamadı")
                self.advance_chain()
                return
            
            # En yüksek 5 BB skorunu seç
            valid_stocks.sort(key=lambda x: x[1], reverse=True)
            selected_stocks = valid_stocks[:5]
            
            selected_tickers = set([ticker for ticker, score in selected_stocks])
            self.current_window.selected_tickers = selected_tickers
            
            print(f"[PSFAlgo2 CHAIN 9] 🚀 Akıllı seçim: {len(selected_tickers)} hisse seçildi (Final BB skor)")
            for ticker, score in selected_stocks:
                print(f"[PSFAlgo2 CHAIN 9]   {ticker}: Final BB skor = {score}")
                
            # Onay bekleme durumunu aktif et
            self.waiting_for_approval = True
            
            # Bid buy butonunu tetikle
            self.current_window.send_bid_buy_orders()
            print("[PSFAlgo2 CHAIN 9] T-Losers akıllı seçim onay penceresi açıldı...")
                
        except Exception as e:
            print(f"[PSFAlgo2 CHAIN 9] ❌ Hata: {e}")
            self.advance_chain()

    def run_t_top_gainers_data_ready(self):
        """10. ADIM DATA READY: T-top gainers akıllı seçim mantığı"""
        print("[PSFAlgo2 CHAIN 10] T-top gainers veri hazır, akıllı seçim başlatılıyor...")
        
        # Eğer onay bekliyorsak, otomatik işlem yapma
        if self.waiting_for_approval:
            print("[PSFAlgo2 CHAIN] ⏸️ Onay bekleniyor, otomatik işlem yapılmıyor")
            return
        
        if not self.current_window:
            print("[PSFAlgo2 CHAIN 10] ❌ Mevcut pencere yok")
            self.advance_chain()
            return
        
        # AKILLI SEÇİM: Final AS skor'una göre EN DÜŞÜK 5 hisse seç (satış için en iyi)
        try:
            rows = self.current_window.rows
            columns = self.current_window.COLUMNS
            
            if not rows:
                print("[PSFAlgo2 CHAIN 10] ❌ Veri yok")
                self.advance_chain()
                return
            
            # Final AS skor kolonunu bul
            try:
                as_score_index = columns.index('Final AS skor')
            except ValueError:
                print("[PSFAlgo2 CHAIN 10] ❌ Final AS skor kolonu bulunamadı")
                self.advance_chain()
                return
            
            # Geçerli skorları olan hisseleri topla
            valid_stocks = []
            for row in rows:
                try:
                    if len(row) <= max(1, as_score_index):
                        continue
                        
                    ticker = row[1] if len(row) > 1 else ""
                    score_str = row[as_score_index] if len(row) > as_score_index else ""
                    
                    if not ticker or not score_str:
                        continue
                    
                    # ✅ EXCLUDE LIST kontrolü
                    if ticker in self.exclude_list:
                        print(f"[PSFAlgo2 CHAIN 10] ⏭️ {ticker} exclude listesinde, atlanıyor")
                        continue
                    
                    # Score'u float'a çevir
                    try:
                        score = float(score_str)
                    except (ValueError, TypeError):
                        continue
                    
                    # Skor > 0 ve <= 1500 olanları al (geçerli skorlar)
                    if 0 < score <= 1500:
                        valid_stocks.append((ticker, score))
                        
                except Exception as e:
                    continue
            
            if not valid_stocks:
                print("[PSFAlgo2 CHAIN 10] ❌ Final AS skor için geçerli hisse bulunamadı")
                self.advance_chain()
                return
            
            # EN DÜŞÜK 5 AS skorunu seç (satış için en iyi)
            valid_stocks.sort(key=lambda x: x[1], reverse=False)  # EN DÜŞÜK önce
            selected_stocks = valid_stocks[:5]
            
            selected_tickers = set([ticker for ticker, score in selected_stocks])
            self.current_window.selected_tickers = selected_tickers
            
            print(f"[PSFAlgo2 CHAIN 10] 🚀 Akıllı seçim: {len(selected_tickers)} hisse seçildi (Final AS skor - EN DÜŞÜK = EN İYİ SATIŞ)")
            for ticker, score in selected_stocks:
                print(f"[PSFAlgo2 CHAIN 10]   {ticker}: Final AS skor = {score}")
                
            # Onay bekleme durumunu aktif et
            self.waiting_for_approval = True
            
            # Ask sell butonunu tetikle
            self.current_window.send_ask_sell_orders()
            print("[PSFAlgo2 CHAIN 10] T-Gainers akıllı seçim onay penceresi açıldı...")
                
        except Exception as e:
            print(f"[PSFAlgo2 CHAIN 10] ❌ Hata: {e}")
            self.advance_chain()

    def run_long_tp_ask_sell_data_ready(self):
        """11. ADIM DATA READY: Long TP Ask Sell akıllı seçim mantığı"""
        print("[PSFAlgo2 CHAIN 11] Long TP Ask Sell veri hazır, akıllı seçim başlatılıyor...")
        
        # Eğer onay bekliyorsak, otomatik işlem yapma
        if self.waiting_for_approval:
            print("[PSFAlgo2 CHAIN] ⏸️ Onay bekleniyor, otomatik işlem yapılmıyor")
            return
        
        if not self.current_window:
            print("[PSFAlgo2 CHAIN 11] ❌ Mevcut pencere yok")
            self.advance_chain()
            return
        
        # AKILLI SEÇİM: Final AS skor'una göre EN DÜŞÜK 3 hisse seç (TP için daha az)
        try:
            rows = self.current_window.rows
            columns = self.current_window.COLUMNS
            
            if not rows:
                print("[PSFAlgo2 CHAIN 11] ❌ Veri yok")
                self.advance_chain()
                return
            
            # Final AS skor kolonunu bul
            try:
                as_score_index = columns.index('Final AS skor')
            except ValueError:
                print("[PSFAlgo2 CHAIN 11] ❌ Final AS skor kolonu bulunamadı")
                self.advance_chain()
                return
            
            # Geçerli skorları olan hisseleri topla
            valid_stocks = []
            for row in rows:
                try:
                    if len(row) <= max(1, as_score_index):
                        continue
                        
                    ticker = row[1] if len(row) > 1 else ""
                    score_str = row[as_score_index] if len(row) > as_score_index else ""
                    
                    if not ticker or not score_str:
                        continue
                    
                    # ✅ EXCLUDE LIST kontrolü
                    if ticker in self.exclude_list:
                        print(f"[PSFAlgo2 CHAIN 11] ⏭️ {ticker} exclude listesinde, atlanıyor")
                        continue
                    
                    # Score'u float'a çevir
                    try:
                        score = float(score_str)
                    except (ValueError, TypeError):
                        continue
                    
                    # Skor > 0 ve <= 1500 olanları al (geçerli skorlar)
                    if 0 < score <= 1500:
                        valid_stocks.append((ticker, score))
                        
                except Exception as e:
                    continue
            
            if not valid_stocks:
                print("[PSFAlgo2 CHAIN 11] ❌ Final AS skor için geçerli hisse bulunamadı")
                self.advance_chain()
                return
            
            # EN DÜŞÜK 3 AS skorunu seç (TP için)
            valid_stocks.sort(key=lambda x: x[1], reverse=False)  # EN DÜŞÜK önce
            selected_stocks = valid_stocks[:3]
            
            selected_tickers = set([ticker for ticker, score in selected_stocks])
            self.current_window.selected_tickers = selected_tickers
            
            print(f"[PSFAlgo2 CHAIN 11] 🚀 Akıllı seçim: {len(selected_tickers)} long TP seçildi (Final AS skor - EN DÜŞÜK = EN İYİ SATIŞ)")
            for ticker, score in selected_stocks:
                print(f"[PSFAlgo2 CHAIN 11]   {ticker}: Final AS skor = {score}")
                
            # Onay bekleme durumunu aktif et
            self.waiting_for_approval = True
            
            # Ask sell butonunu tetikle
            self.current_window.send_ask_sell_orders()
            print("[PSFAlgo2 CHAIN 11] Long TP Ask Sell akıllı seçim onay penceresi açıldı...")
                
        except Exception as e:
            print(f"[PSFAlgo2 CHAIN 11] ❌ Hata: {e}")
            self.advance_chain()

    def run_long_tp_front_sell_data_ready(self):
        """12. ADIM DATA READY: Long TP Front Sell akıllı seçim mantığı"""
        print("[PSFAlgo2 CHAIN 12] Long TP Front Sell veri hazır, akıllı seçim başlatılıyor...")
        
        # Eğer onay bekliyorsak, otomatik işlem yapma
        if self.waiting_for_approval:
            print("[PSFAlgo2 CHAIN] ⏸️ Onay bekleniyor, otomatik işlem yapılmıyor")
            return
        
        if not self.current_window:
            print("[PSFAlgo2 CHAIN 12] ❌ Mevcut pencere yok")
            self.advance_chain()
            return
        
        # AKILLI SEÇİM: Final FS skor'una göre EN DÜŞÜK hisseler + 12 adaydan seçim
        try:
            rows = self.current_window.rows
            columns = self.current_window.COLUMNS
            
            if not rows:
                print("[PSFAlgo2 CHAIN 12] ❌ Veri yok")
                self.advance_chain()
                return
            
            # Final FS skor kolonunu bul
            try:
                fs_score_index = columns.index('Final FS skor')
            except ValueError:
                print("[PSFAlgo2 CHAIN 12] ❌ Final FS skor kolonu bulunamadı")
                self.advance_chain()
                return
            
            # Geçerli skorları olan hisseleri topla
            valid_stocks = []
            for row in rows:
                try:
                    if len(row) <= max(1, fs_score_index):
                        continue
                        
                    ticker = row[1] if len(row) > 1 else ""
                    score_str = row[fs_score_index] if len(row) > fs_score_index else ""
                    
                    if not ticker or not score_str:
                        continue
                    
                    # ✅ EXCLUDE LIST kontrolü
                    if ticker in self.exclude_list:
                        print(f"[PSFAlgo2 CHAIN 12] ⏭️ {ticker} exclude listesinde, atlanıyor")
                        continue
                    
                    # Score'u float'a çevir
                    try:
                        score = float(score_str)
                    except (ValueError, TypeError):
                        continue
                    
                    # Skor > 0 ve <= 1500 olanları al (geçerli skorlar)
                    if 0 < score <= 1500:
                        valid_stocks.append((ticker, score))
                        
                except Exception as e:
                    continue
            
            if not valid_stocks:
                print("[PSFAlgo2 CHAIN 12] ❌ Final FS skor için geçerli hisse bulunamadı")
                self.advance_chain()
                return
            
            # EN DÜŞÜK skorları sırala (front sell için en iyi)
            valid_stocks.sort(key=lambda x: x[1], reverse=False)  # EN DÜŞÜK önce
            
            # ✅ 12 adaydan akıllı seçim yap (front spread kontrolü dahil)
            max_candidates = min(12, len(valid_stocks))
            candidate_stocks = valid_stocks[:max_candidates]
            
            print(f"[PSFAlgo2 CHAIN 12] 📊 En iyi {max_candidates} aday arasından 3 adet seçilecek")
            
            # Front spread ve çakışma kontrolü ile filtrele
            filtered_stocks = self.filter_stocks_with_front_validation(
                candidate_stocks, 
                'SELL', 
                self.current_window,
                target_count=3,
                is_front_order=True
            )
            
            if not filtered_stocks:
                print("[PSFAlgo2 CHAIN 12] ❌ Spread/çakışma kontrolü sonrası uygun hisse bulunamadı")
                self.advance_chain()
                return
            
            selected_tickers = set([ticker for ticker, score in filtered_stocks])
            self.current_window.selected_tickers = selected_tickers
            
            print(f"[PSFAlgo2 CHAIN 12] 🚀 Akıllı seçim: {len(selected_tickers)} long TP seçildi (Final FS skor - EN DÜŞÜK = EN İYİ SATIŞ)")
            for ticker, score in filtered_stocks:
                print(f"[PSFAlgo2 CHAIN 12]   {ticker}: Final FS skor = {score}")
                
            # Onay bekleme durumunu aktif et
            self.waiting_for_approval = True
            
            # Front sell butonunu tetikle
            self.current_window.send_front_sell_orders()
            print("[PSFAlgo2 CHAIN 12] Long TP Front Sell akıllı seçim onay penceresi açıldı...")
                
        except Exception as e:
            print(f"[PSFAlgo2 CHAIN 12] ❌ Hata: {e}")
            self.advance_chain()

    def run_short_tp_bid_buy_data_ready(self):
        """13. ADIM DATA READY: Short TP Bid Buy akıllı seçim mantığı"""
        print("[PSFAlgo2 CHAIN 13] Short TP Bid Buy veri hazır, akıllı seçim başlatılıyor...")
        
        # Eğer onay bekliyorsak, otomatik işlem yapma
        if self.waiting_for_approval:
            print("[PSFAlgo2 CHAIN] ⏸️ Onay bekleniyor, otomatik işlem yapılmıyor")
            return
        
        if not self.current_window:
            print("[PSFAlgo2 CHAIN 13] ❌ Mevcut pencere yok")
            self.advance_chain()
            return
        
        # AKILLI SEÇİM: Final BB skor'una göre en yüksek 3 hisse seç (TP için daha az)
        try:
            rows = self.current_window.rows
            columns = self.current_window.COLUMNS
            
            if not rows:
                print("[PSFAlgo2 CHAIN 13] ❌ Veri yok")
                self.advance_chain()
                return
            
            # Final BB skor kolonunu bul
            try:
                bb_score_index = columns.index('Final BB skor')
            except ValueError:
                print("[PSFAlgo2 CHAIN 13] ❌ Final BB skor kolonu bulunamadı")
                self.advance_chain()
                return
            
            # Geçerli skorları olan hisseleri topla
            valid_stocks = []
            for row in rows:
                try:
                    if len(row) <= max(1, bb_score_index):
                        continue
                        
                    ticker = row[1] if len(row) > 1 else ""
                    score_str = row[bb_score_index] if len(row) > bb_score_index else ""
                    
                    if not ticker or not score_str:
                        continue
                    
                    # ✅ EXCLUDE LIST kontrolü
                    if ticker in self.exclude_list:
                        print(f"[PSFAlgo2 CHAIN 13] ⏭️ {ticker} exclude listesinde, atlanıyor")
                        continue
                    
                    # Score'u float'a çevir
                    try:
                        score = float(score_str)
                    except (ValueError, TypeError):
                        continue
                    
                    # Skor > 0 olanları al (geçerli skorlar)
                    if score > 0:
                        valid_stocks.append((ticker, score))
                        
                except Exception as e:
                    continue
            
            if not valid_stocks:
                print("[PSFAlgo2 CHAIN 13] ❌ Final BB skor için geçerli hisse bulunamadı")
                self.advance_chain()
                return
            
            # En yüksek 3 BB skorunu seç (TP için)
            valid_stocks.sort(key=lambda x: x[1], reverse=True)
            selected_stocks = valid_stocks[:3]
            
            selected_tickers = set([ticker for ticker, score in selected_stocks])
            self.current_window.selected_tickers = selected_tickers
            
            print(f"[PSFAlgo2 CHAIN 13] 🚀 Akıllı seçim: {len(selected_tickers)} short TP seçildi (Final BB skor)")
            for ticker, score in selected_stocks:
                print(f"[PSFAlgo2 CHAIN 13]   {ticker}: Final BB skor = {score}")
                
            # Onay bekleme durumunu aktif et
            self.waiting_for_approval = True
            
            # Bid buy butonunu tetikle
            self.current_window.send_bid_buy_orders()
            print("[PSFAlgo2 CHAIN 13] Short TP Bid Buy akıllı seçim onay penceresi açıldı...")
                
        except Exception as e:
            print(f"[PSFAlgo2 CHAIN 13] ❌ Hata: {e}")
            self.advance_chain()

    def run_short_tp_front_buy_data_ready(self):
        """14. ADIM DATA READY: Short TP Front Buy akıllı seçim mantığı"""
        print("[PSFAlgo2 CHAIN 14] Short TP Front Buy veri hazır, akıllı seçim başlatılıyor...")
        
        # Eğer onay bekliyorsak, otomatik işlem yapma
        if self.waiting_for_approval:
            print("[PSFAlgo2 CHAIN] ⏸️ Onay bekleniyor, otomatik işlem yapılmıyor")
            return
        
        if not self.current_window:
            print("[PSFAlgo2 CHAIN 14] ❌ Mevcut pencere yok")
            self.advance_chain()
            return
        
        # AKILLI SEÇİM: Final FB skor'una göre en yüksek 3 hisse seç (TP için daha az)
        try:
            rows = self.current_window.rows
            columns = self.current_window.COLUMNS
            
            if not rows:
                print("[PSFAlgo2 CHAIN 14] ❌ Veri yok")
                self.advance_chain()
                return
            
            # Final FB skor kolonunu bul
            try:
                fb_score_index = columns.index('Final FB skor')
            except ValueError:
                print("[PSFAlgo2 CHAIN 14] ❌ Final FB skor kolonu bulunamadı")
                self.advance_chain()
                return
            
            # Geçerli skorları olan hisseleri topla
            valid_stocks = []
            for row in rows:
                try:
                    if len(row) <= max(1, fb_score_index):
                        continue
                        
                    ticker = row[1] if len(row) > 1 else ""
                    score_str = row[fb_score_index] if len(row) > fb_score_index else ""
                    
                    if not ticker or not score_str:
                        continue
                    
                    # ✅ EXCLUDE LIST kontrolü
                    if ticker in self.exclude_list:
                        print(f"[PSFAlgo2 CHAIN 14] ⏭️ {ticker} exclude listesinde, atlanıyor")
                        continue
                    
                    # Score'u float'a çevir
                    try:
                        score = float(score_str)
                    except (ValueError, TypeError):
                        continue
                    
                    # Skor > 0 olanları al (geçerli skorlar)
                    if score > 0:
                        valid_stocks.append((ticker, score))
                        
                except Exception as e:
                    continue
            
            if not valid_stocks:
                print("[PSFAlgo2 CHAIN 14] ❌ Final FB skor için geçerli hisse bulunamadı")
                self.advance_chain()
                return
            
            # En yüksek 3 FB skorunu seç (TP için)
            valid_stocks.sort(key=lambda x: x[1], reverse=True)
            selected_stocks = valid_stocks[:3]
            
            selected_tickers = set([ticker for ticker, score in selected_stocks])
            self.current_window.selected_tickers = selected_tickers
            
            print(f"[PSFAlgo2 CHAIN 14] 🚀 Akıllı seçim: {len(selected_tickers)} short TP seçildi (Final FB skor)")
            for ticker, score in selected_stocks:
                print(f"[PSFAlgo2 CHAIN 14]   {ticker}: Final FB skor = {score}")
                
            # Onay bekleme durumunu aktif et
            self.waiting_for_approval = True
            
            # Front buy butonunu tetikle
            self.current_window.send_front_buy_orders()
            print("[PSFAlgo2 CHAIN 14] Short TP Front Buy akıllı seçim onay penceresi açıldı...")
                
        except Exception as e:
            print(f"[PSFAlgo2 CHAIN 14] ❌ Hata: {e}")
            self.advance_chain()

    def get_chain_state_title(self):
        """Chain state'e göre pencere başlığı döndür"""
        state_titles = {
            'T_LOSERS_OLD': 'T-top Losers (Eski)',
            'T_GAINERS_OLD': 'T-top Gainers (Eski)',
            'LONG_TP_ASK': 'Long TP Ask Sell',
            'LONG_TP_FRONT': 'Long TP Front Sell',
            'SHORT_TP_BID': 'Short TP Bid Buy',
            'SHORT_TP_FRONT': 'Short TP Front Buy',
            'FINISHED': 'Tamamlandı'
        }
        return state_titles.get(self.chain_state, self.chain_state)

    def validate_front_order_before_sending(self, ticker, order_type, target_price):
        """
        Front emir göndermeden önce spread koşulunu kontrol et
        PSFAlgo1Utils'den aynı metodları kullan
        
        Args:
            ticker: Hisse senedi kodu
            order_type: 'front_buy' veya 'front_sell'
            target_price: Hedef emir fiyatı
        
        Returns:
            (bool, str): (emir_gönderilebilir_mi, açıklama_mesajı)
        """
        print(f"[PSFAlgo2 FRONT VALIDATION] {ticker} {order_type} @ {target_price:.3f} spread kontrolü...")
        
        # ✅ SPREAD BOYUTU KONTROLÜ - 0.06 centten küçükse kontrol yapma
        bid_price, ask_price = self.get_bid_ask_prices(ticker)
        
        if bid_price and ask_price and bid_price > 0 and ask_price > 0:
            spread = ask_price - bid_price
            
            if spread < 0.06:
                print(f"[PSFAlgo2 FRONT VALIDATION] ✅ {ticker} {order_type} - Spread çok dar ({spread:.4f} < 0.06), kontrol atlanıyor")
                return True, f"Dar spread ({spread:.4f} < 0.06) - kontrol atlandı"
            
            print(f"[PSFAlgo2 FRONT VALIDATION] 🔍 {ticker} {order_type} - Geniş spread ({spread:.4f} ≥ 0.06), kontrol yapılıyor")
        else:
            print(f"[PSFAlgo2 FRONT VALIDATION] ⚠️ {ticker} {order_type} - Bid/Ask alınamadı, kontrol yapılıyor")
        
        # Front spread koşulunu kontrol et
        is_valid, message = self.check_front_order_spread_condition(ticker, order_type, target_price)
        
        if is_valid:
            print(f"[PSFAlgo2 FRONT VALIDATION] ✅ {ticker} {order_type} - {message}")
            return True, message
        else:
            print(f"[PSFAlgo2 FRONT VALIDATION] ❌ {ticker} {order_type} - {message}")
            return False, message

    def check_front_order_spread_condition(self, ticker, order_type, target_price):
        """
        Front emirleri için spread*0.35 uzaklık kontrolü
        
        Args:
            ticker: Hisse senedi kodu
            order_type: 'front_buy' veya 'front_sell'
            target_price: Hedef emir fiyatı
        
        Returns:
            (bool, str): (koşul_sağlanıyor_mu, açıklama_mesajı)
        """
        try:
            # Market data'dan bid/ask bilgilerini al
            bid_price, ask_price = self.get_bid_ask_prices(ticker)
            
            if not bid_price or not ask_price or bid_price <= 0 or ask_price <= 0:
                return False, f"Bid/Ask fiyat bilgisi alınamadı - Bid: {bid_price}, Ask: {ask_price}"
            
            # Spread hesapla
            spread = ask_price - bid_price
            if spread <= 0:
                return False, f"Geçersiz spread: {spread:.4f} (Bid: {bid_price:.3f}, Ask: {ask_price:.3f})"
            
            # Spread*0.35 toleransını hesapla
            spread_tolerance = spread * 0.35
            
            if order_type.lower() == 'front_buy':
                # Front buy: bid'e uzaklık spread*0.35'ten fazla olmamalı
                distance_from_bid = target_price - bid_price
                
                if distance_from_bid > spread_tolerance:
                    return False, (f"Front buy koşulu ihlali - Hedef: {target_price:.3f}, "
                                 f"Bid: {bid_price:.3f}, Uzaklık: {distance_from_bid:.3f}, "
                                 f"Max izin: {spread_tolerance:.3f} (spread*0.35)")
                
                return True, (f"Front buy OK - Hedef: {target_price:.3f}, Bid: {bid_price:.3f}, "
                            f"Uzaklık: {distance_from_bid:.3f} ≤ {spread_tolerance:.3f}")
                
            elif order_type.lower() == 'front_sell':
                # Front sell: ask'a uzaklık spread*0.35'ten fazla olmamalı
                distance_from_ask = ask_price - target_price
                
                if distance_from_ask > spread_tolerance:
                    return False, (f"Front sell koşulu ihlali - Hedef: {target_price:.3f}, "
                                 f"Ask: {ask_price:.3f}, Uzaklık: {distance_from_ask:.3f}, "
                                 f"Max izin: {spread_tolerance:.3f} (spread*0.35)")
                
                return True, (f"Front sell OK - Hedef: {target_price:.3f}, Ask: {ask_price:.3f}, "
                            f"Uzaklık: {distance_from_ask:.3f} ≤ {spread_tolerance:.3f}")
            
            else:
                return False, f"Geçersiz emir türü: {order_type}"
                
        except Exception as e:
            return False, f"Front spread kontrolü hatası: {str(e)}"

    def get_bid_ask_prices(self, ticker):
        """
        Ticker için bid/ask fiyatlarını al
        
        Returns:
            (float, float): (bid_price, ask_price)
        """
        try:
            # IBKR'den market data al
            if hasattr(self.market_data, 'ib') and self.market_data.ib:
                # Contract oluştur
                from ib_insync import Stock
                contract = Stock(ticker, 'SMART', 'USD')
                
                # Market data iste
                ticker_data = self.market_data.ib.reqMktData(contract, '', False, False)
                
                # Kısa süre bekle (market data için)
                import time
                time.sleep(0.5)
                
                bid = getattr(ticker_data, 'bid', None)
                ask = getattr(ticker_data, 'ask', None)
                
                # Market data subscription'ı iptal et
                self.market_data.ib.cancelMktData(contract)
                
                if bid and ask and bid > 0 and ask > 0:
                    return float(bid), float(ask)
            
            # IBKR'den alınamadıysa, pencere verisinden al
            if hasattr(self, 'current_window') and self.current_window:
                bid_price = self.get_price_from_window(self.current_window, ticker, 'Bid')
                ask_price = self.get_price_from_window(self.current_window, ticker, 'Ask')
                
                if bid_price and ask_price and bid_price > 0 and ask_price > 0:
                    return bid_price, ask_price
            
            # Son çare: current price'ın %0.5'i kadar spread varsay
            current_price = self.get_current_price(ticker)
            if current_price and current_price > 0:
                estimated_spread = current_price * 0.005  # %0.5 spread varsayımı
                bid = current_price - (estimated_spread / 2)
                ask = current_price + (estimated_spread / 2)
                return bid, ask
            
            return None, None
            
        except Exception as e:
            print(f"[PSFAlgo2 BID/ASK] {ticker} bid/ask alma hatası: {e}")
            return None, None

    def get_price_from_window(self, window, ticker, price_column):
        """Pencereden belirli ticker için fiyat bilgisini al"""
        try:
            if not hasattr(window, 'rows') or not hasattr(window, 'COLUMNS'):
                return None
                
            rows = window.rows
            columns = window.COLUMNS
            
            if price_column not in columns:
                return None
                
            price_index = columns.index(price_column)
            
            for row in rows:
                if len(row) > 1 and row[1] == ticker and len(row) > price_index:
                    try:
                        return float(row[price_index])
                    except (ValueError, TypeError):
                        continue
            
            return None
            
        except Exception as e:
            print(f"[PSFAlgo2 PRICE FROM WINDOW] ❌ {ticker} fiyat alma hatası: {e}")
            return None

    def get_current_price(self, ticker):
        """Ticker için current price al"""
        try:
            # Market data'dan current price al
            if hasattr(self.market_data, 'get_current_price'):
                return self.market_data.get_current_price(ticker)
            
            # Pencereden current price al
            if hasattr(self, 'current_window') and self.current_window:
                return self.get_price_from_window(self.current_window, ticker, 'Last price')
            
            return None
            
        except Exception as e:
            print(f"[PSFAlgo2 CURRENT PRICE] ❌ {ticker} current price alma hatası: {e}")
            return None

    def filter_stocks_with_front_validation(self, candidate_stocks, order_side, window, target_count=3, is_front_order=False):
        """
        PSFAlgo2 için akıllı filtreleme:
        1. Mevcut emirlerle çakışan hisseleri çıkar (±0.08 toleransı)
        2. Front emirler için spread kontrolü yap (spread ≥ 0.06 ise)
        3. Hedef sayıya ulaşmaya çalış
        
        Args:
            candidate_stocks: [(ticker, score), ...] listesi
            order_side: 'BUY' veya 'SELL'
            window: Pencere objesi
            target_count: Hedef hisse sayısı
            is_front_order: Front emir mi?
        
        Returns:
            [(ticker, score), ...] filtrelenmiş liste
        """
        print(f"[PSFAlgo2 FILTER] 🔍 {len(candidate_stocks)} aday hisse için filtreleme...")
        
        filtered_stocks = []
        
        for ticker, score in candidate_stocks:
            # Hedef fiyatı belirle
            target_price = self.get_price_from_window_for_order(window, ticker, order_side)
            
            if not target_price or target_price <= 0:
                print(f"[PSFAlgo2 FILTER] ⚠️ {ticker} için fiyat alınamadı, atlanıyor")
                continue
            
            # 1. Çakışma kontrolü yap (eğer order manager varsa)
            if hasattr(self, 'order_manager') and self.order_manager:
                has_conflict = self.check_order_conflict(ticker, target_price, order_side)
                if has_conflict:
                    print(f"[PSFAlgo2 FILTER] ⏭️ {ticker} çakışma nedeniyle atlandı")
                    continue
            
            # 2. Front emir spread kontrolü
            if is_front_order:
                front_order_type = 'front_buy' if order_side == 'BUY' else 'front_sell'
                
                is_valid, spread_msg = self.validate_front_order_before_sending(ticker, front_order_type, target_price)
                
                if not is_valid:
                    print(f"[PSFAlgo2 FILTER] ⏭️ {ticker} front spread kontrolü başarısız: {spread_msg}")
                    continue  # Bu hisseyi atla, sonraki adaya geç
            
            # Tüm kontroller başarılı
            filtered_stocks.append((ticker, score))
            print(f"[PSFAlgo2 FILTER] ✅ {ticker} eklendi (fiyat: {target_price:.3f})")
            
            # Hedef sayıya ulaştık mı?
            if len(filtered_stocks) >= target_count:
                break
        
        print(f"[PSFAlgo2 FILTER] 📊 {len(candidate_stocks)} → {len(filtered_stocks)} hisse (filtreleme sonrası)")
        
        return filtered_stocks
    
    def get_price_from_window_for_order(self, window, ticker, order_side):
        """Pencereden emir türüne göre uygun fiyatı al"""
        try:
            if not hasattr(window, 'rows') or not hasattr(window, 'COLUMNS'):
                return self.get_current_price(ticker)
                
            rows = window.rows
            columns = window.COLUMNS
            
            # Emir türüne göre fiyat kolonu belirle
            if order_side == 'BUY':
                price_columns = ['Bid', 'Current Price', 'Last']
            else:
                price_columns = ['Ask', 'Current Price', 'Last']
            
            # Ticker'ın satırını bul
            for row in rows:
                if len(row) > 1 and row[1] == ticker:
                    # Uygun fiyat kolonunu bul ve kullan
                    for price_col in price_columns:
                        if price_col in columns:
                            price_index = columns.index(price_col)
                            if len(row) > price_index:
                                try:
                                    price = float(row[price_index])
                                    if price > 0:
                                        return price
                                except (ValueError, TypeError):
                                    continue
                    break
            
            # Pencereden alınamazsa current price kullan
            return self.get_current_price(ticker)
            
        except Exception as e:
            print(f"[PSFAlgo2 PRICE] ❌ {ticker} fiyat alma hatası: {e}")
            return self.get_current_price(ticker)
    
    def check_order_conflict(self, ticker, target_price, order_side, tolerance=0.08):
        """Basit çakışma kontrolü"""
        # Şimdilik basit implementasyon - geliştirilecek
        return False 