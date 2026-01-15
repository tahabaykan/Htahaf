#!/usr/bin/env python3
"""
Benchmark hesaplama tutarlılığını test etmek için debug script'i
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from janallapp.myjdata import get_current_benchmark_value, get_last_price_for_symbol
from janallapp.main_window import MainWindow

def test_benchmark_consistency():
    """Benchmark hesaplama tutarlılığını test et"""
    print("🔍 Benchmark Hesaplama Tutarlılık Testi")
    print("=" * 50)
    
    # Main window oluştur
    main_window = MainWindow()
    
    # Test edilecek benchmark tipleri
    test_benchmarks = ['C400', 'C500', 'C600', 'DEFAULT']
    
    for benchmark_key in test_benchmarks:
        print(f"\n📊 {benchmark_key} Benchmark Testi:")
        print("-" * 30)
        
        # Main window'daki formülü göster
        if hasattr(main_window, 'benchmark_formulas'):
            formula = main_window.benchmark_formulas.get(benchmark_key, {})
            print(f"Formül: {formula}")
            
            # Her ETF için fiyat al ve hesapla
            total = 0.0
            for etf, coefficient in formula.items():
                if coefficient != 0:
                    # Hammer Pro'dan fiyat al
                    if hasattr(main_window, 'hammer') and main_window.hammer and main_window.hammer.connected:
                        market_data = main_window.hammer.get_market_data(etf)
                        if market_data and 'last' in market_data:
                            etf_price = float(market_data['last'])
                            contribution = coefficient * etf_price
                            total += contribution
                            print(f"  {etf}: ${etf_price:.4f} * {coefficient} = ${contribution:.4f}")
                        else:
                            print(f"  {etf}: Fiyat alınamadı")
                    else:
                        print(f"  {etf}: Hammer Pro bağlantısı yok")
            
            print(f"Manuel hesaplama toplam: ${total:.4f}")
            
            # get_current_benchmark_value ile karşılaştır
            calculated_value = get_current_benchmark_value(benchmark_key, main_window)
            print(f"get_current_benchmark_value: ${calculated_value:.4f}")
            
            if abs(total - calculated_value) > 0.001:
                print(f"⚠️  TUTARSIZLIK: Manuel hesaplama vs fonksiyon: {abs(total - calculated_value):.4f}")
                if abs(total - calculated_value) > 0.5:
                    print(f"🚨 BÜYÜK TUTARSIZLIK: Muhtemelen çift hesaplama var!")
            else:
                print(f"✅ Tutarlı")
        else:
            print("❌ benchmark_formulas bulunamadı")
    
    # Çift hesaplama testi
    print(f"\n🔍 Çift Hesaplama Testi:")
    print("-" * 30)
    
    # C400 için özel test
    if hasattr(main_window, 'benchmark_formulas'):
        c400_formula = main_window.benchmark_formulas.get('C400', {})
        print(f"C400 formülü: {c400_formula}")
        
        # Hammer Pro'dan ETF fiyatları
        if hasattr(main_window, 'hammer') and main_window.hammer and main_window.hammer.connected:
            print("Hammer Pro ETF fiyatları:")
            for etf, coefficient in c400_formula.items():
                if coefficient != 0:
                    market_data = main_window.hammer.get_market_data(etf)
                    if market_data and 'last' in market_data:
                        etf_price = float(market_data['last'])
                        print(f"  {etf}: ${etf_price:.4f}")
            
            # get_current_benchmark_value'yu 2 kez çağır ve karşılaştır
            print("\nÇift çağrı testi:")
            value1 = get_current_benchmark_value('C400', main_window)
            value2 = get_current_benchmark_value('C400', main_window)
            print(f"İlk çağrı: ${value1:.4f}")
            print(f"İkinci çağrı: ${value2:.4f}")
            
            if abs(value1 - value2) > 0.001:
                print(f"⚠️  Tutarsızlık: {abs(value1 - value2):.4f}")
            else:
                print(f"✅ Tutarlı")
    
    # Main window'ı kapat
    main_window.destroy()

if __name__ == "__main__":
    test_benchmark_consistency()
