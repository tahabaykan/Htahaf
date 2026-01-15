"""
Algorithm Service
Karmaşık algoritmaları (Croplit, Qpcal, Top Ten vb.) yöneten servis.
Bu servis arka plan thread'lerinde çalıştırılmak üzere tasarlanmıştır.
"""

import time
import threading
from services.order_service import OrderService
from services.score_service import ScoreService
from services.market_data_service import MarketDataService
from services.position_service import PositionService
from services.csv_service import CSVService

# Lazy imports to avoid circular deps
def get_socketio():
    from app import socketio
    return socketio

class AlgorithmService:
    def __init__(self):
        self.order_service = OrderService()
        self.score_service = ScoreService()
        self.market_data_service = MarketDataService() # Singleton
        self.position_service = PositionService()
        self.csv_service = CSVService() # Singleton

    def run_algorithm(self, algorithm_name, parameters=None):
        """
        Algoritmayı arka planda başlat
        """
        task_id = f"{algorithm_name}_{int(time.time())}"
        
        thread = threading.Thread(
            target=self._execute_algorithm,
            args=(algorithm_name, parameters, task_id),
            daemon=True
        )
        thread.start()
        
        return {'success': True, 'task_id': task_id, 'message': 'Algoritma başlatıldı'}

    def _execute_algorithm(self, algorithm_name, parameters, task_id):
        """
        Thread içinde çalışan asıl mantık
        """
        socketio = get_socketio()
        print(f"[Algo] Başlatılıyor: {algorithm_name} (ID: {task_id})")
        
        try:
            if algorithm_name.startswith('croplit'):
                self._run_croplit(algorithm_name)
            elif algorithm_name == 'qpcal':
                self._run_qpcal()
            elif algorithm_name == 'top_ten_bid_buy':
                self._run_top_ten('bid_buy')
            else:
                print(f"[Algo] Bilinmeyen algoritma: {algorithm_name}")

            # Bitiş bildirimi
            socketio.emit('algo_complete', {'task_id': task_id, 'status': 'success'})
            
        except Exception as e:
            print(f"[Algo] Hata ({algorithm_name}): {e}")
            import traceback
            traceback.print_exc()
            socketio.emit('algo_error', {'task_id': task_id, 'error': str(e)})

    def _run_croplit(self, algo_type):
        """
        Croplit Mantığı (6 ve 9 varyasyonları)
        """
        threshold = 0.09 if '9' in algo_type else 0.06
        is_long = 'longs' in algo_type
        
        print(f"[Croplit] Başlatılıyor: Eşik={threshold}, Yön={'Long' if is_long else 'Short'}")
        
        # 1. Pozisyonları al
        positions = self.position_service.get_positions()
        
        # 2. Filtrele
        target_positions = []
        for pos in positions:
            qty = float(pos.get('qty', 0))
            symbol = pos.get('symbol')
            
            if is_long and qty > 0:
                target_positions.append(pos)
            elif not is_long and qty < 0:
                target_positions.append(pos)
                
        print(f"[Croplit] İncelenecek pozisyon sayısı: {len(target_positions)}")
        
        # 3. Analiz et ve Emir Gönder
        processed_count = 0
        order_count = 0
        
        for pos in target_positions:
            symbol = pos.get('symbol')
            
            # Market data al
            market_data = self.market_data_service.get_market_data(symbol)
            if not market_data:
                continue
                
            bid = float(market_data.get('bid', 0))
            ask = float(market_data.get('ask', 0))
            spread = ask - bid
            
            # Eşik kontrolü
            if spread > threshold:
                # Skor kontrolü (Simüle ediliyor - gerçek implementasyonda ScoreService kullanılır)
                # Orijinal mantık: Ask Sell Pahalılık > -0.06 (Long için)
                # Basitlik için sadece spread kontrolü yapıyoruz şimdilik
                
                # Emir Miktarı: %10 kuralı
                qty = abs(float(pos.get('qty', 0)))
                order_qty = int(qty * 0.1)
                order_qty = (order_qty // 100) * 100 # 100'e yuvarla
                if order_qty < 200: order_qty = 200 # Min 200
                if order_qty > qty: order_qty = int(qty) # Eldekinden fazla satma
                
                if order_qty > 0:
                    print(f"[Croplit] Emir gönderiliyor: {symbol} {order_qty} lot")
                    
                    # Emir gönder
                    side = 'SELL' if is_long else 'BUY'
                    price_type = 'ask_sell' if is_long else 'bid_buy'
                    
                    self.order_service.place_order(
                        symbol=symbol,
                        side=side,
                        quantity=order_qty,
                        price=0, # Otomatik hesaplanacak
                        order_type='LIMIT',
                        order_type_special=price_type
                    )
                    order_count += 1
            
            processed_count += 1
            
        print(f"[Croplit] Tamamlandı. {order_count} emir gönderildi.")

    def _run_qpcal(self):
        """
        Qpcal Mantığı: Spread > 0.20 olanlara saldır
        """
        print("[Qpcal] Spread taraması başlıyor...")
        
        # CSV'den tüm hisseleri al
        df = self.csv_service.get_current_dataframe()
        if df is None:
            print("[Qpcal] CSV yok!")
            return

        symbols = df['PREF IBKR'].tolist()
        high_spread_stocks = []
        
        # Taramayı hızlandırmak için sadece market data cache'ine bakabiliriz
        # veya canlı tarama yapabiliriz
        
        for symbol in symbols:
            data = self.market_data_service.get_market_data(symbol)
            if data:
                bid = float(data.get('bid', 0))
                ask = float(data.get('ask', 0))
                if bid > 0 and ask > 0:
                    spread = ask - bid
                    if spread > 0.20:
                        high_spread_stocks.append(symbol)
                        # Otomatik alım emri gönder (Qpcal mantığı)
                        # SoftFront Buy/Sell gönderilir genelde
                        print(f"[Qpcal] Fırsat: {symbol} Spread: {spread:.2f}")
                        
                        # Burada emir gönderme mantığı eklenebilir
                        # self.order_service.place_order(...)
        
        print(f"[Qpcal] Tarama bitti. {len(high_spread_stocks)} hisse bulundu.")

    def list_algorithms(self):
        return [
            'croplit6_longs', 'croplit9_longs',
            'croplit6_shorts', 'croplit9_shorts',
            'qpcal', 'top_ten_bid_buy', 'bottom_ten_ask_sell'
        ]
