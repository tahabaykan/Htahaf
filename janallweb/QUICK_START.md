# Hızlı Başlangıç

## Backend Başlatma

1. Terminal 1'de:
```bash
cd janallweb
python start_backend.py
```

Backend `http://127.0.0.1:5000` adresinde çalışacak.

## Frontend Başlatma

2. Terminal 2'de:
```bash
cd janallweb/frontend
npm install
npm run dev
```

Frontend `http://127.0.0.1:3000` adresinde çalışacak.

## Kullanım

1. Tarayıcıda `http://127.0.0.1:3000` adresine git
2. Sağ üstteki "Bağlan" butonuna tıkla
3. Hammer Pro bilgilerini gir ve bağlan
4. Ana sayfada CSV dosyası yükle
5. Pozisyonlar ve emirler sayfalarını kullan

## Sorun Giderme

### Backend başlamıyor
- Port 5000 kullanımda mı kontrol et
- `python start_backend.py` çalıştır ve hataları gör

### Frontend başlamıyor
- Node.js yüklü mü kontrol et
- `npm install` çalıştır
- Port 3000 kullanımda mı kontrol et

### WebSocket bağlantısı yok
- Backend çalışıyor mu kontrol et
- Browser console'da hata var mı bak









