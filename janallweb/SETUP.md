# JanAll Web - Kurulum Rehberi

## Hızlı Başlangıç

### 1. Backend Kurulumu

```bash
cd janallweb
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

`.env` dosyası oluştur:
```
SECRET_KEY=dev-secret-key
HAMMER_HOST=127.0.0.1
HAMMER_PORT=16400
HAMMER_PASSWORD=your-password-here
```

Backend'i başlat:
```bash
python app.py
```
veya
```bash
run_backend.bat
```

### 2. Frontend Kurulumu

```bash
cd frontend
npm install
npm run dev
```
veya
```bash
run_frontend.bat
```

### 3. Kullanım

1. Backend çalışıyor olmalı: `http://127.0.0.1:5000`
2. Frontend çalışıyor olmalı: `http://127.0.0.1:3000`
3. Tarayıcıda `http://127.0.0.1:3000` adresine git
4. Hammer Pro'ya bağlan (sağ üstteki "Bağlan" butonu)
5. CSV dosyası yükle

## Sorun Giderme

### Backend başlamıyor
- Python 3.8+ yüklü mü kontrol et
- `pip install -r requirements.txt` çalıştır
- Port 5000 kullanımda mı kontrol et

### Frontend başlamıyor
- Node.js 16+ yüklü mü kontrol et
- `npm install` çalıştır
- Port 3000 kullanımda mı kontrol et

### Hammer Pro bağlantısı başarısız
- Hammer Pro çalışıyor mu kontrol et
- Port 16400 doğru mu kontrol et
- Şifre doğru mu kontrol et

### WebSocket bağlantısı yok
- Backend çalışıyor mu kontrol et
- Browser console'da hata var mı kontrol et
- CORS ayarları doğru mu kontrol et

## Geliştirme

### Yeni API Endpoint Ekleme

1. `routes/api_routes.py` dosyasına yeni route ekle
2. İlgili service'i `services/` klasöründe oluştur veya güncelle
3. Frontend'de `services/api.js` kullanarak çağır

### Yeni WebSocket Event Ekleme

1. `routes/websocket_routes.py` dosyasına yeni event handler ekle
2. Frontend'de `SocketContext` kullanarak dinle

### Yeni Component Ekleme

1. `frontend/src/components/` klasörüne yeni component ekle
2. Gerekirse `pages/` klasöründe kullan

## Production Deployment

### Backend
- Gunicorn veya uWSGI kullan
- Nginx reverse proxy kur
- SSL sertifikası ekle
- Environment variables'ı ayarla

### Frontend
- `npm run build` ile build al
- Nginx ile static dosyaları serve et
- API proxy ayarlarını yap









