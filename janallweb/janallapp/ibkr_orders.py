"""
IBKR Orders - IBKR emirlerini gösteren pencere
"""

import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import os

def show_ibkr_orders_window(parent):
    """IBKR emirlerini gösteren pencere"""
    try:
        # Ana pencere
        win = tk.Toplevel(parent)
        win.title("IBKR Emirlerim")
        win.geometry("1400x700")
        win.transient(parent)
        # grab_set() kaldırıldı - GUI'yi bloklamamak için
        
        # Başlık
        title_label = ttk.Label(win, text="IBKR Emirlerim", font=('Arial', 14, 'bold'))
        title_label.pack(pady=10)
        
        # Notebook (Tab sistemi) - Açık Emirler ve Filled Emirler için
        notebook = ttk.Notebook(win)
        notebook.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Tab 1: Açık Emirler
        open_orders_frame = ttk.Frame(notebook)
        notebook.add(open_orders_frame, text="📋 Açık Emirler")
        
        # Tab 2: Filled Emirler
        filled_orders_frame = ttk.Frame(notebook)
        notebook.add(filled_orders_frame, text="✅ Filled Emirler (Bugün)")
        
        # ==================== AÇIK EMİRLER SEKME ====================
        # Yenile butonu (Açık Emirler için)
        refresh_frame = ttk.Frame(open_orders_frame)
        refresh_frame.pack(fill='x', padx=10, pady=5)
        
        def refresh_orders():
            """Emirleri yenile"""
            try:
                # Tabloyu temizle
                for item in tree.get_children():
                    tree.delete(item)
                
                    status_label.config(text="IBKR emirleri yükleniyor...")
                open_orders_frame.update()
                
                # IBKR'den emirleri çek
                if hasattr(parent, 'ibkr') and parent.ibkr.is_connected():
                    orders = parent.ibkr.get_orders_direct()
                    
                    if not orders:
                        status_label.config(text="IBKR'de aktif emir bulunamadı")
                        return
                    
                    # Emirleri tabloya ekle
                    for order in orders:
                        symbol = order.get('symbol', 'N/A')
                        action = order.get('action', 'N/A')
                        quantity = order.get('quantity', 0)
                        # Emir fiyatı: önce 'price', yoksa 'limit_price' kullan
                        price = order.get('price', 0) or order.get('limit_price', 0)
                        order_type = order.get('order_type', 'N/A')
                        status = order.get('status', 'N/A')
                        order_id = order.get('order_id', 'N/A')
                        
                        # Fill price'ı IBKR'den direkt al (önce IBKR'den, yoksa nfilled'den)
                        fill_price = "N/A"
                        # IBKR'den avg_fill_price veya last_fill_price al
                        avg_fill_price = order.get('avg_fill_price', 0) or 0.0
                        last_fill_price = order.get('last_fill_price', 0) or 0.0
                        
                        if avg_fill_price > 0:
                            # Ortalama fill price varsa onu kullan
                            fill_price = f"${avg_fill_price:.2f}"
                        elif last_fill_price > 0:
                            # Son fill price varsa onu kullan
                            fill_price = f"${last_fill_price:.2f}"
                        else:
                            # IBKR'den fill price yoksa nfilled dosyasından al (fallback)
                            if hasattr(parent, 'get_todays_fills_from_nfilled'):
                                fills = parent.get_todays_fills_from_nfilled(symbol)
                                if fills and len(fills) > 0:
                                    # Ortalama fill price hesapla
                                    total_qty = sum(float(f.get('fill_qty', 0)) for f in fills)
                                    total_value = sum(float(f.get('fill_price', 0)) * float(f.get('fill_qty', 0)) for f in fills)
                                    if total_qty > 0:
                                        fill_price = f"${(total_value / total_qty):.2f}"
                        
                        emir_tipi = "-"
                        
                        # Önce RevOrder kontrolü yap
                        if order.get('revorder', False) or order.get('emir_tipi') == 'RevOrder':
                            emir_tipi = 'RevOrder'
                        # Emir tipini hesapla (pozisyon değişikliğine göre)
                        elif hasattr(parent, 'calculate_position_change'):
                            # Befday qty ve current qty'yi al
                            befday_qty = 0
                            current_qty = 0
                            
                            # Befday qty'yi al
                            if hasattr(parent, 'load_bef_position'):
                                befday_qty = parent.load_bef_position(symbol)
                            
                            # Current qty'yi al (IBKR pozisyonlarından)
                            if hasattr(parent, 'ibkr') and parent.ibkr:
                                positions = parent.ibkr.get_positions_direct()
                                for pos in positions:
                                    if pos.get('symbol') == symbol:
                                        current_qty = pos.get('qty', 0)
                                        break
                            
                            # Todays qty chg hesapla
                            todays_qty_chg = current_qty - befday_qty
                            
                            # Emir tipini belirle
                            emir_tipi = parent.calculate_position_change(befday_qty, todays_qty_chg)
                        
                        # Tabloya ekle - Checkbox sistemi ile
                        tree.insert('', 'end', values=[
                            '☐',  # Seç checkbox'ı (boş)
                            symbol,
                            action,
                            f"{quantity:.0f}",
                            f"${price:.2f}" if price > 0 else "N/A",
                            fill_price,  # Fill Price
                            order_type,
                            status,
                            emir_tipi,  # Emir Tipi
                            order_id
                        ])
                    
                    status_label.config(text=f"{len(orders)} IBKR emri bulundu")
                else:
                    status_label.config(text="IBKR bağlantısı yok")
                    messagebox.showwarning("Uyarı", "IBKR bağlantısı yok!\nÖnce IBKR MOD'a geçin ve bağlantıyı kurun.")
                    
            except Exception as e:
                status_label.config(text=f"Emir yükleme hatası: {e}")
                print(f"[IBKR ORDERS] ❌ Emir yükleme hatası: {e}")
                messagebox.showerror("Hata", f"IBKR emirleri yüklenirken hata: {e}")
        
        ttk.Button(refresh_frame, text="Yenile", command=refresh_orders).pack(side='left')
        
        def select_all_orders():
            """Tüm IBKR emirlerini seç - Checkbox sistemi ile"""
            try:
                for item in tree.get_children():
                    values = list(tree.item(item)['values'])
                    values[0] = '☑'  # Seçili yap
                    tree.item(item, values=values)
                
                print(f"[IBKR_ORDERS] OK Tum IBKR emirler secildi")
                # messagebox.showinfo("Başarılı", "Tüm IBKR emirler seçildi!")  # Uyarı ekranı kaldırıldı
                
            except Exception as e:
                print(f"[IBKR_ORDERS] ❌ Tümünü seçme hatası: {e}")
                messagebox.showerror("Hata", f"Tümünü seçme hatası: {e}")
        
        ttk.Button(refresh_frame, text="Tümünü Seç", command=select_all_orders).pack(side='left', padx=5)
        
        def cancel_all_orders():
            """TÜM emirleri iptal et - Seçim yapmadan direkt tümünü iptal"""
            try:
                # Tüm emirleri al
                all_items = []
                for item in tree.get_children():
                    values = tree.item(item)['values']
                    if len(values) >= 10:
                        order_id = values[9]  # order_id kolonu (Index 9)
                        all_items.append((item, order_id))
                
                if not all_items:
                    messagebox.showwarning("Uyarı", "İptal edilecek emir bulunamadı!")
                    return
                
                # Onay al
                if not messagebox.askyesno("Onay", f"⚠️ DİKKAT: TÜM {len(all_items)} emir iptal edilecek!\n\nDevam etmek istediğinizden emin misiniz?"):
                    return
                
                # IBKR'den TÜM emirleri iptal et - ÖNCE Native client'ı kullan
                ibkr_client = None
                
                # ÖNCE IBKR Native client'ı kontrol et (daha güvenilir)
                if hasattr(parent, 'mode_manager') and parent.mode_manager:
                    if hasattr(parent.mode_manager, 'ibkr_native_client') and parent.mode_manager.ibkr_native_client:
                        native_client = parent.mode_manager.ibkr_native_client
                        if native_client.is_connected():
                            ibkr_client = native_client
                            print(f"[IBKR_ORDERS] ✅ IBKR Native client kullanılıyor (TÜMÜNÜ İPTAL)")
                        else:
                            print(f"[IBKR_ORDERS] ⚠️ Native client bağlı değil, bağlanmayı deniyor...")
                            try:
                                if hasattr(native_client, 'connect_to_ibkr'):
                                    if native_client.connect_to_ibkr():
                                        ibkr_client = native_client
                                        print(f"[IBKR_ORDERS] ✅ IBKR Native client bağlandı ve kullanılıyor (TÜMÜNÜ İPTAL)")
                            except Exception as e:
                                print(f"[IBKR_ORDERS] ⚠️ Native client bağlanma hatası: {e}")
                
                # Fallback: ib_insync client kullan
                if not ibkr_client and hasattr(parent, 'ibkr') and parent.ibkr.is_connected():
                    ibkr_client = parent.ibkr
                    print(f"[IBKR_ORDERS] 🔄 IBKR ib_insync client kullanılıyor (TÜMÜNÜ İPTAL - fallback)")
                
                if ibkr_client and ibkr_client.is_connected():
                    print(f"[IBKR_ORDERS] 🗑️ TÜM {len(all_items)} emir aynı anda iptal ediliyor...")
                    
                    # Tüm emirleri HIZLICA iptal et - bekleme yok, hepsini gönder
                    import time
                    cancel_results = []
                    
                    for item, order_id in all_items:
                        try:
                            # IBKR Native API'de cancelOrder direkt çağrılır (asenkron)
                            if hasattr(ibkr_client, 'cancelOrder'):
                                # Native client - direkt cancelOrder çağrısı
                                order_id_int = int(order_id)
                                ibkr_client.cancelOrder(order_id_int)
                                cancel_results.append((order_id, True, None))
                                print(f"[IBKR_ORDERS] 📤 İptal isteği gönderildi: {order_id}")
                            else:
                                # ib_insync client - cancel_order fonksiyonu
                                success = ibkr_client.cancel_order(order_id)
                                cancel_results.append((order_id, success, None))
                                if success:
                                    print(f"[IBKR_ORDERS] 📤 İptal isteği gönderildi: {order_id}")
                                else:
                                    print(f"[IBKR_ORDERS] ❌ İptal isteği başarısız: {order_id}")
                        except Exception as e:
                            cancel_results.append((order_id, False, str(e)))
                            print(f"[IBKR_ORDERS] ❌ İptal hatası ({order_id}): {e}")
                    
                    # Tüm iptal istekleri gönderildi, kısa bir süre bekle ve kontrol et
                    print(f"[IBKR_ORDERS] ⏳ Tüm iptal istekleri gönderildi, sonuçlar kontrol ediliyor...")
                    time.sleep(2.0)  # Tüm iptal işlemlerinin tamamlanması için kısa bekleme
                    
                    # Sonuçları kontrol et
                    success_count = sum(1 for _, success, _ in cancel_results if success)
                    error_count = len(cancel_results) - success_count
                    
                    print(f"[IBKR_ORDERS] 📊 İptal sonucu: ✅ {success_count} başarılı, ❌ {error_count} hata")
                    
                    if success_count > 0:
                        messagebox.showinfo("Sonuç", f"✅ {success_count} emir başarıyla iptal edildi.\n❌ {error_count} emir iptal edilemedi.")
                    else:
                        messagebox.showerror("Hata", f"Hiç emir iptal edilemedi! ({error_count} hata)")
                    
                    refresh_orders()  # Tabloyu yenile
                else:
                    messagebox.showerror("Hata", "IBKR bağlantısı yok!")
                    
            except Exception as e:
                print(f"[IBKR_ORDERS] ❌ TÜMÜNÜ İPTAL hatası: {e}")
                import traceback
                traceback.print_exc()
                messagebox.showerror("Hata", f"TÜMÜNÜ İPTAL hatası: {e}")
        
        # TÜMÜNÜ İPTAL ET butonu - Kırmızı renk için style oluştur
        style = ttk.Style()
        try:
            style.configure('Danger.TButton', foreground='red', font=('Arial', 9, 'bold'))
        except:
            pass  # Style oluşturulamazsa normal buton kullan
        
        cancel_all_btn = ttk.Button(refresh_frame, text="🗑️ TÜMÜNÜ İPTAL ET", command=cancel_all_orders)
        try:
            cancel_all_btn.configure(style='Danger.TButton')
        except:
            pass  # Style yoksa normal buton kullan
        cancel_all_btn.pack(side='left', padx=5)
        
        def cancel_selected_orders():
            """Seçili emirleri iptal et"""
            try:
                selected_items = []
                for item in tree.get_children():
                    values = tree.item(item)['values']
                    if values[0] == '☑':  # Seçili
                        if len(values) >= 10:
                            selected_items.append((item, values[9]))  # (item, order_id)
                
                if not selected_items:
                    messagebox.showwarning("Uyarı", "Hiç emir seçilmedi!")
                    return
                
                # Onay al
                if not messagebox.askyesno("Onay", f"{len(selected_items)} emir iptal edilecek. Devam edilsin mi?"):
                    return
                
                # IBKR'den emirleri iptal et - ÖNCE Native client'ı kullan
                ibkr_client = None
                
                # ÖNCE IBKR Native client'ı kontrol et (daha güvenilir)
                if hasattr(parent, 'mode_manager') and parent.mode_manager:
                    if hasattr(parent.mode_manager, 'ibkr_native_client') and parent.mode_manager.ibkr_native_client:
                        native_client = parent.mode_manager.ibkr_native_client
                        if native_client.is_connected():
                            ibkr_client = native_client
                            print(f"[IBKR_ORDERS] ✅ IBKR Native client kullanılıyor (daha güvenilir)")
                        else:
                            print(f"[IBKR_ORDERS] ⚠️ Native client bağlı değil, bağlanmayı deniyor...")
                            try:
                                if hasattr(native_client, 'connect_to_ibkr'):
                                    if native_client.connect_to_ibkr():
                                        ibkr_client = native_client
                                        print(f"[IBKR_ORDERS] ✅ IBKR Native client bağlandı ve kullanılıyor")
                            except Exception as e:
                                print(f"[IBKR_ORDERS] ⚠️ Native client bağlanma hatası: {e}")
                
                # Fallback: ib_insync client kullan
                if not ibkr_client and hasattr(parent, 'ibkr') and parent.ibkr.is_connected():
                    ibkr_client = parent.ibkr
                    print(f"[IBKR_ORDERS] 🔄 IBKR ib_insync client kullanılıyor (fallback)")
                
                if ibkr_client and ibkr_client.is_connected():
                    print(f"[IBKR_ORDERS] 🗑️ {len(selected_items)} seçili emir aynı anda iptal ediliyor...")
                    
                    # Tüm emirleri HIZLICA iptal et - bekleme yok, hepsini gönder
                    import time
                    cancel_results = []
                    
                    for item, order_id in selected_items:
                        try:
                            # IBKR Native API'de cancelOrder direkt çağrılır (asenkron)
                            if hasattr(ibkr_client, 'cancelOrder'):
                                # Native client - direkt cancelOrder çağrısı
                                order_id_int = int(order_id)
                                ibkr_client.cancelOrder(order_id_int)
                                cancel_results.append((order_id, True, None))
                                print(f"[IBKR_ORDERS] 📤 İptal isteği gönderildi: {order_id}")
                            else:
                                # ib_insync client - cancel_order fonksiyonu
                                success = ibkr_client.cancel_order(order_id)
                                cancel_results.append((order_id, success, None))
                                if success:
                                    print(f"[IBKR_ORDERS] 📤 İptal isteği gönderildi: {order_id}")
                                else:
                                    print(f"[IBKR_ORDERS] ❌ İptal isteği başarısız: {order_id}")
                        except Exception as e:
                            cancel_results.append((order_id, False, str(e)))
                            print(f"[IBKR_ORDERS] ❌ İptal hatası ({order_id}): {e}")
                            import traceback
                            traceback.print_exc()
                    
                    # Tüm iptal istekleri gönderildi, kısa bir süre bekle ve kontrol et
                    print(f"[IBKR_ORDERS] ⏳ Tüm iptal istekleri gönderildi, sonuçlar kontrol ediliyor...")
                    time.sleep(1.5)  # Tüm iptal işlemlerinin tamamlanması için kısa bekleme
                    
                    # Sonuçları kontrol et
                    success_count = sum(1 for _, success, _ in cancel_results if success)
                    error_count = len(cancel_results) - success_count
                    
                    print(f"[IBKR_ORDERS] 📊 İptal sonucu: ✅ {success_count} başarılı, ❌ {error_count} hata")
                    
                    if success_count > 0:
                        messagebox.showinfo("Sonuç", f"✅ {success_count} emir başarıyla iptal edildi.\n❌ {error_count} emir iptal edilemedi.")
                    else:
                        messagebox.showerror("Hata", f"Hiç emir iptal edilemedi! ({error_count} hata)")
                    
                    refresh_orders()  # Tabloyu yenile
                else:
                    messagebox.showerror("Hata", "IBKR bağlantısı yok!")
                    
            except Exception as e:
                print(f"[IBKR_ORDERS] ❌ Toplu iptal hatası: {e}")
                messagebox.showerror("Hata", f"Toplu iptal hatası: {e}")
        
        ttk.Button(refresh_frame, text="Seçili Emirleri İptal Et", command=cancel_selected_orders).pack(side='left', padx=5)
        
        # Tablo - Checkbox sistemi ile (Açık Emirler için)
        cols = ['select', 'symbol', 'action', 'quantity', 'price', 'fill_price', 'order_type', 'status', 'emir_tipi', 'order_id']
        headers = ['Seç', 'Symbol', 'Action', 'Quantity', 'Price', 'Fill Price', 'Order Type', 'Status', 'Emir Tipi', 'Order ID']
        
        tree = ttk.Treeview(open_orders_frame, columns=cols, show='headings', height=20)
        
        # Font boyutunu küçült
        style = ttk.Style()
        style.configure("Treeview", font=('Arial', 8))
        style.configure("Treeview.Heading", font=('Arial', 8, 'bold'))
        
        # Kolon başlıkları ve genişlikleri
        for c, h in zip(cols, headers):
            tree.heading(c, text=h)
            if c == 'select':
                tree.column(c, width=40, anchor='center')
            elif c == 'symbol':
                tree.column(c, width=80, anchor='center')
            elif c == 'action':
                tree.column(c, width=60, anchor='center')
            elif c == 'quantity':
                tree.column(c, width=70, anchor='center')
            elif c == 'price':
                tree.column(c, width=70, anchor='center')
            elif c == 'fill_price':
                tree.column(c, width=70, anchor='center')
            elif c == 'order_type':
                tree.column(c, width=80, anchor='center')
            elif c == 'status':
                tree.column(c, width=90, anchor='center')
            elif c == 'emir_tipi':
                tree.column(c, width=100, anchor='center')
            elif c == 'order_id':
                tree.column(c, width=100, anchor='center')
            else:
                tree.column(c, width=80, anchor='center')
        
        # Scrollbar (Açık Emirler için)
        scrollbar = ttk.Scrollbar(open_orders_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack (Açık Emirler için)
        tree.pack(side='left', fill='both', expand=True, padx=10, pady=10)
        scrollbar.pack(side='right', fill='y', pady=10)
        
        # Status label (Açık Emirler için)
        status_label = ttk.Label(open_orders_frame, text="IBKR emirleri yükleniyor...")
        status_label.pack(pady=5)
        
        # ==================== FILLED EMİRLER SEKME ====================
        # Yenile butonu (Filled Emirler için)
        filled_refresh_frame = ttk.Frame(filled_orders_frame)
        filled_refresh_frame.pack(fill='x', padx=10, pady=5)
        
        def refresh_filled_orders():
            """Filled emirleri yenile"""
            try:
                # Tabloyu temizle
                for item in filled_tree.get_children():
                    filled_tree.delete(item)
                
                filled_status_label.config(text="Filled emirler yükleniyor...")
                win.update()
                
                # IBKR Native Client'dan bugünkü filled emirleri çek
                filled_orders = []
                
                # Önce IBKR Native client'ı kontrol et
                if hasattr(parent, 'mode_manager') and parent.mode_manager:
                    if hasattr(parent.mode_manager, 'ibkr_native_client') and parent.mode_manager.ibkr_native_client:
                        native_client = parent.mode_manager.ibkr_native_client
                        if native_client.is_connected():
                            filled_orders = native_client.get_todays_filled_orders()
                            print(f"[IBKR_ORDERS] ✅ {len(filled_orders)} filled emir IBKR Native'dan alındı")
                        else:
                            filled_status_label.config(text="IBKR Native bağlantısı yok")
                            return
                    else:
                        filled_status_label.config(text="IBKR Native client bulunamadı")
                        return
                else:
                    filled_status_label.config(text="Mode Manager bulunamadı")
                    return
                
                if not filled_orders:
                    filled_status_label.config(text="Bugünkü filled emir bulunamadı")
                    return
                
                # Filled emirleri tabloya ekle
                for fill in filled_orders:
                    symbol = fill.get('symbol', 'N/A')
                    action = fill.get('action', 'N/A')
                    fill_qty = fill.get('fill_qty', 0) or fill.get('qty', 0)
                    fill_price = fill.get('fill_price', 0) or fill.get('price', 0)
                    fill_time = fill.get('fill_time', 'N/A') or fill.get('time', 'N/A')
                    order_id = fill.get('order_id', 'N/A')
                    exec_id = fill.get('exec_id', 'N/A')
                    
                    filled_tree.insert('', 'end', values=[
                        symbol,
                        action,
                        f"{fill_qty:.0f}",
                        f"${fill_price:.2f}" if fill_price > 0 else "N/A",
                        fill_time,
                        order_id,
                        exec_id
                    ])
                
                filled_status_label.config(text=f"{len(filled_orders)} filled emir bulundu")
                
            except Exception as e:
                filled_status_label.config(text=f"Filled emir yükleme hatası: {e}")
                print(f"[IBKR_ORDERS] ❌ Filled emir yükleme hatası: {e}")
                import traceback
                traceback.print_exc()
        
        ttk.Button(filled_refresh_frame, text="Yenile", command=refresh_filled_orders).pack(side='left')
        
        # Filled Emirler Tablosu
        filled_cols = ['symbol', 'action', 'quantity', 'fill_price', 'fill_time', 'order_id', 'exec_id']
        filled_headers = ['Symbol', 'Action', 'Quantity', 'Fill Price', 'Fill Time', 'Order ID', 'Exec ID']
        
        filled_tree = ttk.Treeview(filled_orders_frame, columns=filled_cols, show='headings', height=25)
        
        # Font boyutunu küçült
        filled_style = ttk.Style()
        filled_style.configure("FilledTreeview", font=('Arial', 8))
        filled_style.configure("FilledTreeview.Heading", font=('Arial', 8, 'bold'))
        
        # Kolon başlıkları ve genişlikleri
        for c, h in zip(filled_cols, filled_headers):
            filled_tree.heading(c, text=h)
            if c == 'symbol':
                filled_tree.column(c, width=100, anchor='center')
            elif c == 'action':
                filled_tree.column(c, width=70, anchor='center')
            elif c == 'quantity':
                filled_tree.column(c, width=80, anchor='center')
            elif c == 'fill_price':
                filled_tree.column(c, width=90, anchor='center')
            elif c == 'fill_time':
                filled_tree.column(c, width=150, anchor='center')
            elif c == 'order_id':
                filled_tree.column(c, width=100, anchor='center')
            elif c == 'exec_id':
                filled_tree.column(c, width=120, anchor='center')
            else:
                filled_tree.column(c, width=80, anchor='center')
        
        # Scrollbar (Filled Emirler için)
        filled_scrollbar = ttk.Scrollbar(filled_orders_frame, orient="vertical", command=filled_tree.yview)
        filled_tree.configure(yscrollcommand=filled_scrollbar.set)
        
        # Pack (Filled Emirler için)
        filled_tree.pack(side='left', fill='both', expand=True, padx=10, pady=10)
        filled_scrollbar.pack(side='right', fill='y', pady=10)
        
        # Status label (Filled Emirler için)
        filled_status_label = ttk.Label(filled_orders_frame, text="Filled emirler yükleniyor...")
        filled_status_label.pack(pady=5)
        
        # İlk yükleme - Açık emirleri ve Filled emirleri yükle
        refresh_orders()  # Açık emirleri yükle
        refresh_filled_orders()  # Filled emirleri yükle
        
        # Checkbox tıklama işlevi
        def on_item_click(event):
            """Checkbox'a tıklandığında çağrılır"""
            try:
                item = tree.selection()[0] if tree.selection() else None
                if item:
                    values = list(tree.item(item)['values'])
                    if values[0] == '☐':  # Boş checkbox
                        values[0] = '☑'  # Dolu checkbox
                    else:  # Dolu checkbox
                        values[0] = '☐'  # Boş checkbox
                    tree.item(item, values=values)
            except Exception as e:
                print(f"[IBKR_ORDERS] Checkbox tıklama hatası: {e}")
        
        tree.bind('<Button-1>', on_item_click)
        
        # Alt panel - Bilgi
        info_frame = ttk.Frame(win)
        info_frame.pack(fill='x', padx=10, pady=5)
        
        status_label = ttk.Label(info_frame, text="IBKR emirleri yükleniyor...")
        status_label.pack(side='left')
        
        # İptal butonu
        def cancel_order():
            """Seçili emri iptal et"""
            try:
                selected_item = tree.selection()
                if not selected_item:
                    messagebox.showwarning("Uyarı", "Önce iptal edilecek emri seçin!")
                    return
                
                # Seçili emrin bilgilerini al
                values = tree.item(selected_item[0])['values']
                symbol = values[1]  # Index 1: Symbol (Değişti)
                order_id = values[9]  # Index 9: Order ID (Değişti)
                
                # Onay al
                if messagebox.askyesno("Emir İptali", 
                                     f"Bu emri iptal etmek istediğinizden emin misiniz?\n\n"
                                     f"Symbol: {symbol}\n"
                                     f"Order ID: {order_id}"):
                    
                    # IBKR'de emri iptal et
                    ibkr_client = None
                    
                    # ÖNCE IBKR Native client'ı kontrol et
                    if hasattr(parent, 'mode_manager') and parent.mode_manager:
                        if hasattr(parent.mode_manager, 'ibkr_native_client') and parent.mode_manager.ibkr_native_client:
                            native_client = parent.mode_manager.ibkr_native_client
                            if native_client.is_connected():
                                ibkr_client = native_client
                                print(f"[IBKR_ORDERS] ✅ IBKR Native client kullanılıyor")
                    
                    # Fallback: ib_insync client
                    if not ibkr_client and hasattr(parent, 'ibkr') and parent.ibkr.is_connected():
                        ibkr_client = parent.ibkr
                        print(f"[IBKR_ORDERS] 🔄 IBKR ib_insync client kullanılıyor (fallback)")
                    
                    if ibkr_client and ibkr_client.is_connected():
                        try:
                            # IBKR Native API
                            if hasattr(ibkr_client, 'cancelOrder'):
                                order_id_int = int(order_id)
                                ibkr_client.cancelOrder(order_id_int)
                                print(f"[IBKR_ORDERS] 📤 İptal isteği gönderildi: {order_id}")
                                messagebox.showinfo("Bilgi", "İptal isteği gönderildi.")
                            else:
                                # ib_insync client
                                success = ibkr_client.cancel_order(order_id)
                                if success:
                                    print(f"[IBKR_ORDERS] 📤 İptal isteği gönderildi: {order_id}")
                                    messagebox.showinfo("Bilgi", "İptal isteği gönderildi.")
                                else:
                                    print(f"[IBKR_ORDERS] ❌ İptal isteği başarısız: {order_id}")
                                    messagebox.showerror("Hata", "İptal isteği başarısız oldu!")
                            
                            # Yenile
                            win.after(1000, refresh_orders)
                            
                        except Exception as e:
                            print(f"[IBKR ORDERS] ❌ Emir iptal hatası: {e}")
                            messagebox.showerror("Hata", f"Emir iptal hatası: {e}")
                    else:
                        messagebox.showerror("Hata", "IBKR bağlantısı yok!")
                        
            except Exception as e:
                print(f"[IBKR ORDERS] ❌ Emir iptal hatası: {e}")
                messagebox.showerror("Hata", f"Emir iptal hatası: {e}")
        
        ttk.Button(info_frame, text="Emri İptal Et", command=cancel_order).pack(side='right')
        
        # İlk yükleme
        refresh_orders()
        
        # Otomatik yenileme - 5 saniyede bir
        def auto_refresh():
            """Otomatik yenileme fonksiyonu"""
            try:
                if win.winfo_exists():  # Pencere hala açık mı?
                    refresh_orders()
                    win.after(8000, auto_refresh)  # 8 saniye sonra tekrar çağır
                else:
                    print("[IBKR_ORDERS] Pencere kapatıldı, otomatik yenileme durduruldu")
            except Exception as e:
                print(f"[IBKR_ORDERS] Otomatik yenileme hatası: {e}")
        
        # Otomatik yenilemeyi başlat
        win.after(8000, auto_refresh)  # 8 saniye sonra başlat
        
    except Exception as e:
        print(f"[IBKR ORDERS] ❌ Pencere açma hatası: {e}")
        messagebox.showerror("Hata", f"IBKR emirler penceresi açılırken hata: {e}")








