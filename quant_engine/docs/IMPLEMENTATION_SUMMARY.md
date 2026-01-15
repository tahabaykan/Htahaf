# PSFALGO Intentions System - Implementation Summary

## 📋 ÖZET

Bu doküman, PSFALGO Intentions sisteminin implementasyonunu özetler.

---

## A) JANALL VS QUANT MAPPING RAPORU

**Rapor Dosyası**: `quant_engine/docs/JANALL_VS_QUANT_MAPPING_REPORT.md`

### Sonuç
- **Birebirlik Durumu**: ⚠️ **%60-70 Eşleşiyor**
- **Ana Farklar**:
  - Quant Engine daha modern, async, WebSocket tabanlı
  - Janall daha "emir gönderme odaklı", cycle-based iptal mekanizması var
  - Quant Engine'de onay mekanizması var ama "intentions" sistemi yok (ŞİMDİ EKLENDİ ✅)
  - Port Adjuster her iki tarafta da CSV'den yükleniyor ama Quant startup'ta 1 kez

---

## B) PORT ADJUSTER CSV OTOMATİK YÜKLEME

### Durum: ✅ TAMAMLANDI

**Dosya**: `quant_engine/app/port_adjuster/port_adjuster_store.py`

**Mevcut Davranış**:
- Startup'ta `_initialize_persisted()` çağrılıyor
- Öncelik sırası:
  1. `exposureadjuster.csv` (project root)
  2. `port_adjuster_config.json` (fallback)
  3. Default config

**Sonuç**: Port Adjuster zaten CSV'den otomatik yükleniyor, kullanıcı bekletmiyor.

---

## C) INTENTIONS SİSTEMİ

### 1. Veri Modelleri

**Dosya**: `quant_engine/app/psfalgo/intent_models.py`

**Modeller**:
- `Intent`: Ana intent modeli
  - `id`, `timestamp`, `symbol`, `action`, `qty`, `price`, `order_type`
  - `reason_code`, `reason_text`, `trigger_rule`, `metric_values`
  - `risk_checks`, `risk_passed`, `status`
  - `approved_at`, `rejected_at`, `sent_at`, `execution_result`
  - `cycle_number`, `engine_name`

- `IntentStatus`: PENDING, APPROVED, REJECTED, SENT, EXPIRED, FAILED
- `IntentAction`: BUY, SELL, BUY_TO_COVER, SELL_SHORT, REPLACE, CANCEL
- `OrderType`: LIMIT, MARKET, STOP, STOP_LIMIT
- `RiskCheckResult`: Risk check sonuçları

### 2. Intent Store

**Dosya**: `quant_engine/app/psfalgo/intent_store.py`

**Özellikler**:
- Ring buffer (son 1000 intent)
- Per-symbol latest intent tracking
- Status filtering
- Expiration (24 saat, opsiyonel)

**Metodlar**:
- `add_intent(intent)`: Intent ekle
- `get_intent(intent_id)`: ID ile intent getir
- `get_latest_intent(symbol)`: Symbol için son intent
- `get_intents(status, symbol, limit)`: Filtreli intent listesi
- `update_intent_status(intent_id, new_status, reason)`: Status güncelle
- `clear_expired()`: Expired intents temizle
- `clear_all()`: Tüm intents temizle
- `get_stats()`: İstatistikler

### 3. API Endpoints

**Dosya**: `quant_engine/app/api/intent_routes.py`

**Endpoints**:
- `GET /api/psfalgo/intents`: Intent listesi (filtre: status, symbol, limit)
- `GET /api/psfalgo/intents/{intent_id}`: Tek intent getir
- `POST /api/psfalgo/intents/{intent_id}/approve`: Intent onayla ve execute et
- `POST /api/psfalgo/intents/{intent_id}/reject`: Intent reddet
- `POST /api/psfalgo/intents/bulk-approve`: Toplu onay
- `POST /api/psfalgo/intents/clear`: Tüm intents temizle
- `GET /api/psfalgo/intents/stats/summary`: İstatistikler

### 4. RunallEngine Entegrasyonu

**Dosya**: `quant_engine/app/psfalgo/runall_engine.py`

**Değişiklikler**:
- `_step_run_karbotu()`: Execution yerine intent_store'a yazıyor
- `_step_run_reducemore()`: (TODO: Aynı değişiklik yapılacak)
- `_step_run_addnewpos()`: (TODO: Aynı değişiklik yapılacak)

**Akış**:
```
Decision Engine → ExecutionPlan → Intent (PENDING) → IntentStore
                                                      ↓
                                              User Approval
                                                      ↓
                                              Execution Engine
```

### 5. Execution Engine Entegrasyonu

**Dosya**: `quant_engine/app/psfalgo/execution_engine.py`

**Yeni Metod**:
- `execute_plan_from_intent(order_plan)`: Approved intent'ten order execute et

---

## D) YAPILACAK İŞLER (Kalan)

### 🔴 KRİTİK

1. **REDUCEMORE Intent Entegrasyonu**: `_step_run_reducemore()` metodunda intent_store'a yazma
2. **ADDNEWPOS Intent Entegrasyonu**: `_step_run_addnewpos()` metodunda intent_store'a yazma

### 🟡 ÖNEMLİ

3. **UI Panel**: PSFALGO Intentions paneli (React component)
4. **WebSocket Broadcast**: Intent status değişikliklerini broadcast et

### 🟢 İYİLEŞTİRME

5. **Risk Checks**: Intent oluşturulurken risk check'leri ekle
6. **Expiration**: PENDING intents için expiration mekanizması
7. **Bulk Operations**: Toplu approve/reject UI

---

## E) DOSYA LİSTESİ

### Yeni Dosyalar
- `quant_engine/app/psfalgo/intent_models.py`
- `quant_engine/app/psfalgo/intent_store.py`
- `quant_engine/app/api/intent_routes.py`
- `quant_engine/docs/JANALL_VS_QUANT_MAPPING_REPORT.md`
- `quant_engine/docs/IMPLEMENTATION_SUMMARY.md`

### Değiştirilen Dosyalar
- `quant_engine/app/psfalgo/runall_engine.py` (KARBOTU intent entegrasyonu)
- `quant_engine/app/psfalgo/execution_engine.py` (execute_plan_from_intent eklendi)
- `quant_engine/app/api/main.py` (intent_router eklendi)

---

## F) AKIŞ DİYAGRAMI

```
RUNALL Cycle
    ↓
KARBOTU/REDUCEMORE/ADDNEWPOS Decision Engine
    ↓
ExecutionPlan (ExecutionIntent listesi)
    ↓
Intent Creation (PENDING status)
    ↓
IntentStore.add_intent()
    ↓
[User sees intent in UI]
    ↓
User Approval/Rejection
    ↓
[If Approved]
    ↓
ExecutionEngine.execute_plan_from_intent()
    ↓
Intent Status → SENT
    ↓
[Order executed (dry-run or real)]
```

---

## G) ACCEPTANCE CRITERIA

### ✅ TAMAMLANAN

- [x] Intent veri modeli oluşturuldu
- [x] IntentStore (in-memory ring buffer) implement edildi
- [x] API endpoints oluşturuldu
- [x] KARBOTU intent entegrasyonu yapıldı
- [x] Execution engine intent desteği eklendi
- [x] Janall vs Quant mapping raporu hazırlandı
- [x] Port Adjuster CSV otomatik yükleme kontrol edildi (zaten var)

### ⏳ KALAN

- [ ] REDUCEMORE intent entegrasyonu
- [ ] ADDNEWPOS intent entegrasyonu
- [ ] UI Panel (React component)
- [ ] WebSocket broadcast (intent status updates)

---

## H) SONUÇ

**Durum**: 🟡 **%70 Tamamlandı**

**Ana Başarılar**:
- Intentions sistemi temel altyapısı hazır
- KARBOTU intent entegrasyonu çalışıyor
- API endpoints hazır ve test edilebilir

**Sonraki Adımlar**:
1. REDUCEMORE ve ADDNEWPOS intent entegrasyonu
2. UI Panel implementasyonu
3. WebSocket broadcast entegrasyonu





