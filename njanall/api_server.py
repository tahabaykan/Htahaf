"""
njanall API Server - n8n entegrasyonu için REST API
Bu modül GUI bağımlılıkları olmadan core fonksiyonları API endpoint'leri olarak expose eder.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import sys
import traceback
from datetime import datetime

# njanall modüllerini import et
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from janallapp.path_helper import get_csv_path, NJANALL_BASE_DIR
from janallapp.merge_csvs import csv_files_with_groups
from janallapp.bdata_storage import BDataStorage
from janallapp.exception_manager import ExceptionListManager
from janallapp.myjdata import (
    get_final_jdata_for_symbol,
    get_symbol_performance_summary,
    convert_jdatalog_to_pref_ibkr
)
import pandas as pd

app = Flask(__name__)
CORS(app)  # n8n'den gelen isteklere izin ver

# Global instances
bdata_storage = BDataStorage()
exception_manager = ExceptionListManager(get_csv_path("exception_list.csv"))

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'base_dir': NJANALL_BASE_DIR
    })

@app.route('/api/csv/merge', methods=['POST'])
def merge_csvs():
    """Tüm ssfinek CSV dosyalarını birleştirip janalldata.csv oluştur"""
    try:
        from janallapp.merge_csvs import merge_all_csvs
        
        success, merged_df, message = merge_all_csvs()
        
        if not success:
            return jsonify({'error': message}), 400
        
        return jsonify({
            'success': True,
            'message': message,
            'rows': len(merged_df),
            'output_path': get_csv_path('janalldata.csv')
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.route('/api/csv/read/<filename>', methods=['GET'])
def read_csv(filename):
    """CSV dosyasını oku"""
    try:
        filepath = get_csv_path(filename)
        if not os.path.exists(filepath):
            return jsonify({'error': f'File not found: {filename}'}), 404
        
        df = pd.read_csv(filepath)
        
        # Query parametreleri
        limit = request.args.get('limit', type=int)
        offset = request.args.get('offset', type=int, default=0)
        
        if limit:
            df = df.iloc[offset:offset+limit]
        
        return jsonify({
            'success': True,
            'filename': filename,
            'rows': len(df),
            'columns': list(df.columns),
            'data': df.to_dict('records')
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.route('/api/csv/write/<filename>', methods=['POST'])
def write_csv(filename):
    """CSV dosyasına yaz"""
    try:
        data = request.json
        if not data or 'data' not in data:
            return jsonify({'error': 'No data provided'}), 400
        
        df = pd.DataFrame(data['data'])
        filepath = get_csv_path(filename)
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        
        return jsonify({
            'success': True,
            'message': f'{filename} kaydedildi',
            'rows': len(df),
            'filepath': filepath
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.route('/api/stocks/list', methods=['GET'])
def list_stocks():
    """janalldata.csv'deki tüm hisseleri listele"""
    try:
        filepath = get_csv_path('janalldata.csv')
        if not os.path.exists(filepath):
            return jsonify({'error': 'janalldata.csv not found'}), 404
        
        df = pd.read_csv(filepath)
        
        # Filtreleme parametreleri
        group = request.args.get('group')
        symbol = request.args.get('symbol')
        
        if group:
            df = df[df['GROUP'] == group]
        if symbol:
            df = df[df['PREF IBKR'] == symbol]
        
        return jsonify({
            'success': True,
            'count': len(df),
            'stocks': df.to_dict('records')
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.route('/api/stocks/<symbol>', methods=['GET'])
def get_stock(symbol):
    """Belirli bir hisse hakkında bilgi al"""
    try:
        filepath = get_csv_path('janalldata.csv')
        if not os.path.exists(filepath):
            return jsonify({'error': 'janalldata.csv not found'}), 404
        
        df = pd.read_csv(filepath)
        stock = df[df['PREF IBKR'] == symbol]
        
        if stock.empty:
            return jsonify({'error': f'Stock not found: {symbol}'}), 404
        
        stock_data = stock.iloc[0].to_dict()
        
        # JDataLog bilgilerini ekle
        jdata = get_final_jdata_for_symbol(symbol)
        stock_data['jdata'] = jdata
        
        return jsonify({
            'success': True,
            'symbol': symbol,
            'data': stock_data
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.route('/api/positions', methods=['GET'])
def get_positions():
    """Açık pozisyonları listele"""
    try:
        summary = bdata_storage.get_position_summary_with_snapshot()
        
        positions = []
        for ticker, data in summary.items():
            if data['total_size'] != 0:
                positions.append({
                    'ticker': ticker,
                    'size': data['total_size'],
                    'avg_cost': data['avg_cost'],
                    'avg_benchmark': data['avg_benchmark']
                })
        
        return jsonify({
            'success': True,
            'count': len(positions),
            'positions': positions
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.route('/api/positions/add', methods=['POST'])
def add_position():
    """Yeni pozisyon ekle"""
    try:
        data = request.json
        ticker = data.get('ticker')
        direction = data.get('direction', 'long')
        fill_price = float(data.get('fill_price', 0))
        fill_size = float(data.get('fill_size', 0))
        benchmark_at_fill = float(data.get('benchmark_at_fill', fill_price + 0.5))
        
        if not ticker:
            return jsonify({'error': 'ticker required'}), 400
        
        bdata_storage.add_fill(
            ticker=ticker,
            direction=direction,
            fill_price=fill_price,
            fill_size=fill_size,
            fill_time=datetime.now(),
            benchmark_at_fill=benchmark_at_fill
        )
        
        return jsonify({
            'success': True,
            'message': f'Position added: {ticker}'
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.route('/api/exceptions', methods=['GET'])
def get_exceptions():
    """Exception listesini al"""
    try:
        exceptions = list(exception_manager.exception_tickers)
        return jsonify({
            'success': True,
            'count': len(exceptions),
            'exceptions': exceptions
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.route('/api/exceptions/add', methods=['POST'])
def add_exception():
    """Exception listesine ekle"""
    try:
        data = request.json
        ticker = data.get('ticker')
        
        if not ticker:
            return jsonify({'error': 'ticker required'}), 400
        
        exception_manager.add_ticker(ticker)
        return jsonify({
            'success': True,
            'message': f'Exception added: {ticker}'
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.route('/api/exceptions/remove', methods=['POST'])
def remove_exception():
    """Exception listesinden çıkar"""
    try:
        data = request.json
        ticker = data.get('ticker')
        
        if not ticker:
            return jsonify({'error': 'ticker required'}), 400
        
        exception_manager.remove_ticker(ticker)
        return jsonify({
            'success': True,
            'message': f'Exception removed: {ticker}'
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.route('/api/jdatalog/convert', methods=['POST'])
def convert_jdatalog():
    """jdatalog.csv'deki sembolleri PREF IBKR formatına çevir"""
    try:
        convert_jdatalog_to_pref_ibkr()
        return jsonify({
            'success': True,
            'message': 'jdatalog.csv converted to PREF IBKR format'
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.route('/api/jdatalog/symbol/<symbol>', methods=['GET'])
def get_jdatalog_symbol(symbol):
    """Belirli bir sembol için JDataLog bilgilerini al"""
    try:
        jdata = get_final_jdata_for_symbol(symbol)
        summary = get_symbol_performance_summary(symbol)
        
        return jsonify({
            'success': True,
            'symbol': symbol,
            'jdata': jdata,
            'summary': summary
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

# n8n Webhook endpoint'i
@app.route('/webhook/n8n', methods=['POST'])
def n8n_webhook():
    """n8n webhook endpoint'i - genel amaçlı"""
    try:
        data = request.json
        action = data.get('action', '')
        
        # Action'a göre işlem yap
        if action == 'merge_csvs':
            return merge_csvs()
        elif action == 'get_stocks':
            return list_stocks()
        elif action == 'add_position':
            return add_position()
        elif action == 'get_positions':
            return get_positions()
        else:
            return jsonify({
                'success': True,
                'message': 'Webhook received',
                'action': action,
                'data': data
            })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

if __name__ == '__main__':
    print("=" * 60)
    print("njanall API Server")
    print("=" * 60)
    print(f"Base Directory: {NJANALL_BASE_DIR}")
    print(f"Server starting on http://localhost:5000")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=True)

