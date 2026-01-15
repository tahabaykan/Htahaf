"""
Basit Kolon Test Scripti
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_columns():
    """Kolon tanımlarını test et"""
    print("🧪 Basit Kolon Testi Başlıyor...")
    
    # Long sekmesi kolonları
    long_cols = ['Group', 'Symbol', 'Final_FB_skor', 'Final_SFS_skor', 'FINAL_THG', 'SHORT_FINAL', 'SMI', 'MAXALW', 'CalculatedLots', 'FinalLots', 'CurrentLots', 'AvailableLots', 'Status']
    long_headers = ['Grup', 'Sembol', 'Final_FB_skor', 'Final_SFS_skor', 'FINAL_THG', 'SHORT_FINAL', 'SMI', 'MAXALW', 'Hesaplanan Lot', 'Final Lot', 'Mevcut Lot', 'Alınabilir Lot', 'Durum']
    
    print(f"\n🔍 Long Sekmesi:")
    print(f"Kolon sayısı: {len(long_cols)}")
    print(f"Header sayısı: {len(long_headers)}")
    
    # Final_FB_skor ve Final_SFS_skor kontrolü
    if 'Final_FB_skor' in long_cols:
        fb_index = long_cols.index('Final_FB_skor')
        print(f"✅ Final_FB_skor kolonu bulundu (index: {fb_index})")
        print(f"   Header: {long_headers[fb_index]}")
    else:
        print("❌ Final_FB_skor kolonu bulunamadı")
    
    if 'Final_SFS_skor' in long_cols:
        sfs_index = long_cols.index('Final_SFS_skor')
        print(f"✅ Final_SFS_skor kolonu bulundu (index: {sfs_index})")
        print(f"   Header: {long_headers[sfs_index]}")
    else:
        print("❌ Final_SFS_skor kolonu bulunamadı")
    
    # Short sekmesi kolonları
    short_cols = ['Group', 'Symbol', 'Final_FB_skor', 'Final_SFS_skor', 'SHORT_FINAL', 'FINAL_THG', 'SMI', 'MAXALW', 'CalculatedLots', 'FinalLots', 'CurrentLots', 'AvailableLots', 'Status']
    short_headers = ['Grup', 'Sembol', 'Final_FB_skor', 'Final_SFS_skor', 'SHORT_FINAL', 'FINAL_THG', 'SMI', 'MAXALW', 'Hesaplanan Lot', 'Final Lot', 'Mevcut Lot', 'Alınabilir Lot', 'Durum']
    
    print(f"\n🔍 Short Sekmesi:")
    print(f"Kolon sayısı: {len(short_cols)}")
    print(f"Header sayısı: {len(short_headers)}")
    
    # Final_FB_skor ve Final_SFS_skor kontrolü
    if 'Final_FB_skor' in short_cols:
        fb_index = short_cols.index('Final_FB_skor')
        print(f"✅ Final_FB_skor kolonu bulundu (index: {fb_index})")
        print(f"   Header: {short_headers[fb_index]}")
    else:
        print("❌ Final_FB_skor kolonu bulunamadı")
    
    if 'Final_SFS_skor' in short_cols:
        sfs_index = short_cols.index('Final_SFS_skor')
        print(f"✅ Final_SFS_skor kolonu bulundu (index: {sfs_index})")
        print(f"   Header: {short_headers[sfs_index]}")
    else:
        print("❌ Final_SFS_skor kolonu bulunamadı")
    
    print("\n✅ Basit kolon testi tamamlandı!")

if __name__ == "__main__":
    test_columns()





















