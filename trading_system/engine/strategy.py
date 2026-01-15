"""engine/strategy.py

Basit "score" üreten strategy örneği. Gerçek sistemde burası ML/istatistik/kural tabanlı olacaktır.

Bu modül strategy logic'ini içerir. Her tick için bir score hesaplanır ve
eğer threshold aşılırsa bir signal üretilir.

Kullanım:
    signal = await compute_score(tick)
    if signal:
        # Signal üretildi, order_manager'a gönder
        await push_signal(signal)

Not: Gerçek sistemde bu fonksiyon CPU yoğun olabilir. Bu durumda
ProcessPoolExecutor kullanılmalı veya ayrı bir worker process'te çalıştırılmalı.
"""

import time
from typing import Optional, Dict, Any


async def compute_score(tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Tick'ten score hesapla ve signal üret.
    
    Args:
        tick: Tick data dict (keys: symbol, last, bid, ask, ts, vb.)
        
    Returns:
        Signal dict veya None (signal yoksa)
        
    Signal format:
        {
            'symbol': str,
            'signal': 'BUY' | 'SELL',
            'price': str (float as string),
            'quantity': int (optional),
            'ts': str (timestamp),
            'score': float (optional),
            'reason': str (optional)
        }
    """
    try:
        symbol = tick.get('symbol', '')
        last_price = float(tick.get('last', 0))
        
        if not symbol or last_price <= 0:
            return None
        
        # DEMO: Basit modulus-based score
        # Gerçek sistemde burada:
        # - Technical indicators (RSI, MACD, vb.)
        # - ML model predictions
        # - Statistical analysis
        # - Risk metrics
        # hesaplanır
        
        score = (last_price % 5)
        
        # Threshold kontrolü
        if score > 4.5:
            signal = {
                'symbol': symbol,
                'signal': 'BUY',
                'price': str(last_price),
                'ts': str(time.time()),
                'score': score,
                'reason': 'demo_score_threshold'
            }
            return signal
        elif score < 0.5:
            signal = {
                'symbol': symbol,
                'signal': 'SELL',
                'price': str(last_price),
                'ts': str(time.time()),
                'score': score,
                'reason': 'demo_score_threshold'
            }
            return signal
        
        return None
        
    except Exception as e:
        # Hata durumunda None döndür (loglama ayrı yapılabilir)
        return None


async def compute_score_batch(ticks: list) -> list:
    """
    Birden fazla tick için batch processing.
    
    Args:
        ticks: Tick dict listesi
        
    Returns:
        Signal dict listesi
    """
    signals = []
    for tick in ticks:
        signal = await compute_score(tick)
        if signal:
            signals.append(signal)
    return signals








