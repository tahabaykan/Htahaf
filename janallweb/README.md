# JanAll Web - Flask + React Uygulaması

JanAll uygulamasının web tabanlı versiyonu.

## Kurulum

### Backend (Flask)

1. Python virtual environment oluştur:
```bash
cd janallweb
python -m venv venv
venv\Scripts\activate  # Windows
```

2. Bağımlılıkları yükle:
```bash
pip install -r requirements.txt
```

3. `.env` dosyası oluştur:
```bash
copy .env.example .env
```

4. `.env` dosyasını düzenle ve Hammer Pro şifresini ekle.

5. Backend'i başlat:
```bash
python app.py
```

Backend `http://127.0.0.1:5000` adresinde çalışacak.

### Frontend (React)

1. Frontend klasörüne git:
```bash
cd frontend
```

2. Node.js bağımlılıklarını yükle:
```bash
npm install
```

3. Frontend'i başlat:
```bash
npm run dev
```

Frontend `http://127.0.0.1:3000` adresinde çalışacak.

## Kullanım

1. Backend ve frontend'i başlat
2. Tarayıcıda `http://127.0.0.1:3000` adresine git
3. Hammer Pro'ya bağlan (sağ üstteki "Bağlan" butonu)
4. CSV dosyası yükle (Ana Sayfa)
5. Pozisyonları ve emirleri görüntüle

## Yapı

```
janallweb/
├── app.py                 # Flask ana uygulama
├── routes/               # API route'ları
│   ├── api_routes.py     # RESTful API endpoint'leri
│   └── websocket_routes.py # WebSocket event handler'ları
├── services/             # Business logic
│   ├── csv_service.py
│   ├── position_service.py
│   ├── order_service.py
│   └── market_data_service.py
├── janallapp/            # Mevcut tkinter uygulaması modülleri (kopyalanmış)
└── frontend/             # React frontend
    └── src/
        ├── components/   # React component'leri
        ├── pages/        # Sayfa component'leri
        ├── contexts/     # React context'leri
        └── services/     # API servisleri
```

## API Endpoint'leri

- `GET /api/health` - Health check
- `GET /api/connection/status` - Bağlantı durumu
- `POST /api/connection/hammer/connect` - Hammer Pro'ya bağlan
- `GET /api/positions` - Pozisyonları getir
- `GET /api/orders` - Emirleri getir
- `POST /api/orders/place` - Yeni emir gönder
- `POST /api/orders/cancel` - Emir iptal et
- `POST /api/csv/load` - CSV dosyası yükle
- `GET /api/csv/list` - CSV dosyalarını listele
- `GET /api/market-data/<symbol>` - Market data getir

## WebSocket Events

- `connect` - Client bağlandığında
- `subscribe_market_data` - Market data'ya subscribe ol
- `market_data_update` - Market data güncellemesi
- `positions_update` - Pozisyon güncellemesi
- `order_update` - Emir güncellemesi
- `fill_update` - Fill güncellemesi

## Notlar

- Backend ve frontend ayrı portlarda çalışır (5000 ve 3000)
- Vite proxy kullanarak frontend'den backend'e istekler yönlendirilir
- WebSocket bağlantısı real-time data için kullanılır
- Hammer Pro bağlantısı backend'de yönetilir









