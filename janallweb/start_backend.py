"""
Backend başlatma scripti - Hataları görmek için
"""

import sys
import traceback

try:
    print("Backend başlatılıyor...")
    from app import app, socketio
    
    print("✓ App import edildi")
    print("Backend http://127.0.0.1:5000 adresinde başlatılıyor...")
    
    socketio.run(
        app,
        host='127.0.0.1',
        port=5000,
        debug=True,
        allow_unsafe_werkzeug=True
    )
except Exception as e:
    print(f"✗ HATA: {e}")
    traceback.print_exc()
    sys.exit(1)









