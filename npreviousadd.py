"""
SSFINEK dosyalarına prev_close kolonu ekleyen script.
Hammer Pro API'den previous close verilerini çeker ve CSV'lere ekler.
NASDAQ exchange'de olan ve TIME TO DIV=90 olan hisselerde previous close'u DIV AMOUNT kadar düşürür.
"""

import pandas as pd
import os
import glob
import time
import json
import websocket
import threading
from datetime import datetime

# NASDAQ exchange'de olan hisseler listesi
NASDAQ_STOCKS = {
    'BCVpA', 'ECFpA', 'GGNpB', 'ACGLN', 'ACGLO', 'AGNCL', 'AGNCM', 'AGNCN', 
    'AGNCO', 'AGNCP', 'ATLCZ', 'BANFP', 'BHFAL', 'BHFAM', 'BHFAN', 'BHFAO', 
    'BHFAP', 'BWBBP', 'CGABL', 'CHSCL', 'CHSCM', 'CHSCN', 'CHSCO', 'CNOBP', 
    'CSWCZ', 'DCOMG', 'DCOMP', 'EFSCP', 'FCNCO', 'FCNCP', 'FGBIP', 'FITBI', 
    'FITBO', 'FITBP', 'FRMEP', 'FULTP', 'GECCH', 'GECCI', 'GECCO', 'GOODN', 
    'GOODO', 'HBANL', 'HBANM', 'HBANP', 'HNNAZ', 'HOVNP', 'HROWL', 'HROWM', 
    'HWCPZ', 'INBKZ', 'JSM', 'LANDO', 'LANDP', 'LBRDP', 'MBINM', 'MBINN', 
    'METCZ', 'MFICL', 'MNSBP', 'MSBIP', 'NEWTG', 'NEWTH', 'NEWTI', 'NHPAP', 
    'NHPBP', 'NMFCZ', 'NTRSO', 'NYMTG', 'NYMTI', 'NYMTL', 'NYMTM', 'NYMTN', 
    'NYMTZ', 'OCCIM', 'OCCIN', 'OCCIO', 'OFSSH', 'ONBPO', 'ONBPP', 'OXLCI', 
    'OXLCL', 'OXLCN', 'OXLCO', 'OXLCP', 'OXLCZ', 'OXSQZ', 'OZKAP', 'PNFPP', 
    'REGCO', 'REGCP', 'RWAYL', 'RWAYZ', 'SIGIP', 'SSSSL', 'SWKHL', 'TCBIO', 
    'TPGXL', 'TRINI', 'UMBFO', 'VLYPN', 'VLYPO', 'VLYPP', 'WAFDP', 'WHFCL', 
    'WSBCP', 'WTFCN', 'XOMAO', 'XOMAP', 'ZIONP'
}

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
            data = json.loads(message)
            req_id = data.get('reqID')
            cmd = data.get('cmd', '')
            
            # Sadece önemli mesajları logla
            if cmd == 'getSymbolSnapshot':
                print(f"📊 SNAPSHOT: {data}")
            elif cmd == 'connect' and data.get('success') == 'OK':
                print(f"✅ AUTH: {data}")
                self.authenticated = True
            elif cmd in ['enumPorts', 'enumPortSymbols', 'addToPort']:
                print(f"📁 PORTFOLIO: {cmd} - {data.get('success', 'unknown')}")
            elif cmd not in ['L1Update', 'dataStreamerStatusUpdate', 'dataStreamerStateUpdate']:
                print(f"🔧 API: {cmd} - {data}")
            
            # Response queue'ya ekle
            if req_id:
                self.response_queue[req_id] = data
                
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
                
                print(f"[Hammer Pro] 📊 {symbol} response result: {result}")
                
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
    
    def start_data_streamer(self):
        """Data streamer'ı başlat (GSMQUOTES veya ALARIC)"""
        try:
            # Önce mevcut streamer'ları listele
            req_id = str(self.get_request_id())
            enum_cmd = {
                "cmd": "enumDataStreamers",
                "reqID": req_id
            }
            
            print("[Hammer Pro] 📋 Mevcut data streamer'lar listeleniyor...")
            self.send_command(enum_cmd)
            
            # Response bekle
            response = self.wait_for_response(req_id, timeout=10)
            
            if response and response.get('success') == 'OK':
                streamers = response.get('result', [])
                print(f"[Hammer Pro] 📊 Bulunan streamer'lar: {len(streamers)}")
                
                # ALARICQ streamer'ı bul ve başlat (screenshot'tan görünen)
                preferred_streamers = ['ALARICQ', 'GSMQUOTES', 'ALARIC', 'AMTD']
                
                for preferred in preferred_streamers:
                    for streamer in streamers:
                        if isinstance(streamer, dict) and streamer.get('streamerID') == preferred:
                            print(f"[Hammer Pro] 🚀 {preferred} streamer başlatılıyor...")
                            
                            start_req_id = str(self.get_request_id())
                            start_cmd = {
                                "cmd": "startDataStreamer",
                                "streamerID": preferred,
                                "reqID": start_req_id
                            }
                            
                            self.send_command(start_cmd)
                            start_response = self.wait_for_response(start_req_id, timeout=15)
                            
                            if start_response and start_response.get('success') == 'OK':
                                print(f"[Hammer Pro] ✅ {preferred} streamer başlatıldı!")
                                time.sleep(2)  # Streamer'ın başlaması için bekle
                                return True
                            else:
                                print(f"[Hammer Pro] ⚠️ {preferred} streamer başlatılamadı: {start_response}")
                
                print("[Hammer Pro] ⚠️ Tercih edilen streamer bulunamadı")
                return False
            else:
                print(f"[Hammer Pro] ❌ Streamer listesi alınamadı: {response}")
                return False
                
        except Exception as e:
            print(f"[Hammer Pro] ❌ Data streamer başlatma hatası: {e}")
            return False
    
    def subscribe_symbol(self, symbol):
        """Bir symbole L1 data için subscribe ol"""
        try:
            req_id = str(self.get_request_id())
            subscribe_cmd = {
                "cmd": "subscribe",
                "sub": "L1",
                "streamerID": "ALARICQ",
                "sym": symbol,
                "reqID": req_id
            }
            
            print(f"[Hammer Pro] 📡 {symbol} subscribe ediliyor...")
            self.send_command(subscribe_cmd)
            
            # Response bekle
            response = self.wait_for_response(req_id, timeout=10)
            
            if response and response.get('success') == 'OK':
                result = response.get('result', {})
                subbed = result.get('subbed', [])
                print(f"[Hammer Pro] ✅ Subscribe başarılı: {subbed}")
                
                # L1 data'nın gelmesi için biraz bekle
                time.sleep(3)
                return True
            else:
                print(f"[Hammer Pro] ❌ Subscribe başarısız: {response}")
                return False
                
        except Exception as e:
            print(f"[Hammer Pro] ❌ Subscribe hatası: {e}")
            return False
    
    def add_symbol_to_portfolio(self, symbol):
        """Symbol'u geçici portfolio'ya ekle ki previous close data'sı database'e girsin"""
        try:
            # Önce mevcut portfolio'ları listele
            req_id = str(self.get_request_id())
            enum_cmd = {
                "cmd": "enumPorts",
                "reqID": req_id
            }
            
            print(f"[Hammer Pro] 📁 Portfolio'lar listeleniyor...")
            self.send_command(enum_cmd)
            
            response = self.wait_for_response(req_id, timeout=10)
            
            if response and response.get('success') == 'OK':
                result = response.get('result', {})
                ports = result.get('ports', [])
                
                # İlk portfolio'yu kullan veya yeni oluştur
                if ports:
                    port_id = ports[0].get('portID')
                    print(f"[Hammer Pro] 📊 Mevcut portfolio kullanılıyor: {port_id}")
                else:
                    # Yeni portfolio oluştur
                    port_id = "API_TEMP_PORT"
                    print(f"[Hammer Pro] 🆕 Yeni portfolio oluşturuluyor: {port_id}")
                
                # Symbol'u portfolio'ya ekle
                add_req_id = str(self.get_request_id())
                add_cmd = {
                    "cmd": "addToPort",
                    "portID": port_id,
                    "new": len(ports) == 0,  # Eğer portfolio yoksa yeni oluştur
                    "name": "API Temp Portfolio",
                    "sym": symbol,
                    "reqID": add_req_id
                }
                
                print(f"[Hammer Pro] ➕ {symbol} portfolio'ya ekleniyor...")
                self.send_command(add_cmd)
                
                add_response = self.wait_for_response(add_req_id, timeout=10)
                
                if add_response and add_response.get('success') == 'OK':
                    print(f"[Hammer Pro] ✅ {symbol} portfolio'ya eklendi!")
                    time.sleep(2)  # Database'in güncellenmesi için bekle
                    return True
                else:
                    print(f"[Hammer Pro] ❌ Portfolio'ya ekleme başarısız: {add_response}")
                    return False
                    
            else:
                print(f"[Hammer Pro] ❌ Portfolio listesi alınamadı: {response}")
                return False
                
        except Exception as e:
            print(f"[Hammer Pro] ❌ Portfolio ekleme hatası: {e}")
            return False
    
    def disconnect(self):
        """Bağlantıyı kapat"""
        if self.ws:
            self.ws.close()
        self.connected = False
        self.authenticated = False

def adjust_previous_close_for_nasdaq_dividends(df, main_data_df):
    """SADECE NASDAQ_STOCKS listesinde olan ve TIME TO DIV=89 olan hisselerde previous close'u DIV AMOUNT kadar düşür"""
    try:
        print("\n🔍 SADECE NASDAQ_STOCKS listesinde olan ve TIME TO DIV=89 olan hisseler kontrol ediliyor...")
        
        # Ana veri dosyasından TIME TO DIV ve DIV AMOUNT bilgilerini al
        if main_data_df is None or main_data_df.empty:
            print("⚠️ Ana veri dosyası bulunamadı, düzenleme yapılamıyor")
            return df
        
        # Gerekli kolonları kontrol et
        required_columns = ['PREF IBKR', 'TIME TO DIV', 'DIV AMOUNT']
        missing_columns = [col for col in required_columns if col not in main_data_df.columns]
        
        if missing_columns:
            print(f"⚠️ Ana veri dosyasında gerekli kolonlar bulunamadı: {missing_columns}")
            return df
        
        adjusted_count = 0
        
        for idx, row in df.iterrows():
            symbol = row['PREF IBKR']
            
            if pd.isna(symbol) or symbol == '':
                continue
            
            # Ana veri dosyasında bu hisseyi bul
            main_data_row = main_data_df[main_data_df['PREF IBKR'] == symbol]
            
            if main_data_row.empty:
                continue
            
            # TIME TO DIV ve DIV AMOUNT değerlerini al
            time_to_div = main_data_row.iloc[0]['TIME TO DIV']
            div_amount = main_data_row.iloc[0]['DIV AMOUNT']
            
            # 1. Koşul: NASDAQ exchange'de mi?
            is_nasdaq = symbol in NASDAQ_STOCKS
            
            # 2. Koşul: SADECE TIME TO DIV = 89 mi? (89 gün var = temettü ödemesine yakın)
            # TIME TO DIV = 89 ise temettü ödemesine yakın demektir, bu durumda previous close'u DIV AMOUNT kadar düşürmemiz gerekiyor
            is_time_to_div_89 = pd.notna(time_to_div) and str(time_to_div).strip() in ['89', '89.0']
            
            if is_nasdaq and is_time_to_div_89:
                try:
                    # DIV AMOUNT'u sayıya çevir
                    if pd.notna(div_amount) and str(div_amount).strip() != '':
                        div_amount_float = float(div_amount)
                        
                        # Previous close'u düşür
                        if 'prev_close' in df.columns and pd.notna(row['prev_close']):
                            original_prev_close = row['prev_close']
                            adjusted_prev_close = original_prev_close - div_amount_float
                            
                            # DataFrame'i güncelle
                            df.at[idx, 'prev_close'] = adjusted_prev_close
                            
                            print(f"✅ {symbol}: {original_prev_close:.2f} - {div_amount_float:.2f} = {adjusted_prev_close:.2f}")
                            adjusted_count += 1
                        else:
                            print(f"⚠️ {symbol}: prev_close kolonu bulunamadı veya boş")
                    else:
                        print(f"⚠️ {symbol}: DIV AMOUNT değeri geçersiz: {div_amount}")
                        
                except Exception as e:
                    print(f"❌ {symbol}: Düzenleme hatası: {e}")
        
        print(f"✅ Toplam {adjusted_count} hisse düzenlendi")
        return df
        
    except Exception as e:
        print(f"❌ NASDAQ dividend düzenleme hatası: {e}")
        return df

def load_main_data():
    """Ana veri dosyasını yükle (TIME TO DIV ve DIV AMOUNT bilgileri için)"""
    try:
        print("⚠️  SADECE ANA DİZİNDEKİ (StockTracker) DOSYALAR KULLANILACAK!")
        
        # Önce janalldata.csv'yi ana dizinde ara
        if os.path.exists('janalldata.csv'):
            print("📊 Ana veri dosyası yükleniyor: janalldata.csv")
            df = pd.read_csv('janalldata.csv')
            return df
        
        # Sonra data.csv'yi dene
        elif os.path.exists('data.csv'):
            print("📊 Ana veri dosyası yükleniyor: data.csv")
            df = pd.read_csv('data.csv')
            return df
        
        # Son olarak .csv uzantılı dosyaları ara (sadece ana dizindeki)
        else:
            csv_files = []
            current_dir = os.getcwd()
            for f in os.listdir(current_dir):
                if f.endswith('.csv'):
                    # Dosya ana dizinde mi kontrol et
                    file_path = os.path.join(current_dir, f)
                    if os.path.isfile(file_path) and not os.path.dirname(file_path).endswith(('janall', 'janallw', 'janall_backup')):
                        csv_files.append(f)
            
            for csv_file in csv_files:
                if 'data' in csv_file.lower() and 'ssfinek' not in csv_file.lower():
                    print(f"📊 Ana veri dosyası yükleniyor: {csv_file}")
                    df = pd.read_csv(csv_file)
                    return df
        
        print("⚠️ Ana veri dosyası bulunamadı!")
        return None
        
    except Exception as e:
        print(f"❌ Ana veri dosyası yükleme hatası: {e}")
        return None

def get_symbols_from_portfolio(api, portfolio_name="janalldata"):
    """Portfolio'dan symbol'ları çek"""
    try:
        # Portfolio'ları listele
        req_id = str(api.get_request_id())
        enum_cmd = {
            "cmd": "enumPorts",
            "reqID": req_id
        }
        
        print(f"[Portfolio] 📁 {portfolio_name} portfolio'su aranıyor...")
        api.send_command(enum_cmd)
        
        response = api.wait_for_response(req_id, timeout=10)
        
        if response and response.get('success') == 'OK':
            result = response.get('result', {})
            ports = result.get('ports', [])
            
            # janalldata portfolio'sunu bul
            target_port_id = None
            for port in ports:
                if port.get('name') == portfolio_name:
                    target_port_id = port.get('portID')
                    break
            
            if target_port_id:
                print(f"[Portfolio] ✅ {portfolio_name} bulundu: {target_port_id}")
                
                # Portfolio symbol'larını çek
                symbols_req_id = str(api.get_request_id())
                symbols_cmd = {
                    "cmd": "enumPortSymbols",
                    "portID": target_port_id,
                    "reqID": symbols_req_id
                }
                
                api.send_command(symbols_cmd)
                symbols_response = api.wait_for_response(symbols_req_id, timeout=10)
                
                if symbols_response and symbols_response.get('success') == 'OK':
                    symbols = symbols_response.get('result', [])
                    print(f"[Portfolio] 📊 {len(symbols)} symbol bulundu!")
                    return symbols
                else:
                    print(f"[Portfolio] ❌ Symbol'lar alınamadı: {symbols_response}")
                    return []
            else:
                print(f"[Portfolio] ❌ {portfolio_name} portfolio'su bulunamadı!")
                return []
        else:
            print(f"[Portfolio] ❌ Portfolio listesi alınamadı: {response}")
            return []
            
    except Exception as e:
        print(f"[Portfolio] ❌ Hata: {e}")
        return []

def process_ssfinek_files(api):
    """SSFINEK dosyalarını işle ve prev_close kolonu ekle"""
    try:
        # Ana veri dosyasını yükle
        main_data_df = load_main_data()
        if main_data_df is None:
            print("❌ Ana veri dosyası yüklenemedi, TIME TO DIV ve DIV AMOUNT bilgileri alınamıyor!")
            return
        
        # Portfolio'dan symbol'ları çek
        print("🎯 janalldata portfolio'sundan symbol'lar çekiliyor...")
        portfolio_symbols = get_symbols_from_portfolio(api, "janalldata")
        
        if portfolio_symbols:
            print(f"📊 Portfolio'da {len(portfolio_symbols)} symbol var, bu symbol'lar için snapshot alınacak!")
            
            # Portfolio symbol'ları için prev_close cache'i oluştur
            prev_close_cache = {}
            
            print("🔄 Portfolio symbol'ları için prev_close değerleri çekiliyor...")
            successful_count = 0
            failed_count = 0
            
            # TÜMÜNÜ cache'e al (ilk 100'ünü)
            max_symbols = min(len(portfolio_symbols), 100)
            
            for i, symbol in enumerate(portfolio_symbols[:max_symbols]):
                if isinstance(symbol, str):
                    prev_close = api.get_symbol_snapshot(symbol)
                    if prev_close > 0:
                        prev_close_cache[symbol] = prev_close
                        successful_count += 1
                        print(f"✅ {symbol}: {prev_close}")
                    else:
                        failed_count += 1
                        if failed_count <= 5:  # İlk 5 başarısızı göster
                            print(f"❌ {symbol}: data yok")
                    
                    if (i + 1) % 20 == 0:
                        print(f"📊 Progress: {i + 1}/{max_symbols} işlendi, Başarılı: {successful_count}, Başarısız: {failed_count}")
                    
                    time.sleep(0.3)  # Rate limiting
            
            print(f"📋 CACHE TAMAMLANDI: {successful_count} başarılı, {failed_count} başarısız")
            print(f"📋 Cache'de {len(prev_close_cache)} symbol'ın prev_close'u var!")
        else:
            prev_close_cache = {}
        
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
                
                # Her hisse için prev_close çek (önce cache'den kontrol et)
                print(f"🔄 {len(df)} hisse için prev_close çekiliyor... (Cache'de {len(prev_close_cache)} symbol var)")
                
                cache_hits = 0
                api_calls = 0
                api_success = 0
                
                for idx, row in df.iterrows():
                    symbol = row['PREF IBKR']
                    if pd.isna(symbol) or symbol == '':
                        continue
                    
                    # Önce cache'den kontrol et
                    if symbol in prev_close_cache:
                        prev_close = prev_close_cache[symbol]
                        cache_hits += 1
                        print(f"📋 {symbol}: cache'den alındı = {prev_close}")
                    else:
                        # Cache'de yoksa API'den çek
                        api_calls += 1
                        print(f"🌐 {symbol}: cache'de yok, API'den çekiliyor...")
                        prev_close = api.get_symbol_snapshot(symbol)
                        
                        # Başarılıysa cache'e ekle
                        if prev_close > 0:
                            prev_close_cache[symbol] = prev_close
                            api_success += 1
                            print(f"✅ {symbol}: API'den alındı = {prev_close}")
                        else:
                            print(f"❌ {symbol}: API'den de alınamadı")
                    
                    df.at[idx, 'prev_close'] = prev_close
                    
                    # Her 10 hissede bir progress göster
                    if (idx + 1) % 10 == 0:
                        print(f"📊 Progress: {idx + 1}/{len(df)} hisse işlendi")
                    
                    # Rate limiting (Hammer Pro API için)
                    time.sleep(1.0)
                
                # NASDAQ exchange ve TIME TO DIV=90 kontrolü yap
                df = adjust_previous_close_for_nasdaq_dividends(df, main_data_df)
                
                # İstatistikleri göster
                print(f"📊 DOSYA İSTATİSTİKLERİ:")
                print(f"   Cache Hit: {cache_hits}")
                print(f"   API Call: {api_calls}")
                print(f"   API Success: {api_success}")
                print(f"   Cache Toplam: {len(prev_close_cache)}")
                
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
    
    # NASDAQ hisseleri hakkında bilgi
    print(f"📊 {len(NASDAQ_STOCKS)} NASDAQ exchange hissesi tanımlandı")
    print("🔍 SADECE TIME TO DIV=89 olan ve bu listedeki NASDAQ hisselerde previous close DIV AMOUNT kadar düşürülecek")
    print("💡 TIME TO DIV=89 = 89 gün var (temettü ödemesine yakın)")
    print("⚠️ Bu listede olmayan hisselerde (PRH, LNC PRD gibi) ASLA düzeltme yapılmayacak!")
    
    # Hammer Pro API bağlantısı
    password = "Nl201090."  # Hammer Pro şifresi
    
    api = HammerProAPI(password)
    
    try:
        # Hammer Pro API'ye bağlan
        if api.connect():
            # Önce data streamer başlat
            print("🔧 Data streamer'ları kontrol ediliyor...")
            api.start_data_streamer()
            
            # AAPL'i subscribe et ki data alabilelim
            print("📡 AAPL subscribe ediliyor...")
            api.subscribe_symbol("AAPL")
            
            # Portfolio'ya ekleyerek previous close data'sını zorla
            print("📊 AAPL'i portfolio'ya ekleniyor...")
            api.add_symbol_to_portfolio("AAPL")
            
            # Test için ETF deneyelim (daha stabil data)
            test_symbols = ["SPY", "TLT", "IWM", "AAPL"]
            test_result = 0
            
            for test_sym in test_symbols:
                print(f"🧪 Test: {test_sym} için prev_close çekiliyor...")
                result = api.get_symbol_snapshot(test_sym)
                print(f"🧪 {test_sym} sonucu: {result}")
                if result > 0:
                    test_result = result
                    print(f"✅ {test_sym} ile test başarılı!")
                    break
                time.sleep(1)  # Rate limiting
            
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
