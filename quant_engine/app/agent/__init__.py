"""
Trading Observer Agent
AI-powered trading system monitor with dual-provider support.

Primary: Gemini 2.0 Flash (free tier — 1500 RPD).
Fallback: Claude Haiku 3.5 (~$1/month) — auto-activates on Gemini quota exhaust.

Monitors dual process execution, detects anomalies, and provides
natural language insights every 10 minutes during market hours.
"""

from app.agent.trading_observer import (
    TradingObserverAgent,
    get_trading_observer,
    start_trading_observer,
    stop_trading_observer,
)
