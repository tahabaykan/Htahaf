# 🔧 Sorun: "Connection Refused" Hatası

## ❌ Problem
n8n'de şu hatayı alıyorsunuz:
```
The service refused the connection - perhaps it is offline
```

## ✅ Çözüm: API Server'ı Başlatın

### ADIM 1: Terminal Açın

1. **Yeni bir terminal penceresi açın**
   - Windows'ta: PowerShell veya Command Prompt
   - Veya VS Code'da yeni terminal açın (Ctrl+`)

### ADIM 2: njanall Dizinine Gidin

Terminal'de şu komutu çalıştırın:

```bash
cd njanall
```

**VEYA** tam yol ile:

```bash
cd "C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\njanall"
```

### ADIM 3: API Server'ı Başlatın

Terminal'de şu komutu çalıştırın:

```bash
python start_api.py
```

**VEYA:**

```bash
python api_server.py
```

### ADIM 4: Server'ın Başladığını Kontrol Edin

Terminal'de şu mesajı görmelisiniz:

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

✅ **Server çalışıyor!**

### ADIM 5: Tarayıcıdan Test Edin

Tarayıcınızda şu adresi açın:

```
http://localhost:5000/health
```

Şu şekilde bir JSON görmelisiniz:

```json
{
  "status": "ok",
  "timestamp": "...",
  "base_dir": "..."
}
```

✅ **API çalışıyor!**

### ADIM 6: n8n'de Tekrar Deneyin

1. **n8n'e geri dönün**
2. **HTTP Request node'una tıklayın**
3. **"▶ Execute Node" butonuna tıklayın**
4. **Artık çalışmalı!** ✅

---

## ⚠️ ÖNEMLİ NOTLAR

### Terminal Penceresini Açık Tutun!

- API server çalışırken terminal penceresini **KAPATMAYIN**
- Kapatırsanız server durur ve n8n tekrar hata verir
- Server'ı durdurmak için: **Ctrl+C** tuşlarına basın

### Server Her Zaman Çalışmalı

- n8n workflow'larını kullanmak için API server'ın çalışıyor olması gerekir
- Server'ı arka planda çalıştırmak isterseniz:
  - Windows'ta: Task Scheduler kullanın
  - Veya bir service olarak kurun

---

## 🔍 Sorun Devam Ederse

### 1. Port Kontrolü

Port 5000 kullanılıyor mu kontrol edin:

```bash
netstat -ano | findstr :5000
```

Eğer başka bir program kullanıyorsa, port'u değiştirin:

`api_server.py` dosyasında:
```python
app.run(host='0.0.0.0', port=5001, debug=True)  # 5000 yerine 5001
```

Ve n8n'deki URL'yi de güncelleyin:
```
http://localhost:5001/health
```

### 2. Firewall Kontrolü

Windows Firewall API server'a izin veriyor mu kontrol edin.

### 3. Python Path Kontrolü

Python doğru kurulu mu kontrol edin:

```bash
python --version
```

### 4. Paketler Kurulu mu?

```bash
pip install flask flask-cors pandas numpy requests
```

---

## ✅ Başarı Kontrol Listesi

- [ ] Terminal açıldı
- [ ] njanall dizinine gidildi
- [ ] `python start_api.py` komutu çalıştırıldı
- [ ] Server başladı mesajı görüldü
- [ ] Tarayıcıda `http://localhost:5000/health` test edildi
- [ ] n8n'de HTTP Request node çalıştı

---

## 💡 İpuçları

1. **Server'ı arka planda çalıştırmak için:**
   - Windows'ta: `start python start_api.py` komutunu kullanın
   - Veya bir batch dosyası oluşturun

2. **Server'ı otomatik başlatmak için:**
   - Windows Task Scheduler kullanın
   - Veya bir Windows Service olarak kurun

3. **Server loglarını görmek için:**
   - Terminal penceresini açık tutun
   - Tüm istekler ve hatalar burada görünecek



