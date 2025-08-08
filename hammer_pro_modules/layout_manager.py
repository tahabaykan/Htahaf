"""
Hammer Pro Layout Manager Module
Layout oluşturma ve yönetimi
"""

import asyncio
import logging
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from connection import HammerProConnection
from config import HammerProConfig

class HammerProLayoutManager:
    """Hammer Pro Layout Yöneticisi"""
    
    def __init__(self, connection: HammerProConnection):
        """Layout manager'ı başlat"""
        self.connection = connection
        self.logger = logging.getLogger(__name__)
        
        # Mevcut layout'lar
        self.layouts: List[Dict[str, Any]] = []
        
    async def create_layout(self, name: str, symbols: List[str]) -> Optional[str]:
        """Yeni layout oluştur"""
        try:
            msg = {
                "cmd": HammerProConfig.get_api_command("create_layout"),
                "name": name,
                "symbols": symbols,
                "reqID": f"create_layout_{datetime.now().timestamp()}"
            }
            
            await self.connection.send_message(msg)
            response = await self.connection._wait_for_response(msg["reqID"])
            
            if response and response.get("success") == "OK":
                self.logger.info(f"Layout '{name}' oluşturuldu: {len(symbols)} sembol")
                return name
            else:
                self.logger.error(f"Layout '{name}' oluşturulamadı")
                return None
                
        except Exception as e:
            self.logger.error(f"Layout oluşturma hatası: {e}")
            return None
    
    async def load_layout(self, name: str) -> bool:
        """Layout yükle"""
        try:
            msg = {
                "cmd": HammerProConfig.get_api_command("load_layout"),
                "name": name,
                "reqID": f"load_layout_{name}_{datetime.now().timestamp()}"
            }
            
            await self.connection.send_message(msg)
            response = await self.connection._wait_for_response(msg["reqID"])
            
            if response and response.get("success") == "OK":
                self.logger.info(f"Layout '{name}' yüklendi")
                return True
            else:
                self.logger.error(f"Layout '{name}' yüklenemedi")
                return False
                
        except Exception as e:
            self.logger.error(f"Layout yükleme hatası: {e}")
            return False
    
    async def save_layout(self, name: str) -> bool:
        """Layout kaydet"""
        try:
            msg = {
                "cmd": HammerProConfig.get_api_command("save_layout"),
                "name": name,
                "reqID": f"save_layout_{name}_{datetime.now().timestamp()}"
            }
            
            await self.connection.send_message(msg)
            response = await self.connection._wait_for_response(msg["reqID"])
            
            if response and response.get("success") == "OK":
                self.logger.info(f"Layout '{name}' kaydedildi")
                return True
            else:
                self.logger.error(f"Layout '{name}' kaydedilemedi")
                return False
                
        except Exception as e:
            self.logger.error(f"Layout kaydetme hatası: {e}")
            return False
    
    async def add_symbols_to_layout(self, layout_name: str, symbols: List[str]) -> bool:
        """Layout'a sembol ekle"""
        try:
            msg = {
                "cmd": HammerProConfig.get_api_command("add_to_layout"),
                "layoutName": layout_name,
                "symbols": symbols,
                "reqID": f"add_to_layout_{layout_name}_{datetime.now().timestamp()}"
            }
            
            await self.connection.send_message(msg)
            response = await self.connection._wait_for_response(msg["reqID"])
            
            if response and response.get("success") == "OK":
                self.logger.info(f"Layout '{layout_name}'a {len(symbols)} sembol eklendi")
                return True
            else:
                self.logger.error(f"Layout '{layout_name}'a sembol eklenemedi")
                return False
                
        except Exception as e:
            self.logger.error(f"Layout'a sembol ekleme hatası: {e}")
            return False
    
    def filter_symbols_for_layout(self, csv_data: pd.DataFrame, layout_type: str, max_symbols: int = 20) -> List[str]:
        """Layout için sembolleri filtrele (daha az sembol)"""
        try:
            symbol_column = HammerProConfig.CSV_SETTINGS["symbol_column"]
            final_thg_column = HammerProConfig.CSV_SETTINGS["final_thg_column"]
            
            # Benzersiz sembolleri al
            symbols = csv_data[symbol_column].dropna().unique().tolist()
            
            if layout_type == "top_final_thg":
                # En yüksek FINAL_THG'ye göre sırala
                sorted_data = csv_data.sort_values(final_thg_column, ascending=False)
                symbols = sorted_data[symbol_column].dropna().unique().tolist()[:max_symbols]
                
            elif layout_type == "bottom_final_thg":
                # En düşük FINAL_THG'ye göre sırala
                sorted_data = csv_data.sort_values(final_thg_column, ascending=True)
                symbols = sorted_data[symbol_column].dropna().unique().tolist()[:max_symbols]
                
            else:
                # Tüm semboller (maksimum sayıya kadar)
                symbols = symbols[:max_symbols]
            
            self.logger.info(f"Layout için filtrelenmiş {len(symbols)} sembol: {layout_type}")
            return symbols
            
        except Exception as e:
            self.logger.error(f"Layout sembol filtreleme hatası: {e}")
            return []
    
    async def create_layout_from_csv(self, csv_data: pd.DataFrame, layout_name: str, 
                                   layout_type: str = "all", max_symbols: int = 20) -> Tuple[bool, List[str]]:
        """CSV verilerinden layout oluştur"""
        try:
            # Sembolleri filtrele (layout için daha az)
            symbols = self.filter_symbols_for_layout(csv_data, layout_type, max_symbols)
            
            if not symbols:
                self.logger.error("Layout için filtrelenmiş sembol bulunamadı")
                return False, []
            
            # Layout oluştur
            result = await self.create_layout(layout_name, symbols)
            
            if result:
                return True, symbols
            else:
                return False, []
                
        except Exception as e:
            self.logger.error(f"CSV'den layout oluşturma hatası: {e}")
            return False, [] 