"""
Order Planner
Plans orders based on intent and market conditions (dry-run, no execution).

Order Plan:
- action: BUY | SELL | NONE
- style: BID | FRONT | ASK | SOFT_FRONT
- price: Planned price
- size: Planned size
- urgency: LOW | MEDIUM | HIGH
- plan_reason: Explanation
"""

import os
import yaml
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

from app.core.logger import logger


class OrderPlanner:
    """
    Plans orders based on intent and market conditions.
    
    This is a planning layer only - NO execution, NO order sending.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize with config file.
        
        Args:
            config_path: Path to order_plan_rules.yaml config file
        """
        if config_path is None:
            # Default to config/order_plan_rules.yaml relative to project root
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "app" / "config" / "order_plan_rules.yaml"
        
        self.config = self._load_config(config_path)
        self._validate_config()
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load YAML config file"""
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                logger.warning(f"Order plan config file not found: {config_path}, using defaults")
                return self._get_default_config()
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            logger.info(f"Loaded order plan rules config from {config_path}")
            return config
            
        except Exception as e:
            logger.error(f"Error loading order plan config from {config_path}: {e}", exc_info=True)
            logger.warning("Using default order plan config")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default config if file not found"""
        return {
            'order_plan': {
                'style_selection': {
                    'bid_max_spread_percent': 0.2,
                    'front_max_spread_percent': 0.5,
                    'soft_front_max_spread_percent': 1.0
                },
                'size': {
                    'max_size_percent_of_adv': 10.0,
                    'min_size': 1,
                    'max_size': 1000
                },
                'price': {
                    'tick_size': 0.01
                }
            }
        }
    
    def _validate_config(self):
        """Validate config structure"""
        if 'order_plan' not in self.config:
            raise ValueError("Config missing required key: order_plan")
    
    def plan_order(
        self,
        intent: str,
        intent_reason: Dict[str, Any],
        market_data: Dict[str, Any],
        static_data: Dict[str, Any],
        grpan_metrics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Plan an order based on intent and conditions.
        
        Args:
            intent: Trading intent ('WANT_BUY', 'WANT_SELL', 'WAIT', 'BLOCKED')
            intent_reason: Intent reason dict
            market_data: Live market data (bid, ask, last, spread_percent)
            static_data: Static CSV data (AVG_ADV, SMI, FINAL_THG)
            
        Returns:
            Order plan dict:
            {
                'action': 'BUY' | 'SELL' | 'NONE',
                'style': 'BID' | 'FRONT' | 'ASK' | 'SOFT_FRONT',
                'price': float or None,
                'size': int or None,
                'urgency': 'LOW' | 'MEDIUM' | 'HIGH',
                'plan_reason': dict
            }
        """
        try:
            # If intent is not WANT_BUY or WANT_SELL, return NONE
            if intent not in ['WANT_BUY', 'WANT_SELL']:
                grpan_hint = self._calculate_grpan_hint(grpan_metrics, market_data)
                return {
                    'action': 'NONE',
                    'style': None,
                    'price': None,
                    'size': None,
                    'urgency': 'LOW',
                    'plan_reason': {
                        'reason': 'no_intent',
                        'intent': intent,
                        'message': f'Intent is {intent}, no order planned'
                    },
                    'grpan_hint': grpan_hint
                }
            
            # Extract market data
            bid = self._safe_float(market_data.get('bid'))
            ask = self._safe_float(market_data.get('ask'))
            last = self._safe_float(market_data.get('last') or market_data.get('price'))
            spread_percent = self._safe_float(market_data.get('spread_percent'))
            
            # Extract static data
            avg_adv = self._safe_float(static_data.get('AVG_ADV'))
            
            # Need valid market data
            if not bid or not ask:
                grpan_hint = self._calculate_grpan_hint(grpan_metrics, market_data)
                return {
                    'action': 'NONE',
                    'style': None,
                    'price': None,
                    'size': None,
                    'urgency': 'LOW',
                    'plan_reason': {
                        'reason': 'no_market_data',
                        'message': 'Missing bid/ask data'
                    },
                    'grpan_hint': grpan_hint
                }
            
            # Determine style based on spread
            style = self._determine_style(spread_percent)
            
            # Calculate price
            price = self._calculate_price(style, bid, ask, spread_percent)
            
            # Calculate size
            size = self._calculate_size(avg_adv, intent)
            
            # Determine urgency
            urgency = self._determine_urgency(spread_percent, intent_reason)
            
            # Build plan reason
            plan_reason = {
                'reason': 'order_planned',
                'intent': intent,
                'style': style,
                'spread_percent': round(spread_percent, 2) if spread_percent else None,
                'price_calculation': self._explain_price_calculation(style, bid, ask, spread_percent),
                'size_calculation': self._explain_size_calculation(avg_adv, size),
                'urgency': urgency,
                'message': f'Planned {intent} order: {style} style at {price:.4f}, size {size}'
            }
            
            # Calculate GRPAN hint (read-only, informational only)
            grpan_hint = self._calculate_grpan_hint(grpan_metrics, market_data)
            
            return {
                'action': 'BUY' if intent == 'WANT_BUY' else 'SELL',
                'style': style,
                'price': price,
                'size': size,
                'urgency': urgency,
                'plan_reason': plan_reason,
                'grpan_hint': grpan_hint
            }
            
        except Exception as e:
            logger.error(f"Error planning order: {e}", exc_info=True)
            grpan_hint = self._calculate_grpan_hint(grpan_metrics, market_data)
            return {
                'action': 'NONE',
                'style': None,
                'price': None,
                'size': None,
                'urgency': 'LOW',
                'plan_reason': {
                    'reason': 'error',
                    'error': str(e)
                },
                'grpan_hint': grpan_hint
            }
    
    def _determine_style(self, spread_percent: Optional[float]) -> str:
        """Determine order style based on spread"""
        if spread_percent is None:
            return 'ASK'  # Conservative default
        
        cfg = self.config['order_plan']['style_selection']
        
        if spread_percent <= cfg['bid_max_spread_percent']:
            return 'BID'
        elif spread_percent <= cfg['front_max_spread_percent']:
            return 'FRONT'
        elif spread_percent <= cfg['soft_front_max_spread_percent']:
            return 'SOFT_FRONT'
        else:
            return 'ASK'
    
    def _calculate_price(
        self,
        style: str,
        bid: float,
        ask: float,
        spread_percent: Optional[float]
    ) -> float:
        """Calculate planned price based on style"""
        tick_size = self.config['order_plan']['price']['tick_size']
        
        if style == 'BID':
            return bid
        
        elif style == 'FRONT':
            # Bid + tick_size (or mid + small offset)
            mid = (bid + ask) / 2
            return round(bid + tick_size, 4)
        
        elif style == 'SOFT_FRONT':
            # Mid + (spread * 0.15)
            mid = (bid + ask) / 2
            spread = ask - bid
            price = mid + (spread * 0.15)
            return round(price, 4)
        
        elif style == 'ASK':
            # Ask - (spread * 0.15)
            spread = ask - bid
            price = ask - (spread * 0.15)
            return round(price, 4)
        
        else:
            # Default to mid
            return round((bid + ask) / 2, 4)
    
    def _calculate_size(self, avg_adv: Optional[float], intent: str) -> int:
        """Calculate planned size based on AVG_ADV"""
        cfg = self.config['order_plan']['size']
        max_size_pct = cfg['max_size_percent_of_adv']
        min_size = cfg['min_size']
        max_size = cfg['max_size']
        
        if avg_adv is None or avg_adv <= 0:
            return min_size
        
        # Calculate size as percentage of AVG_ADV
        calculated_size = int(avg_adv * (max_size_pct / 100))
        
        # Apply limits
        size = max(min_size, min(calculated_size, max_size))
        
        return size
    
    def _determine_urgency(
        self,
        spread_percent: Optional[float],
        intent_reason: Dict[str, Any]
    ) -> str:
        """Determine order urgency"""
        if spread_percent is None:
            return 'LOW'
        
        # High urgency if spread is very tight
        if spread_percent <= 0.2:
            return 'HIGH'
        elif spread_percent <= 0.5:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def _explain_price_calculation(
        self,
        style: str,
        bid: float,
        ask: float,
        spread_percent: Optional[float]
    ) -> Dict[str, Any]:
        """Explain how price was calculated"""
        mid = (bid + ask) / 2
        spread = ask - bid
        
        if style == 'BID':
            return {
                'method': 'bid_price',
                'bid': bid,
                'price': bid
            }
        elif style == 'FRONT':
            tick_size = self.config['order_plan']['price']['tick_size']
            price = bid + tick_size
            return {
                'method': 'bid_plus_tick',
                'bid': bid,
                'tick_size': tick_size,
                'price': price
            }
        elif style == 'SOFT_FRONT':
            price = mid + (spread * 0.15)
            return {
                'method': 'mid_plus_spread_offset',
                'mid': mid,
                'spread': spread,
                'offset': spread * 0.15,
                'price': price
            }
        elif style == 'ASK':
            price = ask - (spread * 0.15)
            return {
                'method': 'ask_minus_spread_offset',
                'ask': ask,
                'spread': spread,
                'offset': spread * 0.15,
                'price': price
            }
        else:
            return {
                'method': 'mid_price',
                'mid': mid,
                'price': mid
            }
    
    def _explain_size_calculation(self, avg_adv: Optional[float], size: int) -> Dict[str, Any]:
        """Explain how size was calculated"""
        cfg = self.config['order_plan']['size']
        max_size_pct = cfg['max_size_percent_of_adv']
        
        if avg_adv is None or avg_adv <= 0:
            return {
                'method': 'default_min',
                'avg_adv': None,
                'size': size
            }
        
        calculated = int(avg_adv * (max_size_pct / 100))
        return {
            'method': 'percentage_of_adv',
            'avg_adv': avg_adv,
            'percentage': max_size_pct,
            'calculated': calculated,
            'final_size': size,
            'applied_limits': {
                'min': cfg['min_size'],
                'max': cfg['max_size']
            }
        }
    
    def _calculate_grpan_hint(
        self,
        grpan_metrics: Optional[Dict[str, Any]],
        market_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate GRPAN hint (read-only, informational only).
        
        This hint does NOT affect order planning logic, only provides context.
        
        Args:
            grpan_metrics: GRPAN metrics dict from GRPANEngine
            market_data: Market data dict (bid, ask, last)
            
        Returns:
            GRPAN hint dict with confidence, distances, and message
        """
        try:
            if not grpan_metrics:
                return {
                    'grpan_price': None,
                    'concentration_percent': None,
                    'print_count': 0,
                    'real_lot_count': 0,
                    'distance_to_last': None,
                    'distance_to_mid': None,
                    'confidence': 'NONE',
                    'message': 'No GRPAN data available'
                }
            
            grpan_price = self._safe_float(grpan_metrics.get('grpan_price'))
            concentration_percent = self._safe_float(grpan_metrics.get('concentration_percent'))
            print_count = grpan_metrics.get('print_count', 0)
            real_lot_count = grpan_metrics.get('real_lot_count', 0)
            
            # Calculate distance to last
            last = self._safe_float(market_data.get('last') or market_data.get('price'))
            distance_to_last = None
            if grpan_price is not None and last is not None:
                distance_to_last = abs(last - grpan_price)
            
            # Calculate distance to mid
            bid = self._safe_float(market_data.get('bid'))
            ask = self._safe_float(market_data.get('ask'))
            distance_to_mid = None
            if grpan_price is not None and bid is not None and ask is not None:
                mid = (bid + ask) / 2
                distance_to_mid = abs(mid - grpan_price)
            
            # Determine confidence
            confidence = 'NONE'
            if concentration_percent is None:
                confidence = 'NONE'
            elif concentration_percent >= 70.0:
                confidence = 'HIGH'
            elif concentration_percent >= 50.0:
                confidence = 'MEDIUM'
            else:
                confidence = 'LOW'
            
            # Build message
            message_parts = []
            if confidence != 'NONE':
                message_parts.append(f'GRPAN {confidence} ({concentration_percent:.1f}%)')
                if grpan_price is not None:
                    message_parts.append(f'grpan={grpan_price:.2f}')
                if distance_to_last is not None:
                    message_parts.append(f'|last-grpan|={distance_to_last:.2f}')
                message = ', '.join(message_parts)
            else:
                message = 'No GRPAN data available'
            
            return {
                'grpan_price': round(grpan_price, 4) if grpan_price is not None else None,
                'concentration_percent': round(concentration_percent, 2) if concentration_percent is not None else None,
                'print_count': print_count,
                'real_lot_count': real_lot_count,
                'distance_to_last': round(distance_to_last, 4) if distance_to_last is not None else None,
                'distance_to_mid': round(distance_to_mid, 4) if distance_to_mid is not None else None,
                'confidence': confidence,
                'message': message
            }
            
        except Exception as e:
            logger.error(f"Error calculating GRPAN hint: {e}", exc_info=True)
            return {
                'grpan_price': None,
                'concentration_percent': None,
                'print_count': 0,
                'real_lot_count': 0,
                'distance_to_last': None,
                'distance_to_mid': None,
                'confidence': 'NONE',
                'message': f'Error calculating GRPAN hint: {str(e)}'
            }
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


