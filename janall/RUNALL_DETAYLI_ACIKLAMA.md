# RUNALL DETAYLI AÇIKLAMA - TÜM ADIMLAR

## GENEL BAKIŞ

RUNALL, otomatik bir trading bot sırasıdır. Mode'a göre (OFANSIF/DEFANSIF/GECIS) farklı algoritmalar çalıştırır ve pozisyon yönetimi yapar.

---

## RUNALL BAŞLANGIÇ ADIMLARI

### **Adım 1: Lot Bölücü Kontrolü**
- **Ne yapar:** Checkbox'tan kontrol eder, eğer işaretliyse Lot Bölücü'yü açar
- **Dikkat:** Eğer checkbox işaretli değilse veya zaten açıksa atlar
- **Emir gönderir mi:** Hayır, sadece pencere açar

### **Adım 2: Controller'ı ON Yap**
- **Ne yapar:** Controller'ı aktif hale getirir
- **CSV dosyası:** Aktif moda göre doğru CSV kullanır:
  - `IBKR_GUN` → `befibgun.csv`
  - `IBKR_PED` → `befibped.csv`
  - `HAMPRO` → `befham.csv`
- **Emir gönderir mi:** Hayır, sadece Controller'ı aktif eder

### **Adım 3: Pot Toplam Kontrolü ve ADDNEWPOS Butonu Durumu**
- **Ne yapar:** 
  - Exposure limitlerini kontrol eder (async - callback ile)
  - Pot Toplam ve Pot Max Lot değerlerini alır
  - Mode'u belirler (OFANSIF/DEFANSIF/GECIS)
  - ADDNEWPOS butonunun durumunu günceller
- **Kontrol kriterleri:**
  - `pot_total >= pot_max_lot` → ADDNEWPOS butonu pasif
  - `mode == "OFANSIF"` ve `pot_total < pot_max_lot` → ADDNEWPOS butonu aktif
- **Emir gönderir mi:** Hayır, sadece kontrol yapar

### **Adım 4: Mode'a Göre KARBOTU veya REDUCEMORE Başlat**
- **Ne yapar:**
  - `mode == "OFANSIF"` → **KARBOTU** başlatır
  - `mode == "DEFANSIF"` veya `mode == "GECIS"` → **REDUCEMORE** başlatır
- **Flag'ler:**
  - `runall_waiting_for_karbotu = True` (KARBOTU için)
  - `runall_waiting_for_reducemore = True` (REDUCEMORE için)
  - `runall_addnewpos_triggered = False` (ADDNEWPOS'un sadece bir kez tetiklenmesi için)
- **Emir gönderir mi:** Hayır, sadece algoritmayı başlatır

### **Allowed Modu Kontrolü**
- **Ne yapar:** Eğer `runall_allowed_var` checkbox'ı işaretliyse:
  - Otomatik onay sistemi başlatılır (`start_runall_auto_confirm_loop`)
  - Onay pencerelerindeki "Tamam", "Gönder", "Onayla" gibi butonlar otomatik tıklanır
  - "Durdur", "Stop", "İptal", "Cancel" gibi butonlar ASLA tıklanmaz
- **Emir gönderir mi:** Hayır, sadece otomatik onay mekanizmasını başlatır

---

## KARBOTU ALGORİTMASI (OFANSIF MODE)

KARBOTU, Take Profit Longs ve Take Profit Shorts pencerelerindeki pozisyonları filtreleyip emir gönderir.

### **KARBOTU Adım 1: Take Profit Longs Penceresini Aç**
- **Ne yapar:** Take Profit Longs penceresini açar
- **Gort kontrolü:** `karbotu_gort_check_take_profit_longs()` çağrılır
- **Emir gönderir mi:** Hayır, sadece pencere açar

### **KARBOTU Adım 2: Fbtot < 1.10 ve Ask Sell Pahalılık > -0.10**
- **Filtreleme kriterleri:**
  - `Fbtot < 1.10`
  - `Ask Sell Pahalılık > -0.10`
  - `Quantity >= 100 lot` (100 lot altı pozisyonlar atlanır)
  - `Fbtot != 0.0` (N/A değerleri atlanır)
- **Lot yüzdesi:** %50
- **Emir tipi:** **Ask Sell** (Long pozisyonu kapatmak için)
- **Emir gönderir mi:** **EVET** - Koşula uyan pozisyonlar için Ask Sell emirleri gönderir
- **Emir gönderme mantığı:**
  - Her pozisyon için: `lot_qty = qty * 0.50` (yuvarlanır: 100, 200, 300, ...)
  - Minimum lot: 200 lot (200 lot altı emirler gönderilmez)
  - Controller kontrolü yapılır (MAXALW limitleri dahil)
  - Emir fiyatı: Pozisyonun Ask fiyatı
  - Emir tipi: LIMIT, Hidden=True
- **Sonraki adım:** Eğer pozisyon bulunamazsa → Adım 3'e geçer

### **KARBOTU Adım 3: Fbtot 1.11-1.45 ve Ask Sell Pahalılık -0.05 ile +0.04 arası**
- **Filtreleme kriterleri:**
  - `1.11 <= Fbtot <= 1.45`
  - `-0.05 <= Ask Sell Pahalılık <= +0.04`
  - `Quantity >= 100 lot`
  - `Fbtot != 0.0`
- **Lot yüzdesi:** %25
- **Emir tipi:** **Ask Sell**
- **Emir gönderir mi:** **EVET**
- **Sonraki adım:** Eğer pozisyon bulunamazsa → Adım 4'e geçer

### **KARBOTU Adım 4: Fbtot 1.11-1.45 ve Ask Sell Pahalılık > +0.05**
- **Filtreleme kriterleri:**
  - `1.11 <= Fbtot <= 1.45`
  - `Ask Sell Pahalılık > +0.05`
  - `Quantity >= 100 lot`
  - `Fbtot != 0.0`
- **Lot yüzdesi:** %50
- **Emir tipi:** **Ask Sell**
- **Emir gönderir mi:** **EVET**
- **Sonraki adım:** Eğer pozisyon bulunamazsa → Adım 5'e geçer

### **KARBOTU Adım 5: Fbtot 1.46-1.85 ve Ask Sell Pahalılık +0.05 ile +0.10 arası**
- **Filtreleme kriterleri:**
  - `1.46 <= Fbtot <= 1.85`
  - `+0.05 <= Ask Sell Pahalılık <= +0.10`
  - `Quantity >= 100 lot`
  - `Fbtot != 0.0`
- **Lot yüzdesi:** %25
- **Emir tipi:** **Ask Sell**
- **Emir gönderir mi:** **EVET**
- **Sonraki adım:** Eğer pozisyon bulunamazsa → Adım 6'ya geçer

### **KARBOTU Adım 6: Fbtot 1.46-1.85 ve Ask Sell Pahalılık > +0.10**
- **Filtreleme kriterleri:**
  - `1.46 <= Fbtot <= 1.85`
  - `Ask Sell Pahalılık > +0.10`
  - `Quantity >= 100 lot`
  - `Fbtot != 0.0`
- **Lot yüzdesi:** %50
- **Emir tipi:** **Ask Sell**
- **Emir gönderir mi:** **EVET**
- **Sonraki adım:** Eğer pozisyon bulunamazsa → Adım 7'ye geçer

### **KARBOTU Adım 7: Fbtot 1.86-2.10 ve Ask Sell Pahalılık > +0.20**
- **Filtreleme kriterleri:**
  - `1.86 <= Fbtot <= 2.10`
  - `Ask Sell Pahalılık > +0.20`
  - `Quantity >= 100 lot`
  - `Fbtot != 0.0`
- **Lot yüzdesi:** %25
- **Emir tipi:** **Ask Sell**
- **Emir gönderir mi:** **EVET**
- **Sonraki adım:** Eğer pozisyon bulunamazsa → Adım 8'e geçer (Take Profit Shorts açılır)

### **KARBOTU Adım 8: Take Profit Shorts Penceresini Aç**
- **Ne yapar:**
  - Take Profit Longs penceresini kapatır
  - Take Profit Shorts penceresini açar
- **Gort kontrolü:** `karbotu_gort_check_take_profit_shorts()` çağrılır
- **Emir gönderir mi:** Hayır, sadece pencere değiştirir

### **KARBOTU Adım 9: SFStot > 1.70 ve Bid Buy Ucuzluk < +0.10**
- **Filtreleme kriterleri:**
  - `SFStot > 1.70`
  - `Bid Buy Ucuzluk < +0.10`
  - `Quantity >= 100 lot` (mutlak değer)
  - `SFStot != 0.0`
- **Lot yüzdesi:** %50
- **Emir tipi:** **Bid Buy** (Short pozisyonu kapatmak için)
- **Emir gönderir mi:** **EVET** - Koşula uyan pozisyonlar için Bid Buy emirleri gönderir
- **Emir gönderme mantığı:**
  - Her pozisyon için: `lot_qty = abs(qty) * 0.50` (yuvarlanır: 100, 200, 300, ...)
  - Minimum lot: 200 lot
  - Controller kontrolü yapılır
  - Emir fiyatı: Pozisyonun Bid fiyatı
  - Emir tipi: LIMIT, Hidden=True
- **Sonraki adım:** Eğer pozisyon bulunamazsa → Adım 10'a geçer

### **KARBOTU Adım 10: SFStot 1.40-1.69 ve Bid Buy Ucuzluk +0.05 ile -0.04 arası**
- **Filtreleme kriterleri:**
  - `1.40 <= SFStot <= 1.69`
  - `-0.04 <= Bid Buy Ucuzluk <= +0.05`
  - `Quantity >= 100 lot`
  - `SFStot != 0.0`
- **Lot yüzdesi:** %25
- **Emir tipi:** **Bid Buy**
- **Emir gönderir mi:** **EVET**
- **Sonraki adım:** Eğer pozisyon bulunamazsa → Adım 11'e geçer

### **KARBOTU Adım 11: SFStot 1.40-1.69 ve Bid Buy Ucuzluk < -0.05**
- **Filtreleme kriterleri:**
  - `1.40 <= SFStot <= 1.69`
  - `Bid Buy Ucuzluk < -0.05`
  - `Quantity >= 100 lot`
  - `SFStot != 0.0`
- **Lot yüzdesi:** %50
- **Emir tipi:** **Bid Buy**
- **Emir gönderir mi:** **EVET**
- **Sonraki adım:** Eğer pozisyon bulunamazsa → Adım 12'ye geçer

### **KARBOTU Adım 12: SFStot 1.10-1.39 ve Bid Buy Ucuzluk +0.05 ile -0.04 arası**
- **Filtreleme kriterleri:**
  - `1.10 <= SFStot <= 1.39`
  - `-0.04 <= Bid Buy Ucuzluk <= +0.05`
  - `Quantity >= 100 lot`
  - `SFStot != 0.0`
- **Lot yüzdesi:** %25
- **Emir tipi:** **Bid Buy**
- **Emir gönderir mi:** **EVET**
- **Sonraki adım:** Eğer pozisyon bulunamazsa → Adım 13'e geçer

### **KARBOTU Adım 13: SFStot 1.10-1.39 ve Bid Buy Ucuzluk < -0.05**
- **Filtreleme kriterleri:**
  - `1.10 <= SFStot <= 1.39`
  - `Bid Buy Ucuzluk < -0.05`
  - `Quantity >= 100 lot`
  - `SFStot != 0.0`
- **Lot yüzdesi:** %50
- **Emir tipi:** **Bid Buy**
- **Emir gönderir mi:** **EVET**
- **Sonraki adım:** Tüm adımlar tamamlandı → KARBOTU biter

### **KARBOTU Tamamlandıktan Sonra:**
- `karbotu_running = False` yapılır
- Eğer `runall_waiting_for_karbotu == True` ise:
  - `runall_check_karbotu_and_addnewpos()` çağrılır (500ms sonra)
  - Bu fonksiyon exposure kontrolü yapar ve ADDNEWPOS'u tetikler

---

## REDUCEMORE ALGORİTMASI (DEFANSIF/GECIS MODE)

REDUCEMORE, pozisyonları azaltmak için emir gönderir. Detayları KARBOTU'ya benzer şekilde çalışır.

### **REDUCEMORE Tamamlandıktan Sonra:**
- `reducemore_running = False` yapılır
- Eğer `runall_waiting_for_reducemore == True` ise:
  - `runall_check_karbotu_and_addnewpos()` çağrılır (500ms sonra)

---

## ADDNEWPOS ALGORİTMASI

ADDNEWPOS, yeni pozisyonlar eklemek için emir gönderir.

### **ADDNEWPOS Tetiklenme Koşulları:**
- KARBOTU veya REDUCEMORE tamamlandıktan sonra
- `runall_check_karbotu_and_addnewpos()` exposure kontrolü yapar
- `mode == "OFANSIF"` ve `pot_total < pot_max_lot` ise ADDNEWPOS başlatılır

### **ADDNEWPOS Adım 1: Port Adjuster Penceresini Aç**
- **Ne yapar:** Port Adjuster penceresini açar
- **Emir gönderir mi:** Hayır, sadece pencere açar

### **ADDNEWPOS Adım 2: CSV'den Yükle**
- **Ne yapar:** Port Adjuster penceresindeki "CSV'den Yükle" butonuna tıklar
- **Emir gönderir mi:** Hayır, sadece CSV yükler

### **ADDNEWPOS Adım 3: Final FB & SFS Penceresini Aç**
- **Ne yapar:** Port Adjuster penceresindeki "3. Step - Final FB & SFS" butonuna tıklar
- **Emir gönderir mi:** Hayır, sadece pencere açar

### **ADDNEWPOS Adım 4: Grup Ağırlıklarını Yükle**
- **Ne yapar:** Final FB & SFS penceresindeki "Grup Ağırlıklarını Yükle" butonuna tıklar
- **Emir gönderir mi:** Hayır, sadece ağırlıkları yükler

### **ADDNEWPOS Adım 5: TUMCSV Ayarlaması Yap**
- **Ne yapar:** Final FB & SFS penceresindeki "TUMCSV Ayarlaması Yap" butonuna tıklar
- **Emir gönderir mi:** Hayır, sadece ayarlamaları yapar

### **ADDNEWPOS Adım 6: BB Long Sekmesinde SMA63CHG Filtresi Uygula**
- **Ne yapar:** BB Long sekmesinde SMA63CHG filtresini -1.6'dan küçük olacak şekilde ayarlar ve "Uygula" butonuna tıklar
- **Emir gönderir mi:** Hayır, sadece filtreleri uygular

### **ADDNEWPOS Adım 7: Mode'a Göre JFIN Emirlerini Aç**
- **Ne yapar:** Mode'a göre JFIN emirlerini açar:
  - `AddLong Only` → BB Long emirleri
  - `AddShort Only` → SAS Short emirleri
  - `AddBoth` → Önce BB Long, sonra SAS Short
- **Emir gönderir mi:** Hayır, sadece emir penceresini açar

### **ADDNEWPOS Adım 8: Excluded Ticker Kontrolü**
- **Ne yapar:** `excluder_psfalgo.csv` dosyasından excluded ticker'ları yükler ve onay penceresinden çıkarır
- **Emir gönderir mi:** Hayır, sadece excluded ticker'ları çıkarır

### **ADDNEWPOS Adım 9: Emirleri Gönder**
- **Ne yapar:** JFIN onay penceresindeki "Emirleri Gönder" butonuna tıklar
- **Allowed modu:** Eğer `runall_allowed_mode == True` ise, buton otomatik tıklanır
- **Emir gönderir mi:** **EVET** - Tüm emirler gönderilir
- **Callback:** Emirler gönderildikten sonra `final_thg_lot_distributor.py` içindeki callback tetiklenir ve Qpcal başlatılır

---

## QPCAL ALGORİTMASI

Qpcal, Spread Kusu penceresini açar ve lot dağıtımı yapar.

### **Qpcal Tetiklenme:**
- ADDNEWPOS emirleri gönderildikten sonra `final_thg_lot_distributor.py` içindeki callback tetiklenir
- Veya ADDNEWPOS gerekmiyorsa direkt Qpcal başlatılır

### **Qpcal Adımları:**
1. Spread Kusu penceresini açar
2. Lot dağıtımı yapar
3. Emirleri gönderir (eğer gerekirse)

---

## RUNALL DÖNGÜSÜ VE RESTART

### **Döngü Mantığı:**
- RUNALL başlatıldığında `runall_loop_running = True` yapılır
- Her döngüde `runall_loop_count` artırılır
- Qpcal tamamlandıktan sonra 2 dakika bekler, sonra restart yapar

### **Restart İşlemi:**
- `runall_cancel_orders_and_restart()` çağrılır
- Tüm açık emirler iptal edilir (IBKR veya HAMPRO'ya göre)
- `_run_all_sequence_impl(from_restart=True)` tekrar çağrılır

---

## EMİR GÖNDERME MANTIĞI

### **KARBOTU Emir Gönderme:**
1. **Filtreleme:** Pozisyonlar Fbtot/SFStot ve Pahalılık/Ucuzluk kriterlerine göre filtrelenir
2. **Lot Hesaplama:** `lot_qty = qty * (lot_percentage / 100)` (yuvarlanır: 100, 200, 300, ...)
3. **Minimum Lot Kontrolü:** `abs(lot_qty) >= 200` olmalı
4. **Controller Kontrolü:** MAXALW limitleri kontrol edilir
5. **Emir Gönderme:**
   - **Long pozisyonlar için:** Ask Sell emirleri (SELL side)
   - **Short pozisyonlar için:** Bid Buy emirleri (BUY side)
   - Emir tipi: LIMIT, Hidden=True
   - Emir fiyatı: Pozisyonun Ask/Bid fiyatı

### **ADDNEWPOS Emir Gönderme:**
1. **Filtreleme:** BB Long veya SAS Short filtreleri uygulanır
2. **Excluded Ticker Kontrolü:** `excluder_psfalgo.csv` dosyasından excluded ticker'lar çıkarılır
3. **Emir Gönderme:** JFIN onay penceresindeki "Emirleri Gönder" butonuna tıklanır
4. **Allowed Modu:** Eğer aktifse, buton otomatik tıklanır

---

## ALLOWED MODU OTOMATİK ONAY SİSTEMİ

### **Ne Yapar:**
- `start_runall_auto_confirm_loop()` her 500ms'de bir çalışır
- Tüm açık pencereleri tarar
- Onay butonlarını bulur ve otomatik tıklar

### **Tıklanan Butonlar:**
- "OK", "Tamam", "Yes", "Evet", "Kabul", "Accept", "Onayla", "Confirm"
- "Gönder", "Send", "Emirleri Gönder", "Okay", "Devam", "Continue"
- "İlerle", "Proceed", "Başlat", "Start", "Çalıştır", "Run"

### **Tıklanmayan Butonlar:**
- "Durdur", "Stop", "Dur", "İptal", "Cancel", "Reddet", "No", "Hayır"
- "Kapat", "Close", "Exit", "Çık"
- **ÖNEMLİ:** "Emirleri Gönder" butonunda "gönder" kelimesi varsa tıklanır (istisna)

---

## FLAG'LER VE DURUM TAKİBİ

### **RUNALL Flag'leri:**
- `runall_loop_running`: Döngü çalışıyor mu?
- `runall_loop_count`: Kaçıncı döngü?
- `runall_allowed_mode`: Allowed modu aktif mi?
- `runall_waiting_for_karbotu`: KARBOTU bitmesini bekliyor mu?
- `runall_waiting_for_reducemore`: REDUCEMORE bitmesini bekliyor mu?
- `runall_addnewpos_triggered`: ADDNEWPOS tetiklendi mi?
- `runall_addnewpos_started`: ADDNEWPOS başlatıldı mı?
- `runall_addnewpos_callback_set`: ADDNEWPOS callback set edildi mi?

### **KARBOTU Flag'leri:**
- `karbotu_running`: KARBOTU çalışıyor mu?
- `karbotu_current_step`: Hangi adımda?

### **REDUCEMORE Flag'leri:**
- `reducemore_running`: REDUCEMORE çalışıyor mu?

---

## TIMEOUT MEKANİZMALARI

### **ADDNEWPOS Timeout:**
- Eğer ADDNEWPOS 5 dakika içinde tamamlanmazsa:
  - 2 dakika daha bekler
  - Sonra tüm emirleri iptal eder ve restart yapar

### **Exposure Kontrolü Timeout:**
- Exposure kontrolü 15 saniye içinde tamamlanmazsa:
  - Varsayılan değerler kullanılır (`mode=OFANSIF`, `can_add_positions=True`)

---

## ÖNEMLİ NOTLAR

1. **Threading:** Tüm uzun süren işlemler thread'de çalışır, UI bloklanmaz
2. **UI Güncellemeleri:** `safe_ui_call()` ve `priority_ui_call()` kullanılır
3. **Pencere Yönetimi:** Bot pencereleri öne getirmez, kullanıcı istediği pencereye geçebilir
4. **Controller:** Tüm emirler Controller'dan geçer, MAXALW limitleri kontrol edilir
5. **Minimum Lot:** 200 lot altı emirler gönderilmez
6. **100 Lot Filtresi:** 100 lot altı pozisyonlar işleme alınmaz
7. **Allowed Modu:** Onay pencereleri otomatik tıklanır, ama "Durdur" butonları ASLA tıklanmaz

---

## SORUN GİDERME

### **ADDNEWPOS Başlamıyor:**
- `runall_check_karbotu_and_addnewpos()` loglarını kontrol et
- `runall_waiting_for_karbotu` veya `runall_waiting_for_reducemore` flag'lerini kontrol et
- Exposure kontrolü timeout oluyor mu kontrol et

### **Emirler Gönderilmiyor:**
- Controller kontrolünü kontrol et
- Minimum lot kontrolünü kontrol et (200 lot)
- Allowed modu aktifse, onay butonlarının otomatik tıklanıp tıklanmadığını kontrol et

### **Bot Yavaş:**
- `after()` delay'lerini kontrol et (500ms, 1000ms, 2000ms)
- `auto_confirm_loop` polling interval'ini kontrol et (500ms)
- Thread'lerin düzgün çalışıp çalışmadığını kontrol et









