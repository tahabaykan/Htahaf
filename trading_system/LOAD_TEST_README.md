# Load Test ve Smoke Test Kılavuzu

Bu dokümantasyon load test ve smoke test araçlarının kullanımını açıklar.

## 📋 İçindekiler

1. [Smoke Test](#smoke-test)
2. [Load Test](#load-test)
3. [Metrikler ve Monitoring](#metrikler-ve-monitoring)

---

## 🧪 Smoke Test

Smoke test, tüm sistemin end-to-end çalıştığını doğrulamak için kullanılır.

### Hızlı Başlangıç

```bash
# 1. Docker servisleri başlat
docker compose up -d redis postgres

# 2. Virtualenv aktif et
source .venv/bin/activate  # Linux/Mac
# veya
.venv\Scripts\activate  # Windows

# 3. Smoke test çalıştır
./run_smoke.sh
```

### Manuel Smoke Test

```bash
# Terminal 1 - Tick Publisher
python collector/publish_tick.py

# Terminal 2 - Engine
python engine/core.py

# Terminal 3 - Router (Mock)
python router/order_router.py

# Terminal 4 - DB Writer
python db/writer.py

# Terminal 5 - UI
python ui/pyqt_client.py
```

### Smoke Test Kontrolleri

Smoke test şunları kontrol eder:
- ✅ Redis bağlantısı
- ✅ Tick publisher çalışıyor mu?
- ✅ Engine ticks stream'ini tüketiyor mu?
- ✅ Signals üretiliyor mu?
- ✅ Orders stream'e yazılıyor mu?
- ✅ Executions kaydediliyor mu?

### Sonuçlar

Smoke test sonunda şu bilgiler gösterilir:
- Stream uzunlukları (ticks, signals, orders, execs)
- Process durumları
- Log dosyaları (`logs/` dizininde)

---

## 📊 Load Test

Load test, sistemin farklı yük seviyelerinde nasıl performans gösterdiğini ölçer.

### Hızlı Başlangıç

```bash
# 1. Tek bir senaryo test et
python load_test/fake_tick_publisher.py --symbols 500 --rate 10 --duration 60

# 2. Otomatik load test (birden fazla senaryo)
python load_test/run_load_test.py --output results.csv
```

### Load Test Senaryoları

Varsayılan senaryolar:
- **50 symbols**, 5 ticks/s, 30s
- **200 symbols**, 10 ticks/s, 30s
- **500 symbols**, 20 ticks/s, 30s

### Özel Senaryolar

JSON dosyası ile özel senaryolar tanımlanabilir:

```json
[
    {
        "symbols": 100,
        "tick_rate": 5.0,
        "duration": 60
    },
    {
        "symbols": 500,
        "tick_rate": 20.0,
        "duration": 120
    }
]
```

```bash
python load_test/run_load_test.py --scenarios scenarios.json --output results.csv
```

### Ölçülen Metrikler

Load test şu metrikleri toplar:
- **Stream uzunlukları**: ticks, signals, orders, execs
- **Pending mesaj sayıları**: consumer group'larda bekleyen mesajlar
- **Redis metrikleri**: memory usage, connected clients
- **Sistem metrikleri**: CPU %, RAM %
- **Throughput**: ticks/s, signals/s, orders/s

### Sonuçlar

Load test sonuçları CSV formatında kaydedilir:

```csv
timestamp,symbols,tick_rate,duration,ticks_produced,signals_produced,orders_produced,execs_produced,avg_pending_ticks,avg_pending_signals,avg_pending_orders,redis_memory_mb,redis_connected_clients,cpu_percent,mem_percent,mem_used_mb
2024-01-01T12:00:00,50,5.0,30,1500,75,75,75,0,0,0,50.2,3,25.5,45.2,2048
```

---

## 📈 Metrikler ve Monitoring

### Prometheus Metrikleri

Engine, Prometheus metrikleri expose eder (port 8001):

- `engine_ticks_processed_total`: İşlenen tick sayısı
- `engine_signals_generated_total`: Üretilen signal sayısı
- `engine_processing_errors_total`: İşleme hataları
- `engine_processing_latency_seconds`: İşleme gecikmesi
- `engine_pending_messages`: Pending mesaj sayısı
- `engine_worker_health`: Worker sağlık durumu

### Metrikleri Görüntüleme

```bash
# Prometheus metriklerini görüntüle
curl http://localhost:8001/metrics

# Grafana ile görselleştir (Grafana dashboard JSON'u eklenebilir)
```

### Redis Monitoring

```bash
# Redis info
redis-cli info

# Stream uzunlukları
redis-cli XLEN ticks
redis-cli XLEN signals
redis-cli XLEN orders
redis-cli XLEN execs

# Consumer group bilgileri
redis-cli XPENDING ticks strategy_group
```

### Sistem Monitoring

```bash
# CPU ve RAM kullanımı
htop

# Process monitoring
ps aux | grep python

# Network monitoring
netstat -tuln | grep 6379  # Redis
netstat -tuln | grep 8001  # Prometheus
```

---

## 🔧 Troubleshooting

### Redis Bağlantı Hatası

```bash
# Redis çalışıyor mu?
redis-cli ping
# PONG dönmeli

# Docker ile başlat
docker compose up -d redis
```

### Yüksek Pending Mesajlar

Eğer pending mesaj sayısı sürekli artıyorsa:
- Worker sayısını artırın: `WORKER_COUNT=3 python engine/core.py`
- Batch size'ı artırın: `BATCH_SIZE=50 python engine/core.py`
- Worker'ların yeterince hızlı çalıştığından emin olun

### Yüksek CPU Kullanımı

- Worker sayısını azaltın
- Batch size'ı optimize edin
- Strategy logic'i optimize edin

### Yüksek Memory Kullanımı

- Redis memory limit ayarlayın
- Batch size'ı azaltın
- Stream retention policy ekleyin

---

## 📝 Notlar

- Load test sırasında gerçek IBKR bağlantısı kullanılmaz (mock mode)
- Production'da load test yapmadan önce test ortamında deneyin
- Yüksek yük testlerinde sistem kaynaklarını izleyin
- Load test sonuçlarını düzenli olarak kaydedin ve karşılaştırın

---

## 🚀 Sonraki Adımlar

1. **Monitoring Dashboard**: Grafana dashboard JSON'u ekle
2. **Alerting**: Prometheus alerting rules ekle
3. **Auto-scaling**: Worker sayısını otomatik ayarla
4. **Performance Tuning**: Load test sonuçlarına göre optimize et








