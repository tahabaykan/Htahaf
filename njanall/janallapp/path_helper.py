"""
Path Helper Modülü - njanall için dosya yolu yönetimi

Bu modül njanall uygulamasının kendi dizininde dosya okuma/yazma
işlemlerini yapmasını sağlar.
"""

import os

def get_njanall_base_dir():
    """
    njanall dizininin tam yolunu döndürür.
    Bu fonksiyon janallapp modülünün bulunduğu dizinden bir üst dizine çıkarak
    njanall dizinini bulur.
    """
    # Bu dosyanın bulunduğu dizin: njanall/janallapp/
    current_file_dir = os.path.dirname(os.path.abspath(__file__))
    # Bir üst dizin: njanall/
    base_dir = os.path.dirname(current_file_dir)
    return base_dir

# Global base_dir değişkeni
NJANALL_BASE_DIR = get_njanall_base_dir()

def get_csv_path(filename):
    """
    CSV dosyası için tam yolu döndürür.
    
    Args:
        filename: CSV dosya adı (örn: 'janalldata.csv')
    
    Returns:
        njanall dizinindeki CSV dosyasının tam yolu
    """
    return os.path.join(NJANALL_BASE_DIR, filename)

def get_json_path(filename):
    """
    JSON dosyası için tam yolu döndürür.
    
    Args:
        filename: JSON dosya adı (örn: 'bdata_fills.json')
    
    Returns:
        njanall dizinindeki JSON dosyasının tam yolu
    """
    return os.path.join(NJANALL_BASE_DIR, filename)

def ensure_njanall_dir():
    """
    njanall dizininin var olduğundan emin olur.
    """
    if not os.path.exists(NJANALL_BASE_DIR):
        os.makedirs(NJANALL_BASE_DIR, exist_ok=True)
    return NJANALL_BASE_DIR












