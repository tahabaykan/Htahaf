import pandas as pd
import threading
import time
from datetime import datetime
import logging
from Htahaf.utils.bdata_storage import BDataStorage
from Htahaf.utils.reasoning_logger import log_reasoning
from Htahaf.psfalgo1_chain import PSFAlgo1Chain
from Htahaf.psfalgo1_orders import PSFAlgo1Orders
from Htahaf.psfalgo1_utils import PSFAlgo1Utils

class PsfAlgo1(PSFAlgo1Chain, PSFAlgo1Orders, PSFAlgo1Utils):
    """
    PSFAlgo1 - YENİ 8 ADIMLI SİSTEM (1-8)
    T_LOSERS → T_LOSERS_FB → T_GAINERS → T_GAINERS_FS → 
    LONG_TP_AS → LONG_TP_FS → SHORT_TP_BB → SHORT_TP_FB → PSFAlgo2'ye devir
    """
    
    def __init__(self, market_data, exclude_list=None, order_manager=None):
        """PSFAlgo1 - YENİ 8 ADIMLI SİSTEM başlatıcısı"""
        
        # Logger ayarla
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        self.logger.info("PsfAlgo1 initialized - YENİ 8 ADIMLI SİSTEM (1-8) - INACTIVE by default")
        
        # Temel özellikler
        self.market_data = market_data
        self.exclude_list = exclude_list or []
        self.order_manager = order_manager
        self.is_active = False
        self.current_window = None
        self.main_window = None
        self.psfalgo2 = None
        
        # Chain durumu - YENİ 8 ADIMLI SİSTEM
        self.chain_state = 'T_LOSERS'  # Başlangıç durumu
        self.pisdongu_cycle_count = 0
        
        # Günlük fill takibi
        self.daily_fills = {}
        self.daily_reverse_orders = {}
        
        # BEFDAY pozisyon limitleri
        self.befday_positions = {}
        self.daily_position_limits = {}
        
        # Onay bekleme durumu
        self.waiting_for_approval = False
        
        # Veri kaynakları
        self.bdata_storage = BDataStorage()
        self.scores_df = pd.DataFrame()
        
        # BEFDAY pozisyon limitlerini yükle
        self.load_befday_positions()
        
        # Veri kaynaklarını güncelle
        self.update_data_sources()
        
        # Otomatik fill kontrolü başlat
        self.start_auto_fill_check()
        
        # Pozisyon tersine çevirme kontrolü başlat
        self.check_and_prevent_position_reversal()
        
        self.logger.info("PsfAlgo initialized - INACTIVE by default")

    def set_main_window(self, main_window):
        """Ana pencere referansını ayarla"""
        self.main_window = main_window
        print("[PSFAlgo1] Ana pencere referansı ayarlandı")

    def set_psfalgo2(self, psfalgo2):
        """PSFAlgo2 referansını ayarla"""
        self.psfalgo2 = psfalgo2
        print("[PSFAlgo1] PSFAlgo2 referansı ayarlandı")

    def reactivate_from_psfalgo2(self, cycle_count, daily_fills, befday_positions, daily_position_limits):
        """PSFAlgo2'den geri devir alındığında reaktive et"""
        print(f"[PSFAlgo1] 🔄 PSFAlgo2'den geri devir alındı - Cycle: {cycle_count}")
        
        # Veri senkronizasyonu
        self.pisdongu_cycle_count = cycle_count
        self.daily_fills = daily_fills
        self.befday_positions = befday_positions
        self.daily_position_limits = daily_position_limits
        
        # Yeni döngü başlat
        self.start_pisdongu_cycle()

    def activate(self):
        """PSFAlgo1'i aktif et"""
        if self.is_active:
            print("🟡 PSFAlgo1 ZATEN AKTİF")
            return
            
        self.is_active = True
        print("🟢 PSFAlgo1 AÇIK - YENİ 8 ADIMLI SİSTEM başlatılıyor")
        
        # Veri kaynaklarını güncelle
        self.update_data_sources()
        
        # İlk PISDoNGU döngüsünü başlat
        self.start_pisdongu_cycle()

    def deactivate(self):
        """PSFAlgo1'i pasif et"""
        if not self.is_active:
            print("🟡 PSFAlgo1 ZATEN PASİF")
            return
            
        self.is_active = False
        print("🔴 PSFAlgo1 KAPALI")
        
        # Mevcut pencereleri kapat
        self.close_current_windows()
        
        # Onay bekleme durumunu sıfırla
        self.waiting_for_approval = False

    def start_pisdongu_cycle(self):
        """Yeni PISDoNGU döngüsü başlat"""
        if not self.is_active:
            print("[PSFAlgo1] ⏸️ PSFAlgo1 pasif - PISDoNGU başlatılmadı")
            return
            
        self.pisdongu_cycle_count += 1
        print(f"[PSFAlgo1] 🔄 PISDoNGU Döngü #{self.pisdongu_cycle_count} başlatılıyor...")
        
        # Chain'i başlangıç durumuna getir
        self.chain_state = 'T_LOSERS'
        self.waiting_for_approval = False
        
        # Veri kaynaklarını güncelle
        self.update_data_sources()
        
        # ✅ İlk adımı başlat - sadece T_LOSERS
        print("[PSFAlgo1] 🚀 1. ADIM: T-Losers BID BUY başlatılıyor...")
        self.start_chain()

    def load_befday_positions(self):
        """BEFDAY pozisyon limitlerini yükle"""
        try:
            df = pd.read_csv('BEFDAY.csv')
            self.befday_positions = {}
            self.daily_position_limits = {}
            
            for _, row in df.iterrows():
                ticker = row['PREF IBKR']
                starting_pos = int(row['Starting Position'])
                
                # Günlük limit: başlangıç pozisyonundan ±600
                min_limit = starting_pos - 600
                max_limit = starting_pos + 600
                
                self.befday_positions[ticker] = starting_pos
                self.daily_position_limits[ticker] = (min_limit, max_limit)
                
                print(f"[BEFDAY] {ticker}: Başlangıç={starting_pos}, Limit=[{min_limit}, {max_limit}]")
            
            print(f"[BEFDAY] ✅ {len(self.befday_positions)} hisse için limit yüklendi")
            
        except FileNotFoundError:
            print("[BEFDAY] ⚠️ BEFDAY.csv dosyası bulunamadı")
            self.befday_positions = {}
            self.daily_position_limits = {}
        except Exception as e:
            print(f"[BEFDAY] ❌ Limit yükleme hatası: {e}")
            self.befday_positions = {}
            self.daily_position_limits = {}

    def update_data_sources(self):
        """Veri kaynaklarını güncelle"""
        try:
            # Scored stocks verilerini yükle
            self.scores_df = pd.read_csv('scored_stocks.csv', index_col='PREF IBKR')
            print(f"[DATA] ✅ {len(self.scores_df)} hisse skoru yüklendi")
        except Exception as e:
            print(f"[DATA] ⚠️ Scored stocks yükleme hatası: {e}")
            self.scores_df = pd.DataFrame()

    def cancel_all_pending_orders(self):
        """Tüm bekleyen emirleri iptal et"""
        if not hasattr(self.market_data, 'ib') or not self.market_data.ib:
            print("[CANCEL ORDERS] ❌ IBKR bağlantısı yok")
            return
        
        print("[CANCEL ORDERS] 🗑️ Tüm bekleyen emirler iptal ediliyor...")
        
        # Ana thread'de çalıştır
        threading.Thread(target=self._cancel_orders_main_thread, daemon=True).start()

    def _cancel_orders_main_thread(self):
        """Ana thread'de emir iptali"""
        try:
            trades = self.market_data.ib.openTrades()
            cancel_count = 0
            
            for trade in trades:
                try:
                    self.market_data.ib.cancelOrder(trade.order)
                    cancel_count += 1
                    print(f"[CANCEL ORDERS] ✅ {trade.contract.symbol} emri iptal edildi")
                except Exception as e:
                    print(f"[CANCEL ORDERS] ❌ {trade.contract.symbol} iptal hatası: {e}")
            
            print(f"[CANCEL ORDERS] ✅ {cancel_count} emir iptal edildi")
            
        except Exception as e:
            print(f"[CANCEL ORDERS] ❌ Genel iptal hatası: {e}") 