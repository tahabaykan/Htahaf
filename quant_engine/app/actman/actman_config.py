"""
ACTMAN Configuration & Constants — V2

3-Tier Execution (K1 Pasif / K2 Front / K3 Aktif)
Hedger: Config L/S drift correction (per-account, same config %)
Panic: ETF 2min/5min bar reaction (freeze-time, diversified)

Tag System: Dual v4 compatible (LT_ACTHEDGE_*, LT_ACTPANIC_*)
"""

from typing import Dict


# ═══════════════════════════════════════════════════════════════
# MASTER ENABLE/DISABLE
# ═══════════════════════════════════════════════════════════════

HEDGER_ENABLED = True              # Hedger engine aktif mi?
PANIC_ENABLED = True               # Panic engine aktif mi?

# Default config target — can be overridden per-account via Redis
# Redis key: psfalgo:actman:config_long_pct:{account_id}
HEDGER_CONFIG_LONG_PCT = 60.0      # Hedef Long yüzdesi (%) — HAMPRO & IBKR_PED default


# ═══════════════════════════════════════════════════════════════
# KUPONLU GROUPS (CGRUP only applies to these)
# ═══════════════════════════════════════════════════════════════

KUPONLU_GROUPS = {'heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta'}

# ═══════════════════════════════════════════════════════════════
# ACTMAN ELIGIBLE GROUPS
# Only "held" prefix groups participate in hedging/panic.
# Non-held groups (highmatur, notcefilliquid, salakilliquid, etc.)
# are illiquid and market-independent → never touched by ACTMAN.
# Also excluded: heldsolidbig (too concentrated), heldbesmaturlu.
# ═══════════════════════════════════════════════════════════════

ACTMAN_EXCLUDED_GROUPS = {
    # Non-held groups — illiquid, piyasadan bağımsız
    'highmatur', 'notcefilliquid', 'notbesmaturlu', 'nottitrekhc',
    'salakilliquid', 'shitremhc', 'rumoreddanger',
    # Held groups with special exclusion
    'heldsolidbig',     # Çok konsantre, büyük bankalar — ayrı yönetilir
    'heldbesmaturlu',   # Vadeye yakın — ACTMAN müdahalesine uygun değil
}

# Eligible = any DOS_GRUP starting with "held" that is NOT in excluded set
ACTMAN_ELIGIBLE_HELD_GROUPS = {
    'heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta',
    'helddeznff', 'heldff', 'heldflr', 'heldnff',
    'heldgarabetaltiyedi', 'heldotelremorta',
    'heldcommonsuz', 'heldtitrekhc', 'heldcilizyeniyedi',
}

def is_actman_eligible(dos_grup: str) -> bool:
    """Check if a DOS_GRUP is eligible for ACTMAN hedging/panic."""
    if not dos_grup:
        return False
    return dos_grup in ACTMAN_ELIGIBLE_HELD_GROUPS


# ═══════════════════════════════════════════════════════════════
# DUAL v4 TAGS — Order tagging for ACTMAN
# Format: {POS}_{ENGINE}_{DIRECTION}_{INC/DEC}
# POS = LT (all ACTMAN positions are Long-Term class)
# ENGINE = ACTHEDGE or ACTPANIC
# ═══════════════════════════════════════════════════════════════

# Hedger tags
TAG_HEDGER_LONG_INC = "LT_ACTHEDGE_LONG_INC"    # Hedger long açma
TAG_HEDGER_SHORT_INC = "LT_ACTHEDGE_SHORT_INC"   # Hedger short açma

# Panic INC tags
TAG_PANIC_LONG_INC = "LT_ACTPANIC_LONG_INC"      # Panic long açma
TAG_PANIC_SHORT_INC = "LT_ACTPANIC_SHORT_INC"     # Panic short açma

# ── DECREASE TAGS ──
# Hedger: config'e yaklaşmak için mevcut pozisyonu azalt
TAG_HEDGER_LONG_DEC = "LT_ACTHEDGE_LONG_DEC"     # Hedger: long azalt (SELL)
TAG_HEDGER_SHORT_DEC = "LT_ACTHEDGE_SHORT_DEC"    # Hedger: short azalt (BUY/COVER)

# Panic: acil pozisyon azaltma
TAG_PANIC_LONG_DEC = "LT_ACTPANIC_LONG_DEC"       # Panic selloff → long azalt (SELL)
TAG_PANIC_SHORT_DEC = "LT_ACTPANIC_SHORT_DEC"      # Panic ralli → short azalt (BUY/COVER)

ALL_ACTMAN_TAGS = [
    TAG_HEDGER_LONG_INC, TAG_HEDGER_SHORT_INC,
    TAG_HEDGER_LONG_DEC, TAG_HEDGER_SHORT_DEC,
    TAG_PANIC_LONG_INC, TAG_PANIC_SHORT_INC,
    TAG_PANIC_LONG_DEC, TAG_PANIC_SHORT_DEC,
]

# Legacy aliases (backward compatibility)
ACTMAN_HEDGER_BUY = TAG_HEDGER_LONG_INC
ACTMAN_HEDGER_SELL = TAG_HEDGER_SHORT_INC
ACTMAN_PANIC_BUY = TAG_PANIC_LONG_INC
ACTMAN_PANIC_SELL = TAG_PANIC_SHORT_INC


# ═══════════════════════════════════════════════════════════════
# DECREASE SCORING WEIGHTS
# Long Decrease: En kötü longları bul → SAT
# Short Decrease: En kötü shortları bul → KAPAT (cover)
# ═══════════════════════════════════════════════════════════════

DEC_WEIGHT_SCORE = 35       # final_bs (long dec) / final_ab (short dec)
DEC_WEIGHT_SPREAD = 30      # Dar spread = kolay execution
DEC_WEIGHT_TRUTH = 30       # Truth-Bid/Ask yakınlığı
DEC_WEIGHT_MAXALW = 5       # MAXALW doluluk

# ═══════════════════════════════════════════════════════════════
# DECREASE LOT RULES (LT_TRIM / KARBOTU'dan kopyalanmış)
# ═══════════════════════════════════════════════════════════════

DEC_MIN_POSITION_LOT = 125  # <125 lot pozisyon → DEC'e aday olmaz (ciddiye alınmaz)
DEC_MIN_LOT = 125           # Min decrease lot (emirin kendisi)
DEC_DUST_THRESHOLD = 70     # <70 lot kalan → es geç (dust)
DEC_FULL_CLOSE_THRESHOLD = 400  # <400 lot kalacaksa → komple kapat
DEC_ROUND_TO = 100          # 100'e yuvarla

# ═══════════════════════════════════════════════════════════════
# EXPOSURE-BASED DEC/INC RATIO
# DEC önce çalışır → kalan lot INC'e devredilir
# ═══════════════════════════════════════════════════════════════

DEC_INC_RATIO_HIGH_EXP = (80, 20)    # Exposure ≥80% → %80 DEC, %20 INC
DEC_INC_RATIO_MID_EXP = (50, 50)     # Exposure 60-80% → default
DEC_INC_RATIO_LOW_EXP = (20, 80)     # Exposure 40-60%
DEC_INC_RATIO_VERY_LOW = (10, 90)    # Exposure <40%


# ═══════════════════════════════════════════════════════════════
# 3-TIER EXECUTION SYSTEM
# K1 = Pasif (limit order, ask/bid önüne)
# K2 = Front (truth tick frontlama, truth ± $0.01)
# K3 = Aktif (bid/ask'a vur, anında fill)
# ═══════════════════════════════════════════════════════════════

# K1: always available (no gate required)
# K2: truth tick data required + moderate spread
TIER_K2_MAX_SPREAD = 0.20         # K2 FRONT için max spread ($)
TIER_K2_MAX_TRUTH_DIST = 0.15     # K2 FRONT için max truth mesafesi ($)

# K3: tight spread + close truth
TIER_K3_MAX_SPREAD = 0.12         # K3 AKTİF için max spread ($)
TIER_K3_MAX_TRUTH_DIST = 0.08     # K3 AKTİF için max truth mesafesi ($)

# Price calculation offsets
K1_SPREAD_FRACTION = 0.15         # K1: ask - spread*0.15 (SELL), bid + spread*0.15 (BUY)
K2_TRUTH_OFFSET = 0.01            # K2: truth - $0.01 (SELL), truth + $0.01 (BUY)
K3_ACTIVE_OFFSET = 0.01           # K3: bid - $0.01 (SELL), ask + $0.01 (BUY)


# ═══════════════════════════════════════════════════════════════
# HEDGER — Drift Correction Config
# L/S yüzde farkına göre K1/K2/K3 katman dağılımı
# ═══════════════════════════════════════════════════════════════

# Minimum drift to trigger hedger (%)
HEDGER_MIN_DRIFT_PCT = 2.0

# Drift tier boundaries (L/S yüzde farkı)
# < 2%   → no action
# 2-5%   → 100% K1 (pasif)
# 5-10%  → K1+K2 blend (pasif + front)
# 10-15% → mostly K2 (front aggressive)
# 15%+   → K2+K3 (front + aktif bid vuruş)
# K3 sadece %15+ drift'te! Altında aktif vurma yok.
HEDGER_TIER_BOUNDARIES = {
    'pasif_only':  5.0,    # %2-%5 → %100 K1
    'front_start': 5.0,    # %5+ → K2 başlar
    'aktif_start': 15.0,   # %15+ → K3 başlar (ÖNCEKİ: %8)
    'full_aktif':  20.0,   # %20+ → max K3
}

# DOS_GRUP Balance Rule
DOSGROUP_TRIGGER_PCT = 15.0
DOSGROUP_MIN_OPPOSITE_PCT = 5.0

# BefDay drift (intraday position change)
BEFDAY_DRIFT_THRESHOLD_PCT = 15.0

# Per-cycle limits
MAX_CANDIDATES_PER_GROUP = 5      # Max symbols to evaluate per group
LOT_ROUND_TO = 100                # Round lots to nearest 100
MIN_LOT_SIZE = 200                # Minimum lot size per order (Hedger)
MAXALW_SAFETY_MARGIN = 0.80       # Use 80% of MAXALW room
HEDGER_MAX_PCT_SINGLE_IN_GROUP = 40  # Tek sembol max %40 grup tahsisinin (diversifikasyon)


# ═══════════════════════════════════════════════════════════════
# HEDGER SCORING WEIGHTS (V7 — 100 puan)
# ═══════════════════════════════════════════════════════════════

# Truth proximity normalization cap (dollars)
TRUTH_PROX_MAX_DIST = 0.30

# SELL scoring (short açma)
SELL_WEIGHTS_KUPONLU = {
    'final_bs':     30,   # FINAL_BS (group-relative) — low = good short
    'spread':       30,   # narrow = cheap to execute
    'truth_prox':   20,   # |truth_avg - bid| — small = safe to sell
    'maxalw':        8,   # room left
    'avg_adv':       7,   # liquidity match
    'cgrup':         5,   # quality proximity (kuponlu only)
}
SELL_WEIGHTS_NONKUP = {
    'final_bs':     30,
    'spread':       30,
    'truth_prox':   20,
    'maxalw':       10,
    'avg_adv':      10,
}

# BUY scoring (long açma)
BUY_WEIGHTS_KUPONLU = {
    'final_as':     30,   # FINAL_AB (group-relative) — high = good long
    'spread':       30,
    'truth_prox':   20,
    'maxalw':        8,
    'avg_adv':       7,
    'cgrup':         5,
}
BUY_WEIGHTS_NONKUP = {
    'final_as':     30,
    'spread':       30,
    'truth_prox':   20,
    'maxalw':       10,
    'avg_adv':      10,
}


# ═══════════════════════════════════════════════════════════════
# HEDGER HARD FILTERS (pass/fail — failing = elimination)
# ═══════════════════════════════════════════════════════════════

CGRUP_MAX_STEPS = 2                # Max CGRUP distance (kuponlu only)
AVG_ADV_MAX_RATIO = 4.0            # Max ADV ratio vs group reference
MIN_AVG_ADV = 3000                 # Minimum AVG_ADV for any candidate
MAX_SPREAD_PCT = 3.0               # Maximum spread as % of ask


# ═══════════════════════════════════════════════════════════════
# PANIC — ETF-Driven Emergency Hedge
# ═══════════════════════════════════════════════════════════════

PANIC_ENABLED = True

# ETF tetikleme eşikleri (2dk ve 5dk bar değişimleri)
# ACTMAN Panic, ETF Guard micro-trigger'dan ÖNCE devreye girer.
# type: 'pct' = % change, 'abs' = $ change
# 2dk: faster detection, 5dk: sustained move
# K2/K3 only for 2min (K1 doesn't make sense for 2min detection)
PANIC_ETF_TIERS: Dict[str, Dict] = {
    #              2dk K2    2dk K3    5dk K1    5dk K2    5dk K3    birim
    'SPY': {'type': 'pct', '2min_k2': 0.25, '2min_k3': 0.40,
            '5min_k1': 0.15, '5min_k2': 0.30, '5min_k3': 0.50},
    'PFF': {'type': 'abs', '2min_k2': 0.04, '2min_k3': 0.06,
            '5min_k1': 0.03, '5min_k2': 0.06, '5min_k3': 0.10},
    'KRE': {'type': 'pct', '2min_k2': 0.30, '2min_k3': 0.50,
            '5min_k1': 0.20, '5min_k2': 0.40, '5min_k3': 0.70},
    'TLT': {'type': 'abs', '2min_k2': 0.15, '2min_k3': 0.25,    # TERSİ: TLT UP = bearish
            '5min_k1': 0.10, '5min_k2': 0.20, '5min_k3': 0.35},
    'IEF': {'type': 'abs', '2min_k2': 0.08, '2min_k3': 0.12,    # TERSİ: IEF UP = bearish
            '5min_k1': 0.06, '5min_k2': 0.12, '5min_k3': 0.18},
    'IWM': {'type': 'pct', '2min_k2': 0.25, '2min_k3': 0.40,
            '5min_k1': 0.15, '5min_k2': 0.30, '5min_k3': 0.60},
}

# TLT and IEF are reverse-correlated: UP = bearish for preferred stocks
PANIC_REVERSE_ETFS = {'TLT', 'IEF'}

# Config shift limits
# How far Panic can shift the L/S target beyond base config
PANIC_MAX_CONFIG_SHIFT = 5.0       # Max %5 beyond config in either direction

# Severity to shift mapping (for SELL direction — shorts)
# Multiplied by PANIC_MAX_CONFIG_SHIFT to get actual shift
# E.g., 'sert' = 1.0 × 5.0 = %5 shift
PANIC_SEVERITY_SHIFT = {
    'hafif':  0.0,    # Config'e kadar izin (shift yok)
    'orta':   0.5,    # Config + %2.5
    'sert':   1.0,    # Config + %5 (maximum)
}


# ═══════════════════════════════════════════════════════════════
# PANIC SCORING WEIGHTS (100 puan — Hedger'dan farklı)
# ═══════════════════════════════════════════════════════════════

PANIC_SELL_WEIGHTS = {
    'final_bs':     20,   # BS grup-içi (düşük = iyi short)
    'spread':       25,   # dar spread = ucuz execution
    'truth_prox':   15,   # truth yakınlığı
    'sfs_score':    20,   # SFS skoru (düşük = front sell ucuz) — YENİ
    'avg_adv_size': 15,   # AVG_ADV büyüklüğü (yüksek = fill kolay) — YENİ
    'maxalw':        5,   # room
}

PANIC_BUY_WEIGHTS = {
    'final_ab':     20,   # AB grup-içi (yüksek = iyi long)
    'spread':       25,
    'truth_prox':   15,
    'fb_score':     20,   # FB skoru (yüksek = front buy uygun) — YENİ
    'avg_adv_size': 15,   # AVG_ADV büyüklüğü — YENİ
    'maxalw':        5,
}

# ADV size breakpoints for panic scoring (no hard filter — only scoring)
PANIC_ADV_SIZE_BREAKPOINTS = [
    (100_000, 15.0),   # 100K+ → full points
    (60_000,  12.0),
    (30_000,   8.0),
    (10_000,   4.0),
    (0,        0.0),   # <10K → 0 points
]


# ═══════════════════════════════════════════════════════════════
# PANIC DIVERSIFICATION
# ═══════════════════════════════════════════════════════════════

PANIC_MAX_PCT_SINGLE_SYMBOL = 25   # Tek sembol max %25 toplam lot'un (daha diversifiye)
PANIC_MIN_SYMBOLS = 2              # Min 2 sembol (dayatma değil ama tercih)
PANIC_MIN_LOT_SIZE = 200           # Min 200 lot (Hedger ile aynı)


# ═══════════════════════════════════════════════════════════════
# PANIC ETF TRIGGER THRESHOLDS
#
# ÖNEMLI: Sadece HIZLI hareketler (2-5 dk penceresi) panic tetikler!
# 30 dk'da $0.05 düşüş = anlamsız, panic tetiklemez.
# 2-5 dk'da $0.04 düşüş = hızlı hareket, panic tetikler.
#
# Her ETF için: (K1_threshold, K2_threshold, K3_threshold)
# ETF Guard piyasayı sürekli izler:
#   Düşüş → panic mode + sell emirleri
#   Recover → ralli uyarısı + cancel all sells
# ═══════════════════════════════════════════════════════════════

# Time window: panic sadece bu pencerede oluşan hareketlere bakar
PANIC_FAST_WINDOW_SEC = 300        # 5 dakika
PANIC_MIN_WINDOW_SEC = 120         # Min 2 dakika (daha kısa veriler güvenilmez)

# SPY: Yüzdesel düşüş (anlık, 2-5 dk penceresi)
PANIC_SPY_K1_PCT = -0.3            # -%0.3 → K1 (front heavy, %70 K2 + %30 K3)
PANIC_SPY_K2_PCT = -0.4            # -%0.4 → K2 (agresif, %40 K2 + %60 K3)
PANIC_SPY_K3_PCT = -0.6            # -%0.6 → K3 (full agresif, %100 K3)

# KRE: Yüzdesel düşüş (anlık, 2-5 dk penceresi)
PANIC_KRE_K1_PCT = -0.4            # -%0.4 → K1
PANIC_KRE_K2_PCT = -0.6            # -%0.6 → K2
PANIC_KRE_K3_PCT = -0.8            # -%0.8 → K3

# IWM: Yüzdesel düşüş (anlık, 2-5 dk penceresi) — KRE ile aynı
PANIC_IWM_K1_PCT = -0.4            # -%0.4 → K1
PANIC_IWM_K2_PCT = -0.6            # -%0.6 → K2
PANIC_IWM_K3_PCT = -0.8            # -%0.8 → K3

# TLT: PANIC YOK — sadece ETF Guard freeze
# TLT düşüşü panic tetiklemez, sadece freeze mekanizması çalışır
PANIC_TLT_ENABLED = False

# PFF: DOLAR bazlı düşüş (yüzde DEĞİL!) — anlık, 2-5 dk penceresi
PANIC_PFF_K1_DOLLAR = -0.04        # -$0.04 → K1
PANIC_PFF_K2_DOLLAR = -0.06        # -$0.06 → K2
PANIC_PFF_K3_DOLLAR = -0.08        # -$0.08 → K3

# PFF HARD STOP: Yavaş kayma (1 saat penceresi) — farklı mekanizma!
# Bu panic değil, ETF Guard hard stop bölgesi.
PFF_HARDSTOP_DOLLAR = -0.15        # -$0.15 düşüş (1 saat) → hard stop bölgesi
PFF_HARDSTOP_WINDOW_SEC = 3600     # 1 saat penceresi

# Ralli tetikleri (panic'in tersi — cancel all sells + short azalt)
# Aynı eşikler ama TERSİ: pozitif hareket
PANIC_RALLY_MULTIPLIER = 1.0       # Ralli eşikleri = düşüş eşikleri × bu çarpan


# Tüm ETF trigger'ları tek dict'te (engine kolay erişsin)
PANIC_ETF_TRIGGERS = {
    'SPY': {
        'type': 'pct',
        'k1': PANIC_SPY_K1_PCT, 'k2': PANIC_SPY_K2_PCT, 'k3': PANIC_SPY_K3_PCT,
        'enabled': True,
    },
    'KRE': {
        'type': 'pct',
        'k1': PANIC_KRE_K1_PCT, 'k2': PANIC_KRE_K2_PCT, 'k3': PANIC_KRE_K3_PCT,
        'enabled': True,
    },
    'IWM': {
        'type': 'pct',
        'k1': PANIC_IWM_K1_PCT, 'k2': PANIC_IWM_K2_PCT, 'k3': PANIC_IWM_K3_PCT,
        'enabled': True,
    },
    'TLT': {
        'type': 'pct',
        'k1': 0, 'k2': 0, 'k3': 0,
        'enabled': False,  # Sadece ETF Guard freeze, panic yok
    },
    'PFF': {
        'type': 'dollar',  # Yüzde değil, dolar bazlı!
        'k1': PANIC_PFF_K1_DOLLAR, 'k2': PANIC_PFF_K2_DOLLAR, 'k3': PANIC_PFF_K3_DOLLAR,
        'enabled': True,
        'hardstop': PFF_HARDSTOP_DOLLAR,
        'hardstop_window': PFF_HARDSTOP_WINDOW_SEC,
    },
}


# ═══════════════════════════════════════════════════════════════
# PANIC — Hedger'dan farklı hard filter kuralları
# Panic modda CGRUP filtresi ve ADV ratio filtresi DEVRE DIŞI
# Sadece: eligible grup + spread ≤ %3
# ═══════════════════════════════════════════════════════════════

PANIC_MAX_SPREAD_PCT = 3.0         # Aynı spread kuralı


# ═══════════════════════════════════════════════════════════════
# CGRUP UTILITIES
# ═══════════════════════════════════════════════════════════════

CGRUP_ORDER = ['c400', 'c425', 'c450', 'c475', 'c500', 'c525', 'c550', 'c575', 'c600', 'c625']

def cgrup_index(cgrup_str: str) -> int:
    """Get numeric index for a CGRUP value. Returns -1 if unknown."""
    if not cgrup_str:
        return -1
    key = cgrup_str.strip().lower()
    try:
        return CGRUP_ORDER.index(key)
    except ValueError:
        return -1

def cgrup_distance(a: str, b: str) -> int:
    """Calculate step distance between two CGRUPs. Returns 999 if either is unknown."""
    ia, ib = cgrup_index(a), cgrup_index(b)
    if ia < 0 or ib < 0:
        return 999
    return abs(ia - ib)


# ═══════════════════════════════════════════════════════════════
# HEDGER TIER SPLIT FUNCTION
# ═══════════════════════════════════════════════════════════════

def hedger_tier_split(drift_pct: float) -> Dict[str, int]:
    """
    L/S yüzde farkına göre tier tercihi.
    K3 (aktif bid vuruş) SADECE %15+ drift'te!

    drift_pct = abs(actual_long_pct - config_long_pct)

    Returns: {'k1': %, 'k2': %, 'k3': %} (sum = 100 or 0)
    """
    d = abs(drift_pct)

    if d < HEDGER_MIN_DRIFT_PCT:
        return {'k1': 0, 'k2': 0, 'k3': 0}  # dengede
    elif d < 5.0:
        return {'k1': 100, 'k2': 0, 'k3': 0}  # sadece pasif
    elif d < 10.0:
        progress = (d - 5.0) / 5.0
        return {
            'k1': int(100 - 60 * progress),   # 100 → 40
            'k2': int(60 * progress),          # 0 → 60
            'k3': 0                            # K3 YOK — %15 altı
        }
    elif d < 15.0:
        progress = (d - 10.0) / 5.0
        return {
            'k1': int(40 - 30 * progress),    # 40 → 10
            'k2': int(60 + 30 * progress),    # 60 → 90
            'k3': 0                            # K3 YOK — %15 altı
        }
    elif d < 20.0:
        progress = (d - 15.0) / 5.0
        return {
            'k1': int(10 - 10 * progress),    # 10 → 0
            'k2': int(90 - 50 * progress),    # 90 → 40
            'k3': int(60 * progress)           # 0 → 60
        }
    else:
        return {'k1': 0, 'k2': 30, 'k3': 70}


def panic_tier_split(tier: str) -> Dict[str, int]:
    """
    Panic execution tier'a göre K2/K3 dağılımı.
    Panic'te K1 emirler fill almaz (ters tarafta spread bekliyorsun).

    Returns: {'k1': %, 'k2': %, 'k3': %} (sum = 100)
    """
    if tier == 'K3':
        return {'k1': 0, 'k2': 0, 'k3': 100}
    elif tier == 'K2':
        return {'k1': 0, 'k2': 40, 'k3': 60}
    elif tier == 'K1':
        return {'k1': 0, 'k2': 70, 'k3': 30}
    else:
        return {'k1': 0, 'k2': 0, 'k3': 0}
