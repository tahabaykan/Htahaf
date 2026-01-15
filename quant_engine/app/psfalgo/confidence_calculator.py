"""
Confidence Calculator - Production-Grade

Calculates decision confidence scores (0-1) based on:
- Metrics quality (data completeness)
- Signal strength (Fbtot, Ask Sell Pahalılık, etc.)
- Market conditions (spread, liquidity)
- Historical accuracy (if available)
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass

from app.core.logger import logger
from app.psfalgo.decision_models import SymbolMetrics, PositionSnapshot


@dataclass
class ConfidenceCalculator:
    """
    Confidence Calculator - calculates decision confidence scores.
    
    Confidence factors:
    1. Data completeness (0.0-0.3): Are all required metrics available?
    2. Signal strength (0.0-0.4): How strong is the signal?
    3. Market conditions (0.0-0.2): Spread, liquidity, etc.
    4. Historical accuracy (0.0-0.1): If available
    """
    
    def calculate_confidence(
        self,
        symbol: str,
        position: PositionSnapshot,
        metrics: SymbolMetrics,
        action: str,
        reason: str
    ) -> float:
        """
        Calculate confidence score (0-1) for a decision.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            position: Position snapshot
            metrics: Symbol metrics
            action: Decision action ("SELL", "BUY", etc.)
            reason: Decision reason
            
        Returns:
            Confidence score (0.0-1.0)
        """
        confidence = 0.0
        
        # Factor 1: Data completeness (0.0-0.3)
        data_completeness = self._calculate_data_completeness(metrics, action)
        confidence += data_completeness * 0.3
        
        # Factor 2: Signal strength (0.0-0.4)
        signal_strength = self._calculate_signal_strength(position, metrics, action)
        confidence += signal_strength * 0.4
        
        # Factor 3: Market conditions (0.0-0.2)
        market_conditions = self._calculate_market_conditions(metrics)
        confidence += market_conditions * 0.2
        
        # Factor 4: Historical accuracy (0.0-0.1) - placeholder for future
        # historical_accuracy = self._calculate_historical_accuracy(symbol, action)
        # confidence += historical_accuracy * 0.1
        
        # Ensure confidence is in [0.0, 1.0]
        confidence = max(0.0, min(1.0, confidence))
        
        return confidence
    
    def _calculate_data_completeness(self, metrics: SymbolMetrics, action: str) -> float:
        """
        Calculate data completeness score (0.0-1.0).
        
        Checks if all required metrics are available for the decision.
        """
        required_metrics = []
        
        # For SELL actions (KARBOTU/REDUCEMORE)
        if action in ['SELL', 'REDUCE']:
            required_metrics = [
                metrics.fbtot,
                metrics.ask_sell_pahalilik,
                metrics.gort,
                metrics.current_price if hasattr(metrics, 'current_price') else metrics.last,
                metrics.spread
            ]
        
        # For BUY actions (ADDNEWPOS)
        elif action in ['BUY', 'ADD']:
            required_metrics = [
                metrics.bid_buy_ucuzluk,
                metrics.fbtot,
                metrics.spread,
                metrics.avg_adv,
                metrics.current_price if hasattr(metrics, 'current_price') else metrics.last
            ]
        
        # Count available metrics
        available_count = sum(1 for m in required_metrics if m is not None)
        total_count = len(required_metrics)
        
        if total_count == 0:
            return 0.0
        
        return available_count / total_count
    
    def _calculate_signal_strength(self, position: PositionSnapshot, metrics: SymbolMetrics, action: str) -> float:
        """
        Calculate signal strength score (0.0-1.0).
        
        Based on how strong the signal is (Fbtot, Ask Sell Pahalılık, etc.).
        """
        if action in ['SELL', 'REDUCE']:
            # For SELL: Higher Ask Sell Pahalılık = stronger signal
            ask_sell = metrics.ask_sell_pahalilik
            if ask_sell is None:
                return 0.0
            
            # Normalize to [0, 1]
            # Ask Sell Pahalılık typically ranges from -0.20 to +0.20
            # Strong signal: > 0.05, Weak signal: < -0.05
            normalized = (ask_sell + 0.20) / 0.40  # Shift and scale
            return max(0.0, min(1.0, normalized))
        
        elif action in ['BUY', 'ADD']:
            # For BUY: Higher Bid Buy Ucuzluk = stronger signal
            bid_buy = metrics.bid_buy_ucuzluk
            if bid_buy is None:
                return 0.0
            
            # Normalize to [0, 1]
            # Bid Buy Ucuzluk typically ranges from -0.20 to +0.20
            # Strong signal: > 0.05, Weak signal: < -0.05
            normalized = (bid_buy + 0.20) / 0.40  # Shift and scale
            return max(0.0, min(1.0, normalized))
        
        return 0.5  # Default for other actions
    
    def _calculate_market_conditions(self, metrics: SymbolMetrics) -> float:
        """
        Calculate market conditions score (0.0-1.0).
        
        Based on spread, liquidity, etc.
        """
        score = 1.0
        
        # Spread check: Lower spread = better conditions
        if metrics.spread_percent is not None:
            # Spread < 0.05% = excellent (1.0)
            # Spread > 0.20% = poor (0.0)
            if metrics.spread_percent < 0.05:
                spread_score = 1.0
            elif metrics.spread_percent > 0.20:
                spread_score = 0.0
            else:
                spread_score = 1.0 - ((metrics.spread_percent - 0.05) / 0.15)
            score *= spread_score
        
        # Liquidity check: Higher AVG_ADV = better conditions
        if metrics.avg_adv is not None:
            # AVG_ADV > 1000 = excellent (1.0)
            # AVG_ADV < 100 = poor (0.0)
            if metrics.avg_adv > 1000:
                liquidity_score = 1.0
            elif metrics.avg_adv < 100:
                liquidity_score = 0.0
            else:
                liquidity_score = (metrics.avg_adv - 100) / 900
            score *= liquidity_score
        
        return max(0.0, min(1.0, score))


# Global instance
_confidence_calculator: Optional[ConfidenceCalculator] = None


def get_confidence_calculator() -> Optional[ConfidenceCalculator]:
    """Get global ConfidenceCalculator instance"""
    return _confidence_calculator


def initialize_confidence_calculator():
    """Initialize global ConfidenceCalculator instance"""
    global _confidence_calculator
    _confidence_calculator = ConfidenceCalculator()
    logger.info("ConfidenceCalculator initialized")






