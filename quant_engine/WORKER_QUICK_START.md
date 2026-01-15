# Worker Quick Start Guide

## 🚀 Hızlı Başlangıç

### 1. Redis'i Başlat (Otomatik)

`baslat.py` çalıştığında Redis otomatik başlar. Manuel başlatmak için:

```bash
docker start redis-quant-engine
```

### 2. Ana Uygulamayı Başlat (Terminal 1)

```bash
cd quant_engine
python baslat.py
```

Bu terminal'de:
- FastAPI server çalışır (Port 8000)
- Emir girişi yapılabilir
- WebSocket bağlantıları aktif
- **ASLA BLOKLANMAZ** (worker ayrı terminal'de)

### 3. Worker'ı Başlat (Terminal 2)

**Windows:**
```bash
cd quant_engine
workers\start_worker.bat
```

**Linux/Mac:**
```bash
cd quant_engine
./workers/start_worker.sh
```

Bu terminal'de:
- Redis'ten job'ları alır
- GOD/ROD/GRPAN hesaplar
- Sonuçları Redis'e yazar
- **Ana uygulamayı bloklamaz**

### 4. Birden Fazla Worker (Terminal 3, 4, ...)

Yük dağılımı için:

**Windows:**
```bash
# Terminal 3
set WORKER_NAME=worker2
python workers\run_deeper_worker.py

# Terminal 4
set WORKER_NAME=worker3
python workers\run_deeper_worker.py
```

**Linux/Mac:**
```bash
# Terminal 3
export WORKER_NAME=worker2
python workers/run_deeper_worker.py

# Terminal 4
export WORKER_NAME=worker3
python workers/run_deeper_worker.py
```

## 📊 Veri Akışı

```
Frontend (React)
    ↓ POST /api/deeper-analysis/compute
FastAPI (Terminal 1)
    ↓ Job ekler
Redis Queue
    ↓ BRPOP (blocking)
Worker (Terminal 2+)
    ↓ Hesaplar (GOD/ROD/GRPAN)
Redis Results
    ↓ GET /api/deeper-analysis/result/{job_id}
FastAPI (Terminal 1)
    ↓
Frontend (React)
```

## ✅ Test Etme

1. Frontend'i aç: `http://localhost:3000`
2. "Deeper Analysis" sayfasına git
3. "Refresh" butonuna tıkla
4. Terminal 2'de job işlendiğini gör

## 🔍 Kontrol

### Worker Çalışıyor mu?

Terminal 2'de şunu görmelisin:
```
✅ Worker worker1 connected to Redis
🚀 Worker worker1 started
```

### Job İşleniyor mu?

Terminal 2'de şunu görmelisin:
```
🔄 [worker1] Processing job abc-123-def
📊 Processing 150 symbols for job abc-123-def
✅ Job abc-123-def completed: 150/150 symbols processed
```

### Redis Queue'da Job Var mı?

```bash
docker exec -it redis-quant-engine redis-cli LLEN deeper_analysis:jobs
```

## 🎯 Avantajlar

- ✅ **Ana uygulama asla bloklanmaz** - emir girişi her zaman aktif
- ✅ **Ölçeklenebilir** - istediğin kadar worker çalıştırabilirsin
- ✅ **Fault tolerant** - bir worker çökerse diğerleri devam eder
- ✅ **Esnek** - başka script'ler Redis'ten okuyabilir

## 📚 Detaylı Dokümantasyon

- `workers/README.md` - Worker detayları
- `workers/MULTI_TERMINAL_SETUP.md` - Multi-terminal setup guide

## ⚠️ Önemli Notlar

1. **Redis çalışmalı** - Worker Redis'e bağlanamazsa çalışmaz
2. **Tick-by-tick enabled olmalı** - DataFabric'te tick-by-tick açık olmalı
3. **Worker ayrı terminal'de** - Ana uygulamayla aynı terminal'de çalıştırma

## 🆘 Sorun Giderme

### Worker Redis'e bağlanamıyor

```bash
# Redis çalışıyor mu?
docker ps | grep redis

# Redis'i başlat
docker start redis-quant-engine
```

### Job'lar işlenmiyor

1. Worker çalışıyor mu? (Terminal 2'yi kontrol et)
2. Redis queue'da job var mı?
3. Worker log'larında hata var mı?

### Sonuçlar görünmüyor

1. Job tamamlandı mı? (Status: completed)
2. Redis'te result var mı?
3. Frontend doğru endpoint'e istek atıyor mu?


