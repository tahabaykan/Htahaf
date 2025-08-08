"""
Hammer Pro Market Data Manager Module
Gerçek zamanlı market data ve FINAL BB skor hesaplama
"""

import asyncio
import logging
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from connection import HammerProConnection
from config import HammerProConfig

class HammerProMarketDataManager:
    """Hammer Pro Market Data Yöneticisi"""
    
    def __init__(self, connection: HammerProConnection):
        """Market data manager'ı başlat"""
        self.connection = connection
        self.logger = logging.getLogger(__name__)
        
        # Market data cache
        self.symbol_data: Dict[str, Dict[str, Any]] = {}
        self.benchmark_data: Dict[str, float] = {}
        
        # FINAL BB skorları
        self.final_bb_scores: Dict[str, float] = {}
        
    async def get_symbol_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Tek sembol için market data al"""
        try:
            msg = {
                "cmd": HammerProConfig.get_api_command("get_symbol_snapshot"),
                "sym": symbol,
                "reqID": f"snapshot_{symbol}_{datetime.now().timestamp()}"
            }
            
            await self.connection.send_message(msg)
            response = await self.connection._wait_for_response(msg["reqID"])
            
            if response and response.get("success") == "OK":
                result = response.get("result", {})
                self.symbol_data[symbol] = result
                self.logger.info(f"Market data alındı: {symbol}")
                return result
            else:
                self.logger.error(f"Market data alınamadı: {symbol}")
                return None
                
        except Exception as e:
            self.logger.error(f"Market data alma hatası: {e}")
            return None
    
    async def get_portfolio_snapshot(self, port_id: str) -> List[Dict[str, Any]]:
        """Portföydeki tüm semboller için market data al"""
        try:
            msg = {
                "cmd": HammerProConfig.get_api_command("get_port_snapshot"),
                "portID": port_id,
                "reqID": f"port_snapshot_{port_id}_{datetime.now().timestamp()}"
            }
            
            await self.connection.send_message(msg)
            response = await self.connection._wait_for_response(msg["reqID"])
            
            if response and response.get("success") == "OK":
                result = response.get("result", [])
                for symbol_data in result:
                    symbol = symbol_data.get("sym", "")
                    if symbol:
                        self.symbol_data[symbol] = symbol_data
                
                self.logger.info(f"Portföy market data alındı: {len(result)} sembol")
                return result
            else:
                self.logger.error(f"Portföy market data alınamadı: {port_id}")
                return []
                
        except Exception as e:
            self.logger.error(f"Portföy market data alma hatası: {e}")
            return []
    
    async def subscribe_to_symbols(self, symbols: List[str]) -> bool:
        """Sembollere gerçek zamanlı abone ol"""
        try:
            msg = {
                "cmd": "subscribe",
                "sub": "L1",
                "streamerID": "AMTD",  # Varsayılan streamer
                "sym": symbols,
                "reqID": f"subscribe_{datetime.now().timestamp()}"
            }
            
            await self.connection.send_message(msg)
            response = await self.connection._wait_for_response(msg["reqID"])
            
            if response and response.get("success") == "OK":
                self.logger.info(f"Gerçek zamanlı abone olundu: {len(symbols)} sembol")
                return True
            else:
                self.logger.error("Gerçek zamanlı abone olunamadı")
                return False
                
        except Exception as e:
            self.logger.error(f"Abone olma hatası: {e}")
            return False
    
    def safe_float(self, x):
        """Güvenli float dönüşümü"""
        try: 
            return float(x)
        except: 
            return None
    
    def calculate_benchmark(self, benchmark_type: str = 'T') -> float:
        """Benchmark hesapla (basit versiyon)"""
        try:
            if benchmark_type == 'T':
                return 0.5  # Treasury benchmark
            elif benchmark_type == 'C':
                return 0.3  # Corporate benchmark
            else:
                return 0.0
        except:
            return 0.0
    
    def calculate_final_bb_score(self, symbol: str, final_thg: float, benchmark_type: str = 'T') -> Dict[str, Any]:
        """Gerçek zamanlı FINAL BB skor hesapla - Orijinal formül kullanarak"""
        try:
            if symbol not in self.symbol_data:
                return {
                    'final_bb': final_thg,
                    'final_fb': final_thg,
                    'final_ab': final_thg,
                    'final_as': final_thg,
                    'final_fs': final_thg,
                    'final_bs': final_thg,
                    'market_data_available': False
                }
            
            market_data = self.symbol_data[symbol]
            
            # Market data'dan değerleri al
            bid = self.safe_float(market_data.get("bid", 0))
            ask = self.safe_float(market_data.get("ask", 0))
            last = self.safe_float(market_data.get("last", 0))
            prev_close = self.safe_float(market_data.get("prevClose", 0))
            volume = self.safe_float(market_data.get("volume", 0))
            
            # Spread hesapla
            spread = ask - bid if ask is not None and bid is not None and ask > 0 and bid > 0 else 0
            
            # Benchmark hesapla
            benchmark_chg = self.calculate_benchmark(benchmark_type)
            
            # Orijinal formül hesaplamaları
            pf_bid_buy = bid + spread * 0.15 if bid is not None and spread is not None else None
            pf_bid_buy_chg = pf_bid_buy - prev_close if pf_bid_buy is not None and prev_close is not None else None
            bid_buy_ucuzluk = pf_bid_buy_chg - benchmark_chg if pf_bid_buy_chg is not None else None
            
            pf_front_buy = last + 0.01 if last is not None else None
            pf_front_buy_chg = pf_front_buy - prev_close if pf_front_buy is not None and prev_close is not None else None
            front_buy_ucuzluk = pf_front_buy_chg - benchmark_chg if pf_front_buy_chg is not None else None
            
            pf_ask_buy = ask + 0.01 if ask is not None else None
            pf_ask_buy_chg = pf_ask_buy - prev_close if pf_ask_buy is not None and prev_close is not None else None
            ask_buy_ucuzluk = pf_ask_buy_chg - benchmark_chg if pf_ask_buy_chg is not None else None
            
            pf_ask_sell = ask - spread * 0.15 if ask is not None and spread is not None else None
            pf_ask_sell_chg = pf_ask_sell - prev_close if pf_ask_sell is not None and prev_close is not None else None
            ask_sell_pahali = pf_ask_sell_chg - benchmark_chg if pf_ask_sell_chg is not None else None
            
            pf_front_sell = last - 0.01 if last is not None else None
            pf_front_sell_chg = pf_front_sell - prev_close if pf_front_sell is not None and prev_close is not None else None
            front_sell_pahali = pf_front_sell_chg - benchmark_chg if pf_front_sell_chg is not None else None
            
            pf_bid_sell = bid - 0.01 if bid is not None else None
            pf_bid_sell_chg = pf_bid_sell - prev_close if pf_bid_sell is not None and prev_close is not None else None
            bid_sell_pahali = pf_bid_sell_chg - benchmark_chg if pf_bid_sell_chg is not None else None
            
            # FINAL BB skorları hesapla
            def final_skor(final_thg, skor):
                try:
                    if skor is None:
                        return final_thg
                    return float(final_thg) - 400 * float(skor)
                except:
                    return final_thg
            
            final_bb = final_skor(final_thg, bid_buy_ucuzluk)
            final_fb = final_skor(final_thg, front_buy_ucuzluk)
            final_ab = final_skor(final_thg, ask_buy_ucuzluk)
            final_as = final_skor(final_thg, ask_sell_pahali)
            final_fs = final_skor(final_thg, front_sell_pahali)
            final_bs = final_skor(final_thg, bid_sell_pahali)
            
            # Sonuçları cache'le
            self.final_bb_scores[symbol] = final_bb
            
            result = {
                'final_bb': final_bb,
                'final_fb': final_fb,
                'final_ab': final_ab,
                'final_as': final_as,
                'final_fs': final_fs,
                'final_bs': final_bs,
                'market_data_available': True,
                'bid': bid,
                'ask': ask,
                'last': last,
                'prev_close': prev_close,
                'volume': volume,
                'spread': spread,
                'benchmark_chg': benchmark_chg,
                'bid_buy_ucuzluk': bid_buy_ucuzluk,
                'front_buy_ucuzluk': front_buy_ucuzluk,
                'ask_buy_ucuzluk': ask_buy_ucuzluk,
                'ask_sell_pahali': ask_sell_pahali,
                'front_sell_pahali': front_sell_pahali,
                'bid_sell_pahali': bid_sell_pahali
            }
            
            self.logger.info(f"FINAL BB skorları hesaplandı: {symbol} - BB: {final_bb:.2f}, FB: {final_fb:.2f}, AB: {final_ab:.2f}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"FINAL BB skor hesaplama hatası: {e}")
            return {
                'final_bb': final_thg,
                'final_fb': final_thg,
                'final_ab': final_thg,
                'final_as': final_thg,
                'final_fs': final_thg,
                'final_bs': final_thg,
                'market_data_available': False,
                'error': str(e)
            }
    
    def calculate_final_bb_scores_batch(self, csv_data: pd.DataFrame, benchmark_type: str = 'T') -> Dict[str, Dict[str, Any]]:
        """Toplu FINAL BB skor hesapla"""
        try:
            symbol_column = HammerProConfig.CSV_SETTINGS["symbol_column"]
            final_thg_column = HammerProConfig.CSV_SETTINGS["final_thg_column"]
            
            scores = {}
            
            for _, row in csv_data.iterrows():
                symbol = row[symbol_column]
                final_thg = row[final_thg_column]
                
                if symbol and pd.notna(final_thg):
                    final_bb_result = self.calculate_final_bb_score(symbol, final_thg, benchmark_type)
                    scores[symbol] = final_bb_result
            
            self.logger.info(f"Toplu FINAL BB skor hesaplandı: {len(scores)} sembol")
            return scores
            
        except Exception as e:
            self.logger.error(f"Toplu FINAL BB skor hesaplama hatası: {e}")
            return {}
    
    async def update_market_data_for_symbols(self, symbols: List[str]) -> bool:
        """Semboller için market data güncelle"""
        try:
            success_count = 0
            
            for symbol in symbols:
                snapshot = await self.get_symbol_snapshot(symbol)
                if snapshot:
                    success_count += 1
            
            self.logger.info(f"Market data güncellendi: {success_count}/{len(symbols)} sembol")
            return success_count > 0
            
        except Exception as e:
            self.logger.error(f"Market data güncelleme hatası: {e}")
            return False
    
    def get_symbol_market_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Sembol için market bilgilerini al"""
        if symbol in self.symbol_data:
            data = self.symbol_data[symbol].copy()
            data['final_bb_score'] = self.final_bb_scores.get(symbol, 0)
            return data
        return None
    
    def get_top_final_bb_symbols(self, n: int = 20) -> List[Tuple[str, float]]:
        """En yüksek FINAL BB skorlu sembolleri al"""
        try:
            # FINAL BB skorlarına göre sırala
            sorted_scores = sorted(self.final_bb_scores.items(), 
                                 key=lambda x: x[1], reverse=True)
            
            return sorted_scores[:n]
            
        except Exception as e:
            self.logger.error(f"En iyi FINAL BB skorları alma hatası: {e}")
            return []
    
    def set_benchmark_data(self, benchmark_data: Dict[str, float]):
        """Benchmark verilerini ayarla"""
        self.benchmark_data = benchmark_data
        self.logger.info(f"Benchmark verileri ayarlandı: {len(benchmark_data)} sembol")
    
    def get_market_data_summary(self) -> Dict[str, Any]:
        """Market data özeti"""
        return {
            "total_symbols": len(self.symbol_data),
            "total_scores": len(self.final_bb_scores),
            "benchmark_symbols": len(self.benchmark_data),
            "last_update": datetime.now().isoformat()
        } 