"""
Janall Order Mechanisms
=======================
This module replicates the exact order management logic from the legacy 'janall' application.
It includes:
1. Smart Lot Splitting (0-399 direct, 400+ split into 200s)
2. Soft Front / Front / Bid-Ask price calculations
3. Bulk order execution orchestration (takir takir logic)
"""

import math
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

class JanallBulkOrderManager:
    def __init__(self, trading_client, market_data_service):
        """
        :param trading_client: Adapter to place/cancel orders (IBKRConnector or similar)
        :param market_data_service: Source for Bid/Ask/Last data
        """
        self.trading_client = trading_client
        self.market_data = market_data_service
        self.lot_divider_enabled = True  # Default to TRUE as per Janall legacy

    def toggle_lot_divider(self, enabled: bool):
        self.lot_divider_enabled = enabled
        logger.info(f"Lot Divider set to: {enabled}")

    def divide_lot_size(self, total_lot: int):
        """
        Replicates janallapp/order_management.py divide_lot_size logic exactly.
        
        Logic:
        - 0-399 lot: Send directly
        - 400+ lot: Split into chunks of 200, with remainder
          Ex: 500 -> 200, 300 (NOT 200, 200, 100)
          Ex: 600 -> 200, 200, 200
          Ex: 700 -> 200, 200, 300
        """
        try:
            if total_lot <= 0:
                return []
            
            if not self.lot_divider_enabled:
                return [total_lot]

            # 0-399 lot: Direkt gönder
            if total_lot <= 399:
                return [total_lot]
            
            # 400+ lot logic
            lot_parts = []
            remaining = total_lot
            
            # Keep subtracting 200 as long as remaining >= 400
            # This ensures the LAST chunk is between 200 and 399 (or exactly 200/0)
            while remaining >= 400:
                lot_parts.append(200)
                remaining -= 200
            
            # Add remaining part
            if remaining > 0:
                lot_parts.append(remaining)
                
            return lot_parts

        except Exception as e:
            logger.error(f"Lot split error: {e}")
            return [total_lot]

    def check_soft_front_conditions(self, bid, ask, last, is_buy=True):
        """
        Replicates soft front conditions:
        1. (Ask - Last) / Spread > 0.60  (For Buy)
        2. (Ask - Last) >= 0.15          (For Buy)
        At least one condition must be true.
        """
        if bid <= 0 or ask <= 0 or last <= 0:
            return False
            
        spread = ask - bid
        if spread <= 0:
            return False
            
        if is_buy:
            # Soft Front Buy
            diff = ask - last
            cond1 = (diff / spread) > 0.60
            cond2 = diff >= 0.15
            return cond1 or cond2
        else:
            # Soft Front Sell
            diff = last - bid
            cond1 = (diff / spread) > 0.60
            cond2 = diff >= 0.15
            return cond1 or cond2

    def calculate_price_and_action(self, ticker: str, order_type: str):
        """
        Calculates price based on order type and current market data.
        Returns: (price, action, error_msg)
        """
        # Fetch data
        data = self.market_data.get_market_data(ticker)
        if not data:
            return None, None, f"No market data for {ticker}"
            
        bid = float(data.get('bid', 0))
        ask = float(data.get('ask', 0))
        last = float(data.get('last', 0))
        spread = ask - bid
        
        price = 0.0
        action = "BUY"
        
        if order_type == 'bid_buy':
            price = bid + (spread * 0.15)
            action = 'BUY'
            
        elif order_type == 'front_buy':
            price = last + 0.01
            action = 'BUY'
            
        elif order_type == 'ask_buy':
            price = ask + 0.01
            action = 'BUY'
            
        elif order_type == 'ask_sell':
            price = ask - (spread * 0.15)
            action = 'SELL'
            
        elif order_type == 'front_sell':
            price = last - 0.01
            action = 'SELL'
            
        elif order_type == 'bid_sell':
            # Note: janall uses bid - 0.01 for 'bid_sell'
            price = bid - 0.01
            action = 'SELL'
            
        elif order_type == 'soft_front_buy':
            if self.check_soft_front_conditions(bid, ask, last, is_buy=True):
                price = last + 0.01
                action = 'BUY'
            else:
                return None, None, "Soft Front Buy conditions not met"
                
        elif order_type == 'soft_front_sell':
            if self.check_soft_front_conditions(bid, ask, last, is_buy=False):
                price = last - 0.01
                action = 'SELL'
            else:
                return None, None, "Soft Front Sell conditions not met"
        else:
            return None, None, f"Unknown order type: {order_type}"
            
        # Round to 2 decimals
        price = round(price, 2)
        return price, action, None

    async def execute_bulk_orders(self, tickers: list, order_type: str, total_lot: int, strategy_tag: str, ledger=None):
        """
        Orchestrates the bulk submission.
        
        :param tickers: List of symbols
        :param order_type: 'bid_buy', 'front_sell', etc. (Tactical)
        :param total_lot: Total quantity
        :param strategy_tag: 'LT_LONG_INCREASE', 'MM_SHORT_DECREASE', etc. (Strategic)
        :param ledger: Optional PSFALGOExecutionLedger instance to record intent
        """
        import asyncio
        results = []
        
        logger.info(f"Starting Bulk Order: {len(tickers)} tickers, Type: {order_type}, Tag: {strategy_tag}, Lot: {total_lot}")
        
        for i, ticker in enumerate(tickers):
            # Throttle between different TICKERS (Sequential "ard arda" logic)
            if i > 0:
                await asyncio.sleep(0.05) # Reduced delay for speed
        
            try:
                # ...
                
                # (Calculation is fast & sync, no need to await unless market data requires it)
                price, action, error = self.calculate_price_and_action(ticker, order_type)
                if error:
                    logger.warning(f"Skipping {ticker}: {error}")
                    results.append({'ticker': ticker, 'status': 'skipped', 'reason': error})
                    continue
                
                # 2. Record to Ledger (Intent)
                if ledger:
                    # Map strategy to psfalgo_action somewhat
                    psfalgo_action = strategy_tag # e.g. LT_LONG_INCREASE
                    
                    ledger.add_entry(
                        symbol=ticker,
                        psfalgo_action=psfalgo_action,
                        size_percent=0,             # Manual bulk
                        size_lot_estimate=total_lot,
                        action_reason=f"Bulk Manual: {order_type}",
                        order_subtype=strategy_tag, # CRITICAL: The 8-type tag
                        book="MANUAL"
                    )
                
                # 3. Split Lots
                lot_chunks = self.divide_lot_size(total_lot)
                logger.info(f"{ticker}: Splitting {total_lot} into {lot_chunks}")
                
                # 4. Send Orders
                ticker_results = []
                for j, chunk_size in enumerate(lot_chunks):
                    if j > 0:
                        await asyncio.sleep(0.05) 
                        
                    # Determine if we can pass the tag to the client
                    # If IBKR/Hammer client supports 'order_ref' or similar, pass it here.
                    # We utilize dynamic checking to support both Sync and Async clients
                    
                    place_func = self.trading_client.place_order
                    
                    if asyncio.iscoroutinefunction(place_func):
                         success = await place_func(
                            symbol=ticker,
                            action=action,
                            quantity=chunk_size,
                            price=price,
                            order_type="LIMIT",
                            strategy_tag=strategy_tag # Pass tag to IBKR/Hammer
                        )
                    else:
                         success = place_func(
                            symbol=ticker,
                            action=action,
                            quantity=chunk_size,
                            price=price,
                            order_type="LIMIT",
                            strategy_tag=strategy_tag
                        )
                    
                    # Inspect result (IBKR returns dict, Hammer returns bool/dict)
                    if isinstance(success, dict):
                         status = 'submitted' if success.get('success') else 'failed'
                    else:
                         status = 'submitted' if success else 'failed'
                         
                    ticker_results.append(status)
                    logger.info(f"  -> Order {j+1}: {chunk_size} @ {price} = {status}")
                
                results.append({'ticker': ticker, 'status': 'processed', 'parts': ticker_results})
                
            except Exception as e:
                logger.error(f"Error processing {ticker}: {e}", exc_info=True)
                results.append({'ticker': ticker, 'status': 'error', 'reason': str(e)})
                
        return results

