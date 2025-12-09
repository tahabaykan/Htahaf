"""
Merkezi logging sistemi
"""

import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional

class JanAllSecLogger:
    """Merkezi logging sistemi - Tüm logları yönetir"""
    
    def __init__(self, name: str = "janallsec", log_dir: str = "logs", 
                 level: str = "INFO", max_bytes: int = 10485760, 
                 backup_count: int = 5, console_output: bool = True):
        """
        Logger'ı başlat
        
        Args:
            name: Logger adı
            log_dir: Log dosyalarının saklanacağı dizin
            level: Log seviyesi (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            max_bytes: Maksimum log dosyası boyutu (bytes)
            backup_count: Kaç tane backup dosyası tutulacak
            console_output: Konsola da yazdırılsın mı
        """
        self.name = name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Logger oluştur
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))
        
        # Eğer zaten handler'lar varsa, tekrar ekleme
        if self.logger.handlers:
            return
        
        # Formatter oluştur
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # File handler - Rotating file handler
        log_file = self.log_dir / f"{name}_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(getattr(logging, level.upper()))
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        
        # Console handler (opsiyonel)
        if console_output:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(getattr(logging, level.upper()))
            console_formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%H:%M:%S'
            )
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)
        
        # Error log dosyası (sadece ERROR ve CRITICAL)
        error_log_file = self.log_dir / f"{name}_errors_{datetime.now().strftime('%Y%m%d')}.log"
        error_handler = RotatingFileHandler(
            error_log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        self.logger.addHandler(error_handler)
    
    def debug(self, message: str, *args, **kwargs):
        """Debug mesajı logla"""
        self.logger.debug(message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        """Info mesajı logla"""
        self.logger.info(message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        """Warning mesajı logla"""
        self.logger.warning(message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        """Error mesajı logla"""
        self.logger.error(message, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        """Critical mesajı logla"""
        self.logger.critical(message, *args, **kwargs)
    
    def exception(self, message: str, *args, **kwargs):
        """Exception bilgisiyle error logla"""
        self.logger.exception(message, *args, **kwargs)

# Global logger instance
_logger_instance: Optional[JanAllSecLogger] = None

def get_logger(name: str = "janallsec", **kwargs) -> JanAllSecLogger:
    """
    Global logger instance'ı döndür
    
    Args:
        name: Logger adı
        **kwargs: Logger parametreleri
        
    Returns:
        JanAllSecLogger instance
    """
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = JanAllSecLogger(name=name, **kwargs)
    return _logger_instance

def setup_logger_from_config(config):
    """Config'den logger ayarlarını yükle"""
    log_config = config.get('logging', {})
    return get_logger(
        name="janallsec",
        log_dir=config.get('paths', {}).get('log_dir', 'logs'),
        level=log_config.get('level', 'INFO'),
        max_bytes=log_config.get('max_bytes', 10485760),
        backup_count=log_config.get('backup_count', 5),
        console_output=log_config.get('console_output', True)
    )


