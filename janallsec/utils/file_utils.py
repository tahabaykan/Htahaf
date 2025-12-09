"""
Dosya işlemleri - Atomic yazma, yedekleme vb.
"""

import os
import shutil
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional

def save_csv_atomic(file_path: str, data: pd.DataFrame, backup: bool = True) -> bool:
    """
    CSV dosyasını atomic olarak kaydet (veri kaybını önler)
    
    Args:
        file_path: Kaydedilecek dosya yolu
        data: DataFrame
        backup: Yedekleme yapılsın mı
        
    Returns:
        True if successful
    """
    file_path = Path(file_path)
    
    # Yedekleme yap (varsa eski dosya)
    if backup and file_path.exists():
        try:
            auto_backup_csv(str(file_path))
        except Exception as e:
            print(f"[FILE_UTILS] ⚠️ Yedekleme hatası: {e}")
    
    # Geçici dosya yolu
    temp_path = file_path.with_suffix(file_path.suffix + '.tmp')
    
    try:
        # Geçici dosyaya yaz
        data.to_csv(temp_path, index=False, encoding='utf-8')
        
        # Atomic replace (Windows'ta da çalışır)
        if os.name == 'nt':  # Windows
            # Windows'ta replace işlemi için önce eski dosyayı sil
            if file_path.exists():
                os.remove(file_path)
            os.rename(temp_path, file_path)
        else:  # Unix/Linux
            os.replace(temp_path, file_path)
        
        print(f"[FILE_UTILS] ✅ CSV atomic kaydedildi: {file_path}")
        return True
        
    except Exception as e:
        # Hata durumunda geçici dosyayı temizle
        if temp_path.exists():
            try:
                temp_path.unlink()
            except:
                pass
        
        print(f"[FILE_UTILS] ❌ CSV kaydetme hatası: {e}")
        raise

def auto_backup_csv(file_path: str, backup_dir: str = "backups", 
                   max_backups: int = 30) -> str:
    """
    CSV dosyasını otomatik yedekle
    
    Args:
        file_path: Yedeklenecek dosya yolu
        backup_dir: Yedekleme dizini
        max_backups: Maksimum yedek sayısı
        
    Returns:
        Yedek dosya yolu
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"Dosya bulunamadı: {file_path}")
    
    # Yedekleme dizinini oluştur
    backup_path = Path(backup_dir)
    backup_path.mkdir(parents=True, exist_ok=True)
    
    # Yedek dosya adı: orijinal_ad_timestamp.csv
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_path / f"{file_path.stem}_backup_{timestamp}{file_path.suffix}"
    
    # Dosyayı kopyala
    shutil.copy2(file_path, backup_file)
    
    print(f"[FILE_UTILS] ✅ Yedekleme yapıldı: {backup_file}")
    
    # Eski yedekleri temizle
    cleanup_old_backups(backup_path, file_path.stem, max_backups)
    
    return str(backup_file)

def cleanup_old_backups(backup_dir: Path, file_prefix: str, max_backups: int):
    """
    Eski yedek dosyalarını temizle
    
    Args:
        backup_dir: Yedekleme dizini
        file_prefix: Dosya öneki
        max_backups: Maksimum yedek sayısı
    """
    try:
        # İlgili yedek dosyalarını bul
        backup_files = sorted(
            backup_dir.glob(f"{file_prefix}_backup_*.csv"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        
        # Eski yedekleri sil
        if len(backup_files) > max_backups:
            for old_backup in backup_files[max_backups:]:
                try:
                    old_backup.unlink()
                    print(f"[FILE_UTILS] 🗑️ Eski yedek silindi: {old_backup.name}")
                except Exception as e:
                    print(f"[FILE_UTILS] ⚠️ Yedek silme hatası: {e}")
                    
    except Exception as e:
        print(f"[FILE_UTILS] ⚠️ Yedek temizleme hatası: {e}")

def ensure_data_dir(data_dir: str) -> Path:
    """
    Veri dizinini oluştur (yoksa)
    
    Args:
        data_dir: Veri dizini yolu
        
    Returns:
        Path objesi
    """
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    return data_path


