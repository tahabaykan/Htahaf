"""
Compression utilities for StockTracker application
"""
import zlib
import pickle
import base64

def compress_market_data(data):
    """Veriyi binary formata dönüştür"""
    try:
        # Nesneyi pickle ile serileştir
        pickled = pickle.dumps(data)
        # Sıkıştır ve base64 kodla
        compressed = base64.b64encode(zlib.compress(pickled))
        return compressed
    except Exception as e:
        print(f"Compression error: {e}")
        return None

def decompress_market_data(binary_data):
    """Binary veriyi aç"""
    try:
        # Base64 decode, decompress ve unpickle
        decompressed = zlib.decompress(base64.b64decode(binary_data))
        return pickle.loads(decompressed)
    except Exception as e:
        print(f"Decompression error: {e}")
        return None 