"""engine/order_manager.py

Strategy'den gelen sinyalleri alıp Redis `signals` stream'ine koyar.

Bu modül strategy ile router arasında köprü görevi görür. Strategy'den gelen
signals'ları Redis'e yazar, risk kontrol servisi bunları okuyup kontrol eder,
ardından `orders` stream'ine yazar.

Kullanım:
    from engine.order_manager import push_signal
    
    signal = {'symbol': 'AAPL', 'signal': 'BUY', 'price': '150.0'}
    await push_signal(signal)

Not: Risk kontrolü ayrı bir serviste (risk.py) yapılacak. Bu modül sadece
signal'ları Redis'e yazar.
"""

import asyncio
from typing import Dict, Any
from engine.data_bus import RedisBus

SIGNALS_STREAM = 'signals'


async def push_signal(signal: Dict[str, Any]):
    """
    Signal'ı Redis signals stream'ine yaz.
    
    Args:
        signal: Signal dict (symbol, signal, price, ts, vb.)
    """
    bus = RedisBus()
    try:
        await bus.connect()
        await bus.publish(SIGNALS_STREAM, signal)
    finally:
        await bus.close()


async def push_signals_batch(signals: list):
    """
    Birden fazla signal'ı batch olarak yaz.
    
    Args:
        signals: Signal dict listesi
    """
    bus = RedisBus()
    try:
        await bus.connect()
        for signal in signals:
            await bus.publish(SIGNALS_STREAM, signal)
    finally:
        await bus.close()








