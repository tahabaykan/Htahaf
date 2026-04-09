"""
Free Exposure Engine
====================

Hesap bazlı "boş kapasite" hesaplayarak MM lot boyutlarını dinamik ayarlar.

Kavramlar:
  free_cur = max_cur_exp - current_exposure   (mevcut boş alan)
  free_pot = max_pot_exp - potential_exposure  (potansiyel boş alan)
  effective_free_pct = min(free_cur_pct, free_pot_pct)

Kademe tablosu (effective_free_pct → AVG_ADV böleni):
  ≥50%  → /30   (cömert)
  40-49 → /40
  30-39 → /50
  20-29 → /60
  10-19 → /70
  5-9   → /100  (sıkışık)
  <5%   → BLOCKED (increase yasak)

Her lot hesabı:
  raw = AVG_ADV / divisor
  lot = max(200, round_down_100(raw))
"""

from typing import Optional, Dict, Tuple
from app.core.logger import logger


# ── Kademe Tablosu ──
# (min_free_pct, adv_divisor)   — None divisor = BLOCKED
TIERS = [
    (50,  30),
    (40,  40),
    (30,  50),
    (20,  60),
    (10,  70),
    (5,  100),
    (0,  None),   # < 5% → BLOCKED
]

MIN_LOT = 200


def _round_down_100(val: float) -> int:
    """100'e aşağı yuvarlama."""
    return max(0, int(val // 100) * 100)


def _tier_for_pct(free_pct: float) -> Tuple[Optional[int], str]:
    """
    Free exposure yüzdesinden kademe bilgisi döndür.
    
    Returns:
        (divisor, label)  — divisor=None → BLOCKED
    """
    for min_pct, divisor in TIERS:
        if free_pct >= min_pct:
            if divisor is None:
                return None, f"BLOCKED (free={free_pct:.1f}% < 5%)"
            return divisor, f"free={free_pct:.1f}% → ADV/{divisor}"
    return None, f"BLOCKED (free={free_pct:.1f}%)"


class FreeExposureEngine:
    """
    Hesap bazlı free exposure hesaplayıp MM lot limiti belirler.
    
    Kullanım:
        engine = get_free_exposure_engine()
        lot = await engine.get_mm_lot_for_symbol(account_id, symbol)
        # lot = 0 ise INCREASE YASAK
    """

    def __init__(self):
        self._cache: Dict[str, dict] = {}  # account_id → son hesaplanan snapshot
        logger.info("[FREE_EXPOSURE] Engine initialized")

    async def calculate_free_exposure(self, account_id: str) -> Dict:
        """
        Hesap için free exposure yüzdelerini hesapla.
        
        Returns:
            {
                'account_id': str,
                'max_cur': float,      # max current exposure ($)
                'max_pot': float,      # max potential exposure ($)
                'current': float,      # mevcut exposure ($)
                'potential': float,    # potansiyel exposure ($)
                'free_cur': float,     # boş current ($)
                'free_pot': float,     # boş potential ($)
                'free_cur_pct': float, # boş current (%)
                'free_pot_pct': float, # boş potential (%)
                'effective_free_pct': float,  # min(cur, pot) (%)
                'divisor': int | None, # ADV böleni (None=BLOCKED)
                'tier_label': str,     # kademe açıklaması
                'blocked': bool,       # True ise increase yasak
            }
        """
        try:
            from app.psfalgo.exposure_calculator import get_current_and_potential_exposure_pct
            from app.psfalgo.exposure_threshold_service_v2 import get_exposure_threshold_service_v2

            # 1. Mevcut ve potansiyel exposure hesapla
            exposure, current_pct, potential_pct = await get_current_and_potential_exposure_pct(account_id)

            if not exposure or exposure.pot_max <= 0:
                logger.warning(f"[FREE_EXPOSURE] {account_id}: No exposure data")
                return self._blocked_result(account_id, "No exposure data")

            # 2. Threshold servisinden max limitleri al
            thresh_svc = get_exposure_threshold_service_v2()
            thresholds = thresh_svc.get_thresholds(account_id)

            pot_max = thresholds['pot_max']              # $1,400,000
            cur_threshold_pct = thresholds['current_threshold']   # 92.0
            pot_threshold_pct = thresholds['potential_threshold'] # 100.0

            # 3. Max değerleri hesapla ($)
            max_cur = pot_max * (cur_threshold_pct / 100.0)   # $1,288,000
            max_pot = pot_max * (pot_threshold_pct / 100.0)   # $1,400,000

            # 4. Mevcut değerleri hesapla ($)
            current_dollars = exposure.pot_total
            potential_dollars = current_dollars * (potential_pct / current_pct) if current_pct > 0 else current_dollars

            # 5. Free hesapla
            free_cur = max(0, max_cur - current_dollars)
            free_pot = max(0, max_pot - potential_dollars)

            # 6. Free yüzde (maksimum kapasitenin yüzdesi olarak)
            free_cur_pct = (free_cur / max_cur * 100.0) if max_cur > 0 else 0.0
            free_pot_pct = (free_pot / max_pot * 100.0) if max_pot > 0 else 0.0

            # 7. Bağlayıcı kural: minimum olan geçerli
            effective_free_pct = min(free_cur_pct, free_pot_pct)

            # 8. Kademe belirle
            divisor, tier_label = _tier_for_pct(effective_free_pct)

            result = {
                'account_id': account_id,
                'max_cur': round(max_cur, 0),
                'max_pot': round(max_pot, 0),
                'current': round(current_dollars, 0),
                'potential': round(potential_dollars, 0),
                'free_cur': round(free_cur, 0),
                'free_pot': round(free_pot, 0),
                'free_cur_pct': round(free_cur_pct, 1),
                'free_pot_pct': round(free_pot_pct, 1),
                'effective_free_pct': round(effective_free_pct, 1),
                'divisor': divisor,
                'adv_divisor': divisor,  # alias for UI
                'tier_label': tier_label,
                'blocked': divisor is None,
            }

            # Cache
            self._cache[account_id] = result

            logger.info(
                f"[FREE_EXPOSURE] {account_id}: "
                f"cur=${current_dollars:,.0f}/{max_cur:,.0f} "
                f"(free={free_cur_pct:.1f}%) | "
                f"pot=${potential_dollars:,.0f}/{max_pot:,.0f} "
                f"(free={free_pot_pct:.1f}%) | "
                f"effective={effective_free_pct:.1f}% → {tier_label}"
            )

            return result

        except Exception as e:
            logger.error(f"[FREE_EXPOSURE] {account_id}: Error: {e}", exc_info=True)
            return self._blocked_result(account_id, str(e))

    def get_cached_snapshot(self, account_id: str) -> Optional[Dict]:
        """Son hesaplanan free exposure snapshot'ını döndür (cache'den)."""
        return self._cache.get(account_id)

    async def get_mm_lot_for_symbol(
        self,
        account_id: str,
        symbol: str,
        avg_adv: Optional[float] = None,
        use_cache: bool = True,
    ) -> int:
        """
        Bir hisse için MM INCREASE lot boyutunu hesapla.
        
        Args:
            account_id: Hesap ID
            symbol: Hisse sembolü
            avg_adv: AVG_ADV değeri (None ise DataFabric'ten alınır)
            use_cache: True ise önceki free exposure hesabını kullan
            
        Returns:
            lot: 100'e yuvarlanmış lot (0 = BLOCKED, min 200)
        """
        # 1. Free exposure snapshot al
        snapshot = self._cache.get(account_id) if use_cache else None
        if not snapshot:
            snapshot = await self.calculate_free_exposure(account_id)

        if snapshot.get('blocked'):
            logger.debug(f"[FREE_EXPOSURE] {account_id}/{symbol}: BLOCKED — increase yasak")
            return 0

        divisor = snapshot['divisor']
        if divisor is None:
            return 0

        # 2. AVG_ADV al
        if avg_adv is None:
            avg_adv = self._get_avg_adv(symbol)

        if avg_adv is None or avg_adv <= 0:
            logger.debug(f"[FREE_EXPOSURE] {symbol}: No AVG_ADV — default {MIN_LOT}")
            return MIN_LOT

        # 3. Lot hesapla
        raw_lot = avg_adv / divisor
        lot = _round_down_100(raw_lot)
        lot = max(MIN_LOT, lot)

        logger.debug(
            f"[FREE_EXPOSURE] {account_id}/{symbol}: "
            f"ADV={avg_adv:.0f} / {divisor} = {raw_lot:.0f} → lot={lot} "
            f"(free={snapshot['effective_free_pct']:.1f}%)"
        )

        return lot

    def get_mm_lot_sync(
        self,
        account_id: str,
        symbol: str,
        avg_adv: Optional[float] = None,
    ) -> int:
        """
        Senkron versiyon — sadece cache kullanır.
        Cache yoksa MIN_LOT (200) döndürür.
        """
        snapshot = self._cache.get(account_id)
        if not snapshot:
            return MIN_LOT

        if snapshot.get('blocked'):
            return 0

        divisor = snapshot.get('divisor')
        if divisor is None:
            return 0

        if avg_adv is None:
            avg_adv = self._get_avg_adv(symbol)

        if avg_adv is None or avg_adv <= 0:
            return MIN_LOT

        raw_lot = avg_adv / divisor
        lot = _round_down_100(raw_lot)
        return max(MIN_LOT, lot)

    def _get_avg_adv(self, symbol: str) -> Optional[float]:
        """DataFabric'ten AVG_ADV al."""
        try:
            from app.core.data_fabric import get_data_fabric
            fabric = get_data_fabric()
            if fabric:
                snap = fabric.get_fast_snapshot(symbol)
                if snap:
                    adv = snap.get('AVG_ADV')
                    if adv is not None:
                        return float(adv)
        except Exception:
            pass
        return None

    def _blocked_result(self, account_id: str, reason: str) -> Dict:
        """Hata/veri yok durumunda BLOCKED sonuç döndür."""
        return {
            'account_id': account_id,
            'max_cur': 0, 'max_pot': 0,
            'current': 0, 'potential': 0,
            'free_cur': 0, 'free_pot': 0,
            'free_cur_pct': 0.0, 'free_pot_pct': 0.0,
            'effective_free_pct': 0.0,
            'divisor': None,
            'tier_label': f"BLOCKED ({reason})",
            'blocked': True,
        }

    def get_status_summary(self) -> Dict:
        """Tüm hesapların durumunu döndür (API/UI için)."""
        return {
            account_id: {
                'effective_free_pct': snap['effective_free_pct'],
                'free_cur_pct': snap['free_cur_pct'],
                'free_pot_pct': snap['free_pot_pct'],
                'divisor': snap['divisor'],
                'tier_label': snap['tier_label'],
                'blocked': snap['blocked'],
            }
            for account_id, snap in self._cache.items()
        }


# ── Global Singleton ──
_free_exposure_engine: Optional[FreeExposureEngine] = None


def get_free_exposure_engine() -> FreeExposureEngine:
    """Get or create global FreeExposureEngine instance."""
    global _free_exposure_engine
    if _free_exposure_engine is None:
        _free_exposure_engine = FreeExposureEngine()
    return _free_exposure_engine
