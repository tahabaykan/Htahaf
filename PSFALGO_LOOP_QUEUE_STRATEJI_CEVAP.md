# Janall'da PSFALGO Loop/Cycle Mantığı, Queue Düzeni, Order İptal-Yaz Stratejisi ve UI Donmaması Trick'leri

## 📋 SORU

"Janall'da PSFALGO loop/cycle mantığı, öncelik/queue düzeni, order iptal-yaz stratejisi ve UI donmaması için yaptığımız trick'ler neydi? Quant_engine'e taşırken hangi noktalar kritik?"

---

## 1. PSFALGO LOOP/CYCLE MANTIĞI

### 1.1. RUNALL Döngü Yapısı

RUNALL, **sürekli döngü halinde** çalışan bir master otomasyon sistemidir. Her döngü şu adımları içerir:

```
Döngü Başlangıcı (runall_loop_count++)
    ↓
Adım 1: Lot Bölücü Kontrolü (checkbox kontrolü)
    ↓
Adım 2: Controller ON (limit kontrolleri için)
    ↓
Adım 3: Exposure Kontrolü (Async - thread'de)
    ├─ Pot Toplam < Pot Max → OFANSIF → KARBOTU
    ├─ Pot Toplam >= Pot Max → DEFANSIF → REDUCEMORE
    └─ GEÇİŞ → REDUCEMORE
    ↓
Adım 4: KARBOTU veya REDUCEMORE Başlat (non-blocking)
    ↓
KARBOTU/REDUCEMORE Bitince:
    ↓
Adım 5: ADDNEWPOS Kontrolü
    ├─ Pot Toplam < Pot Max → ADDNEWPOS aktif
    └─ Pot Toplam >= Pot Max → ADDNEWPOS pasif
    ↓
Adım 6: Qpcal İşlemi (Spreadkusu panel)
    ↓
Adım 7: 2 Dakika Bekle (after(120000))
    ↓
Adım 8: Tüm Emirleri İptal Et (runall_cancel_orders_and_restart)
    ↓
Adım 9: Yeni Döngü Başlat (Adım 1'e dön)
```

### 1.2. Döngü Yönetimi

#### **Döngü Durumu Kontrolü:**
```python
# Döngü çalışıyor mu?
self.runall_loop_running = True/False

# Döngü sayacı (kalıcı)
self.runall_loop_count = 0, 1, 2, ...

# Restart flag'i
self._runall_restart_pending = False
```

#### **Döngü Durdurma:**
- **Toggle Mekanizması**: RUNALL butonuna tekrar tıklanırsa döngü durur
- **Stop Butonu**: "RUNALL DURDUR" butonu ile manuel durdurma
- **Restart Kontrolü**: `from_restart=True` ise, döngü durumu kontrolü atlanır

#### **Döngü Restart:**
- **Emir İptal Sonrası**: Tüm emirler iptal edildikten sonra yeni döngü başlar
- **Callback Mekanizması**: KARBOTU/REDUCEMORE bitince callback ile ADDNEWPOS tetiklenir

### 1.3. Döngü İçi State Yönetimi

Her döngü için state bilgileri tutulur:

```python
# Tıklanmış butonları takip et (tekrar tıklamayı önlemek için)
self._clicked_buttons = set()

# Kapatılmış pencereleri takip et
self._closed_windows = set()

# ADDNEWPOS tetiklenme durumu
self.runall_addnewpos_triggered = False

# KARBOTU/REDUCEMORE bekleme durumu
self.runall_waiting_for_karbotu = False
self.runall_waiting_for_reducemore = False
```

### 1.4. Döngü Raporlama

Her döngü için detaylı rapor tutulur:

```python
# Döngü raporu
self.loop_report_loop_number = self.runall_loop_count
self.clear_loop_report()  # Yeni döngü başladığında temizle

# Psfalgo aktivite logu
self.log_psfalgo_activity(
    action="RUNALL Başlatıldı",
    details=f"Allowed Mode: {self.runall_allowed_mode}",
    status="INFO",
    category="RUNALL",
    loop_number=self.runall_loop_count
)
```

---

## 2. ÖNCELİK/QUEUE DÜZENİ

### 2.1. İki Seviyeli Queue Sistemi

Janall'da **iki ayrı queue** kullanılır:

#### **A) Normal Öncelik Queue (`ui_queue`)**
```python
self.ui_queue = Queue()  # Normal UI güncellemeleri için
```

**Kullanım:**
- Thread'lerden gelen normal UI güncellemeleri
- Log mesajları
- Buton durumu güncellemeleri
- Tablo güncellemeleri

**İşleme:**
- `process_ui_queue()`: Her **50ms'de bir** çalışır
- `safe_ui_call()`: Normal öncelikli çağrılar için

#### **B) Yüksek Öncelik Queue (`user_interaction_queue`)**
```python
self.user_interaction_queue = Queue()  # Kullanıcı etkileşimleri için
```

**Kullanım:**
- Kullanıcı buton tıklamaları
- Pencere açma işlemleri
- Kullanıcı etkileşimleri

**İşleme:**
- `process_user_interactions()`: Her **10ms'de bir** çalışır (daha hızlı)
- `priority_ui_call()`: Yüksek öncelikli çağrılar için

### 2.2. Queue İşleme Mantığı

```python
def process_ui_queue(self):
    """UI queue'sunu işle - thread'lerden gelen UI güncellemelerini main thread'de çalıştır"""
    try:
        # ÖNCE kullanıcı etkileşimlerini işle (en yüksek öncelik)
        while True:
            try:
                callback, args, kwargs = self.user_interaction_queue.get_nowait()
                callback(*args, **kwargs)
            except Empty:
                break
        
        # SONRA normal UI güncellemelerini işle
        processed = 0
        while processed < 10:  # Batch işleme (10 item)
            try:
                callback, args, kwargs = self.ui_queue.get_nowait()
                callback(*args, **kwargs)
                processed += 1
            except Empty:
                break
    except Exception as e:
        print(f"[UI_QUEUE] ⚠️ Queue işleme hatası: {e}")
    finally:
        # Her 50ms'de bir queue'yu kontrol et
        self.after(50, self.process_ui_queue)

def process_user_interactions(self):
    """Kullanıcı etkileşimlerini hemen işle - en yüksek öncelik"""
    try:
        while True:
            try:
                callback, args, kwargs = self.user_interaction_queue.get_nowait()
                # Hemen çalıştır (bloklamadan)
                callback(*args, **kwargs)
            except Empty:
                break
    except Exception as e:
        print(f"[USER_INTERACTION] ⚠️ Kullanıcı etkileşim işleme hatası: {e}")
    finally:
        # Her 10ms'de bir kontrol et (çok hızlı yanıt için)
        self.after(10, self.process_user_interactions)
```

### 2.3. Queue Kullanım Örnekleri

#### **Normal Öncelik (safe_ui_call):**
```python
# Thread'den UI güncellemesi
self.safe_ui_call(self.log_message, "✅ İşlem tamamlandı")
self.safe_ui_call(update_buttons)  # Buton durumu güncelle
```

#### **Yüksek Öncelik (priority_ui_call):**
```python
# Kullanıcı buton tıklaması
self.priority_ui_call(open_window)  # Pencere açma
self.priority_ui_call(open_positions)  # Pozisyon penceresi
```

### 2.4. Queue'nun Avantajları

1. **Thread-Safe**: Thread'lerden güvenli şekilde UI güncellemesi
2. **Öncelik Sistemi**: Kullanıcı etkileşimleri her zaman öncelikli
3. **Batch İşleme**: 10 item batch halinde işlenir (performans)
4. **Non-Blocking**: UI donmaz, sürekli responsive kalır

---

## 3. ORDER İPTAL-YAZ STRATEJİSİ

### 3.1. RUNALL İptal-Yaz Döngüsü

RUNALL'da **"2 dakika bekle → İptal et → Yeni döngü"** stratejisi kullanılır:

```
Qpcal İşlemi Tamamlandı
    ↓
2 Dakika Bekle (after(120000))
    ↓
Tüm Açık Emirleri İptal Et
    ├─ IBKR: cancelOrder() veya cancel_order()
    └─ HAMPRO: cancel_order()
    ↓
Yeni Döngü Başlat (run_all_sequence from_restart=True)
```

### 3.2. İptal Stratejisi Detayları

#### **A) İptal Zamanlaması:**
```python
# Qpcal sonrası 2 dakika sayacı
def schedule_cancel_and_restart():
    # Döngü hala çalışıyor mu kontrol et
    runall_still_running = hasattr(self, 'runall_loop_running') and self.runall_loop_running
    runall_still_allowed = hasattr(self, 'runall_allowed_mode') and self.runall_allowed_mode
    should_proceed = runall_still_running or runall_still_allowed
    
    if should_proceed:
        # 2 dakika geçti, emirleri iptal et
        self.runall_cancel_orders_and_restart()
    else:
        # Döngü durdurulmuş, callback iptal edildi
        print("[RUNALL] ⚠️ RUNALL döngüsü durdurulmuş, callback iptal edildi")

# 2 dakika sonra çağrılacak
self.after(120000, schedule_cancel_and_restart)  # 120 saniye = 2 dakika
```

#### **B) İptal İşlemi:**
```python
def runall_cancel_orders_and_restart(self):
    """RUNALL döngüsü: Tüm emirleri iptal et ve tekrar başla (thread'de çalışır)"""
    
    def cancel_orders_thread():
        # IBKR modunda
        if active_account in ["IBKR_GUN", "IBKR_PED"]:
            open_orders = ibkr_client.get_open_orders()
            for order in open_orders:
                order_id = order.get('order_id')
                ibkr_client.cancelOrder(order_id)  # İptal et
        
        # HAMPRO modunda
        else:
            open_orders = self.hammer.get_orders_direct()
            for order in open_orders:
                order_id = order.get('order_id')
                self.hammer.cancel_order(order_id)  # İptal et
        
        # İptal sonrası yeni döngü başlat
        self._run_all_sequence_impl(from_restart=True)
    
    # Thread'de çalıştır (UI'ı bloklamaz)
    thread = threading.Thread(target=cancel_orders_thread, daemon=True)
    thread.start()
```

### 3.3. İptal-Yaz Stratejisinin Mantığı

#### **Neden İptal Ediyoruz?**

1. **Stale Emir Önleme**: 2 dakika sonra piyasa koşulları değişmiş olabilir
2. **Yeni Fırsatlar**: Yeni döngüde daha iyi fırsatlar olabilir
3. **Risk Kontrolü**: Eski emirler risk oluşturabilir
4. **Sistem Temizliği**: Her döngüde temiz başlangıç

#### **Neden 2 Dakika?**

- **Qpcal İşlemi**: Qpcal işleminin tamamlanması için yeterli süre
- **Emir Gerçekleşme**: Emirlerin gerçekleşmesi için makul süre
- **Döngü Hızı**: Çok sık iptal etmek performans sorunu yaratabilir
- **Piyasa Koşulları**: 2 dakika, piyasa koşullarının değişmesi için yeterli

### 3.4. Reverse Order Koruması

**ÖNEMLİ**: Reverse order'lar (kar garantisi emirleri) **iptal edilmez**:

```python
# Sadece normal emirler iptal edilir
# Reverse order'lar korunur (kar garantisi için)
```

---

## 4. UI DONMAMASI İÇİN TRICK'LER

### 4.1. Threading Mekanizması

#### **A) Daemon Thread'ler:**
```python
# Tüm ağır işlemler daemon thread'de çalışır
thread = threading.Thread(target=heavy_operation, daemon=True)
thread.start()
```

**Avantajları:**
- Ana program kapanınca thread'ler otomatik sonlanır
- UI thread'i bloklamaz
- Arka planda çalışır

#### **B) Thread-Safe UI Güncellemeleri:**
```python
# Thread'den UI güncellemesi
def heavy_operation():
    # Ağır işlem (IBKR API, Hammer API, CSV okuma, vs.)
    result = do_heavy_work()
    
    # UI güncellemesi (thread-safe)
    self.safe_ui_call(self.log_message, f"✅ Sonuç: {result}")
    self.safe_ui_call(update_table, data=result)
```

### 4.2. Non-Blocking Zamanlama (`after()`)

Tkinter'ın `after()` metodu kullanılarak **non-blocking zamanlama** yapılır:

```python
# Bloklamayan zamanlama
self.after(200, self.karbotu_gort_check_take_profit_longs)  # 200ms sonra
self.after(1000, self.karbotu_proceed_to_next_step)  # 1 saniye sonra
self.after(120000, self.runall_cancel_orders_and_restart)  # 2 dakika sonra
```

**Avantajları:**
- UI donmaz
- İşlemler sırayla çalışır
- Kullanıcı etkileşimi devam eder

### 4.3. GUI Güncelleme (`update_idletasks()`)

Ağır işlemler arasında GUI'yi güncellemek için:

```python
# GUI'yi güncelle (donmasını önle)
self.update_idletasks()

# Ağır işlem
do_heavy_work()

# GUI'yi tekrar güncelle
self.update_idletasks()
```

### 4.4. Callback Mekanizması

**Async işlemler** için callback kullanılır:

```python
# Async exposure kontrolü
exposure_result = {'ready': False}

def exposure_callback(exposure_info):
    exposure_result['info'] = exposure_info
    exposure_result['ready'] = True

# Async kontrolü başlat
self.check_exposure_limits_async(callback=exposure_callback)

# Sonucu bekle (ama UI'ı bloklamadan)
timeout = 5
elapsed = 0
check_interval = 0.1  # 100ms bekle
while not exposure_result['ready'] and elapsed < timeout:
    time.sleep(check_interval)
    elapsed += check_interval
```

### 4.5. Auto Confirm Loop (Allowed Mod)

**Allowed modunda** otomatik onay sistemi:

```python
def start_runall_auto_confirm_loop(self):
    """RUNALL Allowed modunda otomatik onay döngüsünü başlat"""
    if not self.runall_allowed_mode or not self.runall_loop_running:
        return
    
    # Her 1 saniyede bir onay mesajlarını kontrol et
    self.runall_auto_confirm_messagebox()
    self.after(1000, self.start_runall_auto_confirm_loop)

def runall_auto_confirm_messagebox(self):
    """Onay mesajlarını otomatik olarak kabul et (Evet/Yes butonuna tıkla)"""
    if not self.runall_allowed_mode:
        return
    
    # Tüm Toplevel pencereleri bul
    all_toplevels = []
    for widget in self.winfo_children():
        if isinstance(widget, tk.Toplevel):
            all_toplevels.append(widget)
    
    # Messagebox'ları tespit et ve otomatik onayla
    for window in all_toplevels:
        title = window.title().lower()
        if any(keyword in title for keyword in ['onay', 'confirm', 'başarılı', 'success']):
            # "Evet" veya "Yes" butonunu bul ve tıkla
            find_and_click_yes_button(window)
```

**Özellikler:**
- Her 1 saniyede bir kontrol eder
- Messagebox'ları otomatik onaylar
- Tıklanmış butonları takip eder (tekrar tıklamayı önler)
- Kapatılmış pencereleri takip eder

### 4.6. Proceed to Next Step Mekanizması

**KARBOTU/REDUCEMORE** adımları arasında geçiş:

```python
def karbotu_proceed_to_next_step(self):
    """KARBOTU: Sonraki adıma geç"""
    if not self.karbotu_running:
        return
    
    # Mevcut adıma göre sonraki adımı çağır
    if self.karbotu_current_step == 2:
        self.karbotu_step_3_fbtot_111_145_low()
    elif self.karbotu_current_step == 3:
        self.karbotu_step_4_fbtot_111_145_high()
    # ... vs.
```

**Özellikler:**
- Her adım bitince `after()` ile sonraki adım çağrılır
- Non-blocking geçiş
- UI donmaz

### 4.7. Panel Açma Trick'leri

**Take Profit panelleri** açılırken:

```python
# Non-blocking pencere açma
self.take_profit_longs_panel = TakeProfitPanel(self, "longs")

# GUI'yi güncelle (pencere açıldıktan sonra)
self.update_idletasks()

# İşlemleri after() ile başlat (non-blocking)
self.after(200, self.karbotu_gort_check_take_profit_longs)
```

---

## 5. QUANT_ENGINE'E TAŞIRKEN KRİTİK NOKTALAR

### 5.1. Loop/Cycle Mantığı

#### **Kritik Noktalar:**

1. **Döngü State Yönetimi:**
   - ✅ Döngü sayacı tutulmalı
   - ✅ Döngü durumu (running/stopped) takip edilmeli
   - ✅ Restart mekanizması olmalı
   - ✅ State temizleme (yeni döngü başladığında)

2. **Async İşlemler:**
   - ✅ Exposure kontrolü async olmalı (callback ile)
   - ✅ Timeout mekanizması olmalı
   - ✅ UI thread'i bloklanmamalı

3. **Callback Zinciri:**
   - ✅ KARBOTU/REDUCEMORE bitince ADDNEWPOS tetiklenmeli
   - ✅ ADDNEWPOS bitince Qpcal tetiklenmeli
   - ✅ Qpcal bitince 2 dakika sayacı başlamalı
   - ✅ 2 dakika sonra iptal ve restart

**Quant_Engine'de Nasıl Yapılmalı:**

```python
# FastAPI async endpoint veya background task
@router.post("/runall/start")
async def start_runall_loop():
    # Background task olarak başlat
    asyncio.create_task(runall_loop_task())

async def runall_loop_task():
    loop_count = 0
    while runall_running:
        loop_count += 1
        # Adım 1: Lot Bölücü
        # Adım 2: Controller ON
        # Adım 3: Exposure kontrolü (async)
        exposure_info = await check_exposure_limits_async()
        # Adım 4: KARBOTU/REDUCEMORE (async)
        if exposure_info['mode'] == 'OFANSIF':
            await start_karbotu_async()
        else:
            await start_reducemore_async()
        # Adım 5: ADDNEWPOS (async)
        await check_and_start_addnewpos_async()
        # Adım 6: Qpcal (async)
        await runall_qpcal_async()
        # Adım 7: 2 dakika bekle
        await asyncio.sleep(120)
        # Adım 8: İptal et
        await cancel_all_orders_async()
        # Adım 9: Yeni döngü (loop devam eder)
```

### 5.2. Queue Düzeni

#### **Kritik Noktalar:**

1. **İki Seviyeli Queue:**
   - ✅ Normal öncelik queue (UI güncellemeleri)
   - ✅ Yüksek öncelik queue (kullanıcı etkileşimleri)
   - ✅ Batch işleme (performans için)

2. **Queue İşleme:**
   - ✅ Önce yüksek öncelikli işlemler
   - ✅ Sonra normal öncelikli işlemler
   - ✅ Periyodik kontrol (50ms normal, 10ms yüksek öncelik)

**Quant_Engine'de Nasıl Yapılmalı:**

```python
# FastAPI'de queue sistemi
from asyncio import Queue, PriorityQueue

# İki ayrı queue
ui_queue = Queue()  # Normal öncelik
priority_queue = Queue()  # Yüksek öncelik

# Background task: Queue işleme
async def process_ui_queue_task():
    while True:
        # Önce yüksek öncelikli
        try:
            callback, args, kwargs = priority_queue.get_nowait()
            await callback(*args, **kwargs)
        except asyncio.QueueEmpty:
            pass
        
        # Sonra normal öncelikli (batch)
        for _ in range(10):
            try:
                callback, args, kwargs = ui_queue.get_nowait()
                await callback(*args, **kwargs)
            except asyncio.QueueEmpty:
                break
        
        await asyncio.sleep(0.05)  # 50ms

# Thread-safe UI güncelleme
def safe_ui_call(callback, *args, **kwargs):
    ui_queue.put_nowait((callback, args, kwargs))

def priority_ui_call(callback, *args, **kwargs):
    priority_queue.put_nowait((callback, args, kwargs))
```

### 5.3. Order İptal-Yaz Stratejisi

#### **Kritik Noktalar:**

1. **Zamanlama:**
   - ✅ Qpcal sonrası 2 dakika bekleme
   - ✅ Timeout kontrolü (döngü durdurulmuş mu?)
   - ✅ Callback iptal mekanizması

2. **İptal İşlemi:**
   - ✅ Tüm açık emirleri al (IBKR/HAMPRO)
   - ✅ Her emri iptal et
   - ✅ İptal sonrası yeni döngü başlat

3. **Reverse Order Koruması:**
   - ✅ Reverse order'lar iptal edilmemeli
   - ✅ Sadece normal emirler iptal edilmeli

**Quant_Engine'de Nasıl Yapılmalı:**

```python
# Async order iptal
async def cancel_all_orders_async():
    # Açık emirleri al
    open_orders = await get_open_orders_async()
    
    # Her emri iptal et (reverse order'lar hariç)
    for order in open_orders:
        if not order.get('is_reverse_order', False):
            await cancel_order_async(order['order_id'])
    
    # İptal sonrası yeni döngü başlat
    await start_new_runall_loop()

# Zamanlama
async def schedule_cancel_and_restart():
    await asyncio.sleep(120)  # 2 dakika bekle
    
    # Döngü hala çalışıyor mu kontrol et
    if runall_loop_running:
        await cancel_all_orders_async()
        await start_new_runall_loop()
```

### 5.4. UI Donmaması Trick'leri

#### **Kritik Noktalar:**

1. **Threading → Async:**
   - ✅ Tkinter threading → FastAPI async/await
   - ✅ `threading.Thread` → `asyncio.create_task`
   - ✅ `after()` → `asyncio.sleep` + callback

2. **Queue Sistemi:**
   - ✅ `safe_ui_call` → WebSocket broadcast
   - ✅ `priority_ui_call` → REST API endpoint (hemen yanıt)

3. **Non-Blocking İşlemler:**
   - ✅ Tüm ağır işlemler async olmalı
   - ✅ UI thread'i (FastAPI main thread) bloklanmamalı
   - ✅ Background task'lar kullanılmalı

4. **Auto Confirm:**
   - ✅ Allowed modunda otomatik onay
   - ✅ WebSocket üzerinden otomatik onay mesajları
   - ✅ Frontend'de otomatik onay mekanizması

**Quant_Engine'de Nasıl Yapılmalı:**

```python
# Async işlemler
async def heavy_operation_async():
    # Ağır işlem (IBKR API, Hammer API, CSV okuma)
    result = await do_heavy_work_async()
    
    # WebSocket üzerinden UI güncellemesi
    await websocket_manager.broadcast({
        'type': 'update',
        'data': result
    })

# Background task
@router.post("/runall/start")
async def start_runall():
    # Background task olarak başlat (non-blocking)
    asyncio.create_task(runall_loop_task())
    return {"status": "started"}

# Auto confirm (WebSocket)
async def handle_auto_confirm():
    if runall_allowed_mode:
        # Frontend'e otomatik onay mesajı gönder
        await websocket_manager.broadcast({
            'type': 'auto_confirm',
            'action': 'confirm'
        })
```

### 5.5. Callback Mekanizması

#### **Kritik Noktalar:**

1. **Async Callback:**
   - ✅ Callback'ler async olmalı
   - ✅ Callback zinciri korunmalı
   - ✅ Timeout mekanizması olmalı

2. **State Yönetimi:**
   - ✅ Callback state'i takip edilmeli
   - ✅ Çift tetikleme önlenmeli
   - ✅ Callback iptal mekanizması olmalı

**Quant_Engine'de Nasıl Yapılmalı:**

```python
# Async callback
async def karbotu_complete_callback():
    """KARBOTU bitince çağrılır"""
    # ADDNEWPOS kontrolü
    await check_and_start_addnewpos_async()

# Callback state yönetimi
karbotu_callbacks = {}  # {symbol: callback}

async def start_karbotu_async():
    # Callback kaydet
    karbotu_callbacks['complete'] = karbotu_complete_callback
    
    # KARBOTU başlat
    await karbotu_task()
    
    # Callback çağır
    if 'complete' in karbotu_callbacks:
        await karbotu_callbacks['complete']()
        del karbotu_callbacks['complete']  # Çift tetiklemeyi önle
```

---

## 6. ÖZET: QUANT_ENGINE'E TAŞIRKEN YAPILMASI GEREKENLER

### 6.1. Loop/Cycle Mantığı

✅ **Yapılması Gerekenler:**
1. **Async Loop Task**: `asyncio.create_task` ile background task
2. **Döngü State**: Redis veya in-memory state yönetimi
3. **Callback Zinciri**: Async callback mekanizması
4. **Restart Mekanizması**: Döngü restart için flag

❌ **Yapılmaması Gerekenler:**
1. ❌ Sync blocking işlemler
2. ❌ Threading (FastAPI async kullan)
3. ❌ Tkinter `after()` (asyncio.sleep kullan)

### 6.2. Queue Düzeni

✅ **Yapılması Gerekenler:**
1. **İki Seviyeli Queue**: Normal ve yüksek öncelik
2. **WebSocket Broadcast**: UI güncellemeleri için
3. **REST API**: Kullanıcı etkileşimleri için (hemen yanıt)
4. **Batch İşleme**: Performans için

❌ **Yapılmaması Gerekenler:**
1. ❌ Tkinter queue (FastAPI async queue kullan)
2. ❌ Blocking queue işleme

### 6.3. Order İptal-Yaz Stratejisi

✅ **Yapılması Gerekenler:**
1. **Async İptal**: `asyncio.sleep(120)` ile zamanlama
2. **State Kontrolü**: Döngü durumu kontrolü
3. **Reverse Order Koruması**: Reverse order'ları iptal etme
4. **Restart Mekanizması**: İptal sonrası yeni döngü

❌ **Yapılmaması Gerekenler:**
1. ❌ Sync blocking iptal işlemi
2. ❌ Tüm emirleri iptal etme (reverse order'lar hariç)

### 6.4. UI Donmaması

✅ **Yapılması Gerekenler:**
1. **Async/Await**: Tüm ağır işlemler async
2. **Background Task**: `asyncio.create_task`
3. **WebSocket**: Real-time UI güncellemeleri
4. **Non-Blocking**: Hiçbir işlem main thread'i bloklamamalı

❌ **Yapılmaması Gerekenler:**
1. ❌ Sync blocking işlemler
2. ❌ Threading (FastAPI async kullan)
3. ❌ Tkinter `after()` (asyncio.sleep kullan)

---

## 7. EN KRİTİK NOKTALAR (ÖZET)

### 🎯 **1. Async/Await Kullanımı**
- Tüm ağır işlemler async olmalı
- FastAPI'nin async yapısı kullanılmalı
- Threading yerine asyncio kullanılmalı

### 🎯 **2. State Yönetimi**
- Döngü state'i Redis veya in-memory tutulmalı
- Callback state'i takip edilmeli
- Çift tetikleme önlenmeli

### 🎯 **3. Queue Sistemi**
- İki seviyeli queue (normal + yüksek öncelik)
- WebSocket broadcast (UI güncellemeleri)
- REST API (kullanıcı etkileşimleri)

### 🎯 **4. Non-Blocking İşlemler**
- Hiçbir işlem main thread'i bloklamamalı
- Background task'lar kullanılmalı
- Async callback mekanizması olmalı

### 🎯 **5. Order İptal-Yaz Stratejisi**
- 2 dakika bekleme (async sleep)
- State kontrolü (döngü durdurulmuş mu?)
- Reverse order koruması

---

## 📝 SONUÇ

Janall'daki PSFALGO sistemi, **threading, queue, callback ve non-blocking işlemler** ile çalışan sofistike bir sistemdir. Quant_Engine'e taşırken:

1. **Threading → Async/Await**: Tüm threading mekanizması async/await'e çevrilmeli
2. **Tkinter Queue → FastAPI Queue**: Queue sistemi FastAPI async queue'ya taşınmalı
3. **after() → asyncio.sleep**: Zamanlama asyncio.sleep ile yapılmalı
4. **safe_ui_call → WebSocket**: UI güncellemeleri WebSocket broadcast ile yapılmalı
5. **Callback Mekanizması**: Async callback mekanizması korunmalı

**En kritik nokta**: **Hiçbir işlem blocking olmamalı, her şey async olmalı!**






