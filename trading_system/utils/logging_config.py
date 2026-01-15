"""utils/logging_config.py

Logging konfigürasyonu - loguru kullanarak structured logging.

Kullanım:
    from utils.logging_config import setup_logging, get_logger
    
    setup_logging(level="INFO")
    logger = get_logger("module_name")
    logger.info("Mesaj")
"""

import sys
import os
from pathlib import Path
from typing import Optional

try:
    from loguru import logger
    LOGURU_AVAILABLE = True
except ImportError:
    LOGURU_AVAILABLE = False
    import logging
    logger = None


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    rotation: str = "10 MB",
    retention: str = "7 days",
    format_string: Optional[str] = None
):
    """
    Logging'i yapılandır.
    
    Args:
        level: Log seviyesi (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Log dosyası yolu (None ise sadece console)
        rotation: Log rotation (örn: "10 MB", "1 day")
        retention: Log retention (örn: "7 days", "1 month")
        format_string: Custom format string
    """
    if not LOGURU_AVAILABLE:
        # Fallback to standard logging
        logging.basicConfig(
            level=getattr(logging, level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        return
    
    # Mevcut handler'ları temizle
    logger.remove()
    
    # Default format
    if format_string is None:
        format_string = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )
    
    # Console handler
    logger.add(
        sys.stderr,
        format=format_string,
        level=level.upper(),
        colorize=True
    )
    
    # File handler (eğer belirtilmişse)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.add(
            log_file,
            format=format_string,
            level=level.upper(),
            rotation=rotation,
            retention=retention,
            compression="zip",
            enqueue=True  # Thread-safe
        )


def get_logger(name: str):
    """
    Belirli bir modül için logger al.
    
    Args:
        name: Logger adı (genellikle __name__)
        
    Returns:
        Logger instance
    """
    if LOGURU_AVAILABLE:
        return logger.bind(name=name)
    else:
        import logging
        return logging.getLogger(name)








