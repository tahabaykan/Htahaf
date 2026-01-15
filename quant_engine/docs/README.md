# Documentation Index

Bu klasör quant_engine projesinin tüm dokümantasyonunu içerir.

## 📚 Dokümantasyon Listesi

### Core Pipeline Documentation

1. **[Execution Pipeline](./EXECUTION_PIPELINE.md)**
   - Execution flow: IBKR → OrderRouter → Redis → ExecutionHandler → PositionManager
   - Message formats
   - Error handling
   - Usage examples
   - Troubleshooting

2. **[Position Manager](./POSITION_MANAGER.md)**
   - FIFO price calculation
   - Position flip handling
   - Realized/unrealized P&L
   - State snapshots
   - Strategy integration

3. **[IBKR Sync](./IBKR_SYNC.md)**
   - Position synchronization
   - Order fetching
   - Account summary
   - Startup sync sequence
   - Offline/online mode

4. **[Strategy Engine](./STRATEGY_ENGINE.md)**
   - Strategy framework
   - Indicators (SMA, EMA, RSI, MACD)
   - Candle management
   - Multi-symbol support
   - Hot-reload

5. **[Risk Manager](./RISK_MANAGER.md)**
   - Risk limits configuration
   - Pre-trade validation
   - Circuit breaker
   - Cooldown logic
   - Exposure tracking

### Testing & Validation

4. **[Test Scripts](./test_scripts.md)**
   - Full pipeline test
   - Execution injection test
   - Position flip test
   - IBKR sync test
   - Performance tests

## 🚀 Quick Links

- [Main README](../README.md) - Project overview
- [Order Pipeline](../ORDER_PIPELINE.md) - Order flow
- [Hammer Integration](../HAMMER_INTEGRATION.md) - Market data

## 📖 Reading Order

Yeni başlayanlar için önerilen okuma sırası:

1. [Main README](../README.md) - Genel bakış
2. [Execution Pipeline](./EXECUTION_PIPELINE.md) - Execution akışı
3. [Position Manager](./POSITION_MANAGER.md) - Position tracking
4. [IBKR Sync](./IBKR_SYNC.md) - Synchronization
5. [Test Scripts](./test_scripts.md) - Testing

## 🔍 Troubleshooting

Sorun yaşıyorsanız:

1. İlgili dokümantasyonu okuyun
2. [Test Scripts](./test_scripts.md) ile test edin
3. Log dosyalarını kontrol edin
4. Redis ve IBKR bağlantılarını doğrulayın

