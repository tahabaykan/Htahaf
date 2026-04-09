# TRUTH TICK VERİ AKIŞI - DETAYLI ANALİZ

## 1. REAL-TIME AKIŞ (Event-Driven - Ana Kaynak)

```
Hammer Pro WebSocket
   ↓ L1Update Event
{
    "cmd": "L1Update",
    "result": {
        "sym": "HBANL",
        "bid": 25.10,
        "ask": 25.12,
        "last": 25.11,      ← TRUTH TICK (gerçek trade)
        "size": 100,        ← Trade size
        "venue": "FNRA"     ← Exchange venue
    }
}
   ↓
HammerFeed._handle_message() (hammer_feed.py:54-105)
   venue = result.get("venue")  ← Artık alınıyor! ✅
   size = result.get("size")    ← Zaten alınıyordu ✅
   
   market_data = {
       "last": 25.11,
       "size": 100,      ← KAYDOLDU ✅
       "venue": "FNRA"   ← KAYDOLDU ✅
   }
   ↓
update_market_data_cache("HBANL", market_data) (market_data_routes.py:754)
   market_data_cache["HBANL"] = market_data
   ↓
XNL Engine / Frontlama kullanımı:
   l1_data = DataFabric.get_fast_snapshot("HBANL")
   {
       "bid": 25.10,
       "ask": 25.12,
       "last": 25.11,   ← TRUTH TICK ✅
       "size": 100,     ← SIZE ✅
       "venue": "FNRA"  ← VENUE ✅
   }
   ↓
Frontlama Validation (frontlama_engine.py:466-493)
   _is_valid_truth_tick(25.11, "FNRA", 100)
   
   FNRA KURALI:
   if venue in ['FNRA', 'ADFN', 'FINRA', 'OTC', 'DARK']:
       return size in [100, 200]  ← 100 lot = GEÇERLI! ✅
```

---

## 2. BOOTSTRAP/RECOVERY AKIŞ (getTicks Komutu)

```
Backend Startup / Symbol Ekleme
   ↓
GRPANTickFetcher._bootstrap_symbol() (grpan_tick_fetcher.py:116-124)
   ↓
HammerClient.get_ticks() (hammer_client.py:648-696)
   Command gönderilir:
   {
       "cmd": "getTicks",
       "reqID": "uuid-1234",
       "sym": "HBANL",
       "lastFew": 150,
       "tradesOnly": true,      ← Sadece trade'ler
       "regHoursOnly": false    ← Tüm saatler
   }
   ↓
Hammer Pro Response:
   {
       "success": "OK",
       "result": {
           "data": [
               {
                   "t": "14:32:15.123",    ← Timestamp
                   "p": 25.11,             ← Price
                   "s": 100,               ← Size
                   "e": "FNRA"             ← Venue (Exchange)
               },
               {
                   "t": "14:30:45.789",
                   "p": 25.10,
                   "s": 200,               ← 200 lot (FNRA geçerli)
                   "e": "FNRA"
               },
               {
                   "t": "14:29:30.456",
                   "p": 25.09,
                   "s": 50,                ← 50 lot (FNRA GEÇERSİZ!)
                   "e": "FNRA"
               },
               {
                   "t": "14:28:00.123",
                   "p": 25.08,
                   "s": 20,                ← 20 lot (NYSE geçerli)
                   "e": "NYSE"
               }
           ]
       }
   }
   ↓
GRPANTickFetcher._fetch_ticks_for_symbol() (grpan_tick_fetcher.py:342-369)
   
   FILTERING LOGIC (KRITIK!):
   
   for tick in all_ticks:
       size = tick.get('s', 0)
       venue = tick.get('e', 'UNKNOWN').upper()
       
       # FNRA/ADFN/TRF (Dark Pool) kuralı:
       if 'FNRA' in venue or 'ADFN' in venue or 'TRF' in venue:
           is_dark = True
           # STRICT: SADECE 100 veya 200 lot
           if size == 100 or size == 200:
               filtered_ticks.append(tick)  ← KABUL ✅
           else:
               # REDDEDİLİR (50 lot fake print!) ❌
               pass
       
       # NYSE/ARCA/NASDAQ kuralı:
       else:
           # SADECE 15+ lot
           if size >= 15:
               filtered_ticks.append(tick)  ← KABUL ✅
   
   SONUÇ:
   filtered_ticks = [
       {"t": "14:32:15.123", "p": 25.11, "s": 100, "e": "FNRA"},  ← ✅
       {"t": "14:30:45.789", "p": 25.10, "s": 200, "e": "FNRA"},  ← ✅
       #  50 lot FNRA → REDDEDİLDİ ❌
       {"t": "14:28:00.123", "p": 25.08, "s": 20, "e": "NYSE"}    ← ✅
   ]
   ↓
TradePrintRouter.route_trade_print() (trade_print_router.py:37-75)
   for tick in filtered_ticks:
       normalized = {
           'time': tick.get('t'),
           'price': float(tick.get('p')),
           'size': float(tick.get('s')),
           'venue': tick.get('e', 'UNKNOWN')
       }
       grpan_engine.add_trade_print(symbol, normalized)
   ↓
GRPANEngine (GRPAN hesaplamaları için kullanılır)
```

---

## 3. TERMİNALLER ARASI VERİ PAYLAŞIMI

### A. XNL Engine → Frontlama Engine

```python
# xnl_engine.py:823
l1_data = await self._get_l1_data("HBANL")

# xnl_engine.py:1206
fabric = get_data_fabric()
snapshot = fabric.get_fast_snapshot("HBANL")

# DataFabric market_data_cache'den okuyor:
return market_data_cache.get("HBANL", {})

# xnl_engine.py:841-843
truth_tick = l1_data.get('last')     # 25.11
truth_size = l1_data.get('size')     # 100  ✅ YENİ!
truth_venue = l1_data.get('venue')   # FNRA ✅ YENİ!

# xnl_engine.py:855-862
frontlama.evaluate_order_for_frontlama(
    ...,
    truth_last=truth_tick,
    truth_venue=truth_venue,  ✅
    truth_size=truth_size     ✅
)
```

### B. GRPAN Tick Fetcher → GRPAN Engine

```
getTicks → Filter (FNRA 100/200, Others 15+) → TradePrintRouter → GRPANEngine
```

### C. RevnBookCheck Terminal → Frontlama Engine

```
Aynı market_data_cache kullanır (ortak kaynak)
```

---

## 4. ✅ SONNormal VERİFİKATİON

### DOĞRU MU?
✅ **EVET!** Truth tick verileri doğru şekilde:

1. **Hammer'dan alınıyor** (L1Update venue bilgisi ile)
2. **market_data_cache'e kaydediliyor** (size ve venue ile birlikte)
3. **XNL Engine'e gönderiliyor** (frontlama validation için)
4. **Frontlama validation çalışıyor** (FNRA 100/200, Others 15+)
5. **GRPAN için filtreleniyor** (aynı kurallar)

### SORUNLAR VAR MIYDI?
❌ **VARDI!** (Ama düzelttik):

1. ❌ **Venue bilgisi alınmıyordu** → ✅ Düzeltildi (hammer_feed.py:81)
2. ❌ **XNL Engine venue/size göndermiyor** → ✅ Düzeltildi (xnl_engine.py:842-843)
3. ✅ **GRPAN Tick Fetcher zaten doğru yapıyordu** (Line 342-369)

---

## 5. ÖZET

| Bileşen | Truth Tick Kullanımı | Validation |
|---------|---------------------|------------|
| **Hammer Feed** | L1Update'ten alır, cache'e yazar | ❌ Validation yok (ham data) |
| **DataFabric** | Cache'den okur, UI'a sunar | ❌ Validation yok (pass-through) |
| **XNL Engine** | Cache'den alır, frontlama'ya gönderir | ✅ Frontlama engine validate eder |
| **Frontlama Engine** | Venue/Size check yapar | ✅ FNRA 100/200, Others 15+ |
| **GRPAN Tick Fetcher** | getTicks ile bootstrap | ✅ Aynı filtre (Line 342-369) |
| **GRPAN Engine** | Filtered tick'leri işler | ✅ Sadece geçerli tick'ler |

---

## 6. KRİTİK KURALLAR

### FNRA/ADFN/TRF (Dark Pool):
```python
SADECE size == 100 OR size == 200
```

### NYSE/ARCA/NASDAQ:
```python
size >= 15
```

### Neden?
- **FNRA 1-5 lot**: Fake/manipülatif printler (market maker test)
- **FNRA 100/200**: Gerçek institutional trade'ler
- **NYSE <15 lot**: Manipülatif (1-14 lot fake printler)
- **NYSE 15+**: Gerçek trade
