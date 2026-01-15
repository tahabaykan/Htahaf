"""utils/token_bucket.py

Basit token bucket rate-limiter implementasyonu.

Token bucket algoritması, rate limiting için kullanılır. Belirli bir kapasiteye kadar
token birikir ve her istek bir token tüketir. Token yoksa istek bekletilir.

Kullanım:
    tb = TokenBucket(rate_per_second=1.0, capacity=5)
    if tb.consume():
        # İşlem yapılabilir
        pass
    else:
        # Bekle, token yok
        await asyncio.sleep(0.1)

Parametreler:
    rate_per_second: Saniyede kaç token ekleneceği
    capacity: Maksimum token sayısı (burst capacity)
"""

import time
from typing import Optional


class TokenBucket:
    """Token bucket rate limiter"""
    
    def __init__(self, rate_per_second: float, capacity: int):
        """
        Args:
            rate_per_second: Saniyede eklenen token sayısı
            capacity: Maksimum token kapasitesi (burst)
        """
        self.rate = rate_per_second
        self.capacity = capacity
        self._tokens = float(capacity)  # Başlangıçta dolu
        self._last_update = time.time()
        self._lock = None  # Thread-safe için (gelecekte threading.Lock eklenebilir)
    
    def consume(self, tokens: int = 1) -> bool:
        """
        Token tüketmeyi dene.
        
        Args:
            tokens: Tüketilecek token sayısı (default: 1)
            
        Returns:
            True if tokens were consumed, False otherwise
        """
        now = time.time()
        elapsed = now - self._last_update
        
        # Zaman geçtikçe token ekle
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_update = now
        
        # Yeterli token var mı?
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False
    
    def available_tokens(self) -> float:
        """Mevcut token sayısını döndür (güncel)"""
        now = time.time()
        elapsed = now - self._last_update
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_update = now
        return self._tokens
    
    def wait_time(self, tokens: int = 1) -> float:
        """
        Belirtilen token sayısı için ne kadar beklemek gerektiğini hesapla.
        
        Returns:
            Bekleme süresi (saniye), 0 ise hemen kullanılabilir
        """
        available = self.available_tokens()
        if available >= tokens:
            return 0.0
        needed = tokens - available
        return needed / self.rate








