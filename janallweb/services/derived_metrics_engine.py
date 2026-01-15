"""
Derived Metrics Engine
Computes live scores using:
- Live market data (bid/ask/last/spread)
- Static data (AVG_ADV, SMI, SMA63chg, SMA246chg)

Outputs are explainable (inputs visible)
"""

from typing import Dict, Optional, Any


class DerivedMetricsEngine:
    """
    Computes derived scoring metrics from live market data and static data.
    All outputs are explainable with visible inputs.
    """
    
    def __init__(self):
        pass
    
    def compute_scores(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        static_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compute all derived scores for a symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            market_data: Live market data with keys: bid, ask, last, spread
            static_data: Static data with keys: AVG_ADV, SMI, SMA63 chg, SMA246 chg, etc.
            
        Returns:
            Dictionary with scores and explainable inputs
        """
        try:
            # Extract market data
            bid = self._safe_float(market_data.get('bid') or market_data.get('price'))
            ask = self._safe_float(market_data.get('ask'))
            last = self._safe_float(market_data.get('last') or market_data.get('price'))
            spread = self._safe_float(market_data.get('spread'))
            
            # Calculate spread if not provided
            if spread is None or spread == 0:
                if bid and ask and bid > 0 and ask > 0:
                    spread = ask - bid
                else:
                    spread = 0.0
            
            # Extract static data
            prev_close = self._safe_float(static_data.get('prev_close'))
            avg_adv = self._safe_float(static_data.get('AVG_ADV'))
            smi = self._safe_float(static_data.get('SMI'))
            sma63_chg = self._safe_float(static_data.get('SMA63 chg'))
            sma246_chg = self._safe_float(static_data.get('SMA246 chg'))
            final_thg = self._safe_float(static_data.get('FINAL_THG'))
            short_final = self._safe_float(static_data.get('SHORT_FINAL'))
            
            # Default values if missing
            prev_close = prev_close or 0.0
            avg_adv = avg_adv or 0.0
            smi = smi or 0.0
            sma63_chg = sma63_chg or 0.0
            sma246_chg = sma246_chg or 0.0
            final_thg = final_thg or 0.0
            short_final = short_final or 0.0
            bid = bid or 0.0
            ask = ask or 0.0
            last = last or 0.0
            
            # Store explainable inputs
            inputs = {
                'bid': bid,
                'ask': ask,
                'last': last,
                'spread': spread,
                'prev_close': prev_close,
                'AVG_ADV': avg_adv,
                'SMI': smi,
                'SMA63_chg': sma63_chg,
                'SMA246_chg': sma246_chg,
                'FINAL_THG': final_thg,
                'SHORT_FINAL': short_final
            }
            
            # Compute scores
            scores = {}
            
            # 1. Front Buy Score (FrontBuyScore)
            # Formula: (bid + 0.01) - prev_close - FINAL_THG + (SMA63chg * 0.3) + SMI
            if bid > 0 and prev_close > 0:
                front_buy_price = bid + 0.01
                front_buy_base = front_buy_price - prev_close - final_thg
                front_buy_score = front_buy_base + (sma63_chg * 0.3) + smi
                scores['FrontBuyScore'] = round(front_buy_score, 4)
                scores['FrontBuyScore_inputs'] = {
                    'front_buy_price': front_buy_price,
                    'base_score': front_buy_base,
                    'sma63_contribution': sma63_chg * 0.3,
                    'smi_contribution': smi
                }
            else:
                scores['FrontBuyScore'] = None
                scores['FrontBuyScore_inputs'] = None
            
            # 2. Final FB Score (FinalFBScore)
            # Same as FrontBuyScore (alias for consistency)
            scores['FinalFBScore'] = scores.get('FrontBuyScore')
            scores['FinalFBScore_inputs'] = scores.get('FrontBuyScore_inputs')
            
            # 3. Additional buy scores (for completeness)
            # Bid Buy Score
            if bid > 0 and prev_close > 0:
                bid_buy_base = bid - prev_close - final_thg
                bid_buy_score = bid_buy_base + (sma63_chg * 0.3) + smi
                scores['BidBuyScore'] = round(bid_buy_score, 4)
            else:
                scores['BidBuyScore'] = None
            
            # Ask Buy Score (with spread adjustment)
            if ask > 0 and prev_close > 0 and spread > 0:
                ask_buy_price = ask - (spread * 0.15)
                ask_buy_base = ask_buy_price - prev_close - final_thg
                ask_buy_score = ask_buy_base + (sma63_chg * 0.3) + smi
                scores['AskBuyScore'] = round(ask_buy_score, 4)
            else:
                scores['AskBuyScore'] = None
            
            # 4. Sell scores (for completeness)
            # Ask Sell Score
            if ask > 0 and prev_close > 0:
                ask_sell_base = ask - prev_close - final_thg
                ask_sell_score = ask_sell_base + (sma246_chg * 0.3) + short_final
                scores['AskSellScore'] = round(ask_sell_score, 4)
            else:
                scores['AskSellScore'] = None
            
            # Front Sell Score
            if ask > 0 and prev_close > 0:
                front_sell_price = ask - 0.01
                front_sell_base = front_sell_price - prev_close - final_thg
                front_sell_score = front_sell_base + (sma246_chg * 0.3) + short_final
                scores['FrontSellScore'] = round(front_sell_score, 4)
            else:
                scores['FrontSellScore'] = None
            
            # Bid Sell Score
            if bid > 0 and prev_close > 0 and spread > 0:
                bid_sell_price = bid + (spread * 0.15)
                bid_sell_base = bid_sell_price - prev_close - final_thg
                bid_sell_score = bid_sell_base + (sma246_chg * 0.3) + short_final
                scores['BidSellScore'] = round(bid_sell_score, 4)
            else:
                scores['BidSellScore'] = None
            
            # Return complete result with inputs
            return {
                'symbol': symbol,
                'inputs': inputs,
                'scores': scores,
                'spread': round(spread, 4)
            }
            
        except Exception as e:
            print(f"[DerivedMetricsEngine] Error computing scores for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return {
                'symbol': symbol,
                'inputs': None,
                'scores': {},
                'error': str(e)
            }
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def compute_batch(
        self,
        symbols: list,
        market_data_dict: Dict[str, Dict[str, Any]],
        static_data_dict: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Compute scores for multiple symbols at once.
        
        Args:
            symbols: List of symbols
            market_data_dict: {symbol: market_data}
            static_data_dict: {symbol: static_data}
            
        Returns:
            {symbol: computed_scores}
        """
        results = {}
        for symbol in symbols:
            market_data = market_data_dict.get(symbol, {})
            static_data = static_data_dict.get(symbol, {})
            results[symbol] = self.compute_scores(symbol, market_data, static_data)
        return results








