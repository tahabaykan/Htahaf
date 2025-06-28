#!/usr/bin/env python3
"""Hızlı PSFAlgo Exclude Test"""

print('🔧 PSFAlgo Exclude Sistem Testi...')

try:
    from Htahaf.psfalgo import PsfAlgo
    
    # Mock data
    class MockData:
        def set_psf_algo(self, a): pass
        def get_etf_data(self): return {}
        def place_order(self, ticker, action, size, **kwargs): 
            print(f'📧 Emir gönderildi: {ticker} {action} {size}')
            return True
    
    # Exclude list ile PSFAlgo oluştur
    exclude_set = {'ARCC', 'AGNC'}
    psf = PsfAlgo(MockData(), exclude_list=exclude_set)
    
    # BEFDAY yüklemesini atla (hızlı test için)
    psf.befday_positions = {}
    psf.daily_position_limits = {}
    psf.is_active = True
    
    print(f'📋 Exclude List: {list(psf.exclude_list)}')
    
    # Test 1: Normal hisse
    print('\n1️⃣ NEWT (normal hisse):')
    result1 = psf.send_order('NEWT', 20.50, 100, 'LONG', 200)
    print(f'   Sonuç: {result1}')
    
    # Test 2: Exclude hisse
    print('\n2️⃣ ARCC (exclude hisse):')
    result2 = psf.send_order('ARCC', 20.15, 100, 'LONG', 200)
    print(f'   Sonuç: {result2}')
    
    # Test 3: Başka exclude hisse
    print('\n3️⃣ AGNC (exclude hisse):')
    result3 = psf.send_order('AGNC', 12.50, 100, 'LONG', 200)
    print(f'   Sonuç: {result3}')
    
    # Sonuç
    print('\n🎯 TEST SONUÇLARI:')
    print(f'✅ NEWT (normal): {result1} - Beklenen: True')
    print(f'❌ ARCC (exclude): {result2} - Beklenen: False')
    print(f'❌ AGNC (exclude): {result3} - Beklenen: False')
    
    if result1 and not result2 and not result3:
        print('\n🎉 EXCLUDE SİSTEMİ MÜKEMMEL ÇALIŞIYOR!')
        print('✅ Normal hisseler emir alıyor')
        print('❌ Exclude hisseler reddediliyor')
    else:
        print('\n⚠️ Exclude sisteminde problem var!')
    
except Exception as e:
    print(f'❌ Test hatası: {e}')
    import traceback
    traceback.print_exc() 