"""
Position Service - Pozisyon yönetimi
"""

from services.market_data_service import MarketDataService

class PositionService:
    """Pozisyon yönetimi için service"""
    
    def __init__(self):
        # MarketDataService üzerinden HammerClient'a erişim sağlıyoruz
        # Ancak circular import olmaması için metod içinde import edebiliriz veya
        # app başlatıldığında instance'ı alabiliriz.
        # Burada doğrudan import yerine, servisi kullanırken alacağız.
        pass
    
    def get_market_data_service(self):
        from routes.api_routes import market_data_service
        return market_data_service

    def get_positions(self):
        """Pozisyonları getir"""
        try:
            market_data_service = self.get_market_data_service()
            hammer_client = market_data_service.hammer_client
            
            if hammer_client and hammer_client.is_connected():
                # HammerClient içindeki cachelenmiş pozisyonları al
                raw_positions = getattr(hammer_client, 'positions', [])
                
                formatted_positions = []
                for pos in raw_positions:
                    # Sembol
                    symbol = pos.get('Symbol') or pos.get('sym')
                    if not symbol: continue
                    
                    # Sembol formatı düzeltme (PR)
                    display_symbol = symbol
                    if '-' in symbol:
                        base, suffix = symbol.split('-')
                        display_symbol = f"{base} PR{suffix}"

                    # Miktar bulma (değişken isimleri farklı olabilir)
                    qty = 0
                    if 'Qty' in pos: qty = pos['Qty']
                    elif 'qty' in pos: qty = pos['qty']
                    elif 'Quantity' in pos: qty = pos['Quantity']
                    elif 'quantity' in pos: qty = pos['quantity']
                    elif 'Position' in pos: qty = pos['Position']
                    
                    try:
                        qty = float(qty)
                    except:
                        qty = 0
                        
                    if qty == 0: continue

                    # Diğer alanlar
                    avg_cost = float(pos.get('AvgPrice') or pos.get('avg_cost') or pos.get('AveragePrice') or 0)
                    last_price = float(pos.get('LastPrice') or pos.get('last') or 0)
                    pnl = float(pos.get('PnL') or pos.get('UnrealizedPnL') or 0)
                    
                    formatted_positions.append({
                        'symbol': display_symbol,
                        'qty': qty,
                        'avg_cost': avg_cost,
                        'last_price': last_price,
                        'pnl': pnl
                    })
                
                return formatted_positions
            else:
                return []
        except Exception as e:
            print(f"[PositionService] Hata: {e}")
            return []
