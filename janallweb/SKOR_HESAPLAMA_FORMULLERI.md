# 📊 JanAll Skor Hesaplama Formülleri

## 🎯 **Skor Sistemi Genel Açıklama**

JanAll uygulaması, preferred stock ticareti için **6 farklı trading stratejisini** skorlar:
- **3 Buy Stratejisi**: Bid Buy, Front Buy, Ask Buy
- **3 Sell Stratejisi**: Ask Sell, Front Sell, Bid Sell

Her strateji için **ucuzluk/pahalılık skoru** ve **final skor** hesaplanır.

---

## 🧮 **Temel Hesaplamalar**

### 1. **Spread Hesaplama**
```
Spread = Ask Fiyatı - Bid Fiyatı
```

### 2. **Passive Fiyat Hesaplamaları**
```
PF_Bid_Buy = Bid + (Spread × 0.15)     # Biraz bid üstünde al
PF_Front_Buy = Last Price + 0.01        # Son fiyatın 1 cent üstünde al
PF_Ask_Buy = Ask + 0.01                 # Ask'ın 1 cent üstünde al

PF_Ask_Sell = Ask - (Spread × 0.15)     # Biraz ask altında sat
PF_Front_Sell = Last Price - 0.01       # Son fiyatın 1 cent altında sat
PF_Bid_Sell = Bid - 0.01                # Bid'in 1 cent altında sat
```

### 3. **Fiyat Değişimi Hesaplama**
```
PF_Change = Passive Fiyat - Previous Close
```

---

## 📈 **Ucuzluk/Pahalılık Skorları**

### **Bid Buy Ucuzluk Skoru**
```
Bid_Buy_Ucuzluk = (PF_Bid_Buy - Prev_Close) - Benchmark_Change
```
**Anlamı**: Bid'e yakın fiyattan alımın benchmark'e göre ne kadar ucuz olduğu
- **Pozitif değer**: Pahalılaşma (kötü)
- **Negatif değer**: Ucuzlama (iyi)

### **Front Buy Ucuzluk Skoru**
```
Front_Buy_Ucuzluk = (PF_Front_Buy - Prev_Close) - Benchmark_Change
```
**Anlamı**: Son işlem fiyatının üstünden alımın benchmark'e göre ucuzluğu

### **Ask Buy Ucuzluk Skoru**
```
Ask_Buy_Ucuzluk = (PF_Ask_Buy - Prev_Close) - Benchmark_Change
```
**Anlamı**: Ask fiyatının üstünden alımın benchmark'e göre ucuzluğu

### **Ask Sell Pahalılık Skoru**
```
Ask_Sell_Pahali = (PF_Ask_Sell - Prev_Close) - Benchmark_Change
```
**Anlamı**: Ask'a yakın fiyattan satımın benchmark'e göre ne kadar pahalı olduğu
- **Pozitif değer**: Pahalı satış (iyi)
- **Negatif değer**: Ucuz satış (kötü)

### **Front Sell Pahalılık Skoru**
```
Front_Sell_Pahali = (PF_Front_Sell - Prev_Close) - Benchmark_Change
```
**Anlamı**: Son işlem fiyatının altından satımın benchmark'e göre pahalılığı

### **Bid Sell Pahalılık Skoru**
```
Bid_Sell_Pahali = (PF_Bid_Sell - Prev_Close) - Benchmark_Change
```
**Anlamı**: Bid'e yakın fiyattan satımın benchmark'e göre pahalılığı

---

## 🎯 **Final Skorlar**

### **Final Skor Formülü**
```
Final_Skor = FINAL_THG - (400 × Ucuzluk/Pahalılık_Skoru)
```

### **Final BB Skoru** (Bid Buy)
```
Final_BB = FINAL_THG - (400 × Bid_Buy_Ucuzluk)
```
**Anlamı**: FINAL_THG skoruna bid buy ucuzluğunu ekleyerek toplam çekicilik
- **Yüksek değer**: Çok çekici alım fırsatı
- **Düşük değer**: Az çekici

### **Final FB Skoru** (Front Buy)
```
Final_FB = FINAL_THG - (400 × Front_Buy_Ucuzluk)
```
**Anlamı**: Front buy stratejisinin toplam çekiciliği

### **Final AB Skoru** (Ask Buy)
```
Final_AB = FINAL_THG - (400 × Ask_Buy_Ucuzluk)
```
**Anlamı**: Ask buy stratejisinin toplam çekiciliği

### **Final AS Skoru** (Ask Sell)
```
Final_AS = FINAL_THG - (400 × Ask_Sell_Pahali)
```
**Anlamı**: Ask sell stratejisinin toplam çekiciliği

### **Final FS Skoru** (Front Sell)
```
Final_FS = FINAL_THG - (400 × Front_Sell_Pahali)
```
**Anlamı**: Front sell stratejisinin toplam çekiciliği

### **Final BS Skoru** (Bid Sell)
```
Final_BS = FINAL_THG - (400 × Bid_Sell_Pahali)
```
**Anlamı**: Bid sell stratejisinin toplam çekiciliği

---

## 🔄 **Skorların Güncellenmesi**

### **Şu anki durum**: Tüm skorlar **0.00**
**Sebep**: Live market data henüz bağlanmamış

### **Skorların hesaplanması için**:
1. **Hammer Pro'ya bağlan** (Connect butonu)
2. **Live Data Başlat** butonu
3. Market veriler gelince skorlar otomatik hesaplanır

### **Benchmark hesaplama**:
- Her ticker için uygun benchmark (PFF, TLT, SPY, etc.) seçilir
- Benchmark'in günlük değişimi hesaplanır
- Bu değişim skorlara dahil edilir

---

## 💡 **Skor Yorumlama Rehberi**

### **Buy Skorları** (negatif iyi):
- **-10 ile -5**: Çok ucuz alım fırsatı
- **-5 ile 0**: Makul alım
- **0 ile +5**: Pahalı alım
- **+5 üstü**: Çok pahalı, alım yapma

### **Sell Skorları** (pozitif iyi):
- **+5 üstü**: Çok pahalı satış fırsatı
- **0 ile +5**: Makul satış
- **-5 ile 0**: Ucuz satış
- **-5 altı**: Çok ucuz, satış yapma

### **Final Skorlar**:
- **Yüksek Final Skor**: O strateji daha çekici
- **Düşük Final Skor**: O strateji daha az çekici
- **FINAL_THG baz alınır** ve fiyat avantajı eklenir

---

## 🎮 **Praktik Kullanım**

1. **En iyi buy stratejisi**: En yüksek Final_BB, Final_FB, Final_AB
2. **En iyi sell stratejisi**: En yüksek Final_AS, Final_FS, Final_BS
3. **Spread analizi**: Dar spread = düşük işlem maliyeti
4. **Benchmark karşılaştırma**: Market hareketiyle normalizasyon

**Not**: Live data bağlandığında bu skorlar gerçek zamanlı güncellenir!