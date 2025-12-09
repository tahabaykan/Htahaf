"""
Config modülü - Yapılandırma yönetimi
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

class ConfigManager:
    """Yapılandırma yöneticisi - Config dosyalarını ve environment variable'ları yönetir"""
    
    def __init__(self, config_file: str = None):
        """
        Config manager'ı başlat
        
        Args:
            config_file: Config dosyası yolu (None ise varsayılan kullanılır)
        """
        # Config dosyası yolunu belirle
        if config_file is None:
            # Bu dosyanın bulunduğu dizini al
            current_dir = Path(__file__).parent
            config_file = current_dir / "config.json"
        
        self.config_file = Path(config_file)
        self.config: Dict[str, Any] = {}
        self._load_config()
        self._load_env_variables()
    
    def _load_config(self):
        """Config dosyasını yükle"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                print(f"[CONFIG] ✅ Config dosyası yüklendi: {self.config_file}")
            else:
                print(f"[CONFIG] ⚠️ Config dosyası bulunamadı: {self.config_file}")
                print(f"[CONFIG] 💡 Varsayılan config kullanılıyor")
                self.config = self._get_default_config()
        except Exception as e:
            print(f"[CONFIG] ❌ Config yükleme hatası: {e}")
            self.config = self._get_default_config()
    
    def _load_env_variables(self):
        """Environment variable'ları yükle ve config'e ekle"""
        try:
            # .env dosyasını yükle (varsa)
            env_file = Path(__file__).parent.parent / ".env"
            if env_file.exists():
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            os.environ[key.strip()] = value.strip()
            
            # Hammer password'ü environment'tan al
            if 'ENV_HAMMER_PASSWORD' in str(self.config.get('hammer', {}).get('password', '')):
                hammer_password = os.environ.get('HAMMER_PASSWORD', '')
                if hammer_password:
                    self.config['hammer']['password'] = hammer_password
                    print("[CONFIG] ✅ Hammer password environment'tan yüklendi")
                else:
                    print("[CONFIG] ⚠️ HAMMER_PASSWORD environment variable bulunamadı")
            
            # IBKR bilgilerini environment'tan al (opsiyonel)
            if 'IBKR_HOST' in os.environ:
                self.config['ibkr']['host'] = os.environ['IBKR_HOST']
            if 'IBKR_PORT' in os.environ:
                self.config['ibkr']['port'] = int(os.environ['IBKR_PORT'])
                
        except Exception as e:
            print(f"[CONFIG] ⚠️ Environment variable yükleme hatası: {e}")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Varsayılan config döndür"""
        return {
            "hammer": {
                "host": "127.0.0.1",
                "port": 16400,
                "password": "",
                "account_key": "ALARIC:TOPI002240A7"
            },
            "ibkr": {
                "host": "127.0.0.1",
                "port": 4001,
                "client_id": 1,
                "native_client_id": 2
            },
            "paths": {
                "data_dir": "../",
                "backup_dir": "backups",
                "log_dir": "logs"
            },
            "logging": {
                "level": "INFO",
                "max_bytes": 10485760,
                "backup_count": 5,
                "console_output": True
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Config değerini al (nested key'ler için dot notation kullanılabilir)
        
        Args:
            key: Config key'i (örn: "hammer.host" veya "hammer")
            default: Varsa varsayılan değer
            
        Returns:
            Config değeri veya default
        """
        keys = key.split('.')
        value = self.config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any):
        """
        Config değerini ayarla
        
        Args:
            key: Config key'i (dot notation desteklenir)
            value: Değer
        """
        keys = key.split('.')
        config = self.config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
    
    def save(self):
        """Config'i dosyaya kaydet"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            print(f"[CONFIG] ✅ Config kaydedildi: {self.config_file}")
        except Exception as e:
            print(f"[CONFIG] ❌ Config kaydetme hatası: {e}")

# Global config instance
_config_instance: Optional[ConfigManager] = None

def get_config() -> ConfigManager:
    """Global config instance'ı döndür"""
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigManager()
    return _config_instance


