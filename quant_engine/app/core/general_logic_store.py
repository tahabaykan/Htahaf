"""
General Logic Store - QE General Logic Formulas
Stores in qegenerallogic.csv - All configurable formula parameters
Based on exact specifications from user
"""

import os
import csv
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from threading import Lock

logger = logging.getLogger(__name__)

# Singleton instance
_general_logic_store: Optional['GeneralLogicStore'] = None
_store_lock = Lock()


def get_general_logic_store() -> 'GeneralLogicStore':
    """Get or create the singleton GeneralLogicStore instance."""
    global _general_logic_store
    with _store_lock:
        if _general_logic_store is None:
            _general_logic_store = GeneralLogicStore()
        return _general_logic_store


class GeneralLogicStore:
    """
    Central store for all configurable formula parameters.
    Reads from qegenerallogic.csv on startup and provides access to all engines.
    """
    
    # ══════════════════════════════════════════════════════════════════════════════
    # DEFAULT VALUES - These are the "Reset Default" values
    # ══════════════════════════════════════════════════════════════════════════════
    DEFAULT_CONFIG: Dict[str, Any] = {
        
        # ══════════════════════════════════════════════════════════════════════════
        # 2️⃣ EXPOSURE MODU & THRESHOLD'LAR
        # ══════════════════════════════════════════════════════════════════════════
        "exposure.defensive_threshold_percent": 95.5,       # DEFANSIF mod başlangıcı
        "exposure.offensive_threshold_percent": 92.7,       # OFANSIF mod başlangıcı
        "exposure.transition_mode": "REDUCEMORE",           # GEÇİŞ modunda hangi engine çalışır
        "exposure.default_exposure_limit": 1400000,         # Varsayılan pot_max ($1.4M)
        "exposure.pot_expo_limit": 1400000,                 # Pot exposure limiti
        
        # ══════════════════════════════════════════════════════════════════════════
        # 3️⃣ KARBOTU ENGINE - KÂR ALMA MOTORU
        # ══════════════════════════════════════════════════════════════════════════
        
        # 3.2 GORT Filtresi (Ön Filtre)
        "karbotu.gort_filter_longs.enabled": False,
        "karbotu.gort_filter_longs.gort_gt": -1,
        "karbotu.gort_filter_longs.ask_sell_pahalilik_gt": -0.05,
        "karbotu.gort_filter_shorts.enabled": False,
        "karbotu.gort_filter_shorts.gort_lt": 1,
        "karbotu.gort_filter_shorts.bid_buy_ucuzluk_lt": 0.05,
        
        # 3.3 LONG Pozisyonlar İçin Adımlar (Step 2-7)
        # Step 2: Fbtot < 1.10 → %50 sat
        "karbotu.step_2.enabled": True,
        "karbotu.step_2.side": "LONGS",
        "karbotu.step_2.fbtot_lt": 1.10,
        "karbotu.step_2.ask_sell_pahalilik_gt": -0.10,
        "karbotu.step_2.qty_ge": 100,
        "karbotu.step_2.lot_percentage": 50,
        "karbotu.step_2.order_type": "ASK_SELL",
        
        # Step 3: Fbtot 1.11-1.45 (Low Range) → %25 sat
        "karbotu.step_3.enabled": True,
        "karbotu.step_3.side": "LONGS",
        "karbotu.step_3.fbtot_gte": 1.11,
        "karbotu.step_3.fbtot_lte": 1.45,
        "karbotu.step_3.ask_sell_pahalilik_gte": -0.05,
        "karbotu.step_3.ask_sell_pahalilik_lte": 0.04,
        "karbotu.step_3.qty_ge": 100,
        "karbotu.step_3.lot_percentage": 25,
        
        # Step 4: Fbtot 1.11-1.45 (High Range) → %50 sat
        "karbotu.step_4.enabled": True,
        "karbotu.step_4.side": "LONGS",
        "karbotu.step_4.fbtot_gte": 1.11,
        "karbotu.step_4.fbtot_lte": 1.45,
        "karbotu.step_4.ask_sell_pahalilik_gt": 0.05,
        "karbotu.step_4.lot_percentage": 50,
        
        # Step 5: Fbtot 1.46-1.85 (Low Range) → %25 sat
        "karbotu.step_5.enabled": True,
        "karbotu.step_5.side": "LONGS",
        "karbotu.step_5.fbtot_gte": 1.46,
        "karbotu.step_5.fbtot_lte": 1.85,
        "karbotu.step_5.ask_sell_pahalilik_gte": 0.05,
        "karbotu.step_5.ask_sell_pahalilik_lte": 0.10,
        "karbotu.step_5.lot_percentage": 25,
        
        # Step 6: Fbtot 1.46-1.85 (High Range) → %50 sat
        "karbotu.step_6.enabled": True,
        "karbotu.step_6.side": "LONGS",
        "karbotu.step_6.fbtot_gte": 1.46,
        "karbotu.step_6.fbtot_lte": 1.85,
        "karbotu.step_6.ask_sell_pahalilik_gt": 0.10,
        "karbotu.step_6.lot_percentage": 50,
        
        # Step 7: Fbtot 1.86-2.10 → %25 sat
        "karbotu.step_7.enabled": True,
        "karbotu.step_7.side": "LONGS",
        "karbotu.step_7.fbtot_gte": 1.86,
        "karbotu.step_7.fbtot_lte": 2.10,
        "karbotu.step_7.ask_sell_pahalilik_gt": 0.20,
        "karbotu.step_7.lot_percentage": 25,
        
        # 3.4 SHORT Pozisyonlar İçin Adımlar (Step 9-13)
        # Step 9: SFStot > 1.70 → %50 cover
        "karbotu.step_9.enabled": True,
        "karbotu.step_9.side": "SHORTS",
        "karbotu.step_9.sfstot_gt": 1.70,
        "karbotu.step_9.bid_buy_ucuzluk_lt": 0.10,
        "karbotu.step_9.lot_percentage": 50,
        "karbotu.step_9.order_type": "BID_BUY",
        
        # Step 10: SFStot 1.40-1.69 (Low) → %25 cover
        "karbotu.step_10.enabled": True,
        "karbotu.step_10.side": "SHORTS",
        "karbotu.step_10.sfstot_gte": 1.40,
        "karbotu.step_10.sfstot_lte": 1.69,
        "karbotu.step_10.bid_buy_ucuzluk_gte": -0.04,
        "karbotu.step_10.bid_buy_ucuzluk_lte": 0.05,
        "karbotu.step_10.lot_percentage": 25,
        
        # Step 11: SFStot 1.40-1.69 (High) → %50 cover
        "karbotu.step_11.enabled": True,
        "karbotu.step_11.side": "SHORTS",
        "karbotu.step_11.sfstot_gte": 1.40,
        "karbotu.step_11.sfstot_lte": 1.69,
        "karbotu.step_11.bid_buy_ucuzluk_lt": -0.05,
        "karbotu.step_11.lot_percentage": 50,
        
        # Step 12: SFStot 1.10-1.39 (Low) → %25 cover
        "karbotu.step_12.enabled": True,
        "karbotu.step_12.side": "SHORTS",
        "karbotu.step_12.sfstot_gte": 1.10,
        "karbotu.step_12.sfstot_lte": 1.39,
        "karbotu.step_12.bid_buy_ucuzluk_gte": -0.04,
        "karbotu.step_12.bid_buy_ucuzluk_lte": 0.05,
        "karbotu.step_12.lot_percentage": 25,
        
        # Step 13: SFStot 1.10-1.39 (High) → %50 cover
        "karbotu.step_13.enabled": True,
        "karbotu.step_13.side": "SHORTS",
        "karbotu.step_13.sfstot_gte": 1.10,
        "karbotu.step_13.sfstot_lte": 1.39,
        "karbotu.step_13.bid_buy_ucuzluk_lt": -0.05,
        "karbotu.step_13.lot_percentage": 50,
        
        # 3.6 KARBOTU Ayarlar
        "karbotu.settings.min_lot_size": 100,
        "karbotu.settings.cooldown_minutes": 5,
        "karbotu.settings.process_longs_first": True,
        "karbotu.settings.exclude_fbtot_zero": True,
        "karbotu.settings.exclude_sfstot_zero": True,
        "karbotu.settings.sweep_threshold": 200,            # Kalan < 200 ise tamamını sat
        
        # ══════════════════════════════════════════════════════════════════════════
        # 4️⃣ REDUCEMORE ENGINE - RİSK AZALTMA MOTORU
        # ══════════════════════════════════════════════════════════════════════════
        
        # 4.2 Eligibility
        "reducemore.eligibility.exposure_ratio_threshold": 0.8,    # Exposure >= %80 ise çalış
        "reducemore.eligibility.pot_total_multiplier": 0.9,        # pot_total > pot_max * 0.9
        "reducemore.eligibility.modes": ["DEFANSIF", "GECIS"],
        
        # 4.3 Adımlar (KARBOTU ile Aynı ama Daha Agresif)
        "reducemore.step_2.lot_percentage": 75,    # KARBOTU'da %50
        "reducemore.step_3.lot_percentage": 50,    # KARBOTU'da %25
        "reducemore.step_4.lot_percentage": 75,    # KARBOTU'da %50
        
        # 4.4 Multiplier Sistemi
        "reducemore.base_multiplier": 1.0,
        "reducemore.high_exposure_multiplier": 1.5,   # %50 daha agresif
        
        # ══════════════════════════════════════════════════════════════════════════
        # 5️⃣ LT TRIM ENGINE - EXECUTION MOTORU
        # ══════════════════════════════════════════════════════════════════════════
        
        # 5.2 4-Stage Befday Model
        "lt_trim.stage_1_score": 0.00,    # Spread Gating (Loose Trim)
        "lt_trim.stage_2_score": 0.10,    # Score >= 0.10
        "lt_trim.stage_3_score": 0.20,    # Score >= 0.20
        "lt_trim.stage_4_score": 0.40,    # Score >= 0.40
        
        # 5.3 Spread Threshold Tabloları - LONG İçin
        "lt_trim.long_spread_thresholds": [
            [0.06, 0.08],   # Spread >= $0.06 → Score >= 0.08 gerekli
            [0.10, 0.05],   # Spread >= $0.10 → Score >= 0.05 gerekli
            [0.15, 0.02],   # Spread >= $0.15 → Score >= 0.02 gerekli
            [0.25, 0.00],   # Spread >= $0.25 → Score >= 0.00 gerekli
            [0.45, -0.02],  # Spread >= $0.45 → Score >= -0.02 tolere edilir
            [10.0, -0.08]   # Extreme → Score >= -0.08 max tolerans
        ],
        
        # 5.3 Spread Threshold Tabloları - SHORT İçin
        "lt_trim.short_spread_thresholds": [
            [0.06, -0.08],
            [0.10, -0.05],
            [0.15, -0.02],
            [0.25, 0.00],
            [0.45, 0.02],
            [10.0, 0.08]
        ],
        
        # 5.4 Trim Lot Hesaplama
        "lt_trim.step_size_pct": 20.0,           # Her stage 1 flag = %20 trim
        "lt_trim.max_daily_trim_pct": 80.0,      # Max günlük %80
        "lt_trim.min_sell_qty": 200,             # Min 200 lot
        "lt_trim.round_to": 100,                 # 100'e yuvarla
        
        # 5.5 Küçük Pozisyon Mantığı (< 400 lot)
        "lt_trim.small_position_threshold": 400,
        "lt_trim.small_position_stage2_qty": 200,
        
        # 5.6 Hidden Price Hesaplama
        "lt_trim.spread_factor": 0.15,           # Spread × 0.15
        
        # ══════════════════════════════════════════════════════════════════════════
        # 6️⃣ ADDNEWPOS ENGINE - YENİ POZİSYON MOTORU
        # ══════════════════════════════════════════════════════════════════════════
        
        # 6.2 Eligibility
        "addnewpos.eligibility.exposure_mode": "OFANSIF",
        
        # 6.3 AddLong / AddShort Filtreleri
        "addnewpos.addlong.enabled": True,
        "addnewpos.addlong.order_type": "BID_BUY",
        "addnewpos.addlong.filters_disabled": True,
        
        "addnewpos.addshort.enabled": True,
        "addnewpos.addshort.order_type": "ASK_SELL",
        "addnewpos.addshort.filters_disabled": True,
        
        # Orijinal Filtreler (Devre Dışı) - AddLong
        "addnewpos.filters.addlong.bid_buy_ucuzluk_lt": -0.02,
        "addnewpos.filters.addlong.fbtot_gt": 1.10,
        "addnewpos.filters.addlong.spread_lt": 0.25,
        "addnewpos.filters.addlong.avg_adv_gt": 500,
        
        # Orijinal Filtreler (Devre Dışı) - AddShort
        "addnewpos.filters.addshort.ask_sell_pahalilik_gt": 0.02,
        "addnewpos.filters.addshort.sfstot_gt": 1.10,
        
        # 6.4 Portfolio Rules (Lot Hesaplama)
        "addnewpos.rules.thresholds": [
            {"max_portfolio_percent": 1, "maxalw_multiplier": 0.50, "portfolio_percent": 5},
            {"max_portfolio_percent": 3, "maxalw_multiplier": 0.40, "portfolio_percent": 4},
            {"max_portfolio_percent": 5, "maxalw_multiplier": 0.30, "portfolio_percent": 3},
            {"max_portfolio_percent": 7, "maxalw_multiplier": 0.20, "portfolio_percent": 2},
            {"max_portfolio_percent": 10, "maxalw_multiplier": 0.10, "portfolio_percent": 1.5},
            {"max_portfolio_percent": 100, "maxalw_multiplier": 0.05, "portfolio_percent": 1}
        ],
        "addnewpos.rules.exposure_usage_percent": 60,
        
        # 6.5 Ayarlar
        "addnewpos.settings.max_lot_per_symbol": 999999,
        "addnewpos.settings.default_lot": 200,
        "addnewpos.settings.min_lot_size": 200,
        "addnewpos.settings.cooldown_minutes": 0,
        "addnewpos.settings.min_avg_adv_divisor": 10,
        "addnewpos.settings.mode": "both",    # addlong_only / addshort_only / both
        
        # ══════════════════════════════════════════════════════════════════════════
        # 7️⃣ MM ENGINE - MARKET MAKING MOTORU
        # ══════════════════════════════════════════════════════════════════════════
        
        # 7.2 Çalışma Koşulları
        "mm.min_spread": 0.06,              # Spread çok dar ise MM yapmıyor
        "mm.min_score": 30.0,               # MM_MIN_SCORE
        "mm.max_score": 250.0,              # MM_MAX_SCORE
        
        # ══════════════════════════════════════════════════════════════════════════
        # 8️⃣ JFIN ENGINE - TUM CSV SEÇİCİ
        # ══════════════════════════════════════════════════════════════════════════
        
        # 8.2 Selection Rules
        "jfin.tumcsv.selection_percent": 0.10,         # %10 seçim
        "jfin.tumcsv.min_selection": 2,                # Min 2 hisse
        "jfin.tumcsv.heldkuponlu_pair_count": 16,      # HELDKUPONLU grubundan 16 adet
        "jfin.tumcsv.long_percent": 25.0,              # En iyi %25 LONG için
        "jfin.tumcsv.long_multiplier": 1.5,            # Ortalama × 1.5 üzeri
        "jfin.tumcsv.short_percent": 25.0,             # En kötü %25 SHORT için
        "jfin.tumcsv.short_multiplier": 0.7,           # Ortalama × 0.7 altı
        "jfin.tumcsv.max_short": 3,                    # Grup başına max SHORT
        "jfin.tumcsv.company_limit_enabled": True,
        "jfin.tumcsv.company_limit_divisor": 1.6,      # max = total / 1.6
        
        # 8.3 Lot Dağıtım Formülü
        "jfin.lot_distribution.alpha": 3,                   # Dağılım katsayısı
        "jfin.lot_distribution.total_long_rights": 28000,   # Toplam LONG hakkı
        "jfin.lot_distribution.total_short_rights": 12000,  # Toplam SHORT hakkı
        "jfin.lot_distribution.lot_rounding": 100,          # 100'e yuvarla
        
        # 8.4 CGRUP Seçim Kuralları (HELDKUPONLU Özel)
        "jfin.cgrup.special_cgrups": ["C600", "C625", "C650"],   # Özel grup - 0 veya daha fazla olabilir
        "jfin.cgrup.min_per_cgrup": 2,                           # Diğer CGRUP'lardan min 2 adet
        
        # ══════════════════════════════════════════════════════════════════════════
        # 9️⃣ PROPOSAL & APPROVAL AKIŞI
        # ══════════════════════════════════════════════════════════════════════════
        
        # 9.3 Hidden Price Formülü
        "proposal.spread_factor": 0.15,      # Spread × 0.15
        
        # ══════════════════════════════════════════════════════════════════════════
        # 🔟 RISK REGİMELERİ
        # ══════════════════════════════════════════════════════════════════════════
        
        # 10.1 Soft/Hard Derisk
        "risk.soft_derisk.threshold_pct": 120.0,              # %120 exposure'da başlar
        "risk.soft_derisk.addnewpos_step_multiplier": 0.25,   # ADDNEWPOS step %25'e düşer
        "risk.soft_derisk.engines_throttled": ["ADDNEWPOS"],
        
        "risk.hard_derisk.threshold_pct": 130.0,              # %130 exposure'da başlar
        "risk.hard_derisk.cancel_risk_increasing": True,      # Risk artıran emirleri iptal et
        "risk.hard_derisk.only_reduce_positions": True,       # Sadece pozisyon azalt
        
        # 10.2 Order Lifecycle (TTL)
        "order_lifecycle.ttl.LT_TRIM": 120,           # 2 dakika
        "order_lifecycle.ttl.MM_CHURN": 60,           # 1 dakika
        "order_lifecycle.ttl.ADDNEWPOS": 180,         # 3 dakika
        "order_lifecycle.ttl.KARBOTU": 120,
        "order_lifecycle.ttl.REDUCEMORE": 90,
        "order_lifecycle.ttl.HARD_DERISK": 30,        # Acil
        "order_lifecycle.ttl.CLOSE_EXIT": 15,         # Çok acil
        
        "order_lifecycle.min_replace_interval_seconds": 2.5,
        "order_lifecycle.price_change_threshold_cents": 1,
    }
    
    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._csv_path = Path(os.getcwd()) / 'qegenerallogic.csv'
        self._lock = Lock()
        self._load_config()
    
    def _load_config(self):
        """Load config from CSV or use defaults."""
        with self._lock:
            # Start with defaults
            self._config = dict(self.DEFAULT_CONFIG)
            
            # Try to load from CSV
            if self._csv_path.exists():
                try:
                    with open(self._csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            key = row.get('key', '').strip()
                            value_str = row.get('value', '').strip()
                            value_type = row.get('type', 'string').strip()
                            
                            if key and value_str:
                                try:
                                    if value_type == 'json' or value_str.startswith('[') or value_str.startswith('{'):
                                        value = json.loads(value_str)
                                    elif value_type == 'float':
                                        value = float(value_str)
                                    elif value_type == 'int':
                                        value = int(value_str)
                                    elif value_type == 'bool':
                                        value = value_str.lower() in ('true', '1', 'yes')
                                    else:
                                        value = value_str
                                    
                                    self._config[key] = value
                                except (json.JSONDecodeError, ValueError) as e:
                                    logger.warning(f"Failed to parse config value for {key}: {e}")
                    
                    logger.info(f"✅ Loaded {len(self._config)} general logic parameters from CSV")
                except Exception as e:
                    logger.error(f"❌ Failed to load general logic CSV: {e}")
            else:
                # Create default CSV
                self._save_config()
                logger.info("📝 Created default qegenerallogic.csv")
    
    def _save_config(self):
        """Save current config to CSV."""
        try:
            with open(self._csv_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['key', 'value', 'type', 'description'])
                
                descriptions = self._get_descriptions()
                
                for key, value in sorted(self._config.items()):
                    if isinstance(value, (list, dict)):
                        value_str = json.dumps(value)
                        value_type = 'json'
                    elif isinstance(value, bool):
                        value_str = str(value).lower()
                        value_type = 'bool'
                    elif isinstance(value, float):
                        value_str = str(value)
                        value_type = 'float'
                    elif isinstance(value, int):
                        value_str = str(value)
                        value_type = 'int'
                    else:
                        value_str = str(value)
                        value_type = 'string'
                    
                    desc = descriptions.get(key, '')
                    writer.writerow([key, value_str, value_type, desc])
            
            logger.info(f"✅ Saved general logic config to {self._csv_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to save general logic CSV: {e}")
            return False
    
    def _get_descriptions(self) -> Dict[str, str]:
        """Get human-readable descriptions for each parameter."""
        return {
            # Exposure
            "exposure.defensive_threshold_percent": "DEFANSIF mod başlangıcı (%)",
            "exposure.offensive_threshold_percent": "OFANSIF mod başlangıcı (%)",
            "exposure.transition_mode": "GEÇİŞ modunda hangi engine çalışır",
            "exposure.default_exposure_limit": "Varsayılan pot_max ($)",
            "exposure.pot_expo_limit": "Pot exposure limiti ($)",
            
            # Karbotu
            "karbotu.step_2.fbtot_lt": "Step 2: Fbtot < X",
            "karbotu.step_2.lot_percentage": "Step 2: Sat yüzdesi (%)",
            
            # LT Trim
            "lt_trim.long_spread_thresholds": "LONG Spread-Score tablosu",
            "lt_trim.short_spread_thresholds": "SHORT Spread-Score tablosu",
            "lt_trim.max_daily_trim_pct": "Günlük max trim yüzdesi (%)",
            "lt_trim.spread_factor": "Hidden price spread faktörü",
            
            # ADDNEWPOS
            "addnewpos.rules.exposure_usage_percent": "Kalan exposure'ın kullanım yüzdesi",
            "addnewpos.settings.min_lot_size": "Minimum lot miktarı",
            
            # JFIN
            "jfin.tumcsv.heldkuponlu_pair_count": "HELDKUPONLU seçilecek adet",
            "jfin.lot_distribution.total_long_rights": "Toplam LONG lot hakkı",
            "jfin.lot_distribution.total_short_rights": "Toplam SHORT lot hakkı",
            
            # Risk
            "risk.soft_derisk.threshold_pct": "Soft derisk başlangıcı (%)",
            "risk.hard_derisk.threshold_pct": "Hard derisk başlangıcı (%)",
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value by key."""
        with self._lock:
            return self._config.get(key, default)
    
    def get_all(self) -> Dict[str, Any]:
        """Get all config values."""
        with self._lock:
            return dict(self._config)
    
    def get_with_descriptions(self) -> Dict[str, Dict[str, Any]]:
        """Get all config values with descriptions for UI."""
        with self._lock:
            descriptions = self._get_descriptions()
            result = {}
            for key, value in self._config.items():
                result[key] = {
                    'value': value,
                    'description': descriptions.get(key, ''),
                    'type': self._get_type_name(value)
                }
            return result
    
    def _get_type_name(self, value: Any) -> str:
        """Get type name for a value."""
        if isinstance(value, list):
            return 'json'
        elif isinstance(value, dict):
            return 'json'
        elif isinstance(value, bool):
            return 'bool'
        elif isinstance(value, float):
            return 'float'
        elif isinstance(value, int):
            return 'int'
        else:
            return 'string'
    
    def set(self, key: str, value: Any) -> bool:
        """Set a config value."""
        with self._lock:
            self._config[key] = value
            return True
    
    def update(self, updates: Dict[str, Any]) -> bool:
        """Update multiple config values and save."""
        with self._lock:
            for key, value in updates.items():
                self._config[key] = value
            return self._save_config()
    
    def reset_to_defaults(self) -> bool:
        """Reset all values to defaults and save."""
        with self._lock:
            self._config = dict(self.DEFAULT_CONFIG)
            return self._save_config()
    
    def save(self) -> bool:
        """Save current config to CSV."""
        with self._lock:
            return self._save_config()
    
    # ══════════════════════════════════════════════════════════════════════════════
    # CONVENIENCE METHODS FOR ENGINES
    # ══════════════════════════════════════════════════════════════════════════════
    
    def get_long_spread_thresholds(self) -> List[Tuple[float, float]]:
        """Get LONG spread thresholds as list of tuples."""
        data = self.get("lt_trim.long_spread_thresholds", [])
        return [(float(row[0]), float(row[1])) for row in data]
    
    def get_short_spread_thresholds(self) -> List[Tuple[float, float]]:
        """Get SHORT spread thresholds as list of tuples."""
        data = self.get("lt_trim.short_spread_thresholds", [])
        return [(float(row[0]), float(row[1])) for row in data]


# Initialize on import
def init_general_logic_store():
    """Initialize the general logic store."""
    return get_general_logic_store()
