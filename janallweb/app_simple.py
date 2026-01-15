"""
Basit app.py - Blueprint hatası olmadan
"""

from flask import Flask, Blueprint
from flask_cors import CORS
from flask_socketio import SocketIO
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

CORS(app, resources={
    r"/api/*": {"origins": "*"},
    r"/socket.io/*": {"origins": "*"}
})

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

# Blueprint'i burada oluştur
api_bp = Blueprint('api', __name__)

# Route'ları direkt buraya ekle (import etmeden)
from flask import request, jsonify
import pandas as pd
from pathlib import Path

# CSV Service
class CSVService:
    def __init__(self):
        self.base_dir = Path(__file__).parent.parent
    
    def load_csv(self, filename):
        try:
            filepath = self.base_dir / filename
            if not filepath.exists():
                alt_path = self.base_dir / 'janall' / filename
                if alt_path.exists():
                    filepath = alt_path
                else:
                    return None
            return pd.read_csv(filepath)
        except:
            return None

csv_service = CSVService()

# Basit route'lar
@api_bp.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'JanAll Web API'})

@api_bp.route('/csv/list', methods=['GET'])
def list_csv():
    try:
        files = []
        base = Path(__file__).parent.parent
        for f in base.glob('*.csv'):
            files.append(f.name)
        return jsonify({'success': True, 'files': sorted(files)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Blueprint'i register et
app.register_blueprint(api_bp, url_prefix='/api')

@app.route('/')
def index():
    return {'message': 'JanAll Web API', 'status': 'running'}

if __name__ == '__main__':
    print("=" * 60)
    print("JANALL WEB BACKEND - BASIT MOD")
    print("=" * 60)
    print("Backend http://127.0.0.1:5000 adresinde baslatiliyor...")
    print("Durdurmak icin Ctrl+C basin")
    print("=" * 60)
    socketio.run(
        app,
        host='127.0.0.1',
        port=5000,
        debug=False,
        allow_unsafe_werkzeug=True
    )









