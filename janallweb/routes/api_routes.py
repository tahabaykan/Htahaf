"""
API Route'ları - RESTful endpoint'ler
"""

from flask import request, jsonify
import pandas as pd
import os

# Blueprint'i routes modülünden al
from routes import api_bp

# Services'i import et
from services.csv_service import CSVService
from services.position_service import PositionService
from services.order_service import OrderService
from services.market_data_service import MarketDataService
from services.score_service import ScoreService
from services.benchmark_service import BenchmarkService
from services.mode_service import ModeService
from services.derived_metrics_engine import DerivedMetricsEngine

# Service instances
csv_service = CSVService()
position_service = PositionService()
order_service = OrderService()
market_data_service = MarketDataService()
score_service = ScoreService()
benchmark_service = BenchmarkService()
mode_service = ModeService()
derived_metrics_engine = DerivedMetricsEngine()

# ==================== CSV İşlemleri ====================

@api_bp.route('/csv/load', methods=['POST'])
def load_csv():
    """CSV dosyası yükle"""
    try:
        data = request.get_json()
        filename = data.get('filename', 'janalldata.csv')
        
        print(f"[API] CSV yükleme isteği: {filename}")
        
        df = csv_service.load_csv(filename)
        
        if df is None:
            return jsonify({'success': False, 'error': f'Dosya bulunamadı: {filename}'}), 404
        
        # DataFrame'i dict'e çevir
        df = df.fillna('')
        for col in df.columns:
            if df[col].dtype == 'datetime64[ns]':
                df[col] = df[col].astype(str)
            elif df[col].dtype == 'object':
                df[col] = df[col].fillna('')
        
        csv_service.set_current_dataframe(df)
        
        # Skor ve benchmark hesaplama (basitleştirilmiş, detaylı logic service'lerde)
        print(f"[API] Skorlar ve benchmark'lar hesaplanıyor...")
        benchmark_service.update_etf_changes_from_market_data(market_data_service)
        
        # ... Hesaplama döngüsü buraya eklenebilir ama şimdilik raw data dönelim ...
        # Performans için client-side hesaplama veya background task daha iyi olabilir
        
        records = df.to_dict(orient='records')
        return jsonify({
            'success': True,
            'message': f'CSV yüklendi: {len(df)} satır',
            'data': records
        })
    except Exception as e:
        print(f"[API] CSV yükleme hatası: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/csv/list', methods=['GET'])
def list_csv_files():
    files = csv_service.list_csv_files()
    return jsonify({'success': True, 'files': files})

# ==================== Market Data & Live ====================

@api_bp.route('/market-data/start-live', methods=['POST'])
def start_live_data():
    """Orijinal JanAll mantığı: janalldata.csv yükle ve abone ol"""
    try:
        filename = 'janalldata.csv'
        print(f"[API] Live Data başlatılıyor... Otomatik yüklenen dosya: {filename}")
        
        # 1. CSV Yükle
        df = csv_service.load_csv(filename)
        if df is None:
            # Yedek dosya dene
            print(f"[API] {filename} bulunamadı, yedek aranıyor...")
            files = csv_service.list_csv_files()
            janek_files = [f for f in files if f.startswith('janek_')]
            if janek_files:
                filename = janek_files[0]
                print(f"[API] Yedek dosya kullanılıyor: {filename}")
                df = csv_service.load_csv(filename)
        
        if df is None:
            return jsonify({'success': False, 'error': 'Yüklenecek veri dosyası bulunamadı'}), 404
            
        csv_service.set_current_dataframe(df)
            
        # 2. Subscribe Ol
        if 'PREF IBKR' in df.columns:
            symbols = df['PREF IBKR'].dropna().tolist()
            subscribed = market_data_service.subscribe_symbols(symbols)
        else:
            symbols = []
            subscribed = []
        
        # 3. Veriyi Hazırla
        df = df.fillna('')
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].fillna('')
                
        records = df.to_dict(orient='records')
        
        return jsonify({
            'success': True, 
            'message': f'{len(subscribed)} sembol için Live Data başlatıldı',
            'data': records,
            'filename': filename
        })
        
    except Exception as e:
        print(f"[API] Live Data başlatma hatası: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/market-data/subscribe', methods=['POST'])
def subscribe_market_data():
    data = request.get_json()
    symbols = data.get('symbols', [])
    subscribed = market_data_service.subscribe_symbols(symbols)
    return jsonify({'success': True, 'subscribed': subscribed})

@api_bp.route('/market-data/merged', methods=['GET'])
def get_merged_market_data():
    """
    Get merged data: static CSV data + live Hammer market data + derived scores
    This is the main endpoint for the market scanner table.
    """
    try:
        # Get all symbols from static store
        static_store = csv_service.get_static_store()
        if not static_store.is_loaded():
            # Try to load if not loaded
            static_store.load_csv()
        
        symbols = static_store.get_all_symbols()
        
        if not symbols:
            return jsonify({
                'success': False,
                'error': 'No static data loaded. Please load janalldata.csv first.'
            }), 404
        
        # Get market data for all symbols
        merged_data = []
        
        for symbol in symbols:
            # Get static data
            static_data = static_store.get_static_data(symbol)
            if not static_data:
                continue
            
            # Get live market data
            market_data = market_data_service.get_market_data(symbol)
            if not market_data:
                # Use empty market data if not available
                market_data = {
                    'bid': None,
                    'ask': None,
                    'last': None,
                    'price': None,
                    'spread': None,
                    'volume': None
                }
            
            # Calculate spread if not provided
            if market_data.get('spread') is None:
                bid = market_data.get('bid')
                ask = market_data.get('ask')
                if bid and ask and bid > 0 and ask > 0:
                    market_data['spread'] = ask - bid
                else:
                    market_data['spread'] = 0.0
            
            # Compute derived scores
            derived_result = derived_metrics_engine.compute_scores(
                symbol=symbol,
                market_data=market_data,
                static_data=static_data
            )
            
            # Merge everything into one record
            merged_record = {
                # Static CSV fields
                'PREF_IBKR': symbol,
                'prev_close': static_data.get('prev_close'),
                'CMON': static_data.get('CMON'),
                'CGRUP': static_data.get('CGRUP'),
                'FINAL_THG': static_data.get('FINAL_THG'),
                'SHORT_FINAL': static_data.get('SHORT_FINAL'),
                'AVG_ADV': static_data.get('AVG_ADV'),
                'SMI': static_data.get('SMI'),
                'SMA63_chg': static_data.get('SMA63 chg'),
                'SMA246_chg': static_data.get('SMA246 chg'),
                
                # Live market data
                'Bid': market_data.get('bid'),
                'Ask': market_data.get('ask'),
                'Last': market_data.get('last') or market_data.get('price'),
                'Volume': market_data.get('volume'),
                'Spread': market_data.get('spread'),
                
                # Derived scores
                'FrontBuyScore': derived_result.get('scores', {}).get('FrontBuyScore'),
                'FinalFBScore': derived_result.get('scores', {}).get('FinalFBScore'),
                'BidBuyScore': derived_result.get('scores', {}).get('BidBuyScore'),
                'AskBuyScore': derived_result.get('scores', {}).get('AskBuyScore'),
                'AskSellScore': derived_result.get('scores', {}).get('AskSellScore'),
                'FrontSellScore': derived_result.get('scores', {}).get('FrontSellScore'),
                'BidSellScore': derived_result.get('scores', {}).get('BidSellScore'),
                
                # Explainable inputs (for debugging/transparency)
                'score_inputs': derived_result.get('inputs'),
            }
            
            merged_data.append(merged_record)
        
        return jsonify({
            'success': True,
            'data': merged_data,
            'count': len(merged_data)
        })
        
    except Exception as e:
        print(f"[API] Merged data error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/market-data/merged/<symbol>', methods=['GET'])
def get_merged_market_data_symbol(symbol):
    """
    Get merged data for a single symbol.
    """
    try:
        static_store = csv_service.get_static_store()
        if not static_store.is_loaded():
            static_store.load_csv()
        
        # Get static data
        static_data = static_store.get_static_data(symbol)
        if not static_data:
            return jsonify({
                'success': False,
                'error': f'Static data not found for {symbol}'
            }), 404
        
        # Get live market data
        market_data = market_data_service.get_market_data(symbol)
        if not market_data:
            market_data = {
                'bid': None,
                'ask': None,
                'last': None,
                'price': None,
                'spread': None,
                'volume': None
            }
        
        # Calculate spread if not provided
        if market_data.get('spread') is None:
            bid = market_data.get('bid')
            ask = market_data.get('ask')
            if bid and ask and bid > 0 and ask > 0:
                market_data['spread'] = ask - bid
            else:
                market_data['spread'] = 0.0
        
        # Compute derived scores
        derived_result = derived_metrics_engine.compute_scores(
            symbol=symbol,
            market_data=market_data,
            static_data=static_data
        )
        
        # Merge everything
        merged_record = {
            'PREF_IBKR': symbol,
            'prev_close': static_data.get('prev_close'),
            'CMON': static_data.get('CMON'),
            'CGRUP': static_data.get('CGRUP'),
            'FINAL_THG': static_data.get('FINAL_THG'),
            'SHORT_FINAL': static_data.get('SHORT_FINAL'),
            'AVG_ADV': static_data.get('AVG_ADV'),
            'SMI': static_data.get('SMI'),
            'SMA63_chg': static_data.get('SMA63 chg'),
            'SMA246_chg': static_data.get('SMA246 chg'),
            'Bid': market_data.get('bid'),
            'Ask': market_data.get('ask'),
            'Last': market_data.get('last') or market_data.get('price'),
            'Volume': market_data.get('volume'),
            'Spread': market_data.get('spread'),
            'FrontBuyScore': derived_result.get('scores', {}).get('FrontBuyScore'),
            'FinalFBScore': derived_result.get('scores', {}).get('FinalFBScore'),
            'BidBuyScore': derived_result.get('scores', {}).get('BidBuyScore'),
            'AskBuyScore': derived_result.get('scores', {}).get('AskBuyScore'),
            'AskSellScore': derived_result.get('scores', {}).get('AskSellScore'),
            'FrontSellScore': derived_result.get('scores', {}).get('FrontSellScore'),
            'BidSellScore': derived_result.get('scores', {}).get('BidSellScore'),
            'score_inputs': derived_result.get('inputs'),
        }
        
        return jsonify({
            'success': True,
            'data': merged_record
        })
        
    except Exception as e:
        print(f"[API] Merged data error for {symbol}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== Connection ====================

@api_bp.route('/connection/hammer/connect', methods=['POST'])
def connect_hammer():
    data = request.get_json()
    password = data.get('password')
    success = market_data_service.connect_hammer(password=password)
    if success:
        return jsonify({'success': True, 'message': 'Bağlantı başarılı'})
    else:
        return jsonify({'success': False, 'error': 'Bağlantı başarısız (şifre kontrol edin)'})

@api_bp.route('/connection/hammer/disconnect', methods=['POST'])
def disconnect_hammer():
    market_data_service.disconnect_hammer()
    return jsonify({'success': True})

@api_bp.route('/connection/status', methods=['GET'])
def connection_status():
    status = {
        'hammer': market_data_service.hammer_client.is_connected() if market_data_service.hammer_client else False
    }
    return jsonify({'success': True, 'status': status})

# ==================== Positions & Orders ====================

@api_bp.route('/positions', methods=['GET'])
def get_positions():
    positions = position_service.get_positions()
    return jsonify({'success': True, 'positions': positions})

@api_bp.route('/orders/place_bulk', methods=['POST'])
def place_bulk_order():
    # Basitleştirilmiş bulk order
    return jsonify({'success': True, 'message': 'Toplu emir alındı'})

# ==================== Panels ====================

@api_bp.route('/panels/<panel_id>', methods=['GET'])
def get_panel(panel_id):
    # Panel HTML içeriği döndür
    html = f"<h3>{panel_id} Paneli</h3><p>İçerik hazırlanıyor...</p>"
    return jsonify({'success': True, 'html': html})

# ==================== Mode ====================

@api_bp.route('/mode/set', methods=['POST'])
def set_mode():
    data = request.get_json()
    mode = data.get('mode')
    success = mode_service.set_mode(mode)
    return jsonify({'success': success})
