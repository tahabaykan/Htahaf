"""app/risk/risk_limits.py

Risk limits configuration - defines static risk limits.
Loaded from settings or config file.
"""

import os
from typing import Optional
from pydantic import BaseModel, Field

from app.config.settings import settings


class RiskLimits(BaseModel):
    """
    Risk limits configuration.
    
    All limits are enforced by RiskManager to prevent excessive risk exposure.
    """
    
    # Position limits
    max_position_per_symbol: float = Field(
        default=10000.0,
        description="Maximum position size per symbol (in shares or dollars)"
    )
    max_total_position: float = Field(
        default=100000.0,
        description="Maximum total position size across all symbols"
    )
    
    # Loss limits
    max_daily_loss: float = Field(
        default=5000.0,
        description="Maximum daily loss limit (in dollars)"
    )
    max_trade_loss: float = Field(
        default=1000.0,
        description="Maximum loss per trade (in dollars)"
    )
    max_drawdown_pct: float = Field(
        default=10.0,
        description="Maximum drawdown percentage before circuit breaker"
    )
    
    # Exposure limits
    max_exposure_pct: float = Field(
        default=50.0,
        description="Maximum exposure as percentage of account value"
    )
    max_exposure_per_symbol_pct: float = Field(
        default=20.0,
        description="Maximum exposure per symbol as percentage of account value"
    )
    
    # Trading frequency limits
    max_trades_per_minute: int = Field(
        default=10,
        description="Maximum number of trades per minute"
    )
    max_trades_per_hour: int = Field(
        default=100,
        description="Maximum number of trades per hour"
    )
    max_trades_per_day: int = Field(
        default=500,
        description="Maximum number of trades per day"
    )
    
    # Circuit breaker
    circuit_breaker_pct: float = Field(
        default=5.0,
        description="Circuit breaker trigger: price move percentage in short time"
    )
    circuit_breaker_window_seconds: int = Field(
        default=60,
        description="Time window for circuit breaker (seconds)"
    )
    
    # Cooldown logic
    cooldown_after_losses: int = Field(
        default=3,
        description="Number of consecutive losses before cooldown"
    )
    cooldown_duration_seconds: int = Field(
        default=300,
        description="Cooldown duration after consecutive losses (seconds)"
    )
    
    # Order validation
    min_order_size: float = Field(
        default=1.0,
        description="Minimum order size"
    )
    max_order_size: float = Field(
        default=10000.0,
        description="Maximum order size"
    )
    
    class Config:
        env_prefix = "RISK_"
        case_sensitive = False


def load_risk_limits(config_path: Optional[str] = None) -> RiskLimits:
    """
    Load risk limits from config file or environment variables.
    
    Args:
        config_path: Path to YAML/JSON config file (optional)
        
    Returns:
        RiskLimits instance
    """
    if config_path and os.path.exists(config_path):
        # Load from file (YAML or JSON)
        import json
        import yaml
        
        with open(config_path, 'r') as f:
            if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                data = yaml.safe_load(f)
            else:
                data = json.load(f)
        
        return RiskLimits(**data)
    else:
        # Load from environment variables or use defaults
        return RiskLimits(
            max_position_per_symbol=float(os.getenv('RISK_MAX_POSITION_PER_SYMBOL', '10000')),
            max_total_position=float(os.getenv('RISK_MAX_TOTAL_POSITION', '100000')),
            max_daily_loss=float(os.getenv('RISK_MAX_DAILY_LOSS', '5000')),
            max_trade_loss=float(os.getenv('RISK_MAX_TRADE_LOSS', '1000')),
            max_exposure_pct=float(os.getenv('RISK_MAX_EXPOSURE_PCT', '50')),
            max_trades_per_minute=int(os.getenv('RISK_MAX_TRADES_PER_MINUTE', '10')),
            circuit_breaker_pct=float(os.getenv('RISK_CIRCUIT_BREAKER_PCT', '5')),
        )


# Default risk limits instance
default_risk_limits = RiskLimits()








