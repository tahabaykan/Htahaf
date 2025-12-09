# n8n Workflow Rehberi - njanall API Entegrasyonu

## 🎯 Adım 1: n8n'de Yeni Workflow Oluşturun

1. n8n'i açın
2. Sol üstteki **"+"** butonuna tıklayın veya **"New Workflow"** seçin
3. Workflow'a bir isim verin: **"njanall API Test"**

---

## 🎯 Adım 2: Health Check Node'u Ekleyin

### 2.1 HTTP Request Node Ekleyin

1. Workflow canvas'ında **"+"** butonuna tıklayın
2. Arama kutusuna **"HTTP Request"** yazın ve seçin
3. Node'a tıklayarak ayarları açın

### 2.2 Ayarları Yapın

**Method:** `GET`

**URL:** `http://localhost:5000/health`

**Authentication:** `None`

**Diğer ayarlar:** Varsayılan değerleri kullanın

### 2.3 Test Edin

1. Sağ üstteki **"Execute Node"** butonuna tıklayın
2. Sonuçları kontrol edin - şu şekilde bir JSON görmelisiniz:
```json
{
  "status": "ok",
  "timestamp": "2025-11-28T12:00:57.441432",
  "base_dir": "C:\\Users\\..."
}
```

✅ **Başarılı!** İlk node'unuz çalışıyor.

---

## 🎯 Adım 3: Stocks List Node'u Ekleyin

### 3.1 İkinci HTTP Request Node Ekleyin

1. İlk node'un sağ tarafındaki **"+"** butonuna tıklayın
2. Yine **"HTTP Request"** seçin
3. İki node'u birbirine bağlayın (drag & drop ile)

### 3.2 Ayarları Yapın

**Method:** `GET`

**URL:** `http://localhost:5000/api/stocks/list`

**Authentication:** `None`

### 3.3 Test Edin

1. İkinci node'u seçin
2. **"Execute Node"** butonuna tıklayın
3. Sonuçları kontrol edin - 441 hisse görmelisiniz

---

## 🎯 Adım 4: Function Node ile Veri İşleme

### 4.1 Function Node Ekleyin

1. Stocks List node'unun sağına **"Function"** node ekleyin
2. Function node'a tıklayın

### 4.2 Kod Yazın

Function node'un kod editörüne şu kodu yazın:

```javascript
// Stocks listesini al
const stocks = $input.all();

// İlk 5 hisseyi göster
const top5 = stocks[0].json.stocks.slice(0, 5);

// Her hisse için bilgi oluştur
const results = top5.map(stock => {
  return {
    symbol: stock['PREF IBKR'],
    group: stock['GROUP'] || 'N/A',
    final_thg: stock['FINAL_THG'] || 'N/A'
  };
});

return results.map(item => ({ json: item }));
```

### 4.3 Test Edin

**"Execute Node"** butonuna tıklayın ve sonuçları kontrol edin.

---

## 🎯 Adım 5: Webhook Node Ekleyin (Opsiyonel)

### 5.1 Webhook Node Ekleyin

1. Workflow'un başına bir **"Webhook"** node ekleyin
2. Webhook node'u en başa taşıyın (drag & drop)

### 5.2 Ayarları Yapın

**Path:** `/njanall-test`

**Method:** `POST`

**Response Mode:** `Respond to Webhook`

### 5.3 Webhook URL'ini Kopyalayın

Webhook node'unda **"Listen for Test Event"** butonuna tıklayın ve URL'i kopyalayın.

### 5.4 Test Edin

Postman veya curl ile test edin:

```bash
curl -X POST http://localhost:5678/webhook/njanall-test \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'
```

---

## 🎯 Adım 6: Schedule Trigger Ekleyin (Otomatik Çalıştırma)

### 6.1 Schedule Trigger Node Ekleyin

1. Workflow'un en başına **"Schedule Trigger"** node ekleyin
2. Health Check node'una bağlayın

### 6.2 Ayarları Yapın

**Trigger Times:** 
- **Every Hour** (Her saat başı)
- veya **Cron Expression:** `0 * * * *` (Her saat başı)

### 6.3 Aktif Edin

1. Workflow'u **"Active"** yapın (sağ üstteki toggle)
2. n8n otomatik olarak her saat başı çalıştıracak

---

## 📊 Örnek Workflow Yapısı

```
[Schedule Trigger] (Her saat başı)
    ↓
[HTTP Request] GET /health
    ↓
[HTTP Request] GET /api/stocks/list
    ↓
[Function] Veri işleme
    ↓
[HTTP Request] POST /api/positions/add (opsiyonel)
```

---

## 🎯 Adım 7: Pozisyon Ekleme Örneği

### 7.1 HTTP Request Node Ekleyin

**Method:** `POST`

**URL:** `http://localhost:5000/api/positions/add`

**Authentication:** `None`

**Body Content Type:** `JSON`

**Body:** 
```json
{
  "ticker": "{{ $json.symbol }}",
  "direction": "long",
  "fill_price": 25.50,
  "fill_size": 100,
  "benchmark_at_fill": 26.00
}
```

---

## 🔧 Sorun Giderme

### Problem: "Connection refused"

**Çözüm:**
- njanall API server'ın çalıştığından emin olun
- `http://localhost:5000/health` adresini tarayıcıda test edin

### Problem: "CORS error"

**Çözüm:**
- `api_server.py` dosyasında `CORS(app)` olduğundan emin olun
- Server'ı yeniden başlatın

### Problem: "404 Not Found"

**Çözüm:**
- URL'in doğru olduğundan emin olun: `http://localhost:5000/api/stocks/list`
- Server loglarını kontrol edin

---

## ✅ Başarı Kontrol Listesi

- [ ] n8n workflow oluşturuldu
- [ ] Health check node çalışıyor
- [ ] Stocks list node çalışıyor
- [ ] Function node veri işliyor
- [ ] Webhook test edildi (opsiyonel)
- [ ] Schedule trigger aktif (opsiyonel)

---

## 💡 İpuçları

1. **Debugging:** Her node'u tek tek test edin
2. **Data Flow:** Node'lar arası veri akışını kontrol edin (`$json` kullanarak)
3. **Error Handling:** Try-catch ekleyin
4. **Logging:** Console.log ile debug yapın

---

## 📚 Sonraki Adımlar

1. ✅ n8n workflow'unu test edin
2. ✅ Production workflow'ları oluşturun
3. ✅ Error handling ekleyin
4. ✅ Notification sistemi ekleyin (email, Slack, vb.)



