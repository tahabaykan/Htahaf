# Trading System Skeleton — Professional, Cloud-ready

Bu repository, **500+ ticker izleyebilen**, **arka planda (server) çalışan**, **PyQt istemcisiyle** bağlanan, **Redis Streams** tabanlı, **IBKR-compatible** algoritmik trading sisteminin minimal, production-ready skeleton'ıdır. Her dosya için açıklayıcı README/yorum satırları ve çalıştırma adımları eklendi — böylece başka bir ajan veya yeni bir sohbet açıldığında dosyaları kolayca anlayıp devam edebilir.

> **Not:** Bu skeleton *örnek* ve başlangıç içindir. Gerçek IB contract detayları, kimlik bilgileri, secret'lar ve production güvenlik adımları projeye eklenmelidir.

---

## 📁 Proje Yapısı

```
trading_system/
├── collector/             # Market data publisher
│   └── publish_tick.py   # Demo tick publisher
├── engine/               # Core async engine, worker pool, signal pipeline
│   ├── __init__.py
│   ├── core.py           # Event loop + service bootstrap
│   ├── data_bus.py       # Redis Streams wrapper
│   ├── strategy.py       # Örnek strategy (score hesaplama)
│   ├── risk.py           # Risk kontrol wrapper
│   └── order_manager.py  # Orders -> router (xadd to orders)
├── router/               # Order routing, token-bucket throttling, ib_insync integration
│   └── order_router.py   # IBKR order router
├── ui/                   # PyQt client (lightweight), WebSocket client wrapper
│   └── pyqt_client.py    # PyQt trading terminal
├── db/                   # DB writer (Postgres/Timescale) örneği
│   └── writer.py         # Execution writer
├── utils/
│   ├── token_bucket.py   # Rate limiter
│   └── logging_config.py # Logging setup
├── docker-compose.yml    # Redis + Postgres
├── requirements.txt      # Python dependencies
└── README.md             # Bu dosya
```

---

## 🚀 Hızlı Başlangıç (Local, Development)

### 1. Gereksinimler

- Python 3.8+
- Redis (Docker veya local)
- Postgres (opsiyonel, DB writer için)
- IBKR TWS/Gateway (order router için)

### 2. Redis ve Postgres Kurulumu

**Docker ile (önerilen):**
```bash
docker compose up -d redis postgres
```

**Veya manuel:**
```bash
# Redis
redis-server

# Postgres
# Sisteminize göre kurulum yapın
```

### 3. Python Ortamı ve Bağımlılıklar

```bash
# Virtualenv oluştur
python -m venv .venv

# Aktif et
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# Bağımlılıkları kur
pip install -r requirements.txt
```

### 4. Çalıştırma Sırası (Development Mode)

**Terminal 1 - Tick Publisher:**
```bash
python collector/publish_tick.py
```

**Terminal 2 - Engine (Strategy Worker):**
```bash
python engine/core.py
```

**Terminal 3 - Risk Manager (Opsiyonel):**
```bash
python engine/risk.py
```

**Terminal 4 - Order Router:**
```bash
# IBKR TWS/Gateway çalışıyor olmalı
python router/order_router.py
```

**Terminal 5 - DB Writer (Opsiyonel):**
```bash
# Postgres çalışıyor olmalı
python db/writer.py
```

**Terminal 6 - PyQt Client:**
```bash
python ui/pyqt_client.py
```

---

## 📋 Environment Variables

Her servis için environment variable'lar ayarlanabilir:

### Genel
- `REDIS_URL`: Redis connection URL (default: `redis://localhost:6379`)
- `LOG_LEVEL`: Log seviyesi (default: `INFO`)

### Engine (core.py)
- `WORKER_NAME`: Worker instance adı (default: `worker1`)
- `WORKER_COUNT`: Worker sayısı (default: `1`)
- `BATCH_SIZE`: Batch processing size (default: `20`)

### Router (order_router.py)
- `IBKR_HOST`: IBKR TWS/Gateway host (default: `127.0.0.1`)
- `IBKR_PORT`: IBKR TWS/Gateway port (default: `4001`)
- `IBKR_CLIENT_ID`: IBKR client ID (default: `1`)
- `RATE_LIMIT`: Orders per second (default: `1.0`)
- `BUCKET_CAPACITY`: Burst capacity (default: `5`)

### Collector (publish_tick.py)
- `N_SYMBOLS`: Symbol sayısı (default: `50`)
- `DELAY`: Tick arası gecikme (saniye, default: `0.1`)

### DB Writer (writer.py)
- `PG_DSN`: Postgres connection string (default: `postgresql://user:pass@localhost:5432/trades`)

---

## 🔧 Dosya Açıklamaları

### `collector/publish_tick.py`
Demo tick publisher. Gerçek market data feed'iniz benzer bir `xadd('ticks', {...})` çağrısı yapmalı.

### `engine/data_bus.py`
Redis Streams wrapper. Tüm servisler bu modülü kullanarak Redis ile iletişim kurar.

### `engine/strategy.py`
Basit score-based strategy. Gerçek sistemde ML/istatistik/kural tabanlı logic buraya eklenir.

### `engine/core.py`
Ana engine. Ticks stream'ini tüketir, strategy'yi çağırır, signals üretir. Multiple worker instance'lar ile ölçeklenebilir.

### `engine/risk.py`
Risk kontrol servisi. Signals'ları kontrol edip orders stream'ine yazar.

### `engine/order_manager.py`
Strategy ile router arasında köprü. Signals'ları Redis'e yazar.

### `router/order_router.py`
Orders stream'ini tüketir, IBKR'ye order gönderir. Token bucket ile rate limiting, ib_insync integration.

### `ui/pyqt_client.py`
PyQt5 trading terminal. Redis pub/sub veya WebSocket ile real-time data gösterir.

### `db/writer.py`
Executions'ları Postgres/TimescaleDB'ye yazar.

---

## 🐳 Docker Deployment

```bash
# Redis + Postgres başlat
docker compose up -d

# Servisleri çalıştır (yukarıdaki gibi)
```

---

## 🔐 Production Notları

1. **IBKR Credentials**: Gerçek IB contract detayları, kimlik bilgileri, secret'lar eklenmelidir.
2. **Security**: Environment variables, secret management (Vault, AWS Secrets Manager, vb.)
3. **Monitoring**: Metrics collection (Prometheus, Grafana)
4. **Error Handling**: Retry logic, circuit breakers
5. **Scaling**: Kubernetes manifests, horizontal scaling
6. **Database**: TimescaleDB için hypertable setup
7. **Logging**: Centralized logging (ELK, Loki)

---

## 📝 Geliştirme Planı

### Kısa Vadeli
- [ ] Gerçek market data feed entegrasyonu
- [ ] Strategy logic geliştirme (ML/technical indicators)
- [ ] Risk management detaylandırma
- [ ] WebSocket API ekleme

### Orta Vadeli
- [ ] Backtesting framework
- [ ] Portfolio management
- [ ] Performance analytics
- [ ] Alert system

### Uzun Vadeli
- [ ] Multi-broker support
- [ ] Cloud deployment (AWS/GCP)
- [ ] Kubernetes manifests
- [ ] CI/CD pipeline

---

## 🤝 Katkıda Bulunma

Bu skeleton başlangıç noktasıdır. Gerçek trading logic, risk management, ve production güvenlik adımları projeye eklenmelidir.

---

## 📄 Lisans

Bu proje örnek amaçlıdır. Kendi sorumluluğunuzda kullanın.

---

## 🆘 Sorun Giderme

### Redis bağlantı hatası
```bash
# Redis çalışıyor mu?
redis-cli ping
# PONG dönmeli
```

### IBKR bağlantı hatası
- TWS/Gateway çalışıyor mu?
- Port doğru mu? (4001 live, 4002 paper)
- API izinleri aktif mi?

### Postgres bağlantı hatası
- Postgres çalışıyor mu?
- Connection string doğru mu?
- Database oluşturuldu mu?

---

**Not:** Bu skeleton production-ready değildir. Gerçek trading için kapsamlı test ve güvenlik önlemleri gereklidir.








