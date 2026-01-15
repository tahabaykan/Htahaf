# 🎨 JanAll Web - HTML Glassmorphism UI Kullanım Rehberi

## ✨ Özellikler

Modern glassmorphism (cam efekti) tasarımı ile oluşturulmuş HTML web uygulaması:

- ✅ **Glassmorphism UI**: Yarı saydam, blur efektli modern tasarım
- ✅ **Responsive**: Mobil ve desktop uyumlu
- ✅ **Real-time Updates**: WebSocket ile anlık güncellemeler
- ✅ **3 Ana Sayfa**: Dashboard, Pozisyonlar, Emirler
- ✅ **Smooth Animations**: Akıcı geçişler ve animasyonlar

## 🚀 Başlatma

### 1. Backend'i Başlat

```bash
cd janallweb
python app.py
```

Backend `http://127.0.0.1:5000` adresinde çalışacak.

### 2. Tarayıcıda Aç

Tarayıcıda şu adrese git:
```
http://127.0.0.1:5000
```

## 📱 Kullanım

### Dashboard Sayfası

1. **Hammer Pro'ya Bağlan**
   - Sağ üstteki "🔗 Hammer Pro'ya Bağlan" butonuna tıkla
   - Şifreyi gir

2. **CSV Yükle**
   - "📁 CSV Yükle" butonuna tıkla
   - Dosya adını gir (örn: `janalldata.csv`)
   - Tablo otomatik olarak yüklenecek

3. **Hisse Seçimi**
   - Tablodaki checkbox'ları kullanarak hisse seç
   - "Tümünü Seç" / "Tümünü Kaldır" butonları ile toplu işlem yap

4. **Lot Ayarlama**
   - Lot input'una manuel değer gir
   - Veya %25, %50, %75, %100 butonlarını kullan
   - "Avg Adv" butonu ile ortalama ADV'ye göre lot ayarla

5. **Emir Gönderme**
   - 8 farklı emir butonu:
     - **Bid Buy** / **Front Buy** / **Ask Buy** (Yeşil - Alış)
     - **Ask Sell** / **Front Sell** / **Bid Sell** (Kırmızı - Satış)
     - **SoftFront Buy** / **SoftFront Sell** (Koşullu emirler)

6. **Arama ve Sıralama**
   - Üst kısımdaki arama kutusu ile hisse ara
   - Sıralama dropdown'ı ile tabloyu sırala

### Pozisyonlar Sayfası

- Açık pozisyonları görüntüle
- Real-time güncellemeler (WebSocket)
- P&L bilgileri

### Emirler Sayfası

- Açık emirleri görüntüle
- Emir iptal etme
- Emir durumu takibi

## 🎨 Tasarım Özellikleri

### Glassmorphism Efektleri

- **Backdrop Blur**: Arka plan bulanıklaştırma
- **Yarı Saydam Arka Planlar**: `rgba(255, 255, 255, 0.1)`
- **Gradient Borders**: Renkli kenarlıklar
- **Smooth Animations**: Akıcı geçişler

### Renk Paleti

- **Primary**: Indigo (`#6366f1`)
- **Success**: Green (`#10b981`)
- **Danger**: Red (`#ef4444`)
- **Buy Buttons**: Yeşil gradient
- **Sell Buttons**: Kırmızı gradient

### Animasyonlar

- **Floating Orbs**: Arka planda yavaşça hareket eden gradient toplar
- **Fade In**: Sayfa geçişlerinde fade efekti
- **Hover Effects**: Buton ve kartlarda hover animasyonları
- **Pulse**: Bağlantı durumu göstergesinde pulse efekti

## 🔧 Özelleştirme

### Renkleri Değiştir

`static/css/style.css` dosyasında `:root` değişkenlerini düzenle:

```css
:root {
    --primary: #6366f1;
    --secondary: #8b5cf6;
    /* ... */
}
```

### API URL'ini Değiştir

`static/js/app.js` dosyasında:

```javascript
const API_BASE_URL = 'http://127.0.0.1:5000/api';
const WS_URL = 'http://127.0.0.1:5000';
```

## 📊 Performans

- **Lightweight**: Sadece HTML, CSS, vanilla JavaScript
- **No Build Step**: Direkt tarayıcıda çalışır
- **Fast Loading**: Minimal dosya boyutu
- **Real-time**: WebSocket ile anlık güncellemeler

## 🐛 Sorun Giderme

### WebSocket Bağlantı Hatası

1. Backend'in çalıştığından emin ol
2. Tarayıcı konsolunda hata mesajlarını kontrol et
3. CORS ayarlarını kontrol et

### CSV Yükleme Hatası

1. Dosya adının doğru olduğundan emin ol
2. Dosyanın `janall` klasöründe olduğundan emin ol
3. Backend loglarını kontrol et

### Emir Gönderme Hatası

1. Hammer Pro bağlantısını kontrol et
2. Hisse seçili olduğundan emin ol
3. Lot değerinin girildiğinden emin ol

## 📝 Notlar

- React frontend hala mevcut (`frontend/` klasöründe)
- HTML app daha hafif ve hızlı
- İki frontend aynı backend'i kullanır
- Tercihine göre birini kullanabilirsin

## 🎯 Sonraki Adımlar

- [ ] Daha fazla filtreleme seçeneği
- [ ] Grafik görünümü
- [ ] Export fonksiyonları
- [ ] Dark/Light mode toggle
- [ ] Daha fazla animasyon







