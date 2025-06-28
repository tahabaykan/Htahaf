"""
StockTracker için veri yönetimi ve işlem fonksiyonları
"""
import pandas as pd
import tkinter as tk
import numpy as np
from tb_modules.tb_utils import safe_format_float, safe_float, safe_int

def get_filtered_stocks(stocks_df, tab_index, tab_names, filter_text=None):
    """
    Sekme ve filtre metnine göre hisse senetlerini filtrele
    
    Args:
        stocks_df (DataFrame): Tüm hisse senetleri
        tab_index (int): Seçili sekme indeksi
        tab_names (list): Sekme adları listesi
        filter_text (str): Filtre metni (None ise filtre uygulanmaz)
        
    Returns:
        DataFrame: Filtrelenmiş hisse senetleri
    """
    if stocks_df is None or stocks_df.empty:
        return pd.DataFrame()
    
    # Temel kopyasını oluştur
    filtered_df = stocks_df.copy()
    
    # Sekme filtrelemesi
    if tab_index > 0:  # 0 = "Hepsi" sekmesi
        sector = tab_names[tab_index]
        if sector == "Diğer":
            # "Diğer" ana sektörlerden hiçbirine ait olmayanlar
            main_sectors = set(tab_names[1:]) - {"Diğer"}
            filtered_df = filtered_df[~filtered_df['sector'].isin(main_sectors)]
        else:
            filtered_df = filtered_df[filtered_df['sector'] == sector]
    
    # Metin filtrelemesi
    if filter_text and len(filter_text.strip()) > 0:
        filter_text = filter_text.strip().upper()
        
        # Ticker veya açıklamada arama yap
        ticker_match = filtered_df['ticker'].str.contains(filter_text, na=False)
        desc_match = filtered_df['desc'].str.contains(filter_text, na=False, case=False)
        
        filtered_df = filtered_df[ticker_match | desc_match]
    
    return filtered_df

def sort_dataframe(df, sort_column, reverse=False):
    """
    DataFrame'i belirtilen sütuna göre sırala
    
    Args:
        df (DataFrame): Sıralanacak DataFrame
        sort_column (str): Sıralama yapılacak sütun
        reverse (bool): Eğer True ise azalan sıralama, aksi halde artan sıralama
        
    Returns:
        DataFrame: Sıralanmış DataFrame
    """
    if df is None or df.empty or sort_column not in df.columns:
        return df
    
    ascending = not reverse
    return df.sort_values(by=sort_column, ascending=ascending, na_position='last')

def get_paginated_data(df, current_page, items_per_page):
    """
    DataFrame'in belirli sayfasını al
    
    Args:
        df (DataFrame): Veri kaynağı
        current_page (int): Mevcut sayfa numarası (1'den başlar)
        items_per_page (int): Sayfa başına öğe sayısı
        
    Returns:
        tuple: (DataFrame, total_pages) sayfa verisi ve toplam sayfa sayısı
    """
    if df is None or df.empty:
        return df, 1
    
    # Toplam sayfa sayısını hesapla
    total_items = len(df)
    total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
    
    # Mevcut sayfa numarasını kontrol et
    current_page = max(1, min(current_page, total_pages))
    
    # Başlangıç ve bitiş indekslerini hesapla
    start_idx = (current_page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, total_items)
    
    # Sayfa verisini al
    page_data = df.iloc[start_idx:end_idx]
    
    return page_data, total_pages

def populate_treeview_from_dataframe(tree, df, ticker_id_map=None, clear_first=True, tag_callback=None):
    """
    Treeview'ı DataFrame'den doldur
    
    Args:
        tree: Doldurulacak Treeview widget'ı
        df (DataFrame): Kaynak veri
        ticker_id_map (dict): Ticker -> TreeID eşleştirme sözlüğü (varsa güncellenir)
        clear_first (bool): İlk önce Treeview'ı temizle
        tag_callback (function): Her satır için tag üretecek fonksiyon (opsiyonel)
        
    Returns:
        dict: Güncellenmiş ticker_id_map
    """
    if ticker_id_map is None:
        ticker_id_map = {}
    
    # Önce Treeview'ı temizle
    if clear_first:
        for item in tree.get_children():
            tree.delete(item)
    
    if df is None or df.empty:
        return ticker_id_map
    
    # Her satır için
    for idx, row in df.iterrows():
        ticker = row.get('ticker', '')
        
        # Treeview'a eklenecek değerleri hazırla
        values = []
        for col in tree['columns']:
            if col in row:
                # Özel sütun formatlamaları
                if col in ['divAmount', 'divYield', 'last', 'bid', 'ask', 'high', 'low', 'close', 'spread']:
                    values.append(safe_format_float(row[col]))
                elif col == 'change':
                    # Değişim yüzdesi için özel format
                    change_val = safe_float(row[col])
                    values.append(f"{change_val:.2f}" if change_val is not None else "0.00")
                elif col == 'volume':
                    # Hacim için özel format (binler ayracı)
                    volume = safe_int(row[col])
                    values.append(f"{volume:,}" if volume else "0")
                else:
                    values.append(row[col])
            else:
                values.append("")
        
        # Varsa tag hesapla
        tags = ()
        if tag_callback:
            tags = tag_callback(row)
        
        # Satırı Treeview'a ekle
        item_id = tree.insert("", tk.END, values=values, tags=tags)
        
        # Ticker -> TreeID eşleştirmesini güncelle
        ticker_id_map[ticker] = item_id
    
    return ticker_id_map

def update_treeview_item(tree, item_id, column_data, column_map=None):
    """
    Treeview'da belirli bir öğeyi güncelle
    
    Args:
        tree: Güncellenecek Treeview
        item_id: Güncellenecek öğenin ID'si
        column_data (dict): Sütun adı -> değer eşleşmeleri
        column_map (dict): UI sütun adı -> veri sütun adı eşleşmeleri
        
    Returns:
        bool: Başarılı olduysa True
    """
    try:
        # Mevcut değerleri al
        current_values = tree.item(item_id, "values")
        if not current_values:
            return False
        
        values_list = list(current_values)
        
        # Her sütun için
        for ui_column, value in column_data.items():
            # Sütun indeksini bul
            col_idx = None
            
            # Eğer column_map varsa, veri sütun adını al
            data_column = column_map.get(ui_column, ui_column) if column_map else ui_column
            
            # Sütunlar içinde ara
            try:
                col_idx = tree['columns'].index(data_column)
            except ValueError:
                continue
            
            if col_idx is not None and col_idx < len(values_list):
                # Özel format kontrolü
                if data_column in ['divAmount', 'divYield', 'last', 'bid', 'ask', 'high', 'low', 'close', 'spread']:
                    values_list[col_idx] = safe_format_float(value)
                elif data_column == 'change':
                    change_val = safe_float(value)
                    values_list[col_idx] = f"{change_val:.2f}" if change_val is not None else "0.00"
                elif data_column == 'volume':
                    volume = safe_int(value)
                    values_list[col_idx] = f"{volume:,}" if volume else "0"
                else:
                    values_list[col_idx] = value
        
        # Değerleri güncelle
        tree.item(item_id, values=values_list)
        return True
    except Exception as e:
        print(f"Treeview öğesi güncelleme hatası: {e}")
        return False

def get_column_title(tree, column):
    """
    Treeview sütununun başlığını al
    
    Args:
        tree: Treeview widget'ı
        column (str): Sütun adı
        
    Returns:
        str: Sütun başlığı
    """
    try:
        return tree.heading(column)['text']
    except (KeyError, TypeError, tk.TclError):
        return column

def find_top_movers(df, column='change', top_n=15, ascending=False):
    """
    En çok değişenleri bul
    
    Args:
        df (DataFrame): Kaynak veri
        column (str): Değişim sütunu adı
        top_n (int): Kaç öğe alınacak
        ascending (bool): Sıralama yönü (False=azalan, True=artan)
        
    Returns:
        DataFrame: En çok değişenler
    """
    if df is None or df.empty or column not in df.columns:
        return pd.DataFrame()
    
    # NaN değerleri temizle
    clean_df = df.dropna(subset=[column])
    
    # Sırala ve ilk/son N öğeyi al
    sorted_df = clean_df.sort_values(by=column, ascending=ascending)
    
    return sorted_df.head(top_n)

def apply_color_tags(tree, item_id, change_value, zero_threshold=0.01):
    """
    Değişime göre renk etiketlerini uygula
    
    Args:
        tree: Treeview widget'ı
        item_id: Öğe ID'si
        change_value (float): Değişim değeri
        zero_threshold (float): Sıfır kabul edilecek eşik değeri
        
    Returns:
        str: Uygulanan etiket ('green', 'red', 'neutral')
    """
    try:
        change = safe_float(change_value)
        
        # Mevcut etiketleri temizle
        tree.item(item_id, tags=())
        
        # Değişim pozitif ise yeşil, negatif ise kırmızı, sıfır yakınında ise nötr
        if change > zero_threshold:
            tree.item(item_id, tags=('green',))
            return 'green'
        elif change < -zero_threshold:
            tree.item(item_id, tags=('red',))
            return 'red'
        else:
            tree.item(item_id, tags=('neutral',))
            return 'neutral'
    except Exception as e:
        print(f"Renk etiketi uygulama hatası: {e}")
        return 'neutral'

def setup_treeview_tags(tree):
    """
    Treeview'a renk etiketlerini ayarla
    
    Args:
        tree: Treeview widget'ı
    """
    tree.tag_configure('green', foreground='green')
    tree.tag_configure('red', foreground='red')
    tree.tag_configure('neutral', foreground='black')
    tree.tag_configure('selected', background='#DDDDDD')
    tree.tag_configure('highlighted', background='#FFFFBB')

def sort_and_paginate_rows(
    tickers,
    row_for_symbol_fn,
    sort_col_idx=None,
    sort_reverse=False,
    page=0,
    items_per_page=20,
    get_sort_key_fn=None
):
    """
    Tüm tickers için satırları oluştur, istenen sütuna göre sırala ve sayfalama uygula.
    Args:
        tickers (list): Sıralanacak ticker listesi
        row_for_symbol_fn (function): Her ticker için satır oluşturan fonksiyon
        sort_col_idx (int): Sıralama yapılacak sütun index'i
        sort_reverse (bool): Azalan sıralama için True
        page (int): Sayfa numarası (0 tabanlı)
        items_per_page (int): Sayfa başına satır
        get_sort_key_fn (function): Sıralama anahtarı fonksiyonu (opsiyonel)
    Returns:
        (rows, total_pages): Sıralanmış ve sayfalanmış satırlar, toplam sayfa
    """
    rows = [row_for_symbol_fn(sym) for sym in tickers]
    if sort_col_idx is not None:
        if get_sort_key_fn is None:
            def get_sort_key(val):
                if val is None or str(val).strip() in ("N/A", "nan", ""):
                    return float("inf")
                try:
                    return float(str(val).replace(",", ""))
                except Exception:
                    return str(val)
        else:
            get_sort_key = get_sort_key_fn
        rows.sort(key=lambda r: (get_sort_key(r[sort_col_idx]) is None, get_sort_key(r[sort_col_idx])), reverse=sort_reverse)
    total_pages = max(1, (len(rows) - 1) // items_per_page + 1)
    start = page * items_per_page
    end = min(start + items_per_page, len(rows))
    return rows[start:end], total_pages 