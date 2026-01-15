"""
Backend kontrol scripti
"""

import requests
import time

print("Backend kontrol ediliyor...")
print("3 saniye bekleniyor (backend başlaması için)...")
time.sleep(3)

try:
    print("\nHealth endpoint test ediliyor...")
    response = requests.get('http://127.0.0.1:5000/api/health', timeout=5)
    print(f"✓ Backend ÇALIŞIYOR!")
    print(f"  Status Code: {response.status_code}")
    print(f"  Response: {response.json()}")
except requests.exceptions.ConnectionError:
    print("✗ Backend çalışmıyor veya erişilemiyor")
    print("  Port 5000'de bir şey dinlemiyor")
except Exception as e:
    print(f"✗ Hata: {e}")









