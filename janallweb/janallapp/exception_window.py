"""
Exception List Window - Exception listesini yönetmek için GUI penceresi.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from .exception_manager import ExceptionListManager

class ExceptionListWindow:
    def __init__(self, parent, exception_manager):
        """
        Exception listesi yönetim penceresi.
        
        Args:
            parent: Ana pencere referansı
            exception_manager: ExceptionListManager instance
        """
        self.parent = parent
        self.exception_manager = exception_manager
        
        # Pencere oluştur
        self.window = tk.Toplevel(parent)
        self.window.title("Exception Listesi Yönetimi")
        self.window.geometry("500x400")
        self.window.resizable(True, True)
        
        # Pencereyi ortala
        self.center_window()
        
        # GUI bileşenlerini oluştur
        self.create_widgets()
        
        # Listeyi güncelle
        self.refresh_list()
        
        # Pencere kapatıldığında ana pencereyi güncelle
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def center_window(self):
        """Pencereyi ekranın ortasına yerleştirir."""
        self.window.update_idletasks()
        width = self.window.winfo_width()
        height = self.window.winfo_height()
        x = (self.window.winfo_screenwidth() // 2) - (width // 2)
        y = (self.window.winfo_screenheight() // 2) - (height // 2)
        self.window.geometry(f"{width}x{height}+{x}+{y}")
    
    def create_widgets(self):
        """GUI bileşenlerini oluşturur."""
        # Ana frame
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Grid ağırlıklarını ayarla
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # Başlık
        title_label = ttk.Label(main_frame, text="Exception Listesi", 
                               font=("Arial", 14, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 10))
        
        # Açıklama
        desc_label = ttk.Label(main_frame, 
                              text="Bu listedeki hisseler trade edilmeyecektir.",
                              font=("Arial", 9))
        desc_label.grid(row=1, column=0, columnspan=3, pady=(0, 10))
        
        # Liste frame
        list_frame = ttk.LabelFrame(main_frame, text="Exception Hisse Listesi", padding="5")
        list_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        # Liste
        self.listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE)
        self.listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.listbox.configure(yscrollcommand=scrollbar.set)
        
        # Butonlar frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.grid(row=3, column=0, columnspan=3, pady=(10, 0))
        
        # Ticker ekle butonu
        add_button = ttk.Button(buttons_frame, text="Ticker Ekle", 
                               command=self.add_ticker)
        add_button.grid(row=0, column=0, padx=(0, 5))
        
        # Çoklu ticker ekle butonu
        add_multiple_button = ttk.Button(buttons_frame, text="Çoklu Ticker Ekle", 
                                        command=self.add_multiple_tickers)
        add_multiple_button.grid(row=0, column=1, padx=5)
        
        # Ticker sil butonu
        remove_button = ttk.Button(buttons_frame, text="Seçili Ticker'ı Sil", 
                                  command=self.remove_selected_ticker)
        remove_button.grid(row=0, column=2, padx=5)
        
        # Listeyi temizle butonu
        clear_button = ttk.Button(buttons_frame, text="Listeyi Temizle", 
                                 command=self.clear_list)
        clear_button.grid(row=0, column=3, padx=5)
        
        # Kapat butonu
        close_button = ttk.Button(buttons_frame, text="Kapat", 
                                 command=self.on_closing)
        close_button.grid(row=0, column=4, padx=(5, 0))
    
    def refresh_list(self):
        """Listeyi günceller."""
        self.listbox.delete(0, tk.END)
        exception_list = self.exception_manager.get_exception_list()
        
        if not exception_list:
            self.listbox.insert(tk.END, "Exception listesi boş")
        else:
            for ticker in exception_list:
                self.listbox.insert(tk.END, ticker)
    
    def add_multiple_tickers(self):
        """Birden fazla ticker ekler."""
        # Çoklu ticker ekleme penceresi oluştur
        multi_window = tk.Toplevel(self.window)
        multi_window.title("Çoklu Ticker Ekle")
        multi_window.geometry("400x300")
        multi_window.transient(self.window)
        multi_window.grab_set()
        
        # Pencereyi ortala
        multi_window.update_idletasks()
        width = multi_window.winfo_width()
        height = multi_window.winfo_height()
        x = (multi_window.winfo_screenwidth() // 2) - (width // 2)
        y = (multi_window.winfo_screenheight() // 2) - (height // 2)
        multi_window.geometry(f"{width}x{height}+{x}+{y}")
        
        # Ana frame
        main_frame = ttk.Frame(multi_window, padding="10")
        main_frame.pack(fill='both', expand=True)
        
        # Başlık
        title_label = ttk.Label(main_frame, text="Çoklu Ticker Ekle", 
                               font=("Arial", 12, "bold"))
        title_label.pack(pady=(0, 10))
        
        # Açıklama
        desc_label = ttk.Label(main_frame, 
                              text="Her satıra bir ticker yazın. Boş satırlar otomatik olarak atlanır.",
                              font=("Arial", 9))
        desc_label.pack(pady=(0, 10))
        
        # Text widget
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        text_widget = tk.Text(text_frame, height=10, width=40)
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Örnek metin ekle
        example_text = """ESGRP
BHFAN
ABR PRF
AAPL
MSFT"""
        text_widget.insert(tk.END, example_text)
        
        # Butonlar frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(pady=(10, 0))
        
        def add_tickers():
            """Ticker'ları ekle"""
            text_content = text_widget.get("1.0", tk.END).strip()
            if not text_content:
                messagebox.showwarning("Uyarı", "Lütfen en az bir ticker girin.")
                return
            
            # Satırları ayır ve temizle
            lines = [line.strip().upper() for line in text_content.split('\n') if line.strip()]
            
            if not lines:
                messagebox.showwarning("Uyarı", "Geçerli ticker bulunamadı.")
                return
            
            # Ticker'ları ekle
            added_count = 0
            already_exists = []
            
            for ticker in lines:
                if ticker and not self.exception_manager.is_exception_ticker(ticker):
                    if self.exception_manager.add_ticker(ticker):
                        added_count += 1
                elif ticker and self.exception_manager.is_exception_ticker(ticker):
                    already_exists.append(ticker)
            
            # Sonuç mesajı
            if added_count > 0:
                message = f"{added_count} ticker başarıyla eklendi."
                if already_exists:
                    message += f"\n\nZaten listede bulunan ticker'lar: {', '.join(already_exists)}"
                messagebox.showinfo("Başarılı", message)
                self.refresh_list()
                multi_window.destroy()
            else:
                if already_exists:
                    messagebox.showinfo("Bilgi", f"Tüm ticker'lar zaten listede bulunuyor: {', '.join(already_exists)}")
                else:
                    messagebox.showerror("Hata", "Hiçbir ticker eklenemedi.")
        
        def cancel():
            """İptal et"""
            multi_window.destroy()
        
        # Ekle butonu
        add_button = ttk.Button(buttons_frame, text="Ekle", command=add_tickers)
        add_button.pack(side='left', padx=(0, 5))
        
        # İptal butonu
        cancel_button = ttk.Button(buttons_frame, text="İptal", command=cancel)
        cancel_button.pack(side='left', padx=5)
    
    def add_ticker(self):
        """Yeni ticker ekler."""
        ticker = simpledialog.askstring("Ticker Ekle", 
                                       "Eklemek istediğiniz ticker'ı girin:",
                                       parent=self.window)
        
        if ticker:
            ticker = ticker.strip().upper()
            if ticker:
                if self.exception_manager.add_ticker(ticker):
                    self.refresh_list()
                    messagebox.showinfo("Başarılı", f"{ticker} exception listesine eklendi.")
                else:
                    messagebox.showerror("Hata", "Ticker eklenemedi.")
            else:
                messagebox.showerror("Hata", "Geçerli bir ticker girin.")
    
    def remove_selected_ticker(self):
        """Seçili ticker'ı siler."""
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showwarning("Uyarı", "Lütfen silmek istediğiniz ticker'ı seçin.")
            return
        
        ticker = self.listbox.get(selection[0])
        
        # Boş liste mesajı kontrolü
        if ticker == "Exception listesi boş":
            return
        
        if messagebox.askyesno("Onay", f"{ticker} ticker'ını exception listesinden silmek istediğinizden emin misiniz?"):
            if self.exception_manager.remove_ticker(ticker):
                self.refresh_list()
                messagebox.showinfo("Başarılı", f"{ticker} exception listesinden silindi.")
            else:
                messagebox.showerror("Hata", "Ticker silinemedi.")
    
    def clear_list(self):
        """Tüm listeyi temizler."""
        if messagebox.askyesno("Onay", "Tüm exception listesini temizlemek istediğinizden emin misiniz?"):
            self.exception_manager.clear_exception_list()
            self.refresh_list()
            messagebox.showinfo("Başarılı", "Exception listesi temizlendi.")
    
    def on_closing(self):
        """Pencere kapatılırken çağrılır."""
        self.window.destroy()
