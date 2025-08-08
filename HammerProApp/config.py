import json
import os
from typing import Dict, Any

class Config:
    """Configuration manager for Hammer Pro settings"""
    
    def __init__(self, config_file='config.json'):
        self.config_file = config_file
        self.default_config = {
            'hammer_pro': {
                'host': '127.0.0.1',
                'port': 8080,
                'password': '',
                'streamer_id': 'AMTD'
            },
            'gui': {
                'window_width': 1400,
                'window_height': 800,
                'items_per_page': 50
            },
            'data': {
                'update_interval': 2.0,
                'live_data_enabled': False
            }
        }
        self.config = self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # Merge with default config to ensure all keys exist
                    return self._merge_configs(self.default_config, config)
            except Exception as e:
                print(f"Error loading config: {e}")
                return self.default_config.copy()
        else:
            # Create default config file
            self.save_config(self.default_config)
            return self.default_config.copy()
    
    def save_config(self, config: Dict[str, Any] = None):
        """Save configuration to file"""
        if config is None:
            config = self.config
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def _merge_configs(self, default: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
        """Merge user config with default config"""
        result = default.copy()
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        return result
    
    def get(self, key: str, default=None):
        """Get configuration value"""
        keys = key.split('.')
        value = self.config
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any):
        """Set configuration value"""
        keys = key.split('.')
        config = self.config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
        self.save_config()
    
    def get_hammer_pro_config(self) -> Dict[str, Any]:
        """Get Hammer Pro connection configuration"""
        return self.config.get('hammer_pro', {})
    
    def set_hammer_pro_config(self, host: str, port: int, password: str, streamer_id: str = 'AMTD'):
        """Set Hammer Pro connection configuration"""
        self.config['hammer_pro'] = {
            'host': host,
            'port': port,
            'password': password,
            'streamer_id': streamer_id
        }
        self.save_config()
    
    def get_gui_config(self) -> Dict[str, Any]:
        """Get GUI configuration"""
        return self.config.get('gui', {})
    
    def get_data_config(self) -> Dict[str, Any]:
        """Get data configuration"""
        return self.config.get('data', {}) 