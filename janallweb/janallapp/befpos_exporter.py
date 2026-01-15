"""
BEFPOS.CSV Exporter - Hammer Pro Pozisyonlarını CSV'ye Aktarır

!!! ÖNEMLİ DOSYA YOLU UYARISI !!!
=================================
BÜTÜN CSV OKUMA VE CSV KAYDETME İŞLEMLERİ StockTracker DİZİNİNE YAPILMALI!!
StockTracker/janall/ dizinine YAPILMAMALI!!!
KARIŞASAYI ÖNLEMEK İÇİN BU KURALA MUTLAKA UYULACAK!

Örnek:
✅ DOĞRU: "befpos.csv" (StockTracker dizininde)
❌ YANLIŞ: "janall/befpos.csv"
=================================
"""

import pandas as pd
import os
import time
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, ttk

class BefposExporter:
    def __init__(self, hammer_client):
        self.hammer = hammer_client
        self.csv_filename = 'befham.csv'
        self.export_history = []
        
    def export_positions_to_csv(self):
        """Hammer Pro'daki tüm pozisyonları BEFPOS.CSV'ye aktar"""
        try:
            print("[BEFHAM] OK Pozisyonlar CSV'ye aktariliyor...")
            
            # Hammer Pro bağlantısını kontrol et
            if not self.hammer or not hasattr(self.hammer, 'connected') or not self.hammer.connected:
                error_msg = "Hammer Pro bağlantısı yok! Önce bağlantı kurun."
                print(f"[BEFHAM] ERROR {error_msg}")
                messagebox.showerror("Bağlantı Hatası", error_msg)
                return False
            
            # Pozisyonları al
            print("[BEFHAM] OK Pozisyonlar aliniliyor...")
            positions = self.hammer.get_positions_direct()
            
            if not positions:
                print("[BEFHAM] WARN Hic pozisyon bulunamadi")
                messagebox.showinfo("Bilgi", "Hiç pozisyon bulunamadı!")
                return False
            
            print(f"[BEFHAM] OK {len(positions)} pozisyon bulundu")
            
            # Pozisyon verilerini DataFrame'e dönüştür
            position_data = []
            for pos in positions:
                try:
                    # Pozisyon verilerini parse et
                    symbol = pos.get('symbol', 'N/A')
                    qty = pos.get('qty', 0.0)
                    avg_cost = pos.get('avg_cost', 0.0)
                    
                    # Raw data'dan ek bilgileri al
                    raw_data = pos.get('raw_data', {})
                    if raw_data:
                        # Hammer Pro'dan gelen ham veriyi parse et
                        market_value = raw_data.get('MarketValue', 0.0)
                        unrealized_pnl = raw_data.get('UnrealizedPnL', 0.0)
                        realized_pnl = raw_data.get('RealizedPnL', 0.0)
                        cost_basis = raw_data.get('CostBasis', 0.0)
                        last_price = raw_data.get('LastPrice', 0.0)
                        exchange = raw_data.get('Exchange', 'N/A')
                        account = raw_data.get('Account', 'N/A')
                    else:
                        # Varsayılan değerler
                        market_value = qty * avg_cost
                        unrealized_pnl = 0.0
                        realized_pnl = 0.0
                        cost_basis = avg_cost
                        last_price = avg_cost
                        exchange = 'N/A'
                        account = 'N/A'
                    
                    # Pozisyon türünü belirle
                    position_type = "LONG" if qty > 0 else "SHORT" if qty < 0 else "FLAT"
                    
                    # Güncel zaman
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    position_data.append({
                        'Export_Time': current_time,
                        'Symbol': symbol,
                        'Position_Type': position_type,
                        'Quantity': abs(qty),
                        'Avg_Cost': avg_cost,
                        'Market_Value': market_value,
                        'Unrealized_PnL': unrealized_pnl,
                        'Realized_PnL': realized_pnl,
                        'Cost_Basis': cost_basis,
                        'Last_Price': last_price,
                        'Exchange': exchange,
                        'Account': account,
                        'Total_Value': market_value + unrealized_pnl
                    })
                    
                except Exception as e:
                    print(f"[BEFHAM] WARN Pozisyon parse hatasi: {e} - {pos}")
                    continue
            
            if not position_data:
                print("[BEFHAM] ERROR Hic pozisyon verisi parse edilemedi")
                messagebox.showerror("Hata", "Hiç pozisyon verisi parse edilemedi!")
                return False
            
            # DataFrame oluştur
            df = pd.DataFrame(position_data)
            
            # CSV'ye kaydet
            csv_path = os.path.join(os.getcwd(), self.csv_filename)
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            
            print(f"[BEFHAM] OK {len(position_data)} pozisyon {csv_path} dosyasina kaydedildi")
            
            # Export geçmişini güncelle
            export_info = {
                'timestamp': current_time,
                'positions_count': len(position_data),
                'file_path': csv_path,
                'total_value': df['Total_Value'].sum()
            }
            self.export_history.append(export_info)
            
            # Başarı mesajı göster
            success_msg = f"OK {len(position_data)} pozisyon basariyla aktarıldı!\n\nDosya: {csv_path}\nToplam Deger: ${df['Total_Value'].sum():,.2f}"
            messagebox.showinfo("Başarılı!", success_msg)
            
            return True
            
        except Exception as e:
            error_msg = f"Pozisyon aktarma hatası: {e}"
            print(f"[BEFHAM] ERROR {error_msg}")
            messagebox.showerror("Hata", error_msg)
            return False
    
    def get_export_summary(self):
        """Export özetini döndür"""
        if not self.export_history:
            return "Henüz export yapılmamış"
        
        last_export = self.export_history[-1]
        return f"Son Export: {last_export['timestamp']}\nPozisyon Sayısı: {last_export['positions_count']}\nToplam Değer: ${last_export['total_value']:,.2f}"
    
    def show_export_window(self):
        """Export penceresini göster"""
        export_window = tk.Toplevel()
        export_window.title("BEFHAM Exporter")
        export_window.geometry("600x400")
        export_window.resizable(True, True)
        
        # Ana frame
        main_frame = ttk.Frame(export_window, padding="20")
        main_frame.pack(fill='both', expand=True)
        
        # Başlık
        title_label = ttk.Label(main_frame, text="BEFHAM Exporter", 
                               font=('Arial', 16, 'bold'))
        title_label.pack(pady=(0, 20))
        
        # Açıklama
        desc_label = ttk.Label(main_frame, 
                              text="Hammer Pro'daki tum pozisyonlari BEFHAM (befham.csv) dosyasina aktarir.\n"
                                   "Bu dosya pozisyon analizi ve raporlama için kullanılır.",
                              font=('Arial', 10), justify='center')
        desc_label.pack(pady=(0, 20))
        
        # Export butonu
        export_btn = ttk.Button(main_frame, text="🚀 Pozisyonları CSV'ye Aktar", 
                               command=self.export_positions_to_csv,
                               style='Accent.TButton')
        export_btn.pack(pady=(0, 20))
        
        # Export geçmişi
        history_frame = ttk.LabelFrame(main_frame, text="Export Geçmişi", padding="10")
        history_frame.pack(fill='both', expand=True)
        
        if self.export_history:
            # Son export bilgileri
            last_export = self.export_history[-1]
            history_text = f"""
📊 Son Export: {last_export['timestamp']}
📈 Pozisyon Sayısı: {last_export['positions_count']}
💰 Toplam Değer: ${last_export['total_value']:,.2f}
📁 Dosya: {os.path.basename(last_export['file_path'])}
            """
            
            history_label = ttk.Label(history_frame, text=history_text, 
                                    font=('Consolas', 10), justify='left')
            history_label.pack(anchor='w')
        else:
            no_history_label = ttk.Label(history_frame, text="Henüz export yapılmamış", 
                                       font=('Arial', 10), foreground='gray')
            no_history_label.pack()
        
        # Kapat butonu
        close_btn = ttk.Button(main_frame, text="Kapat", 
                              command=export_window.destroy)
        close_btn.pack(pady=(20, 0))

def show_befpos_exporter(hammer_client):
    """BEFPOS Exporter penceresini göster"""
    exporter = BefposExporter(hammer_client)
    exporter.show_export_window()
    return exporter

if __name__ == "__main__":
    # Test için
    root = tk.Tk()
    root.withdraw()
    
    # Mock hammer client
    class MockHammerClient:
        def __init__(self):
            self.connected = True
        
        def get_positions_direct(self):
            return [
                {
                    'symbol': 'AAPL',
                    'qty': 100.0,
                    'avg_cost': 150.0,
                    'raw_data': {
                        'MarketValue': 15000.0,
                        'UnrealizedPnL': 500.0,
                        'Exchange': 'NASDAQ'
                    }
                },
                {
                    'symbol': 'MSFT',
                    'qty': -50.0,
                    'avg_cost': 300.0,
                    'raw_data': {
                        'MarketValue': 15000.0,
                        'UnrealizedPnL': -200.0,
                        'Exchange': 'NASDAQ'
                    }
                }
            ]
    
    mock_client = MockHammerClient()
    exporter = BefposExporter(mock_client)
    exporter.show_export_window()
    
    root.mainloop()
