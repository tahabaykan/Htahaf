"""
KARBOTU Configuration Loader

Manages KARBOTU step filters with save/load functionality.
Compatible with JanallApp filtering system.
"""
import pandas as pd
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
from loguru import logger


@dataclass
class KarbotuStepFilter:
    """Filter configuration for a single KARBOTU step"""
    step: int
    side: str  # LONGS or SHORTS
    enabled: bool
    fbtot_min: float  # FBTOT for LONGS, SFSTOT for SHORTS
    fbtot_max: float
    gort_min: float  # -999 = no filter
    gort_max: float
    sma63chg_min: float  # -999 = no filter
    sma63chg_max: float
    pahalilik_min: float  # ask_sell_pahalilik for LONGS, bid_buy_ucuzluk for SHORTS
    pahalilik_max: float
    lot_percentage: int  # 10-50%


class KarbotuConfig:
    """
    KARBOTU Configuration Manager
    
    Loads/saves step filters from CSV.
    Provides filter lookup by step number and side.
    """
    
    def __init__(self, config_path: str = "config/karbotu_filters.csv"):
        self.config_path = Path(config_path)
        self.filters: List[KarbotuStepFilter] = []
        self.load()
    
    def load(self):
        """Load filters from CSV"""
        try:
            if not self.config_path.exists():
                logger.warning(f"[KarbotuConfig] Config file not found: {self.config_path}")
                self._create_default()
                return
            
            df = pd.read_csv(self.config_path)
            self.filters = []
            
            for _, row in df.iterrows():
                self.filters.append(KarbotuStepFilter(
                    step=int(row['step']),
                    side=str(row['side']),
                    enabled=str(row['enabled']).lower() == 'true',
                    fbtot_min=float(row['fbtot_min']),
                    fbtot_max=float(row['fbtot_max']),
                    gort_min=float(row['gort_min']),
                    gort_max=float(row['gort_max']),
                    sma63chg_min=float(row['sma63chg_min']),
                    sma63chg_max=float(row['sma63chg_max']),
                    pahalilik_min=float(row['pahalilik_min']),
                    pahalilik_max=float(row['pahalilik_max']),
                    lot_percentage=int(row['lot_percentage'])
                ))
            
            logger.info(f"[KarbotuConfig] Loaded {len(self.filters)} step filters from {self.config_path}")
        
        except Exception as e:
            logger.error(f"[KarbotuConfig] Error loading config: {e}", exc_info=True)
            self._create_default()
    
    def save(self):
        """Save filters to CSV"""
        try:
            data = []
            for f in self.filters:
                data.append({
                    'step': f.step,
                    'side': f.side,
                    'enabled': 'true' if f.enabled else 'false',
                    'fbtot_min': f.fbtot_min,
                    'fbtot_max': f.fbtot_max,
                    'gort_min': f.gort_min,
                    'gort_max': f.gort_max,
                    'sma63chg_min': f.sma63chg_min,
                    'sma63chg_max': f.sma63chg_max,
                    'pahalilik_min': f.pahalilik_min,
                    'pahalilik_max': f.pahalilik_max,
                    'lot_percentage': f.lot_percentage
                })
            
            df = pd.DataFrame(data)
            
            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            df.to_csv(self.config_path, index=False)
            logger.info(f"[KarbotuConfig] Saved {len(self.filters)} step filters to {self.config_path}")
        
        except Exception as e:
            logger.error(f"[KarbotuConfig] Error saving config: {e}", exc_info=True)
    
    def get_step_filter(self, step: int, side: str) -> Optional[KarbotuStepFilter]:
        """Get filter for specific step and side"""
        for f in self.filters:
            if f.step == step and f.side == side:
                return f
        return None
    
    def get_enabled_filters(self, side: str) -> List[KarbotuStepFilter]:
        """Get all enabled filters for a side"""
        return [f for f in self.filters if f.side == side and f.enabled]
    
    def _create_default(self):
        """Create default JanallApp-compatible filters
        
        LONG SIDE (Steps 2-7): FBTOT = benchmark skoru, ask_sell_pahalilik = pahalılık
          - Düşük FBTOT + pahalı → sat (agresif)
          - Yüksek FBTOT + pahalı → sat (az)
          - Yüksek FBTOT + ucuz → SATMA (tutmaya değer)
        
        SHORT SIDE (Steps 9-13): SFSTOT = short benchmark skoru, bid_buy_ucuzluk = ucuzluk
          - Ucuzluk negatif = hisse ucuz → cover et (pozisyonu kapat)
          - Ucuzluk pozitif = hisse pahalı → cover ETME (short tutmaya devam)
          - Mantık LONG'un simetriği: LONG'da pahalilik>0 → sat, SHORT'ta ucuzluk<0 → cover
        
        NOT: Step 8 (eski catch-all) KALDIRILDI.
              Her short pozisyonu filtre olmadan geçiriyordu.
        """
        logger.info("[KarbotuConfig] Creating default JanallApp filters")
        
        # ==================================================================
        # LONGS Steps 2-7: SELL kararı (FBTOT + pahalilik bazlı)
        #   FBTOT YÜKSEK = iyi long (tutmak isteriz)
        #   FBTOT DÜŞÜK  = kötü long (satmak isteriz)
        # ==================================================================
        self.filters = [
            # Step 2: FBTOT < 1.10 (KÖTÜ long) + pahalilik >= -0.10
            #   → Zaten kötü hisse, biraz bile pahalıysa agresif sat. %50
            KarbotuStepFilter(2, 'LONGS', True, 0.0, 1.10, -999, 999, -999, 999, -0.10, 999, 50),
            
            # Step 3: FBTOT 1.11-1.45 (ORTA) + pahalilik -0.05...0.04 (hafif pahalı)
            #   → Orta kaliteli hisse, hafif pahalı → küçük satış %25
            KarbotuStepFilter(3, 'LONGS', True, 1.11, 1.45, -999, 999, -999, 999, -0.05, 0.04, 25),
            
            # Step 4: FBTOT 1.11-1.45 (ORTA) + pahalilik >= 0.05 (çok pahalı)
            #   → Orta kaliteli hisse ama çok pahalı → agresif satış %50
            KarbotuStepFilter(4, 'LONGS', True, 1.11, 1.45, -999, 999, -999, 999, 0.05, 999, 50),
            
            # Step 5: FBTOT 1.46-1.85 (İYİ) + pahalilik -0.05...0.02 (hafif pahalı)
            #   → İyi hisse, hafif pahalı → minimal satış %15
            KarbotuStepFilter(5, 'LONGS', True, 1.46, 1.85, -999, 999, -999, 999, -0.05, 0.02, 15),
            
            # Step 6: FBTOT 1.46-1.85 (İYİ) + pahalilik >= 0.03 (pahalı)
            #   → İyi hisse ama pahalı → orta satış %30
            KarbotuStepFilter(6, 'LONGS', True, 1.46, 1.85, -999, 999, -999, 999, 0.03, 999, 30),
            
            # Step 7: FBTOT 1.86-2.10 (HARİKA long) + pahalilik >= 0.10
            #   → Harika hisse, en az 10 cent pahalıysa minimal sat %15
            #   → Yüksek eşik: bu hisseyi gerçekten tutmak istiyoruz
            KarbotuStepFilter(7, 'LONGS', True, 1.86, 2.10, -999, 999, -999, 999, 0.10, 999, 15),
            
            # ==================================================================
            # SHORTS Steps 9-14: BUY (cover) kararı (SFSTOT + ucuzluk bazlı)
            #
            # ÇAPRAZ SİMETRİ:
            #   SFSTOT YÜKSEK = kötü short (hisse yükselmiş) → kolay cover
            #   SFSTOT DÜŞÜK  = iyi short (hisse düşmüş)    → zor cover
            #
            #   FBTOT 0-1.10    (KÖTÜ long)   ↔  SFSTOT 1.70+     (KÖTÜ short)   Step 2↔9
            #   FBTOT 1.11-1.45 (ORTA long)   ↔  SFSTOT 1.40-1.69 (ORTA short)   Step 3/4↔10/11
            #   FBTOT 1.46-1.85 (İYİ long)    ↔  SFSTOT 1.10-1.39 (İYİ short)    Step 5/6↔12/13
            #   FBTOT 1.86-2.10 (HARİKA long) ↔  SFSTOT 0-1.10    (HARİKA short) Step 7↔14
            #
            #   NOT: Step 8 (catch-all) KALDIRILDI!
            # ==================================================================
            
            # Step 9: SFSTOT >= 1.70 (KÖTÜ short) + ucuzluk <= 0.10
            #   → Short kâr etmemiş/zarar ediyor, biraz ucuzsa agresif cover %50
            #   (Çapraz simetri: Step 2 → FBTOT<1.10, pahalilik>=-0.10)
            KarbotuStepFilter(9, 'SHORTS', True, 1.70, 999, -999, 999, -999, 999, -999, 0.10, 50),
            
            # Step 10: SFSTOT 1.40-1.69 (ORTA short) + ucuzluk -0.04...0.05 (hafif ucuz)
            #   → Orta short skoru, hafif ucuz → küçük cover %25
            #   (Çapraz simetri: Step 3 → pahalilik -0.05...0.04)
            KarbotuStepFilter(10, 'SHORTS', True, 1.40, 1.69, -999, 999, -999, 999, -0.04, 0.05, 25),
            
            # Step 11: SFSTOT 1.40-1.69 (ORTA short) + ucuzluk <= -0.05 (çok ucuz)
            #   → Orta short skoru + çok ucuz → agresif cover %50
            #   (Çapraz simetri: Step 4 → pahalilik>=0.05)
            KarbotuStepFilter(11, 'SHORTS', True, 1.40, 1.69, -999, 999, -999, 999, -999, -0.05, 50),
            
            # Step 12: SFSTOT 1.10-1.39 (İYİ short) + ucuzluk -0.02...0.05 (hafif ucuz)
            #   → İyi short, hafif ucuz → minimal cover %15
            #   (Çapraz simetri: Step 5 → pahalilik -0.05...0.02)
            KarbotuStepFilter(12, 'SHORTS', True, 1.10, 1.39, -999, 999, -999, 999, -0.02, 0.05, 15),
            
            # Step 13: SFSTOT 1.10-1.39 (İYİ short) + ucuzluk <= -0.03 (ucuz)
            #   → İyi short ama ucuz → orta cover %30
            #   (Çapraz simetri: Step 6 → pahalilik>=0.03)
            KarbotuStepFilter(13, 'SHORTS', True, 1.10, 1.39, -999, 999, -999, 999, -999, -0.03, 30),
            
            # Step 14: SFSTOT < 1.10 (HARİKA short) + ucuzluk <= -0.10
            #   → Mükemmel short, en az 10 cent ucuzsa minimal cover %15
            #   → Yüksek eşik: bu short'u gerçekten tutmak istiyoruz
            #   (Çapraz simetri: Step 7 → FBTOT 1.86-2.10, pahalilik>=0.10)
            KarbotuStepFilter(14, 'SHORTS', True, 0.0, 1.10, -999, 999, -999, 999, -999, -0.10, 15),
        ]
        
        self.save()


# Global instance
_karbotu_config = None

def get_karbotu_config() -> KarbotuConfig:
    """Get global KARBOTU config instance"""
    global _karbotu_config
    if _karbotu_config is None:
        _karbotu_config = KarbotuConfig()
    return _karbotu_config


def reload_karbotu_config():
    """Reload config from disk"""
    global _karbotu_config
    _karbotu_config = KarbotuConfig()
    return _karbotu_config
