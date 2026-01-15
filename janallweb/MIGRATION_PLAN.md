# 🎯 JanAll Web Migration Plan

## 📋 Mevcut Tkinter Uygulaması Özellikleri

### ✅ Zaten Yapılanlar
- ✅ Backend API yapısı (Flask)
- ✅ Frontend temel yapı (React)
- ✅ CSV yükleme
- ✅ WebSocket bağlantısı
- ✅ Hammer Pro bağlantısı
- ✅ Pozisyonlar sayfası (temel)
- ✅ Emirler sayfası (temel)

---

## 🚀 Adım Adım Migration Planı

### **ADIM 1: Ana Tablo İyileştirmesi** ⏳ (ŞU AN BURADAYIZ)

**Hedef:** Tkinter'daki ana tabloyu web'e aktar

**Yapılacaklar:**
1. ✅ CSV yükleme çalışıyor
2. ⏳ Tabloda tüm sütunları göster (97 sütun)
3. ⏳ Seçim checkbox'ları ekle
4. ⏳ Tablo scroll ve filtreleme
5. ⏳ Live data güncellemeleri (Fiyat, Bid, Ask, Skorlar)

**Dosyalar:**
- `frontend/src/components/StockTable.jsx` - Güncellenecek
- `frontend/src/pages/MainDashboard.jsx` - Güncellenecek

---

### **ADIM 2: Emir Butonları**

**Hedef:** Tüm emir butonlarını ekle

**Butonlar:**
- Bid Buy
- Front Buy
- Ask Buy
- Ask Sell
- Front Sell
- Bid Sell
- SoftFront Buy
- SoftFront Sell

**Dosyalar:**
- `frontend/src/components/OrderButtons.jsx` - Yeni
- `frontend/src/pages/MainDashboard.jsx` - Güncellenecek
- `backend/routes/api_routes.py` - Emir endpoint'leri

---

### **ADIM 3: Lot Yönetimi**

**Hedef:** Lot seçim ve yönetim sistemi

**Özellikler:**
- Manuel lot girişi (input)
- %25, %50, %75, %100 butonları
- Avg Adv butonu
- Seçili hisselere lot uygula

**Dosyalar:**
- `frontend/src/components/LotManager.jsx` - Yeni
- `frontend/src/pages/MainDashboard.jsx` - Güncellenecek

---

### **ADIM 4: Seçim Kontrolleri**

**Hedef:** Toplu seçim/kaldırma

**Özellikler:**
- Tümünü Seç butonu
- Tümünü Kaldır butonu
- Checkbox ile tek tek seçim

**Dosyalar:**
- `frontend/src/components/SelectionControls.jsx` - Yeni
- `frontend/src/pages/MainDashboard.jsx` - Güncellenecek

---

### **ADIM 5: Mod Sistemi**

**Hedef:** HAMPRO/IBKR mod değiştirme

**Modlar:**
- HAMPRO MOD
- IBKR GUN MOD
- IBKR PED MOD

**Dosyalar:**
- `frontend/src/components/ModeSelector.jsx` - Yeni
- `backend/services/mode_service.py` - Yeni
- `backend/routes/api_routes.py` - Mod endpoint'leri

---

### **ADIM 6: Pozisyonlar Sayfası İyileştirmesi**

**Hedef:** Tkinter'daki pozisyonlar penceresini web'e aktar

**Özellikler:**
- Pozisyon listesi
- Pozisyon detayları
- Pozisyon güncellemeleri (WebSocket)

**Dosyalar:**
- `frontend/src/pages/PositionsPage.jsx` - Güncellenecek
- `frontend/src/components/PositionsTable.jsx` - Güncellenecek

---

### **ADIM 7: Emirler Sayfası İyileştirmesi**

**Hedef:** Tkinter'daki emirler penceresini web'e aktar

**Özellikler:**
- Açık emirler listesi
- Emir iptal etme
- Emir detayları
- Emir güncellemeleri (WebSocket)

**Dosyalar:**
- `frontend/src/pages/OrdersPage.jsx` - Güncellenecek
- `frontend/src/components/OrdersTable.jsx` - Güncellenecek

---

### **ADIM 8: Take Profit Panelleri**

**Hedef:** Take Profit Longs/Shorts panelleri

**Özellikler:**
- Take Profit Longs paneli
- Take Profit Shorts paneli
- Take profit hesaplamaları

**Dosyalar:**
- `frontend/src/pages/TakeProfitPage.jsx` - Yeni
- `frontend/src/components/TakeProfitPanel.jsx` - Yeni
- `backend/services/take_profit_service.py` - Yeni

---

### **ADIM 9: Diğer Paneller**

**Hedef:** Kalan panelleri ekle

**Paneller:**
- Spreadkusu
- Port Adjuster
- BEFHAM
- jdata Analiz
- Top Ten Bid Buy
- Bottom Ten Ask Sell

**Dosyalar:**
- Her panel için ayrı component ve sayfa

---

### **ADIM 10: BDATA/BEFDAY Export**

**Hedef:** Export fonksiyonları

**Özellikler:**
- BDATA Export
- BEFDAY Export
- BDATA Clear
- Exception List

**Dosyalar:**
- `frontend/src/components/ExportButtons.jsx` - Yeni
- `backend/services/export_service.py` - Yeni

---

## 📝 Notlar

- Her adım tamamlandığında test edilecek
- Backend ve frontend birlikte geliştirilecek
- WebSocket ile real-time güncellemeler sağlanacak
- Tkinter'daki tüm özellikler web'e aktarılacak

---

## 🎯 Öncelik Sırası

1. **ADIM 1** - Ana Tablo (En önemli, şu an buradayız)
2. **ADIM 2** - Emir Butonları (Trading için kritik)
3. **ADIM 3** - Lot Yönetimi (Trading için kritik)
4. **ADIM 4** - Seçim Kontrolleri (Kullanıcı deneyimi)
5. **ADIM 5** - Mod Sistemi (Sistem yapısı)
6. Diğer adımlar...









