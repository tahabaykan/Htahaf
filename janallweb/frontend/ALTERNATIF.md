# Alternatif: Node.js Olmadan Test Et

Eğer Node.js yüklemek istemiyorsan, backend'i test edebiliriz:

## Backend API Test

Backend çalışıyor, direkt API'yi test edebiliriz:

### Tarayıcıda Test

1. Backend çalışıyor: `http://127.0.0.1:5000`
2. Tarayıcıda şu adreslere git:

- Health Check: `http://127.0.0.1:5000/api/health`
- CSV List: `http://127.0.0.1:5000/api/csv/list`

### Python ile Test

```python
import requests

# Health check
response = requests.get('http://127.0.0.1:5000/api/health')
print(response.json())

# CSV list
response = requests.get('http://127.0.0.1:5000/api/csv/list')
print(response.json())
```

## Frontend Olmadan Backend Test

Backend çalışıyor, API endpoint'lerini test edebiliriz!









