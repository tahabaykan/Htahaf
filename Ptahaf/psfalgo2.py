import pandas as pd
from Ptahaf.utils.order_management import OrderManager, log_reasoning
import time
import logging
import os
import tkinter as tk
from tkinter import messagebox
import threading
import json
from datetime import datetime, timedelta, date
import sys
import math

# BDATA entegrasyonu için import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Ptahaf.utils.bdata_storage import BDataStorage

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
    def __init__(self, market_data, exclude_list=None, half_sized_list=None, order_manager=None):
        self.logger = logging.getLogger('PsfAlgo2')
        self.logger.info("PsfAlgo2 initialized - ESKİ 6 ADIMLI SİSTEM (9-14) - INACTIVE by default")
        
        # Temel değişkenler
        self.market_data = market_data
        self.order_manager = order_manager
        self.main_window = None
        self.current_window = None
        self.is_active = False
        self.data_ready = False
        
        # Dinamik lot sistemi - gelecekte ayarlanabilir
        self.default_lot_size = 200  # Şu anda 200, gelecekte AVG ADV oranına göre ayarlanabilir
        
        # BDATA entegrasyonu
        self.bdata_storage = BDataStorage('Ptahaf/data/bdata_fills.json')
        
        # BEFDAY pozisyonları (PSFAlgo1'den alınacak)
        self.befday_positions = {}
        
        self.exclude_list = exclude_list or set()
        self.half_sized_list = half_sized_list or set()
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
        
        # ✅ Cross-Step Company & MAXALW Tracking (PSFAlgo1'den paylaşılan)
        self.session_company_orders = {}  # PSFAlgo1'den alınacak
        
        # ✅ MAXALW size cache (performans için)
        self.maxalw_cache = {}  # {ticker: maxalw_size}
        
        # ✅ Günlük 600 lot limit takibi (PSFAlgo1'den alınacak)
        self.daily_order_totals = {}  # {ticker: {'BUY': total_lots, 'SELL': total_lots, 'date': date}}
        self.befday_update_status = {'updated': False, 'reason': 'PSFAlgo1\'den alınacak'}
        
        # ✅ Scored stocks verilerini yükle (şirket kontrolü için gerekli)
        self.scores_df = pd.DataFrame()
        self.load_scores_data()
        
        logger.info("PsfAlgo2 initialized - ESKİ 6 ADIMLI SİSTEM (9-14) - INACTIVE by default")

    def load_scores_data(self):
        """Scored stocks verilerini yükle"""
        try:
            self.scores_df = pd.read_csv('scored_stocks.csv', index_col='PREF IBKR')
            print(f"[PSFAlgo2 DATA] ✅ {len(self.scores_df)} hisse skoru yüklendi")
        except Exception as e:
            print(f"[PSFAlgo2 DATA] ⚠️ Scored stocks yükleme hatası: {e}")
            self.scores_df = pd.DataFrame()

    def extract_company_symbol(self, ticker):
        """
        Ticker'dan şirket adını çıkarır
        Örnekler: 'INN PRE' -> 'INN', 'PEB PRF' -> 'PEB', 'JAGX' -> 'JAGX'
        """
        if not ticker:
            return ""
        
        # Eğer boşluk varsa, ilk kısmı şirket adı olarak al
        if ' ' in ticker:
            return ticker.split(' ')[0]
        
        # Boşluk yoksa tüm ticker şirket adı
        return ticker
    
    def calculate_max_orders_for_company(self, company, candidate_list):
        """
        Belirli bir şirket için aday listesindeki toplam hisse sayısına göre
        maximum emir sayısını hesaplar
        
        Formül: min(3, max(1, round(total_stocks_for_company / 3)))
        """
        if not company or not candidate_list:
            return 1
        
        # Aynı şirketten kaç hisse var sayalım
        company_stocks_count = 0
        for candidate in candidate_list:
            ticker = candidate[0] if isinstance(candidate, (list, tuple)) else candidate
            if self.extract_company_symbol(ticker) == company:
                company_stocks_count += 1
        
        if company_stocks_count == 0:
            return 1
        
        # 3'e böl ve en yakın tam sayıya yuvarla
        calculated_max = round(company_stocks_count / 3)
        
        # Minimum 1, maksimum 3 sınırlarını uygula
        final_max = max(1, min(3, calculated_max))
        
        print(f"[PSFAlgo2 COMPANY LIMIT] {company}: {company_stocks_count} hisse → {company_stocks_count}/3 = {company_stocks_count/3:.2f} → max {final_max} emir")
        
        return final_max
    
    def filter_by_company_limits(self, candidate_list, max_selections=None):
        """
        Aday hisse listesini şirket bazlı emir limitlerine göre filtreler
        Her şirketten sadece izin verilen maksimum sayıda hisse seçer (en yüksek skorlu olanları)
        
        Args:
            candidate_list: [(ticker, score), ...] formatında aday listesi
            max_selections: Toplam seçilecek maksimum hisse sayısı (None = limit yok)
        
        Returns:
            Filtrelenmiş [(ticker, score), ...] listesi
        """
        if not candidate_list:
            return []
        
        print(f"[PSFAlgo2 COMPANY FILTER] 🔍 Şirket limiti uygulanıyor - {len(candidate_list)} aday")
        
        # Şirketlere göre grupla
        company_groups = {}
        for candidate in candidate_list:
            ticker = candidate[0] if isinstance(candidate, (list, tuple)) else candidate
            score = candidate[1] if isinstance(candidate, (list, tuple)) and len(candidate) > 1 else 0
            
            company = self.extract_company_symbol(ticker)
            if company not in company_groups:
                company_groups[company] = []
            
            company_groups[company].append((ticker, score))
        
        # Her şirket için maximum emir sayısını hesapla ve en yüksek skorluları seç
        filtered_candidates = []
        
        for company, company_candidates in company_groups.items():
            # Bu şirket için maksimum emir sayısını hesapla (tüm aday listeye göre)
            max_orders = self.calculate_max_orders_for_company(company, candidate_list)
            
            # Şirketin hisselerini score'a göre sırala (en yüksek score ilk)
            company_candidates_sorted = sorted(company_candidates, key=lambda x: x[1], reverse=True)
            
            # Maximum sayıda hisse seç
            selected_for_company = company_candidates_sorted[:max_orders]
            
            print(f"[PSFAlgo2 COMPANY FILTER] {company}: {len(company_candidates)} aday → {len(selected_for_company)} seçildi")
            for ticker, score in selected_for_company:
                print(f"[PSFAlgo2 COMPANY FILTER]   ✅ {ticker} (skor: {score:.2f})")
            
            # Seçilmeyenleri bildir
            if len(company_candidates_sorted) > max_orders:
                not_selected = company_candidates_sorted[max_orders:]
                print(f"[PSFAlgo2 COMPANY FILTER] {company}: {len(not_selected)} hisse elendi:")
                for ticker, score in not_selected:
                    print(f"[PSFAlgo2 COMPANY FILTER]   ❌ {ticker} (skor: {score:.2f}) - şirket limiti")
            
            filtered_candidates.extend(selected_for_company)
        
        # Eğer maksimum seçim sayısı belirtilmişse, son filtre uygula
        if max_selections and len(filtered_candidates) > max_selections:
            # Tüm listeden en yüksek skorluları seç
            filtered_candidates_sorted = sorted(filtered_candidates, key=lambda x: x[1], reverse=True)
            final_selection = filtered_candidates_sorted[:max_selections]
            
            print(f"[PSFAlgo2 COMPANY FILTER] 📊 Final seçim: {len(filtered_candidates)} → {len(final_selection)} (toplam limit)")
            
            return final_selection
        
        print(f"[PSFAlgo2 COMPANY FILTER] ✅ Toplam {len(filtered_candidates)} hisse seçildi")
        return filtered_candidates

    def get_scores_for_ticker(self, ticker):
        """Ticker için skorları döndür"""
        try:
            if not self.scores_df.empty and ticker in self.scores_df.index:
                row = self.scores_df.loc[ticker]
                return {
                    'FINAL_THG': float(row.get('FINAL_THG', 0)),
                    'bidbuy_ucuzluk': float(row.get('bidbuy_ucuzluk', 0)),
                    'asksell_pahali': float(row.get('asksell_pahali', 0))
                }
        except Exception:
            pass
        return {'FINAL_THG': 0, 'bidbuy_ucuzluk': 0, 'asksell_pahali': 0}

    def polygonize_ticker(self, ticker):
        """IBKR ticker'ını Polygon formatına çevir"""
        # Preferred stock formatını çevir: "ABC PRA" -> "ABC-PA"
        if ' PR' in ticker:
            base, pref = ticker.split(' PR')
            return f"{base}p{pref}"
        return ticker

    def validate_front_order_before_sending(self, ticker, order_type, target_price):
        """
        Front emir göndermeden önce spread koşulunu kontrol et
        
        Args:
            ticker: Hisse senedi kodu
            order_type: 'front_buy' veya 'front_sell'
            target_price: Hedef emir fiyatı
        
        Returns:
            (bool, str): (emir_gönderilebilir_mi, açıklama_mesajı)
        """
        print(f"[PSFAlgo2 FRONT VALIDATION] {ticker} {order_type} @ {target_price:.3f} spread kontrolü...")
        
        # SPREAD BOYUTU KONTROLÜ - 0.06 centten küçükse kontrol yapma
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
        is_valid, message = self.check_front_spread_condition(ticker, order_type, target_price)
        
        if is_valid:
            print(f"[PSFAlgo2 FRONT VALIDATION] ✅ {ticker} {order_type} - {message}")
            return True, message
        else:
            print(f"[PSFAlgo2 FRONT VALIDATION] ❌ {ticker} {order_type} - {message}")
            return False, message

    def check_front_spread_condition(self, ticker, order_type, target_price):
        """
        Front emirleri için spread*0.35 uzaklık kontrolü
        Args:
            ticker: Hisse kodu
            order_type: 'front_buy' veya 'front_sell'
            target_price: Emir fiyatı
        Returns:
            (bool, str): (koşul sağlanıyor mu, açıklama)
        """
        try:
            bid_price, ask_price = self.get_bid_ask_prices(ticker)
            if not bid_price or not ask_price or bid_price <= 0 or ask_price <= 0:
                return False, f"Bid/Ask fiyat bilgisi alınamadı - Bid: {bid_price}, Ask: {ask_price}"
            spread = ask_price - bid_price
            if spread <= 0:
                return False, f"Geçersiz spread: {spread:.4f} (Bid: {bid_price:.3f}, Ask: {ask_price:.3f})"
            spread_tolerance = spread * 0.35
            if order_type.lower() == 'front_buy':
                distance_from_bid = target_price - bid_price
                if distance_from_bid > spread_tolerance:
                    return False, (f"Front buy koşulu ihlali - Hedef: {target_price:.3f}, "
                                   f"Bid: {bid_price:.3f}, Uzaklık: {distance_from_bid:.3f}, "
                                   f"Max izin: {spread_tolerance:.3f} (spread*0.35)")
                return True, (f"Front buy OK - Hedef: {target_price:.3f}, Bid: {bid_price:.3f}, "
                              f"Uzaklık: {distance_from_bid:.3f} ≤ {spread_tolerance:.3f}")
            elif order_type.lower() == 'front_sell':
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

    def activate_from_psfalgo1(self, cycle_count, daily_fills, befday_positions, daily_position_limits, session_company_orders=None):
        """PSFAlgo1'den devir alındığında aktif et"""
        print(f"[PSFAlgo2] 🔄 PSFAlgo1'den devir alındı - Cycle: {cycle_count}")
        
        # Veri senkronizasyonu
        self.pisdongu_cycle_count = cycle_count
        self.daily_fills = daily_fills
        self.befday_positions = befday_positions
        self.daily_position_limits = daily_position_limits
        
        # ✅ Cross-step company tracking state'ini al
        if session_company_orders:
            self.sync_session_state(session_company_orders)
            
        # ✅ PSFAlgo1'den günlük totalleri ve BEFDAY durumunu al (psfalgo1 referansı varsa)
        if hasattr(self, 'psfalgo1') and self.psfalgo1:
            if hasattr(self.psfalgo1, 'daily_order_totals'):
                self.sync_daily_totals(self.psfalgo1.daily_order_totals)
            if hasattr(self.psfalgo1, 'befday_update_status'):
                self.sync_befday_status(self.psfalgo1.befday_update_status)
        
        # PSFAlgo2'yi aktif et
        self.is_active = True
        print("🟢 PSFAlgo2 AÇIK - ESKİ 6 ADIMLI SİSTEM (9-14) devam ediyor")
        print(f"[PSFAlgo2] 📊 Şirket emir geçmişi: {len(self.session_company_orders)} şirket")
        
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
        """✅ PSFAlgo2 TÜM ADIMLAR TAMAMLANDI - otomatik restart sistemi başlatılıyor"""
        print(f"[PSFAlgo2 CHAIN] ✅ ESKİ 6 adımlı sistem tamamlandı - Cycle #{self.pisdongu_cycle_count}")
        print(f"[PSFAlgo2 CHAIN] 🎯 PSFAlgo1 (8 adım) + PSFAlgo2 (6 adım) = 14 adım TÜM DÖNGÜ TAMAMLANDI!")
        
        # Mevcut pencereleri kapat
        self.close_current_windows()
        
        # PSFAlgo2'yi deaktive et
        self.is_active = False
        
        # PSFAlgo1'e geri devret
        if hasattr(self, 'psfalgo1') and self.psfalgo1:
            print("[PSFAlgo2 CHAIN] 🔄 PSFAlgo1'e devrediliyor - OTOMATİK RESTART sistemi başlatılacak...")
            print("[PSFAlgo2 CHAIN] 📋 RESTART ADIMI: Tüm onay/red alındıktan sonra 3 dk bekleyip veri güncelle + 1.adımdan restart")
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
                    
                    # ✅ KOMPLE EXCLUDE LIST kontrolü
                    if ticker in self.exclude_list:
                        print(f"[PSFAlgo2 CHAIN 9] ⏭️ {ticker} komple exclude listesinde, atlanıyor")
                        continue
                    
                    # ✅ HALF SIZED kontrolü - dinamik lot sistemi
                    if ticker in self.half_sized_list:
                        # Varsayılan lot boyutu (şu anda 200, gelecekte değişebilir)
                        intended_lot_size = getattr(self, 'default_lot_size', 200)
                        half_sized_lot = intended_lot_size // 2
                        minimum_lot_threshold = 200  # Minimum kabul edilebilir lot
                        
                        if intended_lot_size < 400:  # 400'ün altındaysa yarısı 200'den az olacak
                            print(f"[PSFAlgo2 CHAIN 9] ⏭️ {ticker} half-sized listesinde ({intended_lot_size} → {half_sized_lot} lot < {minimum_lot_threshold} minimum), atlanıyor")
                            continue
                        else:
                            print(f"[PSFAlgo2 CHAIN 9] ✅ {ticker} half-sized listesinde kabul edildi ({intended_lot_size} → {half_sized_lot} lot ≥ {minimum_lot_threshold})")
                    
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
            
            # ✅ Cross-step validation - şirket limiti ve MAXALW kontrolü
            cross_step_valid = self.filter_candidates_by_cross_step_rules(
                valid_stocks[:10],  # İlk 10'u kontrol et 
                step_number=9,
                order_side='BUY',
                target_count=5,  # 5 hisse hedefle
                extended_candidates=valid_stocks  # Elenen hisselerin yerine diğer adayları geçir
            )
            
            if not cross_step_valid:
                print("[PSFAlgo2 CHAIN 9] ❌ Cross-step validation sonrası hiçbir hisse kalmadı")
                self.advance_chain()
                return
            
            selected_stocks = cross_step_valid[:5]
            
            selected_tickers = set([ticker for ticker, score in selected_stocks])
            self.current_window.selected_tickers = selected_tickers
            
            print(f"[PSFAlgo2 CHAIN 9] 🚀 Akıllı seçim: {len(selected_tickers)} hisse seçildi (Final BB skor + cross-step validation)")
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
                    
                    # ✅ KOMPLE EXCLUDE LIST kontrolü
                    if ticker in self.exclude_list:
                        print(f"[PSFAlgo2 CHAIN 10] ⏭️ {ticker} komple exclude listesinde, atlanıyor")
                        continue
                    
                    # ✅ HALF SIZED kontrolü - dinamik lot sistemi
                    if ticker in self.half_sized_list:
                        # Varsayılan lot boyutu (şu anda 200, gelecekte değişebilir)
                        intended_lot_size = getattr(self, 'default_lot_size', 200)
                        half_sized_lot = intended_lot_size // 2
                        minimum_lot_threshold = 200  # Minimum kabul edilebilir lot
                        
                        if intended_lot_size < 400:  # 400'ün altındaysa yarısı 200'den az olacak
                            print(f"[PSFAlgo2 CHAIN 10] ⏭️ {ticker} half-sized listesinde ({intended_lot_size} → {half_sized_lot} lot < {minimum_lot_threshold} minimum), atlanıyor")
                            continue
                        else:
                            print(f"[PSFAlgo2 CHAIN 10] ✅ {ticker} half-sized listesinde kabul edildi ({intended_lot_size} → {half_sized_lot} lot ≥ {minimum_lot_threshold})")
                    
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
            
            # ✅ Cross-step validation - şirket limiti ve MAXALW kontrolü
            cross_step_valid = self.filter_candidates_by_cross_step_rules(
                valid_stocks[:10],  # İlk 10'u kontrol et 
                step_number=10,
                order_side='SELL',
                target_count=5,  # 5 hisse hedefle
                extended_candidates=valid_stocks  # Elenen hisselerin yerine diğer adayları geçir
            )
            
            if not cross_step_valid:
                print("[PSFAlgo2 CHAIN 10] ❌ Cross-step validation sonrası hiçbir hisse kalmadı")
                self.advance_chain()
                return
            
            selected_stocks = cross_step_valid[:5]
            
            selected_tickers = set([ticker for ticker, score in selected_stocks])
            self.current_window.selected_tickers = selected_tickers
            
            print(f"[PSFAlgo2 CHAIN 10] 🚀 Akıllı seçim: {len(selected_tickers)} hisse seçildi (Final AS skor - EN DÜŞÜK = EN İYİ SATIŞ + cross-step validation)")
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
                    
                    # ✅ KOMPLE EXCLUDE LIST kontrolü
                    if ticker in self.exclude_list:
                        print(f"[PSFAlgo2 CHAIN 11] ⏭️ {ticker} komple exclude listesinde, atlanıyor")
                        continue
                    
                    # ✅ HALF SIZED kontrolü - dinamik lot sistemi
                    if ticker in self.half_sized_list:
                        intended_lot_size = getattr(self, 'default_lot_size', 200)
                        half_sized_lot = intended_lot_size // 2
                        minimum_lot_threshold = 200
                        
                        if intended_lot_size < 400:
                            print(f"[PSFAlgo2 CHAIN 11] ⏭️ {ticker} half-sized listesinde ({intended_lot_size} → {half_sized_lot} lot < {minimum_lot_threshold} minimum), atlanıyor")
                            continue
                        else:
                            print(f"[PSFAlgo2 CHAIN 11] ✅ {ticker} half-sized listesinde kabul edildi ({intended_lot_size} → {half_sized_lot} lot ≥ {minimum_lot_threshold})")
                    
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
        is_valid, message = self.check_front_spread_condition(ticker, order_type, target_price)
        
        if is_valid:
            print(f"[PSFAlgo2 FRONT VALIDATION] ✅ {ticker} {order_type} - {message}")
            return True, message
        else:
            print(f"[PSFAlgo2 FRONT VALIDATION] ❌ {ticker} {order_type} - {message}")
            return False, message

    def check_front_spread_condition(self, ticker, order_type, target_price):
        """
        Front emirleri için spread*0.35 uzaklık kontrolü
        Args:
            ticker: Hisse kodu
            order_type: 'front_buy' veya 'front_sell'
            target_price: Emir fiyatı
        Returns:
            (bool, str): (koşul sağlanıyor mu, açıklama)
        """
        try:
            bid_price, ask_price = self.get_bid_ask_prices(ticker)
            if not bid_price or not ask_price or bid_price <= 0 or ask_price <= 0:
                return False, f"Bid/Ask fiyat bilgisi alınamadı - Bid: {bid_price}, Ask: {ask_price}"
            spread = ask_price - bid_price
            if spread <= 0:
                return False, f"Geçersiz spread: {spread:.4f} (Bid: {bid_price:.3f}, Ask: {ask_price:.3f})"
            spread_tolerance = spread * 0.35
            if order_type.lower() == 'front_buy':
                distance_from_bid = target_price - bid_price
                if distance_from_bid > spread_tolerance:
                    return False, (f"Front buy koşulu ihlali - Hedef: {target_price:.3f}, "
                                   f"Bid: {bid_price:.3f}, Uzaklık: {distance_from_bid:.3f}, "
                                   f"Max izin: {spread_tolerance:.3f} (spread*0.35)")
                return True, (f"Front buy OK - Hedef: {target_price:.3f}, Bid: {bid_price:.3f}, "
                              f"Uzaklık: {distance_from_bid:.3f} ≤ {spread_tolerance:.3f}")
            elif order_type.lower() == 'front_sell':
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
        Ticker için bid/ask fiyatlarını al (Thread-safe)
        
        Returns:
            (float, float): (bid_price, ask_price)
        """
        try:
            # 1. Önce pencere verisinden al (Thread-safe)
            if hasattr(self, 'current_window') and self.current_window:
                bid_price = self.get_price_from_window(self.current_window, ticker, 'Bid')
                ask_price = self.get_price_from_window(self.current_window, ticker, 'Ask')
                
                if bid_price and ask_price and bid_price > 0 and ask_price > 0:
                    print(f"[PSFAlgo2 BID/ASK] {ticker} pencere verisinden alındı: Bid={bid_price:.3f}, Ask={ask_price:.3f}")
                    return bid_price, ask_price
                else:
                    print(f"[PSFAlgo2 BID/ASK] {ticker} pencere verisi eksik: Bid={bid_price}, Ask={ask_price}")
            
            # 2. Market_data_dict'ten al (Polygon verileri) 
            if hasattr(self.market_data, 'last_data') and self.market_data.last_data:
                poly_ticker = self.polygonize_ticker(ticker)
                if poly_ticker in self.market_data.last_data:
                    data = self.market_data.last_data[poly_ticker]
                    bid = data.get('bid')
                    ask = data.get('ask')
                    
                    if bid and ask and float(bid) > 0 and float(ask) > 0:
                        print(f"[PSFAlgo2 BID/ASK] {ticker} market_data'dan alındı: Bid={bid}, Ask={ask}")
                        return float(bid), float(ask)
                    else:
                        print(f"[PSFAlgo2 BID/ASK] {ticker} market_data bid/ask eksik: Bid={bid}, Ask={ask}")
            
            # 3. Ana pencereden market_data_dict al
            if hasattr(self, 'main_window') and self.main_window and hasattr(self.main_window, 'market_data_dict'):
                poly_ticker = self.polygonize_ticker(ticker)
                if poly_ticker in self.main_window.market_data_dict:
                    data = self.main_window.market_data_dict[poly_ticker]
                    bid = data.get('bid')
                    ask = data.get('ask')
                    
                    if bid and ask and float(bid) > 0 and float(ask) > 0:
                        print(f"[PSFAlgo2 BID/ASK] {ticker} ana pencere market_data'dan alındı: Bid={bid}, Ask={ask}")
                        return float(bid), float(ask)
            
            # 4. Current window'daki market_data_dict'i dene
            if hasattr(self, 'current_window') and self.current_window and hasattr(self.current_window, 'market_data_dict'):
                poly_ticker = self.polygonize_ticker(ticker)
                if poly_ticker in self.current_window.market_data_dict:
                    data = self.current_window.market_data_dict[poly_ticker]
                    bid = data.get('bid')
                    ask = data.get('ask')
                    
                    if bid and ask and float(bid) > 0 and float(ask) > 0:
                        print(f"[PSFAlgo2 BID/ASK] {ticker} current_window market_data'dan alındı: Bid={bid}, Ask={ask}")
                        return float(bid), float(ask)
            
            # 5. Son çare: current price'ın %0.5'i kadar spread varsay
            current_price = self.get_current_price(ticker)
            if current_price and current_price > 0:
                estimated_spread = current_price * 0.005  # %0.5 spread varsayımı
                bid = current_price - (estimated_spread / 2)
                ask = current_price + (estimated_spread / 2)
                print(f"[PSFAlgo2 BID/ASK] {ticker} tahmini bid/ask: Bid={bid:.3f}, Ask={ask:.3f} (spread: {estimated_spread:.3f})")
                return bid, ask
            
            print(f"[PSFAlgo2 BID/ASK] {ticker} hiçbir kaynaktan fiyat alınamadı")
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
        1. Şirket bazlı emir limiti kontrolü (aynı şirketten max 3 emir)
        2. Mevcut emirlerle çakışan hisseleri çıkar (±0.08 toleransı)
        3. Front emirler için spread kontrolü yap (spread ≥ 0.06 ise)
        4. Hedef sayıya ulaşmaya çalış
        
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
        
        # ✅ 1. ŞİRKET LİMİTİ FİLTRESİ (YENİ!) - Aynı şirketten maksimum 3 hisse
        print(f"[PSFAlgo2 FILTER] 🏢 Şirket limiti kontrolü uygulanıyor...")
        
        # Şirket limitlerini uygula
        company_filtered_stocks = self.filter_by_company_limits(candidate_stocks, max_selections=None)
        
        print(f"[PSFAlgo2 FILTER] 📊 Şirket limiti sonrası {len(company_filtered_stocks)} hisse kaldı")
        
        # ✅ 2-4. DİĞER FİLTRELER
        filtered_stocks = []
        
        for ticker, score in company_filtered_stocks:
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
        
        print(f"[PSFAlgo2 FILTER] 📊 {len(candidate_stocks)} → {len(company_filtered_stocks)} → {len(filtered_stocks)} hisse (şirket + diğer filtreler sonrası)")
        
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

    def sync_session_state(self, session_company_orders):
        """PSFAlgo1'den session state'ini al"""
        self.session_company_orders = session_company_orders.copy()
        print(f"[PSFAlgo2 SYNC] ✅ {len(self.session_company_orders)} şirket geçmişi senkronize edildi")

    def sync_daily_totals(self, daily_order_totals):
        """PSFAlgo1'den günlük lot toplamlarını al"""
        self.daily_order_totals = daily_order_totals.copy()
        print(f"[PSFAlgo2 SYNC] ✅ {len(self.daily_order_totals)} hisse günlük totalı senkronize edildi")

    def sync_befday_status(self, befday_update_status):
        """PSFAlgo1'den BEFDAY güncelleme durumunu al"""
        self.befday_update_status = befday_update_status.copy()
        print(f"[PSFAlgo2 SYNC] ✅ BEFDAY güncelleme durumu senkronize edildi: {befday_update_status['updated']}")

    def check_daily_600_lot_limit(self, ticker, side, new_lot_size):
        """
        Günlük 600 lot limitini kontrol eder
        """
        from datetime import date
        
        today = date.today()
        
        # Günlük toplam takibi için ticker'ı initialize et
        if ticker not in self.daily_order_totals:
            self.daily_order_totals[ticker] = {'BUY': 0, 'SELL': 0, 'date': today}
        
        # Eğer farklı bir gün ise sıfırla
        if self.daily_order_totals[ticker]['date'] != today:
            self.daily_order_totals[ticker] = {'BUY': 0, 'SELL': 0, 'date': today}
        
        # Mevcut günlük toplam
        current_daily_total = self.daily_order_totals[ticker][side]
        
        # Yeni toplam
        potential_total = current_daily_total + new_lot_size
        
        # 600 lot limiti kontrolü
        if potential_total > 600:
            reason = f"Günlük 600 lot limiti: Bugün {side} yönünde {current_daily_total} + yeni {new_lot_size} = {potential_total} > 600"
            return True, current_daily_total, reason
        
        return False, current_daily_total, ""

    def record_daily_order_total(self, ticker, side, lot_size):
        """Günlük emir toplamını kaydet"""
        from datetime import date
        
        today = date.today()
        
        # Ticker'ı initialize et
        if ticker not in self.daily_order_totals:
            self.daily_order_totals[ticker] = {'BUY': 0, 'SELL': 0, 'date': today}
        
        # Farklı gün ise sıfırla
        if self.daily_order_totals[ticker]['date'] != today:
            self.daily_order_totals[ticker] = {'BUY': 0, 'SELL': 0, 'date': today}
        
        # Toplama ekle
        self.daily_order_totals[ticker][side] += lot_size
        
        print(f"[PSFAlgo2 DAILY LIMIT] ✅ {ticker} {side}: +{lot_size} lot → Günlük toplam: {self.daily_order_totals[ticker][side]}/600")

    def get_company_order_count(self, company, side=None):
        """
        Belirli bir şirket için bu session boyunca gönderilen emir sayısını döndürür
        """
        if company not in self.session_company_orders:
            return 0
        
        company_orders = self.session_company_orders[company]
        
        if side is None:
            return len(company_orders)
        
        return len([order for order in company_orders if order['side'] == side])

    def check_company_limit_exceeded(self, ticker, side):
        """
        Şirket limitinin aşılıp aşılmadığını kontrol eder
        """
        company = self.extract_company_symbol(ticker)
        if not company:
            return False, ""
        
        # Bu şirkete bu yönde kaç emir gönderilmiş
        same_side_count = self.get_company_order_count(company, side)
        
        # Şirket başına maksimum 2 emir limiti
        MAX_ORDERS_PER_COMPANY = 2
        
        if same_side_count >= MAX_ORDERS_PER_COMPANY:
            reason = f"{company} şirketine {side} yönünde zaten {same_side_count} emir gönderilmiş (max: {MAX_ORDERS_PER_COMPANY})"
            print(f"[PSFAlgo2 COMPANY LIMIT] ❌ {reason}")
            return True, reason
        
        return False, ""

    def record_company_order(self, ticker, side, step, size):
        """
        Şirkete gönderilen emri kaydet
        """
        company = self.extract_company_symbol(ticker)
        if not company:
            return
        
        if company not in self.session_company_orders:
            self.session_company_orders[company] = []
        
        order_record = {
            'side': side,
            'ticker': ticker,
            'step': step,
            'size': size,
            'timestamp': datetime.now()
        }
        
        self.session_company_orders[company].append(order_record)
        
        print(f"[PSFAlgo2 COMPANY TRACK] ✅ {company} → {ticker} {side} (Adım {step}, {size} lot) kaydedildi")
        print(f"[PSFAlgo2 COMPANY TRACK] {company} toplam emirler: {len(self.session_company_orders[company])}")

    def get_pending_orders_total_for_ticker(self, ticker):
        """
        Belirli bir ticker için bekleyen emirlerin toplam miktarını hesaplar
        """
        try:
            pending_orders = self.market_data.get_pending_orders() if hasattr(self.market_data, 'get_pending_orders') else []
            
            buy_total = 0
            sell_total = 0
            
            for order in pending_orders:
                if order.get('ticker') == ticker:
                    quantity = abs(int(order.get('quantity', 0)))
                    side = order.get('side', '').upper()
                    
                    if side in ['BUY', 'LONG']:
                        buy_total += quantity
                    elif side in ['SELL', 'SHORT']:
                        sell_total += quantity
            
            return {'buy_total': buy_total, 'sell_total': sell_total}
            
        except Exception as e:
            print(f"[PSFAlgo2 PENDING ORDERS] ⚠️ Bekleyen emirler alınamadı: {e}")
            return {'buy_total': 0, 'sell_total': 0}

    def get_maxalw_size(self, ticker):
        """Ticker için MAXALW size'ını döndürür (cache ile)"""
        if ticker in self.maxalw_cache:
            return self.maxalw_cache[ticker]
        
        try:
            if ticker in self.scores_df.index:
                maxalw_size = int(self.scores_df.loc[ticker, 'MAXALW SIZE'])
                self.maxalw_cache[ticker] = maxalw_size
                return maxalw_size
        except Exception as e:
            print(f"[PSFAlgo2 MAXALW] ⚠️ {ticker} için MAXALW alınamadı: {e}")
        
        return 0

    def get_position_size(self, ticker):
        """Mevcut pozisyon boyutunu döndürür"""
        try:
            position = self.market_data.get_position(ticker) if hasattr(self.market_data, 'get_position') else 0
            return int(position) if position else 0
        except:
            return 0

    def check_maxalw_violation_with_pending(self, ticker, side, new_order_size):
        """
        Mevcut pozisyon + bekleyen emirler + yeni emir = MAXALW limitini aşar mı kontrol eder
        """
        try:
            # 1. Mevcut pozisyonu al
            current_position = self.get_position_size(ticker)
            
            # 2. Bekleyen emirleri al
            pending = self.get_pending_orders_total_for_ticker(ticker)
            
            # 3. MAXALW limitini al
            maxalw_size = self.get_maxalw_size(ticker)
            if maxalw_size <= 0:
                return False, 0, 0, "MAXALW limiti bulunamadı"
            
            # 4. Senaryoyu hesapla
            if side.upper() in ['BUY', 'LONG']:
                # BUY emirleri için: mevcut + bekleyen buy + yeni buy
                total_long_exposure = current_position + pending['buy_total'] + new_order_size
                
                if total_long_exposure > maxalw_size:
                    reason = f"MAXALW aşımı: Mevcut={current_position} + Bekleyen Buy={pending['buy_total']} + Yeni Buy={new_order_size} = {total_long_exposure} > {maxalw_size}"
                    return True, total_long_exposure, maxalw_size, reason
                    
                return False, total_long_exposure, maxalw_size, ""
                
            else:  # SELL/SHORT
                # SHORT emirleri için: |mevcut - bekleyen sell - yeni sell|
                total_short_exposure = abs(current_position - pending['sell_total'] - new_order_size)
                
                if total_short_exposure > maxalw_size:
                    reason = f"MAXALW aşımı: |Mevcut={current_position} - Bekleyen Sell={pending['sell_total']} - Yeni Sell={new_order_size}| = {total_short_exposure} > {maxalw_size}"
                    return True, total_short_exposure, maxalw_size, reason
                    
                return False, total_short_exposure, maxalw_size, ""
                
        except Exception as e:
            print(f"[PSFAlgo2 MAXALW CHECK] ⚠️ MAXALW kontrolü hatası: {e}")
            return False, 0, 0, f"Kontrol hatası: {e}"

    def validate_order_before_approval(self, ticker, side, size, step_number):
        """
        Emir onay penceresine gönderilmeden önce tüm kontrolleri yapar
        """
        print(f"[PSFAlgo2 ORDER VALIDATION] 🔍 {ticker} {side} {size} lot (Adım {step_number}) doğrulanıyor...")
        
        # 1. BEFDAY.csv güncellemesi kontrolü (sadece uyarı, engelleme yok)
        if not self.befday_update_status['updated']:
            warning_msg = f"BEFDAY.csv güncellemesi önerilir: {self.befday_update_status['reason']}"
            print(f"[PSFAlgo2 ORDER VALIDATION] ⚠️ BEFDAY uyarısı: {warning_msg}")
            # Sadece uyarı ver, emirleri engelleme
        
        # 2. Günlük 600 lot limit kontrolü
        daily_exceeded, current_daily, daily_reason = self.check_daily_600_lot_limit(ticker, side, size)
        if daily_exceeded:
            print(f"[PSFAlgo2 ORDER VALIDATION] ❌ Günlük limit: {daily_reason}")
            return False, daily_reason
        
        # 3. Şirket limiti kontrolü
        company_exceeded, company_reason = self.check_company_limit_exceeded(ticker, side)
        if company_exceeded:
            print(f"[PSFAlgo2 ORDER VALIDATION] ❌ Şirket limiti: {company_reason}")
            return False, company_reason
        
        # 4. MAXALW + bekleyen emirler kontrolü
        maxalw_exceeded, exposure, max_allowed, maxalw_reason = self.check_maxalw_violation_with_pending(ticker, side, size)
        if maxalw_exceeded:
            print(f"[PSFAlgo2 ORDER VALIDATION] ❌ MAXALW limiti: {maxalw_reason}")
            return False, maxalw_reason
        
        # 5. Tüm kontroller geçildi
        print(f"[PSFAlgo2 ORDER VALIDATION] ✅ {ticker} {side} {size} lot onaylandı")
        print(f"[PSFAlgo2 ORDER VALIDATION] 📊 Günlük total: {current_daily + size}/600, Toplam exposure: {exposure}/{max_allowed} MAXALW")
        
        return True, "Onaylandı"

    def filter_candidates_by_cross_step_rules(self, candidate_list, step_number, order_side, target_count=5, extended_candidates=None):
        """
        Aday hisse listesini cross-step kurallarına göre filtreler
        Elenen hisselerin yerine diğer adayları geçirir
        """
        if not candidate_list:
            return []
        
        # Genişletilmiş aday listesi yoksa, orijinal listeyi kullan
        if extended_candidates is None:
            extended_candidates = candidate_list
        
        print(f"[PSFAlgo2 CROSS-STEP FILTER] 🔍 Adım {step_number} için {len(candidate_list)} aday filtreleniyor...")
        print(f"[PSFAlgo2 CROSS-STEP FILTER] 📊 Genişletilmiş aday havuzu: {len(extended_candidates)} hisse")
        print(f"[PSFAlgo2 CROSS-STEP FILTER] 🎯 Hedef: {target_count} hisse seçilecek")
        
        valid_candidates = []
        rejected_candidates = []
        
        # İlk olarak verilen aday listesini kontrol et
        for candidate in candidate_list:
            ticker = candidate[0] if isinstance(candidate, (list, tuple)) else candidate
            score = candidate[1] if isinstance(candidate, (list, tuple)) and len(candidate) > 1 else 0
            
            # Validation yap
            is_valid, reason = self.validate_order_before_approval(ticker, order_side, 200, step_number)
            
            if is_valid:
                valid_candidates.append((ticker, score))
            else:
                rejected_candidates.append((ticker, score, reason))
        
        # Eğer hedef sayıya ulaşılmadıysa, genişletilmiş aday listesinden devam et
        if len(valid_candidates) < target_count and len(extended_candidates) > len(candidate_list):
            print(f"[PSFAlgo2 CROSS-STEP FILTER] ⚠️ Hedef sayıya ulaşılamadı ({len(valid_candidates)}/{target_count}), genişletilmiş adaylardan devam ediliyor...")
            
            # Zaten kontrol edilen hisseleri takip et
            checked_tickers = set([c[0] if isinstance(c, (list, tuple)) else c for c in candidate_list])
            
            # Genişletilmiş aday listesinden devam et
            for candidate in extended_candidates:
                ticker = candidate[0] if isinstance(candidate, (list, tuple)) else candidate
                score = candidate[1] if isinstance(candidate, (list, tuple)) and len(candidate) > 1 else 0
                
                # Zaten kontrol edilmiş hisseleri atla
                if ticker in checked_tickers:
                    continue
                
                # Hedef sayıya ulaştık mı?
                if len(valid_candidates) >= target_count:
                    break
                
                # Validation yap
                is_valid, reason = self.validate_order_before_approval(ticker, order_side, 200, step_number)
                
                if is_valid:
                    valid_candidates.append((ticker, score))
                    print(f"[PSFAlgo2 CROSS-STEP FILTER] ✅ {ticker} (skor: {score:.2f}) - Genişletilmiş adaydan eklendi")
                else:
                    rejected_candidates.append((ticker, score, reason))
                    print(f"[PSFAlgo2 CROSS-STEP FILTER] ❌ {ticker} (skor: {score:.2f}) - {reason} (genişletilmiş aday)")
        
        # Sonuçları bildir
        print(f"[PSFAlgo2 CROSS-STEP FILTER] ✅ {len(valid_candidates)} hisse geçerli:")
        for ticker, score in valid_candidates:
            print(f"[PSFAlgo2 CROSS-STEP FILTER]   ✅ {ticker} (skor: {score:.2f})")
        
        if rejected_candidates:
            print(f"[PSFAlgo2 CROSS-STEP FILTER] ❌ {len(rejected_candidates)} hisse elendi:")
            for ticker, score, reason in rejected_candidates:
                print(f"[PSFAlgo2 CROSS-STEP FILTER]   ❌ {ticker} (skor: {score:.2f}) - {reason}")
        
        # Hedef sayıya ulaşılamadıysa uyarı ver
        if len(valid_candidates) < target_count:
            shortage = target_count - len(valid_candidates)
            print(f"[PSFAlgo2 CROSS-STEP FILTER] ⚠️ Hedef sayıya ulaşılamadı: {shortage} hisse eksik")
            print(f"[PSFAlgo2 CROSS-STEP FILTER] 💡 {len(extended_candidates)} aday arasından sadece {len(valid_candidates)} uygun hisse bulundu")
        
        return valid_candidates

    def get_current_step_number(self):
        """Mevcut adım numarasını döndürür (9-14)"""
        step_mapping = {
            'T_LOSERS_OLD': 9,
            'T_GAINERS_OLD': 10,
            'LONG_TP_ASK': 11,
            'LONG_TP_FRONT': 12,
            'SHORT_TP_BID': 13,
            'SHORT_TP_FRONT': 14,
        }
        
        return step_mapping.get(self.chain_state, 9)
