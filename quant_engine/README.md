# quant_engine

Professional algorithmic trading backend engine.

Modular, scalable, cloud-ready architecture.

Communicates through Redis to UI.

## Architecture

```
quant_engine/
├── app/
│   ├── config/          # Configuration management
│   ├── core/            # Core utilities (Redis, Logger, EventBus)
│   ├── ibkr/            # IBKR integration
│   ├── market_data/     # Market data ingestion
│   ├── strategy/        # Strategy framework
│   ├── engine/          # Trading engine
│   ├── api/             # FastAPI REST/WebSocket API
│   └── utils/           # Utility functions
├── docker-compose.yml
├── requirements.txt
├── main.py              # Main entry point
└── .env.example
```

## Quick Start

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment:
```bash
# Create .env file (copy from .env.example or create manually)
# Edit .env with your settings:
#   REDIS_HOST=localhost
#   REDIS_PORT=6379
#   IBKR_HOST=127.0.0.1
#   IBKR_PORT=7497
```

3. Start Redis:
```bash
docker compose up -d redis
```

4. Run engine:
```bash
# Sync mode (Redis pub/sub)
python main.py engine

# Async mode (Redis streams) - Recommended
python main.py engine-async

# API server
python main.py api

# Both engine and API
python main.py all
```

## Features

- ✅ Modular architecture
- ✅ Redis-based event bus (pub/sub + streams)
- ✅ IBKR integration (ib_insync)
- ✅ Strategy framework (extensible, indicators, candles)
- ✅ **Risk Manager** (position limits, daily loss, circuit breaker)
- ✅ Position tracking (FIFO, P&L calculation)
- ✅ Execution pipeline (IBKR → Position sync)
- ✅ REST API (FastAPI)
- ✅ Async support
- ✅ Comprehensive logging

## Project Structure

### Core Modules

- **config/**: Pydantic-based configuration management
- **core/**: Redis client, logger, event bus
- **ibkr/**: IBKR TWS/Gateway integration
- **strategy/**: Strategy base class and examples
- **engine/**: Trading engine loop, position manager, risk manager
- **api/**: FastAPI REST API
- **market_data/**: Market data ingestion (Hammer PRO stub)

## Development

### Running Tests

```bash
# Run all tests
python tests/test_runner.py --all

# Run specific test suite
python tests/test_runner.py --unit
python tests/test_runner.py --integration
python tests/test_runner.py --load
python tests/test_runner.py --fault

# Using pytest directly
pytest tests/ -v
```

See [Testing Guide](./docs/TESTING_GUIDE.md) for details.

### Running Engine

```bash
# Run engine in async mode
python main.py engine-async

# Run API server
python main.py api
```

### Environment Variables

See `.env.example` for all available configuration options.

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- [Execution Pipeline](./docs/EXECUTION_PIPELINE.md) - Execution flow and processing
- [Position Manager](./docs/POSITION_MANAGER.md) - Position tracking and P&L
- [IBKR Sync](./docs/IBKR_SYNC.md) - IBKR synchronization
- [Test Scripts](./docs/test_scripts.md) - Testing and validation

## Next Steps

1. ✅ Execution → Position pipeline (completed)
2. ✅ IBKR synchronization (completed)
3. ✅ Strategy Engine (completed)
4. ✅ Risk Manager (completed)
5. ⏳ Live Metrics & P&L Dashboard
6. ⏳ WebSocket UI (FastAPI Dashboard)
7. ⏳ Prometheus metrics
8. ⏳ Grafana dashboards
9. ⏳ Production deployment setup
