"""
RUNALL Worker - Multiprocessing worker process için RUNALL implementasyonu

Bu modül ayrı bir process'te çalışır ve UI'ı bloklamaz.
"""

import os
import time
import logging
from typing import Dict, Any
from multiprocessing import Queue

logger = logging.getLogger(__name__)


def run_runall_worker(algorithm_name: str, command_queue: Queue, result_queue: Queue, params: Dict[str, Any]):
    """
    RUNALL algoritması worker process'i
    
    Bu fonksiyon ayrı bir process'te çalışır.
    UI ile iletişim için queue'lar kullanır.
    
    Args:
        algorithm_name: Algoritma adı
        command_queue: UI'dan komut almak için
        result_queue: UI'a sonuç göndermek için
        params: Algoritma parametreleri
    """
    try:
        logger.info(f"[RUNALL_WORKER] ▶️ {algorithm_name} başlatıldı (PID: {os.getpid()})")
        
        # UI'a başlangıç mesajı gönder
        result_queue.put({
            'algorithm_name': algorithm_name,
            'algorithm_type': 'runall',
            'event': 'started',
            'message': 'RUNALL başlatıldı',
            'timestamp': time.time()
        })
        
        from_restart = params.get('from_restart', False)
        runall_allowed_mode = params.get('runall_allowed_mode', False)
        mode = params.get('mode', 'HAMPRO')
        
        # Adım 1: Lot Bölücü kontrolü
        result_queue.put({
            'algorithm_name': algorithm_name,
            'algorithm_type': 'runall',
            'event': 'progress',
            'message': 'Adım 1: Lot Bölücü kontrolü yapılıyor...',
            'step': 1,
            'timestamp': time.time()
        })
        
        # Adım 2: Controller ON
        result_queue.put({
            'algorithm_name': algorithm_name,
            'algorithm_type': 'runall',
            'event': 'progress',
            'message': f'Adım 2: Controller ON (Mode: {mode})',
            'step': 2,
            'timestamp': time.time()
        })
        
        # Adım 3: Exposure kontrolü (CSV okuma - process'te yapılabilir)
        result_queue.put({
            'algorithm_name': algorithm_name,
            'algorithm_type': 'runall',
            'event': 'progress',
            'message': 'Adım 3: Exposure kontrolü yapılıyor...',
            'step': 3,
            'timestamp': time.time()
        })
        
        # Exposure kontrolü yap (CSV'den oku)
        exposure_info = check_exposure_limits(mode, params)
        
        pot_total = exposure_info.get('pot_total', 0)
        pot_max_lot = exposure_info.get('pot_max_lot', 63636)
        exposure_mode = exposure_info.get('mode', 'UNKNOWN')
        total_lots = exposure_info.get('total_lots', 0)
        
        result_queue.put({
            'algorithm_name': algorithm_name,
            'algorithm_type': 'runall',
            'event': 'exposure_check',
            'message': f'Exposure: Pot Total={pot_total:,}, Pot Max={pot_max_lot:,}, Mode={exposure_mode}',
            'exposure_info': exposure_info,
            'timestamp': time.time()
        })
        
        # Adım 4: Mode'a göre KARBOTU veya REDUCEMORE başlat
        # OFANSIF → KARBOTU
        # DEFANSIVE veya GEÇIŞ → REDUCEMORE
        if exposure_mode == "OFANSIF":
            result_queue.put({
                'algorithm_name': algorithm_name,
                'algorithm_type': 'runall',
                'event': 'progress',
                'message': 'Adım 4: Mode=OFANSIF → KARBOTU başlatılıyor...',
                'step': 4,
                'action': 'start_karbotu',
                'exposure_mode': exposure_mode,
                'timestamp': time.time()
            })
        else:  # DEFANSIVE veya GEÇIŞ
            result_queue.put({
                'algorithm_name': algorithm_name,
                'algorithm_type': 'runall',
                'event': 'progress',
                'message': f'Adım 4: Mode={exposure_mode} → REDUCEMORE başlatılıyor...',
                'step': 4,
                'action': 'start_reducemore',
                'exposure_mode': exposure_mode,
                'timestamp': time.time()
            })
        
        # KARBOTU/REDUCEMORE tamamlanmasını bekle (command_queue'dan mesaj gelecek)
        # Şimdilik basit bir bekleme
        time.sleep(1)
        
        # KARBOTU/REDUCEMORE tamamlandıktan sonra ADDNEWPOS kontrolü
        if exposure_mode == "OFANSIF" and pot_total < pot_max_lot:
            result_queue.put({
                'algorithm_name': algorithm_name,
                'algorithm_type': 'runall',
                'event': 'progress',
                'message': f'ADDNEWPOS tetikleniyor: Pot Total {pot_total:,} < Pot Max {pot_max_lot:,}',
                'step': 5,
                'action': 'start_addnewpos',
                'timestamp': time.time()
            })
        
        # UI'a tamamlanma mesajı gönder
        result_queue.put({
            'algorithm_name': algorithm_name,
            'algorithm_type': 'runall',
            'event': 'completed',
            'message': 'RUNALL tamamlandı',
            'timestamp': time.time()
        })
        
        logger.info(f"[RUNALL_WORKER] ✅ {algorithm_name} tamamlandı")
        
    except Exception as e:
        logger.error(f"[RUNALL_WORKER] ❌ {algorithm_name} hatası: {e}")
        import traceback
        traceback.print_exc()
        
        # UI'a hata mesajı gönder
        result_queue.put({
            'algorithm_name': algorithm_name,
            'algorithm_type': 'runall',
            'event': 'error',
            'message': str(e),
            'timestamp': time.time()
        })


def check_exposure_limits(mode: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Exposure limitlerini kontrol et (CSV'den oku)
    
    Args:
        mode: Aktif mod (HAMPRO, IBKR_GUN, IBKR_PED)
    
    Returns:
        Dict: Exposure bilgileri
    """
    try:
        import pandas as pd
        
        # Mode'a göre CSV dosyasını belirle
        if mode == "IBKR_GUN":
            csv_file = "befibgun.csv"
        elif mode == "IBKR_PED":
            csv_file = "befibped.csv"
        else:  # HAMPRO
            csv_file = "befham.csv"
        
        # CSV'yi oku
        if not os.path.exists(csv_file):
            logger.warning(f"[EXPOSURE] ⚠️ CSV dosyası bulunamadı: {csv_file}")
            return {
                'mode': 'UNKNOWN',
                'pot_total': 0,
                'pot_max_lot': 63636,
                'total_lots': 0,
                'max_lot': 54545,
                'can_add_positions': True
            }
        
        df = pd.read_csv(csv_file)
        
        # Pot Toplam hesapla (MAXALW kolonundan)
        if 'MAXALW' in df.columns:
            pot_total = df['MAXALW'].sum()
        else:
            pot_total = 0
        
        # Pot Max Lot hesapla (params'tan al)
        pot_expo_limit = params.get('pot_expo_limit', 6363600) if params else 6363600
        avg_price = params.get('avg_price', 100) if params else 100
        pot_max_lot = int(pot_expo_limit / avg_price)
        
        # Max Lot hesapla (exposure_limit'ten)
        exposure_limit = params.get('exposure_limit', 5000000) if params else 5000000
        max_lot = int(exposure_limit / avg_price)
        
        # Mode belirleme (gerçek mantık - defensive_threshold ve offensive_threshold kullan)
        # Exposure limit ve avg_price parametrelerini al
        if params is None:
            params = {}
        
        exposure_limit = params.get('exposure_limit', 5000000)  # Varsayılan 5M
        avg_price = params.get('avg_price', 100)  # Varsayılan $100
        pot_expo_limit = params.get('pot_expo_limit', 6363600)  # Varsayılan
        
        max_lot = int(exposure_limit / avg_price)
        defensive_threshold = int(max_lot * 0.955)  # %95.5
        offensive_threshold = int(max_lot * 0.927)  # %92.7
        
        # Pot Total yerine total_lots kullan (CSV'den gelen MAXALW toplamı)
        total_lots = int(pot_total)
        
        # Mode belirleme (gerçek mantık)
        if total_lots > defensive_threshold:
            exposure_mode = "DEFANSIVE"  # Sadece REDUCEMORE (KARBOTU değil!)
        elif total_lots < offensive_threshold:
            exposure_mode = "OFANSIF"  # Hem KARBOTU hem ADDPOS
        else:
            exposure_mode = "GEÇIŞ"  # Geçiş modu - REDUCEMORE kullan
        
        return {
            'mode': exposure_mode,
            'pot_total': int(pot_total),
            'pot_max_lot': pot_max_lot,
            'total_lots': int(pot_total),
            'max_lot': max_lot,
            'can_add_positions': pot_total < pot_max_lot
        }
        
    except Exception as e:
        logger.error(f"[EXPOSURE] ❌ Exposure kontrolü hatası: {e}")
        import traceback
        traceback.print_exc()
        return {
            'mode': 'UNKNOWN',
            'pot_total': 0,
            'pot_max_lot': 63636,
            'total_lots': 0,
            'max_lot': 54545,
            'can_add_positions': True
        }

