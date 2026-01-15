# Testing Checklist - Execution Adapter Architecture

## ✅ ADIM 1: DATA + ENGINE TESTİ (EMİRSİZ)

**Amaç**: ExecutionAdapter çalışıyor mu, Hammer feed düzgün mü, mapping doğru mu

**Komut**:
```bash
cd quant_engine
$env:HAMMER_PASSWORD="Nl201090."
python main.py live --execution-broker HAMMER --hammer-account ALARIC:TOPI002240A7 --no-trading
```

**Kontrol Edilecekler**:
- [ ] L1Update geliyor mu? (Tick logları görünüyor mu?)
- [ ] CIM PRB ↔ CIM-B mapping doğru mu? (Symbol mapper çalışıyor mu?)
- [ ] Spread logları mantıklı mı? (Bid/Ask/Spread değerleri doğru mu?)
- [ ] LiveEngine tick alıyor mu? (`🎯 TICK:` logları görünüyor mu?)
- [ ] Orderbook geliyor mu? (`ORDERBOOK:` logları görünüyor mu?)
- [ ] Authentication başarılı mı?
- [ ] Execution adapter bağlandı mı?

**Beklenen Çıktı**:
```
✅ Hammer Pro authentication successful
✅ Using Hammer Pro for execution (account: ALARIC:TOPI002240A7)
✅ Subscribed to CIM PRB
🎯 TICK: CIM PRB | Last: $XX.XX | Bid: $XX.XX | Ask: $XX.XX | Spread: $X.XX (X.XX%)
ORDERBOOK: CIM PRB | Bid: $XX.XX | Ask: $XX.XX | Spread: $X.XX (X.XX%)
```

---

## ✅ ADIM 2: HAMMER EXECUTION DRY-RUN (MIN QTY)

**Amaç**: HammerExecutionAdapter gerçekten doğru hesaba mı yazıyor?

**Komut**:
```bash
cd quant_engine
$env:HAMMER_PASSWORD="Nl201090."
python main.py live --execution-broker HAMMER --hammer-account ALARIC:TOPI002240A7 --test-order
```

**Kontrol Edilecekler**:
- [ ] Hammer GUI'de emir görünüyor mu?
- [ ] Doğru account mı? (ALARIC:TOPI002240A7)
- [ ] Symbol format doğru mu? (CIM-B formatında mı?)
- [ ] Order price mantıklı mı? (Bid'in altında mı? Fill olmamalı)
- [ ] Order quantity = 1 mi?

**⚠️ KRİTİK**: "Yanlış account'a emir gitti mi?" sorusu burada biter.

**Beklenen Çıktı**:
```
🧪 Sending TEST ORDER:
   Symbol: CIM PRB
   Side: BUY
   Quantity: 1
   Price: $XX.XX (bid: $XX.XX, ask: $XX.XX)
   Broker: HAMMER
   Account: ALARIC:TOPI002240A7
✅ Test order sent successfully
```

**Hammer GUI'de Kontrol**:
- Orders tab'ında emir görünmeli
- Account: ALARIC:TOPI002240A7 olmalı
- Symbol: CIM-B olmalı
- Price: Bid'in altında olmalı (fill olmamalı)

---

## ✅ ADIM 3: IBKR EXECUTION DRY-RUN

**Amaç**: IBKR adapter çalışıyor mu? Hammer feed devam ediyor mu?

**Komut**:
```bash
cd quant_engine
$env:HAMMER_PASSWORD="Nl201090."
python main.py live --execution-broker IBKR --ibkr-account DU123456 --test-order
```

**Önkoşul**: IB Gateway/TWS çalışıyor olmalı ve bağlı olmalı.

**Kontrol Edilecekler**:
- [ ] IB Gateway/TWS'te emir görünüyor mu?
- [ ] Hammer feed devam ediyor mu? (EVET OLMALI - market data hala gelmeli)
- [ ] Symbol format IBKR native mi? (CIM PRB formatında mı?)
- [ ] Doğru account mı? (DU123456)
- [ ] Order price mantıklı mı?

**⚠️ ÖNEMLİ**: Market data hala Hammer'dan gelmeli. IBKR sadece execution için.

**Beklenen Çıktı**:
```
✅ Using IBKR for execution (account: DU123456)
🎯 TICK: CIM PRB | ... (Hammer feed devam ediyor)
🧪 Sending TEST ORDER:
   Symbol: CIM PRB
   Side: BUY
   Quantity: 1
   Price: $XX.XX
   Broker: IBKR
   Account: DU123456
✅ IBKR Order placed: BUY 1 CIM PRB @ $XX.XX (OrderID: XXXX)
```

**IB Gateway/TWS'te Kontrol**:
- Orders tab'ında emir görünmeli
- Account: DU123456 olmalı
- Symbol: CIM PRB olmalı (native format)
- Price: Bid'in altında olmalı

---

## ✅ ADIM 4: DECISION SKELETON STRATEGY

**Amaç**: Basit entry logic ekle, preferred stock logic'i test et.

**Durum**: Henüz implement edilmedi. ADIM 1-3 tamamlandıktan sonra yapılacak.

**Plan**:
```python
# app/engine/live_engine.py - on_tick() içinde
if spread_pct > 1.5 and volume_ok and price_near_par:
    place_limit_buy()
```

---

## 🚨 ÖNEMLİ NOTLAR

1. **Market Data ALWAYS from Hammer** - IBKR'den data çekilmiyor
2. **Account Guard** - Hesaplar karışamaz (validation var)
3. **Symbol Mapping** - Strategy display format kullanır, adapters çevirir
4. **No Strategy Yet** - Şu an sadece motor testi, strategy sonra

---

## 📊 Test Sonuçları

Test sonuçlarını buraya not edin:

### ADIM 1 Sonuçları:
- [ ] Başarılı
- [ ] Hata: _______________

### ADIM 2 Sonuçları:
- [ ] Başarılı
- [ ] Hata: _______________

### ADIM 3 Sonuçları:
- [ ] Başarılı
- [ ] Hata: _______________






