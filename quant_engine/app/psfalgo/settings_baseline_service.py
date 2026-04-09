"""
Settings Baseline Service
=========================

Captures the current state of ALL user-configurable settings as a "baseline default".
When the user clicks "Reset to Default", the system restores this baseline
and returns a diff report showing what changed.

Baseline is saved to: config/settings_baseline.json
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from app.core.logger import logger


def _config_dir() -> Path:
    return Path(__file__).parent.parent / "config"


def _baseline_path() -> Path:
    return _config_dir() / "settings_baseline.json"


class SettingsBaselineService:
    """
    Captures and restores settings baselines.
    
    Usage:
        svc = get_settings_baseline_service()
        svc.capture_baseline()          # Save current state as the default
        diff = svc.reset_to_baseline()  # Restore and get change report
    """

    def __init__(self):
        self._baseline: Optional[Dict] = None
        self._load_baseline()

    def _load_baseline(self):
        """Load baseline from JSON file if it exists."""
        path = _baseline_path()
        try:
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    self._baseline = json.load(f)
                logger.info(f"[BASELINE] Loaded baseline from {path} (captured: {self._baseline.get('captured_at', '?')})")
            else:
                logger.info("[BASELINE] No baseline file found — use capture_baseline() to create one")
        except Exception as e:
            logger.error(f"[BASELINE] Failed to load baseline: {e}")

    def has_baseline(self) -> bool:
        return self._baseline is not None

    # ─── CAPTURE ──────────────────────────────────────────────────────────

    def capture_baseline(self) -> Dict:
        """
        Snapshot ALL current settings and save as baseline.
        This becomes the 'factory default' that reset restores to.
        """
        snapshot = {
            'captured_at': datetime.now().isoformat(),
            'heavy': self._read_heavy_settings(),
            'active_engines': self._read_active_engines(),
            'mm_settings': self._read_mm_settings(),
            'exposure_thresholds': self._read_exposure_thresholds(),
            'addnewpos': self._read_addnewpos_settings(),
        }

        # Save to file
        path = _baseline_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)

        self._baseline = snapshot
        logger.info(f"[BASELINE] ✅ Baseline captured at {snapshot['captured_at']}")
        return snapshot

    # ─── RESET ────────────────────────────────────────────────────────────

    def reset_to_baseline(self, category: Optional[str] = None) -> Dict:
        """
        Restore settings from baseline. Returns diff report.
        
        Args:
            category: Optional - 'heavy', 'active_engines', 'mm_settings', 
                      'exposure_thresholds', 'addnewpos', or None for ALL.
        
        Returns:
            {
                'success': True,
                'changes': [
                    {'category': 'heavy', 'account': 'HAMPRO', 'field': 'heavy_lot_pct', 'from': 50, 'to': 30},
                    ...
                ],
                'total_changes': int,
                'message': str
            }
        """
        if not self._baseline:
            return {
                'success': False,
                'changes': [],
                'total_changes': 0,
                'message': 'No baseline captured yet. Call capture_baseline() first.'
            }

        all_changes: List[Dict] = []

        categories = [category] if category else ['heavy', 'active_engines', 'mm_settings', 'exposure_thresholds', 'addnewpos']

        for cat in categories:
            if cat == 'heavy':
                changes = self._reset_heavy()
                all_changes.extend(changes)
            elif cat == 'active_engines':
                changes = self._reset_active_engines()
                all_changes.extend(changes)
            elif cat == 'mm_settings':
                changes = self._reset_mm_settings()
                all_changes.extend(changes)
            elif cat == 'exposure_thresholds':
                changes = self._reset_exposure_thresholds()
                all_changes.extend(changes)
            elif cat == 'addnewpos':
                changes = self._reset_addnewpos()
                all_changes.extend(changes)

        if all_changes:
            msg = f"🔄 Reset {len(all_changes)} settings to baseline ({self._baseline.get('captured_at', '?')})"
        else:
            msg = "✅ All settings already match baseline — no changes needed"

        logger.info(f"[BASELINE] {msg}")
        return {
            'success': True,
            'changes': all_changes,
            'total_changes': len(all_changes),
            'message': msg,
            'baseline_captured_at': self._baseline.get('captured_at')
        }

    def get_current_vs_baseline(self) -> Dict:
        """
        Compare current settings vs baseline WITHOUT changing anything.
        Returns the diff report.
        """
        if not self._baseline:
            return {'success': False, 'message': 'No baseline captured'}

        all_changes: List[Dict] = []
        
        # Compare HEAVY
        current_heavy = self._read_heavy_settings()
        baseline_heavy = self._baseline.get('heavy', {})
        for acc_id in set(list(current_heavy.keys()) + list(baseline_heavy.keys())):
            cur = current_heavy.get(acc_id, {})
            base = baseline_heavy.get(acc_id, {})
            for field in set(list(cur.keys()) + list(base.keys())):
                if cur.get(field) != base.get(field):
                    all_changes.append({
                        'category': 'heavy', 'account': acc_id,
                        'field': field, 'current': cur.get(field), 'baseline': base.get(field)
                    })

        # Compare Active Engines
        cur_engines = sorted(self._read_active_engines())
        base_engines = sorted(self._baseline.get('active_engines', []))
        if cur_engines != base_engines:
            all_changes.append({
                'category': 'active_engines', 'account': 'global',
                'field': 'active_engines', 'current': cur_engines, 'baseline': base_engines
            })

        # Compare MM
        cur_mm = self._read_mm_settings()
        base_mm = self._baseline.get('mm_settings', {})
        for field in set(list(cur_mm.keys()) + list(base_mm.keys())):
            if cur_mm.get(field) != base_mm.get(field):
                all_changes.append({
                    'category': 'mm_settings', 'account': 'global',
                    'field': field, 'current': cur_mm.get(field), 'baseline': base_mm.get(field)
                })

        # Compare Exposure thresholds
        cur_exp = self._read_exposure_thresholds()
        base_exp = self._baseline.get('exposure_thresholds', {})
        for acc_id in set(list(cur_exp.get('accounts', {}).keys()) + list(base_exp.get('accounts', {}).keys())):
            cur_acc = cur_exp.get('accounts', {}).get(acc_id, {})
            base_acc = base_exp.get('accounts', {}).get(acc_id, {})
            for field in set(list(cur_acc.keys()) + list(base_acc.keys())):
                if cur_acc.get(field) != base_acc.get(field):
                    all_changes.append({
                        'category': 'exposure', 'account': acc_id,
                        'field': field, 'current': cur_acc.get(field), 'baseline': base_acc.get(field)
                    })

        return {
            'success': True,
            'drift_count': len(all_changes),
            'drifts': all_changes,
            'baseline_captured_at': self._baseline.get('captured_at')
        }

    # ─── READ HELPERS ─────────────────────────────────────────────────────

    def _read_heavy_settings(self) -> Dict:
        try:
            from app.core.redis_client import get_redis
            r = get_redis()
            result = {}
            for acc in ['HAMPRO', 'IBKR_PED', 'IBKR_MAIN']:
                key = f'psfalgo:heavy_settings:{acc}'
                raw = r.get(key) if r else None
                if raw:
                    result[acc] = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                else:
                    result[acc] = {
                        'heavy_long_dec': False, 'heavy_short_dec': False,
                        'heavy_lot_pct': 30, 'heavy_long_threshold': 0.02,
                        'heavy_short_threshold': -0.02
                    }
            return result
        except Exception as e:
            logger.error(f"[BASELINE] Read heavy error: {e}")
            return {}

    def _read_active_engines(self) -> List[str]:
        try:
            from app.core.redis_client import get_redis
            r = get_redis()
            if r:
                raw = r.get('psfalgo:active_engines')
                if raw:
                    return json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            return ['LT_TRIM', 'KARBOTU', 'PATADD_ENGINE', 'ADDNEWPOS_ENGINE', 'MM_ENGINE']
        except Exception as e:
            logger.error(f"[BASELINE] Read active_engines error: {e}")
            return ['LT_TRIM', 'KARBOTU', 'PATADD_ENGINE', 'ADDNEWPOS_ENGINE', 'MM_ENGINE']

    def _read_mm_settings(self) -> Dict:
        try:
            mm_path = _config_dir() / "mm_xnl_settings.json"
            if mm_path.exists():
                with open(mm_path, 'r') as f:
                    data = json.load(f)
                # Ensure lot_mode is present
                if 'lot_mode' not in data:
                    data['lot_mode'] = 'fixed'
                return data
            return {
                'enabled': True, 'est_cur_ratio': 44.0,
                'min_stock_count': 5, 'max_stock_count': 100,
                'lot_per_stock': 200, 'lot_mode': 'fixed'
            }
        except Exception as e:
            logger.error(f"[BASELINE] Read MM error: {e}")
            return {}

    def _read_exposure_thresholds(self) -> Dict:
        try:
            path = _config_dir() / "exposure_thresholds_v2.json"
            if path.exists():
                with open(path, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"[BASELINE] Read exposure error: {e}")
            return {}

    def _read_addnewpos_settings(self) -> Dict:
        try:
            from app.core.redis_client import get_redis
            r = get_redis()
            result = {}
            for acc in ['HAMPRO', 'IBKR_PED', 'IBKR_MAIN']:
                key = f'psfalgo:addnewpos_settings:{acc}'
                raw = r.get(key) if r else None
                if raw:
                    result[acc] = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                else:
                    result[acc] = None
            return result
        except Exception as e:
            logger.error(f"[BASELINE] Read addnewpos error: {e}")
            return {}

    # ─── RESET HELPERS ────────────────────────────────────────────────────

    def _reset_heavy(self) -> List[Dict]:
        changes = []
        baseline_heavy = self._baseline.get('heavy', {})
        current_heavy = self._read_heavy_settings()
        
        try:
            from app.xnl.heavy_settings_store import get_heavy_settings_store
            store = get_heavy_settings_store()
            
            for acc_id, base_settings in baseline_heavy.items():
                cur = current_heavy.get(acc_id, {})
                diffs = {}
                for field, base_val in base_settings.items():
                    if cur.get(field) != base_val:
                        changes.append({
                            'category': 'heavy', 'account': acc_id,
                            'field': field, 'from': cur.get(field), 'to': base_val
                        })
                        diffs[field] = base_val
                if diffs:
                    store.update_settings(acc_id, diffs)
        except Exception as e:
            logger.error(f"[BASELINE] Reset heavy error: {e}")
        return changes

    def _reset_active_engines(self) -> List[Dict]:
        changes = []
        base_engines = self._baseline.get('active_engines', [])
        cur_engines = self._read_active_engines()
        
        if sorted(cur_engines) != sorted(base_engines):
            changes.append({
                'category': 'active_engines', 'account': 'global',
                'field': 'active_engines', 'from': cur_engines, 'to': base_engines
            })
            try:
                from app.core.redis_client import get_redis
                r = get_redis()
                if r:
                    r.set('psfalgo:active_engines', json.dumps(base_engines))
                # Also update running engine if possible
                try:
                    from app.psfalgo.runall_state_api import get_runall_state_api
                    state_api = get_runall_state_api()
                    if state_api and state_api.runall_engine:
                        state_api.runall_engine.active_engines = base_engines
                except:
                    pass
            except Exception as e:
                logger.error(f"[BASELINE] Reset active_engines error: {e}")
        return changes

    def _reset_mm_settings(self) -> List[Dict]:
        changes = []
        base_mm = self._baseline.get('mm_settings', {})
        cur_mm = self._read_mm_settings()
        
        diffs = {}
        for field, base_val in base_mm.items():
            if cur_mm.get(field) != base_val:
                changes.append({
                    'category': 'mm_settings', 'account': 'global',
                    'field': field, 'from': cur_mm.get(field), 'to': base_val
                })
                diffs[field] = base_val
        
        if diffs:
            try:
                from app.xnl.mm_settings import get_mm_settings_store
                store = get_mm_settings_store()
                store.update_settings(base_mm)  # Overwrite with full baseline
            except Exception as e:
                logger.error(f"[BASELINE] Reset MM error: {e}")
        return changes

    def _reset_exposure_thresholds(self) -> List[Dict]:
        changes = []
        base_exp = self._baseline.get('exposure_thresholds', {})
        cur_exp = self._read_exposure_thresholds()
        
        base_accounts = base_exp.get('accounts', {})
        cur_accounts = cur_exp.get('accounts', {})

        any_change = False
        for acc_id in set(list(base_accounts.keys()) + list(cur_accounts.keys())):
            base_acc = base_accounts.get(acc_id, {})
            cur_acc = cur_accounts.get(acc_id, {})
            for field in set(list(base_acc.keys()) + list(cur_acc.keys())):
                if base_acc.get(field) != cur_acc.get(field):
                    changes.append({
                        'category': 'exposure', 'account': acc_id,
                        'field': field, 'from': cur_acc.get(field), 'to': base_acc.get(field)
                    })
                    any_change = True

        if any_change:
            try:
                path = _config_dir() / "exposure_thresholds_v2.json"
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(base_exp, f, indent=2)
                # Reload in-memory service
                try:
                    from app.psfalgo.exposure_threshold_service_v2 import get_exposure_threshold_service_v2
                    svc = get_exposure_threshold_service_v2()
                    svc._load()
                except:
                    pass
            except Exception as e:
                logger.error(f"[BASELINE] Reset exposure error: {e}")
        return changes

    def _reset_addnewpos(self) -> List[Dict]:
        changes = []
        base_addnewpos = self._baseline.get('addnewpos', {})
        cur_addnewpos = self._read_addnewpos_settings()

        try:
            from app.core.redis_client import get_redis
            r = get_redis()
            
            for acc_id, base_val in base_addnewpos.items():
                cur_val = cur_addnewpos.get(acc_id)
                if base_val != cur_val:
                    if base_val is None:
                        # Delete from Redis
                        key = f'psfalgo:addnewpos_settings:{acc_id}'
                        if r:
                            r.delete(key)
                        changes.append({
                            'category': 'addnewpos', 'account': acc_id,
                            'field': 'all', 'from': '(was set)', 'to': '(cleared)'
                        })
                    else:
                        # Write baseline value
                        key = f'psfalgo:addnewpos_settings:{acc_id}'
                        if r:
                            r.set(key, json.dumps(base_val))
                        changes.append({
                            'category': 'addnewpos', 'account': acc_id,
                            'field': 'all', 'from': '(changed)', 'to': '(baseline restored)'
                        })
        except Exception as e:
            logger.error(f"[BASELINE] Reset addnewpos error: {e}")
        return changes


# ── Global Singleton ──
_baseline_service: Optional[SettingsBaselineService] = None


def get_settings_baseline_service() -> SettingsBaselineService:
    global _baseline_service
    if _baseline_service is None:
        _baseline_service = SettingsBaselineService()
    return _baseline_service
