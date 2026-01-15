"""engine/data_bus.py

Redis Streams için helper fonksiyonları içerir: grup oluşturma, xadd, xreadgroup

Bu modül Redis Streams üzerinden pub/sub ve consumer group pattern'lerini
destekler. Tüm servisler bu modülü kullanarak Redis ile iletişim kurar.

Kullanım:
    bus = RedisBus()
    await bus.connect()
    await bus.ensure_group('ticks', 'strategy_group')
    await bus.publish('ticks', {'symbol': 'AAPL', 'price': '150.0'})
    messages = await bus.read_group('ticks', 'strategy_group', 'worker1')
    await bus.close()

Redis Streams Hakkında:
    - Streams: Append-only log yapısı (kafka-like)
    - Consumer Groups: Birden fazla consumer'ın aynı stream'i tüketmesi
    - XADD: Stream'e mesaj ekleme
    - XREADGROUP: Consumer group'tan mesaj okuma
    - XACK: Mesaj işlendi olarak işaretleme
"""

import asyncio
import os
from typing import Dict, List, Optional, Tuple, Any
from aioredis import Redis, from_url
from aioredis.exceptions import ResponseError

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')


class RedisBus:
    """Redis Streams wrapper class"""
    
    def __init__(self, redis_url: Optional[str] = None):
        """
        Args:
            redis_url: Redis connection URL (default: env REDIS_URL veya redis://localhost:6379)
        """
        self._redis_url = redis_url or REDIS_URL
        self._r: Optional[Redis] = None
        self._connected = False
    
    async def connect(self):
        """Redis'e bağlan"""
        if self._connected and self._r:
            return
        
        try:
            self._r = await from_url(self._redis_url, decode_responses=False)
            # Connection test
            await self._r.ping()
            self._connected = True
        except Exception as e:
            self._connected = False
            raise ConnectionError(f"Redis bağlantı hatası: {e}")
    
    async def close(self):
        """Redis bağlantısını kapat"""
        if self._r:
            await self._r.close()
            self._r = None
            self._connected = False
    
    async def ensure_group(self, stream: str, group: str, start_id: str = '$'):
        """
        Consumer group oluştur (yoksa).
        
        Args:
            stream: Stream adı
            group: Consumer group adı
            start_id: Başlangıç ID (default: '$' = sadece yeni mesajlar)
        """
        if not self._connected:
            await self.connect()
        
        try:
            # Stream yoksa oluştur (mkstream=True)
            await self._r.xgroup_create(
                stream, 
                group, 
                id=start_id, 
                mkstream=True
            )
        except ResponseError as e:
            # Group zaten varsa hata verme (BUSYGROUP)
            if "BUSYGROUP" not in str(e):
                raise
        except Exception as e:
            # Diğer hatalar için tekrar dene
            if "BUSYGROUP" not in str(e):
                raise
    
    async def publish(self, stream: str, data: Dict[str, Any]) -> str:
        """
        Stream'e mesaj ekle (XADD).
        
        Args:
            stream: Stream adı
            data: Mesaj data (dict)
            
        Returns:
            Message ID (stream ID)
        """
        if not self._connected:
            await self.connect()
        
        # String'e çevir (Redis binary string bekler)
        encoded_data = {}
        for k, v in data.items():
            if isinstance(v, (int, float)):
                encoded_data[k] = str(v)
            elif isinstance(v, str):
                encoded_data[k] = v
            else:
                encoded_data[k] = str(v)
        
        msg_id = await self._r.xadd(stream, encoded_data)
        return msg_id.decode() if isinstance(msg_id, bytes) else msg_id
    
    async def read_group(
        self,
        stream: str,
        group: str,
        consumer: str,
        block: int = 2000,
        count: int = 10,
        start_id: str = '>'
    ) -> List[Tuple[str, Dict[str, str]]]:
        """
        Consumer group'tan mesaj oku (XREADGROUP).
        
        Args:
            stream: Stream adı
            group: Consumer group adı
            consumer: Consumer adı
            block: Block süresi (ms, 0 = blocking)
            count: Maksimum mesaj sayısı
            start_id: Başlangıç ID ('>' = pending mesajlar, '0' = baştan)
            
        Returns:
            List of (message_id, data_dict) tuples
        """
        if not self._connected:
            await self.connect()
        
        try:
            resp = await self._r.xreadgroup(
                group,
                consumer,
                streams={stream: start_id},
                count=count,
                block=block
            )
            
            if not resp:
                return []
            
            # Decode response
            messages = []
            for stream_name, stream_messages in resp:
                for msg_id, fields in stream_messages:
                    # Decode bytes to string
                    msg_id_str = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
                    data = {}
                    for k, v in fields.items():
                        key = k.decode() if isinstance(k, bytes) else k
                        val = v.decode() if isinstance(v, bytes) else v
                        data[key] = val
                    messages.append((msg_id_str, data))
            
            return messages
        except Exception as e:
            # Stream/group yoksa boş liste döndür
            if "NOGROUP" in str(e) or "no such key" in str(e).lower():
                return []
            raise
    
    async def ack(self, stream: str, group: str, *message_ids: str):
        """
        Mesajları işlendi olarak işaretle (XACK).
        
        Args:
            stream: Stream adı
            group: Consumer group adı
            *message_ids: İşaretlenecek mesaj ID'leri
        """
        if not self._connected:
            await self.connect()
        
        if message_ids:
            await self._r.xack(stream, group, *message_ids)
    
    async def pending_info(self, stream: str, group: str) -> Dict:
        """
        Pending mesaj bilgilerini al (XPENDING).
        
        Returns:
            Pending mesaj sayısı ve detayları
        """
        if not self._connected:
            await self.connect()
        
        try:
            info = await self._r.xpending(stream, group)
            return info
        except Exception:
            return {}
    
    @property
    def redis(self) -> Optional[Redis]:
        """Direct Redis client access (advanced usage)"""
        return self._r








