"""
My Positions module - Basit pozisyon görüntüleme
"""

import tkinter as tk
from tkinter import ttk

def show_positions_window(parent, get_last):
    """Hammer Pro'dan doğrudan pozisyonları çek ve göster"""
    win = tk.Toplevel(parent)
    win.title("Pozisyonlarım - Hammer Pro")
    win.geometry("900x400")
    
    # Hammer client'ı al
    hammer_client = None
    try:
        # Parent'tan hammer client'ı al (self.hammer)
        if hasattr(parent, 'hammer'):
            hammer_client = parent.hammer
        else:
            print("[POSITIONS] ❌ Hammer client bulunamadı")
            return
    except Exception as e:
        print(f"[POSITIONS] ❌ Hammer client hatası: {e}")
        return
    
    cols = ['symbol', 'qty', 'avg_cost', 'current_price', 'pnl_vs_cost']
    headers = ['Symbol', 'Qty', 'Avg Cost', 'Current', 'PnL']
    tree = ttk.Treeview(win, columns=cols, show='headings', height=15)
    
    for c, h in zip(cols, headers):
        tree.heading(c, text=h)
        tree.column(c, width=100, anchor='center')
    
    tree.pack(fill='both', expand=True)
    
    def do_refresh():
        """Hammer Pro'dan pozisyonları çek ve tabloya yükle"""
        # Tabloyu temizle
        for item in tree.get_children():
            tree.delete(item)
        
        try:
            print("[POSITIONS] 🔄 Pozisyonlar yenileniyor...")
            
            # Hammer Pro'dan pozisyonları çek
            positions = hammer_client.get_positions_direct()
            
            if not positions:
                print("[POSITIONS] ⚠️ Pozisyon bulunamadı")
                return
                
            print(f"[POSITIONS] ✅ {len(positions)} pozisyon bulundu")
            
            # Her pozisyon için tabloya ekle
            for pos in positions:
                symbol = pos['symbol']
                qty = pos['qty']
                avg_cost = pos['avg_cost']
                current_price = float(get_last(symbol) or 0.0)
                pnl = current_price - avg_cost if avg_cost > 0 else 0.0
                
                # Sadece pozisyonu olan hisseleri göster
                if qty != 0:
                    tree.insert('', 'end', values=[
                        symbol,
                        f"{qty:.0f}",
                        f"${avg_cost:.2f}",
                        f"${current_price:.2f}",
                        f"${pnl:.2f}"
                    ])
                    
        except Exception as e:
            print(f"[POSITIONS] ❌ Yenileme hatası: {e}")
    
    # İlk yükleme
    do_refresh()
    
    # Refresh butonu
    ttk.Button(win, text='Yenile', command=do_refresh).pack(pady=6)
