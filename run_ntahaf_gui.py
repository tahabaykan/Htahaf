#!/usr/bin/env python3
"""
Ntahaf GUI'yi çalıştırmak için script
"""

import sys
import os

# Ntahaf dizinini Python path'ine ekle
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Ntahaf'))

try:
    from Ntahaf.gui.main_window import MainWindow
    import tkinter as tk
    
    def main():
        """Ana GUI'yi başlat"""
        print("🚀 Ntahaf GUI başlatılıyor...")
        
        # Ana pencereyi oluştur
        root = MainWindow()
        
        # Pencere başlığını ayarla
        root.title("Ntahaf Stock Tracker")
        
        # Pencereyi ortala
        root.update_idletasks()
        width = root.winfo_width()
        height = root.winfo_height()
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f"{width}x{height}+{x}+{y}")
        
        print("✅ Ntahaf GUI hazır!")
        print("📊 21 adet SSFINEK butonu eklendi")
        print("🔗 IBKR bağlantısı için 'IBKR'ye Bağlan' butonunu kullanın")
        
        # GUI'yi başlat
        root.mainloop()
    
    if __name__ == "__main__":
        main()
        
except ImportError as e:
    print(f"❌ Hata: Ntahaf modülü bulunamadı: {e}")
    print("💡 Ntahaf dizininin doğru konumda olduğundan emin olun")
except Exception as e:
    print(f"❌ Beklenmeyen hata: {e}")
    import traceback
    traceback.print_exc() 