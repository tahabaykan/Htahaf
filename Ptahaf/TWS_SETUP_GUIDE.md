# TWS API Ayarları Rehberi

## 🔧 TWS'de API Ayarlarını Açma

### Adım 1: TWS'yi Açın
1. Interactive Brokers TWS'yi açın
2. Paper Trading hesabınızla giriş yapın
3. TWS tamamen yüklendiğinden emin olun

### Adım 2: API Ayarlarını Açın
1. TWS'de **File** > **Global Configuration**'a tıklayın
2. Sol menüden **API** > **Settings**'e tıklayın
3. Şu ayarları kontrol edin:

### Adım 3: Gerekli Ayarlar
✅ **Enable ActiveX and Socket Clients** - İşaretli olmalı
✅ **Socket port** - 4001 (Paper Trading) veya 4002 (Live Trading)
✅ **Allow connections from localhost** - İşaretli olmalı
❌ **Read-Only API** - İşaretli OLMAMALI
✅ **Download open orders on connection** - İşaretli olmalı
✅ **Include FX positions** - İşaretli olmalı

### Adım 4: Uygulayın
1. **Apply** butonuna tıklayın
2. **OK** butonuna tıklayın
3. TWS'yi **yeniden başlatın**

### Adım 5: Test Edin
```bash
python Ptahaf/ibkr_test.py
```

## 🚨 Yaygın Sorunlar

### Sorun 1: "Connection Refused"
**Çözüm:** TWS açık değil veya API ayarları kapalı

### Sorun 2: "Timeout"
**Çözüm:** TWS'de API ayarlarını kontrol edin

### Sorun 3: "Client ID in use"
**Çözüm:** Başka bir uygulama aynı Client ID'yi kullanıyor

## 📋 Kontrol Listesi

- [ ] TWS açık mı?
- [ ] Paper Trading hesabına giriş yapıldı mı?
- [ ] API Settings açık mı?
- [ ] Socket port doğru mu? (4001/4002)
- [ ] Allow localhost işaretli mi?
- [ ] Read-Only API işaretli değil mi?
- [ ] TWS yeniden başlatıldı mı?
- [ ] Test scripti çalıştırıldı mı?

## 🔍 Test Sonuçları

Başarılı test sonucu şöyle olmalı:
```
✅ TWS Paper Trading başarılı!
✅ Account bilgileri alındı: X öğe
✅ Pozisyonlar alındı: X pozisyon
```

## 💡 İpuçları

1. **TWS'yi her zaman açık tutun** - Uygulama çalışırken TWS kapalı olmamalı
2. **Paper Trading kullanın** - Test için Paper Trading hesabı daha güvenli
3. **Port 4001 kullanın** - Paper Trading için standart port
4. **Client ID'yi değiştirin** - Eğer çakışma varsa farklı bir ID kullanın 
