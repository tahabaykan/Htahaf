# Hammer PRO Market Data Integration

Bu dokümantasyon Hammer PRO market data ingestion'ının nasıl çalıştığını ve nasıl kullanılacağını açıklar.

## 📋 İçindekiler

1. [Genel Bakış](#genel-bakış)
2. [Kullanım](#kullanım)
3. [Veri Akışı](#veri-akışı)
4. [Gerçek Hammer PRO API Entegrasyonu](#gerçek-hammer-pro-api-entegrasyonu)

---

## 🎯 Genel Bakış

Hammer PRO market data ingestion sistemi şu bileşenlerden oluşur:

- **HammerIngest**: Market data'yı okuyup Redis'e yayınlayan ana sınıf
- **hammer_fake_feed**: Test için fake data üreten generator
- **HammerProAPI**: Gerçek Hammer PRO API entegrasyonu (placeholder)

### Veri Akışı

```
Hammer PRO API → HammerIngest → Redis Pub/Sub ("ticks") → Engine → Strategy
```

---

## 🚀 Kullanım

### 1. Fake Feed ile Test

```bash
# Terminal 1: Hammer ingest başlat (fake data)
python main.py hammer --symbol AAPL

# Terminal 2: Engine başlat
python main.py engine-async
```

### 2. Birden Fazla Symbol

```python
from app.market_data.hammer_api_stub import hammer_fake_feed_multi
from app.market_data.hammer_ingest_stub import HammerIngest

# Multiple symbols
symbols = ["AAPL", "MSFT", "GOOGL"]
feed = hammer_fake_feed_multi(symbols, delay=0.05)

ingest = HammerIngest(feed_reader=feed)
ingest.start()
```

### 3. Programatik Kullanım

```python
from app.market_data.hammer_ingest_stub import HammerIngest
from app.market_data.hammer_api_stub import hammer_fake_feed

# Create feed reader
feed = hammer_fake_feed("AAPL", delay=0.05)

# Create and start ingestor
ingest = HammerIngest(feed_reader=feed)
ingest.start()

# ... do other work ...

# Stop when done
ingest.stop()
```

---

## 📊 Veri Formatı

### Hammer PRO Format (Input)

Hammer PRO'dan gelen tick formatı (örnek):

```python
{
    "symbol": "AAPL",
    "last": 178.52,
    "bid": 178.50,
    "ask": 178.53,
    "volume": 1203412,
    "timestamp": 1700000000123
}
```

### Normalize Edilmiş Format (Output)

Redis'e yayınlanan format:

```python
{
    "symbol": "AAPL",
    "last": "178.52",      # String (JSON compatibility)
    "bid": "178.50",
    "ask": "178.53",
    "volume": "1203412",
    "ts": "1700000000123"  # Timestamp in milliseconds
}
```

### Engine'de Kullanım

Engine, Redis'ten gelen tick'leri şu şekilde alır:

```python
# engine_loop.py içinde
tick = json.loads(message["data"])  # JSON string'den parse
symbol = tick.get("symbol")
last_price = float(tick.get("last"))
```

---

## 🔧 Gerçek Hammer PRO API Entegrasyonu

### Adım 1: API Client Oluştur

`app/market_data/hammer_api_stub.py` dosyasındaki `HammerProAPI` sınıfını gerçek API ile değiştirin:

```python
class HammerProAPI:
    def __init__(self, api_key: str, api_url: str = "https://api.hammerpro.com"):
        self.api_key = api_key
        self.api_url = api_url
        # Real API client initialization
        self.client = HammerProClient(api_key, api_url)
    
    def get_ticks(self, symbol: str) -> Iterator[Dict[str, Any]]:
        """Get real-time ticks from Hammer PRO"""
        # Real API call
        stream = self.client.stream_ticks(symbol)
        for tick in stream:
            yield tick
```

### Adım 2: Environment Variables

`.env` dosyasına Hammer PRO credentials ekleyin:

```bash
HAMMER_API_KEY=your_api_key_here
HAMMER_API_URL=https://api.hammerpro.com
```

### Adım 3: Kullanım

```bash
# Real Hammer PRO feed kullan
python main.py hammer --symbol AAPL --real-feed
```

---

## 🐛 Troubleshooting

### Problem: Engine tick almıyor

**Çözüm:**
1. Redis'in çalıştığından emin olun: `redis-cli ping`
2. Hammer ingest'in çalıştığını kontrol edin
3. Redis pub/sub channel'ını kontrol edin: `redis-cli PUBSUB CHANNELS`

### Problem: Tick formatı uyumsuz

**Çözüm:**
1. `_normalize_tick()` metodunu gerçek Hammer PRO formatına göre güncelleyin
2. Log'larda raw tick formatını kontrol edin

### Problem: Yüksek CPU kullanımı

**Çözüm:**
1. `delay` parametresini artırın (örn: 0.1 saniye)
2. Batch processing ekleyin

---

## 📝 Notlar

- Fake feed sadece test için kullanılmalıdır
- Production'da mutlaka gerçek Hammer PRO API kullanın
- Tick rate'i ihtiyacınıza göre ayarlayın (delay parametresi)
- Multiple symbol feed'leri için `hammer_fake_feed_multi` kullanın

---

## 🎯 Sonraki Adımlar

1. ✅ Fake feed implementasyonu (tamamlandı)
2. ⏳ Gerçek Hammer PRO API entegrasyonu
3. ⏳ Error handling ve retry logic
4. ⏳ Rate limiting ve backpressure
5. ⏳ Metrics ve monitoring






