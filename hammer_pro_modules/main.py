"""
Hammer Pro FINAL BB Score Calculator
Gerçek zamanlı market data ile FINAL BB skor hesaplama
"""

import asyncio
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import pandas as pd
import threading
import logging
from datetime import datetime
from typing import Dict, Any, Optional

# Import our modules
from connection import HammerProConnection
from config import HammerProConfig
from csv_handler import HammerProCSVHandler
from market_data_manager import HammerProMarketDataManager
from watchlist_manager import HammerProWatchlistManager
from layout_manager import HammerProLayoutManager

class HammerProFinalBBCalculator:
    """Hammer Pro FINAL BB Skor Hesaplayıcı"""
    
    def __init__(self):
        """Ana uygulama başlat"""
        self.setup_logging()
        self.setup_gui()
        
        # Hammer Pro bağlantıları
        self.connection = None
        self.market_data_manager = None
        self.watchlist_manager = None
        self.layout_manager = None
        self.csv_handler = HammerProCSVHandler()
        
        # Durum değişkenleri
        self.is_connected = False
        self.current_csv_data = None
        
    def setup_logging(self):
        """Logging ayarla"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('hammer_pro_final_bb.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def setup_gui(self):
        """GUI ayarla"""
        self.root = tk.Tk()
        self.root.title("Hammer Pro FINAL BB Skor Hesaplayıcı")
        self.root.geometry("1200x800")
        self.root.resizable(True, True)
        
        # Ana frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Bağlantı bölümü
        self.setup_connection_frame(main_frame)
        
        # CSV yükleme bölümü
        self.setup_csv_frame(main_frame)
        
        # Market data bölümü
        self.setup_market_data_frame(main_frame)
        
        # FINAL BB skorları bölümü
        self.setup_final_bb_frame(main_frame)
        
        # Log bölümü
        self.setup_log_frame(main_frame)
        
    def setup_connection_frame(self, parent):
        """Bağlantı frame'i oluştur"""
        connection_frame = ttk.LabelFrame(parent, text="Hammer Pro Bağlantısı", padding=10)
        connection_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Bağlantı ayarları
        settings_frame = ttk.Frame(connection_frame)
        settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(settings_frame, text="Host:").grid(row=0, column=0, sticky='w', padx=(0, 5))
        self.host_var = tk.StringVar(value=HammerProConfig.DEFAULT_HOST)
        ttk.Entry(settings_frame, textvariable=self.host_var, width=15).grid(row=0, column=1, padx=(0, 10))
        
        ttk.Label(settings_frame, text="Port:").grid(row=0, column=2, sticky='w', padx=(0, 5))
        self.port_var = tk.StringVar(value=str(HammerProConfig.DEFAULT_PORT))
        ttk.Entry(settings_frame, textvariable=self.port_var, width=10).grid(row=0, column=3, padx=(0, 10))
        
        ttk.Label(settings_frame, text="Password:").grid(row=0, column=4, sticky='w', padx=(0, 5))
        self.password_var = tk.StringVar(value="")  # Default empty password
        ttk.Entry(settings_frame, textvariable=self.password_var, show="*", width=15).grid(row=0, column=5, padx=(0, 10))
        
        # Bağlantı butonları
        button_frame = ttk.Frame(connection_frame)
        button_frame.pack(fill=tk.X)
        
        self.connect_btn = ttk.Button(button_frame, text="Bağlan", command=self.connect_to_hammer)
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.disconnect_btn = ttk.Button(button_frame, text="Bağlantıyı Kes", command=self.disconnect_from_hammer, state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.status_label = ttk.Label(button_frame, text="Bağlantı durumu: Bağlı değil")
        self.status_label.pack(side=tk.LEFT)
        
    def setup_csv_frame(self, parent):
        """CSV frame'i oluştur"""
        csv_frame = ttk.LabelFrame(parent, text="CSV Veri Yönetimi", padding=10)
        csv_frame.pack(fill=tk.X, pady=(0, 10))
        
        # CSV dosya seçimi
        file_frame = ttk.Frame(csv_frame)
        file_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(file_frame, text="CSV Dosyası:").pack(side=tk.LEFT, padx=(0, 5))
        self.csv_path_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.csv_path_var, width=50).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(file_frame, text="Dosya Seç", command=self.select_csv_file).pack(side=tk.LEFT)
        
        # CSV yükleme butonları
        load_frame = ttk.Frame(csv_frame)
        load_frame.pack(fill=tk.X)
        
        ttk.Button(load_frame, text="CSV Yükle", command=self.load_csv_data).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(load_frame, text="Market Data Güncelle", command=self.update_market_data).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(load_frame, text="FINAL BB Hesapla", command=self.calculate_final_bb_scores).pack(side=tk.LEFT)
        
        # CSV bilgileri
        info_frame = ttk.Frame(csv_frame)
        info_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.csv_info_label = ttk.Label(info_frame, text="CSV yüklenmedi")
        self.csv_info_label.pack(side=tk.LEFT)
        
    def setup_market_data_frame(self, parent):
        """Market data frame'i oluştur"""
        market_frame = ttk.LabelFrame(parent, text="Market Data Bilgileri", padding=10)
        market_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Market data tablosu
        columns = ('Symbol', 'Bid', 'Ask', 'Last', 'Prev Close', 'Volume', 'Spread', 'Benchmark')
        self.market_tree = ttk.Treeview(market_frame, columns=columns, show='headings', height=8)
        
        for col in columns:
            self.market_tree.heading(col, text=col)
            self.market_tree.column(col, width=100)
        
        # Scrollbar
        market_scrollbar = ttk.Scrollbar(market_frame, orient=tk.VERTICAL, command=self.market_tree.yview)
        self.market_tree.configure(yscrollcommand=market_scrollbar.set)
        
        self.market_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        market_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
    def setup_final_bb_frame(self, parent):
        """FINAL BB frame'i oluştur"""
        bb_frame = ttk.LabelFrame(parent, text="FINAL BB Skorları", padding=10)
        bb_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # FINAL BB tablosu
        columns = ('Symbol', 'FINAL_THG', 'BB', 'FB', 'AB', 'AS', 'FS', 'BS', 'Market Data')
        self.bb_tree = ttk.Treeview(bb_frame, columns=columns, show='headings', height=12)
        
        for col in columns:
            self.bb_tree.heading(col, text=col)
            if col == 'Symbol':
                self.bb_tree.column(col, width=120)
            else:
                self.bb_tree.column(col, width=100)
        
        # Scrollbar
        bb_scrollbar = ttk.Scrollbar(bb_frame, orient=tk.VERTICAL, command=self.bb_tree.yview)
        self.bb_tree.configure(yscrollcommand=bb_scrollbar.set)
        
        self.bb_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        bb_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # FINAL BB formülü açıklaması
        formula_frame = ttk.LabelFrame(parent, text="FINAL BB Formülü", padding=10)
        formula_frame.pack(fill=tk.X)
        
        formula_text = """
FINAL BB Formülü:
- FINAL_BB = FINAL_THG - 400 × bid_buy_ucuzluk
- bid_buy_ucuzluk = (bid + spread × 0.15 - prev_close) - benchmark
- FINAL_FB = FINAL_THG - 400 × front_buy_ucuzluk  
- front_buy_ucuzluk = (last + 0.01 - prev_close) - benchmark
- FINAL_AB = FINAL_THG - 400 × ask_buy_ucuzluk
- ask_buy_ucuzluk = (ask + 0.01 - prev_close) - benchmark
- FINAL_AS = FINAL_THG - 400 × ask_sell_pahali
- ask_sell_pahali = (ask - spread × 0.15 - prev_close) - benchmark
- FINAL_FS = FINAL_THG - 400 × front_sell_pahali
- front_sell_pahali = (last - 0.01 - prev_close) - benchmark
- FINAL_BS = FINAL_THG - 400 × bid_sell_pahali
- bid_sell_pahali = (bid - 0.01 - prev_close) - benchmark
        """
        
        formula_label = ttk.Label(formula_frame, text=formula_text, justify=tk.LEFT, font=('Courier', 9))
        formula_label.pack(anchor=tk.W)
        
    def setup_log_frame(self, parent):
        """Log frame'i oluştur"""
        log_frame = ttk.LabelFrame(parent, text="Log Mesajları", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, font=('Courier', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
    def log_message(self, message: str):
        """Log mesajı ekle"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        self.logger.info(message)
        
    def connect_to_hammer(self):
        """Hammer Pro'ya bağlan"""
        try:
            host = self.host_var.get()
            port = int(self.port_var.get())
            password = self.password_var.get()
            
            self.log_message(f"Hammer Pro'ya bağlanılıyor: {host}:{port}")
            
            # Bağlantıyı başlat
            self.connection = HammerProConnection(host, port, password)
            
            # Asenkron bağlantı
            def connect_async():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    success = loop.run_until_complete(self.connection.connect())
                    if success:
                        self.root.after(0, self.on_connection_success)
                    else:
                        self.root.after(0, self.on_connection_failed)
                except Exception as e:
                    self.root.after(0, lambda: self.on_connection_failed(str(e)))
                finally:
                    loop.close()
            
            threading.Thread(target=connect_async, daemon=True).start()
            
        except Exception as e:
            self.log_message(f"Bağlantı hatası: {e}")
            messagebox.showerror("Bağlantı Hatası", f"Hammer Pro'ya bağlanılamadı: {e}")
    
    def on_connection_success(self):
        """Bağlantı başarılı"""
        self.is_connected = True
        self.connect_btn.config(state=tk.DISABLED)
        self.disconnect_btn.config(state=tk.NORMAL)
        self.status_label.config(text="Bağlantı durumu: Bağlı")
        
        # Manager'ları başlat
        self.market_data_manager = HammerProMarketDataManager(self.connection)
        self.watchlist_manager = HammerProWatchlistManager(self.connection)
        self.layout_manager = HammerProLayoutManager(self.connection)
        
        self.log_message("Hammer Pro'ya başarıyla bağlandı!")
        
    def on_connection_failed(self, error: str = "Bilinmeyen hata"):
        """Bağlantı başarısız"""
        self.is_connected = False
        self.connect_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Bağlantı durumu: Bağlı değil")
        
        self.log_message(f"Hammer Pro bağlantısı başarısız: {error}")
        messagebox.showerror("Bağlantı Hatası", f"Hammer Pro'ya bağlanılamadı: {error}")
    
    def disconnect_from_hammer(self):
        """Hammer Pro bağlantısını kes"""
        try:
            if self.connection:
                self.connection.close()
            
            self.is_connected = False
            self.connect_btn.config(state=tk.NORMAL)
            self.disconnect_btn.config(state=tk.DISABLED)
            self.status_label.config(text="Bağlantı durumu: Bağlı değil")
            
            self.log_message("Hammer Pro bağlantısı kesildi")
            
        except Exception as e:
            self.log_message(f"Bağlantı kesme hatası: {e}")
    
    def select_csv_file(self):
        """CSV dosyası seç"""
        from tkinter import filedialog
        
        filename = filedialog.askopenfilename(
            title="CSV Dosyası Seç",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if filename:
            self.csv_path_var.set(filename)
            self.log_message(f"CSV dosyası seçildi: {filename}")
    
    def load_csv_data(self):
        """CSV verilerini yükle"""
        try:
            csv_path = self.csv_path_var.get()
            if not csv_path:
                messagebox.showwarning("Uyarı", "Lütfen bir CSV dosyası seçin")
                return
            
            success = self.csv_handler.load_csv(csv_path)
            if success:
                self.current_csv_data = self.csv_handler.csv_data
                symbol_count = len(self.current_csv_data)
                self.csv_info_label.config(text=f"CSV yüklendi: {symbol_count} sembol")
                self.log_message(f"CSV yüklendi: {symbol_count} sembol")
                
                # Market data tablosunu güncelle
                self.update_market_data_table()
            else:
                messagebox.showerror("Hata", "CSV dosyası yüklenemedi")
                
        except Exception as e:
            self.log_message(f"CSV yükleme hatası: {e}")
            messagebox.showerror("Hata", f"CSV yükleme hatası: {e}")
    
    def update_market_data(self):
        """Market data güncelle"""
        if not self.is_connected or not self.market_data_manager:
            messagebox.showwarning("Uyarı", "Önce Hammer Pro'ya bağlanın")
            return
        
        if self.current_csv_data is None:
            messagebox.showwarning("Uyarı", "Önce CSV verilerini yükleyin")
            return
        
        try:
            symbols = self.current_csv_data[HammerProConfig.CSV_SETTINGS["symbol_column"]].dropna().unique().tolist()
            
            self.log_message(f"Market data güncelleniyor: {len(symbols)} sembol")
            
            def update_async():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    success = loop.run_until_complete(self.market_data_manager.update_market_data_for_symbols(symbols))
                    if success:
                        self.root.after(0, lambda: self.log_message("Market data güncellendi"))
                        self.root.after(0, self.update_market_data_table)
                    else:
                        self.root.after(0, lambda: self.log_message("Market data güncellenemedi"))
                except Exception as e:
                    self.root.after(0, lambda: self.log_message(f"Market data güncelleme hatası: {e}"))
                finally:
                    loop.close()
            
            threading.Thread(target=update_async, daemon=True).start()
            
        except Exception as e:
            self.log_message(f"Market data güncelleme hatası: {e}")
    
    def calculate_final_bb_scores(self):
        """FINAL BB skorlarını hesapla"""
        if not self.is_connected or not self.market_data_manager:
            messagebox.showwarning("Uyarı", "Önce Hammer Pro'ya bağlanın")
            return
        
        if self.current_csv_data is None:
            messagebox.showwarning("Uyarı", "Önce CSV verilerini yükleyin")
            return
        
        try:
            self.log_message("FINAL BB skorları hesaplanıyor...")
            
            # FINAL BB skorlarını hesapla
            scores = self.market_data_manager.calculate_final_bb_scores_batch(self.current_csv_data)
            
            # Sonuçları tabloya ekle
            self.update_final_bb_table(scores)
            
            self.log_message(f"FINAL BB skorları hesaplandı: {len(scores)} sembol")
            
        except Exception as e:
            self.log_message(f"FINAL BB hesaplama hatası: {e}")
            messagebox.showerror("Hata", f"FINAL BB hesaplama hatası: {e}")
    
    def update_market_data_table(self):
        """Market data tablosunu güncelle"""
        # Tabloyu temizle
        for item in self.market_tree.get_children():
            self.market_tree.delete(item)
        
        if not self.market_data_manager or self.current_csv_data is None:
            return
        
        try:
            symbols = self.current_csv_data[HammerProConfig.CSV_SETTINGS["symbol_column"]].dropna().unique().tolist()
            
            for symbol in symbols[:20]:  # İlk 20 sembolü göster
                market_info = self.market_data_manager.get_symbol_market_info(symbol)
                if market_info:
                    self.market_tree.insert('', 'end', values=(
                        symbol,
                        f"{market_info.get('bid', 'N/A'):.2f}" if market_info.get('bid') else 'N/A',
                        f"{market_info.get('ask', 'N/A'):.2f}" if market_info.get('ask') else 'N/A',
                        f"{market_info.get('last', 'N/A'):.2f}" if market_info.get('last') else 'N/A',
                        f"{market_info.get('prevClose', 'N/A'):.2f}" if market_info.get('prevClose') else 'N/A',
                        f"{market_info.get('volume', 'N/A'):,.0f}" if market_info.get('volume') else 'N/A',
                        f"{market_info.get('spread', 'N/A'):.2f}" if market_info.get('spread') else 'N/A',
                        "T"  # Benchmark type
                    ))
            
        except Exception as e:
            self.log_message(f"Market data tablosu güncelleme hatası: {e}")
    
    def update_final_bb_table(self, scores: Dict[str, Dict[str, Any]]):
        """FINAL BB tablosunu güncelle"""
        # Tabloyu temizle
        for item in self.bb_tree.get_children():
            self.bb_tree.delete(item)
        
        try:
            for symbol, score_data in list(scores.items())[:50]:  # İlk 50 sembolü göster
                final_thg = self.current_csv_data[
                    self.current_csv_data[HammerProConfig.CSV_SETTINGS["symbol_column"]] == symbol
                ][HammerProConfig.CSV_SETTINGS["final_thg_column"]].iloc[0]
                
                self.bb_tree.insert('', 'end', values=(
                    symbol,
                    f"{final_thg:.2f}" if pd.notna(final_thg) else 'N/A',
                    f"{score_data.get('final_bb', 'N/A'):.2f}" if score_data.get('final_bb') is not None else 'N/A',
                    f"{score_data.get('final_fb', 'N/A'):.2f}" if score_data.get('final_fb') is not None else 'N/A',
                    f"{score_data.get('final_ab', 'N/A'):.2f}" if score_data.get('final_ab') is not None else 'N/A',
                    f"{score_data.get('final_as', 'N/A'):.2f}" if score_data.get('final_as') is not None else 'N/A',
                    f"{score_data.get('final_fs', 'N/A'):.2f}" if score_data.get('final_fs') is not None else 'N/A',
                    f"{score_data.get('final_bs', 'N/A'):.2f}" if score_data.get('final_bs') is not None else 'N/A',
                    "✓" if score_data.get('market_data_available') else "✗"
                ))
            
        except Exception as e:
            self.log_message(f"FINAL BB tablosu güncelleme hatası: {e}")
    
    def run(self):
        """Uygulamayı çalıştır"""
        self.log_message("Hammer Pro FINAL BB Skor Hesaplayıcı başlatıldı")
        self.root.mainloop()

def main():
    """Ana fonksiyon"""
    app = HammerProFinalBBCalculator()
    app.run()

if __name__ == "__main__":
    main() 