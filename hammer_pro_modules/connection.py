"""
Hammer Pro Connection Module
WebSocket bağlantısı ve API iletişimi
"""

import asyncio
import websockets
import json
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from config import HammerProConfig

class HammerProConnection:
    """Hammer Pro WebSocket bağlantı sınıfı"""
    
    def __init__(self, host: str = None, port: int = None, password: str = None):
        """Bağlantı sınıfını başlat"""
        config = HammerProConfig.get_connection_config()
        self.host = host or config["host"]
        self.port = port or config["port"]
        self.password = password
        self.websocket = None
        self.connected = False
        self.logger = logging.getLogger(__name__)
        
        # Message handlers
        self.message_handlers: Dict[str, Callable] = {}
        
        # Response tracking
        self.pending_responses: Dict[str, asyncio.Future] = {}
        
    async def connect(self) -> bool:
        """Hammer Pro'ya bağlan"""
        try:
            ws_url = f"ws://{self.host}:{self.port}"
            self.logger.info(f"Hammer Pro'ya bağlanıyor: {ws_url}")
            
            self.websocket = await websockets.connect(ws_url)
            self.connected = True
            
            # Kimlik doğrulama (dokümantasyona göre)
            if self.password:
                auth_success = await self._authenticate()
                if not auth_success:
                    self.connected = False
                    await self.websocket.close()
                    return False
            
            # Message listener başlat
            asyncio.create_task(self._listen_for_messages())
            
            self.logger.info("Hammer Pro'ya başarıyla bağlandı")
            return True
            
        except Exception as e:
            self.logger.error(f"Bağlantı hatası: {e}")
            self.connected = False
            return False
    
    async def _authenticate(self) -> bool:
        """Şifre ile kimlik doğrulama"""
        try:
            auth_msg = {
                "cmd": HammerProConfig.get_api_command("connect"),
                "pwd": self.password,
                "reqID": f"auth_{datetime.now().timestamp()}"
            }
            
            await self.send_message(auth_msg)
            
            # Auth response bekle
            response = await self._wait_for_response(auth_msg["reqID"], timeout=10)
            
            if response and response.get("success") == "OK":
                self.logger.info("Kimlik doğrulama başarılı")
                return True
            else:
                self.logger.error("Kimlik doğrulama başarısız")
                return False
                
        except Exception as e:
            self.logger.error(f"Kimlik doğrulama hatası: {e}")
            return False
    
    async def _listen_for_messages(self):
        """Gelen mesajları dinle"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                await self._handle_message(data)
        except Exception as e:
            self.logger.error(f"Message listener hatası: {e}")
            self.connected = False
    
    async def _handle_message(self, data: Dict[str, Any]):
        """Gelen mesajı işle"""
        try:
            cmd = data.get("cmd", "")
            req_id = data.get("reqID", "")
            
            # Response tracking
            if req_id in self.pending_responses:
                future = self.pending_responses.pop(req_id)
                future.set_result(data)
            
            # Message handler çağır
            if cmd in self.message_handlers:
                await self.message_handlers[cmd](data)
            else:
                self.logger.debug(f"Unhandled message: {cmd}")
                
        except Exception as e:
            self.logger.error(f"Message handling hatası: {e}")
    
    async def send_message(self, message: Dict[str, Any]) -> bool:
        """Mesaj gönder"""
        try:
            if not self.connected or not self.websocket:
                raise Exception("Bağlantı yok")
            
            await self.websocket.send(json.dumps(message))
            return True
            
        except Exception as e:
            self.logger.error(f"Message sending hatası: {e}")
            return False
    
    async def _wait_for_response(self, req_id: str, timeout: int = 30) -> Optional[Dict[str, Any]]:
        """Response bekle"""
        try:
            future = asyncio.Future()
            self.pending_responses[req_id] = future
            
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
            
        except asyncio.TimeoutError:
            self.logger.error(f"Response timeout for reqID: {req_id}")
            self.pending_responses.pop(req_id, None)
            return None
        except Exception as e:
            self.logger.error(f"Response waiting hatası: {e}")
            return None
    
    def register_handler(self, cmd: str, handler: Callable):
        """Message handler kaydet"""
        self.message_handlers[cmd] = handler
    
    async def disconnect(self):
        """Bağlantıyı kes"""
        try:
            if self.websocket:
                await self.websocket.close()
            self.connected = False
            self.logger.info("Hammer Pro bağlantısı kesildi")
        except Exception as e:
            self.logger.error(f"Disconnect hatası: {e}")
    
    def is_connected(self) -> bool:
        """Bağlantı durumunu kontrol et"""
        return self.connected and self.websocket is not None 