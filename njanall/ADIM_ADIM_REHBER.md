# 🚀 njanall API Server - Adım Adım Rehber

Bu rehber size njanall API server'ını kurup çalıştırmanız için gereken tüm adımları gösterir.

## 📋 ADIM 1: Gerekli Paketleri Kurun

### Terminal'de şu komutu çalıştırın:

```bash
pip install flask flask-cors pandas numpy requests
```

**Beklenen çıktı:**
```
Successfully installed flask flask-cors ...
```

✅ **Kontrol:** Şu komutu çalıştırın:
```bash
python -c "import flask; print('Flask kurulu:', flask.__version__)"
```

---

## 📋 ADIM 2: API Server'ı Başlatın

### Terminal'de şu komutu çalıştırın:

```bash
cd njanall
python start_api.py
```

**Beklenen çıktı:**
```
============================================================
🚀 njanall API Server
============================================================
📡 Server başlatılıyor...
🌐 URL: http://localhost:5000
📚 API Docs: http://localhost:5000/health
============================================================

💡 n8n entegrasyonu için:
   - Webhook URL: http://localhost:5000/webhook/n8n
   - API Base URL: http://localhost:5000/api

⏹️  Durdurmak için: Ctrl+C
============================================================
 * Running on http://0.0.0.0:5000
```

⚠️ **ÖNEMLİ:** Bu terminal penceresini açık tutun! Server çalışırken kapatmayın.

---

## 📋 ADIM 3: API'yi Test Edin

### Yeni bir terminal penceresi açın ve şu komutları çalıştırın:

#### 3.1 Health Check Testi

```bash
python njanall/test_api_simple.py
```

**Beklenen çıktı:**
```
============================================================
🚀 njanall API Test Suite
============================================================

1. Health Check Test
============================================================
✅ Health check başarılı!
   Response: {
     "status": "ok",
     "timestamp": "2024-01-01T12:00:00",
     "base_dir": "..."
   }
```

#### 3.2 Tarayıcıdan Test

Tarayıcınızda şu adresi açın:
```
http://localhost:5000/health
```

Şu şekilde bir JSON görmelisiniz:
```json
{
  "status": "ok",
  "timestamp": "2024-01-01T12:00:00.123456",
  "base_dir": "C:\\Users\\...\\njanall"
}
```

#### 3.3 curl ile Test (Opsiyonel)

Yeni bir terminal penceresi açın:

```bash
curl http://localhost:5000/health
```

---

## 📋 ADIM 4: API Endpoint'lerini Test Edin

### 4.1 Hisseleri Listele

**Tarayıcıdan:**
```
http://localhost:5000/api/stocks/list
```

**Python ile:**
```python
import requests
response = requests.get('http://localhost:5000/api/stocks/list')
print(response.json())
```

### 4.2 CSV Birleştirme (Uzun sürebilir)

**Python ile:**
```python
import requests
response = requests.post('http://localhost:5000/api/csv/merge')
print(response.json())
```

---

## 📋 ADIM 5: n8n Entegrasyonu

### 5.1 n8n'de Yeni Workflow Oluşturun

1. n8n'i açın
2. "New Workflow" butonuna tıklayın
3. Workflow'a bir isim verin: "njanall API Test"

### 5.2 HTTP Request Node Ekleyin

1. "+" butonuna tıklayın
2. "HTTP Request" node'unu seçin
3. Ayarları şu şekilde yapın:
   - **Method**: GET
   - **URL**: `http://localhost:5000/health`
   - **Authentication**: None

4. "Execute Node" butonuna tıklayın
5. Sonuçları kontrol edin

### 5.3 Stocks List Node Ekleyin

1. Yeni bir HTTP Request node ekleyin
2. Ayarları şu şekilde yapın:
   - **Method**: GET
   - **URL**: `http://localhost:5000/api/stocks/list`
   - **Authentication**: None

3. İlk node'a bağlayın
4. "Execute Workflow" butonuna tıklayın

### 5.4 Webhook Node Ekleyin (Opsiyonel)

1. Yeni bir Webhook node ekleyin
2. Ayarları şu şekilde yapın:
   - **Path**: `/webhook/n8n`
   - **Method**: POST
   - **Response Mode**: Respond to Webhook

3. Webhook URL'ini kopyalayın
4. Test için Postman veya curl kullanın:
```bash
curl -X POST http://localhost:5000/webhook/n8n \
  -H "Content-Type: application/json" \
  -d '{"action": "get_stocks"}'
```

---

## 🔧 Sorun Giderme

### Problem: "ModuleNotFoundError: No module named 'flask'"

**Çözüm:**
```bash
pip install flask flask-cors
```

### Problem: "Address already in use" (Port 5000 kullanılıyor)

**Çözüm 1:** Port'u değiştirin:
`api_server.py` dosyasında:
```python
app.run(host='0.0.0.0', port=5001, debug=True)
```

**Çözüm 2:** Kullanan programı kapatın:
```bash
# Windows'ta
netstat -ano | findstr :5000
taskkill /PID <PID_NUMARASI> /F
```

### Problem: "Connection refused"

**Çözüm:**
- Server'ın çalıştığından emin olun
- `python start_api.py` komutunu çalıştırın
- Terminal penceresini açık tutun

### Problem: "Import errors"

**Çözüm:**
```bash
cd njanall
python -c "from janallapp.path_helper import get_csv_path; print('OK')"
```

---

## ✅ Başarı Kontrol Listesi

- [ ] Flask ve flask-cors kurulu
- [ ] API server çalışıyor (`python start_api.py`)
- [ ] Health check başarılı (`http://localhost:5000/health`)
- [ ] Stocks list çalışıyor (`http://localhost:5000/api/stocks/list`)
- [ ] n8n workflow oluşturuldu
- [ ] n8n'den API'ye bağlantı başarılı

---

## 📚 Sonraki Adımlar

1. ✅ API server'ı test edin
2. ✅ n8n workflow'ları oluşturun
3. ✅ Production için authentication ekleyin
4. ✅ Logging sistemi ekleyin
5. ✅ Error handling'i geliştirin

---

## 💡 İpuçları

- Server'ı arka planda çalıştırmak için: `python start_api.py &` (Linux/Mac)
- Windows'ta arka planda çalıştırmak için: Task Scheduler kullanın
- Production'da: `gunicorn` veya `waitress` kullanın
- HTTPS için: `flask-talisman` kullanın

---

## 🆘 Yardım

Sorun yaşıyorsanız:
1. `test_api_simple.py` scriptini çalıştırın
2. Server loglarını kontrol edin
3. `README_API.md` dosyasına bakın










