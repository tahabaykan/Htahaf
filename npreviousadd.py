"""
SSFINEK dosyalarına prev_close kolonu ekleyen script.
Hammer Pro API'den previous close verilerini çeker ve CSV'lere ekler.
"""

import pandas as pd
import os
import glob
import time
import json
import websocket
import threading
from datetime import datetime

class HammerProAPI:
    def __init__(self, password, host='127.0.0.1', port=16400):
        self.password = password
        self.host = host
        self.port = port
        self.ws = None
        self.connected = False
        self.authenticated = False
        self.response_queue = {}
        self.request_id = 0
        
    def connect(self):
        """Hammer Pro API'ye WebSocket bağlantısı kur"""
        try:
            print(f"🔗 Hammer Pro API'ye bağlanılıyor... {self.host}:{self.port}")
            
            # WebSocket bağlantısı
            self.ws = websocket.WebSocketApp(
                f"ws://{self.host}:{self.port}",
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close
            )
            
            # WebSocket'i ayrı thread'de çalıştır
            wst = threading.Thread(target=self.ws.run_forever)
            wst.daemon = True
            wst.start()
            
            # Bağlantının kurulmasını bekle
            timeout = 10
            while not self.connected and timeout > 0:
                time.sleep(0.1)
                timeout -= 0.1
                
            if self.connected:
                print("✅ WebSocket bağlantısı başarılı")
                
                # Authentication için bekle
                auth_timeout = 10
                while not self.authenticated and auth_timeout > 0:
                    time.sleep(0.1)
                    auth_timeout -= 0.1
                    
                if self.authenticated:
                    print("✅ Authentication başarılı")
                    return True
                else:
                    print("❌ Authentication başarısız")
                    return False
            else:
                print("❌ WebSocket bağlantısı başarısız")
                return False
                
        except Exception as e:
            print(f"❌ Hammer Pro API bağlantı hatası: {e}")
            return False
    
    def on_open(self, ws):
        """WebSocket bağlantısı açıldığında"""
        print("🔌 WebSocket bağlantısı açıldı, authenticate ediliyor...")
        self.connected = True
        
        # Connect komutu gönder
        connect_cmd = {
            "cmd": "connect",
            "pwd": self.password,
            "reqID": str(self.get_request_id())
        }
        
        self.send_command(connect_cmd)
    
    def on_message(self, ws, message):
        """WebSocket mesajı alındığında"""
        try:
            print(f"📨 Ham mesaj alındı: {message}")
            data = json.loads(message)
            req_id = data.get('reqID')
            
            print(f"📨 Parsed mesaj: {data}")
            
            # Response queue'ya ekle
            if req_id:
                self.response_queue[req_id] = data
                print(f"📨 Response queue'ya eklendi: {req_id}")
            else:
                print(f"📨 Mesaj alındı: {data.get('cmd', 'unknown')}")
                
            # Authentication başarılı mı kontrol et
            if data.get('cmd') == 'connect' and data.get('success') == 'OK':
                self.authenticated = True
                print("✅ Authentication onaylandı")
                
        except Exception as e:
            print(f"❌ Mesaj parse hatası: {e}")
    
    def on_error(self, ws, error):
        """WebSocket hatası"""
        print(f"❌ WebSocket hatası: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        """WebSocket bağlantısı kapandığında"""
        print("🔌 WebSocket bağlantısı kapandı")
        self.connected = False
        self.authenticated = False
    
    def get_request_id(self):
        """Benzersiz request ID oluştur"""
        self.request_id += 1
        return self.request_id
    
    def send_command(self, command):
        """Komut gönder"""
        if self.ws and self.connected:
            print(f"📤 Komut gönderiliyor: {command}")
            self.ws.send(json.dumps(command))
        else:
            print("❌ WebSocket bağlantısı yok!")
    
    def wait_for_response(self, req_id, timeout=10):
        """Belirli bir request ID için response bekle"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if req_id in self.response_queue:
                response = self.response_queue.pop(req_id)
                return response
            time.sleep(0.1)
        return None
    
    def get_symbol_snapshot(self, symbol):
        """Bir hisse için snapshot data al"""
        try:
            print(f"[Hammer Pro] 📊 {symbol} için snapshot çekiliyor...")
            
            # PR -> - dönüşümü yap
            formatted_symbol = symbol
            if " PR" in symbol:
                formatted_symbol = symbol.replace(" PR", "-")
                print(f"[Hammer Pro] 🔄 {symbol} -> {formatted_symbol} dönüştürüldü")
            
            # getSymbolSnapshot komutu gönder
            req_id = str(self.get_request_id())
            command = {
                "cmd": "getSymbolSnapshot",
                "sym": formatted_symbol,
                "reqID": req_id
            }
            
            self.send_command(command)
            
            # Response bekle
            response = self.wait_for_response(req_id, timeout=10)
            
            if response and response.get('success') == 'OK':
                result = response.get('result', {})
                prev_close = result.get('prevClose', '0')
                
                if prev_close and prev_close != '0':
                    try:
                        prev_close = float(prev_close)
                        print(f"[Hammer Pro] ✅ {symbol}: prev_close = {prev_close}")
                        return prev_close
                    except:
                        print(f"[Hammer Pro] ⚠️ {symbol}: prev_close değeri sayısal değil: {prev_close}")
                        return 0
                else:
                    print(f"[Hammer Pro] ⚠️ {symbol}: prev_close değeri bulunamadı")
                    return 0
            else:
                print(f"[Hammer Pro] ❌ {symbol}: snapshot alınamadı")
                print(f"[Hammer Pro] 📊 Response: {response}")
                return 0
                
        except Exception as e:
            print(f"[Hammer Pro] ❌ {symbol} için snapshot çekilemedi: {e}")
            return 0
    
    def disconnect(self):
        """Bağlantıyı kapat"""
        if self.ws:
            self.ws.close()
        self.connected = False
        self.authenticated = False

def process_ssfinek_files(api):
    """SSFINEK dosyalarını işle ve prev_close kolonu ekle"""
    try:
        # SSFINEK dosyalarını bul - sadece doğru formatı olanları al
        ssfinek_files = glob.glob("*ssfinek*.csv")
        # short_pairs_ ile başlayan dosyaları filtrele
        ssfinek_files = [f for f in ssfinek_files if not f.startswith("short_pairs_")]
        
        if not ssfinek_files:
            print("❌ SSFINEK dosyası bulunamadı!")
            return
            
        print(f"📁 {len(ssfinek_files)} SSFINEK dosyası bulundu")
        
        for file_path in ssfinek_files:
            try:
                print(f"\n📋 İşleniyor: {file_path}")
                
                # CSV'yi oku
                df = pd.read_csv(file_path)
                
                # PREF IBKR kolonunu kontrol et
                if 'PREF IBKR' not in df.columns:
                    print(f"⚠️ {file_path} dosyasında 'PREF IBKR' kolonu bulunamadı!")
                    continue
                
                # Prev_close kolonu ekle
                if 'prev_close' not in df.columns:
                    df['prev_close'] = 0
                
                # Her hisse için prev_close çek
                print(f"🔄 {len(df)} hisse için prev_close çekiliyor...")
                
                for idx, row in df.iterrows():
                    symbol = row['PREF IBKR']
                    if pd.isna(symbol) or symbol == '':
                        continue
                    
                    # Hammer Pro API'den prev_close çek
                    prev_close = api.get_symbol_snapshot(symbol)
                    df.at[idx, 'prev_close'] = prev_close
                    
                    # Her 10 hissede bir progress göster
                    if (idx + 1) % 10 == 0:
                        print(f"📊 Progress: {idx + 1}/{len(df)} hisse işlendi")
                    
                    # Rate limiting (Hammer Pro API için)
                    time.sleep(1.0)
                
                # Dosya adını janek_ ile başlayacak şekilde değiştir
                base_name = os.path.basename(file_path)
                dir_name = os.path.dirname(file_path)
                
                # Dosya adını janek_ ile başlat
                if not base_name.startswith('janek_'):
                    new_name = f"janek_{base_name}"
                else:
                    new_name = base_name
                
                new_file_path = os.path.join(dir_name, new_name)
                
                # CSV'yi kaydet
                df.to_csv(new_file_path, index=False)
                print(f"✅ Kaydedildi: {new_file_path}")
                
                # Orijinal dosyayı da güncelle
                df.to_csv(file_path, index=False)
                print(f"✅ Orijinal dosya güncellendi: {file_path}")
                
            except Exception as e:
                print(f"❌ {file_path} işlenirken hata: {e}")
                continue
                
    except Exception as e:
        print(f"❌ SSFINEK dosyaları işlenirken hata: {e}")

def process_etfs(api):
    """ETF'ler için prev_close değerlerini çek ve janeketfs.csv dosyasına kaydet"""
    try:
        print("\n📊 ETF'ler için prev_close çekiliyor...")
        
        # ETF listesi
        etf_symbols = ["SPY", "IWM", "TLT", "KRE", "IEI", "IEF", "PFF", "PGF"]
        
        # DataFrame oluştur
        etf_data = []
        
        for symbol in etf_symbols:
            print(f"🔄 {symbol} için prev_close çekiliyor...")
            
            # Hammer Pro API'den prev_close çek
            prev_close = api.get_symbol_snapshot(symbol)
            
            etf_data.append({
                'Symbol': symbol,
                'prev_close': prev_close
            })
            
            # Rate limiting
            time.sleep(1.0)
        
        # DataFrame oluştur
        df_etfs = pd.DataFrame(etf_data)
        
        # janeketfs.csv dosyasına kaydet
        output_file = "janeketfs.csv"
        df_etfs.to_csv(output_file, index=False)
        print(f"✅ ETF verileri kaydedildi: {output_file}")
        
        # Sonuçları göster
        print("\n📊 ETF Prev Close Değerleri:")
        for _, row in df_etfs.iterrows():
            print(f"  {row['Symbol']}: {row['prev_close']}")
        
    except Exception as e:
        print(f"❌ ETF'ler işlenirken hata: {e}")

def main():
    """Ana fonksiyon"""
    print("🚀 npreviousadd.py başlatılıyor...")
    print(f"⏰ Başlangıç zamanı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Hammer Pro API bağlantısı
    password = "Nl201090."  # Hammer Pro şifresi
    
    api = HammerProAPI(password)
    
    try:
        # Hammer Pro API'ye bağlan
        if api.connect():
            # Test için bir hisse deneyelim
            print("🧪 Test: AAPL için prev_close çekiliyor...")
            test_result = api.get_symbol_snapshot("AAPL")
            print(f"🧪 Test sonucu: {test_result}")
            
            if test_result > 0:
                print("✅ Test başarılı, dosyalar işleniyor...")
                
                # Önce ETF'leri işle
                process_etfs(api)
                
                # Sonra SSFINEK dosyalarını işle
                process_ssfinek_files(api)
            else:
                print("❌ Test başarısız, Hammer Pro API bağlantısında sorun var!")
                print("⚠️ Hammer Pro'nun çalıştığından ve API'nin aktif olduğundan emin olun!")
                return
        else:
            print("❌ Hammer Pro API bağlantısı başarısız!")
            print("⚠️ Hammer Pro'nun çalıştığından ve API port'unun doğru olduğundan emin olun!")
            return
        
    except Exception as e:
        print(f"❌ Hammer Pro API bağlantı hatası: {e}")
        print("⚠️ Hammer Pro'nun çalıştığından ve API'nin aktif olduğundan emin olun!")
        return
    finally:
        try:
            api.disconnect()
            print("🔌 Hammer Pro API bağlantısı kapatıldı")
        except:
            pass
    
    print(f"✅ Tamamlandı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
