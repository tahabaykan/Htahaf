# IB Gateway API Ayarları Rehberi

## 🔧 IB Gateway'de API Ayarlarını Açma

### Adım 1: IB Gateway'i Açın
1. Interactive Brokers Gateway'i açın
2. Paper Trading hesabınızla giriş yapın
3. Gateway tamamen yüklendiğinden emin olun

### Adım 2: Gateway API Ayarlarını Kontrol Edin
1. Gateway'de **Configure** > **Settings**'e tıklayın
2. **API** sekmesine gidin
3. Şu ayarları kontrol edin:

### Adım 3: Gerekli Ayarlar
✅ **Enable ActiveX and Socket Clients** - İşaretli olmalı
✅ **Socket port** - 4001 (Paper Trading)
✅ **Allow connections from localhost** - İşaretli olmalı
❌ **Read-Only API** - İşaretli OLMAMALI
✅ **Download open orders on connection** - İşaretli olmalı
✅ **Include FX positions** - İşaretli olmalı

### Adım 4: Gateway'de Özel Ayarlar
1. **Configure** > **Settings** > **API**
2. **Socket port**: 4001
3. **Allow connections from**: 127.0.0.1
4. **Read-Only API**: İşaretli değil
5. **Download open orders on connection**: İşaretli
6. **Include FX positions**: İşaretli

### Adım 5: Uygulayın
1. **OK** butonuna tıklayın
2. Gateway'i **yeniden başlatın**

### Adım 6: Test Edin
```bash
python Ptahaf/ibkr_test.py
```

## 🚨 Gateway'e Özel Sorunlar

### Sorun 1: "Connection Refused" (4001 port)
**Çözüm:** 
- Gateway açık değil
- API ayarları kapalı
- Port 4001 yanlış

### Sorun 2: "Client ID in use"
**Çözüm:** 
- Başka bir uygulama aynı Client ID'yi kullanıyor
- Client ID'yi değiştirin

### Sorun 3: "Timeout"
**Çözüm:**
- Gateway'de API ayarlarını kontrol edin
- Firewall ayarlarını kontrol edin

## 📋 Gateway Kontrol Listesi

- [ ] IB Gateway açık mı?
- [ ] Paper Trading hesabına giriş yapıldı mı?
- [ ] API Settings açık mı?
- [ ] Socket port 4001 mi?
- [ ] Allow localhost işaretli mi?
- [ ] Read-Only API işaretli değil mi?
- [ ] Gateway yeniden başlatıldı mı?
- [ ] Test scripti çalıştırıldı mı?

## 🔍 Gateway Test Sonuçları

Başarılı test sonucu şöyle olmalı:
```
✅ Gateway Paper Trading başarılı!
✅ Account bilgileri alındı: X öğe
✅ Pozisyonlar alındı: X pozisyon
```

## 💡 Gateway İpuçları

1. **Gateway'i her zaman açık tutun** - Uygulama çalışırken Gateway kapalı olmamalı
2. **Paper Trading kullanın** - Test için Paper Trading hesabı daha güvenli
3. **Port 4001 kullanın** - Gateway Paper Trading için standart port
4. **Client ID'yi değiştirin** - Eğer çakışma varsa farklı bir ID kullanın
5. **Gateway loglarını kontrol edin** - Hata mesajları için

## 🔧 Gateway Log Kontrolü

Gateway'de logları kontrol etmek için:
1. Gateway'de **Help** > **About**'a tıklayın
2. Log dosyası konumunu not edin
3. Log dosyasını açın ve hata mesajlarını kontrol edin 
