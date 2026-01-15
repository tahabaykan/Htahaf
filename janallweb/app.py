"""
JanAll Web - Flask Backend
Ana Flask uygulaması
"""

from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO
import os
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

app = Flask(__name__, 
            static_folder='static', 
            static_url_path='/static',
            template_folder='static')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# CORS ayarları (React frontend için)
CORS(app, resources={
    r"/api/*": {"origins": "*"},
    r"/socket.io/*": {"origins": "*"}
})

# SocketIO (WebSocket için)
# eventlet yoksa threading mode kullan
try:
    import eventlet
    async_mode = 'eventlet'
except ImportError:
    async_mode = 'threading'

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode=async_mode,
    logger=True,
    engineio_logger=True
)

# ÖNEMLİ: Blueprint'i app.py'de oluştur, route'larda kullan
# Bu, Flask'ın debug mode'unda app'in iki kez yüklenmesi sorununu çözer

# 1. Blueprint'i burada oluştur
from flask import Blueprint
api_bp = Blueprint('api', __name__)

# 2. Blueprint'i route modülüne inject et
import routes
routes.api_bp = api_bp

# 3. Route'ları import et (bu sırada @api_bp.route decorator'ları çalışır)
from routes import api_routes  # noqa: F401

# 4. Şimdi Blueprint'i register et (route'lar zaten yüklendi)
app.register_blueprint(api_bp, url_prefix='/api')

# 4. WebSocket routes'u import et (socketio event handler'ları için)
from routes import websocket_routes  # noqa: F401

# Static files serving - EN SON EKLE (diğer route'ları override etmesin)
from flask import send_from_directory, render_template_string
import os

@app.route('/')
def index():
    """Ana HTML sayfası"""
    from flask import send_from_directory
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    # Railway veya production ortamında PORT environment variable'ı kullan
    port = int(os.getenv('PORT', 5000))
    host = os.getenv('HOST', '127.0.0.1')
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    # Development mode
    # NOT: use_reloader=False yaparak blueprint hatasını önle
    # (Flask reloader app'i iki kez yükler, bu blueprint hatasını önler)
    import sys
    # Reloader'ı kapat (blueprint hatasını önler)
    socketio.run(
        app,
        host=host,
        port=port,
        debug=debug,
        use_reloader=False,  # Reloader'ı kapat - blueprint hatasını önler
        allow_unsafe_werkzeug=True
    )

