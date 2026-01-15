# Phase 9: Real Trader Mode (Human-First UI)

## 📋 Genel Bakış

Phase 9, algoritmayı "order gönderen robot" değil, "tecrübeli trader assistant" gibi kullanmayı sağlar.

**ÖNEMLİ**: Decision / Execution / Proposal katmanlarına **ASLA dokunulmaz**. Sadece trader-friendly UI ve raporlama eklenir.

---

## 🎯 Hedefler

1. **Proposal Board (Trader View)**: PROPOSED proposal'ları trader-friendly format'ta göster
2. **"Why This Trade?" Panel**: Her proposal için detay açıklama
3. **Session Mode**: HUMAN_ONLY mode (ACCEPT/REJECT sadece logging)
4. **Daily Summary**: Gün sonu trader raporu
5. **Proposal Expiration**: Eski proposal'ları expire et

---

## 📁 Dosya Yapısı

```
quant_engine/app/psfalgo/
├── trader_mode.py           # Trader mode manager
└── proposal_explainer.py    # "Why This Trade?" explanations

quant_engine/app/api/
└── psfalgo_routes.py        # Trader endpoints (updated)
```

---

## 🔧 Bileşenler

### 1. TraderModeManager (`trader_mode.py`)

**Sorumluluklar:**
- Manage trader mode (HUMAN_ONLY)
- Handle ACCEPT/REJECT (logging only)
- Proposal expiration
- Daily summary generation

**Özellikler:**
- `accept_proposal()`: ACCEPT (logging only, no execution)
- `reject_proposal()`: REJECT (logging only)
- `expire_old_proposals()`: Expire old proposals (5 min default)
- `generate_daily_summary()`: Daily trader summary

**Trader Mode:**
- `HUMAN_ONLY`: ACCEPT/REJECT sadece logging, execution yok
- `PROPOSAL_ONLY`: Sadece proposal üret, ACCEPT/REJECT yok

### 2. ProposalExplainer (`proposal_explainer.py`)

**Sorumluluklar:**
- Generate human-readable explanations
- Analyze which metrics passed thresholds
- Identify borderline metrics
- Explain befday/today effects
- Explain SMA direction

**Özellikler:**
- `explain_proposal()`: Generate "Why This Trade?" explanation

**Explanation Format:**
```
Bu trade önerildi çünkü:
- FBTOT = 1.05 (< 1.10) ✅
- GORT = 0.8 (> -1) ✅
- SMA63 = +2.5 (pozitif trend) ✅
- Spread = 0.15% (kabul edilebilir) ✅
- Güven skoru: 62% (orta)
```

### 3. Trader API Endpoints (`psfalgo_routes.py`)

**Endpoints:**

#### Proposal Board
- `GET /api/psfalgo/trader/proposals` - Get PROPOSED proposals (trader view)
  - Filters: `sort_by` (confidence, spread_percent, engine, decision_ts)
  - `sort_desc`: Descending (default: True)
  - `limit`: Max proposals (default: 100, max: 500)

#### Why This Trade?
- `GET /api/psfalgo/trader/proposals/{id}/explain` - Get detailed explanation

#### Accept/Reject
- `POST /api/psfalgo/trader/proposals/{id}/accept` - Accept proposal (logging only)
- `POST /api/psfalgo/trader/proposals/{id}/reject` - Reject proposal (logging only)

#### Daily Summary
- `GET /api/psfalgo/trader/daily-summary` - Get daily trader summary

#### Expiration
- `POST /api/psfalgo/trader/expire-old` - Expire old proposals

---

## 📊 Proposal Board Format

**Table Columns:**
- `symbol`: Symbol (PREF_IBKR)
- `engine`: KARBOTU / REDUCEMORE / ADDNEWPOS
- `action`: SELL 300 / BUY 200 / ADD 100
- `qty`: Lot amount
- `proposed_price`: Limit price (or MARKET)
- `bid`, `ask`, `last`: Market prices
- `spread_percent`: Spread percentage
- `fbtot`, `gort`, `sma63_chg`: Key metrics
- `reason`: Decision reason
- `confidence`: Confidence score (0-1)
- `warnings`: Warnings list
- `decision_ts`: Decision timestamp
- `cycle_id`: RUNALL cycle ID
- `explanation`: "Why This Trade?" explanation

**Sort Options:**
- `confidence` (desc): Highest confidence first
- `spread_percent` (asc): Lowest spread first
- `engine`: By engine name
- `decision_ts` (desc): Most recent first

---

## 💬 "Why This Trade?" Explanation

**Format:**
```
Bu trade önerildi çünkü:
- FBTOT = 1.05 (< 1.10) ✅
- GORT = 0.8 (> -1) ✅
- Ask Sell Pahalılık = 0.05 (> -0.10) ✅
- SMA63 = +2.5 (pozitif trend) ✅
- SMA246 = +1.2 (uzun vadeli pozitif) ✅
- Spread = 0.15% (kabul edilebilir) ✅
- Önceki gün pozisyon: 400 lot (bugün değişim: +0 lot)
- Güven skoru: 62% (orta)
```

**Threshold Analysis:**
- Which metrics passed thresholds
- Which are borderline
- Why each metric matters

**Borderline Metrics:**
- Metrics that are close to thresholds
- May need trader attention

---

## 🎮 Session Mode

### HUMAN_ONLY Mode

**Behavior:**
- ACCEPT: Proposal status → ACCEPTED, logged, **NO EXECUTION**
- REJECT: Proposal status → REJECTED, logged
- Execution ASLA tetiklenmez
- Proposal EXPIRED olabilir (5 dk sonra)

**Use Case:**
- Trader proposal'ları görür
- ACCEPT/REJECT kararı verir (logging)
- Manuel olarak broker'da trade eder
- Sistem sadece "ne yapacağını" söyler

### PROPOSAL_ONLY Mode

**Behavior:**
- Sadece proposal üretilir
- ACCEPT/REJECT yok
- Trader sadece proposal'ları görür

---

## 📈 Daily Summary (Trader Raporu)

**Endpoint:** `GET /api/psfalgo/trader/daily-summary?session_date=2025-12-15`

**Response:**
```json
{
  "success": true,
  "summary": {
    "session_date": "2025-12-15",
    "total_proposals": 45,
    "by_engine": {
      "KARBOTU": 30,
      "REDUCEMORE": 10,
      "ADDNEWPOS": 5
    },
    "by_status": {
      "PROPOSED": 20,
      "ACCEPTED": 15,
      "REJECTED": 8,
      "EXPIRED": 2
    },
    "top_symbols": {
      "MS PRK": 8,
      "WFC PRY": 6,
      "BAC PRY": 5
    },
    "accepted_count": 15,
    "rejected_count": 8,
    "expired_count": 2,
    "proposed_count": 20,
    "acceptance_rate": 33.33
  }
}
```

**Human Notes (Optional):**
- Trader hangi proposal'ları gerçekten trade etti?
- Manuel not girişi (future enhancement)

---

## 🚀 Kullanım

### 1. Get Trader Proposals

```bash
GET /api/psfalgo/trader/proposals?sort_by=confidence&sort_desc=true&limit=50
```

### 2. Get Explanation

```bash
GET /api/psfalgo/trader/proposals/{proposal_id}/explain
```

### 3. Accept Proposal

```bash
POST /api/psfalgo/trader/proposals/{proposal_id}/accept
{
  "trader_note": "Good opportunity, will trade manually"
}
```

### 4. Reject Proposal

```bash
POST /api/psfalgo/trader/proposals/{proposal_id}/reject
{
  "trader_note": "Spread too wide"
}
```

### 5. Get Daily Summary

```bash
GET /api/psfalgo/trader/daily-summary?session_date=2025-12-15
```

### 6. Expire Old Proposals

```bash
POST /api/psfalgo/trader/expire-old
```

---

## ⚠️ Önemli Notlar

1. **Execution Layer'a Dokunma YOK**:
   - Execution logic değişmez
   - Broker adapter çağrısı yok
   - ACCEPT/REJECT sadece logging

2. **Dry-Run Kapatma YOK**:
   - `dry_run` ASLA `false` yapılmaz
   - Execution ASLA tetiklenmez

3. **Decision Logic Değiştirme YOK**:
   - Decision engine'ler değişmez
   - Threshold / rule / config değişmez
   - Sadece UI ve raporlama

4. **HUMAN_ONLY Mode**:
   - ACCEPT/REJECT sadece logging
   - Trader manuel olarak trade eder
   - Sistem sadece "ne yapacağını" söyler

5. **Proposal Expiration**:
   - Proposals 5 dakika sonra expire olabilir
   - Expired proposal'lar artık görünmez (PROPOSED değil)

---

## 📈 Sonraki Adımlar

1. ✅ TraderModeManager oluşturuldu
2. ✅ ProposalExplainer oluşturuldu
3. ✅ Trader API endpoints eklendi
4. ✅ Daily summary generation
5. ✅ Proposal expiration
6. ⏳ UI integration (frontend)
7. ⏳ Manual trade notes (optional)

---

## 🎯 Phase 9 Durumu

**TAMAMLANDI** ✅

- TraderModeManager: ✅
- ProposalExplainer: ✅
- Trader API endpoints: ✅
- Daily summary: ✅
- Proposal expiration: ✅
- Documentation: ✅

**Sistem artık "tecrübeli trader assistant" gibi kullanılabilir!** 🔍

Algoritma "ne yapacağını" söyler, trader (sen) son kararı verir.




