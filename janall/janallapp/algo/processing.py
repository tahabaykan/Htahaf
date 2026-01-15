"""
Algo Processing Module - Multiprocessing için algoritma işlemleri

Bu modül RUNALL, KARBOTU, ADDNEWPOS, Qpcal gibi algoritmik işlemleri
ayrı process'lerde çalıştırarak UI'ı bloklamaz.
"""

import multiprocessing
from multiprocessing import Process, Queue, Manager
import queue
import time
import os
import logging
from typing import Dict, Any, Optional, Callable

logger = logging.getLogger(__name__)

# Global process states (worker process'lerde kullanılmak üzere)
_process_states = None

def set_process_states(states_dict):
    """Worker process'lerde kullanılmak üzere process states dict'ini set et"""
    global _process_states
    _process_states = states_dict


class AlgoProcessor:
    """
    Algoritma işlemlerini multiprocessing ile yöneten sınıf
    
    UI thread'inden bağımsız olarak çalışır, queue'lar üzerinden iletişim kurar.
    """
    
    def __init__(self, ui_command_queue: Queue, ui_result_queue: Queue):
        """
        Args:
            ui_command_queue: UI'dan process'e komut göndermek için
            ui_result_queue: Process'ten UI'a sonuç göndermek için
        """
        self.ui_command_queue = ui_command_queue
        self.ui_result_queue = ui_result_queue
        
        # Process yönetimi
        self.processes: Dict[str, Process] = {}
        self.process_queues: Dict[str, Queue] = {}
        self.process_manager = Manager()
        
        # Process durumları (shared dict)
        self.process_states = self.process_manager.dict()
        
        # Çalışan algoritma process'leri
        self.running_algorithms = self.process_manager.dict()
        
        logger.info("[ALGO_PROCESSOR] ✅ AlgoProcessor başlatıldı")
    
    def start_algorithm(self, algorithm_name: str, algorithm_type: str, params: Dict[str, Any]) -> bool:
        """
        Bir algoritma process'ini başlat
        
        Args:
            algorithm_name: Algoritma adı (örn: "runall_1", "karbotu_1")
            algorithm_type: Algoritma tipi ("runall", "karbotu", "addnewpos", "qpcal")
            params: Algoritma parametreleri (dict)
        
        Returns:
            bool: Başarılı ise True
        """
        try:
            # Eğer aynı isimde bir process zaten çalışıyorsa durdur
            if algorithm_name in self.processes:
                if self.processes[algorithm_name].is_alive():
                    logger.warning(f"[ALGO_PROCESSOR] ⚠️ {algorithm_name} zaten çalışıyor, durduruluyor...")
                    self.stop_algorithm(algorithm_name)
            
            # Process için queue oluştur
            process_queue = Queue()
            self.process_queues[algorithm_name] = process_queue
            
            # Process state'i başlat
            self.process_states[algorithm_name] = {
                'status': 'starting',
                'algorithm_type': algorithm_type,
                'start_time': time.time(),
                'params': params
            }
            
            # Algoritma tipine göre process başlat
            if algorithm_type == "runall":
                process = Process(
                    target=self._run_runall_worker,
                    args=(algorithm_name, process_queue, self.ui_result_queue, params),
                    daemon=True
                )
            elif algorithm_type == "karbotu":
                process = Process(
                    target=self._run_karbotu_worker,
                    args=(algorithm_name, process_queue, self.ui_result_queue, params),
                    daemon=True
                )
            elif algorithm_type == "reducemore":
                process = Process(
                    target=self._run_reducemore_worker,
                    args=(algorithm_name, process_queue, self.ui_result_queue, params),
                    daemon=True
                )
            elif algorithm_type == "addnewpos":
                process = Process(
                    target=self._run_addnewpos_worker,
                    args=(algorithm_name, process_queue, self.ui_result_queue, params),
                    daemon=True
                )
            elif algorithm_type == "qpcal":
                process = Process(
                    target=self._run_qpcal_worker,
                    args=(algorithm_name, process_queue, self.ui_result_queue, params),
                    daemon=True
                )
            else:
                logger.error(f"[ALGO_PROCESSOR] ❌ Bilinmeyen algoritma tipi: {algorithm_type}")
                return False
            
            # Process'i başlat
            process.start()
            self.processes[algorithm_name] = process
            
            # Running algorithms'a ekle
            self.running_algorithms[algorithm_name] = {
                'type': algorithm_type,
                'start_time': time.time(),
                'params': params
            }
            
            logger.info(f"[ALGO_PROCESSOR] ✅ {algorithm_name} ({algorithm_type}) başlatıldı (PID: {process.pid})")
            return True
            
        except Exception as e:
            logger.error(f"[ALGO_PROCESSOR] ❌ {algorithm_name} başlatma hatası: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def stop_algorithm(self, algorithm_name: str) -> bool:
        """
        Bir algoritma process'ini durdur
        
        Args:
            algorithm_name: Durdurulacak algoritma adı
        
        Returns:
            bool: Başarılı ise True
        """
        try:
            if algorithm_name not in self.processes:
                logger.warning(f"[ALGO_PROCESSOR] ⚠️ {algorithm_name} bulunamadı")
                return False
            
            process = self.processes[algorithm_name]
            
            # Process'e durdurma komutu gönder
            if algorithm_name in self.process_queues:
                try:
                    self.process_queues[algorithm_name].put({'command': 'stop'}, timeout=1)
                except queue.Full:
                    pass
            
            # Process'i bekle (maksimum 5 saniye)
            process.join(timeout=5)
            
            # Hala çalışıyorsa zorla sonlandır
            if process.is_alive():
                logger.warning(f"[ALGO_PROCESSOR] ⚠️ {algorithm_name} zorla sonlandırılıyor...")
                process.terminate()
                process.join(timeout=2)
                if process.is_alive():
                    process.kill()
            
            # Temizlik
            del self.processes[algorithm_name]
            if algorithm_name in self.process_queues:
                del self.process_queues[algorithm_name]
            if algorithm_name in self.process_states:
                del self.process_states[algorithm_name]
            if algorithm_name in self.running_algorithms:
                del self.running_algorithms[algorithm_name]
            
            logger.info(f"[ALGO_PROCESSOR] ✅ {algorithm_name} durduruldu")
            return True
            
        except Exception as e:
            logger.error(f"[ALGO_PROCESSOR] ❌ {algorithm_name} durdurma hatası: {e}")
            return False
    
    def is_algorithm_running(self, algorithm_name: str) -> bool:
        """Bir algoritmanın çalışıp çalışmadığını kontrol et"""
        if algorithm_name not in self.processes:
            return False
        return self.processes[algorithm_name].is_alive()
    
    def get_algorithm_status(self, algorithm_name: str) -> Optional[Dict[str, Any]]:
        """Bir algoritmanın durumunu al"""
        if algorithm_name not in self.process_states:
            return None
        return dict(self.process_states[algorithm_name])
    
    def get_all_running_algorithms(self) -> Dict[str, Dict[str, Any]]:
        """Tüm çalışan algoritmaları döndür"""
        # Ölü process'leri temizle
        dead_processes = []
        for name, process in self.processes.items():
            if not process.is_alive():
                dead_processes.append(name)
        
        for name in dead_processes:
            logger.info(f"[ALGO_PROCESSOR] 🧹 Ölü process temizleniyor: {name}")
            if name in self.processes:
                del self.processes[name]
            if name in self.process_queues:
                del self.process_queues[name]
            if name in self.process_states:
                del self.process_states[name]
            if name in self.running_algorithms:
                del self.running_algorithms[name]
        
        return dict(self.running_algorithms)
    
    def stop_all_algorithms(self):
        """Tüm algoritmaları durdur"""
        algorithm_names = list(self.processes.keys())
        for name in algorithm_names:
            self.stop_algorithm(name)
        logger.info("[ALGO_PROCESSOR] ✅ Tüm algoritmalar durduruldu")
    
    # ==================== WORKER FUNCTIONS ====================
    
    def _run_runall_worker(self, algorithm_name: str, command_queue: Queue, result_queue: Queue, params: Dict[str, Any]):
        """
        RUNALL algoritması worker process'i
        
        Bu fonksiyon ayrı bir process'te çalışır.
        UI ile iletişim için queue'lar kullanır.
        """
        # runall_worker modülünden import et
        from .runall_worker import run_runall_worker
        run_runall_worker(algorithm_name, command_queue, result_queue, params)
    
    def _run_karbotu_worker(self, algorithm_name: str, command_queue: Queue, result_queue: Queue, params: Dict[str, Any]):
        """KARBOTU algoritması worker process'i"""
        # karbotu_worker modülünden import et (henüz oluşturulmadı, placeholder)
        # from .karbotu_worker import run_karbotu_worker
        # run_karbotu_worker(algorithm_name, command_queue, result_queue, params)
        
        # Şimdilik placeholder
        try:
            logger.info(f"[KARBOTU_WORKER] ▶️ {algorithm_name} başlatıldı (PID: {os.getpid()})")
            
            result_queue.put({
                'algorithm_name': algorithm_name,
                'algorithm_type': 'karbotu',
                'event': 'started',
                'message': 'KARBOTU başlatıldı',
                'timestamp': time.time()
            })
            
            # TODO: KARBOTU işlemlerini buraya taşı
            
        except Exception as e:
            logger.error(f"[KARBOTU_WORKER] ❌ {algorithm_name} hatası: {e}")
            result_queue.put({
                'algorithm_name': algorithm_name,
                'algorithm_type': 'karbotu',
                'event': 'error',
                'message': str(e),
                'timestamp': time.time()
            })
    
    def _run_reducemore_worker(self, algorithm_name: str, command_queue: Queue, result_queue: Queue, params: Dict[str, Any]):
        """REDUCEMORE algoritması worker process'i"""
        from .reducemore_worker import run_reducemore_worker
        run_reducemore_worker(algorithm_name, command_queue, result_queue, params)
    
    def _run_addnewpos_worker(self, algorithm_name: str, command_queue: Queue, result_queue: Queue, params: Dict[str, Any]):
        """ADDNEWPOS algoritması worker process'i"""
        try:
            logger.info(f"[ADDNEWPOS_WORKER] ▶️ {algorithm_name} başlatıldı (PID: {os.getpid()})")
            
            # TODO: ADDNEWPOS işlemlerini buraya taşı
            
            result_queue.put({
                'algorithm_name': algorithm_name,
                'algorithm_type': 'addnewpos',
                'event': 'started',
                'message': 'ADDNEWPOS başlatıldı',
                'timestamp': time.time()
            })
            
        except Exception as e:
            logger.error(f"[ADDNEWPOS_WORKER] ❌ {algorithm_name} hatası: {e}")
            result_queue.put({
                'algorithm_name': algorithm_name,
                'algorithm_type': 'addnewpos',
                'event': 'error',
                'message': str(e),
                'timestamp': time.time()
            })
    
    def _run_qpcal_worker(self, algorithm_name: str, command_queue: Queue, result_queue: Queue, params: Dict[str, Any]):
        """Qpcal algoritması worker process'i"""
        try:
            logger.info(f"[QPCAL_WORKER] ▶️ {algorithm_name} başlatıldı (PID: {os.getpid()})")
            
            # TODO: Qpcal işlemlerini buraya taşı
            
            result_queue.put({
                'algorithm_name': algorithm_name,
                'algorithm_type': 'qpcal',
                'event': 'started',
                'message': 'Qpcal başlatıldı',
                'timestamp': time.time()
            })
            
        except Exception as e:
            logger.error(f"[QPCAL_WORKER] ❌ {algorithm_name} hatası: {e}")
            result_queue.put({
                'algorithm_name': algorithm_name,
                'algorithm_type': 'qpcal',
                'event': 'error',
                'message': str(e),
                'timestamp': time.time()
            })

