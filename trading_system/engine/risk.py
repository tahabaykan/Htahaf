"""engine/risk.py

Risk kontrol wrapper - signals'ları kontrol edip orders stream'ine yazar.

Bu modül signals stream'ini tüketir, risk kontrollerini yapar ve
uygun olanları orders stream'ine yazar.

Risk kontrolleri:
    - Position limits
    - Daily loss limits
    - Per-symbol limits
    - Account balance checks
    - vb.

Kullanım:
    python engine/risk.py

Not: Bu basit bir örnek. Gerçek sistemde daha kapsamlı risk yönetimi gerekir.
"""

import asyncio
from typing import Dict, Any, Optional
from engine.data_bus import RedisBus

SIGNALS_STREAM = 'signals'
ORDERS_STREAM = 'orders'
RISK_GROUP = 'risk_group'


async def risk_check(signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Signal için risk kontrolü yap.
    
    Args:
        signal: Signal dict
        
    Returns:
        Order dict (risk geçtiyse) veya None
    """
    # DEMO: Basit risk kontrolü
    # Gerçek sistemde:
    # - Position size kontrolü
    # - Account balance kontrolü
    # - Daily P&L limit kontrolü
    # - Per-symbol limit kontrolü
    # - Market hours kontrolü
    # yapılır
    
    symbol = signal.get('symbol', '')
    signal_type = signal.get('signal', '')
    price = float(signal.get('price', 0))
    
    if not symbol or not signal_type or price <= 0:
        return None
    
    # Basit örnek: Her signal'ı order'a çevir (risk kontrolü geçti say)
    order = {
        'symbol': symbol,
        'action': signal_type,  # BUY/SELL
        'price': signal.get('price'),
        'quantity': 100,  # Default quantity (gerçek sistemde hesaplanır)
        'order_type': 'LIMIT',
        'ts': signal.get('ts', ''),
        'signal_id': signal.get('ts', '')  # Trace için
    }
    
    return order


async def risk_worker_loop(consumer_name: str = 'risk1'):
    """
    Risk kontrol worker loop - signals stream'ini tüketir, orders'a yazar.
    
    Args:
        consumer_name: Consumer adı
    """
    bus = RedisBus()
    await bus.connect()
    await bus.ensure_group(SIGNALS_STREAM, RISK_GROUP)
    
    try:
        while True:
            messages = await bus.read_group(
                SIGNALS_STREAM,
                RISK_GROUP,
                consumer_name,
                block=2000,
                count=20
            )
            
            if not messages:
                await asyncio.sleep(0.1)
                continue
            
            for msg_id, signal_data in messages:
                try:
                    # Risk kontrolü
                    order = await risk_check(signal_data)
                    
                    if order:
                        # Order'ı orders stream'ine yaz
                        await bus.publish(ORDERS_STREAM, order)
                    
                    # ACK
                    await bus.ack(SIGNALS_STREAM, RISK_GROUP, msg_id)
                    
                except Exception as e:
                    # Hata durumunda logla ve ACK et (retry yok)
                    print(f"[RISK] Error processing signal: {e}")
                    await bus.ack(SIGNALS_STREAM, RISK_GROUP, msg_id)
    
    finally:
        await bus.close()


if __name__ == '__main__':
    asyncio.run(risk_worker_loop())








