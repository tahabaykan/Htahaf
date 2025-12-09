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
        win.geometry("1200x600")
        win.transient(parent)
        win.grab_set()
        
        # Başlık
        title_label = ttk.Label(win, text="IBKR Emirlerim", font=('Arial', 14, 'bold'))
        title_label.pack(pady=10)
        
        # Yenile butonu
        refresh_frame = ttk.Frame(win)
        refresh_frame.pack(fill='x', padx=10, pady=5)
        
        def refresh_orders():
            """Emirleri yenile"""
            try:
                # Tabloyu temizle
                for item in tree.get_children():
                    tree.delete(item)
                
                status_label.config(text="IBKR emirleri yükleniyor...")
                win.update()
                
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
                        price = order.get('price', 0)
                        order_type = order.get('order_type', 'N/A')
                        status = order.get('status', 'N/A')
                        order_id = order.get('order_id', 'N/A')
                        
                        # Fill price'ı nfilled dosyasından al
                        fill_price = "N/A"
                        emir_tipi = "-"
                        if hasattr(parent, 'get_todays_fills_from_nfilled'):
                            fills = parent.get_todays_fills_from_nfilled(symbol)
                            if fills and len(fills) > 0:
                                # Ortalama fill price hesapla
                                total_qty = sum(float(f.get('fill_qty', 0)) for f in fills)
                                total_value = sum(float(f.get('fill_price', 0)) * float(f.get('fill_qty', 0)) for f in fills)
                                if total_qty > 0:
                                    fill_price = f"${(total_value / total_qty):.2f}"
                        
                        # Emir tipini hesapla (pozisyon değişikliğine göre)
                        if hasattr(parent, 'calculate_position_change'):
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
                    if len(values) >= 8:
                        order_id = values[7]  # order_id kolonu
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
                        selected_items.append((item, values[7]))  # (item, order_id)
                
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
        
        # Tablo - Checkbox sistemi ile
        cols = ['select', 'symbol', 'action', 'quantity', 'price', 'order_type', 'status', 'order_id']
        headers = ['Seç', 'Symbol', 'Action', 'Quantity', 'Price', 'Order Type', 'Status', 'Order ID']
        
        tree = ttk.Treeview(win, columns=cols, show='headings', height=20)
        
        # Font boyutunu küçült
        style = ttk.Style()
        style.configure("Treeview", font=('Arial', 8))
        style.configure("Treeview.Heading", font=('Arial', 8, 'bold'))
        
        # Kolon başlıkları ve genişlikleri
        for c, h in zip(cols, headers):
            tree.heading(c, text=h)
            if c == 'select':
                tree.column(c, width=50, anchor='center')
            elif c == 'symbol':
                tree.column(c, width=100, anchor='center')
            elif c == 'action':
                tree.column(c, width=80, anchor='center')
            elif c == 'quantity':
                tree.column(c, width=80, anchor='center')
            elif c == 'price':
                tree.column(c, width=80, anchor='center')
            elif c == 'fill_price':
                tree.column(c, width=100, anchor='center')
            elif c == 'order_type':
                tree.column(c, width=100, anchor='center')
            elif c == 'status':
                tree.column(c, width=100, anchor='center')
            elif c == 'emir_tipi':
                tree.column(c, width=120, anchor='center')
            elif c == 'order_id':
                tree.column(c, width=120, anchor='center')
            else:
                tree.column(c, width=100, anchor='center')
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(win, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack
        tree.pack(side='left', fill='both', expand=True, padx=10, pady=10)
        scrollbar.pack(side='right', fill='y', pady=10)
        
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
                symbol = values[0]
                order_id = values[6]
                
                # Onay al
                if messagebox.askyesno("Emir İptali", 
                                     f"Bu emri iptal etmek istediğinizden emin misiniz?\n\n"
                                     f"Symbol: {symbol}\n"
                                     f"Order ID: {order_id}"):
                    
                    # IBKR'de emri iptal et
                    if hasattr(parent, 'ibkr') and parent.ibkr.is_connected():
                        # IBKR'de emir iptal etme implementasyonu burada olacak
                        # Şimdilik sadece mesaj göster
                        messagebox.showinfo("Bilgi", "IBKR emir iptal etme henüz implement edilmedi!")
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








