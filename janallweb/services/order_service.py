"""
Order Service
Emir fiyat hesaplamaları ve emir gönderimi
Mantık: janall/janallapp/main_window.py (place_order_for_selected) ile birebir aynı
"""

class OrderService:
    def __init__(self):
        # Market data service'e erişim lazım
        # (Circular dependency olmaması için metodlarda import edilebilir veya app context kullanılır)
        pass

    def get_market_data_service(self):
        # Lazy import
        from services.market_data_service import MarketDataService
        # Singleton instance'a erişim (App context üzerinden veya global)
        # Basitlik için yeni instance oluşturmuyoruz, mevcut olanı bulmaya çalışıyoruz
        # Ancak Flask app context içinde çalıştığımız için global servisi kullanabiliriz
        from routes.api_routes import market_data_service
        return market_data_service

    def get_mode_service(self):
        from routes.api_routes import mode_service
        return mode_service

    def calculate_price(self, order_type_special, bid, ask):
        """
        Özel emir tiplerine göre fiyat hesapla
        """
        try:
            bid = float(bid)
            ask = float(ask)
            spread = ask - bid
            price = 0.0
            side = 'BUY'

            if order_type_special == 'bid_buy':
                # Bid + Spread * 0.15 (Hidden)
                price = bid + (spread * 0.15)
                side = 'BUY'
            
            elif order_type_special == 'front_buy':
                # Bid + 0.01
                price = bid + 0.01
                side = 'BUY'
            
            elif order_type_special == 'ask_buy':
                # Ask - Spread * 0.15
                price = ask - (spread * 0.15)
                side = 'BUY'
            
            elif order_type_special == 'ask_sell':
                # Ask - Spread * 0.15 (Hidden)
                price = ask - (spread * 0.15)
                side = 'SELL'
            
            elif order_type_special == 'front_sell':
                # Ask - 0.01
                price = ask - 0.01
                side = 'SELL'
            
            elif order_type_special == 'bid_sell':
                # Bid + Spread * 0.15
                price = bid + (spread * 0.15)
                side = 'SELL'
            
            elif order_type_special == 'softfront_buy':
                # (Bid + Ask) / 2 - 0.01
                mid = (bid + ask) / 2
                price = mid - 0.01
                side = 'BUY'
            
            elif order_type_special == 'softfront_sell':
                # (Bid + Ask) / 2 + 0.01
                mid = (bid + ask) / 2
                price = mid + 0.01
                side = 'SELL'
            
            else:
                # Default LIMIT
                price = 0.0
                side = 'BUY' # Güvenlik için default

            return round(price, 2), side

        except Exception as e:
            print(f"Fiyat hesaplama hatası: {e}")
            return 0.0, 'BUY'

    def place_order(self, symbol, side, quantity, price, order_type='LIMIT', order_type_special=None):
        """
        Emir gönder
        """
        try:
            market_data_service = self.get_market_data_service()
            mode_service = self.get_mode_service()
            
            # Sembol formatı düzeltme (Hammer için)
            hammer_symbol = symbol.replace(" PR", "-")
            
            # Eğer special order type varsa fiyatı otomatik hesapla
            if order_type_special:
                market_data = market_data_service.get_market_data(symbol)
                if not market_data:
                    return {'success': False, 'error': f'{symbol} için market data yok'}
                
                bid = market_data.get('bid', 0)
                ask = market_data.get('ask', 0)
                
                if bid == 0 or ask == 0:
                    return {'success': False, 'error': f'{symbol} için Bid/Ask fiyatı yok'}
                
                calculated_price, calculated_side = self.calculate_price(order_type_special, bid, ask)
                
                # Parametreleri güncelle
                price = calculated_price
                side = calculated_side
                
                print(f"[OrderService] 🧮 {symbol} {order_type_special}: Bid={bid}, Ask={ask} -> Fiyat={price}")

            # Emir hidden mı? (Masaüstü uygulamasındaki mantık)
            is_hidden = False
            if order_type_special in ['bid_buy', 'ask_sell', 'softfront_buy', 'softfront_sell']:
                is_hidden = True

            # Mod kontrolü ve gönderim
            current_mode = mode_service.get_mode()
            
            if current_mode == 'HAMPRO':
                if not market_data_service.hammer_client or not market_data_service.hammer_client.is_connected():
                    return {'success': False, 'error': 'Hammer Pro bağlı değil'}
                
                # Hammer Client'a gönder
                success = market_data_service.hammer_client.place_order(
                    symbol=hammer_symbol,
                    side=side.upper(),
                    quantity=int(quantity),
                    price=float(price),
                    order_type=order_type.upper(),
                    hidden=is_hidden
                )
                
                if success:
                    return {'success': True, 'message': 'Emir gönderildi', 'details': f"{side} {quantity} @ {price}"}
                else:
                    return {'success': False, 'error': 'Hammer reddetti'}
            
            elif current_mode in ['IBKR_GUN', 'IBKR_PED']:
                # IBKR logic (henüz tam implemente değilse placeholder)
                # TODO: IBKR entegrasyonu
                return {'success': False, 'error': 'IBKR modu henüz aktif değil'}
                
            else:
                return {'success': False, 'error': 'Bilinmeyen mod'}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_orders(self):
        """Açık emirleri listele"""
        # Şimdilik boş liste veya memory'den
        # İleride Hammer/IBKR'dan çekilecek
        return []

    def cancel_order(self, order_id):
        """Emir iptal et"""
        # TODO: Implementasyon
        return {'success': True}
