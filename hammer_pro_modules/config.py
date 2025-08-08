"""
Hammer Pro Configuration Module
Hammer Pro API ayarları ve sabitleri
"""

import os
from typing import Dict, Any

class HammerProConfig:
    """Hammer Pro yapılandırma sınıfı"""
    
    # Varsayılan bağlantı ayarları
    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 8080
    DEFAULT_TIMEOUT = 30
    
    # API Komutları (dokümantasyona göre)
    API_COMMANDS = {
        "connect": "connect",
        "enum_ports": "enumPorts",
        "enum_port_symbols": "enumPortSymbols", 
        "add_to_port": "addToPort",
        "remove_from_port": "removeFromPort",
        "get_symbol_snapshot": "getSymbolSnapshot",
        "get_port_snapshot": "getPortSnapshot",
        "start_data_streamer": "startDataStreamer",
        "subscribe": "subscribe",
        "unsubscribe": "unsubscribe",
        # Layout komutları
        "create_layout": "createLayout",
        "load_layout": "loadLayout", 
        "save_layout": "saveLayout",
        "add_to_layout": "addToLayout"
    }
    
    # Watchlist türleri
    WATCHLIST_TYPES = {
        "all_symbols": "all",
        "top_final_thg": "top_final_thg", 
        "bottom_final_thg": "bottom_final_thg",
        "custom_filter": "custom_filter"
    }
    
    # CSV dosya ayarları
    CSV_SETTINGS = {
        "default_file": "ssfinekheldkuponlu.csv",
        "symbol_column": "PREF IBKR",
        "final_thg_column": "FINAL_THG",
        "company_column": "Company"
    }
    
    # Log ayarları
    LOG_SETTINGS = {
        "level": "INFO",
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "file": "hammer_pro.log"
    }
    
    @classmethod
    def get_connection_config(cls) -> Dict[str, Any]:
        """Bağlantı yapılandırmasını döndür"""
        return {
            "host": os.getenv("HAMMER_PRO_HOST", cls.DEFAULT_HOST),
            "port": int(os.getenv("HAMMER_PRO_PORT", cls.DEFAULT_PORT)),
            "timeout": cls.DEFAULT_TIMEOUT
        }
    
    @classmethod
    def get_api_command(cls, command_name: str) -> str:
        """API komutunu döndür"""
        return cls.API_COMMANDS.get(command_name, command_name)
    
    @classmethod
    def get_watchlist_type(cls, type_name: str) -> str:
        """Watchlist türünü döndür"""
        return cls.WATCHLIST_TYPES.get(type_name, "all") 