import asyncio
import websockets
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
import threading
import logging
from datetime import datetime

class SimpleHammerWatchlist:
    """
    Basit Hammer Pro Watchlist Oluşturucu
    ssfinekheldkuponlu.csv'den watchlist oluşturur
    """
    
    def __init__(self):
        self.setup_logging()
        self.websocket = None
        self.connected = False
        self.csv_data = None
        self.setup_gui()
        
    def setup_logging(self):
        """Logging ayarları"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('hammer_watchlist.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def setup_gui(self):
        """GUI kurulumu"""
        self.root = tk.Tk()
        self.root.title("Hammer Pro Watchlist Oluşturucu")
        self.root.geometry("800x600")
        
        # Ana frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill='both', expand=True)
        
        # Başlık
        ttk.Label(main_frame, text="Hammer Pro Watchlist Oluşturucu", 
                 font=("Arial", 16, "bold")).pack(pady=(0, 20))
        
        # Bağlantı ayarları
        conn_frame = ttk.LabelFrame(main_frame, text="Hammer Pro Bağlantısı")
        conn_frame.pack(fill='x', pady=10)
        
        # Host
        ttk.Label(conn_frame, text="Host:").grid(row=0, column=0, padx=5, pady=5)
        self.host_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(conn_frame, textvariable=self.host_var).grid(row=0, column=1, padx=5, pady=5)
        
        # Port
        ttk.Label(conn_frame, text="Port:").grid(row=1, column=0, padx=5, pady=5)
        self.port_var = tk.StringVar(value="8080")
        ttk.Entry(conn_frame, textvariable=self.port_var).grid(row=1, column=1, padx=5, pady=5)
        
        # Şifre
        ttk.Label(conn_frame, text="Şifre:").grid(row=2, column=0, padx=5, pady=5)
        self.password_var = tk.StringVar()
        ttk.Entry(conn_frame, textvariable=self.password_var, show="*").grid(row=2, column=1, padx=5, pady=5)
        
        # Bağlantı butonları
        btn_frame = ttk.Frame(conn_frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10)
        
        self.connect_btn = ttk.Button(btn_frame, text="Hammer Pro'ya Bağlan", command=self.connect_to_hammer)
        self.connect_btn.pack(side='left', padx=5)
        
        self.disconnect_btn = ttk.Button(btn_frame, text="Bağlantıyı Kes", command=self.disconnect_from_hammer, state='disabled')
        self.disconnect_btn.pack(side='left', padx=5)
        
        # Durum
        self.status_label = ttk.Label(conn_frame, text="Durum: Bağlantı Yok", foreground="red")
        self.status_label.grid(row=4, column=0, columnspan=2, pady=5)
        
        # CSV dosya seçimi
        csv_frame = ttk.LabelFrame(main_frame, text="CSV Dosya Seçimi")
        csv_frame.pack(fill='x', pady=10)
        
        ttk.Label(csv_frame, text="CSV Dosyası:").pack(anchor='w', padx=5, pady=2)
        
        csv_select_frame = ttk.Frame(csv_frame)
        csv_select_frame.pack(fill='x', padx=5, pady=2)
        
        self.csv_path_var = tk.StringVar(value="ssfinekheldkuponlu.csv")
        ttk.Entry(csv_select_frame, textvariable=self.csv_path_var, width=50).pack(side='left', fill='x', expand=True)
        ttk.Button(csv_select_frame, text="Dosya Seç", command=self.select_csv_file).pack(side='right', padx=5)
        
        ttk.Button(csv_frame, text="CSV'yi Yükle", command=self.load_csv_data).pack(pady=5)
        
        # Watchlist oluşturma
        watchlist_frame = ttk.LabelFrame(main_frame, text="Watchlist Oluşturma")
        watchlist_frame.pack(fill='x', pady=10)
        
        ttk.Label(watchlist_frame, text="Watchlist Adı:").pack(anchor='w', padx=5, pady=2)
        self.watchlist_name_var = tk.StringVar(value="SSFI_HELD_KUPONLU")
        ttk.Entry(watchlist_frame, textvariable=self.watchlist_name_var, width=30).pack(anchor='w', padx=5, pady=2)
        
        # Watchlist türü seçimi
        ttk.Label(watchlist_frame, text="Watchlist Türü:").pack(anchor='w', padx=5, pady=2)
        self.watchlist_type_var = tk.StringVar(value="all")
        watchlist_type_frame = ttk.Frame(watchlist_frame)
        watchlist_type_frame.pack(anchor='w', padx=5, pady=2)
        
        ttk.Radiobutton(watchlist_type_frame, text="Tüm Semboller", 
                       variable=self.watchlist_type_var, value="all").pack(side='left', padx=5)
        ttk.Radiobutton(watchlist_type_frame, text="En Yüksek FINAL_THG", 
                       variable=self.watchlist_type_var, value="top_final_thg").pack(side='left', padx=5)
        ttk.Radiobutton(watchlist_type_frame, text="En Düşük FINAL_THG", 
                       variable=self.watchlist_type_var, value="bottom_final_thg").pack(side='left', padx=5)
        
        # Sembol sayısı
        ttk.Label(watchlist_frame, text="Maksimum Sembol Sayısı:").pack(anchor='w', padx=5, pady=2)
        self.max_symbols_var = tk.StringVar(value="50")
        ttk.Entry(watchlist_frame, textvariable=self.max_symbols_var, width=10).pack(anchor='w', padx=5, pady=2)
        
        # Watchlist oluştur butonu
        ttk.Button(watchlist_frame, text="Watchlist Oluştur", command=self.create_watchlist).pack(pady=10)
        
        # Sonuçlar
        result_frame = ttk.LabelFrame(main_frame, text="Sonuçlar")
        result_frame.pack(fill='both', expand=True, pady=10)
        
        # Treeview için scrollbar
        tree_frame = ttk.Frame(result_frame)
        tree_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Treeview
        columns = ('Symbol', 'FINAL_THG', 'Company', 'Status')
        self.result_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=15)
        
        for col in columns:
            self.result_tree.heading(col, text=col)
            self.result_tree.column(col, width=120)
            
        self.result_tree.pack(side='left', fill='both', expand=True)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient='vertical', command=self.result_tree.yview)
        scrollbar.pack(side='right', fill='y')
        self.result_tree.configure(yscrollcommand=scrollbar.set)
        
    def select_csv_file(self):
        """CSV dosyası seç"""
        filename = filedialog.askopenfilename(
            title="CSV Dosyası Seç",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if filename:
            self.csv_path_var.set(filename)
            
    def load_csv_data(self):
        """CSV verilerini yükle"""
        try:
            csv_path = self.csv_path_var.get()
            self.csv_data = pd.read_csv(csv_path)
            
            # Sembol sayısını göster
            symbol_count = len(self.csv_data['PREF IBKR'].dropna().unique())
            messagebox.showinfo("Başarılı", f"CSV yüklendi!\nToplam {symbol_count} benzersiz sembol bulundu.")
            
            # Treeview'i güncelle
            self.update_result_tree()
            
        except Exception as e:
            messagebox.showerror("Hata", f"CSV yüklenirken hata oluştu: {e}")
            
    def update_result_tree(self):
        """Sonuç treeview'ini güncelle"""
        # Mevcut verileri temizle
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
            
        if self.csv_data is not None:
            # İlk 20 sembolü göster
            symbols = self.csv_data['PREF IBKR'].dropna().unique()[:20]
            
            for symbol in symbols:
                symbol_data = self.csv_data[self.csv_data['PREF IBKR'] == symbol]
                if not symbol_data.empty:
                    row = symbol_data.iloc[0]
                    final_thg = row.get('FINAL_THG', 'N/A')
                    company = row.get('Company', 'N/A')
                    
                    self.result_tree.insert('', 'end', values=(symbol, final_thg, company, 'Hazır'))
                    
    async def connect_to_hammer_async(self):
        """Hammer Pro'ya async bağlantı"""
        try:
            ws_url = f"ws://{self.host_var.get()}:{self.port_var.get()}"
            self.websocket = await websockets.connect(ws_url)
            self.connected = True
            
            # Şifre ile kimlik doğrulama
            if self.password_var.get():
                auth_msg = {
                    "cmd": "connect",
                    "pwd": self.password_var.get(),
                    "reqID": "auth_001"
                }
                await self.websocket.send(json.dumps(auth_msg))
                
            self.logger.info("Hammer Pro'ya başarıyla bağlandı")
            
        except Exception as e:
            self.logger.error(f"Hammer Pro'ya bağlanırken hata: {e}")
            self.connected = False
            
    def connect_to_hammer(self):
        """Hammer Pro'ya bağlan (threaded)"""
        def connect_thread():
            asyncio.run(self.connect_to_hammer_async())
            
        threading.Thread(target=connect_thread, daemon=True).start()
        
        # UI güncelle
        self.connect_btn.config(state='disabled')
        self.disconnect_btn.config(state='normal')
        self.status_label.config(text="Durum: Bağlanıyor...", foreground="orange")
        
        # 2 saniye sonra durumu kontrol et
        self.root.after(2000, self.check_connection_status)
        
    def check_connection_status(self):
        """Bağlantı durumunu kontrol et"""
        if self.connected:
            self.status_label.config(text="Durum: Bağlandı", foreground="green")
        else:
            self.status_label.config(text="Durum: Bağlantı Başarısız", foreground="red")
            self.connect_btn.config(state='normal')
            self.disconnect_btn.config(state='disabled')
            
    async def disconnect_from_hammer_async(self):
        """Hammer Pro'dan async bağlantıyı kes"""
        try:
            if self.websocket:
                await self.websocket.close()
            self.connected = False
            self.logger.info("Hammer Pro bağlantısı kesildi")
        except Exception as e:
            self.logger.error(f"Bağlantı kesilirken hata: {e}")
            
    def disconnect_from_hammer(self):
        """Hammer Pro'dan bağlantıyı kes (threaded)"""
        def disconnect_thread():
            asyncio.run(self.disconnect_from_hammer_async())
            
        threading.Thread(target=disconnect_thread, daemon=True).start()
        
        # UI güncelle
        self.connect_btn.config(state='normal')
        self.disconnect_btn.config(state='disabled')
        self.status_label.config(text="Durum: Bağlantı Yok", foreground="red")
        
    async def create_watchlist_async(self):
        """Watchlist oluştur (async)"""
        try:
            if not self.connected or not self.websocket:
                raise Exception("Hammer Pro'ya bağlı değil")
                
            if self.csv_data is None:
                raise Exception("CSV verisi yüklenmemiş")
                
            # Sembolleri al
            symbols = self.csv_data['PREF IBKR'].dropna().unique().tolist()
            watchlist_type = self.watchlist_type_var.get()
            max_symbols = int(self.max_symbols_var.get())
            
            # Watchlist türüne göre filtrele
            if watchlist_type == "top_final_thg":
                # En yüksek FINAL_THG'ye göre sırala
                sorted_data = self.csv_data.sort_values('FINAL_THG', ascending=False)
                symbols = sorted_data['PREF IBKR'].dropna().unique().tolist()[:max_symbols]
            elif watchlist_type == "bottom_final_thg":
                # En düşük FINAL_THG'ye göre sırala
                sorted_data = self.csv_data.sort_values('FINAL_THG', ascending=True)
                symbols = sorted_data['PREF IBKR'].dropna().unique().tolist()[:max_symbols]
            else:
                # Tüm semboller (maksimum sayıya kadar)
                symbols = symbols[:max_symbols]
                
            # Watchlist oluştur
            watchlist_name = self.watchlist_name_var.get()
            
            create_msg = {
                "cmd": "addToPort",
                "new": True,
                "name": watchlist_name,
                "sym": symbols,
                "reqID": f"create_watchlist_{datetime.now().timestamp()}"
            }
            
            await self.websocket.send(json.dumps(create_msg))
            
            # Sonuçları güncelle
            self.update_watchlist_results(symbols)
            
            self.logger.info(f"Watchlist '{watchlist_name}' oluşturuldu: {len(symbols)} sembol")
            
        except Exception as e:
            self.logger.error(f"Watchlist oluşturulurken hata: {e}")
            raise e
            
    def create_watchlist(self):
        """Watchlist oluştur (threaded)"""
        def create_thread():
            try:
                asyncio.run(self.create_watchlist_async())
                messagebox.showinfo("Başarılı", f"Watchlist '{self.watchlist_name_var.get()}' oluşturuldu!")
            except Exception as e:
                messagebox.showerror("Hata", f"Watchlist oluşturulurken hata: {e}")
                
        threading.Thread(target=create_thread, daemon=True).start()
        
    def update_watchlist_results(self, symbols):
        """Watchlist sonuçlarını güncelle"""
        # Treeview'i temizle
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
            
        # Yeni sembolleri ekle
        for i, symbol in enumerate(symbols):
            symbol_data = self.csv_data[self.csv_data['PREF IBKR'] == symbol]
            if not symbol_data.empty:
                row = symbol_data.iloc[0]
                final_thg = row.get('FINAL_THG', 'N/A')
                company = row.get('Company', 'N/A')
                
                self.result_tree.insert('', 'end', values=(symbol, final_thg, company, 'Watchlist\'e Eklendi'))
                
    def run(self):
        """Uygulamayı çalıştır"""
        self.root.mainloop()
        
    def close(self):
        """Uygulamayı kapat"""
        if self.connected and self.websocket:
            asyncio.run(self.disconnect_from_hammer_async())
        self.root.destroy()

if __name__ == "__main__":
    app = SimpleHammerWatchlist()
    try:
        app.run()
    except KeyboardInterrupt:
        app.close() 