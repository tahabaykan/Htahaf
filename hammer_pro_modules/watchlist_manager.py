"""
Hammer Pro Watchlist Manager Module
Watchlist oluşturma ve yönetimi
"""

import asyncio
import logging
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from connection import HammerProConnection
from config import HammerProConfig

class HammerProWatchlistManager:
    """Hammer Pro Watchlist Yöneticisi"""
    
    def __init__(self, connection: HammerProConnection):
        """Watchlist manager'ı başlat"""
        self.connection = connection
        self.logger = logging.getLogger(__name__)
        
        # Mevcut portföyler
        self.portfolios: List[Dict[str, Any]] = []
        
    async def get_portfolios(self) -> List[Dict[str, Any]]:
        """Mevcut portföyleri al (dokümantasyona göre enumPorts)"""
        try:
            msg = {
                "cmd": HammerProConfig.get_api_command("enum_ports"),
                "reqID": f"get_ports_{datetime.now().timestamp()}"
            }
            
            await self.connection.send_message(msg)
            response = await self.connection._wait_for_response(msg["reqID"])
            
            if response and response.get("success") == "OK":
                result = response.get("result", {})
                self.portfolios = result.get("ports", [])
                self.logger.info(f"{len(self.portfolios)} portföy bulundu")
                return self.portfolios
            else:
                self.logger.error("Portföy listesi alınamadı")
                return []
                
        except Exception as e:
            self.logger.error(f"Portföy alma hatası: {e}")
            return []
    
    async def get_portfolio_symbols(self, port_id: str, detailed: bool = False) -> List[str]:
        """Portföydeki sembolleri al (dokümantasyona göre enumPortSymbols)"""
        try:
            msg = {
                "cmd": HammerProConfig.get_api_command("enum_port_symbols"),
                "portID": port_id,
                "detailed": detailed,
                "reqID": f"get_symbols_{port_id}_{datetime.now().timestamp()}"
            }
            
            await self.connection.send_message(msg)
            response = await self.connection._wait_for_response(msg["reqID"])
            
            if response and response.get("success") == "OK":
                result = response.get("result", [])
                if detailed:
                    # Detailed response - symbol listesi
                    symbols = [item.get("sym", "") for item in result if item.get("sym")]
                else:
                    # Simple response - string listesi
                    symbols = result if isinstance(result, list) else []
                
                self.logger.info(f"Portföy {port_id}: {len(symbols)} sembol")
                return symbols
            else:
                self.logger.error(f"Portföy {port_id} sembolleri alınamadı")
                return []
                
        except Exception as e:
            self.logger.error(f"Portföy sembolleri alma hatası: {e}")
            return []
    
    async def create_watchlist(self, name: str, symbols: List[str]) -> Optional[str]:
        """Yeni watchlist oluştur (dokümantasyona göre addToPort)"""
        try:
            msg = {
                "cmd": HammerProConfig.get_api_command("add_to_port"),
                "new": True,
                "name": name,
                "sym": symbols,
                "reqID": f"create_watchlist_{datetime.now().timestamp()}"
            }
            
            await self.connection.send_message(msg)
            response = await self.connection._wait_for_response(msg["reqID"])
            
            if response and response.get("success") == "OK":
                self.logger.info(f"Watchlist '{name}' oluşturuldu: {len(symbols)} sembol")
                return name
            else:
                self.logger.error(f"Watchlist '{name}' oluşturulamadı")
                return None
                
        except Exception as e:
            self.logger.error(f"Watchlist oluşturma hatası: {e}")
            return None
    
    async def update_watchlist(self, port_id: str, symbols: List[str]) -> bool:
        """Mevcut watchlist'i güncelle"""
        try:
            msg = {
                "cmd": HammerProConfig.get_api_command("add_to_port"),
                "portID": port_id,
                "sym": symbols,
                "reqID": f"update_watchlist_{port_id}_{datetime.now().timestamp()}"
            }
            
            await self.connection.send_message(msg)
            response = await self.connection._wait_for_response(msg["reqID"])
            
            if response and response.get("success") == "OK":
                self.logger.info(f"Watchlist {port_id} güncellendi: {len(symbols)} sembol")
                return True
            else:
                self.logger.error(f"Watchlist {port_id} güncellenemedi")
                return False
                
        except Exception as e:
            self.logger.error(f"Watchlist güncelleme hatası: {e}")
            return False
    
    async def remove_from_watchlist(self, port_id: str, symbols: List[str]) -> bool:
        """Watchlist'ten sembol kaldır"""
        try:
            msg = {
                "cmd": HammerProConfig.get_api_command("remove_from_port"),
                "portID": port_id,
                "sym": symbols,
                "reqID": f"remove_symbols_{port_id}_{datetime.now().timestamp()}"
            }
            
            await self.connection.send_message(msg)
            response = await self.connection._wait_for_response(msg["reqID"])
            
            if response and response.get("success") == "OK":
                self.logger.info(f"Watchlist {port_id}'den {len(symbols)} sembol kaldırıldı")
                return True
            else:
                self.logger.error(f"Watchlist {port_id}'den sembol kaldırılamadı")
                return False
                
        except Exception as e:
            self.logger.error(f"Watchlist'ten kaldırma hatası: {e}")
            return False
    
    def filter_symbols_by_type(self, csv_data: pd.DataFrame, watchlist_type: str, max_symbols: int = 50) -> List[str]:
        """CSV verilerine göre sembolleri filtrele"""
        try:
            symbol_column = HammerProConfig.CSV_SETTINGS["symbol_column"]
            final_thg_column = HammerProConfig.CSV_SETTINGS["final_thg_column"]
            
            # Benzersiz sembolleri al
            symbols = csv_data[symbol_column].dropna().unique().tolist()
            
            if watchlist_type == "top_final_thg":
                # En yüksek FINAL_THG'ye göre sırala
                sorted_data = csv_data.sort_values(final_thg_column, ascending=False)
                symbols = sorted_data[symbol_column].dropna().unique().tolist()[:max_symbols]
                
            elif watchlist_type == "bottom_final_thg":
                # En düşük FINAL_THG'ye göre sırala
                sorted_data = csv_data.sort_values(final_thg_column, ascending=True)
                symbols = sorted_data[symbol_column].dropna().unique().tolist()[:max_symbols]
                
            elif watchlist_type == "custom_filter":
                # Özel filtreleme (gelecekte genişletilebilir)
                symbols = symbols[:max_symbols]
                
            else:
                # Tüm semboller (maksimum sayıya kadar)
                symbols = symbols[:max_symbols]
            
            self.logger.info(f"Filtrelenmiş {len(symbols)} sembol: {watchlist_type}")
            return symbols
            
        except Exception as e:
            self.logger.error(f"Sembol filtreleme hatası: {e}")
            return []
    
    async def create_watchlist_from_csv(self, csv_data: pd.DataFrame, watchlist_name: str, 
                                      watchlist_type: str = "all", max_symbols: int = 50) -> Tuple[bool, List[str]]:
        """CSV verilerinden watchlist oluştur"""
        try:
            # Sembolleri filtrele
            symbols = self.filter_symbols_by_type(csv_data, watchlist_type, max_symbols)
            
            if not symbols:
                self.logger.error("Filtrelenmiş sembol bulunamadı")
                return False, []
            
            # Watchlist oluştur
            result = await self.create_watchlist(watchlist_name, symbols)
            
            if result:
                return True, symbols
            else:
                return False, []
                
        except Exception as e:
            self.logger.error(f"CSV'den watchlist oluşturma hatası: {e}")
            return False, []
    
    async def get_watchlist_info(self, port_id: str) -> Optional[Dict[str, Any]]:
        """Watchlist bilgilerini al"""
        try:
            # Portföy listesini güncelle
            await self.get_portfolios()
            
            # Portföyü bul
            portfolio = next((p for p in self.portfolios if p.get("portID") == port_id), None)
            
            if portfolio:
                # Sembolleri al
                symbols = await self.get_portfolio_symbols(port_id)
                
                return {
                    "portID": port_id,
                    "name": portfolio.get("name", ""),
                    "symbols": symbols,
                    "symbol_count": len(symbols)
                }
            else:
                self.logger.error(f"Portföy {port_id} bulunamadı")
                return None
                
        except Exception as e:
            self.logger.error(f"Watchlist bilgisi alma hatası: {e}")
            return None 