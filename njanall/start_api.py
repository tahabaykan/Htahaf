"""
njanall API Server Başlatma Scripti
"""

import sys
import os

# njanall dizinini path'e ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == '__main__':
    from api_server import app
    
    print("=" * 60)
    print("🚀 njanall API Server")
    print("=" * 60)
    print("📡 Server başlatılıyor...")
    print("🌐 URL: http://localhost:5000")
    print("📚 API Docs: http://localhost:5000/health")
    print("=" * 60)
    print("\n💡 n8n entegrasyonu için:")
    print("   - Webhook URL: http://localhost:5000/webhook/n8n")
    print("   - API Base URL: http://localhost:5000/api")
    print("\n⏹️  Durdurmak için: Ctrl+C")
    print("=" * 60)
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\n\n👋 Server durduruldu.")
    except Exception as e:
        print(f"\n❌ Hata: {e}")
        import traceback
        traceback.print_exc()










