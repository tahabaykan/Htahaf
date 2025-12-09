"""
IBKR Positions module - IBKR pozisyon görüntüleme

!!! ÖNEMLİ DOSYA YOLU UYARISI !!!
=================================
BÜTÜN CSV OKUMA VE CSV KAYDETME İŞLEMLERİ StockTracker DİZİNİNE YAPILMALI!!
StockTracker/janall/ dizinine YAPILMAMALI!!!
KARIŞASAYI ÖNLEMEK İÇİN BU KURALA MUTLAKA UYULACAK!

Bu modül IBKR pozisyonlarını gösterir
=================================
"""

import tkinter as tk
from tkinter import ttk
import pandas as pd

def show_ibkr_positions_window(parent, get_last):
    """IBKR'den pozisyonları çek ve göster"""
    win = tk.Toplevel(parent)
    win.title("Pozisyonlarım - IBKR")
    win.geometry("900x400")
    
    # IBKR client'ı al
    ibkr_client = None
    try:
        # Parent'tan mode manager'ı al
        if hasattr(parent, 'mode_manager'):
            mode_manager = parent.mode_manager
            # Native IBKR client'i kullan (avgCost bilgisi için)
            ibkr_client = mode_manager.ibkr_native_client
            if not ibkr_client or not ibkr_client.is_connected():
                # Fallback: ib_insync client
                ibkr_client = mode_manager.ibkr_client
                print("[IBKR_POSITIONS] ⚠️ Native client bağlı değil, ib_insync kullanılıyor")
            else:
                print("[IBKR_POSITIONS] ✅ Native IBKR client kullanılıyor")
        else:
            print("[IBKR_POSITIONS] ❌ Mode manager bulunamadı")
            return
    except Exception as e:
        print(f"[IBKR_POSITIONS] ❌ Mode manager hatası: {e}")
        return
    
    if not ibkr_client:
        print("[IBKR_POSITIONS] ❌ IBKR client bulunamadı")
        return
    
    cols = ['symbol', 'qty', 'avg_cost', 'current_price', 'pnl_vs_cost', 'avg_adv', 'maxalw', 'smi', 'final_fb', 'final_sfs']
    headers = ['Symbol', 'Qty', 'Avg Cost', 'Current', 'PnL', 'AVG_ADV', 'MAXALW', 'SMI', 'Final FB', 'Final SFS']
    tree = ttk.Treeview(win, columns=cols, show='headings', height=15)
    
    for c, h in zip(cols, headers):
        tree.heading(c, text=h)
        tree.column(c, width=100, anchor='center')
    
    tree.pack(fill='both', expand=True)
    
    # Sıralama durumu
    sort_column = None
    sort_reverse = False
    
    def sort_by_column(column_index):
        """Kolon'a göre sırala"""
        try:
            nonlocal sort_column, sort_reverse
            
            # Kolon adını al
            col_name = cols[column_index]
            
            # Aynı kolona tekrar tıklandıysa sıralama yönünü değiştir
            if sort_column == col_name:
                sort_reverse = not sort_reverse
            else:
                sort_column = col_name
                sort_reverse = False
            
            print(f"[IBKR_POSITIONS] 🔄 {col_name} kolonuna göre sıralanıyor... {'Azalan' if sort_reverse else 'Artan'}")
            
            # Mevcut verileri al
            items = []
            for item in tree.get_children():
                values = tree.item(item)['values']
                items.append(values)
            
            # Sırala
            if col_name in ['qty', 'avg_cost', 'current_price', 'pnl_vs_cost', 'avg_adv', 'maxalw']:
                # Sayısal kolonlar
                items.sort(key=lambda x: float(str(x[column_index]).replace('$', '').replace(',', '')) if x[column_index] and str(x[column_index]) != 'N/A' else 0, reverse=sort_reverse)
            elif col_name in ['smi', 'final_fb', 'final_sfs']:
                # Skor kolonları
                items.sort(key=lambda x: float(x[column_index]) if x[column_index] and str(x[column_index]) != 'N/A' else 0, reverse=sort_reverse)
            else:
                # Metin kolonları
                items.sort(key=lambda x: str(x[column_index]) if x[column_index] else '', reverse=sort_reverse)
            
            # Tabloyu temizle ve sıralanmış verileri ekle
            for item in tree.get_children():
                tree.delete(item)
            
            for values in items:
                tree.insert('', 'end', values=values)
            
            print(f"[IBKR_POSITIONS] ✅ Sıralama tamamlandı")
            
        except Exception as e:
            print(f"[IBKR_POSITIONS] ❌ Sıralama hatası: {e}")
    
    # Kolon başlıklarına tıklama olayları ekle
    for i, col in enumerate(cols):
        tree.heading(col, text=headers[i], command=lambda idx=i: sort_by_column(idx))
    
    def get_avg_adv_from_csv(symbol):
        """CSV'den AVG_ADV değerini al"""
        try:
            # CSV dosyalarından AVG_ADV değerini bul
            import glob
            
            # Tüm ssfinek CSV dosyalarını bul
            csv_files = glob.glob('ssfinek*.csv')
            
            for csv_file in csv_files:
                try:
                    # Dosyayı oku
                    df = pd.read_csv(csv_file, encoding='utf-8-sig')
                    
                    # PREF IBKR ve AVG_ADV kolonları var mı kontrol et
                    if 'PREF IBKR' in df.columns and 'AVG_ADV' in df.columns:
                        # Symbol'ü bul
                        row = df[df['PREF IBKR'] == symbol]
                        if not row.empty:
                            avg_adv = row['AVG_ADV'].iloc[0]
                            if pd.notna(avg_adv) and avg_adv != 'N/A':
                                return float(avg_adv)
                except Exception as e:
                    continue
            
            return 0.0
        except:
            return 0.0
    
    def get_smi_from_csv(symbol):
        """CSV'den SMI değerini al"""
        try:
            # CSV dosyalarından SMI değerini bul
            import glob
            
            # Tüm ssfinek CSV dosyalarını bul
            csv_files = glob.glob('ssfinek*.csv')
            
            for csv_file in csv_files:
                try:
                    # Dosyayı oku
                    df = pd.read_csv(csv_file, encoding='utf-8-sig')
                    
                    # PREF IBKR ve SMI kolonları var mı kontrol et
                    if 'PREF IBKR' in df.columns and 'SMI' in df.columns:
                        # Symbol'ü bul
                        row = df[df['PREF IBKR'] == symbol]
                        if not row.empty:
                            smi = row['SMI'].iloc[0]
                            if pd.notna(smi) and smi != 'N/A':
                                return float(smi)
                except Exception as e:
                    continue
            
            return 0.0
        except:
            return 0.0

    def get_final_fb_from_csv(symbol):
        """DataFrame'den Final FB skorunu al"""
        try:
            # Parent'tan DataFrame'i al
            if hasattr(parent, 'df') and not parent.df.empty:
                # PREF IBKR kolonunda symbol'ü ara
                row = parent.df[parent.df['PREF IBKR'] == symbol]
                if not row.empty:
                    # Önce DataFrame'den Final_FB_skor kolonunu kontrol et
                    if 'Final_FB_skor' in parent.df.columns:
                        value = row['Final_FB_skor'].iloc[0]
                        if pd.notna(value) and value != 'N/A':
                            return float(value)
                    
                    # DataFrame'de yoksa hesapla
                    if hasattr(parent, 'calculate_scores') and hasattr(parent, 'mode_manager'):
                        # Market data al (her zaman Hammer Pro'dan)
                        market_data = parent.mode_manager.get_market_data(symbol)
                        if market_data:
                            bid_raw = float(market_data.get('bid', 0))
                            ask_raw = float(market_data.get('ask', 0))
                            last_raw = float(market_data.get('last', 0))
                            prev_close = float(market_data.get('prevClose', 0))
                            
                            # Benchmark değişimini hesapla
                            benchmark_chg = parent.get_benchmark_change_for_ticker(symbol)
                            
                            # Skorları hesapla
                            scores = parent.calculate_scores(symbol, row.iloc[0], bid_raw, ask_raw, last_raw, prev_close, benchmark_chg)
                            
                            if scores and 'Final_FB_skor' in scores:
                                return float(scores['Final_FB_skor'])
            
            return 0.0
        except:
            return 0.0

    def get_final_sfs_from_csv(symbol):
        """DataFrame'den Final SFS skorunu al"""
        try:
            # Parent'tan DataFrame'i al
            if hasattr(parent, 'df') and not parent.df.empty:
                # PREF IBKR kolonunda symbol'ü ara
                row = parent.df[parent.df['PREF IBKR'] == symbol]
                if not row.empty:
                    # Önce DataFrame'den Final_SFS_skor kolonunu kontrol et
                    if 'Final_SFS_skor' in parent.df.columns:
                        value = row['Final_SFS_skor'].iloc[0]
                        if pd.notna(value) and value != 'N/A':
                            return float(value)
                    
                    # DataFrame'de yoksa hesapla
                    if hasattr(parent, 'calculate_scores') and hasattr(parent, 'mode_manager'):
                        # Market data al (her zaman Hammer Pro'dan)
                        market_data = parent.mode_manager.get_market_data(symbol)
                        if market_data:
                            bid_raw = float(market_data.get('bid', 0))
                            ask_raw = float(market_data.get('ask', 0))
                            last_raw = float(market_data.get('last', 0))
                            prev_close = float(market_data.get('prevClose', 0))
                            
                            # Benchmark değişimini hesapla
                            benchmark_chg = parent.get_benchmark_change_for_ticker(symbol)
                            
                            # Skorları hesapla
                            scores = parent.calculate_scores(symbol, row.iloc[0], bid_raw, ask_raw, last_raw, prev_close, benchmark_chg)
                            
                            if scores and 'Final_SFS_skor' in scores:
                                return float(scores['Final_SFS_skor'])
            
            return 0.0
        except:
            return 0.0
    
    def do_refresh():
        """IBKR'den pozisyonları çek ve tabloya yükle"""
        # Tabloyu temizle
        for item in tree.get_children():
            tree.delete(item)
        
        try:
            print("[IBKR_POSITIONS] 🔄 Pozisyonlar yenileniyor...")
            print(f"[IBKR_POSITIONS] 🔍 IBKR client: {ibkr_client}")
            print(f"[IBKR_POSITIONS] 🔍 IBKR client connected: {ibkr_client.is_connected()}")
            
            # IBKR'den pozisyonları çek (Native client için get_positions kullan)
            if hasattr(ibkr_client, 'get_positions'):
                positions = ibkr_client.get_positions()
                print(f"[IBKR_POSITIONS] 📊 Native get_positions() sonucu: {len(positions)} pozisyon")
            else:
                positions = ibkr_client.get_positions_direct()
                print(f"[IBKR_POSITIONS] 📊 ib_insync get_positions_direct() sonucu: {len(positions)} pozisyon")
            
            if not positions:
                print("[IBKR_POSITIONS] ⚠️ Pozisyon bulunamadı")
                print("[IBKR_POSITIONS] 💡 Kontrol edilecekler:")
                print("   1. IBKR Gateway çalışıyor mu?")
                print("   2. Kimlik doğrulaması yapıldı mı?")
                print("   3. Pozisyon var mı?")
                return
                
            print(f"[IBKR_POSITIONS] ✅ {len(positions)} pozisyon bulundu")
            
            # Her pozisyon için tabloya ekle
            for pos in positions:
                symbol = pos['symbol']
                qty = pos['qty']
                avg_cost = pos['avg_cost']
                current_price = float(get_last(symbol) or 0.0)
                
                # AVG COST hesaplamasını düzelt
                if avg_cost is None or avg_cost == 0:
                    # AVG COST yoksa pozisyon değerini hesapla
                    if qty != 0 and current_price > 0:
                        # Pozisyon değerini al
                        position_value = pos.get('positionValue', 0)
                        if position_value > 0:
                            avg_cost = position_value / abs(qty)
                        else:
                            avg_cost = current_price
                    else:
                        avg_cost = 0.0
                
                # PnL hesapla
                if avg_cost > 0 and current_price > 0:
                    pnl = (current_price - avg_cost) * abs(qty)
                else:
                    pnl = 0.0
                
                # AVG_ADV ve MAXALW değerlerini al
                avg_adv = get_avg_adv_from_csv(symbol)
                maxalw = avg_adv / 10 if avg_adv > 0 else 0
                
                # SMI değerini al
                smi = get_smi_from_csv(symbol)
                
                # Final FB ve Final SFS değerlerini al
                final_fb = get_final_fb_from_csv(symbol)
                final_sfs = get_final_sfs_from_csv(symbol)
                
                # Debug: Skorları logla
                print(f"[IBKR_POSITIONS] 📊 {symbol}: Final_FB={final_fb:.4f}, Final_SFS={final_sfs:.4f}")
                print(f"[IBKR_POSITIONS] 💰 {symbol}: Qty={qty}, AvgCost={avg_cost:.2f}, Current={current_price:.2f}, PnL={pnl:.2f}")
                
                # Sadece pozisyonu olan hisseleri göster
                if qty != 0:
                    tree.insert('', 'end', values=[
                        symbol,
                        f"{qty:.0f}",
                        f"${avg_cost:.2f}" if avg_cost > 0 else "N/A",
                        f"${current_price:.2f}",
                        f"${pnl:.2f}",
                        f"{avg_adv:.0f}",
                        f"{maxalw:.0f}",
                        f"{smi:.4f}" if smi > 0 else "N/A",
                        f"{final_fb:.4f}" if final_fb > 0 else "N/A",
                        f"{final_sfs:.4f}" if final_sfs > 0 else "N/A"
                    ])
                    
        except Exception as e:
            print(f"[IBKR_POSITIONS] ❌ Yenileme hatası: {e}")
    
    # İlk yükleme
    do_refresh()
    
    # Refresh butonu
    ttk.Button(win, text='Yenile', command=do_refresh).pack(pady=6)







