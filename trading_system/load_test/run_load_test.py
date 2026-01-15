"""load_test/run_load_test.py

Sistem yük testi scripti - farklı yük seviyelerinde test yapar ve metrikleri toplar.

Bu script:
    1. Farklı symbol sayıları ve tick rate'lerde test yapar
    2. Redis queue length, latency, CPU/RAM kullanımını ölçer
    3. Sonuçları CSV'ye yazar

Kullanım:
    python load_test/run_load_test.py --output results.csv

Environment Variables:
    REDIS_URL: Redis connection URL
"""

import asyncio
import os
import time
import subprocess
import csv
import argparse
import json
from typing import Dict, List, Any
from datetime import datetime

from aioredis import from_url
from utils.logging_config import setup_logging, get_logger

# Logging
setup_logging(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = get_logger(__name__)


class LoadTestRunner:
    """Load test runner - metrikleri toplar ve raporlar"""
    
    def __init__(self, redis_url: str = 'redis://localhost:6379'):
        self.redis_url = redis_url
        self.results: List[Dict[str, Any]] = []
    
    async def get_redis_info(self) -> Dict[str, Any]:
        """Redis bilgilerini al"""
        try:
            r = await from_url(self.redis_url)
            info = await r.info()
            await r.close()
            return info
        except Exception as e:
            logger.error(f"Redis info error: {e}")
            return {}
    
    async def get_stream_lengths(self) -> Dict[str, int]:
        """Stream uzunluklarını al"""
        try:
            r = await from_url(self.redis_url)
            
            streams = ['ticks', 'signals', 'orders', 'execs']
            lengths = {}
            
            for stream in streams:
                try:
                    length = await r.xlen(stream)
                    lengths[stream] = length
                except Exception:
                    lengths[stream] = 0
            
            await r.close()
            return lengths
        except Exception as e:
            logger.error(f"Stream length error: {e}")
            return {}
    
    async def get_pending_counts(self) -> Dict[str, int]:
        """Consumer group pending mesaj sayılarını al"""
        try:
            r = await from_url(self.redis_url)
            
            groups = {
                'ticks': 'strategy_group',
                'signals': 'risk_group',
                'orders': 'router_group'
            }
            
            pending = {}
            
            for stream, group in groups.items():
                try:
                    info = await r.xpending(stream, group)
                    if info:
                        # info format: [pending_count, min_id, max_id, consumers]
                        pending[stream] = info[0] if isinstance(info, list) else 0
                    else:
                        pending[stream] = 0
                except Exception:
                    pending[stream] = 0
            
            await r.close()
            return pending
        except Exception as e:
            logger.error(f"Pending count error: {e}")
            return {}
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """Sistem metriklerini al (CPU, RAM)"""
        try:
            # psutil kullan (yoksa basit alternatif)
            try:
                import psutil
                cpu_percent = psutil.cpu_percent(interval=1)
                mem = psutil.virtual_memory()
                return {
                    'cpu_percent': cpu_percent,
                    'mem_percent': mem.percent,
                    'mem_used_mb': mem.used / 1024 / 1024,
                    'mem_total_mb': mem.total / 1024 / 1024
                }
            except ImportError:
                # Basit alternatif (Linux)
                try:
                    # CPU
                    cpu_result = subprocess.run(
                        ['top', '-bn1', '|', 'grep', 'Cpu'],
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    # RAM
                    mem_result = subprocess.run(
                        ['free', '-m'],
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    return {
                        'cpu_percent': 0,  # Parse edilebilir
                        'mem_percent': 0,
                        'mem_used_mb': 0,
                        'mem_total_mb': 0
                    }
                except Exception:
                    return {}
        except Exception as e:
            logger.error(f"System metrics error: {e}")
            return {}
    
    async def measure_latency(self, test_duration: int = 10) -> Dict[str, float]:
        """
        Latency ölç - tick'ten order'a kadar geçen süre.
        
        Args:
            test_duration: Test süresi (saniye)
        """
        try:
            r = await from_url(self.redis_url)
            
            # Bir tick ekle ve timestamp kaydet
            start_time = time.time()
            tick_data = {
                'symbol': 'LATENCY_TEST',
                'last': '100.0',
                'ts': str(start_time),
                'test_marker': 'true'
            }
            tick_id = await r.xadd('ticks', tick_data)
            
            # Order stream'inde bu tick'ten gelen order'ı bekle
            max_wait = test_duration
            wait_start = time.time()
            latency = None
            
            while time.time() - wait_start < max_wait:
                # Orders stream'ini kontrol et
                orders = await r.xread({'orders': '0-0'}, count=100, block=1000)
                
                for stream, items in orders:
                    for msg_id, data in items:
                        # Test marker'ı kontrol et
                        if data.get(b'test_marker') == b'true' or data.get('test_marker') == 'true':
                            order_time = float(data.get(b'ts', data.get('ts', 0)))
                            latency = order_time - start_time
                            break
                
                if latency is not None:
                    break
                
                await asyncio.sleep(0.1)
            
            await r.close()
            
            return {
                'tick_to_order_latency_ms': latency * 1000 if latency else None
            }
        except Exception as e:
            logger.error(f"Latency measurement error: {e}")
            return {}
    
    async def run_test_scenario(
        self,
        symbols: int,
        tick_rate: float,
        duration: int = 30
    ) -> Dict[str, Any]:
        """
        Tek bir test senaryosu çalıştır.
        
        Args:
            symbols: Symbol sayısı
            tick_rate: Tick rate (ticks/s)
            duration: Test süresi (saniye)
        """
        logger.info(f"=== Test Senaryosu: {symbols} symbols, {tick_rate} ticks/s, {duration}s ===")
        
        # Başlangıç metrikleri
        start_streams = await self.get_stream_lengths()
        start_redis_info = await self.get_redis_info()
        start_system = self.get_system_metrics()
        
        # Test başlat (fake_tick_publisher'ı subprocess olarak çalıştır)
        import sys
        publisher_cmd = [
            sys.executable,
            'load_test/fake_tick_publisher.py',
            '--symbols', str(symbols),
            '--rate', str(tick_rate),
            '--duration', str(duration)
        ]
        
        logger.info(f"Publisher başlatılıyor: {' '.join(publisher_cmd)}")
        publisher_process = subprocess.Popen(
            publisher_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Test süresi boyunca metrikleri topla
        metrics_samples = []
        sample_interval = 5  # Her 5 saniyede bir örnek
        
        test_start = time.time()
        while time.time() - test_start < duration + 5:  # +5 buffer
            await asyncio.sleep(sample_interval)
            
            streams = await self.get_stream_lengths()
            pending = await self.get_pending_counts()
            system = self.get_system_metrics()
            
            metrics_samples.append({
                'timestamp': time.time(),
                'streams': streams,
                'pending': pending,
                'system': system
            })
        
        # Publisher'ı bekle
        publisher_process.wait()
        
        # Son metrikler
        end_streams = await self.get_stream_lengths()
        end_redis_info = await self.get_redis_info()
        end_system = self.get_system_metrics()
        
        # Ortalama metrikleri hesapla
        avg_pending = {}
        if metrics_samples:
            for stream in ['ticks', 'signals', 'orders']:
                pending_values = [s['pending'].get(stream, 0) for s in metrics_samples]
                avg_pending[stream] = sum(pending_values) / len(pending_values) if pending_values else 0
        
        # Sonuç
        result = {
            'timestamp': datetime.now().isoformat(),
            'symbols': symbols,
            'tick_rate': tick_rate,
            'duration': duration,
            
            # Stream uzunlukları (değişim)
            'ticks_produced': end_streams.get('ticks', 0) - start_streams.get('ticks', 0),
            'signals_produced': end_streams.get('signals', 0) - start_streams.get('signals', 0),
            'orders_produced': end_streams.get('orders', 0) - start_streams.get('orders', 0),
            'execs_produced': end_streams.get('execs', 0) - start_streams.get('execs', 0),
            
            # Pending (ortalama)
            'avg_pending_ticks': avg_pending.get('ticks', 0),
            'avg_pending_signals': avg_pending.get('signals', 0),
            'avg_pending_orders': avg_pending.get('orders', 0),
            
            # Redis
            'redis_memory_mb': end_redis_info.get('used_memory', 0) / 1024 / 1024,
            'redis_connected_clients': end_redis_info.get('connected_clients', 0),
            
            # System
            'cpu_percent': end_system.get('cpu_percent', 0),
            'mem_percent': end_system.get('mem_percent', 0),
            'mem_used_mb': end_system.get('mem_used_mb', 0),
        }
        
        logger.info(f"Test tamamlandı: {result}")
        return result
    
    def save_results_csv(self, filename: str):
        """Sonuçları CSV'ye kaydet"""
        if not self.results:
            logger.warn("Kaydedilecek sonuç yok")
            return
        
        fieldnames = [
            'timestamp', 'symbols', 'tick_rate', 'duration',
            'ticks_produced', 'signals_produced', 'orders_produced', 'execs_produced',
            'avg_pending_ticks', 'avg_pending_signals', 'avg_pending_orders',
            'redis_memory_mb', 'redis_connected_clients',
            'cpu_percent', 'mem_percent', 'mem_used_mb'
        ]
        
        with open(filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.results)
        
        logger.info(f"Sonuçlar kaydedildi: {filename}")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Load test runner')
    parser.add_argument('--output', type=str, default='load_test_results.csv', help='Output CSV file')
    parser.add_argument('--scenarios', type=str, help='JSON scenarios file (optional)')
    
    args = parser.parse_args()
    
    runner = LoadTestRunner()
    
    # Test senaryoları
    if args.scenarios and os.path.exists(args.scenarios):
        with open(args.scenarios, 'r') as f:
            scenarios = json.load(f)
    else:
        # Default senaryolar
        scenarios = [
            {'symbols': 50, 'tick_rate': 5.0, 'duration': 30},
            {'symbols': 200, 'tick_rate': 10.0, 'duration': 30},
            {'symbols': 500, 'tick_rate': 20.0, 'duration': 30},
        ]
    
    logger.info(f"Toplam {len(scenarios)} test senaryosu çalıştırılacak")
    
    for i, scenario in enumerate(scenarios, 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"Senaryo {i}/{len(scenarios)}")
        logger.info(f"{'='*60}\n")
        
        result = await runner.run_test_scenario(
            symbols=scenario['symbols'],
            tick_rate=scenario['tick_rate'],
            duration=scenario.get('duration', 30)
        )
        
        runner.results.append(result)
        
        # Senaryolar arası bekleme
        if i < len(scenarios):
            logger.info("Sonraki senaryo için 10 saniye bekleniyor...")
            await asyncio.sleep(10)
    
    # Sonuçları kaydet
    runner.save_results_csv(args.output)
    
    logger.info(f"\n{'='*60}")
    logger.info("Tüm testler tamamlandı!")
    logger.info(f"Sonuçlar: {args.output}")
    logger.info(f"{'='*60}")


if __name__ == '__main__':
    asyncio.run(main())








