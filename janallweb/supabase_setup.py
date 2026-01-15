"""
Supabase entegrasyonu için setup ve helper fonksiyonlar.

Supabase kullanarak:
1. Veritabanı işlemlerini hızlandırır (PostgreSQL)
2. Real-time subscriptions ile market data güncellemelerini optimize eder
3. Edge functions ile hesaplamaları hızlandırır
4. Caching ile tekrarlayan sorguları azaltır
"""

import os
from supabase import create_client, Client
from dotenv import load_dotenv
import logging
from typing import Optional, Dict, List
import json
from datetime import datetime

load_dotenv()

logger = logging.getLogger(__name__)

class SupabaseClient:
    """Supabase client wrapper"""
    
    def __init__(self):
        self.url = os.getenv('SUPABASE_URL')
        self.key = os.getenv('SUPABASE_ANON_KEY')
        self.service_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        
        if not self.url or not self.key:
            logger.warning("Supabase credentials not found. Supabase features will be disabled.")
            self.client: Optional[Client] = None
        else:
            self.client = create_client(self.url, self.key)
            logger.info("Supabase client initialized")
    
    def is_available(self) -> bool:
        """Supabase kullanılabilir mi?"""
        return self.client is not None
    
    # ==================== Market Data Caching ====================
    
    def cache_market_data(self, symbol: str, data: Dict):
        """Market data'yı cache'le (hızlı erişim için)"""
        if not self.is_available():
            return False
        
        try:
            # Market data tablosuna kaydet (upsert)
            result = self.client.table('market_data').upsert({
                'symbol': symbol,
                'data': json.dumps(data),
                'updated_at': datetime.utcnow().isoformat()
            }).execute()
            return True
        except Exception as e:
            logger.error(f"Market data cache error: {e}")
            return False
    
    def get_cached_market_data(self, symbol: str) -> Optional[Dict]:
        """Cache'den market data al"""
        if not self.is_available():
            return None
        
        try:
            result = self.client.table('market_data').select('*').eq('symbol', symbol).execute()
            if result.data:
                return json.loads(result.data[0]['data'])
            return None
        except Exception as e:
            logger.error(f"Get cached market data error: {e}")
            return None
    
    def batch_cache_market_data(self, data_dict: Dict[str, Dict]):
        """Birden fazla market data'yı toplu olarak cache'le (daha hızlı)"""
        if not self.is_available():
            return False
        
        try:
            records = []
            for symbol, data in data_dict.items():
                records.append({
                    'symbol': symbol,
                    'data': json.dumps(data),
                    'updated_at': datetime.utcnow().isoformat()
                })
            
            # Batch upsert (PostgreSQL'in hızlı bulk insert özelliği)
            self.client.table('market_data').upsert(records).execute()
            return True
        except Exception as e:
            logger.error(f"Batch cache market data error: {e}")
            return False
    
    # ==================== Positions & Orders ====================
    
    def save_positions(self, positions: List[Dict]):
        """Pozisyonları veritabanına kaydet"""
        if not self.is_available():
            return False
        
        try:
            # Mevcut pozisyonları sil ve yenilerini ekle
            self.client.table('positions').delete().neq('id', 0).execute()  # Tümünü sil
            
            # Yeni pozisyonları ekle
            if positions:
                self.client.table('positions').insert(positions).execute()
            return True
        except Exception as e:
            logger.error(f"Save positions error: {e}")
            return False
    
    def get_positions(self) -> List[Dict]:
        """Pozisyonları veritabanından al"""
        if not self.is_available():
            return []
        
        try:
            result = self.client.table('positions').select('*').execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Get positions error: {e}")
            return []
    
    def save_orders(self, orders: List[Dict]):
        """Emirleri veritabanına kaydet"""
        if not self.is_available():
            return False
        
        try:
            # Mevcut emirleri sil ve yenilerini ekle
            self.client.table('orders').delete().neq('id', 0).execute()
            
            # Yeni emirleri ekle
            if orders:
                self.client.table('orders').insert(orders).execute()
            return True
        except Exception as e:
            logger.error(f"Save orders error: {e}")
            return False
    
    def get_orders(self) -> List[Dict]:
        """Emirleri veritabanından al"""
        if not self.is_available():
            return []
        
        try:
            result = self.client.table('orders').select('*').execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Get orders error: {e}")
            return []
    
    # ==================== CSV Data Caching ====================
    
    def cache_csv_data(self, filename: str, data: List[Dict]):
        """CSV verilerini cache'le (tekrar yükleme hızlandırır)"""
        if not self.is_available():
            return False
        
        try:
            self.client.table('csv_cache').upsert({
                'filename': filename,
                'data': json.dumps(data),
                'updated_at': datetime.utcnow().isoformat()
            }).execute()
            return True
        except Exception as e:
            logger.error(f"Cache CSV data error: {e}")
            return False
    
    def get_cached_csv_data(self, filename: str) -> Optional[List[Dict]]:
        """Cache'den CSV verilerini al"""
        if not self.is_available():
            return None
        
        try:
            result = self.client.table('csv_cache').select('*').eq('filename', filename).execute()
            if result.data:
                return json.loads(result.data[0]['data'])
            return None
        except Exception as e:
            logger.error(f"Get cached CSV data error: {e}")
            return None
    
    # ==================== Real-time Subscriptions ====================
    
    def subscribe_market_data(self, callback):
        """Market data için real-time subscription (Supabase Realtime)"""
        if not self.is_available():
            return None
        
        try:
            # Supabase Realtime subscription
            subscription = self.client.table('market_data').on(
                'UPDATE',
                callback
            ).subscribe()
            return subscription
        except Exception as e:
            logger.error(f"Subscribe market data error: {e}")
            return None
    
    def unsubscribe(self, subscription):
        """Subscription'ı iptal et"""
        if subscription:
            try:
                self.client.remove_subscription(subscription)
            except Exception as e:
                logger.error(f"Unsubscribe error: {e}")

# Global instance
supabase_client = SupabaseClient()









