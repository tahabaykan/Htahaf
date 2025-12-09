"""
Health check ve monitoring sistemi
"""

from typing import Dict, Any, Optional
from pathlib import Path
import shutil
from datetime import datetime

class HealthChecker:
    """Sistem sağlık kontrolü"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Health checker'ı başlat
        
        Args:
            config: Config dictionary
        """
        self.config = config
    
    def check_all(self) -> Dict[str, Any]:
        """
        Tüm sağlık kontrollerini yap
        
        Returns:
            Health check sonuçları
        """
        results = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': 'healthy',
            'checks': {}
        }
        
        # Bağlantı kontrolleri
        results['checks']['connections'] = self.check_connections()
        
        # Dosya sistemi kontrolleri
        results['checks']['filesystem'] = self.check_filesystem()
        
        # Veri kontrolleri
        results['checks']['data'] = self.check_data()
        
        # Performans kontrolleri
        results['checks']['performance'] = self.check_performance()
        
        # Genel durum belirleme
        all_healthy = all(
            check.get('status') == 'healthy' 
            for check in results['checks'].values()
        )
        
        if not all_healthy:
            results['overall_status'] = 'degraded'
        
        return results
    
    def check_connections(self) -> Dict[str, Any]:
        """
        Bağlantı durumlarını kontrol et
        
        Returns:
            Bağlantı durumu
        """
        # Bu kontroller gerçek bağlantıları test etmez, sadece config'i kontrol eder
        # Gerçek bağlantı testleri client'larda yapılmalı
        
        result = {
            'status': 'healthy',
            'details': {}
        }
        
        # Hammer config kontrolü
        hammer_config = self.config.get('hammer', {})
        if not hammer_config.get('host'):
            result['status'] = 'degraded'
            result['details']['hammer'] = 'Host yapılandırılmamış'
        else:
            result['details']['hammer'] = f"Host: {hammer_config.get('host')}:{hammer_config.get('port')}"
        
        # IBKR config kontrolü
        ibkr_config = self.config.get('ibkr', {})
        if not ibkr_config.get('host'):
            result['status'] = 'degraded'
            result['details']['ibkr'] = 'Host yapılandırılmamış'
        else:
            result['details']['ibkr'] = f"Host: {ibkr_config.get('host')}:{ibkr_config.get('port')}"
        
        return result
    
    def check_filesystem(self) -> Dict[str, Any]:
        """
        Dosya sistemi kontrollerini yap
        
        Returns:
            Dosya sistemi durumu
        """
        result = {
            'status': 'healthy',
            'details': {}
        }
        
        paths_config = self.config.get('paths', {})
        
        # Veri dizini kontrolü
        data_dir = Path(paths_config.get('data_dir', '../'))
        if data_dir.exists():
            result['details']['data_dir'] = f"Mevcut: {data_dir}"
        else:
            result['status'] = 'degraded'
            result['details']['data_dir'] = f"Bulunamadı: {data_dir}"
        
        # Yedekleme dizini kontrolü
        backup_dir = Path(paths_config.get('backup_dir', 'backups'))
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            result['details']['backup_dir'] = f"Mevcut: {backup_dir}"
        except Exception as e:
            result['status'] = 'degraded'
            result['details']['backup_dir'] = f"Hata: {e}"
        
        # Log dizini kontrolü
        log_dir = Path(paths_config.get('log_dir', 'logs'))
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            result['details']['log_dir'] = f"Mevcut: {log_dir}"
        except Exception as e:
            result['status'] = 'degraded'
            result['details']['log_dir'] = f"Hata: {e}"
        
        # Disk alanı kontrolü
        try:
            disk_usage = shutil.disk_usage(data_dir if data_dir.exists() else Path('.'))
            free_gb = disk_usage.free / (1024**3)
            result['details']['disk_free'] = f"{free_gb:.2f} GB"
            
            if free_gb < 1.0:  # 1 GB'dan az disk alanı varsa
                result['status'] = 'degraded'
                result['details']['disk_warning'] = 'Disk alanı az!'
        except Exception as e:
            result['details']['disk_check'] = f"Hata: {e}"
        
        return result
    
    def check_data(self) -> Dict[str, Any]:
        """
        Veri durumunu kontrol et
        
        Returns:
            Veri durumu
        """
        result = {
            'status': 'healthy',
            'details': {}
        }
        
        # Ana CSV dosyası kontrolü
        data_dir = Path(self.config.get('paths', {}).get('data_dir', '../'))
        main_csv = data_dir / 'janalldata.csv'
        
        if main_csv.exists():
            try:
                import pandas as pd
                df = pd.read_csv(main_csv, nrows=1)  # Sadece ilk satırı oku
                result['details']['main_csv'] = f"Mevcut, kolonlar: {len(df.columns)}"
            except Exception as e:
                result['status'] = 'degraded'
                result['details']['main_csv'] = f"Okuma hatası: {e}"
        else:
            result['status'] = 'degraded'
            result['details']['main_csv'] = 'Bulunamadı'
        
        return result
    
    def check_performance(self) -> Dict[str, Any]:
        """
        Performans metriklerini kontrol et
        
        Returns:
            Performans durumu
        """
        result = {
            'status': 'healthy',
            'details': {}
        }
        
        # Cache durumu
        cache_config = self.config.get('performance', {}).get('cache_enabled', False)
        result['details']['cache'] = 'Aktif' if cache_config else 'Pasif'
        
        return result

def get_health_status(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sistem sağlık durumunu döndür
    
    Args:
        config: Config dictionary
        
    Returns:
        Health check sonuçları
    """
    checker = HealthChecker(config)
    return checker.check_all()


