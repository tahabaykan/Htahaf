# Proje Yapısı Önerisi

## Mevcut Durum
- `quant_engine/` - Yeni headless trading engine (backtest, optimization, live)
- `trading_system/` - Eski sistem (collector, router)
- `janall/` - Eski Tkinter GUI

## Önerilen Yapı

```
trading_system/
├── app/
│   ├── live/              # Live trading (Hammer + IBKR)
│   │   ├── hammer_client.py
│   │   ├── hammer_feed.py
│   │   ├── hammer_execution.py
│   │   └── symbol_mapper.py
│   │
│   ├── backtest/           # Backtest engine
│   │   ├── backtest_engine.py
│   │   ├── replay_engine.py
│   │   └── execution_simulator.py
│   │
│   ├── strategy/           # Strategy framework
│   │   ├── strategy_base.py
│   │   ├── indicators.py
│   │   └── candle_manager.py
│   │
│   ├── risk/               # Risk management
│   │   ├── risk_manager.py
│   │   ├── risk_limits.py
│   │   └── monte_carlo.py
│   │
│   ├── engine/             # Core engine
│   │   ├── live_engine.py
│   │   ├── position_manager.py
│   │   └── execution_handler.py
│   │
│   ├── data/               # Data collection
│   │   ├── collector/
│   │   └── publisher.py
│   │
│   ├── order/              # Order management
│   │   ├── order_router.py
│   │   └── order_publisher.py
│   │
│   ├── ibkr/               # IBKR integration
│   │   ├── ibkr_client.py
│   │   └── ibkr_sync.py
│   │
│   ├── api/                # API server
│   │   └── main.py
│   │
│   └── optimization/       # Optimization
│       ├── advanced_optimizer.py
│       └── walk_forward_engine.py
│
├── config/                 # Configuration files
├── data/                   # Data storage
├── docs/                   # Documentation
├── tests/                  # Tests
├── main.py                 # Main entry point
└── requirements.txt        # Dependencies
```

## Migration Plan

1. **quant_engine/** → **trading_system/app/** (tüm modüller)
2. **trading_system/** (eski) → **trading_system/app/data/** (collector)
3. **janall/** → **trading_system/ui/** (optional, legacy)

## Avantajlar

✅ Tek bir ana klasör (`trading_system/`)
✅ Modüler yapı (`app/` altında)
✅ Net isimlendirme
✅ Kolay import (`from app.live import ...`)
✅ Backward compatibility (eski kodlar çalışmaya devam eder)

## Sonraki Adım

İstersen bu yapıyı oluşturabilirim:
1. `quant_engine/app/` → `trading_system/app/` taşı
2. Eski `trading_system/` içeriğini merge et
3. Import'ları güncelle
4. Test et

Devam edeyim mi?






