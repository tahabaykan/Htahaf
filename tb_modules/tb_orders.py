"""
StockTracker için emir/sipariş yönetimi fonksiyonları
"""
from ib_insync import LimitOrder, MarketOrder
from tkinter import messagebox
import traceback
from ib_insync import Stock

def create_limit_order(action, quantity, price, outside_rth=False):
    """
    Limit emir oluştur
    
    Args:
        action (str): "BUY" veya "SELL"
        quantity (int): Miktar
        price (float): Fiyat
        outside_rth (bool): Regular Trading Hours dışında da geçerli olsun mu
        
    Returns:
        LimitOrder: Oluşturulan IB limit order nesnesi
    """
    order = LimitOrder(
        action=action,
        totalQuantity=quantity,
        lmtPrice=price,
        outsideRth=outside_rth,
        tif='DAY',  # Set time in force to DAY
        hidden=True,  # Set as hidden order
        displaySize=0  # Set visible size to 0
    )
    return order

def create_market_order(action, quantity, outside_rth=False):
    """
    Market emir oluştur
    
    Args:
        action (str): "BUY" veya "SELL"
        quantity (int): Miktar
        outside_rth (bool): Regular Trading Hours dışında da geçerli olsun mu
        
    Returns:
        MarketOrder: Oluşturulan IB market order nesnesi
    """
    order = MarketOrder(
        action=action,
        totalQuantity=quantity,
        outsideRth=outside_rth,
        tif='DAY',  # Set time in force to DAY
        hidden=True,  # Set as hidden order
        displaySize=0  # Set visible size to 0
    )
    return order

def format_order_row(order_data):
    """
    Emir verilerini tablo satırı için formatla
    
    Args:
        order_data (dict): Emir verilerini içeren sözlük
        
    Returns:
        tuple: Tablo satırı için değerler
    """
    symbol = order_data.get('symbol', '')
    order_type = order_data.get('order_type', 'Limit')
    action = order_data.get('action', 'BUY')
    quantity = order_data.get('quantity', 0)
    price = order_data.get('price', 0.0)
    status = order_data.get('status', 'Beklemede')
    
    return (symbol, order_type, action, quantity, price, status)

def calculate_order_value(quantity, price):
    """
    Emrin toplam değerini hesapla
    
    Args:
        quantity (int): Miktar
        price (float): Fiyat
        
    Returns:
        float: Toplam değer
    """
    try:
        return float(quantity) * float(price)
    except (ValueError, TypeError):
        return 0.0

def place_hidden_orders(ib_client, tree, action="BUY", parent_window=None, lot_size=200, spread_multiplier=0.15):
    """
    Seçilen hisseler için hidden emirler yerleştir
    
    Args:
        ib_client: IB bağlantı nesnesi
        tree: Treeview nesnesi (selectable_treeview ile oluşturulmuş)
        action: "BUY" veya "SELL"
        parent_window: Mesaj kutularının parent penceresi
        lot_size: Her hisse için emir miktarı (lot)
        spread_multiplier: Spread çarpanı (0.15 = spread'in %15'i)
        
    Returns:
        int: Başarıyla gönderilen emir sayısı
    """
    if not hasattr(tree, 'selected_positions'):
        messagebox.showinfo("Hata", "Geçersiz treeview nesnesi. Lütfen selectable_treeview kullanın.", parent=parent_window)
        return 0
    
    selected_positions = tree.selected_positions
    
    if not selected_positions:
        messagebox.showinfo("Uyarı", "Lütfen en az bir hisse seçin.", parent=parent_window)
        return 0
    
    print(f"Seçilen hisse sayısı: {len(selected_positions)}")
    
    # Seçili hisselerin verilerini topla
    orders_to_place = []
    
    for item_id in tree.get_children():
        item_values = tree.item(item_id, "values")
        
        if not item_values or len(item_values) < 7 or item_values[0] != "✓":
            continue
        
        try:
            symbol = item_values[1]
            
            # Satır yapısına göre bid ve ask sütunlarını belirleme
            # Tipik yapı: Select, Symbol, Last, Bid, Ask, ...
            bid_idx = 3  # Varsayılan
            ask_idx = 4  # Varsayılan
            
            # Veri tiplerine göre doğru sütunları bulma
            for i in range(2, min(6, len(item_values))):
                try:
                    val = float(item_values[i].replace("%", "").replace(",", ""))
                    if i == 2:  # Last price (3. sütun)
                        pass
                    elif i == 3:  # Muhtemelen bid (4. sütun)
                        bid_idx = i
                    elif i == 4:  # Muhtemelen ask (5. sütun)
                        ask_idx = i
                except (ValueError, AttributeError):
                    continue
            
            bid = float(item_values[bid_idx].replace(",", ""))
            ask = float(item_values[ask_idx].replace(",", ""))
            spread = ask - bid
            
            # Hedef fiyatı hesapla
            if action == "BUY":
                # Alış emri: bid + spread*multiplier
                target_price = bid + (spread * spread_multiplier)
            else:
                # Satış emri: ask - spread*multiplier
                target_price = ask - (spread * spread_multiplier)
            
            # Lot size ayarla
            quantity = lot_size
            
            orders_to_place.append({
                'symbol': symbol,
                'quantity': quantity,
                'price': target_price
            })
            
            print(f"Emir listeye eklendi: {symbol}, {quantity} adet @ {target_price:.2f}")
        except Exception as e:
            print(f"Hata: {e}, Değerler: {item_values}")
    
    if not orders_to_place:
        messagebox.showinfo("Uyarı", "Geçerli emirler oluşturulamadı. Verileri kontrol edin.", parent=parent_window)
        return 0
    
    # Emir detaylarını hazırla
    order_details = "\n".join([
        f"{order['symbol']}: {order['quantity']} adet @ {order['price']:.2f}$"
        for order in orders_to_place
    ])
    
    # Onay kutusu göster
    confirm = messagebox.askyesno(
        "Hidden Buy Emir Onayı",
        f"Aşağıdaki {len(orders_to_place)} hidden {action.lower()} emri gönderilecek:\n\n{order_details}\n\n"
        f"Onaylıyor musunuz?",
        parent=parent_window
    )
    
    if confirm:
        print("Emirler onaylandı!")
        try:
            # Gerçek emirleri gönder
            sent_orders = 0
            for order in orders_to_place:
                symbol = order['symbol']
                price = float(order['price'])
                quantity = int(order['quantity'])
                
                # Kontrat oluştur
                contract = Stock(symbol, 'SMART', 'USD')
                
                # Emir oluştur ve gönder
                limit_order = create_limit_order(action, quantity, round(price, 2))
                ib_client.placeOrder(contract, limit_order)
                print(f"Emir gönderildi: {symbol} {action} @ {price:.2f} x {quantity}")
                sent_orders += 1
            
            messagebox.showinfo(
                "Başarılı", 
                f"{sent_orders} adet hidden {action.lower()} emri başarıyla gönderildi!",
                parent=parent_window
            )
            return sent_orders
        except Exception as e:
            print(f"Emir gönderirken hata: {e}")
            traceback.print_exc()
            messagebox.showerror(
                "Hata", 
                f"Emirler gönderilirken hata oluştu: {str(e)}",
                parent=parent_window
            )
            return 0
    else:
        print("Emirler iptal edildi!")
        return 0 