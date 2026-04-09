"""
OrderBook Fetcher

Fetch OrderBook data from Hammer Pro Market Data API.
Uses similar logic to JanallApp OrderBook button.
"""
from typing import List, Tuple, Optional, Any
from loguru import logger
from app.live.hammer_client import HammerClient
from app.config.settings import settings

class OrderBookFetcher:
    """
    Fetch OrderBook from Hammer Pro WebSocket.
    """
    
    def __init__(self, client: Optional[HammerClient] = None):
        self._client = client
        self._is_internal_client = False
        
    def _get_client(self) -> Optional[HammerClient]:
        if self._client:
            return self._client
        
        # Try to get global singleton if available
        try:
            from app.live.hammer_client import get_hammer_client
            self._client = get_hammer_client()
            if self._client:
                return self._client
        except ImportError:
            # get_hammer_client not available, use fallback
            pass

        # Internal client creation (fallback if no singleton and not provided)
        try:
            from app.config.settings import settings
            self._client = HammerClient(
                host=settings.HAMMER_HOST,
                port=settings.HAMMER_PORT,
                password=settings.HAMMER_PASSWORD,
                account_key=settings.HAMMER_ACCOUNT_KEY
            )
            if self._client.connect():
                self._is_internal_client = True
                return self._client
        except Exception as e:
            logger.error(f"[OrderBook] Failed to create internal client: {e}")
        return None

    def fetch_orderbook(
        self, 
        symbol: str, 
        max_levels: int = 10
    ) -> Tuple[List[Tuple[float, int]], List[Tuple[float, int]]]:
        """
        Fetch OrderBook for symbol.
        """
        client = self._get_client()
        if not client:
            return [], []
            
        try:
            snapshot = client.get_l2_snapshot(symbol)
            if not snapshot:
                return [], []
            
            # Hammer orderbook format from getQuotes/L2Update
            bids = []
            for b in snapshot.get('bids', []):
                price = b.get('price')
                qty = b.get('size', b.get('qty', 0))
                if price:
                    bids.append((float(price), int(qty)))
            
            asks = []
            for a in snapshot.get('asks', []):
                price = a.get('price')
                qty = a.get('size', a.get('qty', 0))
                if price:
                    asks.append((float(price), int(qty)))
            
            # Sort just in case
            bids.sort(key=lambda x: x[0], reverse=True)
            asks.sort(key=lambda x: x[0])
            
            return bids[:max_levels], asks[:max_levels]
            
        except Exception as e:
            logger.error(f"[OrderBook] Error fetching {symbol}: {e}")
            return [], []

    def find_suitable_ask(
        self, 
        symbol_or_list: Any, 
        min_price: float
    ) -> Tuple[Optional[float], Optional[int]]:
        """
        Unified finder for ASK.
        Returns (price, level_index) where level_index is 1-based.
        """
        asks = []
        if isinstance(symbol_or_list, str):
            _, asks = self.fetch_orderbook(symbol_or_list)
        else:
            asks = symbol_or_list

        for i, (ask_price, _) in enumerate(asks):
            if ask_price >= min_price:
                return ask_price, i + 1
        return None, None

    def find_suitable_bid(
        self, 
        symbol_or_list: Any, 
        max_price: float
    ) -> Tuple[Optional[float], Optional[int]]:
        """
        Unified finder for BID.
        Returns (price, level_index) where level_index is 1-based.
        """
        bids = []
        if isinstance(symbol_or_list, str):
            bids, _ = self.fetch_orderbook(symbol_or_list)
        else:
            bids = symbol_or_list

        for i, (bid_price, _) in enumerate(bids):
            if bid_price <= max_price:
                return bid_price, i + 1
        return None, None
