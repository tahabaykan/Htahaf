import os
from datetime import datetime

def log_reasoning(message):
    """Reasoning mesajlarını dosyaya kaydet"""
    try:
        # Logs klasörü yoksa oluştur
        os.makedirs('logs', exist_ok=True)
        
        # Bugünün dosya adı
        today = datetime.now().strftime('%Y-%m-%d')
        log_file = f'logs/reasoning_{today}.log'
        
        # Timestamp ile mesajı kaydet
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_entry = f"[{timestamp}] {message}\n"
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
            
    except Exception as e:
        print(f"[REASONING LOG] Kayıt hatası: {e}") 