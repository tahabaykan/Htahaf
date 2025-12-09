import time
import threading

class PSFAlgo1Chain:
    """PSFAlgo1 Chain yönetimi - 8 adımlı sistem"""
    
    def start_chain(self):
        """8 adımlı chain'i başlat - SADECE MEVCUT STATE'E UYGUN PENCEREYI AÇ"""
        if not self.is_active:
            print("[PSFAlgo1 CHAIN] ❌ PSFAlgo1 aktif değil")
            return
            
        print(f"[PSFAlgo1 CHAIN] 🚀 Chain başlatılıyor - State: {self.chain_state}")
        
        # ✅ SADECE MEVCUT STATE'E UYGUN PENCEREYI AÇ
        if self.chain_state == 'T_LOSERS':
            print("[PSFAlgo1 CHAIN] 📉 T-Losers BID BUY (1/8) penceresi açılıyor...")
            self.run_t_losers_bid_buy_chain()
            
        elif self.chain_state == 'T_GAINERS':
            print("[PSFAlgo1 CHAIN] 📈 T-Gainers ASK SELL (3/8) penceresi açılıyor...")
            self.run_t_gainers_ask_sell_chain()
            
        elif self.chain_state == 'LONG_TP_ASK':
            print("[PSFAlgo1 CHAIN] 💰 Long TP ASK SELL (5/8) penceresi açılıyor...")
            self.run_long_tp_ask_sell_chain()
            
        elif self.chain_state == 'SHORT_TP_BID':
            print("[PSFAlgo1 CHAIN] 💰 Short TP BID BUY (7/8) penceresi açılıyor...")
            self.run_short_tp_bid_buy_chain()
            
        else:
            print(f"[PSFAlgo1 CHAIN] ❌ Bilinmeyen state: {self.chain_state}")
            return

    def close_current_windows(self):
        """Mevcut açık pencereleri kapat"""
        if self.current_window:
            try:
                self.current_window.destroy()
                print("[PSFAlgo1 CHAIN] ✅ Mevcut pencere kapatıldı")
            except:
                pass
            finally:
                self.current_window = None

    def finish_chain(self):
        """8 adımlı chain tamamlandı - PSFAlgo2'ye devret"""
        print(f"[PSFAlgo1 CHAIN] ✅ 8 adımlı sistem tamamlandı - Cycle #{self.pisdongu_cycle_count}")
        
        # ✅ PSFAlgo1'i ÖNCE deaktive et (başka pencereler açılmasın)
        self.is_active = False
        print("[PSFAlgo1 CHAIN] ⏸️ PSFAlgo1 deaktive edildi")
        
        # Mevcut pencereleri kapat
        self.close_current_windows()
        
        # ✅ Current window referansını temizle
        self.current_window = None
        
        # PSFAlgo2'ye devret
        if self.psfalgo2:
            print("[PSFAlgo1 CHAIN] 🔄 PSFAlgo2'ye devrediliyor...")
            # PSFAlgo2'yi aktif et ve başlat
            self.psfalgo2.activate_from_psfalgo1(
                self.pisdongu_cycle_count,
                self.daily_fills,
                self.befday_positions,
                self.daily_position_limits
            )
        else:
            print("[PSFAlgo1 CHAIN] ⚠️ PSFAlgo2 referansı yok - 3 dakika bekleyip yeni döngü")
            self.schedule_next_pisdongu_cycle()

    def schedule_next_pisdongu_cycle(self):
        """3 dakika sonra yeni PISDoNGU döngüsü başlat"""
        print("[PSFAlgo1 CHAIN] ⏰ 3 dakika sonra yeni döngü başlatılacak...")
        
        def delayed_start():
            time.sleep(180)  # 3 dakika bekle
            if not self.is_active:  # Hala pasifse yeni döngü başlat
                self.activate()
        
        threading.Thread(target=delayed_start, daemon=True).start()

    def advance_chain(self):
        """Chain'i bir sonraki aşamaya ilerlet"""
        print(f"[PSFAlgo1 CHAIN] 🔄 Chain ilerliyor: {self.chain_state} → ", end="")
        
        # Onay bekleme durumunu sıfırla
        self.waiting_for_approval = False
        
        # ✅ DOĞRU STATE GEÇİŞLERİ
        if self.chain_state == 'T_LOSERS':
            self.chain_state = 'T_LOSERS_FB'
            print(f"T_LOSERS_FB")
            # Aynı pencerede devam et (T-Losers FINAL BUY)
            self.continue_current_window_next_step()
            return
            
        elif self.chain_state == 'T_LOSERS_FB':
            self.chain_state = 'T_GAINERS'
            print(f"T_GAINERS")
            # YENİ PENCERE GEREKLİ
            
        elif self.chain_state == 'T_GAINERS':
            self.chain_state = 'T_GAINERS_FS'
            print(f"T_GAINERS_FS")
            # Aynı pencerede devam et (T-Gainers FRONT SELL)
            self.continue_current_window_next_step()
            return
            
        elif self.chain_state == 'T_GAINERS_FS':
            self.chain_state = 'LONG_TP_ASK'
            print(f"LONG_TP_ASK")
            # YENİ PENCERE GEREKLİ
            
        elif self.chain_state == 'LONG_TP_ASK':
            self.chain_state = 'LONG_TP_FRONT'
            print(f"LONG_TP_FRONT")
            # Aynı pencerede devam et (Long TP FRONT SELL)
            self.continue_current_window_next_step()
            return
            
        elif self.chain_state == 'LONG_TP_FRONT':
            self.chain_state = 'SHORT_TP_BID'
            print(f"SHORT_TP_BID")
            # YENİ PENCERE GEREKLİ
            
        elif self.chain_state == 'SHORT_TP_BID':
            self.chain_state = 'SHORT_TP_FRONT'
            print(f"SHORT_TP_FRONT")
            # Aynı pencerede devam et (Short TP FRONT BUY)
            self.continue_current_window_next_step()
            return
            
        elif self.chain_state == 'SHORT_TP_FRONT':
            print(f"FINISHED")
            self.finish_chain()
            return
            
        else:
            print(f"❌ Bilinmeyen state: {self.chain_state}")
            return
        
        # Buraya geldiysek yeni pencere açmamız gerekiyor
        print(f"[PSFAlgo1 CHAIN] 🪟 Yeni pencere açılıyor...")
        self.start_chain()

    def run_t_losers_bid_buy_chain(self):
        """T-Top Losers aşaması"""
        print("[PSFAlgo1 CHAIN] 📉 T-Top Losers aşaması başlatılıyor...")
        
        if not self.main_window:
            print("[PSFAlgo1 CHAIN] ❌ Ana pencere referansı yok")
            self.advance_chain()
            return
        
        # T-top losers penceresini aç (maltopla versiyonu)
        self.main_window.open_t_top_losers_maltopla()
        
        # Pencere açılana kadar bekle - on_data_ready otomatik olarak run_t_top_losers'ı çağıracak
        print("[PSFAlgo1 CHAIN] T-top losers penceresi açıldı, veri yüklenmeyi bekliyor...")

    def run_t_gainers_ask_sell_chain(self):
        """T-Top Gainers aşaması"""
        print("[PSFAlgo1 CHAIN] 📈 T-Top Gainers aşaması başlatılıyor...")
        
        if not self.main_window:
            print("[PSFAlgo1 CHAIN] ❌ Ana pencere referansı yok")
            self.advance_chain()
            return
        
        # T-top gainers penceresini aç (maltopla versiyonu)
        self.main_window.open_t_top_gainers_maltopla()
        
        # Pencere açılana kadar bekle - on_data_ready otomatik olarak run_t_top_gainers'ı çağıracak
        print("[PSFAlgo1 CHAIN] T-top gainers penceresi açıldı, veri yüklenmeyi bekliyor...")

    def run_long_tp_ask_sell_chain(self):
        """Long Take Profit - Ask Sell aşaması"""
        print("[PSFAlgo1 CHAIN] 💰 Long TP - Ask Sell aşaması başlatılıyor...")
        
        if not self.main_window:
            print("[PSFAlgo1 CHAIN] ❌ Ana pencere referansı yok")
            self.advance_chain()
            return
        
        # Long Take Profit penceresini aç
        self.main_window.open_long_take_profit_window()
        
        # Pencere açılana kadar bekle - on_data_ready otomatik olarak run_long_tp_ask_sell'i çağıracak
        print("[PSFAlgo1 CHAIN] Long TP penceresi açıldı, veri yüklenmeyi bekliyor...")

    def run_short_tp_bid_buy_chain(self):
        """Short Take Profit - Bid Buy aşaması"""
        print("[PSFAlgo1 CHAIN] 💰 Short TP - Bid Buy aşaması başlatılıyor...")
        
        if not self.main_window:
            print("[PSFAlgo1 CHAIN] ❌ Ana pencere referansı yok")
            self.advance_chain()
            return
        
        # Short Take Profit penceresini aç
        self.main_window.open_short_take_profit_window()
        
        # Pencere açılana kadar bekle - on_data_ready otomatik olarak run_short_tp_bid_buy'ı çağıracak
        print("[PSFAlgo1 CHAIN] Short TP penceresi açıldı, veri yüklenmeyi bekliyor...")

    def get_chain_state_title(self):
        """Chain durumuna göre başlık döndür"""
        titles = {
            'T_LOSERS': "🔄 PISDoNGU (1/8) - T-Losers BID BUY",
            'T_LOSERS_FB': "🔄 PISDoNGU (2/8) - T-Losers FINAL BUY", 
            'T_GAINERS': "🔄 PISDoNGU (3/8) - T-Gainers ASK SELL",
            'T_GAINERS_FS': "🔄 PISDoNGU (4/8) - T-Gainers FRONT SELL",
            'LONG_TP_ASK': "🔄 PISDoNGU (5/8) - Long TP ASK SELL",
            'LONG_TP_FRONT': "🔄 PISDoNGU (6/8) - Long TP FRONT SELL",
            'SHORT_TP_BID': "🔄 PISDoNGU (7/8) - Short TP BID BUY",
            'SHORT_TP_FRONT': "🔄 PISDoNGU (8/8) - Short TP FRONT BUY"
        }
        return titles.get(self.chain_state, f"🔄 PISDoNGU - {self.chain_state}")

    def on_window_opened(self, window):
        """Pencere açıldığında çağrılır"""
        self.current_window = window
        print(f"[PSFAlgo1 CHAIN] ✅ Pencere açıldı: {window.title()}")

    def on_data_ready(self, window):
        """Pencere verisi hazır olduğunda çağrılır - SADECE AKTİF CHAIN STATE İÇİN"""
        print(f"[PSFAlgo1 CHAIN] 📊 Veri hazır: {window.title()}")
        
        # ✅ PSFAlgo1 aktif değilse hiçbir işlem yapma
        if not self.is_active:
            print("[PSFAlgo1 CHAIN] ⏸️ PSFAlgo1 deaktif, otomatik işlem yapılmıyor")
            return
        
        # ✅ Eğer onay bekliyorsak, otomatik işlem yapma
        if hasattr(self, 'waiting_for_approval') and self.waiting_for_approval:
            print("[PSFAlgo1 CHAIN] ⏸️ Onay bekleniyor, otomatik işlem yapılmıyor")
            return
        
        # ✅ SADECE MEVCUT CHAIN STATE'E UYGUN PENCEREDE İŞLEM YAP
        window_title = window.title().lower()
        
        print(f"[PSFAlgo1 CHAIN] 🎯 Mevcut state: {self.chain_state}")
        
        # T-TOP LOSERS penceresi için - sadece T_LOSERS state'inde
        if "t-top losers" in window_title and self.chain_state == 'T_LOSERS':
            print("[PSFAlgo1 CHAIN] ✅ T-Losers BID BUY (1/8) başlatılıyor...")
            self.run_new_t_losers_bb()
            
        # T-TOP GAINERS penceresi için - sadece T_GAINERS state'inde  
        elif "t-top gainers" in window_title and self.chain_state == 'T_GAINERS':
            print("[PSFAlgo1 CHAIN] ✅ T-Gainers ASK SELL (3/8) başlatılıyor...")
            self.run_new_t_gainers_as()
            
        # LONG TAKE PROFIT penceresi için - sadece LONG_TP_* state'lerinde
        elif "long take profit" in window_title and self.chain_state in ['LONG_TP_ASK', 'LONG_TP_FRONT']:
            if self.chain_state == 'LONG_TP_ASK':
                print("[PSFAlgo1 CHAIN] ✅ Long TP ASK SELL (5/8) başlatılıyor...")
                self.run_new_long_tp_as()
            elif self.chain_state == 'LONG_TP_FRONT':
                print("[PSFAlgo1 CHAIN] ✅ Long TP FRONT SELL (6/8) başlatılıyor...")
                self.run_new_long_tp_fs()
                
        # SHORT TAKE PROFIT penceresi için - sadece SHORT_TP_* state'lerinde
        elif "short take profit" in window_title and self.chain_state in ['SHORT_TP_BID', 'SHORT_TP_FRONT']:
            if self.chain_state == 'SHORT_TP_BID':
                print("[PSFAlgo1 CHAIN] ✅ Short TP BID BUY (7/8) başlatılıyor...")
                self.run_new_short_tp_bb()
            elif self.chain_state == 'SHORT_TP_FRONT':
                print("[PSFAlgo1 CHAIN] ✅ Short TP FRONT BUY (8/8) başlatılıyor...")
                self.run_new_short_tp_fb()
        else:
            print(f"[PSFAlgo1 CHAIN] ⏭️ Bu pencere mevcut state ile uyuşmuyor: {window_title} vs {self.chain_state}")
            return

    def continue_current_window_next_step(self):
        """Mevcut pencerede bir sonraki adıma geç (yeni pencere açma)"""
        print(f"[PSFAlgo1 CHAIN] 🔄 Mevcut pencerede sonraki adım: {self.chain_state}")
        
        if self.chain_state == 'T_LOSERS_FB':
            print("[PSFAlgo1 CHAIN] ✅ T-Losers FINAL BUY (2/8) başlatılıyor...")
            self.run_new_t_losers_fb()
            
        elif self.chain_state == 'T_GAINERS_FS':
            print("[PSFAlgo1 CHAIN] ✅ T-Gainers FRONT SELL (4/8) başlatılıyor...")
            self.run_new_t_gainers_fs()
            
        elif self.chain_state == 'LONG_TP_FRONT':
            print("[PSFAlgo1 CHAIN] ✅ Long TP FRONT SELL (6/8) başlatılıyor...")
            self.run_new_long_tp_fs()
            
        elif self.chain_state == 'SHORT_TP_FRONT':
            print("[PSFAlgo1 CHAIN] ✅ Short TP FRONT BUY (8/8) başlatılıyor...")
            self.run_new_short_tp_fb()
            
        else:
            print(f"[PSFAlgo1 CHAIN] ❌ continue_current_window_next_step için bilinmeyen state: {self.chain_state}")
            return 