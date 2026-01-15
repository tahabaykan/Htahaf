"""
REDUCEMORE Worker - Multiprocessing worker process için REDUCEMORE implementasyonu

Bu modül ayrı bir process'te çalışır ve UI'ı bloklamaz.
REDUCEMORE, DEFANSIVE veya GEÇIŞ modunda pozisyonları azaltmak için kullanılır.
"""

import os
import time
import logging
from typing import Dict, Any
from multiprocessing import Queue

logger = logging.getLogger(__name__)


def run_reducemore_worker(algorithm_name: str, command_queue: Queue, result_queue: Queue, params: Dict[str, Any]):
    """
    REDUCEMORE algoritması worker process'i
    
    Bu fonksiyon ayrı bir process'te çalışır.
    UI ile iletişim için queue'lar kullanır.
    
    Args:
        algorithm_name: Algoritma adı
        command_queue: UI'dan komut almak için
        result_queue: UI'a sonuç göndermek için
        params: Algoritma parametreleri
    """
    try:
        logger.info(f"[REDUCEMORE_WORKER] ▶️ {algorithm_name} başlatıldı (PID: {os.getpid()})")
        
        # UI'a başlangıç mesajı gönder
        result_queue.put({
            'algorithm_name': algorithm_name,
            'algorithm_type': 'reducemore',
            'event': 'started',
            'message': 'REDUCEMORE başlatıldı',
            'timestamp': time.time()
        })
        
        from_runall = params.get('from_runall', False)
        exposure_mode = params.get('exposure_mode', 'DEFANSIVE')
        
        logger.info(f"[REDUCEMORE_WORKER] Mode: {exposure_mode}, From RUNALL: {from_runall}")
        
        # REDUCEMORE adımları (13 adım - KARBOTU'ya benzer ama pozisyon azaltma için)
        # Şimdilik placeholder - gerçek implementasyon KARBOTU'ya benzer şekilde yapılacak
        
        result_queue.put({
            'algorithm_name': algorithm_name,
            'algorithm_type': 'reducemore',
            'event': 'progress',
            'message': f'REDUCEMORE çalışıyor (Mode: {exposure_mode})...',
            'step': 1,
            'timestamp': time.time()
        })
        
        # TODO: REDUCEMORE adımlarını implement et
        # 1. Take Profit Longs penceresini aç
        # 2-7. Fbtot ve Ask Sell pahalılık kriterlerine göre pozisyonları azalt
        # 8. Take Profit Shorts penceresine geç
        # 9-13. SFStot ve Bid Buy ucuzluk kriterlerine göre pozisyonları azalt
        
        # Şimdilik basit bir bekleme (gerçek implementasyon eklenecek)
        time.sleep(2)
        
        # UI'a tamamlanma mesajı gönder
        result_queue.put({
            'algorithm_name': algorithm_name,
            'algorithm_type': 'reducemore',
            'event': 'completed',
            'message': 'REDUCEMORE tamamlandı',
            'timestamp': time.time()
        })
        
        # RUNALL'dan çağrıldıysa, ADDNEWPOS kontrolü için sinyal gönder
        if from_runall:
            result_queue.put({
                'algorithm_name': algorithm_name,
                'algorithm_type': 'reducemore',
                'event': 'runall_callback',
                'message': 'REDUCEMORE tamamlandı, ADDNEWPOS kontrolü yapılabilir',
                'action': 'check_addnewpos',
                'timestamp': time.time()
            })
        
        logger.info(f"[REDUCEMORE_WORKER] ✅ {algorithm_name} tamamlandı")
        
    except Exception as e:
        logger.error(f"[REDUCEMORE_WORKER] ❌ {algorithm_name} hatası: {e}")
        import traceback
        traceback.print_exc()
        
        # UI'a hata mesajı gönder
        result_queue.put({
            'algorithm_name': algorithm_name,
            'algorithm_type': 'reducemore',
            'event': 'error',
            'message': str(e),
            'timestamp': time.time()
        })









