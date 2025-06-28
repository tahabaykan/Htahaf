"""
Data caching functionality for StockTracker application
"""
import time
import datetime
from collections import defaultdict, OrderedDict
import math
import pandas as pd
import threading
import pickle
import gzip
import base64
import os
import json

class MarketDataCache:
    """Market verilerini önbellekleme ve yönetme sınıfı"""
    
    def __init__(self, max_size=2000, max_subscriptions=50):
        """
        Market verilerini önbellekleme ve yönetme sınıfını başlat
        
        Args:
            max_size: Önbellekte tutulacak maksimum sembol sayısı
            max_subscriptions: Aynı anda aktif olabilecek maksimum abonelik sayısı
        """
        # Veri sözlükleri
        self.data = {}  # Sembol -> veri eşlemesi (tüm önbellek)
        self.subscriptions = {}  # Aktif abonelikler (sembol -> contract, ib)
        self.last_access = {}  # Sembol -> son erişim zamanı eşlemesi
        self.priorities = set()  # Öncelikli sembollerin kümesi
        
        # Snapshot verileri - sayfa değiştirdiğimizde bile korunan veriler
        self.snapshot_data = {}  # Sembol -> son veri eşlemesi (abonelik bitse bile korunur)
        
        # Kapasite sınırları
        self.max_size = max_size
        self.max_subscriptions = max_subscriptions
        
        # Thread güvenliği için kilit
        self.lock = threading.RLock()
        
        # En son temizleme zamanı
        self.last_cleanup = time.time()
        
        # Temizleme işlemini otomatik başlat
        threading.Timer(60.0, self.cleanup_old_data).start()
        
        print(f"MarketDataCache başlatıldı: max_size={max_size}, max_subscriptions={max_subscriptions}")
    
    def update(self, symbol, ticker_data):
        """
        Sembol için veriyi güncelle ve son erişim zamanını kaydet
        
        Args:
            symbol: Hisse sembolü
            ticker_data: Ticker verisi (IB'den gelen)
        """
        with self.lock:
            # Veriyi güncelle
            self.data[symbol] = ticker_data
            
            # Snapshot verisi olarak da kaydet - abonelik bitse bile bu veri korunacak
            self.snapshot_data[symbol] = ticker_data
            
            # Son erişim zamanını güncelle
            self.last_access[symbol] = time.time()
    
    def get(self, symbol):
        """
        Sembol için veriyi döndür. Eğer varsa ve güncel ise, son erişim zamanını güncelle.
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            ticker_data veya None (eğer sembol önbellekte yoksa)
        """
        with self.lock:
            # Önce aktif abonelikler arasında ara
            if symbol in self.data:
                # Son erişim zamanını güncelle
                self.last_access[symbol] = time.time()
                return self.data.get(symbol)
            
            # Aktif abonelik yoksa snapshot verilerinde ara
            if symbol in self.snapshot_data:
                # Snapshot verisi bulunduğunda da son erişim zamanını güncelle
                # Bu sayede sık kullanılan ama aktif olmayan semboller de önbellekte kalır
                self.last_access[symbol] = time.time()
                return self.snapshot_data.get(symbol)
            
            # Hiçbir yerde yoksa None döndür
            return None
    
    def add_subscription(self, symbol, contract, ib):
        """
        Yeni bir market verisi aboneliği ekle
        
        Args:
            symbol: Hisse sembolü
            contract: IB kontratı
            ib: IB API bağlantısı
            
        Returns:
            True if successful, False otherwise
        """
        with self.lock:
            # Eğer zaten bu sembol için abonelik varsa
            if symbol in self.subscriptions:
                return True
            
            # Abonelik limitini kontrol et
            if len(self.subscriptions) >= self.max_subscriptions and symbol not in self.priorities:
                # Eğer sembol öncelikli değilse ve limit doluysa
                # Önceliksiz ve en eski erişilen bir aboneliği kaldır
                self._remove_oldest_subscription(ib)
            
            # Yeni aboneliği kaydet
            self.subscriptions[symbol] = {"contract": contract, "time": time.time()}
            
            # Son erişim zamanını güncelle
            self.last_access[symbol] = time.time()
            
            print(f"+ Abonelik eklendi: {symbol} (toplam: {len(self.subscriptions)})")
            return True
    
    def remove_subscription(self, symbol, ib):
        """
        Market verisi aboneliğini kaldır, ancak verileri hafızada tut
        
        Args:
            symbol: Hisse sembolü
            ib: IB API bağlantısı
            
        Returns:
            True if successful, False otherwise
        """
        with self.lock:
            # Eğer bu sembol için abonelik yoksa
            if symbol not in self.subscriptions:
                return False
            
            # Kontratı al
            contract = self.subscriptions[symbol]["contract"]
            
            try:
                # IB aboneliğini iptal et
                ib.cancelMktData(contract)
                
                # Aboneliği sözlükten kaldır, ama veriyi sil
                del self.subscriptions[symbol]
                
                print(f"- Abonelik kaldırıldı: {symbol} (kalan: {len(self.subscriptions)})")
                return True
            except Exception as e:
                print(f"Abonelik kaldırma hatası ({symbol}): {e}")
                return False
    
    def clear_all_subscriptions(self, ib):
        """
        Tüm market verisi aboneliklerini kaldır, ancak verileri hafızada tut
        
        Args:
            ib: IB API bağlantısı
        """
        with self.lock:
            symbols = list(self.subscriptions.keys())
            for symbol in symbols:
                self.remove_subscription(symbol, ib)
    
    def prioritize_symbol(self, symbol):
        """
        Sembolü öncelikli olarak işaretle (önbellek temizliği sırasında korunması için)
        
        Args:
            symbol: Hisse sembolü
        """
        with self.lock:
            self.priorities.add(symbol)
            # Son erişim zamanını da güncelle
            self.last_access[symbol] = time.time()
    
    def cleanup_old_data(self):
        """
        Uzun süredir erişilmemiş ve öncelikli olmayan verileri temizle
        """
        with self.lock:
            now = time.time()
            
            # Son temizlemeden bu yana en az 5 dakika geçtiyse
            if now - self.last_cleanup < 300:
                # 5 dakika geçmemişse, tekrar planlayıp çık
                threading.Timer(60.0, self.cleanup_old_data).start()
                return
            
            # En son temizleme zamanını güncelle
            self.last_cleanup = now
            
            # Önbellekteki toplam sembol sayısını kontrol et
            if len(self.data) <= self.max_size:
                # Limit dolmamışsa, temizleme yapmadan çık
                threading.Timer(60.0, self.cleanup_old_data).start()
                return
            
            # Sembolleri son erişim zamanına göre sırala (en eskiden yeniye)
            sorted_symbols = sorted(self.last_access.items(), key=lambda x: x[1])
            
            # En eskiden başlayarak temizle, öncelikli sembolleri atla
            removed_count = 0
            for symbol, _ in sorted_symbols:
                # Eğer sembol aktif abonelikler arasında veya öncelikli ise atla
                if symbol in self.subscriptions or symbol in self.priorities:
                    continue
                
                # 12 saatten eski olup olmadığını kontrol et
                last_access_time = self.last_access.get(symbol, 0)
                if now - last_access_time > 43200:  # 12 saat
                    # Önbellekten kaldır
                    if symbol in self.data:
                        del self.data[symbol]
                    
                    # Son erişim kaydını sil
                    if symbol in self.last_access:
                        del self.last_access[symbol]
                    
                    removed_count += 1
                    
                    # Önbellek boyutu uygun seviyeye gelince dur
                    if len(self.data) <= self.max_size * 0.9:  # %90'a düştüyse
                        break
            
            if removed_count > 0:
                print(f"Önbellek temizliği: {removed_count} sembol kaldırıldı (kalan: {len(self.data)})")
            
            # Bir sonraki temizleme işlemini planla (1 dakika sonra)
            threading.Timer(60.0, self.cleanup_old_data).start()
    
    def _remove_oldest_subscription(self, ib):
        """
        En eski aboneliği kaldır (yer açmak için)
        
        Args:
            ib: IB API bağlantısı
        """
        # Öncelikli olmayan abonelikleri listeye al
        candidates = [(s, info["time"]) for s, info in self.subscriptions.items() if s not in self.priorities]
        
        if not candidates:
            return False  # Kaldırılacak abone yok
        
        # En eski aboneliği bul
        candidates.sort(key=lambda x: x[1])  # Abonelik zamanına göre sırala
        oldest_symbol = candidates[0][0]
        
        # En eski aboneliği kaldır
        return self.remove_subscription(oldest_symbol, ib)
    
    def get_subscription_count(self):
        """Aktif abonelik sayısını döndür"""
        with self.lock:
            return len(self.subscriptions)
            
    def get_all_symbols(self):
        """Önbellekteki tüm sembolleri döndür"""
        with self.lock:
            # Aktif veri ve snapshot verilerin birleşimi
            all_symbols = set(self.data.keys()) | set(self.snapshot_data.keys())
            return list(all_symbols)
    
    def get_all_snapshot_data(self):
        """Tüm snapshot verilerini içeren sözlüğü döndür"""
        with self.lock:
            return self.snapshot_data
    
    def get_symbol_count(self):
        """Önbellekte toplam kaç sembol olduğunu döndür"""
        with self.lock:
            return len(self.snapshot_data)
    
    def save_cache_to_file(self, filename="market_data_cache.pkl"):
        """Önbelleği dosyaya kaydet"""
        try:
            # Sadece snapshot verilerini kaydet (ticker objeleri pickle edilebilir değil)
            snapshot_summary = {}
            
            for symbol, ticker in self.snapshot_data.items():
                # Her sembol için önemli değerleri al
                ticker_summary = {}
                
                if hasattr(ticker, 'last') and ticker.last is not None and not math.isnan(ticker.last):
                    ticker_summary['last'] = ticker.last
                    
                if hasattr(ticker, 'bid') and ticker.bid is not None and not math.isnan(ticker.bid):
                    ticker_summary['bid'] = ticker.bid
                    
                if hasattr(ticker, 'ask') and ticker.ask is not None and not math.isnan(ticker.ask):
                    ticker_summary['ask'] = ticker.ask
                    
                if hasattr(ticker, 'close') and ticker.close is not None and not math.isnan(ticker.close):
                    ticker_summary['close'] = ticker.close
                    
                if hasattr(ticker, 'volume') and ticker.volume is not None and not math.isnan(ticker.volume):
                    ticker_summary['volume'] = ticker.volume
                
                # Eğer özetlenen veri doluysa
                if ticker_summary:
                    snapshot_summary[symbol] = ticker_summary
            
            # Zamanı ekle
            cache_data = {
                'timestamp': datetime.datetime.now().isoformat(),
                'symbols': list(snapshot_summary.keys()),
                'data': snapshot_summary
            }
            
            # JSON formatında kaydet
            with open(filename, 'w') as f:
                json.dump(cache_data, f)
                
            print(f"Önbellek {filename} dosyasına kaydedildi ({len(snapshot_summary)} sembol)")
            return True
        except Exception as e:
            print(f"Önbellek kaydetme hatası: {e}")
            return False
    
    def load_cache_from_file(self, filename="market_data_cache.pkl"):
        """Önbelleği dosyadan yükle"""
        try:
            if not os.path.exists(filename):
                print(f"Önbellek dosyası bulunamadı: {filename}")
                return False
                
            # JSON formatında oku
            with open(filename, 'r') as f:
                cache_data = json.load(f)
            
            # Zaman bilgisini kontrol et (24 saatten eski mi?)
            cache_time = datetime.datetime.fromisoformat(cache_data['timestamp'])
            now = datetime.datetime.now()
            
            if (now - cache_time).total_seconds() > 86400:  # 24 saat
                print(f"Önbellek dosyası çok eski ({cache_time}), yükleme yapılmadı")
                return False
            
            # Snapshot verilerini yükle
            data_dict = cache_data['data']
            loaded_count = 0
            
            for symbol, values in data_dict.items():
                # Ticker oluştur ve sembole ekle
                ticker = type('Ticker', (), {})
                
                for field, value in values.items():
                    setattr(ticker, field, value)
                
                # Snapshot verilerine ekle
                self.snapshot_data[symbol] = ticker
                loaded_count += 1
            
            print(f"Önbellek {filename} dosyasından yüklendi ({loaded_count} sembol)")
            return True
        except Exception as e:
            print(f"Önbellek yükleme hatası: {e}")
            return False 