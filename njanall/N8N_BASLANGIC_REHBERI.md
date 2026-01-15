# n8n Başlangıç Rehberi - Adım Adım

## 🎯 ADIM 1: İlk Node'u Ekleyin

### Şu anda ekranda ne görüyorsunuz?
- Ortada büyük bir boş alan
- Sol tarafta "Add first step..." yazısı
- Sağ tarafta "Build with AI" seçeneği

### Ne yapmalısınız?

1. **Sol taraftaki "Add first step..." kutusuna tıklayın**
   - Veya ortadaki büyük "+" işaretine tıklayın

2. **Açılan menüde "HTTP Request" yazısını arayın**
   - Üstteki arama kutusuna "http" yazabilirsiniz
   - Veya kategorilerden "Core Nodes" → "HTTP Request" seçin

3. **"HTTP Request" node'una tıklayın**
   - Canvas'a bir node eklenecek

---

## 🎯 ADIM 2: Node'u Yapılandırın

### Node'a tıkladığınızda ne olur?
- Sağ tarafta bir panel açılacak
- Bu panelde node ayarları var

### Ayarları şu şekilde yapın:

1. **"Method" bölümüne gidin**
   - Dropdown menüden **"GET"** seçin

2. **"URL" bölümüne gidin**
   - Şu URL'yi yazın: `http://localhost:5000/health`

3. **"Authentication" bölümüne gidin**
   - **"None"** seçin (varsayılan olarak seçili olabilir)

4. **Sağ üstteki "Save" butonuna tıklayın**
   - Veya Ctrl+S tuşlarına basın

---

## 🎯 ADIM 3: Node'u Test Edin

### Test etmek için:

1. **Node'un üzerine gelin**
   - Node'un sağ üst köşesinde küçük bir "▶" (play) butonu görünecek

2. **"▶ Execute Node" butonuna tıklayın**
   - Veya node'a sağ tıklayıp "Execute Node" seçin

3. **Sonuçları kontrol edin**
   - Node'un altında yeşil bir çizgi görünecek (başarılı)
   - Node'a tıklayın ve sağ panelde "Output" sekmesine bakın
   - Şu şekilde bir JSON görmelisiniz:
   ```json
   {
     "status": "ok",
     "timestamp": "...",
     "base_dir": "..."
   }
   ```

✅ **Tebrikler! İlk node'unuz çalışıyor!**

---

## 🎯 ADIM 4: İkinci Node'u Ekleyin

### Nasıl eklenir?

1. **İlk node'un sağ tarafında küçük bir "+" işareti görünecek**
   - Bu "+" işaretine tıklayın

2. **Yine "HTTP Request" seçin**

3. **İkinci node'u yapılandırın:**
   - **Method:** `GET`
   - **URL:** `http://localhost:5000/api/stocks/list`
   - **Authentication:** `None`

4. **"Save" butonuna tıklayın**

5. **İkinci node'u test edin**
   - "▶ Execute Node" butonuna tıklayın
   - Sonuçlarda 441 hisse görmelisiniz

---

## 🎯 ADIM 5: Workflow'u Çalıştırın

### Tüm workflow'u çalıştırmak için:

1. **Sağ üstteki "Save" butonuna tıklayın**
   - Workflow kaydedilecek

2. **Sağ üstteki "▶ Execute Workflow" butonuna tıklayın**
   - Veya Ctrl+Enter tuşlarına basın

3. **Sonuçları kontrol edin**
   - Her node'un altında yeşil çizgi görünecek
   - Her node'a tıklayarak sonuçları görebilirsiniz

---

## 📸 Görsel Rehber

### Node ekleme:
```
[Boş Canvas]
    ↓ (Ortadaki "+" veya "Add first step..." kutusuna tıklayın)
[Node Seçim Menüsü]
    ↓ ("HTTP Request" seçin)
[HTTP Request Node Canvas'a Eklendi]
```

### Node yapılandırma:
```
[Node'a Tıklayın]
    ↓
[Sağ Panel Açılır]
    ↓
[Method: GET seçin]
[URL: http://localhost:5000/health yazın]
[Authentication: None seçin]
    ↓
[Save butonuna tıklayın]
```

### Node test etme:
```
[Node'un üzerine gelin]
    ↓
[▶ Execute Node butonuna tıklayın]
    ↓
[Sonuçlar görünür]
```

---

## 🔧 Sorun Giderme

### Problem: "Add first step..." kutusu görünmüyor
**Çözüm:** Ortadaki büyük "+" işaretine tıklayın

### Problem: Node eklenmiyor
**Çözüm:** 
- Sayfayı yenileyin (F5)
- Tarayıcı konsolunu kontrol edin (F12)

### Problem: "Execute Node" butonu görünmüyor
**Çözüm:**
- Node'a tıklayın
- Sağ panelde "Execute Node" butonunu arayın
- Veya node'a sağ tıklayın

### Problem: "Connection refused" hatası
**Çözüm:**
- njanall API server'ın çalıştığından emin olun
- Terminal'de `python start_api.py` çalıştırın
- Tarayıcıda `http://localhost:5000/health` adresini test edin

---

## ✅ Kontrol Listesi

- [ ] n8n açıldı ve workflow editörü görünüyor
- [ ] İlk node eklendi (HTTP Request)
- [ ] Node yapılandırıldı (GET /health)
- [ ] Node test edildi ve çalışıyor
- [ ] İkinci node eklendi (GET /api/stocks/list)
- [ ] İkinci node test edildi ve çalışıyor
- [ ] Workflow kaydedildi

---

## 💡 İpuçları

1. **Node'ları taşımak için:** Node'a tıklayıp sürükleyin
2. **Node'ları silmek için:** Node'a sağ tıklayıp "Delete" seçin
3. **Zoom yapmak için:** Mouse tekerleğini kullanın veya sağ alttaki zoom butonlarını kullanın
4. **Undo/Redo için:** Ctrl+Z / Ctrl+Y tuşlarını kullanın

---

## 🎓 Sonraki Adımlar

1. ✅ İlk workflow'unuzu oluşturun
2. ✅ Node'ları test edin
3. ✅ Workflow'u kaydedin
4. ✅ Daha fazla node ekleyin (Function, Webhook, vb.)










