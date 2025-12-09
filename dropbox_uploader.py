import os
import time
import schedule
import dropbox
from datetime import datetime
from dotenv import load_dotenv
import logging

# Logging ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('dropbox_uploader.log'),
        logging.StreamHandler()
    ]
)

# .env dosyasını yükle
load_dotenv()

class DropboxUploader:
    def __init__(self):
        """Dropbox uploader sınıfını başlat"""
        self.dbx = None
        self.local_file_path = os.getenv('LOCAL_FILE_PATH', r'C:\Users\User\Documents\data.csv')
        self.dropbox_folder = os.getenv('DROPBOX_FOLDER', '/StockTracker')
        self.dropbox_filename = os.getenv('DROPBOX_FILENAME', 'data.csv')
        
        # Dropbox token'ını kontrol et
        token = os.getenv('DROPBOX_ACCESS_TOKEN')
        if not token:
            logging.error("DROPBOX_ACCESS_TOKEN bulunamadı! Lütfen .env dosyasını kontrol edin.")
            return
            
        try:
            self.dbx = dropbox.Dropbox(token)
            # Token'ı test et
            self.dbx.users_get_current_account()
            logging.info("Dropbox bağlantısı başarılı!")
        except Exception as e:
            logging.error(f"Dropbox bağlantı hatası: {e}")
            self.dbx = None

    def upload_file(self):
        """CSV dosyasını Dropbox'a yükle"""
        if not self.dbx:
            logging.error("Dropbox bağlantısı yok!")
            return False
            
        try:
            # Dosyanın var olup olmadığını kontrol et
            if not os.path.exists(self.local_file_path):
                logging.warning(f"Local dosya bulunamadı: {self.local_file_path}")
                return False
            
            # Dosyayı oku
            with open(self.local_file_path, 'rb') as f:
                file_data = f.read()
            
            # Dropbox'a yükle
            dropbox_path = f"{self.dropbox_folder}/{self.dropbox_filename}"
            
            # Mevcut dosyayı güncelle veya yeni dosya oluştur
            self.dbx.files_upload(
                file_data, 
                dropbox_path, 
                mode=dropbox.files.WriteMode.overwrite,
                autorename=False
            )
            
            logging.info(f"Dosya başarıyla yüklendi: {self.local_file_path} -> {dropbox_path}")
            return True
            
        except Exception as e:
            logging.error(f"Dosya yükleme hatası: {e}")
            return False

    def start_scheduler(self):
        """Zamanlayıcıyı başlat"""
        if not self.dbx:
            logging.error("Dropbox bağlantısı olmadığı için zamanlayıcı başlatılamıyor!")
            return
            
        # Her 3 dakikada bir çalışacak şekilde ayarla
        schedule.every(3).minutes.do(self.upload_file)
        
        logging.info("Dropbox otomatik yükleyici başlatıldı!")
        logging.info(f"Local dosya: {self.local_file_path}")
        logging.info(f"Dropbox hedef: {self.dropbox_folder}/{self.dropbox_filename}")
        logging.info("Her 3 dakikada bir dosya kontrol edilecek...")
        
        # İlk yüklemeyi hemen yap
        self.upload_file()
        
        # Sonsuz döngü
        while True:
            try:
                schedule.run_pending()
                time.sleep(30)  # 30 saniye bekle
            except KeyboardInterrupt:
                logging.info("Program kullanıcı tarafından durduruldu.")
                break
            except Exception as e:
                logging.error(f"Zamanlayıcı hatası: {e}")
                time.sleep(60)  # Hata durumunda 1 dakika bekle

def main():
    """Ana fonksiyon"""
    print("Dropbox Otomatik Dosya Yükleyici")
    print("=" * 40)
    
    uploader = DropboxUploader()
    
    if uploader.dbx:
        uploader.start_scheduler()
    else:
        print("Dropbox bağlantısı kurulamadı. Lütfen .env dosyasını kontrol edin.")
        print("\nGerekli ayarlar:")
        print("1. .env dosyasında DROPBOX_ACCESS_TOKEN")
        print("2. LOCAL_FILE_PATH (varsayılan: C:\\Users\\User\\Documents\\data.csv)")
        print("3. DROPBOX_FOLDER (varsayılan: /StockTracker)")
        print("4. DROPBOX_FILENAME (varsayılan: data.csv)")

if __name__ == "__main__":
    main()

