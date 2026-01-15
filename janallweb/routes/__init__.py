"""
Routes modülü - API endpoint'leri ve WebSocket handler'ları
"""

from flask import Blueprint

# API Blueprint - app.py'de oluşturulacak ve buraya inject edilecek
# Varsayılan olarak oluştur (app.py inject etmezse)
try:
    api_bp
except NameError:
    api_bp = Blueprint('api', __name__)

