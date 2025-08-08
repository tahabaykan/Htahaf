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
logger = logging.getLogger('PsfAlgo')
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

class PsfAlgo:
    def __init__(self, market_data, exclude_list=None, half_sized_list=None, order_manager=None):
        self.logger = logging.getLogger('PsfAlgo')
        self.logger.info("PsfAlgo initialized - INACTIVE by default")
        
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
        self.bdata_storage = BDataStorage('Htahaf/data/bdata_fills.json')
        
        # BEFDAY pozisyonları
        self.befday_positions = self.load_befday_positions()
        
        self.exclude_list = exclude_list or set()
        self.half_sized_list = half_sized_list or set()
        self.filled_sizes = {}  # Her hisse için toplam fill miktarı
        
        # ✅ Günlük fill takibi
        self.today = date.today()
        self.daily_fills = {}  # {ticker: {'long': total_size, 'short': total_size, 'date': date}}
        
        # ✅ PISDoNGU sistemi
        self.pisdongu_active = False
        self.pisdongu_timer = None
        self.pisdongu_cycle_count = 0
        
        # ✅ BEFDAY pozisyon limitleri
        self.daily_position_limits = {}  # Her hisse için ±600 limit
        
        # ✅ Chain yönetimi
        self.chain_state = 'IDLE'  # IDLE, T_LOSERS, T_GAINERS, LONG_TP_ASK, LONG_TP_FRONT, SHORT_TP_BID, SHORT_TP_FRONT, FINISHED
        self.waiting_for_approval = False  # Onay bekleme kontrolü
        
        # ✅ Cross-Step Company & MAXALW Tracking
        self.session_company_orders = {}  # {company: [{'side': 'BUY/SELL', 'ticker': 'PEB PRE', 'step': 1, 'size': 200}, ...]}
        self.psfalgo2 = None  # PSFAlgo2 referansı paylaşım için
        
        # ✅ MAXALW size cache (performans için)
        self.maxalw_cache = {}  # {ticker: maxalw_size}
        
        # ✅ Günlük 600 lot limit takibi
        self.daily_order_totals = {}  # {ticker: {'BUY': total_lots, 'SELL': total_lots, 'date': date}}
        self.befday_update_status = self.check_befday_update_status()
        
        logger.info("PsfAlgo initialized - INACTIVE by default")

    def set_psfalgo2(self, psfalgo2):
        """PSFAlgo2 referansını ayarla (state paylaşımı için)"""
        self.psfalgo2 = psfalgo2
        print("[PSFAlgo1] PSFAlgo2 referansı ayarlandı")

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
        
        print(f"[PSFAlgo1 COMPANY LIMIT] {company}: {company_stocks_count} hisse → {company_stocks_count}/3 = {company_stocks_count/3:.2f} → max {final_max} emir")
        
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
        
        print(f"[PSFAlgo1 COMPANY FILTER] 🔍 Şirket limiti uygulanıyor - {len(candidate_list)} aday")
        
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
            
            print(f"[PSFAlgo1 COMPANY FILTER] {company}: {len(company_candidates)} aday → {len(selected_for_company)} seçildi")
            for ticker, score in selected_for_company:
                print(f"[PSFAlgo1 COMPANY FILTER]   ✅ {ticker} (skor: {score:.2f})")
            
            # Seçilmeyenleri bildir
            if len(company_candidates_sorted) > max_orders:
                not_selected = company_candidates_sorted[max_orders:]
                print(f"[PSFAlgo1 COMPANY FILTER] {company}: {len(not_selected)} hisse elendi:")
                for ticker, score in not_selected:
                    print(f"[PSFAlgo1 COMPANY FILTER]   ❌ {ticker} (skor: {score:.2f}) - şirket limiti")
            
            filtered_candidates.extend(selected_for_company)
        
        # Eğer maksimum seçim sayısı belirtilmişse, son filtre uygula
        if max_selections and len(filtered_candidates) > max_selections:
            # Tüm listeden en yüksek skorluları seç
            filtered_candidates_sorted = sorted(filtered_candidates, key=lambda x: x[1], reverse=True)
            final_selection = filtered_candidates_sorted[:max_selections]
            
            print(f"[PSFAlgo1 COMPANY FILTER] 📊 Final seçim: {len(filtered_candidates)} → {len(final_selection)} (toplam limit)")
            
            return final_selection
        
        print(f"[PSFAlgo1 COMPANY FILTER] ✅ Toplam {len(filtered_candidates)} hisse seçildi")
        return filtered_candidates

    def get_company_order_count(self, company, side=None):
        """
        Belirli bir şirket için bu session boyunca gönderilen emir sayısını döndürür
        
        Args:
            company: Şirket adı (örn: 'PEB', 'INN')
            side: 'BUY' veya 'SELL' (None = toplam)
        
        Returns:
            Bu session'da o şirkete gönderilen emir sayısı
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
        
        Args:
            ticker: Kontrol edilecek hisse
            side: 'BUY' veya 'SELL'
        
        Returns:
            (is_exceeded, reason) tuple
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
            print(f"[COMPANY LIMIT] ❌ {reason}")
            return True, reason
        
        return False, ""

    def record_company_order(self, ticker, side, step, size):
        """
        Şirkete gönderilen emri kaydet
        
        Args:
            ticker: Hisse adı
            side: 'BUY' veya 'SELL'
            step: Hangi adımda gönderildi (1-14)
            size: Emir boyutu
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
        
        print(f"[COMPANY TRACK] ✅ {company} → {ticker} {side} (Adım {step}, {size} lot) kaydedildi")
        print(f"[COMPANY TRACK] {company} toplam emirler: {len(self.session_company_orders[company])}")

    def get_pending_orders_total_for_ticker(self, ticker):
        """
        Belirli bir ticker için bekleyen emirlerin toplam miktarını hesaplar
        
        Returns:
            {'buy_total': int, 'sell_total': int}
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
            print(f"[PENDING ORDERS] ⚠️ Bekleyen emirler alınamadı: {e}")
            return {'buy_total': 0, 'sell_total': 0}

    def check_maxalw_violation_with_pending(self, ticker, side, new_order_size):
        """
        Mevcut pozisyon + bekleyen emirler + yeni emir = MAXALW limitini aşar mı kontrol eder
        
        Args:
            ticker: Kontrol edilecek hisse
            side: 'BUY' veya 'SELL'
            new_order_size: Gönderilmek istenen emir boyutu
        
        Returns:
            (will_exceed, current_exposure, max_allowed, reason)
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
            print(f"[MAXALW CHECK] ⚠️ MAXALW kontrolü hatası: {e}")
            return False, 0, 0, f"Kontrol hatası: {e}"



    def filter_candidates_by_cross_step_rules(self, candidate_list, step_number, order_side, target_count=5, extended_candidates=None):
        """
        Aday hisse listesini cross-step kurallarına göre filtreler
        Elenen hisselerin yerine diğer adayları geçirir
        
        Args:
            candidate_list: [(ticker, score), ...] formatında aday listesi
            step_number: Hangi adımda (1-14)
            order_side: 'BUY' veya 'SELL'
            target_count: Hedef hisse sayısı (varsayılan: 5)
            extended_candidates: Genişletilmiş aday listesi (None ise candidate_list kullanılır)
        
        Returns:
            Filtrelenmiş ve geçerli [(ticker, score), ...] listesi
        """
        if not candidate_list:
            return []
        
        # Genişletilmiş aday listesi yoksa, orijinal listeyi kullan
        if extended_candidates is None:
            extended_candidates = candidate_list
        
        print(f"[CROSS-STEP FILTER] 🔍 Adım {step_number} için {len(candidate_list)} aday filtreleniyor...")
        print(f"[CROSS-STEP FILTER] 📊 Genişletilmiş aday havuzu: {len(extended_candidates)} hisse")
        print(f"[CROSS-STEP FILTER] 🎯 Hedef: {target_count} hisse seçilecek")
        
        valid_candidates = []
        rejected_candidates = []
        
        # İlk olarak verilen aday listesini kontrol et
        for candidate in candidate_list:
            ticker = candidate[0] if isinstance(candidate, (list, tuple)) else candidate
            score = candidate[1] if isinstance(candidate, (list, tuple)) and len(candidate) > 1 else 0
            
            # Validation yap
            is_valid, reason = self.validate_order_before_approval(ticker, order_side, self.default_lot_size, step_number)
            
            if is_valid:
                valid_candidates.append((ticker, score))
            else:
                rejected_candidates.append((ticker, score, reason))
        
        # Eğer hedef sayıya ulaşılmadıysa, genişletilmiş aday listesinden devam et
        if len(valid_candidates) < target_count and len(extended_candidates) > len(candidate_list):
            print(f"[CROSS-STEP FILTER] ⚠️ Hedef sayıya ulaşılamadı ({len(valid_candidates)}/{target_count}), genişletilmiş adaylardan devam ediliyor...")
            
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
                is_valid, reason = self.validate_order_before_approval(ticker, order_side, self.default_lot_size, step_number)
                
                if is_valid:
                    valid_candidates.append((ticker, score))
                    print(f"[CROSS-STEP FILTER] ✅ {ticker} (skor: {score:.2f}) - Genişletilmiş adaydan eklendi")
                else:
                    rejected_candidates.append((ticker, score, reason))
                    print(f"[CROSS-STEP FILTER] ❌ {ticker} (skor: {score:.2f}) - {reason} (genişletilmiş aday)")
        
        # Sonuçları bildir
        print(f"[CROSS-STEP FILTER] ✅ {len(valid_candidates)} hisse geçerli:")
        for ticker, score in valid_candidates:
            print(f"[CROSS-STEP FILTER]   ✅ {ticker} (skor: {score:.2f})")
        
        if rejected_candidates:
            print(f"[CROSS-STEP FILTER] ❌ {len(rejected_candidates)} hisse elendi:")
            for ticker, score, reason in rejected_candidates:
                print(f"[CROSS-STEP FILTER]   ❌ {ticker} (skor: {score:.2f}) - {reason}")
        
        # Hedef sayıya ulaşılamadıysa uyarı ver
        if len(valid_candidates) < target_count:
            shortage = target_count - len(valid_candidates)
            print(f"[CROSS-STEP FILTER] ⚠️ Hedef sayıya ulaşılamadı: {shortage} hisse eksik")
            print(f"[CROSS-STEP FILTER] 💡 {len(extended_candidates)} aday arasından sadece {len(valid_candidates)} uygun hisse bulundu")
        
        return valid_candidates

    def get_current_step_number(self):
        """Mevcut adım numarasını döndürür (1-14)"""
        step_mapping = {
            'T_LOSERS': 1,
            'T_GAINERS': 2,
            'LONG_TP_ASK': 3,
            'LONG_TP_FRONT': 4,
            'SHORT_TP_BID': 5,
            'SHORT_TP_FRONT': 6,
            'T_LOSERS_OLD': 7,   # PSFAlgo2'ye geçiş
            'T_GAINERS_OLD': 8,
            'LONG_TP_ASK_OLD': 9,
            'LONG_TP_FRONT_OLD': 10,
            'SHORT_TP_BID_OLD': 11,
            'SHORT_TP_FRONT_OLD': 12,
        }
        
        return step_mapping.get(self.chain_state, 0)

    def check_befday_update_status(self):
        """BEFDAY.csv'nin bugün güncellenip güncellenmediğini kontrol eder"""
        try:
            import os
            from datetime import date
            
            # BEFDAY.csv dosyası var mı?
            if not os.path.exists('BEFDAY.csv'):
                return {'updated': False, 'reason': 'BEFDAY.csv dosyası bulunamadı'}
            
            # Dosyanın son güncelleme tarihi
            last_modified = os.path.getmtime('BEFDAY.csv')
            last_modified_date = date.fromtimestamp(last_modified)
            today = date.today()
            
            # Bugün güncellenmiş mi?
            if last_modified_date == today:
                return {'updated': True, 'date': today}
            else:
                return {'updated': False, 'reason': f'Son güncelleme: {last_modified_date}, Bugün: {today}'}
                
        except Exception as e:
            return {'updated': False, 'reason': f'Kontrol hatası: {e}'}

    def check_daily_600_lot_limit(self, ticker, side, new_lot_size):
        """
        Günlük 600 lot limitini kontrol eder
        
        Args:
            ticker: Hisse adı
            side: 'BUY' veya 'SELL'
            new_lot_size: Yeni gönderilecek lot miktarı
            
        Returns:
            (will_exceed, current_total, reason)
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
        
        print(f"[DAILY LIMIT] ✅ {ticker} {side}: +{lot_size} lot → Günlük toplam: {self.daily_order_totals[ticker][side]}/600")

    def validate_order_before_approval(self, ticker, side, size, step_number):
        """
        Emir onay penceresine gönderilmeden önce tüm kontrolleri yapar
        
        Args:
            ticker: Hisse adı
            side: 'BUY' veya 'SELL'
            size: Emir boyutu
            step_number: Hangi adımda (1-14)
        
        Returns:
            (is_valid, reason) tuple
        """
        print(f"[ORDER VALIDATION] 🔍 {ticker} {side} {size} lot (Adım {step_number}) doğrulanıyor...")
        
        # 1. BEFDAY.csv güncellemesi kontrolü (sadece uyarı, engelleme yok)
        if not self.befday_update_status['updated']:
            warning_msg = f"BEFDAY.csv güncellemesi önerilir: {self.befday_update_status['reason']}"
            print(f"[ORDER VALIDATION] ⚠️ BEFDAY uyarısı: {warning_msg}")
            # Sadece uyarı ver, emirleri engelleme
        
        # 2. Günlük 600 lot limit kontrolü
        daily_exceeded, current_daily, daily_reason = self.check_daily_600_lot_limit(ticker, side, size)
        if daily_exceeded:
            print(f"[ORDER VALIDATION] ❌ Günlük limit: {daily_reason}")
            return False, daily_reason
        
        # 3. Şirket limiti kontrolü
        company_exceeded, company_reason = self.check_company_limit_exceeded(ticker, side)
        if company_exceeded:
            print(f"[ORDER VALIDATION] ❌ Şirket limiti: {company_reason}")
            return False, company_reason
        
        # 4. MAXALW + bekleyen emirler kontrolü
        maxalw_exceeded, exposure, max_allowed, maxalw_reason = self.check_maxalw_violation_with_pending(ticker, side, size)
        if maxalw_exceeded:
            print(f"[ORDER VALIDATION] ❌ MAXALW limiti: {maxalw_reason}")
            return False, maxalw_reason
        
        # 5. Tüm kontroller geçildi
        print(f"[ORDER VALIDATION] ✅ {ticker} {side} {size} lot onaylandı")
        print(f"[ORDER VALIDATION] 📊 Günlük total: {current_daily + size}/600, Toplam exposure: {exposure}/{max_allowed} MAXALW")
        
        return True, "Onaylandı"

    def send_order_with_validation(self, ticker, price, final_thg, side, size=200):
        """
        Emri validasyon ile gönderir ve şirket kayıtlarını tutar
        ⚠️ NOT: Validation zaten filter_candidates_by_cross_step_rules() ile yapıldı
        """
        step_number = self.get_current_step_number()
        
        print(f"[SEND ORDER] 📤 {ticker} {side} {size} lot emri gönderiliyor (validation önceden yapıldı)")
        
        # Orijinal send_order fonksiyonunu çağır (validation atlandı - önceden yapıldı)
        success = self.send_order(ticker, price, final_thg, side, size)
        
        if success:
            # Başarılı gönderimde kayıtları tut
            self.record_company_order(ticker, side, step_number, size)
            self.record_daily_order_total(ticker, side, size)
            
            print(f"[SEND ORDER] ✅ {ticker} emri başarıyla gönderildi ve kaydedildi")
            
            # PSFAlgo2 ile state paylaş
            if self.psfalgo2:
                self.psfalgo2.sync_session_state(self.session_company_orders)
                self.psfalgo2.sync_daily_totals(self.daily_order_totals)
                self.psfalgo2.sync_befday_status(self.befday_update_status)
        else:
            print(f"[SEND ORDER] ❌ {ticker} emri gönderilemedi (IBKR hatası)")
        
        return success

    def set_main_window(self, main_window):
        """Ana pencere referansını ayarla"""
        self.main_window = main_window
        print("[PSFAlgo] Ana pencere referansı ayarlandı")

    def activate(self):
        """PSFAlgo'yu aktif hale getir ve PISDoNGU sistemini başlat"""
        self.is_active = True
        self.pisdongu_active = True
        self.pisdongu_cycle_count = 0
        
        logger.info("PsfAlgo ACTIVATED - PISDoNGU sistemi başlatılıyor")
        print("[PSFAlgo] ✅ PSFAlgo aktif hale getirildi!")
        print("[PISDoNGU] 🔄 PISDoNGU sistemi başlatılıyor...")
        
        # ✅ Otomatik fill kontrolünü başlat
        self.start_auto_fill_check()
        
        # İlk başlatma işlemleri
        self.start_pisdongu_cycle()

    def deactivate(self):
        """PSFAlgo'yu pasif hale getir ve PISDoNGU'yu durdur"""
        self.is_active = False
        self.pisdongu_active = False
        self.chain_state = 'IDLE'
        
        # Timer'ı durdur
        if self.pisdongu_timer:
            self.pisdongu_timer.cancel()
            self.pisdongu_timer = None
        
        # Ana penceredeki buton durumunu güncelle
        if self.main_window and hasattr(self.main_window, 'btn_psf_algo'):
            self.main_window.btn_psf_algo.config(text="PsfAlgo OFF", style='TButton')
        
        logger.info("PsfAlgo DEACTIVATED - PISDoNGU durduruldu")
        print("[PSFAlgo] ❌ PSFAlgo pasif hale getirildi!")
        print("[PISDoNGU] ⏹️ PISDoNGU sistemi durduruldu!")

    def start_pisdongu_cycle(self):
        """✅ OTOMATİK RESTART ÇALIŞTI: PISDoNGU döngüsünü başlat"""
        if not self.pisdongu_active:
            return
            
        self.pisdongu_cycle_count += 1
        print(f"[🔄 OTOMATİK RESTART] 🚀 RESTART ÇALIŞTI - Döngü #{self.pisdongu_cycle_count} başlatılıyor...")
        
        # 1. BEFDAY pozisyonlarını yükle
        print(f"[🔄 OTOMATİK RESTART] 1️⃣ BEFDAY pozisyonları yükleniyor...")
        self.load_befday_positions()
        
        # 2. Veri güncellemelerini yap
        print(f"[🔄 OTOMATİK RESTART] 2️⃣ Veri kaynakları güncelleniyor...")
        self.update_data_sources()
        
        # 3. Eğer ilk döngü değilse, tüm emirleri iptal et
        if self.pisdongu_cycle_count > 1:
            print(f"[🔄 OTOMATİK RESTART] 3️⃣ Tüm normal emirler iptal ediliyor (Rev emirler korunuyor)...")
            self.cancel_all_pending_orders()
        else:
            print(f"[🔄 OTOMATİK RESTART] 3️⃣ İlk döngü - emir iptali atlanıyor...")
        
        # 4. Chain'i başlat
        print(f"[🔄 OTOMATİK RESTART] 4️⃣ PSFAlgo1 chain başlatılıyor (1. adım: T-Losers)...")
        self.chain_state = 'T_LOSERS'
        self.start_chain()
        
        print(f"[🔄 OTOMATİK RESTART] ✅ Restart tamamlandı - PSFAlgo1 döngü #{self.pisdongu_cycle_count} aktif!")

    def load_befday_positions(self):
        """BEFDAY.csv'den gün başı pozisyonlarını yükle ve limitleri hesapla"""
        try:
            import pandas as pd
            df = pd.read_csv('befday.csv')
            
            self.befday_positions = {}
            self.daily_position_limits = {}
            
            for _, row in df.iterrows():
                symbol = row['Symbol']
                start_position = int(row['Quantity'])
                
                self.befday_positions[symbol] = start_position
                
                # ±600 lot limit hesapla
                self.daily_position_limits[symbol] = {
                    'min': start_position - 600,
                    'max': start_position + 600,
                    'start': start_position
                }
                
                print(f"[BEFDAY] {symbol}: Başlangıç={start_position}, Limit=[{start_position-600}, {start_position+600}]")
            
            print(f"[BEFDAY] ✅ {len(self.befday_positions)} hisse için limit yüklendi")
            
        except Exception as e:
            print(f"[BEFDAY] ❌ BEFDAY.csv yüklenemedi: {e}")
            self.befday_positions = {}
            self.daily_position_limits = {}

    def update_data_sources(self):
        """ETF veri güncelle ve Veri güncelle butonlarını çalıştır"""
        print("[PISDoNGU] 📊 Veri kaynakları güncelleniyor...")
        
        try:
            if self.main_window:
                # ETF veri güncelle
                if hasattr(self.main_window, 'update_etf_data'):
                    print("[PISDoNGU] ETF veri güncelle çalıştırılıyor...")
                    self.main_window.update_etf_data()
                
                # 1 saniye bekle
                import time
                time.sleep(1)
                
                # Veri güncelle
                if hasattr(self.main_window, 'update_data'):
                    print("[PISDoNGU] Veri güncelle çalıştırılıyor...")
                    self.main_window.update_data()
                
                print("[PISDoNGU] ✅ Veri kaynakları güncellendi")
            else:
                print("[PISDoNGU] ⚠️ Ana pencere referansı yok")
        except Exception as e:
            print(f"[PISDoNGU] ❌ Veri güncelleme hatası: {e}")

    def cancel_all_pending_orders(self):
        """Tüm bekleyen emirleri iptal et"""
        print("[PISDoNGU] 🗑️ Tüm bekleyen emirler iptal ediliyor...")
        
        try:
            if hasattr(self.market_data, 'ib') and self.market_data.ib:
                # Ana thread'de çalıştır (event loop sorunu için)
                if hasattr(self.main_window, 'after'):
                    self.main_window.after(0, self._cancel_orders_main_thread)
                else:
                    self._cancel_orders_main_thread()
        except Exception as e:
            print(f"[PISDoNGU] ❌ Emir iptali genel hatası: {e}")

    def _cancel_orders_main_thread(self):
        """Ana thread'de emir iptali yap - Rev emirlerini koru"""
        try:
            if not hasattr(self.market_data, 'ib') or not self.market_data.ib:
                print("[PISDoNGU] ℹ️ IBKR bağlantısı yok")
                return
                
            trades = self.market_data.ib.openTrades()
            
            if not trades:
                print("[PISDoNGU] ℹ️ İptal edilecek emir bulunamadı")
                return
            
            # ✅ REVERSE ORDER ID'LERİNİ TOPLA (REV EMİRLERİ KORUMAK İÇİN)
            reverse_order_ids = set()
            if hasattr(self, 'order_manager') and self.order_manager:
                for ro in self.order_manager.reverse_orders:
                    if ro.get('orderId'):
                        reverse_order_ids.add(ro['orderId'])
                        print(f"[PISDoNGU CANCEL] Rev emir korunacak: {ro['ticker']} {ro.get('orderId')}")
            
            cancelled_count = 0
            protected_count = 0
            
            for trade in trades:
                try:
                    order_id = trade.order.orderId
                    symbol = trade.contract.symbol
                    action = trade.order.action
                    quantity = trade.order.totalQuantity
                    
                    # ✅ REV EMİRLERİNİ KORU
                    if order_id in reverse_order_ids:
                        print(f"[PISDoNGU CANCEL] 🔒 Rev emir korundu: {symbol} {action} {quantity} (ID: {order_id})")
                        protected_count += 1
                        continue
                    
                    # Normal emirleri iptal et
                    self.market_data.ib.cancelOrder(trade.order)
                    cancelled_count += 1
                    print(f"[PISDoNGU CANCEL] ✅ Nor emir iptal edildi: {symbol} {action} {quantity} (ID: {order_id})")
                    
                except Exception as e:
                    print(f"[PISDoNGU CANCEL] ❌ Emir iptali hatası: {e}")
            
            print(f"[PISDoNGU CANCEL] ✅ {cancelled_count} Nor emir iptal edildi, {protected_count} Rev emir korundu")
            
            # İptal işlemlerinin tamamlanması için bekle
            import time
            time.sleep(2)
            
        except Exception as e:
            print(f"[PISDoNGU] ❌ Ana thread emir iptali hatası: {e}")

    def check_befday_limits(self, ticker, side, quantity):
        """
        Emir göndermeden önce BEFDAY limitlerini kontrol et
        Returns: (allowed, max_allowed_quantity)
        """
        if ticker not in self.daily_position_limits:
            # BEFDAY'de olmayan hisseler için varsayılan limit
            print(f"[BEFDAY CHECK] {ticker} BEFDAY'de yok, varsayılan ±600 limit uygulanıyor")
            self.daily_position_limits[ticker] = {'min': -600, 'max': 600, 'start': 0}
        
        limits = self.daily_position_limits[ticker]
        
        # Mevcut pozisyonu al
        current_position = self.get_position_size(ticker)
        
        # Açık emirleri al
        open_orders = {}
        if hasattr(self.market_data, 'ib') and self.market_data.ib:
            trades = self.market_data.ib.openTrades()
            
            for trade in trades:
                contract = trade.contract
                order = trade.order
                symbol = contract.symbol
                
                if symbol not in open_orders:
                    open_orders[symbol] = []
                
                order_info = {
                    'orderId': order.orderId,
                    'action': order.action,  # BUY/SELL
                    'quantity': order.totalQuantity,
                    'price': order.lmtPrice,
                    'trade_obj': trade  # Trade objesi saklayalım
                }
                open_orders[symbol].append(order_info)
        
        # Potansiyel pozisyonu hesapla
        potential_position = current_position + sum(o['quantity'] for o in open_orders.get(ticker, []) if o['action'] == 'BUY') - sum(o['quantity'] for o in open_orders.get(ticker, []) if o['action'] == 'SELL')
        
        # Yeni emir eklenirse ne olur?
        if side == 'LONG':
            final_position = potential_position + quantity
        else:  # SHORT
            final_position = potential_position - quantity
        
        # Limit kontrolü
        if final_position < limits['min']:
            # Minimum limitin altına düşecek
            max_allowed = potential_position - limits['min']
            if max_allowed <= 0:
                print(f"[BEFDAY CHECK] ❌ {ticker} {side} {quantity}: Minimum limit aşılacak ({final_position} < {limits['min']})")
                return False, 0
            else:
                print(f"[BEFDAY CHECK] ⚠️ {ticker} {side} {quantity}: Kısmi izin ({max_allowed} lot)")
                return True, max_allowed
        
        elif final_position > limits['max']:
            # Maksimum limitin üstüne çıkacak
            max_allowed = limits['max'] - potential_position
            if max_allowed <= 0:
                print(f"[BEFDAY CHECK] ❌ {ticker} {side} {quantity}: Maksimum limit aşılacak ({final_position} > {limits['max']})")
                return False, 0
            else:
                print(f"[BEFDAY CHECK] ⚠️ {ticker} {side} {quantity}: Kısmi izin ({max_allowed} lot)")
                return True, max_allowed
        
        else:
            # Limit içinde
            print(f"[BEFDAY CHECK] ✅ {ticker} {side} {quantity}: Limit OK ({final_position} ∈ [{limits['min']}, {limits['max']}])")
            return True, quantity

    def check_maxalw_limits(self, ticker, side, quantity):
        """
        MAXALW Size limitlerini kontrol et
        Returns: (allowed, max_allowed_quantity)
        """
        try:
            # MAXALW size'ı al (AVGADV/10)
            maxalw_size = self.get_maxalw_size(ticker)
            
            if maxalw_size is None or maxalw_size == 'N/A':
                print(f"[MAXALW CHECK] ⚠️ {ticker} MAXALW size alınamadı, varsayılan 200 limit")
                maxalw_size = 200
            
            # Effective MAXALW size: max(200, raw_maxalw_size)
            effective_maxalw = max(200, maxalw_size)
            
            # Mevcut pozisyonu al
            current_position = self.get_position_size(ticker)
            
            # Açık emirleri al
            open_orders = {}
            if hasattr(self.market_data, 'ib') and self.market_data.ib:
                trades = self.market_data.ib.openTrades()
                
                for trade in trades:
                    contract = trade.contract
                    order = trade.order
                    symbol = contract.symbol
                    
                    if symbol not in open_orders:
                        open_orders[symbol] = []
                    
                    order_info = {
                        'action': order.action,
                        'quantity': order.totalQuantity,
                    }
                    open_orders[symbol].append(order_info)
            
            # Potansiyel pozisyonu hesapla (bekleyen emirler dahil)
            potential_position = current_position
            for order in open_orders.get(ticker, []):
                if order['action'] == 'BUY':
                    potential_position += order['quantity']
                else:  # SELL
                    potential_position -= order['quantity']
            
            # Yeni emir eklenirse ne olur?
            if side == 'LONG':
                final_position = potential_position + quantity
            else:  # SHORT
                final_position = potential_position - quantity
            
            # Mutlak pozisyon değeri kontrolü: |final_position| ≤ effective_maxalw
            abs_final_position = abs(final_position)
            
            if abs_final_position > effective_maxalw:
                # MAXALW limit aşılacak
                current_abs_position = abs(potential_position)
                max_allowed = effective_maxalw - current_abs_position
                
                if max_allowed <= 0:
                    print(f"[MAXALW CHECK] ❌ {ticker} {side} {quantity}: MAXALW limit aşılacak")
                    print(f"[MAXALW CHECK]    Raw MAXALW: {maxalw_size}, Effective: {effective_maxalw}")
                    print(f"[MAXALW CHECK]    |{final_position}| = {abs_final_position} > {effective_maxalw}")
                    return False, 0
                else:
                    print(f"[MAXALW CHECK] ⚠️ {ticker} {side} {quantity}: Kısmi izin ({max_allowed} lot)")
                    print(f"[MAXALW CHECK]    Raw MAXALW: {maxalw_size}, Effective: {effective_maxalw}")
                    print(f"[MAXALW CHECK]    |{potential_position + max_allowed}| = {abs(potential_position + max_allowed)} ≤ {effective_maxalw}")
                    return True, max_allowed
            else:
                # MAXALW limit içinde
                print(f"[MAXALW CHECK] ✅ {ticker} {side} {quantity}: MAXALW OK")
                print(f"[MAXALW CHECK]    Raw MAXALW: {maxalw_size}, Effective: {effective_maxalw}")
                print(f"[MAXALW CHECK]    |{final_position}| = {abs_final_position} ≤ {effective_maxalw}")
                return True, quantity
                
        except Exception as e:
            print(f"[MAXALW CHECK] ❌ {ticker} MAXALW kontrolü hatası: {e}")
            # Hata durumunda varsayılan 200 limit uygula
            return self.check_maxalw_limits(ticker, side, min(quantity, 200))

    def get_maxalw_size(self, ticker):
        """
        Ticker için MAXALW size değerini döndür (AVGADV/10)
        """
        try:
            # Market data'dan AVGADV değerini al
            if hasattr(self.market_data, 'get_market_data'):
                data = self.market_data.get_market_data([ticker])
                if ticker in data and 'avg_adv' in data[ticker]:
                    avg_adv = data[ticker]['avg_adv']
                    if avg_adv and avg_adv != 'N/A':
                        maxalw_size = int(float(avg_adv) / 10)
                        print(f"[MAXALW] {ticker} AVGADV: {avg_adv} → MAXALW: {maxalw_size}")
                        return maxalw_size
            
            # Alternatif: GUI pencerelerinden veri al
            if self.current_window and hasattr(self.current_window, 'rows'):
                try:
                    for row in self.current_window.rows:
                        if len(row) > 1 and row[1] == ticker:
                            # MAXALW Size kolunu bul
                            if hasattr(self.current_window, 'COLUMNS'):
                                columns = self.current_window.COLUMNS
                                if 'MAXALW Size' in columns:
                                    maxalw_index = columns.index('MAXALW Size')
                                    if len(row) > maxalw_index:
                                        maxalw_str = row[maxalw_index]
                                        if maxalw_str and maxalw_str != 'N/A':
                                            maxalw_size = int(float(maxalw_str))
                                            print(f"[MAXALW] {ticker} GUI'den MAXALW: {maxalw_size}")
                                            return maxalw_size
                except Exception as e:
                    print(f"[MAXALW] {ticker} GUI'den veri alma hatası: {e}")
            
            print(f"[MAXALW] ⚠️ {ticker} için MAXALW size bulunamadı")
            return None
            
        except Exception as e:
            print(f"[MAXALW] ❌ {ticker} MAXALW size alma hatası: {e}")
            return None

    def get_pending_orders_for_ticker(self, ticker):
        """Ticker için bekleyen emirleri döndür"""
        orders = []
        try:
            if hasattr(self.market_data, 'ib') and self.market_data.ib:
                trades = self.market_data.ib.openTrades()
                for trade in trades:
                    contract = trade.contract
                    order = trade.order
                    symbol = contract.symbol
                    if symbol == ticker:
                        orders.append({
                            'action': order.action,
                            'quantity': order.totalQuantity,
                            'price': order.lmtPrice
                        })
        except Exception as e:
            print(f"[DEBUG] {ticker} için bekleyen emirler alınamadı: {e}")
        
        return orders

    def start_chain(self):
        """PSFAlgo chain'ini başlat - YENİ 14 ADIMLI SİSTEM"""
        if not self.is_active or self.chain_state == 'IDLE':
            return
            
        print(f"[PSFAlgo CHAIN] Başlatılıyor - Durum: {self.chain_state}")
        
        # YENİ 8 ADIMLI SİSTEM (1-8)
        if self.chain_state == 'T_LOSERS':
            self.run_new_t_losers_bb()  # 1. FINAL BB en yüksek 5 → bid buy
        elif self.chain_state == 'T_LOSERS_FB':
            # 2. FINAL FB front buy - mevcut T-Losers penceresinde işlem yap
            print("[PSF CHAIN 2] T-Losers FB - mevcut pencerede FINAL FB işlemi tetikleniyor...")
            if self.current_window and hasattr(self.current_window, 'rows'):
                self.run_new_t_losers_fb()
            else:
                print("[PSF CHAIN 2] ❌ T-Losers penceresi bulunamadı, bir sonraki adıma geç")
                self.advance_chain()
        elif self.chain_state == 'T_GAINERS':
            self.run_new_t_gainers_as()  # 3. FINAL AS en düşük 5 → ask sell
        elif self.chain_state == 'T_GAINERS_FS':
            # 4. FINAL FS front sell - mevcut T-Gainers penceresinde işlem yap
            print("[PSF CHAIN 4] T-Gainers FS - mevcut pencerede FINAL FS işlemi tetikleniyor...")
            if self.current_window and hasattr(self.current_window, 'rows'):
                self.run_new_t_gainers_fs()
            else:
                print("[PSF CHAIN 4] ❌ T-Gainers penceresi bulunamadı, bir sonraki adıma geç")
                self.advance_chain()
        elif self.chain_state == 'LONG_TP_AS':
            self.run_new_long_tp_as()    # 5. FINAL AS en düşük 5 → ask sell
        elif self.chain_state == 'LONG_TP_FS':
            # 6. FINAL FS front sell - mevcut Long TP penceresinde işlem yap
            print("[PSF CHAIN 6] Long TP FS - mevcut pencerede FINAL FS işlemi tetikleniyor...")
            if self.current_window and hasattr(self.current_window, 'rows'):
                self.run_new_long_tp_fs()
            else:
                print("[PSF CHAIN 6] ❌ Long TP penceresi bulunamadı, bir sonraki adıma geç")
                self.advance_chain()
        elif self.chain_state == 'SHORT_TP_BB':
            self.run_new_short_tp_bb()   # 7. FINAL BB en yüksek 5 → bid buy
        elif self.chain_state == 'SHORT_TP_FB':
            # 8. FINAL FB front buy - mevcut Short TP penceresinde işlem yap
            print("[PSF CHAIN 8] Short TP FB - mevcut pencerede FINAL FB işlemi tetikleniyor...")
            if self.current_window and hasattr(self.current_window, 'rows'):
                self.run_new_short_tp_fb()
            else:
                print("[PSF CHAIN 8] ❌ Short TP penceresi bulunamadı, bir sonraki adıma geç")
                self.advance_chain()
        elif self.chain_state == 'FINISHED':
            self.finish_chain()

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

    def finish_chain(self):
        """Chain'i bitir ve PISDoNGU döngüsünü devam ettir"""
        print("[PSFAlgo CHAIN] 🔍 İşlemler tamamlandı, pozisyon kontrolü yapılıyor...")
        
        # Pozisyon kontrolü yap
        self.check_and_prevent_position_reversal()
        
        self.close_current_windows()
        
        print(f"[PISDoNGU] ✅ Döngü #{self.pisdongu_cycle_count} tamamlandı")
        
        # PISDoNGU aktifse 3 dakika sonra yeni döngü başlat
        if self.pisdongu_active:
            print("[PISDoNGU] ⏰ 3 dakika sonra yeni döngü başlatılacak...")
            self.schedule_next_pisdongu_cycle()
        else:
            # PSFAlgo kapatıldıysa normal şekilde bitir
            self.deactivate()
            if self.main_window and hasattr(self.main_window, 'btn_psf_algo') and self.main_window.btn_psf_algo:
                self.main_window.btn_psf_algo.config(text="PsfAlgo OFF", style='TButton')

    def schedule_next_pisdongu_cycle(self):
        """✅ OTOMATİK RESTART SİSTEMİ: 3 dakika sonra tüm emirleri iptal edip veri güncelle ve yeni döngü başlat"""
        if not self.pisdongu_active:
            return
            
        # Önceki timer'ı iptal et
        if self.pisdongu_timer:
            self.pisdongu_timer.cancel()
        
        print(f"[🔄 OTOMATİK RESTART] ✅ PSFAlgo1 ve PSFAlgo2 döngüleri tamamlandı!")
        print(f"[🔄 OTOMATİK RESTART] 📋 RESTART SİSTEMİ BAŞLATILUYOR:")
        print(f"[🔄 OTOMATİK RESTART]   ⏰ 3 dakika (180 saniye) bekleme")
        print(f"[🔄 OTOMATİK RESTART]   🗑️ Tüm normal emirleri iptal etme (Rev emirler korunacak)")
        print(f"[🔄 OTOMATİK RESTART]   📊 ETF veri güncelleme")
        print(f"[🔄 OTOMATİK RESTART]   📈 Veri güncelleme") 
        print(f"[🔄 OTOMATİK RESTART]   🚀 1. adımdan (T-Losers) yeni döngü başlatma")
        
        # 3 dakika = 180 saniye
        self.pisdongu_timer = threading.Timer(180.0, self.start_pisdongu_cycle)
        self.pisdongu_timer.start()
        
        print(f"[🔄 OTOMATİK RESTART] ⏰ Timer kuruldu - 180 saniye sonra otomatik restart başlayacak")

    def check_and_prevent_position_reversal(self):
        """
        Pozisyon kontrolü yaparak ters pozisyona geçmeyi önler:
        - Long pozisyonda: En pahalı sell emirlerini iptal et
        - Short pozisyonda: En ucuz buy emirlerini iptal et
        """
        print("[PSFAlgo POSITION CONTROL] 📊 Pozisyon tersine geçme kontrolü başlatılıyor...")
        
        if not self.is_active:
            print("[PSFAlgo] ⏸️ PSFAlgo pasif - pozisyon kontrolü yapılmadı")
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
            
            # Açık emirleri al
            open_orders = {}
            if hasattr(self.market_data, 'ib') and self.market_data.ib:
                trades = self.market_data.ib.openTrades()
                
                for trade in trades:
                    contract = trade.contract
                    order = trade.order
                    symbol = contract.symbol
                    
                    if symbol not in open_orders:
                        open_orders[symbol] = []
                    
                    order_info = {
                        'orderId': order.orderId,
                        'action': order.action,  # BUY/SELL
                        'quantity': order.totalQuantity,
                        'price': order.lmtPrice,
                        'trade_obj': trade  # Trade objesi saklayalım
                    }
                    open_orders[symbol].append(order_info)
            
            # Her hisse için pozisyon kontrolü yap
            all_symbols = set(list(current_positions.keys()) + list(open_orders.keys()))
            
            for symbol in all_symbols:
                current_pos = current_positions.get(symbol, 0)
                symbol_orders = open_orders.get(symbol, [])
                
                if not symbol_orders:
                    continue
                    
                print(f"[POSITION CONTROL] {symbol}: Pozisyon={current_pos}, Emir sayısı={len(symbol_orders)}")
                
                # Buy ve sell emirlerini ayır
                buy_orders = [o for o in symbol_orders if o['action'] == 'BUY']
                sell_orders = [o for o in symbol_orders if o['action'] == 'SELL']
                
                total_buy_qty = sum(o['quantity'] for o in buy_orders)
                total_sell_qty = sum(o['quantity'] for o in sell_orders)
                
                # Tüm emirler fillense pozisyon ne olur?
                projected_position = current_pos + total_buy_qty - total_sell_qty
                
                print(f"[POSITION CONTROL] {symbol}: Buy={total_buy_qty}, Sell={total_sell_qty}")
                print(f"[POSITION CONTROL] {symbol}: Mevcut={current_pos} → Tahmini={projected_position}")
                
                orders_to_cancel = []
                
                # LONG POZİSYON KONTROLÜ
                if current_pos > 0:  # Mevcut LONG pozisyon
                    if projected_position < 0:  # SHORT'a geçecek
                        print(f"[POSITION CONTROL] ⚠️ {symbol} LONG→SHORT geçiş tespit edildi!")
                        
                        # En pahalı sell emirlerini iptal et
                        sell_orders.sort(key=lambda x: x['price'], reverse=True)  # Yüksek → düşük
                        
                        # 0'da kalmak için max satılabilir miktar
                        max_sellable = current_pos + total_buy_qty  # Buy'lar pozisyonu arttırır
                        
                        cumulative_sell = 0
                        for order in sell_orders:
                            if cumulative_sell + order['quantity'] > max_sellable:
                                # Bu emir fazla, iptal et
                                orders_to_cancel.append(order)
                                print(f"[CANCEL] {symbol} SELL {order['quantity']} @ {order['price']:.3f} (en pahalı)")
                            else:
                                cumulative_sell += order['quantity']
                
                # SHORT POZİSYON KONTROLÜ  
                elif current_pos < 0:  # Mevcut SHORT pozisyon
                    if projected_position > 0:  # LONG'a geçecek
                        print(f"[POSITION CONTROL] ⚠️ {symbol} SHORT→LONG geçiş tespit edildi!")
                        
                        # En ucuz buy emirlerini iptal et
                        buy_orders.sort(key=lambda x: x['price'])  # Düşük → yüksek
                        
                        # 0'da kalmak için max alınabilir miktar
                        max_buyable = abs(current_pos) - total_sell_qty  # Sell'ler pozisyonu azaltır
                        
                        cumulative_buy = 0
                        for order in buy_orders:
                            if cumulative_buy + order['quantity'] > max_buyable:
                                # Bu emir fazla, iptal et
                                orders_to_cancel.append(order)
                                print(f"[CANCEL] {symbol} BUY {order['quantity']} @ {order['price']:.3f} (en ucuz)")
                            else:
                                cumulative_buy += order['quantity']
                
                # POZİSYON YOK - DENGELI KONTROL
                elif current_pos == 0:  # Pozisyon yok
                    if abs(projected_position) > 0:
                        print(f"[POSITION CONTROL] ℹ️ {symbol} sıfır pozisyondan {projected_position} pozisyona geçecek")
                        # Pozisyon yokken yeni pozisyon açması normal, kontrol etmeyelim
                
                # ✅ MAXALW SIZE KONTROLÜ - Tüm pozisyonlar için
                maxalw_size = self.get_maxalw_size(symbol)
                if maxalw_size is not None and maxalw_size != 'N/A':
                    effective_maxalw = max(200, maxalw_size)
                    abs_projected_position = abs(projected_position)
                    
                    if abs_projected_position > effective_maxalw:
                        print(f"[POSITION CONTROL] ⚠️ {symbol} MAXALW size limiti aşılacak!")
                        print(f"[POSITION CONTROL] |{projected_position}| = {abs_projected_position} > {effective_maxalw}")
                        
                        # En büyük emirleri iptal ederek MAXALW limitine uy
                        # Long pozisyon için: en büyük buy emirlerini iptal et
                        # Short pozisyon için: en büyük sell emirlerini iptal et
                        
                        target_position_abs = effective_maxalw  # Hedef mutlak pozisyon
                        current_abs_position = abs(current_pos)
                        
                        if projected_position > 0:  # Long tarafa geçecek
                            # En büyük buy emirlerini iptal et
                            buy_orders.sort(key=lambda x: x['quantity'], reverse=True)  # Büyük → küçük
                            
                            for order in buy_orders:
                                if abs(projected_position) <= target_position_abs:
                                    break
                                    
                                # Bu emri iptal et
                                orders_to_cancel.append(order)
                                projected_position -= order['quantity']  # Buy emrini iptal ettiğimiz için pozisyon azalır
                                print(f"[MAXALW CANCEL] {symbol} BUY {order['quantity']} iptal edildi (MAXALW limit)")
                                
                        elif projected_position < 0:  # Short tarafa geçecek
                            # En büyük sell emirlerini iptal et
                            sell_orders.sort(key=lambda x: x['quantity'], reverse=True)  # Büyük → küçük
                            
                            for order in sell_orders:
                                if abs(projected_position) <= target_position_abs:
                                    break
                                    
                                # Bu emri iptal et
                                orders_to_cancel.append(order)
                                projected_position += order['quantity']  # Sell emrini iptal ettiğimiz için pozisyon artar
                                print(f"[MAXALW CANCEL] {symbol} SELL {order['quantity']} iptal edildi (MAXALW limit)")
                    else:
                        print(f"[POSITION CONTROL] {symbol}: MAXALW size kontrolü OK ✅ (|{projected_position}| = {abs_projected_position} ≤ {effective_maxalw})")
                
                # Emirleri iptal et
                if orders_to_cancel:
                    print(f"[POSITION CONTROL] {symbol}: {len(orders_to_cancel)} emir iptal edilecek")
                    
                    for order_info in orders_to_cancel:
                        try:
                            self.market_data.ib.cancelOrder(order_info['trade_obj'].order)
                            print(f"[POSITION CONTROL] ✅ {symbol} {order_info['action']} {order_info['quantity']} @ {order_info['price']:.3f} iptal edildi")
                            log_reasoning(f"Pozisyon tersine geçmeyi önlemek için {symbol} {order_info['action']} emri iptal edildi")
                        except Exception as e:
                            print(f"[POSITION CONTROL] ❌ {symbol} emir iptali hatası: {e}")
                else:
                    print(f"[POSITION CONTROL] {symbol}: Pozisyon kontrolü OK ✅")
                    
        except Exception as e:
            print(f"[POSITION CONTROL] ❌ Genel hata: {e}")
            import traceback
            traceback.print_exc()

    def run_t_top_losers_chain(self):
        """T-top losers chain aşaması"""
        print("[PSFAlgo CHAIN] 📈 T-top Losers aşaması başlatılıyor...")
        
        if not self.main_window:
            print("[PSFAlgo CHAIN] ❌ Ana pencere referansı yok")
            self.advance_chain()
            return
        
        # T-top losers penceresini aç
        self.main_window.open_t_top_losers_maltopla()
        
        # Pencere açılana kadar bekle - on_data_ready otomatik olarak run_t_top_losers'ı çağıracak
        print("[PSFAlgo CHAIN] T-top losers penceresi açıldı, veri yüklenmeyi bekliyor...")

    def run_t_top_gainers_chain(self):
        """T-top gainers chain aşaması"""
        print("[PSFAlgo CHAIN] 📉 T-top Gainers aşaması başlatılıyor...")
        
        if not self.main_window:
            print("[PSFAlgo CHAIN] ❌ Ana pencere referansı yok")
            self.advance_chain()
            return
        
        # T-top gainers penceresini aç
        self.main_window.open_t_top_gainers_maltopla()
        
        # Pencere açılana kadar bekle - on_data_ready otomatik olarak run_t_top_gainers'ı çağıracak
        print("[PSFAlgo CHAIN] T-top gainers penceresi açıldı, veri yüklenmeyi bekliyor...")

    def run_long_tp_ask_sell_chain(self):
        """Long Take Profit - Ask Sell aşaması"""
        print("[PSFAlgo CHAIN] 💰 Long TP - Ask Sell aşaması başlatılıyor...")
        
        if not self.main_window:
            print("[PSFAlgo CHAIN] ❌ Ana pencere referansı yok")
            self.advance_chain()
            return
        
        # Long Take Profit penceresini aç
        self.main_window.open_long_take_profit_window()
        
        # Pencere açılana kadar bekle - on_data_ready otomatik olarak run_long_tp_ask_sell'i çağıracak
        print("[PSFAlgo CHAIN] Long TP penceresi açıldı, veri yüklenmeyi bekliyor...")

    def run_long_tp_front_sell_chain(self):
        """Long Take Profit - Front Sell aşaması"""
        print("[PSFAlgo CHAIN] 🎯 Long TP - Front Sell aşaması başlatılıyor...")
        
        # Mevcut long pozisyonları al
        positions = self.get_long_positions()
        
        if not positions:
            print("[PSFAlgo CHAIN] ❌ Long pozisyon bulunamadı")
            self.advance_chain()
            return
        
        # Long TP penceresi zaten açık olmalı, sadece state değiştir
        print("[PSFAlgo CHAIN] Long TP Front Sell için mevcut pencere kullanılıyor...")
        
        # Mevcut pencerede front sell işlemini tetikle
        if self.current_window and "long take profit" in self.current_window.title().lower():
            self.run_long_tp_front_sell()
        else:
            print("[PSFAlgo CHAIN] ❌ Long TP penceresi bulunamadı")
            self.advance_chain()

    def run_short_tp_bid_buy_chain(self):
        """Short Take Profit - Bid Buy aşaması"""
        print("[PSFAlgo CHAIN] �� Short TP - Bid Buy aşaması başlatılıyor...")
        
        if not self.main_window:
            print("[PSFAlgo CHAIN] ❌ Ana pencere referansı yok")
            self.advance_chain()
            return
        
        # Short Take Profit penceresini aç
        self.main_window.open_short_take_profit_window()
        
        # Pencere açılana kadar bekle - on_data_ready otomatik olarak run_short_tp_bid_buy'ı çağıracak
        print("[PSFAlgo CHAIN] Short TP penceresi açıldı, veri yüklenmeyi bekliyor...")

    def run_short_tp_front_buy_chain(self):
        """Short TP Front Buy işlemlerini yap - hisse seç ve onay penceresi aç"""
        print("[DEBUG] run_short_tp_front_buy başladı")
        
        if not self.is_active:
            print("[PSFAlgo] ⏸️ PSFAlgo pasif - Short TP Front Buy işlenmedi")
            return
            
        if not self.current_window:
            print("[DEBUG] current_window yok")
            return
            
        rows = self.current_window.rows
        columns = self.current_window.COLUMNS
        selected = set()
        reasoning_msgs = []
        
        # Front buy ucuzluk < -0.10 olanları seç (en düşük 3)
        valid_rows = []
        for row in rows:
            try:
                ticker = row[1]
                front_buy_ucuzluk = float(row[columns.index('Front buy ucuzluk skoru')])
                if front_buy_ucuzluk < -0.10:
                    valid_rows.append((ticker, front_buy_ucuzluk, row))
                    msg = f"{ticker} değerlendiriliyor - front buy ucuzluk {front_buy_ucuzluk}"
                    reasoning_msgs.append(msg)
            except Exception as e:
                print(f"[DEBUG] Skipping {row[1] if len(row)>1 else row} - Error: {e}")
                continue
        
        # En düşük 3'ü seç (en negatif olanlar)
        valid_rows.sort(key=lambda x: x[1])
        selected = set([ticker for ticker, _, _ in valid_rows[:3]])
        
        if not selected:
            print("[PSFAlgo CHAIN] ❌ Front buy için uygun short pozisyon bulunamadı")
            self.advance_chain()
            return
        
        if selected:
            for ticker, skor, _ in valid_rows[:3]:
                msg = f"{ticker} seçildi - front buy ucuzluk {skor} (top 3)"
                print("[REASONING]", msg)
                reasoning_msgs.append(msg)
        
        # Seçili hisseleri GUI'ye aktar
        self.current_window.selected_tickers = selected
        
        # Reasoning logla
        for msg in reasoning_msgs:
            log_reasoning(msg)
        
        # Front buy butonunu tetikle
        print("[DEBUG] send_front_buy_orders çağrılıyor...")
        self.current_window.send_front_buy_orders()
        
        print("[PSFAlgo CHAIN] Short TP Front Buy onay penceresi açıldı, kullanıcı onayı bekleniyor...")

    # Helper fonksiyonlar
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

    def get_ask_sell_score(self, ticker):
        """Ask sell pahalilik skorunu al"""
        try:
            df = pd.read_csv('mastermind_histport.csv')
            row = df[df['PREF IBKR'] == ticker]
            if not row.empty:
                return float(row.iloc[0]['Ask sell pahalilik skoru'])
        except Exception:
            pass
        return 0.0

    def get_front_sell_score(self, ticker):
        """Front sell pahalilik skorunu al"""
        try:
            df = pd.read_csv('mastermind_histport.csv')
            row = df[df['PREF IBKR'] == ticker]
            if not row.empty:
                return float(row.iloc[0]['Front sell pahalilik skoru'])
        except Exception:
            pass
        return 0.0

    def get_bid_buy_score(self, ticker):
        """Bid buy ucuzluk skorunu al"""
        try:
            df = pd.read_csv('mastermind_histport.csv')
            row = df[df['PREF IBKR'] == ticker]
            if not row.empty:
                return float(row.iloc[0]['Bid buy Ucuzluk skoru'])
        except Exception:
            pass
        return 0.0

    def get_front_buy_score(self, ticker):
        """Front buy ucuzluk skorunu al"""
        try:
            df = pd.read_csv('mastermind_histport.csv')
            row = df[df['PREF IBKR'] == ticker]
            if not row.empty:
                return float(row.iloc[0]['Front buy ucuzluk skoru'])
        except Exception:
            pass
        return 0.0

    def get_t_top_losers(self):
        """T-top losers listesini döndür (GUI veya veri kaynağından)."""
        if hasattr(self.market_data, 'get_t_top_losers'):
            return self.market_data.get_t_top_losers()
        return []

    def get_t_top_gainers(self):
        """T-top gainers listesini döndür (GUI veya veri kaynağından)."""
        if hasattr(self.market_data, 'get_t_top_gainers'):
            return self.market_data.get_t_top_gainers()
        return []

    def get_scores_for_ticker(self, ticker):
        # scored_stocks.csv'den skorları çek
        try:
            row = self.scores_df.loc[ticker]
            return {
                'FINAL_THG': float(row.get('FINAL_THG', 0)),
                'bidbuy_ucuzluk': float(row.get('bidbuy_ucuzluk', 0)),
                'asksell_pahali': float(row.get('asksell_pahali', 0))
            }
        except Exception:
            return {'FINAL_THG': 0, 'bidbuy_ucuzluk': 0, 'asksell_pahali': 0}

    def get_position(self, ticker):
        # market_data.get_positions() IBKR'den pozisyonları döndürür
        if hasattr(self.market_data, 'get_positions'):
            positions = self.market_data.get_positions()
            for pos in positions:
                if pos['symbol'] == ticker:
                    return {'size': pos['quantity'], 'avgCost': pos.get('avgCost', 0)}
        return None

    def calculate_benchmark_at_fill(self, ticker):
        """Fill anında benchmark değerini hesapla"""
        try:
            # Önce güncel fiyatı al
            current_price = self.get_current_price(ticker)
            if current_price:
                return current_price
            
            # Fallback: GUI'den Last price
            if self.current_window:
                price = self.get_price_from_window(self.current_window, ticker, 'Last price')
                if price and price > 0:
                    return price
            
            # Son çare: None döndür
            print(f"[BENCHMARK] ⚠️ {ticker} için benchmark hesaplanamadı")
            return None
            
        except Exception as e:
            print(f"[BENCHMARK ERROR] {ticker} benchmark hesaplanırken hata: {e}")
            return None

    def on_fill(self, ticker, side, price, size, **kwargs):
        """Fill geldiğinde pozisyon yönetimi ve reverse order kontrolü yapar."""
        
        # ✅ PSFAlgo aktif değilse hiçbir şey yapma
        if not self.is_active:
            print(f"[PSFAlgo] ⏸️ PSFAlgo pasif - {ticker} fill işlenmedi")
            return
            
        # ✅ KOMPLE EXCLUDE LIST kontrolü - fill'ler de ignore edilmeli
        if ticker in self.exclude_list:
            print(f"[PSFAlgo KOMPLE EXCLUDE] ❌ {ticker} komple exclude listesinde - fill işlenmedi")
            return
        
        # ✅ HALF SIZED - fill işleme devam et ama uyarı ver
        if ticker in self.half_sized_list:
            print(f"[PSFAlgo HALF SIZED] 📉 {ticker} half sized listesinde - fill işleniyor: {side} {size} @ {price}")
            
        print(f"[FILL] {ticker} fill alındı: {side} {size} lot @ {price}")
        
        # Side parametresini normalize et
        if side.upper() in ['BUY', 'BOT']:
            normalized_side = 'long'
        elif side.upper() in ['SELL', 'SLD']:
            normalized_side = 'short'
        else:
            normalized_side = side.lower()
        
        # ✅ MEVCUT POZİSYON BİLGİSİNİ AL
        current_position = self.get_position_size(ticker)
        
        # ✅ SNAPSHOT TABALLI BDATA GÜNCELLEMESİ
        try:
            benchmark_at_fill = self.calculate_benchmark_at_fill(ticker)
            fill_time = datetime.now()
            
            # Pozisyon arttırma mı azaltma mı kontrol et
            is_increase = self.bdata_storage.update_position_on_fill(
                ticker=ticker,
                direction=normalized_side,
                fill_price=float(price),
                fill_size=int(size),
                benchmark_at_fill=benchmark_at_fill,
                current_total_size=current_position
            )
            
            print(f"[BDATA] ✅ {ticker} fill BDATA'ya eklendi: {normalized_side} {size}@{price}, "
                  f"benchmark: {benchmark_at_fill:.4f}, increase: {is_increase}")
            
            # ✅ İLK DEFA POZİSYON AÇILIYORSA VEYA SNAPSHOT YOKSA OTOMATİK SNAPSHOT OLUŞTUR
            existing_snapshot = self.bdata_storage.get_latest_snapshot(ticker)
            
            if not existing_snapshot and is_increase:
                # İlk pozisyon açılışında veya snapshot yoksa otomatik snapshot oluştur
                current_price_for_snapshot = self.get_current_price(ticker)
                if not current_price_for_snapshot:
                    current_price_for_snapshot = float(price)
                
                self.bdata_storage.create_snapshot(
                    ticker=ticker,
                    current_price=current_price_for_snapshot,
                    current_benchmark=benchmark_at_fill,
                    total_size=size if normalized_side == 'long' else -size,
                    avg_cost=float(price),
                    avg_benchmark=benchmark_at_fill
                )
                print(f"[BDATA SNAPSHOT] ✅ {ticker} için otomatik snapshot oluşturuldu (ilk pozisyon/milat)")
            
            # ✅ HER FILL SONRASI CSV'Yİ OTOMATİK GÜNCELLE
            self.update_main_bdata_csv()
            print(f"[BDATA CSV] ✅ {ticker} fill sonrası CSV otomatik güncellendi")
            
        except Exception as e:
            print(f"[BDATA] ❌ {ticker} BDATA güncellemesi hatası: {e}")
            import traceback
            traceback.print_exc()
        
        # ✅ Günlük fill takibi güncelle
        self.update_daily_fills(ticker, normalized_side, size)
        
        # ✅ Günlük fill miktarını kontrol et
        daily_total = self.get_daily_fill_total(ticker, normalized_side)
        print(f"[DAILY FILL] {ticker} {normalized_side} günlük toplam: {daily_total} lot")
        
        # ✅ 200+ lot olduğunda reverse order kontrolü
        if daily_total >= 200:
            print(f"[REVERSE TRIGGER] {ticker} {normalized_side} günlük fill 200+ lot ({daily_total}), pozisyon arttırma kontrolü yapılıyor")
            
            # Fill sonrası pozisyonu hesapla
            if normalized_side == 'long':
                new_position = current_position + size
            else:  # short
                new_position = current_position - size
                
            print(f"[REVERSE] {ticker} pozisyon değişimi: {current_position} -> {new_position}")
            
            # ✅ DOĞRU POZİSYON ARTTIRMA MANTIGI
            # Reverse order SADECE pozisyon arttırma işlemlerinde açılır:
            # - LONG ARTTIRMA: Pozisyon yok/long varken BUY
            # - SHORT ARTTIRMA: Pozisyon yok/short varken SELL
            # POZISYON AZALTMA işlemlerinde reverse order AÇILMAZ:
            # - LONG AZALTMA: Long pozisyon varken SELL (kapatma)
            # - SHORT AZALTMA: Short pozisyon varken BUY (kapatma)
            is_position_increasing = False
            
            if normalized_side == 'long':
                # Long fill: pozisyon arttırma mı?
                # 1. Sıfırdan pozitife (0 -> +200) = LONG ARTTIRMA
                # 2. Pozitiften daha pozitife (+500 -> +700) = LONG ARTTIRMA
                if current_position >= 0 and new_position > current_position:
                    is_position_increasing = True
                    print(f"[REVERSE] {ticker} LONG ARTTIRMA tespit edildi: {current_position} -> {new_position}")
                else:
                    print(f"[REVERSE] {ticker} SHORT AZALTMA (short kapatma): {current_position} -> {new_position}")
            
            else:  # normalized_side == 'short'
                # Short fill: pozisyon arttırma mı?
                # 1. Sıfırdan negatife (0 -> -200) = SHORT ARTTIRMA
                # 2. Negatiften daha negatife (-500 -> -700) = SHORT ARTTIRMA
                if current_position <= 0 and new_position < current_position:
                    is_position_increasing = True
                    print(f"[REVERSE] {ticker} SHORT ARTTIRMA tespit edildi: {current_position} -> {new_position}")
                else:
                    print(f"[REVERSE] {ticker} LONG AZALTMA (long kapatma): {current_position} -> {new_position}")
            
            if is_position_increasing:
                # ✅ Maksimum 600 lot reverse order kontrolü
                current_reverse_orders = self.get_daily_reverse_orders(ticker)
                max_reverse_limit = 600
                
                if current_reverse_orders >= max_reverse_limit:
                    print(f"[REVERSE] ❌ {ticker} için reverse order limiti aşıldı ({current_reverse_orders}/{max_reverse_limit})")
                    return
                
                # Açılacak reverse order miktarını hesapla
                remaining_reverse_capacity = max_reverse_limit - current_reverse_orders
                reverse_size = min(daily_total, remaining_reverse_capacity)
                
                if reverse_size <= 0:
                    print(f"[REVERSE] ❌ {ticker} için reverse order kapasitesi yok")
                    return
                
                print(f"[REVERSE] ✅ {ticker} pozisyon arttırma işlemi - reverse order açılıyor ({reverse_size} lot)")
                # Pozisyon artışı varsa reverse order aç
                reverse_side = 'SHORT' if normalized_side == 'long' else 'LONG'
                success = self.open_reverse_order(ticker, reverse_side, reverse_size, fill_price=price)
                
                if success:
                    # Reverse order sayacını güncelle
                    self.update_daily_reverse_orders(ticker, reverse_size)
                    print(f"[REVERSE] ✅ {ticker} reverse order başarılı - toplam reverse: {self.get_daily_reverse_orders(ticker)}")
            else:
                print(f"[REVERSE] ❌ {ticker} pozisyon azaltma işlemi - reverse order açılmıyor")
        else:
            print(f"[DAILY FILL] {ticker} {normalized_side} günlük fill henüz 200'ün altında ({daily_total}), reverse order açılmıyor")

    def update_daily_fills(self, ticker, side, size):
        """Günlük fill miktarını güncelle"""
        today = date.today()
        
        # Gün değişmişse sıfırla
        if self.today != today:
            self.today = today
            self.daily_fills = {}
            print(f"[DAILY FILL] Yeni gün ({today}), günlük fill takibi sıfırlandı")
        
        # Ticker için entry oluştur
        if ticker not in self.daily_fills:
            self.daily_fills[ticker] = {'long': 0, 'short': 0, 'reverse_orders': 0, 'date': today}
        
        # Fill miktarını ekle
        self.daily_fills[ticker][side] += size
        print(f"[DAILY FILL UPDATE] {ticker} {side}: +{size} → toplam: {self.daily_fills[ticker][side]}")

    def get_daily_fill_total(self, ticker, side):
        """Ticker ve side için günlük toplam fill miktarını döndür"""
        if ticker in self.daily_fills:
            return self.daily_fills[ticker].get(side, 0)
        return 0

    def get_daily_reverse_orders(self, ticker):
        """Ticker için günlük toplam reverse order miktarını döndür"""
        if ticker in self.daily_fills:
            return self.daily_fills[ticker].get('reverse_orders', 0)
        return 0

    def update_daily_reverse_orders(self, ticker, size):
        """Ticker için günlük reverse order miktarını güncelle"""
        today = date.today()
        
        # Gün değişmişse sıfırla
        if self.today != today:
            self.today = today
            self.daily_fills = {}
            print(f"[DAILY REVERSE] Yeni gün ({today}), günlük reverse order takibi sıfırlandı")
        
        # Ticker için entry oluştur
        if ticker not in self.daily_fills:
            self.daily_fills[ticker] = {'long': 0, 'short': 0, 'reverse_orders': 0, 'date': today}
        
        # Reverse order entry yoksa ekle
        if 'reverse_orders' not in self.daily_fills[ticker]:
            self.daily_fills[ticker]['reverse_orders'] = 0
        
        # Reverse order miktarını ekle
        self.daily_fills[ticker]['reverse_orders'] += size
        print(f"[DAILY REVERSE UPDATE] {ticker}: +{size} → toplam reverse: {self.daily_fills[ticker]['reverse_orders']}")

    def open_reverse_order(self, ticker, side, size, fill_price):
        """Reverse order açar - size parametresi günlük toplam fill miktarı"""
        
        # ✅ PSFAlgo aktif değilse hiçbir şey yapma
        if not self.is_active:
            print(f"[PSFAlgo] ⏸️ PSFAlgo pasif - {ticker} reverse order işlenmedi")
            return
            
        # ✅ KOMPLE EXCLUDE LIST kontrolü - reverse order da ignore edilmeli
        if ticker in self.exclude_list:
            print(f"[PSFAlgo KOMPLE EXCLUDE] ❌ {ticker} komple exclude listesinde - reverse order açılmadı")
            return
        
        # ✅ GÜNLÜK 600 LOT LİMİT KONTROLÜ - Reverse order için de geçerli!
        daily_exceeded, current_daily, daily_reason = self.check_daily_600_lot_limit(ticker, side, size)
        if daily_exceeded:
            print(f"[REVERSE DAILY LIMIT] ❌ {ticker} {side} reverse order reddedildi: {daily_reason}")
            return False
        
        # ✅ HALF SIZED kontrolü - reverse order boyutunu da yarıya düşür
        if ticker in self.half_sized_list:
            original_size = size
            size = max(size // 2, 100)  # En az 100 lot
            print(f"[PSFAlgo HALF SIZED REVERSE] 📉 {ticker} half sized - reverse order boyutu: {original_size} → {size}")
            
        try:
            # Mevcut fiyatları al
            current_price = self.get_current_price(ticker)
            if not current_price:
                print(f"[REVERSE] {ticker} için fiyat alınamadı, reverse order açılamıyor")
                return
                
            # Market data'dan bid/ask al
            bid = 0
            ask = 0
            spread = 0
            
            if hasattr(self.market_data, 'last_data') and ticker in self.market_data.last_data:
                md = self.market_data.last_data[ticker]
                bid = float(md.get('bid', 0))
                ask = float(md.get('ask', 0))
                spread = ask - bid
                print(f"[REVERSE] {ticker} market data bulundu: bid={bid:.3f}, ask={ask:.3f}, spread={spread:.3f}")
            elif hasattr(self.market_data, 'get_market_data'):
                # last_data yoksa get_market_data'dan dene
                try:
                    data = self.market_data.get_market_data([ticker])
                    if ticker in data:
                        md = data[ticker]
                        bid = float(md.get('bid', 0)) if md.get('bid') not in [None, 'N/A'] else 0
                        ask = float(md.get('ask', 0)) if md.get('ask') not in [None, 'N/A'] else 0
                        spread = ask - bid if ask > 0 and bid > 0 else 0
                        print(f"[REVERSE] {ticker} market data alındı: bid={bid:.3f}, ask={ask:.3f}, spread={spread:.3f}")
                except Exception as e:
                    print(f"[REVERSE] {ticker} market data alma hatası: {e}")
            
            # Test için varsayılan değerler (market data yoksa)
            if bid <= 0 or ask <= 0:
                print(f"[REVERSE] {ticker} için market data yok, test için varsayılan değerler kullanılıyor")
                bid = fill_price - 0.02  # Fill fiyatından 2 cent düşük
                ask = fill_price + 0.02  # Fill fiyatından 2 cent yüksek
                spread = ask - bid
                print(f"[REVERSE] {ticker} test değerleri: bid={bid:.3f}, ask={ask:.3f}, spread={spread:.3f}")
            
            # ✅ DÜZGÜN REVERSE ORDER MANTıĞı - PASİF KAR ALMA + ORDERBOOK DEPTH
            print(f"[REVERSE] 📊 {ticker} Market: Bid={bid:.3f}, Ask={ask:.3f}, Spread={spread:.3f}, Fill={fill_price:.3f}")
            
            # Reverse emir fiyatını hesapla
            if side == 'SHORT':  # LONG arttırma fill'i sonrası SHORT reverse
                # LONG pozisyon açtıysak → reverse SELL emri → daha yüksek fiyata
                min_profit_price = fill_price + 0.05
                print(f"[REVERSE] 🎯 LONG fill sonrası SELL reverse: Fill={fill_price:.3f} → Kar hedefi={min_profit_price:.3f}")
                
                # Orderbook depth kontrolü ile pasif SELL fiyatı hesapla
                price, logic = self.calculate_passive_sell_price_psfalgo(ticker, fill_price, min_profit_price, bid, ask, spread)
                
            else:  # side == 'LONG' - SHORT arttırma fill'i sonrası LONG reverse
                # SHORT pozisyon açtıysak → reverse BUY emri → daha düşük fiyata
                min_profit_price = fill_price - 0.05
                print(f"[REVERSE] 🎯 SHORT fill sonrası BUY reverse: Fill={fill_price:.3f} → Kar hedefi={min_profit_price:.3f}")
                
                # Orderbook depth kontrolü ile pasif BUY fiyatı hesapla
                price, logic = self.calculate_passive_buy_price_psfalgo(ticker, fill_price, min_profit_price, bid, ask, spread)
            
            # Fiyat güvenlik kontrolü
            if price <= 0.10:
                print(f"[REVERSE] ❌ {ticker} reverse fiyat çok düşük: {price:.3f}")
                return False
                
            print(f"[REVERSE] {ticker} reverse emir açılıyor: {side} {size} lot @ {price:.3f}")
            print(f"[REVERSE] {ticker} kar hesabı: Fill={fill_price:.3f} → Reverse={price:.3f} → Kar={abs(price-fill_price):.3f}")
            
            # ✅ ORDER_MANAGER İLE ENTEGRASYONu - REVERSE ORDER KAYDET
            if hasattr(self, 'order_manager') and self.order_manager:
                # Reverse order bilgilerini order_manager'a kaydet
                reverse_order_info = {
                    'ticker': ticker,
                    'direction': side.lower(),  # 'LONG' -> 'long', 'SHORT' -> 'short'
                    'price': round(price, 4),
                    'size': size,
                    'hidden': True,
                    'order_type': 'TP',  # Take Profit reverse order
                    'parent_fill_time': datetime.now(),
                    'parent_fill_price': fill_price,
                    'orderId': None  # IBKR'den gelecek
                }
                
                # Order manager'a ekle
                self.order_manager.reverse_orders.append(reverse_order_info)
                print(f"[REVERSE] ✅ {ticker} reverse order order_manager'a kaydedildi")
            
            # Emri gönder (günlük toplam fill miktarı kadar)
            success = self.send_order(ticker, price, 0, side, size)  # FINAL_THG'yi 0 olarak gönderiyoruz çünkü reverse emir
            
            if success:
                print(f"[REVERSE] ✅ {ticker} reverse order başarılı")
                
                # ✅ Başarılı reverse order için günlük toplam kaydet
                self.record_daily_order_total(ticker, side, size)
                
                # ✅ IBKR'den order ID'yi al ve order_manager'ı güncelle
                if hasattr(self, 'order_manager') and self.order_manager and hasattr(self.market_data, 'ib'):
                    # Son açık emirleri kontrol et ve order ID'yi bul
                    try:
                        import time
                        time.sleep(0.5)  # IBKR'nin emri sisteme kaydetmesi için bekle
                        
                        trades = self.market_data.ib.openTrades()
                        for trade in trades:
                            contract = trade.contract
                            order = trade.order
                            
                            # Bu reverse order'a ait emir mi?
                            if (contract.symbol == ticker and 
                                order.action == ('BUY' if side == 'LONG' else 'SELL') and
                                order.totalQuantity == size and
                                abs(order.lmtPrice - price) < 0.01):  # Fiyat toleransı
                                
                                # Order ID'yi güncelle
                                for ro in self.order_manager.reverse_orders:
                                    if (ro['ticker'] == ticker and 
                                        ro['orderId'] is None and
                                        ro['price'] == round(price, 4) and
                                        ro['size'] == size):
                                        ro['orderId'] = order.orderId
                                        print(f"[REVERSE] ✅ {ticker} reverse order ID güncellendi: {order.orderId}")
                                        break
                                break
                    except Exception as e:
                        print(f"[REVERSE] ⚠️ {ticker} order ID güncellemesi hatası: {e}")
                
                return True
            else:
                print(f"[REVERSE] ❌ {ticker} reverse order başarısız")
                
                # Başarısız olursa order_manager'dan çıkar
                if hasattr(self, 'order_manager') and self.order_manager:
                    self.order_manager.reverse_orders = [
                        ro for ro in self.order_manager.reverse_orders
                        if not (ro['ticker'] == ticker and ro['orderId'] is None and ro['price'] == round(price, 4))
                    ]
                
                return False
            
        except Exception as e:
            print(f"[REVERSE ERROR] {ticker} reverse order açılırken hata: {str(e)}")
            log_reasoning(f"{ticker} için reverse order açılamadı: {str(e)}")
            return False

    def get_position_size(self, ticker):
        """Ticker için mevcut pozisyon büyüklüğünü döndürür."""
        position = self.get_position(ticker)
        return position['size'] if position else 0

    def send_order(self, ticker, price, final_thg, side, size=200):
        """Emir gönder - sadece PSFAlgo aktifken"""
        
        # ✅ PSFAlgo aktif değilse hiçbir şey yapma
        if not self.is_active:
            print(f"[PSFAlgo] ⏸️ PSFAlgo pasif - {ticker} emir gönderilmedi")
            return False
            
        # ✅ KOMPLE EXCLUDE LIST kontrolü - önce bu kontrol edilmeli
        if ticker in self.exclude_list:
            print(f"[PSFAlgo KOMPLE EXCLUDE] ❌ {ticker} komple exclude listesinde - emir gönderilmedi")
            log_reasoning(f"{ticker} komple exclude listesinde olduğu için emir gönderilmedi")
            return False
        
        # ✅ HALF SIZED kontrolü - emir boyutunu yarıya düşür
        if ticker in self.half_sized_list:
            original_size = size
            size = max(size // 2, 100)  # En az 100 lot
            print(f"[PSFAlgo HALF SIZED] 📉 {ticker} half sized listesinde - emir boyutu: {original_size} → {size}")
            log_reasoning(f"{ticker} half sized listesinde - emir boyutu yarıya düşürüldü: {original_size} → {size}")
            
            # Eğer yarıya düşürülmüş lot boyutu minimum threshold'dan küçükse, emir gönderme
            minimum_lot_threshold = 200
            if size < minimum_lot_threshold:
                print(f"[PSFAlgo HALF SIZED] ❌ {ticker} yarıya düşürülen lot ({size}) minimum threshold'dan ({minimum_lot_threshold}) küçük - emir gönderilmedi")
                log_reasoning(f"{ticker} half sized - yarıya düşürülen lot {size} < {minimum_lot_threshold} minimum threshold, emir gönderilmedi")
                return False
            
        # ✅ BEFDAY limit kontrolü - PISDoNGU aktifken
        if self.pisdongu_active:
            allowed, max_allowed = self.check_befday_limits(ticker, side, size)
            if not allowed:
                print(f"[PSFAlgo] ❌ {ticker} {side} {size}: BEFDAY limiti aşıldı, emir gönderilmedi")
                log_reasoning(f"{ticker} {side} {size} lot emir BEFDAY limiti nedeniyle reddedildi")
                return False
            elif max_allowed < size:
                print(f"[PSFAlgo] ⚠️ {ticker} {side}: Lot azaltıldı {size} → {max_allowed} (BEFDAY limiti)")
                size = max_allowed
                log_reasoning(f"{ticker} {side} lot BEFDAY limiti nedeniyle {size} → {max_allowed} azaltıldı")
        
        # ✅ MAXALW Size limit kontrolü
        allowed, max_allowed = self.check_maxalw_limits(ticker, side, size)
        if not allowed:
            print(f"[PSFAlgo] ❌ {ticker} {side} {size}: MAXALW size limiti aşıldı, emir gönderilmedi")
            log_reasoning(f"{ticker} {side} {size} lot emir MAXALW size limiti nedeniyle reddedildi")
            return False
        elif max_allowed < size:
            print(f"[PSFAlgo] ⚠️ {ticker} {side}: Lot azaltıldı {size} → {max_allowed} (MAXALW size limiti)")
            size = max_allowed
            log_reasoning(f"{ticker} {side} lot MAXALW size limiti nedeniyle {size} → {max_allowed} azaltıldı")
        
        # Pozisyon durumunu al
        current_position = self.get_position_size(ticker)
        
        # Pozisyon türünü belirle (4 kategori)
        order_type = self._get_order_type(side, current_position)
        
        # SMI rate kontrolü - SADECE Short arttırma işlemlerinde
        if order_type == 'SHORT_INCREASE':
            smi_rate = self.get_smi_rate(ticker)
            if smi_rate > 0.28:
                print(f"[PSFAlgo SMI FILTER] {ticker} short arttırma işlemi reddedildi - SMI rate: {smi_rate:.4f} > 0.28")
                log_reasoning(f"{ticker} short arttırma reddedildi - SMI rate: {smi_rate:.4f} > 0.28")
                return False
            else:
                print(f"[PSFAlgo SMI FILTER] {ticker} short arttırma onaylandı - SMI rate: {smi_rate:.4f} <= 0.28")
        else:
            print(f"[PSFAlgo SMI FILTER] {ticker} {order_type} işlemi - SMI kontrolü atlandı")
            
        # Long açarken short kapat
        if side == 'LONG' and current_position < 0:
            size = min(size, abs(current_position))
            print(f"[DEBUG] {ticker} için mevcut short pozisyon: {current_position}, sadece {size} lot BUY gönderilecek.")
        # Short açarken long kapat
        elif side == 'SHORT' and current_position > 0:
            size = min(size, abs(current_position))
            print(f"[DEBUG] {ticker} için mevcut long pozisyon: {current_position}, sadece {size} lot SELL gönderilecek.")
        print(f"[DEBUG] send_order çağrıldı: {ticker}, price: {price}, final_thg: {final_thg}, side: {side}, size: {size}, order_type: {order_type}")
        if size <= 0:
            print(f"[DEBUG] {ticker} için gönderilecek lot yok, emir atlanıyor.")
            return False
        if price <= 0.1:
            print(f"[DEBUG] {ticker} için fiyat çok düşük: {price}, emir gönderilmedi.")
            log_reasoning(f"{ticker} için fiyat çok düşük: {price}, emir gönderilmedi.")
            return False
        action = 'BUY' if side == 'LONG' else 'SELL'
        if hasattr(self.market_data, 'place_order'):
            # Lot'u 200'lük parçalara böl
            lot_chunks = self._split_lot_to_chunks(size, 200)
            
            print(f"[PSFAlgo LOT SPLIT] {ticker} toplam {size} lot → {len(lot_chunks)} parçaya bölündü: {lot_chunks}")
            
            # Her parça için emir gönder
            successful_orders = 0
            for i, chunk_size in enumerate(lot_chunks):
                try:
                    success = self.market_data.place_order(ticker, action, chunk_size, price=price, order_type='LIMIT')
                    if success:
                        print(f"[PSFAlgo EMIR {i+1}/{len(lot_chunks)}] ✅ {ticker} {action} {chunk_size} @ {price}")
                        successful_orders += 1
                        # Fill simulation
                        self.order_manager.on_fill(ticker, 'long' if side == 'LONG' else 'short', price, chunk_size)
                    else:
                        print(f"[PSFAlgo EMIR {i+1}/{len(lot_chunks)}] ❌ {ticker} {action} {chunk_size} başarısız")
                        
                    # Emirler arası kısa bekleme
                    if i < len(lot_chunks) - 1:
                        time.sleep(0.1)
                        
                except Exception as e:
                    print(f"[PSFAlgo EMIR {i+1}/{len(lot_chunks)}] ❌ {ticker} parça emir hatası: {e}")
            
            print(f"[PSFAlgo LOT SPLIT SONUÇ] {ticker}: {successful_orders}/{len(lot_chunks)} emir başarılı")
            
            if successful_orders > 0:
                print(f"[PSFAlgo] ✅ {ticker} için {successful_orders} parça emir gönderildi")
                return True
            else:
                print(f"[PSFAlgo] ❌ {ticker} için hiçbir emir gönderilemedi")
                return False
        else:
            print(f"[PSFAlgo] ⚠️ Market data place_order metodu yok")
            return False

    def get_smi_rate(self, ticker):
        """Ticker için SMI rate değerini döndür"""
        try:
            # Smiall.csv'den SMI rate'i oku
            df = pd.read_csv('Smiall.csv')
            row = df[df['PREF IBKR'] == ticker]
            if not row.empty:
                return float(row.iloc[0]['SMI'])
            return 0.0
        except Exception as e:
            print(f"[DEBUG] SMI rate alınamadı {ticker}: {e}")
            return 0.0

    def _get_order_type(self, side, current_position):
        """
        Emirleri 4 kategoriye ayır:
        - LONG_INCREASE: Long pozisyon arttırma
        - LONG_DECREASE: Long pozisyon azaltma  
        - SHORT_INCREASE: Short pozisyon arttırma
        - SHORT_DECREASE: Short pozisyon azaltma
        """
        if side == 'LONG':
            if current_position < 0:
                # Short pozisyon varken BUY = Short azaltma
                return 'SHORT_DECREASE'
            else:
                # Pozisyon yok veya Long pozisyon varken BUY = Long arttırma
                return 'LONG_INCREASE'
        else:  # side == 'SHORT'
            if current_position > 0:
                # Long pozisyon varken SELL = Long azaltma
                return 'LONG_DECREASE'
            else:
                # Pozisyon yok veya Short pozisyon varken SELL = Short arttırma
                return 'SHORT_INCREASE'

    def _is_number(self, val):
        try:
            float(val)
            return True
        except (ValueError, TypeError):
            return False

    def _split_lot_to_chunks(self, total_lot, chunk_size=200):
        """Lot'u belirtilen boyutta parçalara böl"""
        total_lot = int(total_lot)
        chunks = []
        
        while total_lot > 0:
            if total_lot >= chunk_size:
                chunks.append(chunk_size)
                total_lot -= chunk_size
            else:
                chunks.append(total_lot)
                total_lot = 0
                
        return chunks

    def get_current_price(self, ticker):
        """Ticker için mevcut fiyatı döndür"""
        try:
            # Önce market_data'dan fiyatı çek
            if hasattr(self.market_data, 'get_market_data'):
                # get_market_data fonksiyonu symbols parametresi istiyor
                market_data = self.market_data.get_market_data([ticker])
                if market_data and ticker in market_data and 'last' in market_data[ticker]:
                    return market_data[ticker]['last']
            
            # Alternatif: Polygon REST API'den çek
            if hasattr(self.market_data, 'get_current_price'):
                return self.market_data.get_current_price(ticker)
            
            # Alternatif: Son bilinen fiyat (eğer varsa)
            if hasattr(self.market_data, 'last_data') and ticker in self.market_data.last_data:
                last_data = self.market_data.last_data[ticker]
                if isinstance(last_data, dict) and 'last' in last_data:
                    return last_data['last']
                    
        except Exception as e:
            print(f"[PRICE] ⚠️ {ticker} fiyatı alınamadı: {e}")
            
        return None

    def advance_chain(self):
        """Chain'de bir sonraki aşamaya geç - YENİ 14 ADIMLI SİSTEM"""
        # Onay bekleniyorsa yeni adım başlatma
        if self.waiting_for_approval:
            print(f"[PSFAlgo CHAIN] ⏸️ Onay bekleniyor, yeni adım başlatılmadı")
            return
            
        # YENİ 8 ADIMLI SİSTEM (1-8)
        if self.chain_state == 'T_LOSERS':
            self.chain_state = 'T_LOSERS_FB'
            print(f"[PSFAlgo CHAIN] 1→2: T_LOSERS → T_LOSERS_FB")
        elif self.chain_state == 'T_LOSERS_FB':
            self.chain_state = 'T_GAINERS'
            print(f"[PSFAlgo CHAIN] 2→3: T_LOSERS_FB → T_GAINERS")
        elif self.chain_state == 'T_GAINERS':
            self.chain_state = 'T_GAINERS_FS'
            print(f"[PSFAlgo CHAIN] 3→4: T_GAINERS → T_GAINERS_FS")
        elif self.chain_state == 'T_GAINERS_FS':
            self.chain_state = 'LONG_TP_AS'
            print(f"[PSFAlgo CHAIN] 4→5: T_GAINERS_FS → LONG_TP_AS")
        elif self.chain_state == 'LONG_TP_AS':
            self.chain_state = 'LONG_TP_FS'
            print(f"[PSFAlgo CHAIN] 5→6: LONG_TP_AS → LONG_TP_FS")
        elif self.chain_state == 'LONG_TP_FS':
            self.chain_state = 'SHORT_TP_BB'
            print(f"[PSFAlgo CHAIN] 6→7: LONG_TP_FS → SHORT_TP_BB")
        elif self.chain_state == 'SHORT_TP_BB':
            self.chain_state = 'SHORT_TP_FB'
            print(f"[PSFAlgo CHAIN] 7→8: SHORT_TP_BB → SHORT_TP_FB")
        elif self.chain_state == 'SHORT_TP_FB':
            self.chain_state = 'T_LOSERS_OLD'
            print(f"[PSFAlgo CHAIN] 8→9: SHORT_TP_FB → T_LOSERS_OLD")
        # ESKİ 6 ADIMLI SİSTEM (9-14)
        elif self.chain_state == 'T_LOSERS_OLD':
            self.run_t_top_losers()  # 9. ESKİ T-Losers (ask sell)
        elif self.chain_state == 'T_GAINERS_OLD':
            self.run_t_top_gainers()  # 10. ESKİ T-Gainers (bid buy)
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
            return  # finish_chain çağrıldığında start_chain çağrılmamalı
        
        # Sonraki aşamayı başlat (sadece onay beklenmiyorsa)
        print(f"[PSFAlgo CHAIN] Yeni state: {self.chain_state}, pencere açılıyor...")
        self.start_chain()

    def on_window_opened(self, window):
        """Pencere açıldığında çağrılır"""
        print("[DEBUG] on_window_opened çağrıldı")
        
        # ✅ PSFAlgo aktif değilse hiçbir şey yapma
        if not self.is_active:
            print("[PSFAlgo] ⏸️ PSFAlgo pasif - pencere açılması işlenmedi")
            return
            
        self.current_window = window
        self.data_ready = False

    def on_data_ready(self, window):
        """Veri hazır olduğunda çağrılır - YENİ 14 ADIMLI SİSTEM"""
        print("[DEBUG] on_data_ready çağrıldı")
        
        # ✅ PSFAlgo aktif değilse hiçbir şey yapma
        if not self.is_active:
            print("[PSFAlgo] ⏸️ PSFAlgo pasif - veri hazır olması işlenmedi")
            return
            
        # ✅ PISDoNGU aktif değilse otomatik işlem yapma (manuel pencere açılması)
        if not self.pisdongu_active:
            print("[PSFAlgo] ℹ️ PISDoNGU pasif - manuel pencere açılması, otomatik işlem yapılmıyor")
            return
            
        self.data_ready = True
        self.current_window = window  # Her zaman güncel pencereyi kullan
        
        # Pencere tipine ve chain state'e göre işlem yap - YENİ SİSTEM
        window_title = window.title().lower()
        
        # T-LOSERS penceresi için (1. ve 2. adım)
        if "losers" in window_title:
            if self.chain_state == 'T_LOSERS':
                # 1. ADIM: FINAL BB en yüksek 5 → Bid Buy
                self.run_new_t_losers_bb_data_ready()
            elif self.chain_state == 'T_LOSERS_FB':
                # 2. ADIM: FINAL FB en yüksek 5 → Front Buy (spread koşulu ile)
                self.run_new_t_losers_fb()
                
        # T-GAINERS penceresi için (3. ve 4. adım)
        elif "gainers" in window_title:
            if self.chain_state == 'T_GAINERS':
                # 3. ADIM: FINAL AS en düşük 5 → Ask Sell
                self.run_new_t_gainers_as_data_ready()
            elif self.chain_state == 'T_GAINERS_FS':
                # 4. ADIM: FINAL FS en düşük 5 → Front Sell (spread koşulu + SMI)
                self.run_new_t_gainers_fs()
                
        # LONG TAKE PROFIT penceresi için (5. ve 6. adım)
        elif "long take profit" in window_title:
            if self.chain_state == 'LONG_TP_AS':
                # 5. ADIM: FINAL AS en düşük 5 → Ask Sell
                self.run_new_long_tp_as_data_ready()
            elif self.chain_state == 'LONG_TP_FS':
                # 6. ADIM: FINAL FS en düşük 5 → Front Sell (spread koşulu + SMI)
                self.run_new_long_tp_fs()
            # ESKİ SİSTEM (11. ve 12. adım)
            elif self.chain_state == 'LONG_TP_ASK':
                self.run_long_tp_ask_sell()
            elif self.chain_state == 'LONG_TP_FRONT':
                self.run_long_tp_front_sell()
                
        # SHORT TAKE PROFIT penceresi için (7. ve 8. adım)
        elif "short take profit" in window_title:
            if self.chain_state == 'SHORT_TP_BB':
                # 7. ADIM: FINAL BB en yüksek 5 → Bid Buy
                self.run_new_short_tp_bb_data_ready()
            elif self.chain_state == 'SHORT_TP_FB':
                # 8. ADIM: FINAL FB front buy - mevcut Short TP penceresinde işlem yap
                print("[PSF CHAIN 8] Short TP FB - mevcut pencerede FINAL FB işlemi tetikleniyor...")
                if self.current_window and hasattr(self.current_window, 'rows'):
                    self.run_new_short_tp_fb()
                else:
                    print("[PSF CHAIN 8] ❌ Short TP penceresi bulunamadı, bir sonraki adıma geç")
                    self.advance_chain()
            # ESKİ SİSTEM (13. ve 14. adım)
            elif self.chain_state == 'SHORT_TP_BID':
                self.run_short_tp_bid_buy()
            elif self.chain_state == 'SHORT_TP_FRONT':
                self.run_short_tp_front_buy()
        else:
            print(f"[PSFAlgo] Pencere '{window.title()}' için otomatik işlem yapılmıyor (chain_state: {self.chain_state})")

    def run_t_top_losers(self):
        """T-top losers işlemlerini yap - hisse seç ve onay penceresi aç"""
        print("[DEBUG] run_t_top_losers başladı")
        
        # ✅ PSFAlgo aktif değilse hiçbir şey yapma
        if not self.is_active:
            print("[PSFAlgo] ⏸️ PSFAlgo pasif - T-top losers işlenmedi")
            return
            
        if not self.current_window:
            print("[DEBUG] current_window yok")
            return
            
        rows = self.current_window.rows
        columns = self.current_window.COLUMNS
        selected = set()
        reasoning_msgs = []
        
        # Filtrele ve seç
        for row in rows:
            try:
                ticker = row[1]
                bid_buy_ucuzluk = float(row[columns.index('Bid buy Ucuzluk skoru')])
                if bid_buy_ucuzluk <= -0.25:
                    selected.add(ticker)
                    msg = f"{ticker} seçildi çünkü bid buy ucuzluk {bid_buy_ucuzluk} (eşik: -0.25)"
                    print("[REASONING]", msg)
                    reasoning_msgs.append(msg)
            except Exception as e:
                print(f"[DEBUG] Skipping {row[1] if len(row)>1 else row} - Error: {e}")
                continue
        
        # Seçili hisseleri GUI'ye aktar
        self.current_window.selected_tickers = selected
        
        # Reasoning logla
        for msg in reasoning_msgs:
            log_reasoning(msg)
        
        # Bid buy butonunu tetikle
        print("[DEBUG] send_bid_buy_orders çağrılıyor...")
        self.current_window.send_bid_buy_orders()
        
        # PSFAlgo chain'i devam ettirme - onay sonrası yapılacak
        print("[PSFAlgo CHAIN] T-top losers onay penceresi açıldı, kullanıcı onayı bekleniyor...")

    def run_t_top_gainers(self):
        """T-top gainers işlemlerini yap - hisse seç ve onay penceresi aç"""
        print("[DEBUG] run_t_top_gainers başladı")
        
        # ✅ PSFAlgo aktif değilse hiçbir şey yapma
        if not self.is_active:
            print("[PSFAlgo] ⏸️ PSFAlgo pasif - T-top gainers işlenmedi")
            return
            
        if not self.current_window:
            print("[DEBUG] current_window yok")
            return
            
        rows = self.current_window.rows
        columns = self.current_window.COLUMNS
        selected = set()
        reasoning_msgs = []
        
        # Ask sell pahalilik >= 0.25 olanları seç (en yüksek 30)
        valid_rows = []
        for row in rows:
            try:
                ticker = row[1]
                ask_sell_pahali = float(row[columns.index('Ask sell pahalilik skoru')])
                if ask_sell_pahali >= 0.25:
                    valid_rows.append((ticker, ask_sell_pahali, row))
                    msg = f"{ticker} değerlendiriliyor - ask sell pahalilik {ask_sell_pahali}"
                    reasoning_msgs.append(msg)
            except Exception as e:
                print(f"[DEBUG] Skipping {row[1] if len(row)>1 else row} - Error: {e}")
                continue
        
        # En yüksek 30'u seç
        valid_rows.sort(key=lambda x: x[1], reverse=True)
        selected = set([ticker for ticker, _, _ in valid_rows[:30]])
        
        if selected:
            for ticker, skor, _ in valid_rows[:30]:
                msg = f"{ticker} seçildi - ask sell pahalilik {skor} (top 30)"
                print("[REASONING]", msg)
                reasoning_msgs.append(msg)
        
        # Seçili hisseleri GUI'ye aktar
        self.current_window.selected_tickers = selected
        
        # Reasoning logla
        for msg in reasoning_msgs:
            log_reasoning(msg)
        
        # Ask sell butonunu tetikle
        print("[DEBUG] send_ask_sell_orders çağrılıyor...")
        self.current_window.send_ask_sell_orders()
        
        # PSFAlgo chain'i devam ettirme - onay sonrası yapılacak
        print("[PSFAlgo CHAIN] T-top gainers onay penceresi açıldı, kullanıcı onayı bekleniyor...")

    def run_long_tp_ask_sell(self):
        """Long TP Ask Sell işlemlerini yap - hisse seç ve onay penceresi aç"""
        print("[DEBUG] run_long_tp_ask_sell başladı")
        
        if not self.is_active:
            print("[PSFAlgo] ⏸️ PSFAlgo pasif - Long TP Ask Sell işlenmedi")
            return
            
        if not self.current_window:
            print("[DEBUG] current_window yok")
            return
            
        rows = self.current_window.rows
        columns = self.current_window.COLUMNS
        selected = set()
        reasoning_msgs = []
        
        # Ask sell pahalilik > 0.20 olanları seç
        for row in rows:
            try:
                ticker = row[1]
                ask_sell_pahali = float(row[columns.index('Ask sell pahalilik skoru')])
                if ask_sell_pahali > 0.20:
                    selected.add(ticker)
                    msg = f"{ticker} seçildi - ask sell pahalilik {ask_sell_pahali} > 0.20"
                    print("[REASONING]", msg)
                    reasoning_msgs.append(msg)
            except Exception as e:
                print(f"[DEBUG] Skipping {row[1] if len(row)>1 else row} - Error: {e}")
                continue
        
        if not selected:
            print("[PSFAlgo CHAIN] ❌ Ask sell için uygun long pozisyon bulunamadı")
            self.advance_chain()
            return
        
        # Seçili hisseleri GUI'ye aktar
        self.current_window.selected_tickers = selected
        
        # Reasoning logla
        for msg in reasoning_msgs:
            log_reasoning(msg)
        
        # Ask sell butonunu tetikle
        print("[DEBUG] send_ask_sell_orders çağrılıyor...")
        self.current_window.send_ask_sell_orders()
        
        print("[PSFAlgo CHAIN] Long TP Ask Sell onay penceresi açıldı, kullanıcı onayı bekleniyor...")

    def run_long_tp_front_sell(self):
        """Long TP Front Sell işlemlerini yap - hisse seç ve onay penceresi aç"""
        print("[DEBUG] run_long_tp_front_sell başladı")
        
        if not self.is_active:
            print("[PSFAlgo] ⏸️ PSFAlgo pasif - Long TP Front Sell işlenmedi")
            return
            
        if not self.current_window:
            print("[DEBUG] current_window yok")
            return
            
        rows = self.current_window.rows
        columns = self.current_window.COLUMNS
        selected = set()
        reasoning_msgs = []
        
        # Front sell pahalilik > 0.10 olanları seç (en yüksek 3)
        valid_rows = []
        for row in rows:
            try:
                ticker = row[1]
                front_sell_pahali = float(row[columns.index('Front sell pahalilik skoru')])
                if front_sell_pahali > 0.10:
                    valid_rows.append((ticker, front_sell_pahali, row))
                    msg = f"{ticker} değerlendiriliyor - front sell pahalilik {front_sell_pahali}"
                    reasoning_msgs.append(msg)
            except Exception as e:
                print(f"[DEBUG] Skipping {row[1] if len(row)>1 else row} - Error: {e}")
                continue
        
        # En yüksek 3'ü seç
        valid_rows.sort(key=lambda x: x[1], reverse=True)
        selected = set([ticker for ticker, _, _ in valid_rows[:3]])
        
        if not selected:
            print("[PSFAlgo CHAIN] ❌ Front sell için uygun long pozisyon bulunamadı")
            self.advance_chain()
            return
        
        if selected:
            for ticker, skor, _ in valid_rows[:3]:
                msg = f"{ticker} seçildi - front sell pahalilik {skor} (top 3)"
                print("[REASONING]", msg)
                reasoning_msgs.append(msg)
        
        # Seçili hisseleri GUI'ye aktar
        self.current_window.selected_tickers = selected
        
        # Reasoning logla
        for msg in reasoning_msgs:
            log_reasoning(msg)
        
        # Front sell butonunu tetikle
        print("[DEBUG] send_front_sell_orders çağrılıyor...")
        self.current_window.send_front_sell_orders()
        
        print("[PSFAlgo CHAIN] Long TP Front Sell onay penceresi açıldı, kullanıcı onayı bekleniyor...")

    def run_short_tp_bid_buy(self):
        """Short TP Bid Buy işlemlerini yap - hisse seç ve onay penceresi aç"""
        print("[DEBUG] run_short_tp_bid_buy başladı")
        
        if not self.is_active:
            print("[PSFAlgo] ⏸️ PSFAlgo pasif - Short TP Bid Buy işlenmedi")
            return
            
        if not self.current_window:
            print("[DEBUG] current_window yok")
            return
            
        rows = self.current_window.rows
        columns = self.current_window.COLUMNS
        selected = set()
        reasoning_msgs = []
        
        # Bid buy ucuzluk < -0.20 olanları seç
        for row in rows:
            try:
                ticker = row[1]
                bid_buy_ucuzluk = float(row[columns.index('Bid buy Ucuzluk skoru')])
                if bid_buy_ucuzluk < -0.20:
                    selected.add(ticker)
                    msg = f"{ticker} seçildi - bid buy ucuzluk {bid_buy_ucuzluk} < -0.20"
                    print("[REASONING]", msg)
                    reasoning_msgs.append(msg)
            except Exception as e:
                print(f"[DEBUG] Skipping {row[1] if len(row)>1 else row} - Error: {e}")
                continue
        
        if not selected:
            print("[PSFAlgo CHAIN] ❌ Bid buy için uygun short pozisyon bulunamadı")
            self.advance_chain()
            return
        
        # Seçili hisseleri GUI'ye aktar
        self.current_window.selected_tickers = selected
        
        # Reasoning logla
        for msg in reasoning_msgs:
            log_reasoning(msg)
        
        # Bid buy butonunu tetikle
        print("[DEBUG] send_bid_buy_orders çağrılıyor...")
        self.current_window.send_bid_buy_orders()
        
        print("[PSFAlgo CHAIN] Short TP Bid Buy onay penceresi açıldı, kullanıcı onayı bekleniyor...")

    # Diğer yardımcı fonksiyonlar (skor hesaplama, pozisyon kontrolü, emir gönderme, reasoning üretme) burada olacak. 

    def test_reverse_order_system(self, ticker="JAGX", side="long", fill_price=2.89, fill_size=200):
        """Reverse order sistemini test et"""
        print(f"[TEST] 🧪 Reverse order sistemi test ediliyor...")
        print(f"[TEST] Parametreler: {ticker} {side} {fill_size} lot @ {fill_price}")
        print(f"[TEST] PSFAlgo aktif mi: {self.is_active}")
        
        if not self.is_active:
            print(f"[TEST] ❌ PSFAlgo pasif - test için aktifleştirin")
            return False
        
        # Test fill'i simüle et
        print(f"[TEST] 📈 Test fill simülasyonu başlatılıyor...")
        self.on_fill(ticker, side, fill_price, fill_size)
        
        # Günlük fill durumunu kontrol et
        daily_total = self.get_daily_fill_total(ticker, side)
        reverse_orders = self.get_daily_reverse_orders(ticker)
        
        print(f"[TEST] 📊 Test sonuçları:")
        print(f"[TEST]   - {ticker} {side} günlük toplam: {daily_total} lot")
        print(f"[TEST]   - {ticker} reverse order toplam: {reverse_orders} lot")
        print(f"[TEST] ✅ Test tamamlandı")
        
        return True

    def debug_daily_fills(self):
        """Günlük fill durumunu debug et"""
        print(f"[DEBUG] 📊 Günlük fill durumu:")
        print(f"[DEBUG] Bugün: {self.today}")
        print(f"[DEBUG] PSFAlgo aktif: {self.is_active}")
        
        if not self.daily_fills:
            print(f"[DEBUG] ❌ Henüz günlük fill yok")
            return
        
        for ticker, data in self.daily_fills.items():
            print(f"[DEBUG] {ticker}:")
            print(f"[DEBUG]   - Long: {data.get('long', 0)} lot")
            print(f"[DEBUG]   - Short: {data.get('short', 0)} lot") 
            print(f"[DEBUG]   - Reverse orders: {data.get('reverse_orders', 0)} lot")
            print(f"[DEBUG]   - Tarih: {data.get('date', 'N/A')}")

    def get_chain_state_title(self):
        """PISDoNGU chain state'ine göre işlem başlığını döndür - YENİ 14 ADIMLI SİSTEM"""
        if not self.pisdongu_active:
            return ""
        
        state_titles = {
            'IDLE': "",
            # YENİ 8 ADIMLI SİSTEM (1-8)
            'T_LOSERS': "🔄 PISDoNGU (1/14) - T-Losers FINAL BB → Bid Buy",
            'T_LOSERS_FB': "🔄 PISDoNGU (2/14) - T-Losers FINAL FB → Front Buy",
            'T_GAINERS': "🔄 PISDoNGU (3/14) - T-Gainers FINAL AS → Ask Sell",
            'T_GAINERS_FS': "🔄 PISDoNGU (4/14) - T-Gainers FINAL FS → Front Sell",
            'LONG_TP_AS': "🔄 PISDoNGU (5/14) - Long TP FINAL AS → Ask Sell",
            'LONG_TP_FS': "🔄 PISDoNGU (6/14) - Long TP FINAL FS → Front Sell",
            'SHORT_TP_BB': "🔄 PISDoNGU (7/14) - Short TP FINAL BB → Bid Buy",
            'SHORT_TP_FB': "🔄 PISDoNGU (8/14) - Short TP FINAL FB → Front Buy",
            # ESKİ 6 ADIMLI SİSTEM (9-14)
            'T_LOSERS_OLD': "🔄 PISDoNGU (9/14) - T-Losers (Eski Sistem)",
            'T_GAINERS_OLD': "🔄 PISDoNGU (10/14) - T-Gainers (Eski Sistem)",
            'LONG_TP_ASK': "🔄 PISDoNGU (11/14) - Long TP Ask Sell (Eski)",
            'LONG_TP_FRONT': "🔄 PISDoNGU (12/14) - Long TP Front Sell (Eski)",
            'SHORT_TP_BID': "🔄 PISDoNGU (13/14) - Short TP Bid Buy (Eski)",
            'SHORT_TP_FRONT': "🔄 PISDoNGU (14/14) - Short TP Front Buy (Eski)",
            'FINISHED': "✅ PISDoNGU Tamamlandı"
        }
        
        return state_titles.get(self.chain_state, "")

    def run_new_long_tp_as(self):
        """
        5. ADIM: Long Take Profit penceresinde FINAL AS en düşük 5 hisse → Hidden Ask Sell
        """
        print("[PSF NEW CHAIN 5/14] 🎯 Long TP FINAL AS → Ask Sell")
        
        if not self.is_active:
            print("[PSFAlgo] ⏸️ PSFAlgo pasif - Long TP AS işlenmedi")
            return
            
        # Long Take Profit penceresini aç
        if self.main_window and hasattr(self.main_window, 'open_long_take_profit'):
            self.main_window.open_long_take_profit()
            print("[PSF CHAIN 5] Long Take Profit penceresi açılıyor...")
        else:
            print("[PSF CHAIN 5] ❌ Long Take Profit penceresi açılamadı")
            self.advance_chain()
    
    def run_new_long_tp_fs(self):
        """
        6. ADIM: Long Take Profit penceresinde FINAL FS en düşük 5 hisse → Hidden Front Sell (spread koşulu + SMI kontrolü)
        """
        print("[PSF NEW CHAIN 6/14] 🎯 Long TP FINAL FS → Front Sell (spread koşulu + SMI)")
        
        if not self.is_active or not self.current_window:
            print("[PSF CHAIN 6] ❌ Pencere bulunamadı veya PSFAlgo pasif")
            self.advance_chain()
            return
        
        # FINAL FS en düşük 15 hisse seç (daha fazla seç ki cross-step validation sonrası 5 tane kalabilsin)
        selected_stocks = self.get_top_stocks_by_score(
            self.current_window, 
            'Final FS skor', 
            count=15, 
            ascending=True,   # En düşük
            score_range=(0, 1500)
        )
        
        if not selected_stocks:
            print("[PSF CHAIN 6] ❌ FINAL FS kriterleri sağlayan hisse bulunamadı")
            self.advance_chain()
            return
        
        # ✅ Cross-step validation - şirket limiti ve MAXALW kontrolü
        cross_step_valid = self.filter_candidates_by_cross_step_rules(
            selected_stocks[:10],  # İlk 10'u kontrol et 
            step_number=6,
            order_side='SELL',
            target_count=5,  # 5 hisse hedefle
            extended_candidates=selected_stocks  # Elenen hisselerin yerine diğer adayları geçir
        )
        
        # Long pozisyon kontrolü + Spread koşulu + SMI kontrolü ile hisse filtrele
        valid_tickers = []
        
        for ticker, score in cross_step_valid[:5]:  # İlk 5'i al
            # Long pozisyon kontrolü
            current_position = self.get_position_size(ticker)
            if current_position <= 0:
                print(f"[PSF CHAIN 6] ❌ {ticker} (FS:{score:.2f}) - Long pozisyon yok ({current_position})")
                continue
                
            # SMI kontrolü (short arttırma durumu için)
            if current_position > 0:  # Long azaltma için SMI kontrolü yapmaya gerek yok
                pass  # Long azaltma işlemi SMI kontrolü gerektirmez
            elif current_position <= 0:  # Short arttırma durumu
                smi_rate = self.get_smi_rate(ticker)
                if smi_rate > 0.28:
                    print(f"[PSF CHAIN 6] ❌ {ticker} (FS:{score:.2f}) - SMI {smi_rate:.4f} > 0.28")
                    continue
                    
            # Spread koşulu kontrolü
            target_price = self.get_price_from_window(self.current_window, ticker, 'Last price')
            if not target_price:
                print(f"[PSF CHAIN 6] ❌ {ticker} (FS:{score:.2f}) - Last price alınamadı")
                continue
            spread_ok, spread_msg = self.check_front_spread_condition(ticker, 'FRONT_SELL', target_price)
            
            if spread_ok:
                valid_tickers.append(ticker)
                print(f"[PSF CHAIN 6] ✅ {ticker} (FS:{score:.2f}) - {spread_msg}")
            else:
                print(f"[PSF CHAIN 6] ❌ {ticker} (FS:{score:.2f}) - {spread_msg}")
        
        # ✅ Eğer yeterli hisse kalmadıysa, genişletilmiş aday listesinden devam et
        if len(valid_tickers) < 5 and len(cross_step_valid) < len(selected_stocks):
            print(f"[PSF CHAIN 6] ⚠️ Spread koşulu sonrası {len(valid_tickers)} hisse kaldı, genişletilmiş adaylardan devam ediliyor...")
            
            # Zaten kontrol edilen hisseleri takip et
            checked_tickers = set([c[0] if isinstance(c, (list, tuple)) else c for c in cross_step_valid])
            
            # Genişletilmiş aday listesinden devam et
            for candidate in selected_stocks:
                ticker = candidate[0] if isinstance(candidate, (list, tuple)) else candidate
                score = candidate[1] if isinstance(candidate, (list, tuple)) and len(candidate) > 1 else 0
                
                # Zaten kontrol edilmiş hisseleri atla
                if ticker in checked_tickers:
                    continue
                
                # Hedef sayıya ulaştık mı?
                if len(valid_tickers) >= 5:
                    break
                
                # Long pozisyon kontrolü
                current_position = self.get_position_size(ticker)
                if current_position <= 0:
                    print(f"[PSF CHAIN 6] ❌ {ticker} (FS:{score:.2f}) - Long pozisyon yok ({current_position}) (genişletilmiş aday)")
                    continue
                    
                # Spread kontrolü
                target_price = self.get_price_from_window(self.current_window, ticker, 'Last price')
                if not target_price:
                    print(f"[PSF CHAIN 6] ❌ {ticker} (FS:{score:.2f}) - Last price alınamadı (genişletilmiş aday)")
                    continue
                spread_ok, spread_msg = self.check_front_spread_condition(ticker, 'FRONT_SELL', target_price)
                
                if spread_ok:
                    valid_tickers.append(ticker)
                    print(f"[PSF CHAIN 6] ✅ {ticker} (FS:{score:.2f}) - Genişletilmiş adaydan eklendi - {spread_msg}")
                else:
                    print(f"[PSF CHAIN 6] ❌ {ticker} (FS:{score:.2f}) - {spread_msg} (genişletilmiş aday)")
        
        if not valid_tickers:
            print("[PSF CHAIN 6] ❌ Hiçbir hisse koşulları sağlamıyor")
            self.advance_chain()
            return
        
        # GUI'ye hisseleri aktar ve Front Sell emri gönder
        self.current_window.selected_tickers = set(valid_tickers[:5])
        
        print(f"[PSF CHAIN 6] 📋 {len(valid_tickers[:5])} hisse seçildi: {list(valid_tickers[:5])}")
        
        # ✅ Onay bekleme durumunu aktif et
        self.waiting_for_approval = True
        
        # Front Sell butonunu tetikle
        print("[DEBUG] send_front_sell_orders çağrılıyor...")
        self.current_window.send_front_sell_orders()
        print("[PSF CHAIN 6] Front Sell emirleri gönderildi, kullanıcı onayı bekleniyor...")
        print("[PSF CHAIN 6] ⏸️ Onay bekleme modu aktif - advance_chain bloke edildi")
    
    def run_new_short_tp_bb(self):
        """
        7. ADIM: Short Take Profit penceresinde FINAL BB en yüksek 5 hisse → Hidden Bid Buy
        """
        print("[PSF NEW CHAIN 7/14] 🎯 Short TP FINAL BB → Bid Buy")
        
        if not self.is_active:
            print("[PSFAlgo] ⏸️ PSFAlgo pasif - Short TP BB işlenmedi")
            return
            
        # Short Take Profit penceresini aç
        if self.main_window and hasattr(self.main_window, 'open_short_take_profit'):
            self.main_window.open_short_take_profit()
            print("[PSF CHAIN 7] Short Take Profit penceresi açılıyor...")
        else:
            print("[PSF CHAIN 7] ❌ Short Take Profit penceresi açılamadı")
            self.advance_chain()
    
    def run_new_short_tp_fb(self):
        """
        8. ADIM: Short Take Profit penceresinde FINAL FB en yüksek 5 hisse → Hidden Front Buy (spread koşulu)
        """
        print("[PSF NEW CHAIN 8/14] 🎯 Short TP FINAL FB → Front Buy (spread koşulu)")
        
        if not self.is_active or not self.current_window:
            print("[PSF CHAIN 8] ❌ Pencere bulunamadı veya PSFAlgo pasif")
            self.advance_chain()
            return
        
        # FINAL FB en yüksek 15 hisse seç (daha fazla seç ki cross-step validation sonrası 5 tane kalabilsin)
        selected_stocks = self.get_top_stocks_by_score(
            self.current_window, 
            'Final FB skor', 
            count=15, 
            ascending=False,  # En yüksek
            score_range=(0, 1500)
        )
        
        if not selected_stocks:
            print("[PSF CHAIN 8] ❌ FINAL FB kriterleri sağlayan hisse bulunamadı")
            self.advance_chain()
            return
        
        # ✅ Cross-step validation - şirket limiti ve MAXALW kontrolü
        cross_step_valid = self.filter_candidates_by_cross_step_rules(
            selected_stocks[:10],  # İlk 10'u kontrol et 
            step_number=8,
            order_side='BUY',
            target_count=5,  # 5 hisse hedefle
            extended_candidates=selected_stocks  # Elenen hisselerin yerine diğer adayları geçir
        )
        
        # Short pozisyon kontrolü + Spread koşulu ile hisse filtrele
        valid_tickers = []
        
        for ticker, score in cross_step_valid[:5]:  # İlk 5'i al
            # Short pozisyon kontrolü
            current_position = self.get_position_size(ticker)
            if current_position >= 0:
                print(f"[PSF CHAIN 8] ❌ {ticker} (FB:{score:.2f}) - Short pozisyon yok ({current_position})")
                continue
                
            # Spread koşulu kontrolü
            target_price = self.get_price_from_window(self.current_window, ticker, 'Last price')
            if not target_price:
                print(f"[PSF CHAIN 8] ❌ {ticker} (FB:{score:.2f}) - Last price alınamadı")
                continue
            spread_ok, spread_msg = self.check_front_spread_condition(ticker, 'FRONT_BUY', target_price)
            
            if spread_ok:
                valid_tickers.append(ticker)
                print(f"[PSF CHAIN 8] ✅ {ticker} (FB:{score:.2f}) - {spread_msg}")
            else:
                print(f"[PSF CHAIN 8] ❌ {ticker} (FB:{score:.2f}) - {spread_msg}")
        
        # ✅ Eğer yeterli hisse kalmadıysa, genişletilmiş aday listesinden devam et
        if len(valid_tickers) < 5 and len(cross_step_valid) < len(selected_stocks):
            print(f"[PSF CHAIN 8] ⚠️ Spread koşulu sonrası {len(valid_tickers)} hisse kaldı, genişletilmiş adaylardan devam ediliyor...")
            
            # Zaten kontrol edilen hisseleri takip et
            checked_tickers = set([c[0] if isinstance(c, (list, tuple)) else c for c in cross_step_valid])
            
            # Genişletilmiş aday listesinden devam et
            for candidate in selected_stocks:
                ticker = candidate[0] if isinstance(candidate, (list, tuple)) else candidate
                score = candidate[1] if isinstance(candidate, (list, tuple)) and len(candidate) > 1 else 0
                
                # Zaten kontrol edilmiş hisseleri atla
                if ticker in checked_tickers:
                    continue
                
                # Hedef sayıya ulaştık mı?
                if len(valid_tickers) >= 5:
                    break
                
                # Short pozisyon kontrolü
                current_position = self.get_position_size(ticker)
                if current_position >= 0:
                    print(f"[PSF CHAIN 8] ❌ {ticker} (FB:{score:.2f}) - Short pozisyon yok ({current_position}) (genişletilmiş aday)")
                    continue
                    
                # Spread kontrolü
                target_price = self.get_price_from_window(self.current_window, ticker, 'Last price')
                if not target_price:
                    print(f"[PSF CHAIN 8] ❌ {ticker} (FB:{score:.2f}) - Last price alınamadı (extended)")
                    continue
                spread_ok, spread_msg = self.check_front_spread_condition(ticker, 'FRONT_BUY', target_price)
                
                if spread_ok:
                    valid_tickers.append(ticker)
                    print(f"[PSF CHAIN 8] ✅ {ticker} (FB:{score:.2f}) - {spread_msg}")
                    
                    if len(valid_tickers) >= 5:
                        break
        
        if not valid_tickers:
            print("[PSF CHAIN 8] ❌ Hiçbir hisse spread koşulunu sağlamıyor")
            self.advance_chain()
            return
        
        # GUI'ye hisseleri aktar ve Front Buy emri gönder
        self.current_window.selected_tickers = set(valid_tickers[:5])
        
        print(f"[PSF CHAIN 8] 📋 {len(valid_tickers[:5])} hisse seçildi: {list(valid_tickers[:5])}")
        
        # ✅ Onay bekleme durumunu aktif et
        self.waiting_for_approval = True
        
        # Front Buy butonunu tetikle
        print("[DEBUG] send_front_buy_orders çağrılıyor...")
        self.current_window.send_front_buy_orders()
        print("[PSF CHAIN 8] Front Buy emirleri gönderildi, kullanıcı onayı bekleniyor...")
        print("[PSF CHAIN 8] ⏸️ Onay bekleme modu aktif - advance_chain bloke edildi")
    
    # ================== YENİ SİSTEM ON_DATA_READY GÜNCELLEMESİ ==================

    def run_new_t_losers_bb_data_ready(self):
        """
        1. ADIM DATA READY: T-Top Losers penceresinde FINAL BB en yüksek 5 hisse seç → Bid Buy
        """
        print("[PSF NEW CHAIN 1/14] 📊 T-Losers FINAL BB → Bid Buy (data ready)")
        
        if not self.is_active or not self.current_window:
            print("[PSF CHAIN 1] ❌ Pencere bulunamadı veya PSFAlgo pasif")
            self.advance_chain()
            return
        
        # FINAL BB en yüksek 5 hisse seç
        selected_stocks = self.get_top_stocks_by_score(
            self.current_window, 
            'Final BB skor', 
            count=15,  # Daha fazla seç ki çakışma filtresi sonrası 5 tane kalabilsin
            ascending=False,  # En yüksek
            score_range=(0, 1500)
        )
        
        if not selected_stocks:
            print("[PSF CHAIN 1] ❌ FINAL BB kriterleri sağlayan hisse bulunamadı")
            self.advance_chain()
            return
        
        # ✅ ÇAKİŞMA FİLTRESİ - Mevcut BUY emirlerini kontrol et
        filtered_stocks = self.filter_stocks_by_existing_orders(
            selected_stocks, 
            'BUY', 
            self.current_window
        )
        
        if len(filtered_stocks) < 5:
            print(f"[PSF CHAIN 1] ⚠️ Çakışma filtresi sonrası sadece {len(filtered_stocks)} hisse kaldı, genişletiliyor...")
            
            # Genişletilmiş seçim yap
            extended_stocks = self.get_extended_stock_selection(
                self.current_window,
                'Final BB skor',
                original_count=15,
                needed_count=5 - len(filtered_stocks),
                ascending=False,
                score_range=(0, 1500),
                order_side='BUY'
            )
            
            filtered_stocks = extended_stocks
        
        # ✅ Cross-step validation - şirket limiti ve MAXALW kontrolü
        # Genişletilmiş aday listesini hazırla (çakışma filtresi sonrası kalan tüm hisseler)
        extended_candidates = filtered_stocks
        
        cross_step_valid = self.filter_candidates_by_cross_step_rules(
            filtered_stocks[:10],  # İlk 10'u kontrol et 
            step_number=1,
            order_side='BUY',
            target_count=5,  # 5 hisse hedefle
            extended_candidates=extended_candidates  # Elenen hisselerin yerine diğer adayları geçir
        )
        
        # Pozisyon güvenliği kontrolü ile hisse filtrele
        valid_tickers = []
        
        for ticker, score in cross_step_valid[:5]:  # İlk 5'i al
            # ✅ HALF SIZED kontrolü - dinamik lot sistemi (PSFAlgo2 ile uyumlu)
            if ticker in self.half_sized_list:
                # Varsayılan lot boyutu (şu anda 200, gelecekte değişebilir)
                intended_lot_size = getattr(self, 'default_lot_size', 200)
                half_sized_lot = intended_lot_size // 2
                minimum_lot_threshold = 200  # Minimum kabul edilebilir lot
                
                if intended_lot_size < 400:  # 400'ün altındaysa yarısı 200'den az olacak
                    print(f"[PSF CHAIN 1] ⏭️ {ticker} half-sized listesinde ({intended_lot_size} → {half_sized_lot} lot < {minimum_lot_threshold} minimum), atlanıyor")
                    continue
                else:
                    print(f"[PSF CHAIN 1] ✅ {ticker} half-sized listesinde kabul edildi ({intended_lot_size} → {half_sized_lot} lot ≥ {minimum_lot_threshold})")
            
            # Pozisyon güvenli lot hesapla
            safe_lot = self.get_position_safe_lot_size(ticker, 'BUY', 200)
            
            if safe_lot > 0:
                valid_tickers.append(ticker)
                print(f"[PSF CHAIN 1] ✅ {ticker} (BB:{score:.2f}) - Güvenli lot: {safe_lot}")
            else:
                print(f"[PSF CHAIN 1] ❌ {ticker} (BB:{score:.2f}) - Pozisyon güvenliği: {safe_lot}")
        
        # ✅ Eğer yeterli hisse kalmadıysa, genişletilmiş aday listesinden devam et
        if len(valid_tickers) < 5 and len(cross_step_valid) < len(extended_candidates):
            print(f"[PSF CHAIN 1] ⚠️ Pozisyon güvenliği sonrası {len(valid_tickers)} hisse kaldı, genişletilmiş adaylardan devam ediliyor...")
            
            # Zaten kontrol edilen hisseleri takip et
            checked_tickers = set([c[0] if isinstance(c, (list, tuple)) else c for c in cross_step_valid])
            
            # Genişletilmiş aday listesinden devam et
            for candidate in extended_candidates:
                ticker = candidate[0] if isinstance(candidate, (list, tuple)) else candidate
                score = candidate[1] if isinstance(candidate, (list, tuple)) and len(candidate) > 1 else 0
                
                # Zaten kontrol edilmiş hisseleri atla
                if ticker in checked_tickers:
                    continue
                
                # Hedef sayıya ulaştık mı?
                if len(valid_tickers) >= 5:
                    break
                
                # ✅ HALF SIZED kontrolü
                if ticker in self.half_sized_list:
                    intended_lot_size = getattr(self, 'default_lot_size', 200)
                    half_sized_lot = intended_lot_size // 2
                    minimum_lot_threshold = 200
                    
                    if intended_lot_size < 400:
                        print(f"[PSF CHAIN 1] ⏭️ {ticker} half-sized listesinde (genişletilmiş aday), atlanıyor")
                        continue
                
                # Pozisyon güvenli lot hesapla
                safe_lot = self.get_position_safe_lot_size(ticker, 'BUY', 200)
                
                if safe_lot > 0:
                    valid_tickers.append(ticker)
                    print(f"[PSF CHAIN 1] ✅ {ticker} (BB:{score:.2f}) - Genişletilmiş adaydan eklendi, güvenli lot: {safe_lot}")
                else:
                    print(f"[PSF CHAIN 1] ❌ {ticker} (BB:{score:.2f}) - Pozisyon güvenliği: {safe_lot} (genişletilmiş aday)")
        
        if not valid_tickers:
            print("[PSF CHAIN 1] ❌ Hiçbir hisse tüm güvenlik kontrollerini sağlamıyor")
            self.advance_chain()
            return
        
        # GUI'ye hisseleri aktar ve Bid Buy emri gönder
        self.current_window.selected_tickers = set(valid_tickers[:5])
        
        print(f"[PSF CHAIN 1] 📋 {len(valid_tickers[:5])} hisse seçildi: {list(valid_tickers[:5])}")
        print(f"[PSF CHAIN 1] 🔍 Çakışma kontrolü: Mevcut BUY emirlerle ±0.08 cent toleransında çakışma kontrolü yapıldı")
        
        # ✅ Onay bekleme durumunu aktif et
        self.waiting_for_approval = True
        
        # Bid Buy butonunu tetikle
        self.current_window.send_bid_buy_orders()
        print("[PSF CHAIN 1] Bid Buy emirleri gönderildi, kullanıcı onayı bekleniyor...")
        print("[PSF CHAIN 1] ⏸️ Onay bekleme modu aktif - advance_chain bloke edildi")
    
    def run_new_t_gainers_as_data_ready(self):
        """
        3. ADIM DATA READY: T-Top Gainers penceresinde FINAL AS en düşük 5 hisse seç → Ask Sell
        """
        print("[PSF NEW CHAIN 3/14] 📊 T-Gainers FINAL AS → Ask Sell (data ready)")
        
        if not self.is_active or not self.current_window:
            print("[PSF CHAIN 3] ❌ Pencere bulunamadı veya PSFAlgo pasif")
            self.advance_chain()
            return
        
        # FINAL AS en düşük 5 hisse seç
        selected_stocks = self.get_top_stocks_by_score(
            self.current_window, 
            'Final AS skor', 
            count=15,  # Daha fazla seç ki çakışma filtresi sonrası 5 tane kalabilsin
            ascending=True,   # En düşük
            score_range=(0, 1500)
        )
        
        if not selected_stocks:
            print("[PSF CHAIN 3] ❌ FINAL AS kriterleri sağlayan hisse bulunamadı")
            self.advance_chain()
            return
        
        # ✅ ÇAKİŞMA FİLTRESİ - Mevcut SELL emirlerini kontrol et
        filtered_stocks = self.filter_stocks_by_existing_orders(
            selected_stocks, 
            'SELL', 
            self.current_window
        )
        
        if len(filtered_stocks) < 5:
            print(f"[PSF CHAIN 3] ⚠️ Çakışma filtresi sonrası sadece {len(filtered_stocks)} hisse kaldı, genişletiliyor...")
            
            # Genişletilmiş seçim yap
            extended_stocks = self.get_extended_stock_selection(
                self.current_window,
                'Final AS skor',
                original_count=15,
                needed_count=5 - len(filtered_stocks),
                ascending=True,
                score_range=(0, 1500),
                order_side='SELL'
            )
            
            filtered_stocks = extended_stocks
        
        # ✅ Cross-step validation - şirket limiti ve MAXALW kontrolü
        # Genişletilmiş aday listesini hazırla (çakışma filtresi sonrası kalan tüm hisseler)
        extended_candidates = filtered_stocks
        
        cross_step_valid = self.filter_candidates_by_cross_step_rules(
            filtered_stocks[:10],  # İlk 10'u kontrol et 
            step_number=3,
            order_side='SELL',
            target_count=5,  # 5 hisse hedefle
            extended_candidates=extended_candidates  # Elenen hisselerin yerine diğer adayları geçir
        )
        
        # SMI kontrolü + Pozisyon güvenliği ile hisse filtrele
        valid_tickers = []
        
        for ticker, score in cross_step_valid[:5]:  # İlk 5'i al
            # ✅ HALF SIZED kontrolü - dinamik lot sistemi (PSFAlgo2 ile uyumlu)
            if ticker in self.half_sized_list:
                # Varsayılan lot boyutu (şu anda 200, gelecekte değişebilir)
                intended_lot_size = getattr(self, 'default_lot_size', 200)
                half_sized_lot = intended_lot_size // 2
                minimum_lot_threshold = 200  # Minimum kabul edilebilir lot
                
                if intended_lot_size < 400:  # 400'ün altındaysa yarısı 200'den az olacak
                    print(f"[PSF CHAIN 3] ⏭️ {ticker} half-sized listesinde ({intended_lot_size} → {half_sized_lot} lot < {minimum_lot_threshold} minimum), atlanıyor")
                    continue
                else:
                    print(f"[PSF CHAIN 3] ✅ {ticker} half-sized listesinde kabul edildi ({intended_lot_size} → {half_sized_lot} lot ≥ {minimum_lot_threshold})")
            
            # SMI kontrolü (short arttırma için)
            current_position = self.get_position_size(ticker)
            
            if current_position <= 0:  # Short arttırma durumu
                smi_rate = self.get_smi_rate(ticker)
                if smi_rate > 0.28:
                    print(f"[PSF CHAIN 3] ❌ {ticker} (AS:{score:.2f}) - SMI {smi_rate:.4f} > 0.28")
                    continue
                    
            # Pozisyon güvenli lot hesapla
            safe_lot = self.get_position_safe_lot_size(ticker, 'SELL', 200)
            
            if safe_lot > 0:
                valid_tickers.append(ticker)
                print(f"[PSF CHAIN 3] ✅ {ticker} (AS:{score:.2f}) - Güvenli lot: {safe_lot}")
            else:
                print(f"[PSF CHAIN 3] ❌ {ticker} (AS:{score:.2f}) - Pozisyon güvenliği: {safe_lot}")
        
        # ✅ Eğer yeterli hisse kalmadıysa, genişletilmiş aday listesinden devam et
        if len(valid_tickers) < 5 and len(cross_step_valid) < len(extended_candidates):
            print(f"[PSF CHAIN 3] ⚠️ Pozisyon güvenliği sonrası {len(valid_tickers)} hisse kaldı, genişletilmiş adaylardan devam ediliyor...")
            
            # Zaten kontrol edilen hisseleri takip et
            checked_tickers = set([c[0] if isinstance(c, (list, tuple)) else c for c in cross_step_valid])
            
            # Genişletilmiş aday listesinden devam et
            for candidate in extended_candidates:
                ticker = candidate[0] if isinstance(candidate, (list, tuple)) else candidate
                score = candidate[1] if isinstance(candidate, (list, tuple)) and len(candidate) > 1 else 0
                
                # Zaten kontrol edilmiş hisseleri atla
                if ticker in checked_tickers:
                    continue
                
                # Hedef sayıya ulaştık mı?
                if len(valid_tickers) >= 5:
                    break
                
                # ✅ HALF SIZED kontrolü
                if ticker in self.half_sized_list:
                    intended_lot_size = getattr(self, 'default_lot_size', 200)
                    half_sized_lot = intended_lot_size // 2
                    minimum_lot_threshold = 200
                    
                    if intended_lot_size < 400:
                        print(f"[PSF CHAIN 3] ⏭️ {ticker} half-sized listesinde (genişletilmiş aday), atlanıyor")
                        continue
                
                # SMI kontrolü (short arttırma için)
                current_position = self.get_position_size(ticker)
                
                if current_position <= 0:  # Short arttırma durumu
                    smi_rate = self.get_smi_rate(ticker)
                    if smi_rate > 0.28:
                        print(f"[PSF CHAIN 3] ❌ {ticker} (AS:{score:.2f}) - SMI {smi_rate:.4f} > 0.28 (genişletilmiş aday)")
                        continue
                        
                # Pozisyon güvenli lot hesapla
                safe_lot = self.get_position_safe_lot_size(ticker, 'SELL', 200)
                
                if safe_lot > 0:
                    valid_tickers.append(ticker)
                    print(f"[PSF CHAIN 3] ✅ {ticker} (AS:{score:.2f}) - Genişletilmiş adaydan eklendi, güvenli lot: {safe_lot}")
                else:
                    print(f"[PSF CHAIN 3] ❌ {ticker} (AS:{score:.2f}) - Pozisyon güvenliği: {safe_lot} (genişletilmiş aday)")
        
        if not valid_tickers:
            print("[PSF CHAIN 3] ❌ Hiçbir hisse tüm güvenlik kontrollerini sağlamıyor")
            self.advance_chain()
            return
        
        # GUI'ye hisseleri aktar ve Ask Sell emri gönder
        self.current_window.selected_tickers = set(valid_tickers[:5])
        
        print(f"[PSF CHAIN 3] 📋 {len(valid_tickers[:5])} hisse seçildi: {list(valid_tickers[:5])}")
        print(f"[PSF CHAIN 3] 🔍 Çakışma kontrolü: Mevcut SELL emirlerle ±0.08 cent toleransında çakışma kontrolü yapıldı")
        
        # ✅ Onay bekleme durumunu aktif et
        self.waiting_for_approval = True
        
        # Ask Sell butonunu tetikle
        self.current_window.send_ask_sell_orders()
        print("[PSF CHAIN 3] Ask Sell emirleri gönderildi, kullanıcı onayı bekleniyor...")
        print("[PSF CHAIN 3] ⏸️ Onay bekleme modu aktif - advance_chain bloke edildi")
    
    def run_new_long_tp_as_data_ready(self):
        """
        5. ADIM DATA READY: Long Take Profit penceresinde FINAL AS en düşük 5 hisse seç → Ask Sell
        """
        print("[PSF NEW CHAIN 5/14] 📊 Long TP FINAL AS → Ask Sell (data ready)")
        
        if not self.is_active or not self.current_window:
            print("[PSF CHAIN 5] ❌ Pencere bulunamadı veya PSFAlgo pasif")
            self.advance_chain()
            return
        
        # FINAL AS en düşük 5 hisse seç (sadece long pozisyonlar)
        selected_stocks = self.get_top_stocks_by_score(
            self.current_window, 
            'Final AS skor', 
            count=15,  # Daha fazla seç ki çakışma filtresi sonrası 5 tane kalabilsin
            ascending=True,   # En düşük
            score_range=(0, 1500)
        )
        
        if not selected_stocks:
            print("[PSF CHAIN 5] ❌ FINAL AS kriterleri sağlayan hisse bulunamadı")
            self.advance_chain()
            return
        
        # ✅ ÇAKİŞMA FİLTRESİ - Mevcut SELL emirlerini kontrol et
        filtered_stocks = self.filter_stocks_by_existing_orders(
            selected_stocks, 
            'SELL', 
            self.current_window
        )
        
        if len(filtered_stocks) < 5:
            print(f"[PSF CHAIN 5] ⚠️ Çakışma filtresi sonrası sadece {len(filtered_stocks)} hisse kaldı, genişletiliyor...")
            
            # Genişletilmiş seçim yap
            extended_stocks = self.get_extended_stock_selection(
                self.current_window,
                'Final AS skor',
                original_count=15,
                needed_count=5 - len(filtered_stocks),
                ascending=True,
                score_range=(0, 1500),
                order_side='SELL'
            )
            
            filtered_stocks = extended_stocks
        
        # ✅ Cross-step validation - şirket limiti ve MAXALW kontrolü
        # Genişletilmiş aday listesini hazırla (çakışma filtresi sonrası kalan tüm hisseler)
        extended_candidates = filtered_stocks
        
        cross_step_valid = self.filter_candidates_by_cross_step_rules(
            filtered_stocks[:10],  # İlk 10'u kontrol et 
            step_number=5,
            order_side='SELL',
            target_count=5,  # 5 hisse hedefle
            extended_candidates=extended_candidates  # Elenen hisselerin yerine diğer adayları geçir
        )
        
        # Long pozisyon kontrolü + Pozisyon güvenliği ile hisse filtrele
        valid_tickers = []
        
        for ticker, score in cross_step_valid[:5]:  # İlk 5'i al
            # ✅ HALF SIZED kontrolü - dinamik lot sistemi (PSFAlgo2 ile uyumlu)
            if ticker in self.half_sized_list:
                # Varsayılan lot boyutu (şu anda 200, gelecekte değişebilir)
                intended_lot_size = getattr(self, 'default_lot_size', 200)
                half_sized_lot = intended_lot_size // 2
                minimum_lot_threshold = 200  # Minimum kabul edilebilir lot
                
                if intended_lot_size < 400:  # 400'ün altındaysa yarısı 200'den az olacak
                    print(f"[PSF CHAIN 5] ⏭️ {ticker} half-sized listesinde ({intended_lot_size} → {half_sized_lot} lot < {minimum_lot_threshold} minimum), atlanıyor")
                    continue
                else:
                    print(f"[PSF CHAIN 5] ✅ {ticker} half-sized listesinde kabul edildi ({intended_lot_size} → {half_sized_lot} lot ≥ {minimum_lot_threshold})")
            
            # Long pozisyon kontrolü
            current_position = self.get_position_size(ticker)
            if current_position <= 0:
                print(f"[PSF CHAIN 5] ❌ {ticker} (AS:{score:.2f}) - Long pozisyon yok ({current_position})")
                continue
                
            # Pozisyon güvenli lot hesapla
            safe_lot = self.get_position_safe_lot_size(ticker, 'SELL', 200)
            
            if safe_lot > 0:
                valid_tickers.append(ticker)
                print(f"[PSF CHAIN 5] ✅ {ticker} (AS:{score:.2f}) - Güvenli lot: {safe_lot}")
            else:
                print(f"[PSF CHAIN 5] ❌ {ticker} (AS:{score:.2f}) - Pozisyon güvenliği: {safe_lot}")
        
        # ✅ Eğer yeterli hisse kalmadıysa, genişletilmiş aday listesinden devam et
        if len(valid_tickers) < 5 and len(cross_step_valid) < len(extended_candidates):
            print(f"[PSF CHAIN 5] ⚠️ Pozisyon güvenliği sonrası {len(valid_tickers)} hisse kaldı, genişletilmiş adaylardan devam ediliyor...")
            
            # Zaten kontrol edilen hisseleri takip et
            checked_tickers = set([c[0] if isinstance(c, (list, tuple)) else c for c in cross_step_valid])
            
            # Genişletilmiş aday listesinden devam et
            for candidate in extended_candidates:
                ticker = candidate[0] if isinstance(candidate, (list, tuple)) else candidate
                score = candidate[1] if isinstance(candidate, (list, tuple)) and len(candidate) > 1 else 0
                
                # Zaten kontrol edilmiş hisseleri atla
                if ticker in checked_tickers:
                    continue
                
                # Hedef sayıya ulaştık mı?
                if len(valid_tickers) >= 5:
                    break
                
                # ✅ HALF SIZED kontrolü
                if ticker in self.half_sized_list:
                    intended_lot_size = getattr(self, 'default_lot_size', 200)
                    half_sized_lot = intended_lot_size // 2
                    minimum_lot_threshold = 200
                    
                    if intended_lot_size < 400:
                        print(f"[PSF CHAIN 5] ⏭️ {ticker} half-sized listesinde (genişletilmiş aday), atlanıyor")
                        continue
                
                # Long pozisyon kontrolü
                current_position = self.get_position_size(ticker)
                if current_position <= 0:
                    print(f"[PSF CHAIN 5] ❌ {ticker} (AS:{score:.2f}) - Long pozisyon yok ({current_position}) (genişletilmiş aday)")
                    continue
                    
                # Pozisyon güvenli lot hesapla
                safe_lot = self.get_position_safe_lot_size(ticker, 'SELL', 200)
                
                if safe_lot > 0:
                    valid_tickers.append(ticker)
                    print(f"[PSF CHAIN 5] ✅ {ticker} (AS:{score:.2f}) - Genişletilmiş adaydan eklendi, güvenli lot: {safe_lot}")
                else:
                    print(f"[PSF CHAIN 5] ❌ {ticker} (AS:{score:.2f}) - Pozisyon güvenliği: {safe_lot} (genişletilmiş aday)")
        
        if not valid_tickers:
            print("[PSF CHAIN 5] ❌ Hiçbir hisse koşulları sağlamıyor")
            self.advance_chain()
            return
        
        # GUI'ye hisseleri aktar ve Ask Sell emri gönder
        self.current_window.selected_tickers = set(valid_tickers[:5])
        
        print(f"[PSF CHAIN 5] 📋 {len(valid_tickers[:5])} hisse seçildi: {list(valid_tickers[:5])}")
        
        # ✅ Onay bekleme durumunu aktif et
        self.waiting_for_approval = True
        
        # Ask Sell butonunu tetikle
        print("[DEBUG] send_ask_sell_orders çağrılıyor...")
        self.current_window.send_ask_sell_orders()
        print("[PSF CHAIN 5] Ask Sell emirleri gönderildi, kullanıcı onayı bekleniyor...")
        print("[PSF CHAIN 5] ⏸️ Onay bekleme modu aktif - advance_chain bloke edildi")
    
    def run_new_short_tp_bb_data_ready(self):
        """
        7. ADIM DATA READY: Short Take Profit penceresinde FINAL BB en yüksek 5 hisse seç → Bid Buy
        """
        print("[PSF NEW CHAIN 7/14] 📊 Short TP FINAL BB → Bid Buy (data ready)")
        
        if not self.is_active or not self.current_window:
            print("[PSF CHAIN 7] ❌ Pencere bulunamadı veya PSFAlgo pasif")
            self.advance_chain()
            return
        
        # FINAL BB en yüksek 5 hisse seç (sadece short pozisyonlar)
        selected_stocks = self.get_top_stocks_by_score(
            self.current_window, 
            'Final BB skor', 
            count=15,  # Daha fazla seç ki çakışma filtresi sonrası 5 tane kalabilsin
            ascending=False,  # En yüksek
            score_range=(0, 1500)
        )
        
        if not selected_stocks:
            print("[PSF CHAIN 7] ❌ FINAL BB kriterleri sağlayan hisse bulunamadı")
            self.advance_chain()
            return
        
        # ✅ ÇAKİŞMA FİLTRESİ - Mevcut BUY emirlerini kontrol et
        filtered_stocks = self.filter_stocks_by_existing_orders(
            selected_stocks, 
            'BUY', 
            self.current_window
        )
        
        if len(filtered_stocks) < 5:
            print(f"[PSF CHAIN 7] ⚠️ Çakışma filtresi sonrası sadece {len(filtered_stocks)} hisse kaldı, genişletiliyor...")
            
            # Genişletilmiş seçim yap
            extended_stocks = self.get_extended_stock_selection(
                self.current_window,
                'Final BB skor',
                original_count=15,
                needed_count=5 - len(filtered_stocks),
                ascending=False,
                score_range=(0, 1500),
                order_side='BUY'
            )
            
            filtered_stocks = extended_stocks
        
        # ✅ Cross-step validation - şirket limiti ve MAXALW kontrolü
        # Genişletilmiş aday listesini hazırla (çakışma filtresi sonrası kalan tüm hisseler)
        extended_candidates = filtered_stocks
        
        cross_step_valid = self.filter_candidates_by_cross_step_rules(
            filtered_stocks[:10],  # İlk 10'u kontrol et 
            step_number=7,
            order_side='BUY',
            target_count=5,  # 5 hisse hedefle
            extended_candidates=extended_candidates  # Elenen hisselerin yerine diğer adayları geçir
        )
        
        # Short pozisyon kontrolü + Pozisyon güvenliği ile hisse filtrele
        valid_tickers = []
        
        for ticker, score in cross_step_valid[:5]:  # İlk 5'i al
            # ✅ HALF SIZED kontrolü - dinamik lot sistemi (PSFAlgo2 ile uyumlu)
            if ticker in self.half_sized_list:
                # Varsayılan lot boyutu (şu anda 200, gelecekte değişebilir)
                intended_lot_size = getattr(self, 'default_lot_size', 200)
                half_sized_lot = intended_lot_size // 2
                minimum_lot_threshold = 200  # Minimum kabul edilebilir lot
                
                if intended_lot_size < 400:  # 400'ün altındaysa yarısı 200'den az olacak
                    print(f"[PSF CHAIN 7] ⏭️ {ticker} half-sized listesinde ({intended_lot_size} → {half_sized_lot} lot < {minimum_lot_threshold} minimum), atlanıyor")
                    continue
                else:
                    print(f"[PSF CHAIN 7] ✅ {ticker} half-sized listesinde kabul edildi ({intended_lot_size} → {half_sized_lot} lot ≥ {minimum_lot_threshold})")
            
            # Short pozisyon kontrolü
            current_position = self.get_position_size(ticker)
            if current_position >= 0:
                print(f"[PSF CHAIN 7] ❌ {ticker} (BB:{score:.2f}) - Short pozisyon yok ({current_position})")
                continue
                
            # Pozisyon güvenli lot hesapla
            safe_lot = self.get_position_safe_lot_size(ticker, 'BUY', 200)
            
            if safe_lot > 0:
                valid_tickers.append(ticker)
                print(f"[PSF CHAIN 7] ✅ {ticker} (BB:{score:.2f}) - Güvenli lot: {safe_lot}")
            else:
                print(f"[PSF CHAIN 7] ❌ {ticker} (BB:{score:.2f}) - Pozisyon güvenliği: {safe_lot}")
        
        # ✅ Eğer yeterli hisse kalmadıysa, genişletilmiş aday listesinden devam et
        if len(valid_tickers) < 5 and len(cross_step_valid) < len(extended_candidates):
            print(f"[PSF CHAIN 7] ⚠️ Pozisyon güvenliği sonrası {len(valid_tickers)} hisse kaldı, genişletilmiş adaylardan devam ediliyor...")
            
            # Zaten kontrol edilen hisseleri takip et
            checked_tickers = set([c[0] if isinstance(c, (list, tuple)) else c for c in cross_step_valid])
            
            # Genişletilmiş aday listesinden devam et
            for candidate in extended_candidates:
                ticker = candidate[0] if isinstance(candidate, (list, tuple)) else candidate
                score = candidate[1] if isinstance(candidate, (list, tuple)) and len(candidate) > 1 else 0
                
                # Zaten kontrol edilmiş hisseleri atla
                if ticker in checked_tickers:
                    continue
                
                # Hedef sayıya ulaştık mı?
                if len(valid_tickers) >= 5:
                    break
                
                # ✅ HALF SIZED kontrolü
                if ticker in self.half_sized_list:
                    intended_lot_size = getattr(self, 'default_lot_size', 200)
                    half_sized_lot = intended_lot_size // 2
                    minimum_lot_threshold = 200
                    
                    if intended_lot_size < 400:
                        print(f"[PSF CHAIN 7] ⏭️ {ticker} half-sized listesinde (genişletilmiş aday), atlanıyor")
                        continue
                
                # Short pozisyon kontrolü
                current_position = self.get_position_size(ticker)
                if current_position >= 0:
                    print(f"[PSF CHAIN 7] ❌ {ticker} (BB:{score:.2f}) - Short pozisyon yok ({current_position}) (genişletilmiş aday)")
                    continue
                    
                # Pozisyon güvenli lot hesapla
                safe_lot = self.get_position_safe_lot_size(ticker, 'BUY', 200)
                
                if safe_lot > 0:
                    valid_tickers.append(ticker)
                    print(f"[PSF CHAIN 7] ✅ {ticker} (BB:{score:.2f}) - Genişletilmiş adaydan eklendi, güvenli lot: {safe_lot}")
                else:
                    print(f"[PSF CHAIN 7] ❌ {ticker} (BB:{score:.2f}) - Pozisyon güvenliği: {safe_lot} (genişletilmiş aday)")
        
        if not valid_tickers:
            print("[PSF CHAIN 7] ❌ Hiçbir hisse koşulları sağlamıyor")
            self.advance_chain()
            return
        
        # GUI'ye hisseleri aktar ve Bid Buy emri gönder
        self.current_window.selected_tickers = set(valid_tickers[:5])
        
        print(f"[PSF CHAIN 7] 📋 {len(valid_tickers[:5])} hisse seçildi: {list(valid_tickers[:5])}")
        print(f"[PSF CHAIN 7] 🔍 Çakışma kontrolü: Mevcut BUY emirlerle ±0.08 cent toleransında çakışma kontrolü yapıldı")
        
        # ✅ Onay bekleme durumunu aktif et
        self.waiting_for_approval = True
        
        # Bid Buy butonunu tetikle
        self.current_window.send_bid_buy_orders()
        print("[PSF CHAIN 7] Bid Buy emirleri gönderildi, kullanıcı onayı bekleniyor...")
        print("[PSF CHAIN 7] ⏸️ Onay bekleme modu aktif - advance_chain bloke edildi")

    def test_new_14_step_system(self):
        """Yeni 14 adımlı PISDoNGU sistemini test et"""
        print(f"\n[NEW 14-STEP TEST] 🚀 Yeni 14 Adımlı PISDoNGU Sistemi Testi")
        print(f"[NEW 14-STEP TEST] ================================================")
        
        # Sistem özeti
        print(f"\n[NEW 14-STEP TEST] 📋 SİSTEM ÖZETİ:")
        print(f"[NEW 14-STEP TEST] YENİ 8 ADIMLI SİSTEM (Skor Bazlı):")
        print(f"[NEW 14-STEP TEST]   1. T-Losers: FINAL BB en yüksek 5 → Hidden Bid Buy")
        print(f"[NEW 14-STEP TEST]   2. T-Losers: FINAL FB en yüksek 5 → Hidden Front Buy (spread koşulu)")
        print(f"[NEW 14-STEP TEST]   3. T-Gainers: FINAL AS en düşük 5 → Hidden Ask Sell")
        print(f"[NEW 14-STEP TEST]   4. T-Gainers: FINAL FS en düşük 5 → Hidden Front Sell (spread + SMI)")
        print(f"[NEW 14-STEP TEST]   5. Long TP: FINAL AS en düşük 5 → Hidden Ask Sell")
        print(f"[NEW 14-STEP TEST]   6. Long TP: FINAL FS en düşük 5 → Hidden Front Sell (spread + SMI)")
        print(f"[NEW 14-STEP TEST]   7. Short TP: FINAL BB en yüksek 5 → Hidden Bid Buy")
        print(f"[NEW 14-STEP TEST]   8. Short TP: FINAL FB en yüksek 5 → Hidden Front Buy (spread)")
        print(f"")
        print(f"[NEW 14-STEP TEST] ESKİ 6 ADIMLI SİSTEM (Mevcut Mantık):")
        print(f"[NEW 14-STEP TEST]   9. T-Losers: Bid buy ucuzluk ≤ -0.25")
        print(f"[NEW 14-STEP TEST]   10. T-Gainers: Ask sell pahalilik ≥ 0.25 (top 30)")
        print(f"[NEW 14-STEP TEST]   11. Long TP Ask: Ask sell pahalilik > 0.20")
        print(f"[NEW 14-STEP TEST]   12. Long TP Front: Front sell pahalilik > 0.30")
        print(f"[NEW 14-STEP TEST]   13. Short TP Bid: Bid buy ucuzluk < -0.30")
        print(f"[NEW 14-STEP TEST]   14. Short TP Front: Front buy ucuzluk < -0.20")
        
        # Chain state sırası test
        print(f"\n[NEW 14-STEP TEST] 🔄 CHAIN STATE SIRALAMA TESTİ:")
        
        chain_order = [
            'T_LOSERS',          # 1
            'T_LOSERS_FB',       # 2
            'T_GAINERS',         # 3
            'T_GAINERS_FS',      # 4
            'LONG_TP_AS',        # 5
            'LONG_TP_FS',        # 6
            'SHORT_TP_BB',       # 7
            'SHORT_TP_FB',       # 8
            'T_LOSERS_OLD',      # 9
            'T_GAINERS_OLD',     # 10
            'LONG_TP_ASK',       # 11
            'LONG_TP_FRONT',     # 12
            'SHORT_TP_BID',      # 13
            'SHORT_TP_FRONT',    # 14
            'FINISHED'           # Bitiş
        ]
        
        # Her adımın başlığını göster
        for i, state in enumerate(chain_order, 1):
            original_state = self.chain_state
            self.chain_state = state
            title = self.get_chain_state_title()
            self.chain_state = original_state
            
            if state == 'FINISHED':
                print(f"[NEW 14-STEP TEST]   Bitiş: {title}")
            else:
                print(f"[NEW 14-STEP TEST]   Adım {i:2d}: {title}")
        
        # Advance chain test
        print(f"\n[NEW 14-STEP TEST] ⚡ ADVANCE CHAIN TESTİ:")
        print(f"[NEW 14-STEP TEST] Chain state geçişlerini test ediyorum...")
        
        original_state = self.chain_state
        test_transitions = [
            ('T_LOSERS', 'T_LOSERS_FB'),
            ('T_LOSERS_FB', 'T_GAINERS'),
            ('T_GAINERS', 'T_GAINERS_FS'),
            ('T_GAINERS_FS', 'LONG_TP_AS'),
            ('LONG_TP_AS', 'LONG_TP_FS'),
            ('LONG_TP_FS', 'SHORT_TP_BB'),
            ('SHORT_TP_BB', 'SHORT_TP_FB'),
            ('SHORT_TP_FB', 'T_LOSERS_OLD'),
            ('T_LOSERS_OLD', 'T_GAINERS_OLD'),
            ('T_GAINERS_OLD', 'LONG_TP_ASK'),
            ('LONG_TP_ASK', 'LONG_TP_FRONT'),
            ('LONG_TP_FRONT', 'SHORT_TP_BID'),
            ('SHORT_TP_BID', 'SHORT_TP_FRONT'),
            ('SHORT_TP_FRONT', 'FINISHED')
        ]
        
        for current, expected_next in test_transitions:
            self.chain_state = current
            
            # advance_chain'i test et (ama window açmasın)
            if current == 'T_LOSERS':
                next_state = 'T_LOSERS_FB'
            elif current == 'T_LOSERS_FB':
                next_state = 'T_GAINERS'
            elif current == 'T_GAINERS':
                next_state = 'T_GAINERS_FS'
            elif current == 'T_GAINERS_FS':
                next_state = 'LONG_TP_AS'
            elif current == 'LONG_TP_AS':
                next_state = 'LONG_TP_FS'
            elif current == 'LONG_TP_FS':
                next_state = 'SHORT_TP_BB'
            elif current == 'SHORT_TP_BB':
                next_state = 'SHORT_TP_FB'
            elif current == 'SHORT_TP_FB':
                next_state = 'T_LOSERS_OLD'
            elif current == 'T_LOSERS_OLD':
                next_state = 'T_GAINERS_OLD'
            elif current == 'T_GAINERS_OLD':
                next_state = 'LONG_TP_ASK'
            elif current == 'LONG_TP_ASK':
                next_state = 'LONG_TP_FRONT'
            elif current == 'LONG_TP_FRONT':
                next_state = 'SHORT_TP_BID'
            elif current == 'SHORT_TP_BID':
                next_state = 'SHORT_TP_FRONT'
            elif current == 'SHORT_TP_FRONT':
                next_state = 'FINISHED'
            else:
                next_state = 'UNKNOWN'
            
            if next_state == expected_next:
                print(f"[NEW 14-STEP TEST]   ✅ {current} → {next_state}")
            else:
                print(f"[NEW 14-STEP TEST]   ❌ {current} → {next_state} (beklenen: {expected_next})")
        
        # Orijinal state'i geri yükle
        self.chain_state = original_state
        
        # Yeni özellikler testi
        print(f"\n[NEW 14-STEP TEST] 🎯 YENİ ÖZELLİKLER TESTİ:")
        print(f"[NEW 14-STEP TEST] ✅ Spread koşulu kontrolü: check_front_spread_condition()")
        print(f"[NEW 14-STEP TEST] ✅ Skor bazlı hisse seçimi: get_top_stocks_by_score()")
        print(f"[NEW 14-STEP TEST] ✅ Pozisyon güvenli lot hesaplama: get_position_safe_lot_size()")
        print(f"[NEW 14-STEP TEST] ✅ Polygon ticker dönüştürme: polygonize_ticker()")
        print(f"[NEW 14-STEP TEST] ✅ 14 adımlı chain state sistemi")
        print(f"[NEW 14-STEP TEST] ✅ Hibrit sistem: Yeni 8 + Eski 6 adım")
        
        # Avantajlar
        print(f"\n[NEW 14-STEP TEST] 🚀 SİSTEM AVANTAJLARI:")
        print(f"[NEW 14-STEP TEST] 🔹 Çift katman strateji: Hem skor bazlı hem mevcut mantık")
        print(f"[NEW 14-STEP TEST] 🔹 Gelişmiş spread analizi: Front emirler için akıllı koşullar")
        print(f"[NEW 14-STEP TEST] 🔹 Pozisyon güvenliği: Ters pozisyona geçme önleme")
        print(f"[NEW 14-STEP TEST] 🔹 SMI entegrasyonu: Short arttırma için otomatik kontrol")
        print(f"[NEW 14-STEP TEST] 🔹 Skor aralığı filtresi: 0-1500 geçerli skorlar")
        print(f"[NEW 14-STEP TEST] 🔹 Otomatik lot ayarlama: Güvenli pozisyon yönetimi")
        print(f"[NEW 14-STEP TEST] 🔹 14 adımlı kapsamlı işlem zinciri")
        
        print(f"\n[NEW 14-STEP TEST] ✅ Yeni 14 adımlı sistem testi tamamlandı!")
        print(f"[NEW 14-STEP TEST] 🎯 Sistem aktifleştirme için PSFAlgo ON yapın")
        
        return True

    # ================== YENİ 14 ADIMLI SİSTEM FONKSİYONLARI ==================

    def run_new_t_losers_bb(self):
        """
        1. ADIM: T-Top Losers penceresinde FINAL BB en yüksek 5 hisse → Hidden Bid Buy
        """
        print("[PSF NEW CHAIN 1/14] 📊 T-Losers FINAL BB → Bid Buy")
        
        if not self.is_active:
            print("[PSFAlgo] ⏸️ PSFAlgo pasif - T-Losers BB işlenmedi")
            return
            
        # T-Top Losers penceresini aç
        if self.main_window and hasattr(self.main_window, 'open_t_top_losers_maltopla'):
            self.main_window.open_t_top_losers_maltopla()
            print("[PSF CHAIN 1] T-Top Losers penceresi açılıyor...")
        else:
            print("[PSF CHAIN 1] ❌ T-Top Losers penceresi açılamadı")
            self.advance_chain()

    def run_new_t_losers_fb(self):
        """
        2. ADIM: T-Top Losers penceresinde FINAL FB en yüksek 5 hisse → Hidden Front Buy (spread koşulu)
        """
        print("[PSF NEW CHAIN 2/14] 📊 T-Losers FINAL FB → Front Buy (spread koşulu)")
        
        if not self.is_active or not self.current_window:
            print("[PSF CHAIN 2] ❌ Pencere bulunamadı veya PSFAlgo pasif")
            self.advance_chain()
            return
        
        # FINAL FB en yüksek 15 hisse seç (daha fazla seç ki cross-step validation sonrası 5 tane kalabilsin)
        selected_stocks = self.get_top_stocks_by_score(
            self.current_window, 
            'Final FB skor', 
            count=15, 
            ascending=False,  # En yüksek
            score_range=(0, 1500)
        )
        
        if not selected_stocks:
            print("[PSF CHAIN 2] ❌ FINAL FB kriterleri sağlayan hisse bulunamadı")
            self.advance_chain()
            return
        
        # ✅ Cross-step validation - şirket limiti ve MAXALW kontrolü
        cross_step_valid = self.filter_candidates_by_cross_step_rules(
            selected_stocks[:10],  # İlk 10'u kontrol et 
            step_number=2,
            order_side='BUY',
            target_count=5,  # 5 hisse hedefle
            extended_candidates=selected_stocks  # Elenen hisselerin yerine diğer adayları geçir
        )
        
        # Spread koşulu ile hisse filtrele
        valid_tickers = []
        
        for ticker, score in cross_step_valid[:5]:  # İlk 5'i al
            # Spread koşulu kontrolü
            target_price = self.get_price_from_window(self.current_window, ticker, 'Last price')
            spread_ok, spread_msg = self.check_front_spread_condition(ticker, 'FRONT_BUY', target_price)
            
            if spread_ok:
                valid_tickers.append(ticker)
                print(f"[PSF CHAIN 2] ✅ {ticker} (FB:{score:.2f}) - {spread_msg}")
            else:
                print(f"[PSF CHAIN 2] ❌ {ticker} (FB:{score:.2f}) - {spread_msg}")
        
        # ✅ Eğer yeterli hisse kalmadıysa, genişletilmiş aday listesinden devam et
        if len(valid_tickers) < 5 and len(cross_step_valid) < len(selected_stocks):
            print(f"[PSF CHAIN 2] ⚠️ Spread koşulu sonrası {len(valid_tickers)} hisse kaldı, genişletilmiş adaylardan devam ediliyor...")
            
            # Zaten kontrol edilen hisseleri takip et
            checked_tickers = set([c[0] if isinstance(c, (list, tuple)) else c for c in cross_step_valid])
            
            # Genişletilmiş aday listesinden devam et
            for candidate in selected_stocks:
                ticker = candidate[0] if isinstance(candidate, (list, tuple)) else candidate
                score = candidate[1] if isinstance(candidate, (list, tuple)) and len(candidate) > 1 else 0
                
                # Zaten kontrol edilmiş hisseleri atla
                if ticker in checked_tickers:
                    continue
                
                # Hedef sayıya ulaştık mı?
                if len(valid_tickers) >= 5:
                    break
                
                # Spread koşulu kontrolü
                target_price = self.get_price_from_window(self.current_window, ticker, 'Last price')
                spread_ok, spread_msg = self.check_front_spread_condition(ticker, 'FRONT_BUY', target_price)
                
                if spread_ok:
                    valid_tickers.append(ticker)
                    print(f"[PSF CHAIN 2] ✅ {ticker} (FB:{score:.2f}) - Genişletilmiş adaydan eklendi - {spread_msg}")
                else:
                    print(f"[PSF CHAIN 2] ❌ {ticker} (FB:{score:.2f}) - {spread_msg} (genişletilmiş aday)")
        
        if not valid_tickers:
            print("[PSF CHAIN 2] ❌ Hiçbir hisse spread koşulunu sağlamıyor")
            self.advance_chain()
            return
        
        # GUI'ye hisseleri aktar ve Front Buy emri gönder
        self.current_window.selected_tickers = set(valid_tickers[:5])
        
        print(f"[PSF CHAIN 2] 📋 {len(valid_tickers[:5])} hisse seçildi: {list(valid_tickers[:5])}")
        print(f"[DEBUG] selected_tickers set edildi: {self.current_window.selected_tickers}")
        
        # ✅ Onay bekleme durumunu aktif et
        self.waiting_for_approval = True
        print(f"[DEBUG] waiting_for_approval = {self.waiting_for_approval}")
        
        # Front Buy butonunu tetikle
        print("[DEBUG] send_front_buy_orders çağrılıyor...")
        try:
            self.current_window.send_front_buy_orders()
            print("[PSF CHAIN 2] Front Buy emirleri gönderildi, kullanıcı onayı bekleniyor...")
            print("[PSF CHAIN 2] ⏸️ Onay bekleme modu aktif - advance_chain bloke edildi")
        except Exception as e:
            print(f"[DEBUG] send_front_buy_orders hatası: {e}")
            import traceback
            traceback.print_exc()
            # Hata durumunda sonraki adıma geç
            self.waiting_for_approval = False
            self.advance_chain()

    def run_new_t_gainers_as(self):
        """
        3. ADIM: T-Top Gainers penceresinde FINAL AS en düşük 5 hisse → Hidden Ask Sell
        """
        print("[PSF NEW CHAIN 3/14] 📊 T-Gainers FINAL AS → Ask Sell")
        
        if not self.is_active:
            print("[PSFAlgo] ⏸️ PSFAlgo pasif - T-Gainers AS işlenmedi")
            return
            
        # T-Top Gainers penceresini aç
        if self.main_window and hasattr(self.main_window, 'open_t_top_gainers_maltopla'):
            self.main_window.open_t_top_gainers_maltopla()
            print("[PSF CHAIN 3] T-Top Gainers penceresi açılıyor...")
        else:
            print("[PSF CHAIN 3] ❌ T-Top Gainers penceresi açılamadı")
            self.advance_chain()

    def run_new_t_gainers_fs(self):
        """
        4. ADIM: T-Top Gainers penceresinde FINAL FS en düşük 5 hisse → Hidden Front Sell (spread koşulu + SMI kontrolü)
        """
        print("[PSF NEW CHAIN 4/14] 📊 T-Gainers FINAL FS → Front Sell (spread koşulu + SMI)")
        
        if not self.is_active or not self.current_window:
            print("[PSF CHAIN 4] ❌ Pencere bulunamadı veya PSFAlgo pasif")
            self.advance_chain()
            return
        
        # FINAL FS en düşük 15 hisse seç (daha fazla seç ki cross-step validation sonrası 5 tane kalabilsin)
        selected_stocks = self.get_top_stocks_by_score(
            self.current_window, 
            'Final FS skor', 
            count=15, 
            ascending=True,   # En düşük
            score_range=(0, 1500)
        )
        
        if not selected_stocks:
            print("[PSF CHAIN 4] ❌ FINAL FS kriterleri sağlayan hisse bulunamadı")
            self.advance_chain()
            return
        
        # ✅ Cross-step validation - şirket limiti ve MAXALW kontrolü
        cross_step_valid = self.filter_candidates_by_cross_step_rules(
            selected_stocks[:10],  # İlk 10'u kontrol et 
            step_number=4,
            order_side='SELL',
            target_count=5,  # 5 hisse hedefle
            extended_candidates=selected_stocks  # Elenen hisselerin yerine diğer adayları geçir
        )
        
        # Spread koşulu + SMI kontrolü ile hisse filtrele
        valid_tickers = []
        
        for ticker, score in cross_step_valid[:5]:  # İlk 5'i al
            # SMI kontrolü (short arttırma için)
            current_position = self.get_position_size(ticker)
            
            if current_position <= 0:  # Short arttırma durumu
                smi_rate = self.get_smi_rate(ticker)
                if smi_rate > 0.28:
                    print(f"[PSF CHAIN 4] ❌ {ticker} (FS:{score:.2f}) - SMI {smi_rate:.4f} > 0.28")
                    continue
                    
            # Spread koşulu kontrolü
            target_price = self.get_price_from_window(self.current_window, ticker, 'Last price')
            if not target_price:
                print(f"[PSF CHAIN 4] ❌ {ticker} (FS:{score:.2f}) - Last price alınamadı")
                continue
            spread_ok, spread_msg = self.check_front_spread_condition(ticker, 'FRONT_SELL', target_price)
            
            if spread_ok:
                valid_tickers.append(ticker)
                print(f"[PSF CHAIN 4] ✅ {ticker} (FS:{score:.2f}) - {spread_msg}")
            else:
                print(f"[PSF CHAIN 4] ❌ {ticker} (FS:{score:.2f}) - {spread_msg}")
        
        # ✅ Eğer yeterli hisse kalmadıysa, genişletilmiş aday listesinden devam et
        if len(valid_tickers) < 5 and len(cross_step_valid) < len(selected_stocks):
            print(f"[PSF CHAIN 4] ⚠️ Spread koşulu sonrası {len(valid_tickers)} hisse kaldı, genişletilmiş adaylardan devam ediliyor...")
            
            # Zaten kontrol edilen hisseleri takip et
            checked_tickers = set([c[0] if isinstance(c, (list, tuple)) else c for c in cross_step_valid])
            
            # Genişletilmiş aday listesinden devam et
            for candidate in selected_stocks:
                ticker = candidate[0] if isinstance(candidate, (list, tuple)) else candidate
                score = candidate[1] if isinstance(candidate, (list, tuple)) and len(candidate) > 1 else 0
                
                # Zaten kontrol edilmiş hisseleri atla
                if ticker in checked_tickers:
                    continue
                
                # Hedef sayıya ulaştık mı?
                if len(valid_tickers) >= 5:
                    break
                
                # SMI kontrolü
                current_position = self.get_position_size(ticker)
                if current_position <= 0:
                    smi_rate = self.get_smi_rate(ticker)
                    if smi_rate > 0.28:
                        print(f"[PSF CHAIN 4] ❌ {ticker} (FS:{score:.2f}) - SMI {smi_rate:.4f} > 0.28 (genişletilmiş aday)")
                        continue
                        
                # Spread kontrolü
                target_price = self.get_price_from_window(self.current_window, ticker, 'Last price')
                if not target_price:
                    print(f"[PSF CHAIN 4] ❌ {ticker} (FS:{score:.2f}) - Last price alınamadı (genişletilmiş aday)")
                    continue
                spread_ok, spread_msg = self.check_front_spread_condition(ticker, 'FRONT_SELL', target_price)
                
                if spread_ok:
                    valid_tickers.append(ticker)
                    print(f"[PSF CHAIN 4] ✅ {ticker} (FS:{score:.2f}) - Genişletilmiş adaydan eklendi - {spread_msg}")
                else:
                    print(f"[PSF CHAIN 4] ❌ {ticker} (FS:{score:.2f}) - {spread_msg} (genişletilmiş aday)")
        
        if not valid_tickers:
            print("[PSF CHAIN 4] ❌ Hiçbir hisse koşulları sağlamıyor")
            self.advance_chain()
            return
        
        # GUI'ye hisseleri aktar ve Front Sell emri gönder
        self.current_window.selected_tickers = set(valid_tickers[:5])
        
        print(f"[PSF CHAIN 4] 📋 {len(valid_tickers[:5])} hisse seçildi: {list(valid_tickers[:5])}")
        
        # ✅ Onay bekleme durumunu aktif et
        self.waiting_for_approval = True
        
        # Front Sell butonunu tetikle
        print("[DEBUG] send_front_sell_orders çağrılıyor...")
        self.current_window.send_front_sell_orders()
        print("[PSF CHAIN 4] Front Sell emirleri gönderildi, kullanıcı onayı bekleniyor...")
        print("[PSF CHAIN 4] ⏸️ Onay bekleme modu aktif - advance_chain bloke edildi")
    
    def manual_fill_check(self):
        """Manuel fill kontrolü - dakikada 1 kez IBKR'den fill'leri kontrol et"""
        try:
            print(f"[MANUAL FILL CHECK] 🔍 IBKR'den fill'ler kontrol ediliyor...")
            
            # IBKR'den son fill'leri al
            if hasattr(self.market_data, 'get_recent_fills'):
                recent_fills = self.market_data.get_recent_fills()
                
                for fill in recent_fills:
                    # Fill'i işle
                    self.on_fill(
                        ticker=fill.get('symbol', ''),
                        side=fill.get('side', ''),
                        price=fill.get('price', 0),
                        size=fill.get('quantity', 0)
                    )
                    
                print(f"[MANUAL FILL CHECK] ✅ {len(recent_fills)} fill işlendi")
            else:
                print(f"[MANUAL FILL CHECK] ⚠️ Market data'da get_recent_fills yok")
                
        except Exception as e:
            print(f"[MANUAL FILL CHECK] ❌ Fill kontrol hatası: {e}")

    def start_auto_fill_check(self):
        """Otomatik fill kontrolünü başlat - dakikada 1 kez"""
        import threading
        import time
        
        def auto_check():
            while self.is_active:
                try:
                    self.manual_fill_check()
                    time.sleep(60)  # 1 dakika bekle
                except Exception as e:
                    print(f"[AUTO FILL CHECK] ❌ Hata: {e}")
                    time.sleep(60)
        
        if self.is_active:
            threading.Thread(target=auto_check, daemon=True).start()
            print(f"[AUTO FILL CHECK] ✅ Otomatik fill kontrolü başlatıldı")

    # ================== YENİ 8 ADIMLI SİSTEM - ADIM 3 ==================

    def run_new_t_gainers_as(self):
        """
        3. ADIM: T-Top Gainers penceresinde FINAL AS en düşük 5 hisse → Hidden Ask Sell
        """
        print("[PSF NEW CHAIN 3/14] 📊 T-Gainers FINAL AS → Ask Sell")
        
        if not self.is_active:
            print("[PSFAlgo] ⏸️ PSFAlgo pasif - T-Gainers AS işlenmedi")
            return
            
        # T-Top Gainers penceresini aç
        if self.main_window and hasattr(self.main_window, 'open_t_top_gainers_maltopla'):
            self.main_window.open_t_top_gainers_maltopla()
            print("[PSF CHAIN 3] T-Top Gainers penceresi açılıyor...")
        else:
            print("[PSF CHAIN 3] ❌ T-Top Gainers penceresi açılamadı")
            self.advance_chain()

    # ================== HELPER FONKSİYONLAR ==================

    def get_top_stocks_by_score(self, window, score_column, count=5, ascending=True, score_range=(0, 1500)):
        """
        Penceredeki hisseleri belirtilen skor kolonuna göre sıralar ve en iyi 'count' tanesini döndürür
        
        Args:
            window: Pencere objesi (rows ve COLUMNS içermeli)
            score_column: Skor kolonu adı
            count: Seçilecek hisse sayısı
            ascending: True = en düşük skorlar (min), False = en yüksek skorlar (max)
            score_range: Geçerli skor aralığı (min, max)
        
        Returns:
            [(ticker, score), ...] listesi
        """
        if not window or not hasattr(window, 'rows') or not hasattr(window, 'COLUMNS'):
            print(f"[SCORE SELECTION] ❌ Geçersiz pencere")
            return []
        
        try:
            rows = window.rows
            columns = window.COLUMNS
            
            if score_column not in columns:
                print(f"[SCORE SELECTION] ❌ Skor kolonu bulunamadı: {score_column}")
                print(f"[SCORE SELECTION] Mevcut kolonlar: {columns}")
                return []
            
            score_index = columns.index(score_column)
            valid_stocks = []
            excluded_count = 0
            
            for row in rows:
                try:
                    if len(row) <= score_index or len(row) <= 1:
                        continue
                        
                    ticker = row[1]  # Symbol kolonu
                    score = float(row[score_index])
                    
                    # Skor aralığı kontrolü
                    if score_range[0] <= score <= score_range[1]:
                        valid_stocks.append((ticker, score))
                        
                except (ValueError, IndexError, TypeError):
                    continue
            
            if excluded_count > 0:
                print(f"[SCORE SELECTION] ⚠️ {excluded_count} hisse exclude listesinde atlandı")
            
            if not valid_stocks:
                print(f"[SCORE SELECTION] ❌ {score_column} için geçerli hisse bulunamadı (aralık: {score_range})")
                return []
            
            # Sırala
            valid_stocks.sort(key=lambda x: x[1], reverse=not ascending)
            
            # İlk 'count' tanesini al
            selected = valid_stocks[:count]
            
            direction = "en düşük" if ascending else "en yüksek"
            print(f"[SCORE SELECTION] ✅ {score_column} {direction} {len(selected)} hisse seçildi:")
            for ticker, score in selected:
                print(f"[SCORE SELECTION]   - {ticker}: {score:.2f}")
            
            return selected
            
        except Exception as e:
            print(f"[SCORE SELECTION] ❌ Hata: {e}")
            return []

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

    def get_position_safe_lot_size(self, ticker, action, requested_lot):
        """
        Pozisyon tersine geçmeyi önleyecek güvenli lot miktarını hesaplar
        
        Args:
            ticker: Hisse sembolü
            action: 'BUY' veya 'SELL'
            requested_lot: İstenilen lot miktarı
        
        Returns:
            int: Güvenli lot miktarı (0 = hiç emir göndermeme)
        """
        try:
            current_position = self.get_position_size(ticker)
            
            if action == 'BUY':
                # BUY emri: pozisyon arttırır
                # Short pozisyon varsa sadece o kadar kapatabilir
                if current_position < 0:
                    max_safe_lot = abs(current_position)
                    safe_lot = min(requested_lot, max_safe_lot)
                    print(f"[SAFE LOT] {ticker} BUY: Short {current_position} → max {max_safe_lot} → safe {safe_lot}")
                    return safe_lot
                else:
                    # Long/sıfır pozisyon: güvenli
                    print(f"[SAFE LOT] {ticker} BUY: Pozisyon {current_position} → güvenli {requested_lot}")
                    return requested_lot
                    
            elif action == 'SELL':
                # SELL emri: pozisyon azaltır
                # Long pozisyon varsa sadece o kadar kapatabilir
                if current_position > 0:
                    max_safe_lot = current_position
                    safe_lot = min(requested_lot, max_safe_lot)
                    print(f"[SAFE LOT] {ticker} SELL: Long {current_position} → max {max_safe_lot} → safe {safe_lot}")
                    return safe_lot
                else:
                    # Short/sıfır pozisyon: güvenli
                    print(f"[SAFE LOT] {ticker} SELL: Pozisyon {current_position} → güvenli {requested_lot}")
                    return requested_lot
            else:
                print(f"[SAFE LOT] ❌ {ticker} bilinmeyen action: {action}")
                return 0
                
        except Exception as e:
            print(f"[SAFE LOT] ❌ {ticker} güvenli lot hesaplama hatası: {e}")
            return 0

    def polygonize_ticker(self, ticker):
        """Polygon API için ticker'ı uygun formata çevirir (ör: 'INN PRE' → 'INN+PR+E')"""
        if not ticker:
            return ticker
        if ' ' in ticker:
            parts = ticker.split(' ')
            return parts[0] + '+' + '+'.join(list(parts[1]))
        return ticker

    def get_bid_ask_prices(self, ticker):
        """
        Ticker için bid/ask fiyatlarını al (Thread-safe, fallback'lı)
        Returns:
            (float, float): (bid_price, ask_price)
        """
        try:
            # 1. Önce pencere verisinden al
            if hasattr(self, 'current_window') and self.current_window:
                bid_price = self.get_price_from_window(self.current_window, ticker, 'Bid')
                ask_price = self.get_price_from_window(self.current_window, ticker, 'Ask')
                if bid_price and ask_price and bid_price > 0 and ask_price > 0:
                    print(f"[PSFAlgo1 BID/ASK] {ticker} pencere verisinden alındı: Bid={bid_price:.3f}, Ask={ask_price:.3f}")
                    return bid_price, ask_price
                else:
                    print(f"[PSFAlgo1 BID/ASK] {ticker} pencere verisi eksik: Bid={bid_price}, Ask={ask_price}")
            # 2. Market_data.last_data'dan al (Polygon verileri)
            if hasattr(self.market_data, 'last_data') and self.market_data.last_data:
                poly_ticker = self.polygonize_ticker(ticker)
                if poly_ticker in self.market_data.last_data:
                    data = self.market_data.last_data[poly_ticker]
                    bid = data.get('bid')
                    ask = data.get('ask')
                    if bid and ask and float(bid) > 0 and float(ask) > 0:
                        print(f"[PSFAlgo1 BID/ASK] {ticker} market_data'dan alındı: Bid={bid}, Ask={ask}")
                        return float(bid), float(ask)
                    else:
                        print(f"[PSFAlgo1 BID/ASK] {ticker} market_data bid/ask eksik: Bid={bid}, Ask={ask}")
            # 3. Ana pencere market_data_dict'ten al
            if hasattr(self, 'main_window') and self.main_window and hasattr(self.main_window, 'market_data_dict'):
                poly_ticker = self.polygonize_ticker(ticker)
                if poly_ticker in self.main_window.market_data_dict:
                    data = self.main_window.market_data_dict[poly_ticker]
                    bid = data.get('bid')
                    ask = data.get('ask')
                    if bid and ask and float(bid) > 0 and float(ask) > 0:
                        print(f"[PSFAlgo1 BID/ASK] {ticker} ana pencere market_data'dan alındı: Bid={bid}, Ask={ask}")
                        return float(bid), float(ask)
            # 4. Current window market_data_dict'ten al
            if hasattr(self, 'current_window') and self.current_window and hasattr(self.current_window, 'market_data_dict'):
                poly_ticker = self.polygonize_ticker(ticker)
                if poly_ticker in self.current_window.market_data_dict:
                    data = self.current_window.market_data_dict[poly_ticker]
                    bid = data.get('bid')
                    ask = data.get('ask')
                    if bid and ask and float(bid) > 0 and float(ask) > 0:
                        print(f"[PSFAlgo1 BID/ASK] {ticker} current_window market_data'dan alındı: Bid={bid}, Ask={ask}")
                        return float(bid), float(ask)
            # 5. Son çare: current price'ın %0.5'i kadar spread varsay
            current_price = self.get_current_price(ticker)
            if current_price and current_price > 0:
                estimated_spread = current_price * 0.005
                bid = current_price - (estimated_spread / 2)
                ask = current_price + (estimated_spread / 2)
                print(f"[PSFAlgo1 BID/ASK] {ticker} tahmini bid/ask: Bid={bid:.3f}, Ask={ask:.3f} (spread: {estimated_spread:.3f})")
                return bid, ask
            print(f"[PSFAlgo1 BID/ASK] {ticker} hiçbir kaynaktan fiyat alınamadı")
            return None, None
        except Exception as e:
            print(f"[PSFAlgo1 BID/ASK] {ticker} bid/ask alma hatası: {e}")
            return None, None

    def get_current_price(self, ticker):
        """Ticker için mevcut fiyatı döndür (fallback'lı, mapping'li)"""
        try:
            # 1. Pencere verisinden al
            if hasattr(self, 'current_window') and self.current_window:
                for col in ['Last price', 'Current Price', 'Last', 'Bid', 'Ask']:
                    price = self.get_price_from_window(self.current_window, ticker, col)
                    if price and price > 0:
                        print(f"[PSFAlgo1 PRICE] {ticker} pencere {col} ile bulundu: {price}")
                        return price
            # 2. Market_data.get_market_data ile (Polygon)
            if hasattr(self.market_data, 'get_market_data'):
                poly_ticker = self.polygonize_ticker(ticker)
                market_data = self.market_data.get_market_data([poly_ticker])
                if market_data and poly_ticker in market_data and 'last' in market_data[poly_ticker]:
                    price = market_data[poly_ticker]['last']
                    if price and price > 0:
                        print(f"[PSFAlgo1 PRICE] {ticker} market_data ile bulundu: {price}")
                        return price
            # 3. market_data.get_current_price fallback
            if hasattr(self.market_data, 'get_current_price'):
                price = self.market_data.get_current_price(ticker)
                if price and price > 0:
                    print(f"[PSFAlgo1 PRICE] {ticker} market_data.get_current_price ile bulundu: {price}")
                    return price
            # 4. last_data fallback
            if hasattr(self.market_data, 'last_data'):
                poly_ticker = self.polygonize_ticker(ticker)
                if poly_ticker in self.market_data.last_data:
                    last_data = self.market_data.last_data[poly_ticker]
                    if isinstance(last_data, dict) and 'last' in last_data:
                        price = last_data['last']
                        if price and price > 0:
                            print(f"[PSFAlgo1 PRICE] {ticker} last_data ile bulundu: {price}")
                            return price
            print(f"[PSFAlgo1 PRICE] {ticker} için fiyat bulunamadı")
        except Exception as e:
            print(f"[PSFAlgo1 PRICE] ⚠️ {ticker} fiyatı alınamadı: {e}")
        return None

    def calculate_benchmark_at_fill(self, ticker):
        """Fill anında benchmark değerini hesapla"""
        try:
            # Önce güncel fiyatı al
            current_price = self.get_current_price(ticker)
            if current_price:
                return current_price
            
            # Fallback: GUI'den Last price
            if self.current_window:
                price = self.get_price_from_window(self.current_window, ticker, 'Last price')
                if price and price > 0:
                    return price
            
            # Son çare: None döndür
            print(f"[BENCHMARK] ⚠️ {ticker} için benchmark hesaplanamadı")
            return None
            
        except Exception as e:
            print(f"[BENCHMARK ERROR] {ticker} benchmark hesaplanırken hata: {e}")
            return None

    def validate_front_order_before_sending(self, ticker, order_type, target_price):
        """
        Front emir göndermeden önce spread koşulunu kontrol et (PSFAlgo2 ile uyumlu)
        Args:
            ticker: Hisse senedi kodu
            order_type: 'front_buy' veya 'front_sell'
            target_price: Hedef emir fiyatı
        Returns:
            (bool, str): (emir_gönderilebilir_mi, açıklama_mesajı)
        """
        print(f"[PSFAlgo1 FRONT VALIDATION] {ticker} {order_type} @ {target_price:.3f} spread kontrolü...")
        bid_price, ask_price = self.get_bid_ask_prices(ticker)
        if bid_price and ask_price and bid_price > 0 and ask_price > 0:
            spread = ask_price - bid_price
            if spread < 0.06:
                print(f"[PSFAlgo1 FRONT VALIDATION] ✅ {ticker} {order_type} - Spread çok dar ({spread:.4f} < 0.06), kontrol atlanıyor")
                return True, f"Dar spread ({spread:.4f} < 0.06) - kontrol atlandı"
            print(f"[PSFAlgo1 FRONT VALIDATION] 🔍 {ticker} {order_type} - Geniş spread ({spread:.4f} ≥ 0.06), kontrol yapılıyor")
        else:
            print(f"[PSFAlgo1 FRONT VALIDATION] ⚠️ {ticker} {order_type} - Bid/Ask alınamadı, kontrol yapılıyor")
        # Front spread koşulunu kontrol et
        is_valid, message = self.check_front_spread_condition(ticker, order_type, target_price)
        if is_valid:
            print(f"[PSFAlgo1 FRONT VALIDATION] ✅ {ticker} {order_type} - {message}")
            return True, message
        else:
            print(f"[PSFAlgo1 FRONT VALIDATION] ❌ {ticker} {order_type} - {message}")
            return False, message

    def check_existing_orders_conflict(self, ticker, target_price, order_side, tolerance=0.08):
        """
        Ticker için mevcut emirleri kontrol eder ve hedef fiyatın +/-tolerance aralığında 
        aynı yönde emir olup olmadığını kontrol eder
        
        Args:
            ticker: Hisse sembolü
            target_price: Hedef emir fiyatı
            order_side: 'BUY' veya 'SELL'
            tolerance: Fiyat toleransı (varsayılan 0.08)
        
        Returns:
            (bool, str): (çakışma_var, açıklama_mesajı)
        """
        try:
            if not hasattr(self.market_data, 'ib') or not self.market_data.ib:
                return False, "IBKR bağlantısı yok"
            
            trades = self.market_data.ib.openTrades()
            
            for trade in trades:
                contract = trade.contract
                order = trade.order
                
                if contract.symbol != ticker:
                    continue
                    
                existing_action = order.action  # BUY/SELL
                existing_price = order.lmtPrice
                existing_quantity = order.totalQuantity
                
                # Aynı yönde emir mi?
                if existing_action != order_side:
                    continue
                
                # Fiyat toleransı içinde mi?
                price_diff = abs(existing_price - target_price)
                
                if price_diff <= tolerance:
                    conflict_msg = (f"Çakışma tespit edildi - Mevcut: {existing_action} {existing_quantity} @ {existing_price:.3f}, "
                                  f"Hedef: {order_side} @ {target_price:.3f}, Fark: {price_diff:.3f} ≤ {tolerance}")
                    
                    print(f"[ORDER CONFLICT] ❌ {ticker} - {conflict_msg}")
                    return True, conflict_msg
            
            # Çakışma yok
            return False, f"Çakışma yok - {order_side} @ {target_price:.3f} (tolerance: ±{tolerance})"
            
        except Exception as e:
            print(f"[ORDER CONFLICT] ❌ {ticker} emir çakışma kontrolü hatası: {e}")
            return False, f"Kontrol hatası: {str(e)}"

    def filter_stocks_by_existing_orders(self, selected_stocks, order_side, window, price_column=None):
        """
        Seçili hisselerden mevcut emirlerle çakışanları filtreler ve sıradaki hisseleri ekler
        
        Args:
            selected_stocks: [(ticker, score), ...] listesi
            order_side: 'BUY' veya 'SELL'
            window: Pencere objesi (fiyat bilgisi için)
            price_column: Fiyat kolonu adı (None ise current price kullanılır)
        
        Returns:
            [(ticker, score), ...] filtrelenmiş liste
        """
        if not selected_stocks:
            return []
        
        filtered_stocks = []
        conflicts_found = []
        
        for ticker, score in selected_stocks:
            # Hedef fiyatı belirle - ÖNCE PENCEREDEN ALMAYA ÇALIŞcak
            target_price = None
            
            # 1. Önce pencereden Last price veya Current Price almaya çalış
            if hasattr(window, 'rows') and hasattr(window, 'COLUMNS'):
                # Last price, Current Price, Bid, Ask sırasıyla dene
                price_columns_to_try = ['Last price', 'Current Price', 'Last', 'Bid', 'Ask']
                for col_name in price_columns_to_try:
                    try:
                        target_price = self.get_price_from_window(window, ticker, col_name)
                        if target_price and target_price > 0:
                            print(f"[PRICE] ✅ {ticker} fiyat alındı ({col_name}): {target_price:.3f}")
                            break
                    except:
                        continue
            
            # 2. Pencereden alamadıysa market data'dan dene
            if not target_price or target_price <= 0:
                target_price = self.get_current_price(ticker)
                if target_price and target_price > 0:
                    print(f"[PRICE] ✅ {ticker} fiyat alındı (market data): {target_price:.3f}")
            
            # 3. Hiçbirinden alamadıysa atla
            if not target_price or target_price <= 0:
                print(f"[ORDER FILTER] ❌ {ticker} için fiyat alınamadı (pencere ve market data başarısız), atlanıyor")
                continue
            
            # Çakışma kontrolü
            has_conflict, conflict_msg = self.check_existing_orders_conflict(ticker, target_price, order_side)
            
            if has_conflict:
                conflicts_found.append((ticker, score, conflict_msg))
                print(f"[ORDER FILTER] ❌ {ticker} (skor:{score:.2f}) - {conflict_msg}")
            else:
                filtered_stocks.append((ticker, score))
                print(f"[ORDER FILTER] ✅ {ticker} (skor:{score:.2f}) - Çakışma yok, fiyat: {target_price:.3f}")
        
        if conflicts_found:
            print(f"[ORDER FILTER] ⚠️ {len(conflicts_found)} hisse çakışma nedeniyle filtrelendi:")
            for ticker, score, msg in conflicts_found:
                print(f"[ORDER FILTER]   - {ticker}: {msg}")
        
        return filtered_stocks

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
            print(f"[PRICE FROM WINDOW] ❌ {ticker} fiyat alma hatası: {e}")
            return None

    def get_extended_stock_selection(self, window, score_column, original_count, needed_count, ascending=True, score_range=(0, 1500), order_side='BUY'):
        """
        Çakışma nedeniyle filtrelenen hisseler için genişletilmiş seçim yapar
        
        Args:
            window: Pencere objesi
            score_column: Skor kolonu adı
            original_count: Orijinal seçim sayısı
            needed_count: İhtiyaç duyulan ek hisse sayısı
            ascending: Sıralama yönü
            score_range: Skor aralığı
            order_side: Emir yönü ('BUY'/'SELL')
        
        Returns:
            [(ticker, score), ...] genişletilmiş liste
        """
        # Daha geniş bir seçim yap (original_count + needed_count + buffer)
        buffer_count = max(5, needed_count * 2)  # En az 5, ideal olarak needed_count'un 2 katı
        extended_count = original_count + needed_count + buffer_count
        
        print(f"[EXTENDED SELECTION] 🔍 {score_column} için genişletilmiş seçim: {extended_count} hisse")
        
        # Genişletilmiş seçim yap
        extended_stocks = self.get_top_stocks_by_score(
            window, 
            score_column, 
            count=extended_count,
            ascending=ascending,
            score_range=score_range
        )
        
        if not extended_stocks:
            return []
        
        # Çakışma filtresi uygula
        filtered_stocks = self.filter_stocks_by_existing_orders(
            extended_stocks, 
            order_side, 
            window
        )
        
        print(f"[EXTENDED SELECTION] ✅ {len(extended_stocks)} → {len(filtered_stocks)} hisse (çakışma filtresi sonrası)")
        
        return filtered_stocks

    def calculate_passive_buy_price_psfalgo(self, ticker, fill_price, min_profit_price, bid, ask, spread):
        """✅ PSFAlgo - SHORT fill sonrası pasif BUY reverse order fiyatı hesapla"""
        print(f"[PSF PASSIVE BUY] 📈 {ticker} SHORT fill {fill_price:.3f} sonrası pasif BUY hesaplama")
        
        # Mevcut bid kar hedefimizden düşükse → hidden order
        if bid <= min_profit_price:
            hidden_price = bid + (spread * 0.15)  # Bidin %15 üstüne hidden
            logic = f"Bid ({bid:.3f}) ≤ Kar hedefi ({min_profit_price:.3f}) → Hidden: {hidden_price:.3f}"
            return hidden_price, logic
        else:
            # Bid kar hedefinden yüksek - orderbook depth simülasyonu
            search_range_start = fill_price - 0.05
            search_range_end = fill_price - 0.10
            
            # Basit depth analizi
            estimated_bids = []
            current_level = search_range_start
            while current_level >= search_range_end:
                if current_level % 0.05 == 0 or current_level % 0.01 == 0:
                    estimated_bids.append(current_level)
                current_level -= 0.01
                current_level = round(current_level, 2)
            
            if len(estimated_bids) >= 2:
                first_bid = estimated_bids[0]
                second_bid = estimated_bids[1]
                optimal_price = second_bid + 0.01
                logic = f"Depth: İlk bid {first_bid:.3f}, İkinci bid {second_bid:.3f} → Optimal: {optimal_price:.3f}"
                return optimal_price, logic
            else:
                logic = f"Depth yetersiz → Güvenli kar: {min_profit_price:.3f}"
                return min_profit_price, logic

    def calculate_passive_sell_price_psfalgo(self, ticker, fill_price, min_profit_price, bid, ask, spread):
        """✅ PSFAlgo - LONG fill sonrası pasif SELL reverse order fiyatı hesapla"""
        print(f"[PSF PASSIVE SELL] 📉 {ticker} LONG fill {fill_price:.3f} sonrası pasif SELL hesaplama")
        
        # Mevcut ask kar hedefimizden yüksekse → hidden order
        if ask >= min_profit_price:
            hidden_price = ask - (spread * 0.15)  # Askin %15 altına hidden
            logic = f"Ask ({ask:.3f}) ≥ Kar hedefi ({min_profit_price:.3f}) → Hidden: {hidden_price:.3f}"
            return hidden_price, logic
        else:
            # Ask kar hedefinden düşük - orderbook depth simülasyonu
            search_range_start = fill_price + 0.05
            search_range_end = fill_price + 0.10
            
            # Basit depth analizi
            estimated_asks = []
            current_level = search_range_start
            while current_level <= search_range_end:
                if current_level % 0.05 == 0 or current_level % 0.01 == 0:
                    estimated_asks.append(current_level)
                current_level += 0.01
                current_level = round(current_level, 2)
            
            if len(estimated_asks) >= 2:
                first_ask = estimated_asks[0]
                second_ask = estimated_asks[1]
                optimal_price = second_ask - 0.01
                logic = f"Depth: İlk ask {first_ask:.3f}, İkinci ask {second_ask:.3f} → Optimal: {optimal_price:.3f}"
                return optimal_price, logic
            else:
                logic = f"Depth yetersiz → Güvenli kar: {min_profit_price:.3f}"
                return min_profit_price, logic
