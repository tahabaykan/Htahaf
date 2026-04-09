"""app/core/logger.py

Logging configuration using loguru (with fallback to standard logging).

Persistent logging:
- Console (stderr) for live terminal output
- Daily rotating file in data/logs/app/ with 7-day retention
- All fills, orders, engine decisions survive restarts
"""

import sys
import os
from typing import Optional

try:
    from loguru import logger
    LOGURU_AVAILABLE = True
except ImportError:
    LOGURU_AVAILABLE = False
    import logging
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger("quant_engine")

# Configure loguru if available
if LOGURU_AVAILABLE:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.remove()  # Remove default handler
    
    # ═══════════════════════════════════════════════════════════════════
    # FIX: Ensure sys.stderr supports UTF-8 on Windows
    # Windows CP1254 encoding crashes on emoji characters (🎯, 🚀, ✅)
    # used throughout logger messages. Reconfigure BEFORE adding handler.
    # ═══════════════════════════════════════════════════════════════════
    if sys.platform == 'win32':
        try:
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, Exception):
            pass  # Best effort — runner scripts handle this too
    
    # 1) Console output (stderr) — colorized, live terminal
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>",
        level=log_level,
        colorize=True
    )

    
    # 2) Persistent daily log file — survives restarts, 7-day retention
    _log_dir = os.path.join("data", "logs", "app")
    os.makedirs(_log_dir, exist_ok=True)
    _daily_log_path = os.path.join(_log_dir, "quant_engine_{time:YYYY-MM-DD}.log")
    
    logger.add(
        _daily_log_path,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        level=log_level,
        rotation="00:00",       # New file at midnight
        retention="7 days",     # Keep 7 days of logs
        compression="zip",      # Compress old logs
        encoding="utf-8",
        enqueue=True,           # Thread-safe async write
    )
    
    # 3) Optional: Extra file logging via env var (legacy support)
    log_file = os.getenv("LOG_FILE")
    if log_file:
        logger.add(
            log_file,
            rotation="10 MB",
            retention="7 days",
            compression="zip",
            level=log_level
        )




