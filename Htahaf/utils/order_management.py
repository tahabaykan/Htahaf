import datetime
import os

REASONING_LOG_FILE = 'psf_reasoning.log'

def log_reasoning(message):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {message}"
    # Dosyaya ekle
    with open(REASONING_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')
    # Bellekte de tutmak için (OrderManager içinde de bir liste olacak)
    if hasattr(OrderManager, '_reasoning_log'):
        OrderManager._reasoning_log.append(line)

class OrderFill:
    """
    Represents a filled order and its associated data, including benchmark and reverse order info.
    """
    def __init__(self, ticker, direction, fill_price, fill_size, fill_time, ask, bid, spread, benchmark_value, order_type="Normal"):
        self.ticker = ticker
        self.direction = direction  # 'long' or 'short'
        self.fill_price = fill_price
        self.fill_size = fill_size
        self.fill_time = fill_time
        self.ask = ask
        self.bid = bid
        self.spread = spread
        self.benchmark_at_fill = benchmark_value
        self.current_benchmark = benchmark_value
        self.bench_chg_from_fill = 0.0
        self.reverse_order = None  # Will be set when reverse order is filled
        self.realized_pnl = None
        self.benchmark_pnl = None
        self.outperformance = None
        self.order_type = order_type

    def update_current_benchmark(self, new_benchmark):
        self.current_benchmark = new_benchmark
        self.bench_chg_from_fill = round(self.current_benchmark - self.benchmark_at_fill, 4)

    def create_reverse_order(self):
        """
        Create a reverse take profit order based on fill direction and size logic.
        Returns a dict with order details. All orders are marked as hidden.
        """
        if self.direction == 'long':
            tp_price = self.ask - self.spread * 0.15
        else:
            tp_price = self.bid + self.spread * 0.15

        # Size logic
        if self.fill_size <= 400:
            tp_size = self.fill_size
        elif self.fill_size <= 1000:
            tp_size = self.fill_size // 2
        else:
            tp_size = self.fill_size // 3

        reverse_direction = 'short' if self.direction == 'long' else 'long'
        return {
            'ticker': self.ticker,
            'direction': reverse_direction,
            'price': round(tp_price, 4),
            'size': tp_size,
            'hidden': True,
            'order_type': 'TP',
            'parent_fill_time': self.fill_time,
            'parent_fill_price': self.fill_price
        }

    def fill_reverse_order(self, reverse_fill_price, reverse_fill_time, reverse_benchmark_value):
        """
        Register the fill of the reverse order and calculate realized and benchmark PNL.
        """
        self.reverse_order = {
            'fill_price': reverse_fill_price,
            'fill_time': reverse_fill_time,
            'benchmark_value': reverse_benchmark_value,
            'hidden': True,
            'order_type': 'TP',
            'parent_fill_time': self.fill_time,
            'parent_fill_price': self.fill_price
        }
        # Realized PNL
        if self.direction == 'long':
            self.realized_pnl = (reverse_fill_price - self.fill_price) * self.fill_size
            self.benchmark_pnl = (reverse_benchmark_value - self.benchmark_at_fill) * self.fill_size
            self.outperformance = self.realized_pnl - self.benchmark_pnl
        else:
            self.realized_pnl = (self.fill_price - reverse_fill_price) * self.fill_size
            self.benchmark_pnl = (self.benchmark_at_fill - reverse_benchmark_value) * self.fill_size
            self.outperformance = self.realized_pnl - self.benchmark_pnl

class OrderManager:
    """
    Manages all fills and reverse orders. Integrate this with GUI fill/cancel events.
    """
    _reasoning_log = []  # Sınıf düzeyinde, bellekte log

    def __init__(self):
        self.fills = []
        self.reverse_orders = []
        self.positions = {}  # ticker -> (direction, size)

    def on_fill(self, ticker, direction, fill_price, fill_size, ask, bid, spread, benchmark_value, order_type="Normal", reasoning=None):
        """
        Call this when an order is filled. Returns the fill object and the reverse order dict.
        All orders are marked as hidden.
        """
        import math
        fill_time = datetime.datetime.now()
        fill = OrderFill(ticker, direction, fill_price, fill_size, fill_time, ask, bid, spread, benchmark_value, order_type=order_type)
        self.fills.append(fill)

        # --- POZİSYON TAKİBİ ---
        prev_dir, prev_size = self.positions.get(ticker, (None, 0))
        new_size = prev_size
        if direction == 'long':
            new_size += fill_size
        else:
            new_size -= fill_size

        # --- REASONING LOG: Fill ---
        if reasoning:
            log_reasoning(f"{ticker} {fill_price} {fill_size} {direction} fill: {reasoning}")
        else:
            log_reasoning(f"{ticker} {fill_price} {fill_size} {direction} fill")

        # --- REVERSE ORDER AÇMA KARARI ---
        reverse_order = None
        # Sadece Normal fill'ler için (TP fill'lerinde açma)
        if order_type == "Normal":
            # Minimum 200 share şartı
            if fill_size >= 200:
                # Pozisyon açılıyorsa veya artırılıyorsa
                same_dir = (prev_dir == direction or prev_dir is None)
                pos_increase = (abs(new_size) > abs(prev_size))
                pos_open = (prev_size == 0 and new_size != 0 and same_dir)
                # Ters yöne geçiş yok (ör: +200'den -100'e gibi değil)
                not_cross = (prev_size == 0 or (prev_size * new_size > 0))
                if (pos_open or (pos_increase and same_dir)) and not_cross:
                    # Reverse order fiyatı parent fill'den en az 0.05 farklı olmalı
                    if direction == 'long':
                        tp_price = max(ask - spread * 0.15, fill_price + 0.05)
                        reverse_direction = 'short'
                    else:
                        tp_price = min(bid + spread * 0.15, fill_price - 0.05)
                        reverse_direction = 'long'
                    # Size: fill_size kadar (veya daha önceki reverse'lar ile aşılmasın)
                    total_reverse_size = sum(
                        ro['size'] for ro in self.reverse_orders
                        if ro['ticker'] == ticker and ro['direction'] == reverse_direction
                    )
                    allowed_size = max(0, fill_size - total_reverse_size)
                    tp_size = min(fill_size, allowed_size)
                    if tp_size > 0:
                        reverse_order = {
                            'ticker': ticker,
                            'direction': reverse_direction,
                            'price': round(tp_price, 4),
                            'size': tp_size,
                            'hidden': True,
                            'order_type': 'TP',
                            'parent_fill_time': fill_time,
                            'parent_fill_price': fill_price
                        }
                        self.reverse_orders.append(reverse_order)
                        log_reasoning(f"{ticker} {tp_price:.2f} {tp_size} hidden {reverse_direction} reverse TP emri açıldı (parent fill: {fill_price}, {fill_size}, {direction})")
                    else:
                        log_reasoning(f"{ticker} için reverse order açılmadı, toplam reverse order size fill size'ı aşıyor.")
        # Pozisyonu güncelle
        if new_size == 0:
            self.positions.pop(ticker, None)
        else:
            self.positions[ticker] = (direction if new_size > 0 else ('short' if direction == 'long' else 'long'), new_size)
        return fill, reverse_order

    def on_reverse_fill(self, fill: OrderFill, reverse_fill_price, reverse_benchmark_value):
        """
        Call this when the reverse (take profit) order is filled. Updates PNL and performance.
        """
        reverse_fill_time = datetime.datetime.now()
        fill.fill_reverse_order(reverse_fill_price, reverse_fill_time, reverse_benchmark_value)
        # Reverse orderı reverse_orders listesinden çıkar
        self.reverse_orders = [
            ro for ro in self.reverse_orders
            if not (ro['ticker'] == fill.ticker and ro['direction'] != fill.direction and ro['parent_fill_time'] == fill.fill_time)
        ]
        log_reasoning(f"{fill.ticker} {reverse_fill_price} {fill.fill_size} reverse TP fillendi, realized PNL: {fill.realized_pnl:.2f}, benchmark PNL: {fill.benchmark_pnl:.2f}, outperformance: {fill.outperformance:.2f}")

    def update_benchmarks(self, ticker, new_benchmark):
        for fill in self.fills:
            if fill.ticker == ticker:
                fill.update_current_benchmark(new_benchmark)

    def get_normal_orders(self):
        # Hem 'Normal' hem de 'TP' tipli fill'leri döndür
        return [fill for fill in self.fills if fill.order_type in ("Normal", "TP")]

    def get_reverse_orders(self):
        # Sadece otomatik TP reverse emirlerini döndür
        return [ro for ro in self.reverse_orders if ro.get('order_type') == 'TP']

    def get_reasoning_log(self, last_n=100):
        # Son N reasoning logunu döndür
        return OrderManager._reasoning_log[-last_n:]

    def print_summary(self):
        """
        Print a summary of all fills, reverse orders, realized PNL, benchmark PNL, and outperformance.
        """
        print("\n=== Order Management Summary ===")
        for i, fill in enumerate(self.fills, 1):
            print(f"\nOrder {i}: {fill.ticker} | {fill.direction.upper()} | Fill Price: {fill.fill_price} | Size: {fill.fill_size} | Time: {fill.fill_time.strftime('%Y-%m-%d %H:%M:%S')} | OrderType: {fill.order_type}")
            print(f"  Benchmark at Fill: {fill.benchmark_at_fill}")
            print(f"  Current Benchmark: {fill.current_benchmark}")
            print(f"  Bench Chg from Fill: {fill.bench_chg_from_fill:.4f}")
            if fill.reverse_order:
                print(f"  Reverse Order: {fill.reverse_order}")
                print(f"  Realized PNL: {fill.realized_pnl:.2f} | Benchmark PNL: {fill.benchmark_pnl:.2f} | Outperformance: {fill.outperformance:.2f}")
            else:
                print("  Reverse Order: Not filled yet.")

# Example usage (to be integrated with GUI/IBKR events):
# manager = OrderManager()
# fill, reverse_order = manager.on_fill('AFGE', 'long', 16.21, 200, ask=16.25, bid=16.18, spread=0.07, benchmark_value=29.12)
# # ... reverse_order fill olunca:
# manager.on_reverse_fill(fill, reverse_fill_price=16.50, reverse_benchmark_value=29.50)
# manager.print_summary() 
