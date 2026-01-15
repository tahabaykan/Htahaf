"""
WebSocket Route'ları - Real-time data streaming
"""

from flask import request
from flask_socketio import emit, join_room, leave_room
from app import socketio

# Market data service'i lazy import et (circular import'u önlemek için)
def get_market_data_service():
    from services.market_data_service import MarketDataService
    if not hasattr(get_market_data_service, '_instance'):
        get_market_data_service._instance = MarketDataService()
    return get_market_data_service._instance

@socketio.on('connect')
def handle_connect():
    """Client bağlandığında"""
    print(f"Client connected: {request.sid}")
    emit('connected', {'message': 'Bağlantı başarılı'})

@socketio.on('disconnect')
def handle_disconnect():
    """Client bağlantısı kesildiğinde"""
    print(f"Client disconnected: {request.sid}")

@socketio.on('subscribe_market_data')
def handle_subscribe_market_data(data):
    """Market data'ya subscribe ol - Tkinter uygulamasındaki gibi"""
    try:
        symbols = data.get('symbols', [])
        room = f"market_data_{request.sid}"
        
        print(f"[WebSocket] 📡 subscribe_market_data event'i geldi: {len(symbols)} sembol")
        print(f"[WebSocket] DEBUG: Event handler çalışıyor...")
        
        # Market data service'e subscribe et (Hammer Pro'ya subscribe ol)
        market_data_service = get_market_data_service()
        print(f"[WebSocket] DEBUG: Market data service alındı")
        
        if not market_data_service.hammer_client:
            print(f"[WebSocket] ⚠️ Hammer client yok!")
            emit('error', {'message': 'Hammer client başlatılmamış'})
            return
        
        print(f"[WebSocket] DEBUG: Hammer client var")
        
        if not market_data_service.hammer_client.is_connected():
            print(f"[WebSocket] ⚠️ Hammer Pro bağlantısı yok!")
            print(f"[WebSocket] DEBUG: Hammer client connected durumu: {market_data_service.hammer_client.is_connected()}")
            emit('error', {'message': 'Hammer Pro bağlantısı yok'})
            return
        
        print(f"[WebSocket] ✅ Hammer Pro bağlantısı var, subscribe başlatılıyor...")
        
        # Her sembol için Hammer Pro'ya subscribe ol
        subscribed = market_data_service.subscribe_symbols(symbols)
        print(f"[WebSocket] ✅ {len(subscribed)}/{len(symbols)} sembol için Hammer Pro'ya subscribe olundu")
        
        # WebSocket room'larına join et
        for symbol in symbols:
            join_room(f"symbol_{symbol}")
        
        emit('subscribed', {'symbols': symbols, 'room': room, 'subscribed_count': len(subscribed)})
    except Exception as e:
        print(f"[WebSocket] ❌ Subscribe hatası: {e}")
        import traceback
        traceback.print_exc()
        emit('error', {'message': str(e)})

@socketio.on('unsubscribe_market_data')
def handle_unsubscribe_market_data(data):
    """Market data subscription'ı iptal et"""
    try:
        symbols = data.get('symbols', [])
        
        for symbol in symbols:
            leave_room(f"symbol_{symbol}")
        
        emit('unsubscribed', {'symbols': symbols})
    except Exception as e:
        emit('error', {'message': str(e)})

@socketio.on('get_positions')
def handle_get_positions():
    """Pozisyonları iste"""
    try:
        from services.position_service import PositionService
        position_service = PositionService()
        positions = position_service.get_positions()
        
        emit('positions_update', {'positions': positions})
    except Exception as e:
        emit('error', {'message': str(e)})

# Market data service instance'ı
market_data_service = None

# Market data güncellemelerini broadcast etmek için helper fonksiyon
def broadcast_market_data(symbol, data):
    """Market data güncellemesini tüm subscriber'lara gönder"""
    socketio.emit('market_data_update', {
        'symbol': symbol,
        'data': data
    }, room=f"symbol_{symbol}")

# Pozisyon güncellemelerini broadcast etmek için
def broadcast_positions_update(positions):
    """Pozisyon güncellemelerini tüm client'lara gönder"""
    socketio.emit('positions_update', {'positions': positions})

# Emir güncellemelerini broadcast etmek için
def broadcast_order_update(order):
    """Emir güncellemesini tüm client'lara gönder"""
    socketio.emit('order_update', {'order': order})

