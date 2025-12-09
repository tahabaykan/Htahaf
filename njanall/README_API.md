# njanall API Server - n8n Entegrasyonu

Bu dokümantasyon njanall API server'ını n8n ile nasıl kullanacağınızı açıklar.

## Kurulum

```bash
cd njanall
pip install -r requirements_api.txt
```

## Server'ı Başlatma

```bash
python api_server.py
```

Server `http://localhost:5000` adresinde çalışacaktır.

## API Endpoints

### Health Check
```
GET /health
```

### CSV İşlemleri

#### CSV Birleştirme
```
POST /api/csv/merge
```
Tüm ssfinek CSV dosyalarını birleştirip janalldata.csv oluşturur.

#### CSV Okuma
```
GET /api/csv/read/<filename>?limit=100&offset=0
```
CSV dosyasını okur.

#### CSV Yazma
```
POST /api/csv/write/<filename>
Body: {"data": [{"col1": "val1", "col2": "val2"}]}
```

### Hisseler

#### Tüm Hisseleri Listele
```
GET /api/stocks/list?group=heldkuponlu&symbol=ABC
```

#### Belirli Hisse Bilgisi
```
GET /api/stocks/<symbol>
```

### Pozisyonlar

#### Pozisyonları Listele
```
GET /api/positions
```

#### Pozisyon Ekle
```
POST /api/positions/add
Body: {
    "ticker": "ABC",
    "direction": "long",
    "fill_price": 25.50,
    "fill_size": 100,
    "benchmark_at_fill": 26.00
}
```

### Exception Listesi

#### Exception Listesini Al
```
GET /api/exceptions
```

#### Exception Ekle
```
POST /api/exceptions/add
Body: {"ticker": "ABC"}
```

#### Exception Kaldır
```
POST /api/exceptions/remove
Body: {"ticker": "ABC"}
```

### JDataLog

#### JDataLog Dönüştürme
```
POST /api/jdatalog/convert
```

#### Sembol JDataLog Bilgisi
```
GET /api/jdatalog/symbol/<symbol>
```

### n8n Webhook

#### Genel Webhook Endpoint
```
POST /webhook/n8n
Body: {
    "action": "merge_csvs|get_stocks|add_position|get_positions",
    ...
}
```

## n8n Entegrasyonu

### 1. HTTP Request Node Kullanımı

n8n'de bir HTTP Request node'u ekleyin:

- **Method**: GET veya POST
- **URL**: `http://localhost:5000/api/stocks/list`
- **Authentication**: None (şimdilik)

### 2. Webhook Node Kullanımı

n8n'de bir Webhook node'u ekleyin:

- **Path**: `/webhook/n8n`
- **Method**: POST
- **Response Mode**: Respond to Webhook

### Örnek Workflow

1. **Schedule Trigger** - Her saat başı çalıştır
2. **HTTP Request** - `GET /api/csv/merge` - CSV'leri birleştir
3. **HTTP Request** - `GET /api/stocks/list` - Hisseleri al
4. **Function Node** - Verileri işle
5. **HTTP Request** - `POST /api/positions/add` - Pozisyon ekle

## Güvenlik Notları

- Production'da authentication ekleyin
- HTTPS kullanın
- Rate limiting ekleyin
- Input validation yapın

## Sorun Giderme

### Port Zaten Kullanılıyor
```bash
# Port'u değiştirin
app.run(host='0.0.0.0', port=5001, debug=True)
```

### Import Hataları
```bash
# Python path'i kontrol edin
python -c "import sys; print(sys.path)"
```



