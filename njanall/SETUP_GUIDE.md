# njanall API Server Kurulum ve Kullanım Rehberi

## 📋 Adım 1: Gerekli Paketleri Kurun

Terminal'de şu komutu çalıştırın:

```bash
cd njanall
pip install flask flask-cors pandas numpy
```

veya

```bash
cd njanall
pip install -r requirements_api.txt
```

## 📋 Adım 2: Server'ı Başlatın

Terminal'de şu komutu çalıştırın:

```bash
cd njanall
python start_api.py
```

veya

```bash
cd njanall
python api_server.py
```

Server başladığında şu mesajı göreceksiniz:
```
🚀 njanall API Server
============================================================
📡 Server başlatılıyor...
🌐 URL: http://localhost:5000
```

## 📋 Adım 3: API'yi Test Edin

### 3.1 Tarayıcıdan Test

Tarayıcınızda şu adresi açın:
```
http://localhost:5000/health
```

Şu şekilde bir JSON yanıt görmelisiniz:
```json
{
  "status": "ok",
  "timestamp": "2024-01-01T12:00:00",
  "base_dir": "..."
}
```

### 3.2 curl ile Test (Terminal)

Yeni bir terminal penceresi açın ve şu komutu çalıştırın:

```bash
curl http://localhost:5000/health
```

### 3.3 Python ile Test

Yeni bir terminal penceresi açın:

```python
import requests

# Health check
response = requests.get('http://localhost:5000/health')
print(response.json())

# Stocks listesi
response = requests.get('http://localhost:5000/api/stocks/list')
print(response.json())
```

## 📋 Adım 4: n8n Entegrasyonu

### 4.1 n8n'de HTTP Request Node Oluşturun

1. n8n'de yeni bir workflow oluşturun
2. Bir **HTTP Request** node'u ekleyin
3. Ayarları şu şekilde yapın:
   - **Method**: GET
   - **URL**: `http://localhost:5000/api/stocks/list`
   - **Authentication**: None

### 4.2 Webhook Node Oluşturun

1. Bir **Webhook** node'u ekleyin
2. Ayarları şu şekilde yapın:
   - **Path**: `/webhook/n8n`
   - **Method**: POST
   - **Response Mode**: Respond to Webhook

### 4.3 Örnek Workflow

```
Schedule Trigger (Her saat başı)
    ↓
HTTP Request (POST /api/csv/merge)
    ↓
HTTP Request (GET /api/stocks/list)
    ↓
Function Node (Veri işleme)
    ↓
HTTP Request (POST /api/positions/add)
```

## 📋 Adım 5: API Endpoint'lerini Test Edin

### CSV Birleştirme
```bash
curl -X POST http://localhost:5000/api/csv/merge
```

### Hisseleri Listele
```bash
curl http://localhost:5000/api/stocks/list
```

### Belirli Hisse Bilgisi
```bash
curl http://localhost:5000/api/stocks/ABC
```

### Pozisyonları Listele
```bash
curl http://localhost:5000/api/positions
```

### Pozisyon Ekle
```bash
curl -X POST http://localhost:5000/api/positions/add \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "ABC",
    "direction": "long",
    "fill_price": 25.50,
    "fill_size": 100,
    "benchmark_at_fill": 26.00
  }'
```

## 🔧 Sorun Giderme

### Port Zaten Kullanılıyor
Eğer port 5000 kullanılıyorsa, `api_server.py` dosyasındaki port numarasını değiştirin:
```python
app.run(host='0.0.0.0', port=5001, debug=True)
```

### Import Hataları
```bash
# Python path'i kontrol edin
python -c "import sys; print(sys.path)"

# Modülleri kontrol edin
python -c "from janallapp.path_helper import get_csv_path; print('OK')"
```

### Connection Refused
- Server'ın çalıştığından emin olun
- Firewall ayarlarını kontrol edin
- `localhost` yerine `127.0.0.1` deneyin

## 📚 Daha Fazla Bilgi

Detaylı API dokümantasyonu için `README_API.md` dosyasına bakın.












