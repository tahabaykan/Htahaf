import logging
import time
from ..data.hammer_pro_direct import HammerProDirectClient

# Logging setup
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def on_market_data(symbol, data):
    """Market data callback"""
    print(f"\nMarket Data Update for {symbol}:")
    print(f"Price: {data['price']}")
    print(f"Bid: {data['bid']}")
    print(f"Ask: {data['ask']}")
    print(f"Last: {data['last']}")
    print(f"Volume: {data['volume']}")
    print(f"Prev Close: {data['prev_close']}")
    
def main():
    # Create client
    client = HammerProDirectClient(
        host='127.0.0.1',
        port=16400,
        password='YOUR_PASSWORD'  # Hammer Pro API şifrenizi buraya girin
    )
    
    # Set callback
    client.on_market_data = on_market_data
    
    # Connect
    print("Connecting to Hammer Pro...")
    if not client.connect():
        print("Failed to connect!")
        return
        
    # Subscribe to some symbols
    symbols = [
        "ABR PRD",  # -> ABR-D
        "ALL PRB",  # -> ALL-B
        "SPY",      # ETF
        "TLT"       # ETF
    ]
    
    print("\nSubscribing to symbols...")
    for symbol in symbols:
        client.subscribe_symbol(symbol)
        
    try:
        # Main loop
        while True:
            # Her sembol için orderbook ve son işlemleri göster
            for symbol in symbols:
                print(f"\nOrderbook for {symbol}:")
                book = client.get_orderbook(symbol)
                print("Bids:")
                for price, size in book['bids']:
                    print(f"  {size} @ {price}")
                print("Asks:")
                for price, size in book['asks']:
                    print(f"  {size} @ {price}")
                    
                print(f"\nLast 10 trades for {symbol}:")
                trades = client.get_last_prints(symbol)
                for trade in trades:
                    print(f"  {trade['size']} @ {trade['price']}")
                    
            # 5 saniye bekle
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
        client.disconnect()
        
if __name__ == "__main__":
    main()