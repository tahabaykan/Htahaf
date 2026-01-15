"""
Debug mode ile çalıştırmak için alternatif
"""

from app import app, socketio

if __name__ == '__main__':
    # Debug mode ile çalıştır (reloader kapalı)
    socketio.run(
        app,
        host='127.0.0.1',
        port=5000,
        debug=True,
        use_reloader=False,  # Reloader'ı kapat (blueprint hatasını önler)
        allow_unsafe_werkzeug=True
    )









