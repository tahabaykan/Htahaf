"""
UI utility functions for StockTracker application
"""
import tkinter as tk
from tkinter import ttk
from typing import List, Dict, Any, Callable, Optional

def create_simple_treeview(parent, columns: List[Dict[str, Any]], selection_callback: Optional[Callable] = None):
    """
    Standart bir Treeview oluşturur
    
    Args:
        parent: Treeview'ın yerleştirileceği parent widget
        columns: Sütun bilgilerini içeren liste. Her sütun için bir dict: 
                 {'id': 'column_id', 'text': 'Column Title', 'width': 100, 'anchor': 'center'}
        selection_callback: Bir öğe seçildiğinde çağrılacak fonksiyon
    
    Returns:
        tuple: (treeview, scrollbar) tuple
    """
    # Frame oluştur
    frame = ttk.Frame(parent)
    frame.pack(fill=tk.BOTH, expand=True)
    
    # Scrollbar oluştur
    scrollbar = ttk.Scrollbar(frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    # Sütun ID'lerini al
    column_ids = [col['id'] for col in columns]
    
    # Treeview oluştur
    tree = ttk.Treeview(frame, columns=column_ids, show="headings", yscrollcommand=scrollbar.set)
    
    # Sütun ayarlarını yap
    for col in columns:
        tree.column(col['id'], width=col.get('width', 100), anchor=col.get('anchor', 'center'))
        tree.heading(col['id'], text=col['text'])
    
    # Treeview'ı yerleştir
    tree.pack(fill=tk.BOTH, expand=True)
    
    # Scrollbar'ı Treeview'a bağla
    scrollbar.config(command=tree.yview)
    
    # Seçim callback'ini bağla (eğer verilmişse)
    if selection_callback:
        tree.bind("<<TreeviewSelect>>", selection_callback)
    
    return tree, scrollbar

def create_selectable_treeview(parent, columns, default_lot_size=200):
    """
    Manuel seçim imkanı sunan bir Treeview oluşturur
    
    Args:
        parent: Treeview'ın yerleştirileceği parent widget
        columns: Sütun listesi (ilk sütun "Select" olmalıdır)
        default_lot_size: Varsayılan emir miktarı
    
    Returns:
        tuple: (frame, tree, scrollbar, selected_positions) tuple
    """
    # Seçilen öğeleri saklamak için set
    selected_positions = set()
    
    # Frame oluştur
    frame = ttk.Frame(parent)
    frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
    
    # Treeview oluştur
    tree = ttk.Treeview(
        frame,
        columns=columns,
        show="headings",
        selectmode="none"  # Normal seçim kullanmıyoruz, manuel kontrol edeceğiz
    )
    
    # Sütunları yapılandır
    for i, col in enumerate(columns):
        tree.heading(col, text=col)
        if col == "Select":
            width = 40
            anchor = tk.CENTER
        else:
            width = 100 if col not in ["symbol", "cheapness_score", "outperform_score"] else 120
            anchor = tk.CENTER if col != "symbol" else tk.W
        tree.column(col, width=width, anchor=anchor)
    
    # Scrollbar
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    tree.configure(yscrollcommand=scrollbar.set)
    tree.pack(fill=tk.BOTH, expand=True)
    
    # Treeview tıklama fonksiyonu
    def on_tree_click(event):
        region = tree.identify_region(event.x, event.y)
        column = tree.identify_column(event.x)
        
        # Sadece ilk sütuna (seçim sütunu) tıklandığında işlem yap
        if region == "cell" and column == "#1":
            item_id = tree.identify_row(event.y)
            if item_id:
                item_values = tree.item(item_id, "values")
                if item_values:
                    symbol = item_values[1]  # Symbol değeri
                    current_state = item_values[0]  # Seçim durumu
                    
                    # Durumu değiştir
                    new_state = "✓" if current_state == "□" else "□"
                    tree.set(item_id, "Select", new_state)
                    
                    # Set'e ekle veya çıkar
                    if new_state == "✓":
                        selected_positions.add(symbol)
                    else:
                        if symbol in selected_positions:
                            selected_positions.remove(symbol)
                    
                    print(f"Toplam seçili hisse: {len(selected_positions)}")
    
    # Tıklama olayını bağla
    tree.bind("<ButtonRelease-1>", on_tree_click)
    
    # Butonlar için yardımcı fonksiyonlar
    def select_all_items():
        for item_id in tree.get_children():
            tree.set(item_id, "Select", "✓")
            item_values = tree.item(item_id, "values")
            if item_values and len(item_values) > 1:
                selected_positions.add(item_values[1])  # Symbol değeri
        print(f"Tüm hisseler seçildi. Toplam: {len(selected_positions)}")
        
    def deselect_all_items():
        for item_id in tree.get_children():
            tree.set(item_id, "Select", "□")
        selected_positions.clear()
        print("Tüm seçimler temizlendi.")
    
    # Düzgün satır ekleme fonksiyonu
    def add_row(values, tag=""):
        # İlk değer olarak "□" ekleyerek başla (seçili değil)
        new_values = ("□",) + values  # tuple birleştirme
        return tree.insert("", tk.END, values=new_values, tags=(tag,))
    
    # Ek özellikler
    tree.select_all = select_all_items
    tree.deselect_all = deselect_all_items
    tree.add_selectable_row = add_row
    tree.selected_positions = selected_positions
    tree.default_lot_size = default_lot_size
    
    # Sonuçları döndür
    return frame, tree, scrollbar, selected_positions

def safe_reset_tags(tree, item_id):
    """
    Bir treeview öğesindeki tüm etiketleri güvenli bir şekilde temizler
    
    Args:
        tree: Treeview nesnesi
        item_id: Treeview öğe ID'si
    """
    try:
        # Mevcut öğe bilgilerini al
        current_values = tree.item(item_id, "values")
        
        # Etiketleri sıfırla (boş liste ile)
        tree.item(item_id, tags=())
        
        return current_values
    except Exception as e:
        print(f"Error resetting tags for item {item_id}: {e}")
        return None 