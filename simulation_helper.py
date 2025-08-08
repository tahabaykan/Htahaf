#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simülasyon Modu Yardımcı Fonksiyonları
15 Aralık 2024 tarihinde çalıştırılmış gibi simüle eder
"""

import os
from datetime import datetime, date, timedelta

def get_simulation_date():
    """Simülasyon tarihini al"""
    simulation_date = os.environ.get('SIMULATION_DATE', '2024-12-15')
    return datetime.strptime(simulation_date, '%Y-%m-%d').date()

def is_simulation_mode():
    """Simülasyon modunda mı kontrol et"""
    return os.environ.get('SIMULATION_MODE', 'false').lower() == 'true'

def get_current_date():
    """Mevcut tarihi al (simülasyon modunda simülasyon tarihini döndür)"""
    if is_simulation_mode():
        return get_simulation_date()
    else:
        return date.today()

def get_historical_end_date():
    """Historical data için bitiş tarihini al"""
    if is_simulation_mode():
        # 15 Aralık 2024'ten önceki verileri çek
        simulation_date = get_simulation_date()
        return simulation_date - timedelta(days=1)  # 14 Aralık 2024
    else:
        return date.today()

def get_sma_periods():
    """SMA periyotlarını al (simülasyon modunda 15 Aralık 2024'ten önceki veriler)"""
    if is_simulation_mode():
        simulation_date = get_simulation_date()
        return {
            'SMA20': simulation_date - timedelta(days=20),
            'SMA63': simulation_date - timedelta(days=63),
            'SMA246': simulation_date - timedelta(days=246)
        }
    else:
        today = date.today()
        return {
            'SMA20': today - timedelta(days=20),
            'SMA63': today - timedelta(days=63),
            'SMA246': today - timedelta(days=246)
        }

def get_high_low_periods():
    """High/Low periyotlarını al"""
    if is_simulation_mode():
        simulation_date = get_simulation_date()
        return {
            '3M': simulation_date - timedelta(days=90),
            '6M': simulation_date - timedelta(days=180),
            '1Y': simulation_date - timedelta(days=365)
        }
    else:
        today = date.today()
        return {
            '3M': today - timedelta(days=90),
            '6M': today - timedelta(days=180),
            '1Y': today - timedelta(days=365)
        }

def get_special_dates():
    """Özel tarihleri al (Aug4, Oct19)"""
    if is_simulation_mode():
        simulation_date = get_simulation_date()
        # 2024 yılındaki Aug4 ve Oct19 tarihleri
        aug4_2024 = datetime(2024, 8, 4).date()
        oct19_2024 = datetime(2024, 10, 19).date()
        return {
            'Aug4': aug4_2024,
            'Oct19': oct19_2024
        }
    else:
        # Mevcut yılın Aug4 ve Oct19 tarihleri
        current_year = date.today().year
        aug4_current = datetime(current_year, 8, 4).date()
        oct19_current = datetime(current_year, 10, 19).date()
        return {
            'Aug4': aug4_current,
            'Oct19': oct19_current
        }

def print_simulation_info():
    """Simülasyon bilgilerini yazdır"""
    if is_simulation_mode():
        print(f"🎯 SIMÜLASYON MODU AKTİF")
        print(f"📅 Simülasyon Tarihi: {get_simulation_date()}")
        print(f"📊 Historical Data Bitiş: {get_historical_end_date()}")
        print(f"📈 SMA Periyotları: {get_sma_periods()}")
        print(f"📊 High/Low Periyotları: {get_high_low_periods()}")
        print(f"📅 Özel Tarihler: {get_special_dates()}")
        print("-" * 50)
    else:
        print(f"📅 NORMAL MOD - Bugün: {date.today()}")

def get_manual_yield_data():
    """Manuel yield verilerini al (CNBC'den çekilemeyen veriler için)"""
    # 15 Aralık 2024 tarihindeki manuel yield verileri
    # Bu verileri kullanıcıdan alacağız
    manual_yields = {
        # Örnek veriler - gerçek verilerle değiştirilecek
        'FCNCP': 6.67,
        'AFGB': 6.60,
        'SOJD': 5.93,
        'PRS': 5.59,
        'CFG PRE': 6.40,
        # Diğer hisseler için yield verileri eklenecek
    }
    return manual_yields

def get_simulation_filename(filename):
    """Simülasyon modunda dosya adının başına dec ekler, normalde aynen döndürür"""
    if is_simulation_mode():
        # Eğer zaten dec ile başlıyorsa tekrar ekleme
        if filename.startswith('dec'):
            return filename
        # Sadece dosya adının başına ekle, klasör varsa koru
        import os
        dirname, basename = os.path.split(filename)
        decname = 'dec' + basename
        return os.path.join(dirname, decname) if dirname else decname
    else:
        return filename

if __name__ == "__main__":
    print_simulation_info() 