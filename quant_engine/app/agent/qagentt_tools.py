"""
QAGENTT Tool Definitions & Implementations
============================================

Bu dosya QAGENTT'a "aktif araştırma" yeteneği kazandırır.
Agent artık pasif snapshot okumak yerine, merak ettiği her şeyi sorgulayabilir.

TOOL CATEGORIES:
  1. Symbol Tools   — Tek hisse detayı, truth tick history, fill geçmişi
  2. Group Tools    — DOS grup analizi, grup karşılaştırma
  3. Portfolio Tools — Pozisyonlar, açık emirler, exposure
  4. Market Tools   — ETF verileri, piyasa genel durumu
  5. History Tools  — Snapshot geçmişi, QeBench, benchmark

Her tool:
  - schema: Claude API tool definition (JSON Schema)
  - execute: Python function that queries Redis/DataFabric
"""

import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.core.logger import logger


# ═══════════════════════════════════════════════════════════════
# TOOL SCHEMAS — Claude API format
# ═══════════════════════════════════════════════════════════════

TOOL_SCHEMAS = [
    {
        "name": "get_symbol_detail",
        "description": (
            "Tek bir sembol hakkında TÜM metrikleri getir: "
            "fiyat (bid/ask/last/spread), GORT, FINAL_THG, SHORT_FINAL, "
            "FBTOT, SFSTOT, SMA63chg, SMA246chg, ucuzluk/pahalılık skoru, "
            "bench_chg, daily_chg, ADV, DOS grubu, CGRUP, par value. "
            "Bir hisseyi derinlemesine anlamak istediğinde kullan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Hisse sembolü, örn: 'NLY PRF', 'CIM PRD', 'AGNCN'"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_truth_tick_history",
        "description": (
            "Bir sembolün truth tick geçmişini getir (son N tick). "
            "Her tick: zaman, fiyat, lot büyüklüğü, venue (FNRA/ARCA/BATS/XNYS). "
            "Ayrıca volav analizi (BUYER_DOMINANT, SELLER_VACUUM vb.) ve "
            "temporal analiz (1h/4h/1d değişimler) içerir. "
            "Likidite, fiyat trendi ve market microstructure anlamak için kullan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Hisse sembolü"
                },
                "last_n": {
                    "type": "integer",
                    "description": "Son kaç truth tick getirilsin (default: 20, max: 50)",
                    "default": 20
                }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_group_analysis",
        "description": (
            "Bir DOS grubundaki TÜM hisseleri getir. "
            "Her hisse: fiyat, GORT, bench_chg, daily_chg, ucuzluk/pahalılık. "
            "Grup ortalaması ve en iyi/en kötü performans gösteren hisseler. "
            "Bir grubun genel durumunu, outlier'ları ve korelasyonu anlamak için kullan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "group_name": {
                    "type": "string",
                    "description": (
                        "DOS grup adı, örn: 'heldkuponlu', 'heldkuponlukreciliz', "
                        "'heldff', 'heldflr', 'heldotelremorta', 'helddeznff'"
                    )
                }
            },
            "required": ["group_name"]
        }
    },
    {
        "name": "get_positions",
        "description": (
            "Bir hesaptaki TÜM pozisyonları getir: sembol, miktar (qty), "
            "befday_qty, potential_qty, mevcut fiyat, P&L. "
            "Portföy durumunu anlamak için kullan. "
            "account_id boş bırakılırsa TÜM hesapları getirir."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {
                    "type": "string",
                    "description": "Hesap ID: 'HAMPRO' veya 'IBKR_PED'. Boş bırakılırsa tümü."
                }
            },
            "required": []
        }
    },
    {
        "name": "get_open_orders",
        "description": (
            "Bir hesaptaki TÜM açık emirleri getir: sembol, yön (BUY/SELL), "
            "miktar, fiyat, emir tipi, hangi motor tarafından oluşturuldu (tag). "
            "Emir-pozisyon uyumunu kontrol etmek için kullan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {
                    "type": "string",
                    "description": "Hesap ID: 'HAMPRO' veya 'IBKR_PED'. Boş bırakılırsa tümü."
                }
            },
            "required": []
        }
    },
    {
        "name": "get_fills_today",
        "description": (
            "Bugünkü fill'leri getir. Opsiyonel olarak tek sembol filtreleme. "
            "Her fill: sembol, yön, miktar, fiyat, zaman, hangi motor (tag), "
            "bench_chg (fill anındaki benchmark değişimi). "
            "Fill kalitesini ve motor performansını anlamak için kullan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Opsiyonel: belirli sembol filtresi"
                },
                "account_id": {
                    "type": "string",
                    "description": "Opsiyonel: belirli hesap filtresi"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_exposure_status",
        "description": (
            "Tüm hesapların exposure durumunu getir: "
            "current_pct, potential_pct, rejim (OFANSIF/GEÇİŞ/DEFANSİF), "
            "pot_max limiti, long/short dağılımı. "
            "Risk ve kapasite durumunu anlamak için kullan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_etf_data",
        "description": (
            "ETF fiyatlarını ve günlük değişimlerini getir: "
            "TLT, SPY, PFF, HYG, JNK, SJNK, VNQ, AGG. "
            "Preferred stock'ları etkileyen makro faktörleri anlamak için kullan. "
            "TLT ↑ → kuponlular ↓ (ters korelasyon), HYG ↓ → kredi spreadi açılıyor."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_qebench_performance",
        "description": (
            "QeBench (portföy vs benchmark) performans verilerini getir: "
            "outperform oranı, benchmark vs portföy değişim, "
            "en çok outperform/underperform eden hisseler. "
            "Stratejinin ne kadar iyi çalıştığını anlamak için kullan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {
                    "type": "string",
                    "description": "Hesap ID: 'HAMPRO' veya 'IBKR_PED'. Boş bırakılırsa tümü."
                }
            },
            "required": []
        }
    },
    {
        "name": "compare_symbols",
        "description": (
            "İki veya daha fazla sembolü yan yana karşılaştır: "
            "fiyat, GORT, bench_chg, ucuzluk/pahalılık, SMA, truth tick. "
            "Aynı gruptaki hisseleri karşılaştırmak veya "
            "anomali tespit etmek için kullan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Karşılaştırılacak semboller listesi (2-5 arası)"
                }
            },
            "required": ["symbols"]
        }
    },
    {
        "name": "search_by_criteria",
        "description": (
            "Belirli kriterlere göre hisse ara: "
            "GORT aralığı, ucuzluk skoru, grup, spread genişliği, "
            "bench_chg yönü. Fırsat veya risk taraması için kullan. "
            "Örnek: 'GORT < -2 olan heldkuponlu hisseleri bul'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "group": {
                    "type": "string",
                    "description": "Opsiyonel: DOS grup filtresi"
                },
                "gort_min": {
                    "type": "number",
                    "description": "Opsiyonel: minimum GORT değeri"
                },
                "gort_max": {
                    "type": "number",
                    "description": "Opsiyonel: maksimum GORT değeri"
                },
                "min_ucuzluk": {
                    "type": "number",
                    "description": "Opsiyonel: minimum ucuzluk skoru"
                },
                "min_pahalilik": {
                    "type": "number",
                    "description": "Opsiyonel: minimum pahalılık skoru"
                },
                "min_spread": {
                    "type": "number",
                    "description": "Opsiyonel: minimum spread ($)"
                },
                "sort_by": {
                    "type": "string",
                    "description": "Sıralama: 'gort', 'ucuzluk', 'pahalilik', 'bench_chg', 'spread'",
                    "enum": ["gort", "ucuzluk", "pahalilik", "bench_chg", "spread"]
                },
                "limit": {
                    "type": "integer",
                    "description": "Maksimum sonuç sayısı (default: 10)",
                    "default": 10
                }
            },
            "required": []
        }
    },
    {
        "name": "get_order_fill_analysis",
        "description": (
            "Açık emirlerin ve bugünkü fill'lerin detaylı performans analizi. "
            "Her açık emir için: kaç dakikadır bekliyor, truth tick şu an nerede, "
            "fill alabilir mi (spread/price uzaklığı), hangi engine gönderdi. "
            "Her fill için: fill fiyatı, şu anki truth tick, unrealized PnL, engine tag. "
            "Engine bazlı fill oranları ve NEWCLMM özel metrikleri. "
            "Neden fill alamadığımızı veya neden kâr edemediğimizi anlamak için kullan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {
                    "type": "string",
                    "description": "Hesap ID: 'HAMPRO' veya 'IBKR_PED'. Boş bırakılırsa tümü."
                }
            },
            "required": []
        }
    },
]


# ═══════════════════════════════════════════════════════════════
# TOOL IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════

def _get_redis():
    """Get Redis sync client."""
    try:
        from app.core.redis_client import get_redis_client
        client = get_redis_client()
        return getattr(client, 'sync', client)
    except Exception:
        import redis
        return redis.Redis(host='localhost', port=6379, db=0)


def _get_fabric():
    """Get DataFabric instance."""
    try:
        from app.core.data_fabric import DataFabric
        return DataFabric()
    except Exception:
        return None


def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """
    Execute a tool and return JSON result string.
    This is the main dispatcher called by the agent loop.
    """
    try:
        handlers = {
            "get_symbol_detail": _tool_symbol_detail,
            "get_truth_tick_history": _tool_truth_tick_history,
            "get_group_analysis": _tool_group_analysis,
            "get_positions": _tool_positions,
            "get_open_orders": _tool_open_orders,
            "get_fills_today": _tool_fills_today,
            "get_exposure_status": _tool_exposure_status,
            "get_etf_data": _tool_etf_data,
            "get_qebench_performance": _tool_qebench,
            "compare_symbols": _tool_compare_symbols,
            "search_by_criteria": _tool_search_criteria,
            "get_order_fill_analysis": _tool_order_fill_analysis,
        }
        
        handler = handlers.get(tool_name)
        if not handler:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        
        result = handler(tool_input)
        return json.dumps(result, ensure_ascii=False, default=str)
        
    except Exception as e:
        logger.error(f"[QAGENTT-TOOLS] Error executing {tool_name}: {e}")
        return json.dumps({"error": str(e)})


# ─── Individual Tool Implementations ─────────────────────────

def _tool_symbol_detail(params: Dict) -> Dict:
    """Full detail for a single symbol."""
    symbol = params.get("symbol", "")
    fabric = _get_fabric()
    redis_client = _get_redis()
    
    if not fabric or not fabric.is_ready():
        return {"error": "DataFabric not available"}
    
    snap = fabric.get_fast_snapshot(symbol)
    if not snap:
        return {"error": f"Symbol '{symbol}' not found or no live data"}
    
    result = {
        "symbol": symbol,
        "group": snap.get('GROUP', ''),
        "cgrup": snap.get('CGRUP', ''),
        "bid": float(snap.get('bid', 0) or 0),
        "ask": float(snap.get('ask', 0) or 0),
        "last": float(snap.get('last', 0) or 0),
        "spread": round(float(snap.get('ask', 0) or 0) - float(snap.get('bid', 0) or 0), 3),
        "daily_chg": round(float(snap.get('daily_chg', 0) or 0), 3),
        "bench_chg": round(float(snap.get('bench_chg', 0) or 0), 3),
        "GORT": round(float(snap.get('GORT', 0) or 0), 2),
        "FINAL_THG": round(float(snap.get('FINAL_THG', 0) or 0), 1),
        "SHORT_FINAL": round(float(snap.get('SHORT_FINAL', 0) or 0), 1),
        "FBTOT": round(float(snap.get('Fbtot', 0) or 0), 2),
        "SFSTOT": round(float(snap.get('SFStot', 0) or 0), 2),
        "SMA63chg": round(float(snap.get('SMA63chg', 0) or 0), 3),
        "SMA246chg": round(float(snap.get('SMA246chg', 0) or 0), 3),
        "ucuzluk_skoru": round(float(snap.get('Bid_buy_ucuzluk_skoru', 0) or 0), 3),
        "pahalilik_skoru": round(float(snap.get('Ask_sell_pahalilik_skoru', 0) or 0), 3),
        "AVG_ADV": int(float(snap.get('AVG_ADV', 0) or 0)),
        "par_value": float(snap.get('PAR', 25) or 25),
    }
    
    # Add L1 data from Redis
    try:
        raw = redis_client.get(f"market:l1:{symbol}")
        if raw:
            l1 = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            result["l1_ts"] = l1.get("ts")
            result["l1_age_sec"] = round(time.time() - float(l1.get("ts", 0))) if l1.get("ts") else None
    except Exception:
        pass
    
    # Add latest truth tick from canonical source: tt:ticks:{symbol}
    try:
        raw = redis_client.get(f"tt:ticks:{symbol}")
        if raw:
            ticks = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            if ticks and isinstance(ticks, list) and len(ticks) > 0:
                # Get the last tick
                last_tick = ticks[-1]
                result["truth_tick"] = {
                    "price": last_tick.get("price"),
                    "venue": last_tick.get("exch") or last_tick.get("venue"),
                    "size": last_tick.get("size"),
                    "age_sec": round(time.time() - float(last_tick.get("ts", 0))) if last_tick.get("ts") else None,
                }
                result["truth_tick_count"] = len(ticks)
    except Exception:
        pass
    
    return result


def _tool_truth_tick_history(params: Dict) -> Dict:
    """Truth tick history with volav analysis."""
    symbol = params.get("symbol", "")
    last_n = min(params.get("last_n", 20), 50)
    redis_client = _get_redis()
    
    result = {"symbol": symbol, "ticks": [], "volav": None, "temporal": None}
    
    try:
        # Get truth tick inspect data (canonical key: truth_ticks:inspect:{symbol})
        raw = redis_client.get(f"truth_ticks:inspect:{symbol}")
        if raw:
            data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            
            # Path dataset (tick history)
            path = data.get("path_dataset", [])
            recent = path[-last_n:] if path else []
            result["ticks"] = [
                {
                    "time": datetime.fromtimestamp(t.get("timestamp", 0)).strftime("%H:%M:%S") if t.get("timestamp") else "?",
                    "price": round(t.get("price", 0), 2),
                    "size": t.get("size", 0),
                    "venue": t.get("venue", "?"),
                }
                for t in recent
            ]
            result["total_ticks"] = len(path)
            
            # Volav summary (market microstructure state)
            summary = data.get("summary", {})
            if summary:
                result["volav"] = {
                    "state": summary.get("state", "UNKNOWN"),
                    "confidence": summary.get("state_conf", 0),
                    "v1_shift": summary.get("v1_shift"),
                    "avg_lot": summary.get("avg_lot"),
                }
            
            # Temporal analysis (price changes over time windows)
            temporal = data.get("temporal_analysis", {})
            if temporal:
                result["temporal"] = temporal
            
    except Exception as e:
        result["error"] = str(e)
    
    # Fallback: if inspect data was empty, try canonical tt:ticks:{symbol}
    if not result["ticks"]:
        try:
            raw = redis_client.get(f"tt:ticks:{symbol}")
            if raw:
                ticks = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                if ticks and isinstance(ticks, list):
                    recent = ticks[-last_n:]
                    result["ticks"] = [
                        {
                            "time": datetime.fromtimestamp(t.get("ts", 0)).strftime("%H:%M:%S") if t.get("ts") else "?",
                            "price": round(t.get("price", 0), 2),
                            "size": t.get("size", 0),
                            "venue": t.get("exch") or t.get("venue", "?"),
                        }
                        for t in recent
                    ]
                    result["total_ticks"] = len(ticks)
                    result["source"] = "tt:ticks (canonical)"
        except Exception:
            pass
    
    # Also add latest single truth tick from canonical source
    try:
        raw = redis_client.get(f"tt:ticks:{symbol}")
        if raw:
            ticks = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            if ticks and isinstance(ticks, list) and len(ticks) > 0:
                last_tick = ticks[-1]
                result["latest"] = {
                    "price": last_tick.get("price"),
                    "venue": last_tick.get("exch") or last_tick.get("venue"),
                    "size": last_tick.get("size"),
                    "age_sec": round(time.time() - float(last_tick.get("ts", 0))) if last_tick.get("ts") else None,
                }
    except Exception:
        pass
    
    return result


def _tool_group_analysis(params: Dict) -> Dict:
    """All symbols in a DOS group with metrics."""
    group_name = params.get("group_name", "")
    fabric = _get_fabric()
    
    if not fabric or not fabric.is_ready():
        return {"error": "DataFabric not available"}
    
    all_symbols = fabric.get_all_static_symbols()
    members = []
    
    for symbol in all_symbols:
        snap = fabric.get_fast_snapshot(symbol)
        if not snap:
            continue
        if snap.get('GROUP', '') != group_name:
            continue
        
        last = float(snap.get('last', 0) or 0)
        if last <= 0:
            continue
        
        members.append({
            "s": symbol,
            "cg": snap.get('CGRUP', ''),
            "last": round(last, 2),
            "gort": round(float(snap.get('GORT', 0) or 0), 2),
            "bc": round(float(snap.get('bench_chg', 0) or 0), 3),
            "dc": round(float(snap.get('daily_chg', 0) or 0), 3),
            "uc": round(float(snap.get('Bid_buy_ucuzluk_skoru', 0) or 0), 3),
            "ph": round(float(snap.get('Ask_sell_pahalilik_skoru', 0) or 0), 3),
            "sp": round(
                float(snap.get('ask', 0) or 0) - float(snap.get('bid', 0) or 0), 3
            ),
            "adv": int(float(snap.get('AVG_ADV', 0) or 0)),
            "thg": round(float(snap.get('FINAL_THG', 0) or 0), 1),
        })
    
    if not members:
        return {"error": f"Group '{group_name}' not found or empty"}
    
    # Compute group summary
    gorts = [m["gort"] for m in members if m["gort"] != 0]
    bcs = [m["bc"] for m in members]
    dcs = [m["dc"] for m in members]
    
    members_sorted = sorted(members, key=lambda x: x["gort"])
    
    return {
        "group": group_name,
        "count": len(members),
        "avg_gort": round(sum(gorts) / len(gorts), 2) if gorts else 0,
        "avg_bench_chg": round(sum(bcs) / len(bcs), 3) if bcs else 0,
        "avg_daily_chg": round(sum(dcs) / len(dcs), 3) if dcs else 0,
        "best_performer": members_sorted[-1] if members_sorted else None,
        "worst_performer": members_sorted[0] if members_sorted else None,
        "members": members_sorted,
    }


def _tool_positions(params: Dict) -> Dict:
    """Get positions from Redis."""
    account_id = params.get("account_id")
    redis_client = _get_redis()
    
    accounts = [account_id] if account_id else ["HAMPRO", "IBKR_PED", "IBKR_GUN"]
    result = {}
    
    for acct in accounts:
        try:
            raw = redis_client.get(f"psfalgo:unified_positions:{acct}")
            if raw:
                positions = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                compact = []
                for p in positions:
                    qty = float(p.get('qty', 0) or 0)
                    if abs(qty) < 0.01:
                        continue
                    compact.append({
                        "symbol": p.get('symbol', ''),
                        "qty": qty,
                        "befday_qty": float(p.get('befday_qty', 0) or 0),
                        "potential_qty": float(p.get('potential_qty', 0) or 0),
                        "current_price": float(p.get('current_price', 0) or 0),
                        "direction": "LONG" if qty > 0 else "SHORT",
                    })
                result[acct] = {
                    "count": len(compact),
                    "long_count": sum(1 for p in compact if p["qty"] > 0),
                    "short_count": sum(1 for p in compact if p["qty"] < 0),
                    "positions": compact,
                }
        except Exception as e:
            result[acct] = {"error": str(e)}
    
    return result


def _tool_open_orders(params: Dict) -> Dict:
    """Get open orders from Redis."""
    account_id = params.get("account_id")
    redis_client = _get_redis()
    
    accounts = [account_id] if account_id else ["HAMPRO", "IBKR_PED", "IBKR_GUN"]
    result = {}
    
    for acct in accounts:
        try:
            raw = redis_client.get(f"psfalgo:open_orders:{acct}")
            if raw:
                data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                orders = data if isinstance(data, list) else data.get('orders', [])
                result[acct] = {
                    "count": len(orders),
                    "orders": orders[:50],  # Cap at 50
                }
            else:
                result[acct] = {"count": 0, "orders": []}
        except Exception as e:
            result[acct] = {"error": str(e)}
    
    return result


def _tool_fills_today(params: Dict) -> Dict:
    """Get today's fills."""
    symbol_filter = params.get("symbol")
    account_filter = params.get("account_id")
    redis_client = _get_redis()
    
    fills = []
    
    # Read from fill streams in Redis
    accounts = [account_filter] if account_filter else ["HAMPRO", "IBKR_PED", "IBKR_GUN"]
    
    for acct in accounts:
        try:
            raw = redis_client.get(f"psfalgo:todays_fills:{acct}")
            if raw:
                data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                fill_list = data if isinstance(data, list) else data.get('fills', [])
                for f in fill_list:
                    sym = f.get('symbol', '')
                    if symbol_filter and sym != symbol_filter:
                        continue
                    fills.append({
                        "account": acct,
                        "symbol": sym,
                        "action": f.get('action', ''),
                        "qty": float(f.get('qty', 0) or 0),
                        "price": float(f.get('price', 0) or 0),
                        "time": f.get('time', ''),
                        "tag": f.get('tag', ''),
                        "bench_chg": float(f.get('bench_chg', 0) or 0),
                    })
        except Exception:
            pass
    
    return {
        "count": len(fills),
        "fills": fills,
        "filter": {"symbol": symbol_filter, "account": account_filter},
    }


def _tool_exposure_status(params: Dict) -> Dict:
    """Get exposure status for all accounts."""
    redis_client = _get_redis()
    result = {}
    
    for acct in ["HAMPRO", "IBKR_PED", "IBKR_GUN"]:
        try:
            raw = redis_client.get(f"psfalgo:exposure:{acct}")
            if raw:
                data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                result[acct] = data
            else:
                # Fallback: try live calculation
                try:
                    import asyncio
                    from app.psfalgo.exposure_calculator import calculate_exposure_for_account
                    
                    loop = asyncio.get_event_loop()
                    if not loop.is_running():
                        exposure = loop.run_until_complete(calculate_exposure_for_account(acct))
                        if exposure and exposure.pot_max > 0:
                            result[acct] = {
                                "pot_total": round(exposure.pot_total, 2),
                                "pot_max": round(exposure.pot_max, 2),
                                "exposure_pct": round(exposure.pot_total / exposure.pot_max * 100, 2),
                                "mode": exposure.mode,
                                "source": "live_calc",
                            }
                        else:
                            result[acct] = {"status": "no_positions"}
                    else:
                        result[acct] = {"status": "no_cache_async_running"}
                except Exception as e:
                    result[acct] = {"status": "no_cache", "error": str(e)}
        except Exception as e:
            result[acct] = {"error": str(e)}
    
    # Also get pot_max
    try:
        raw = redis_client.get("psfalgo:pot_max")
        if raw:
            result["pot_max"] = float(raw.decode() if isinstance(raw, bytes) else raw)
    except Exception:
        pass
    
    return result


def _tool_etf_data(params: Dict) -> Dict:
    """Get ETF prices and daily changes."""
    fabric = _get_fabric()
    
    if not fabric:
        return {"error": "DataFabric not available"}
    
    etf_symbols = ["TLT", "SPY", "PFF", "HYG", "JNK", "SJNK", "VNQ", "AGG"]
    result = {}
    
    for sym in etf_symbols:
        try:
            live = fabric.get_etf_live(sym)
            prev_close = fabric.get_etf_prev_close(sym)
            
            if live:
                last = float(live.get('last', 0) or 0)
                pc = float(prev_close) if prev_close else 0
                daily_chg = round(last - pc, 3) if pc > 0 else 0
                daily_pct = round((last - pc) / pc * 100, 2) if pc > 0 else 0
                
                result[sym] = {
                    "last": round(last, 2),
                    "daily_chg": daily_chg,
                    "daily_pct": daily_pct,
                    "prev_close": round(pc, 2),
                }
        except Exception:
            pass
    
    return result


def _tool_qebench(params: Dict) -> Dict:
    """Get QeBench performance data."""
    account_id = params.get("account_id")
    redis_client = _get_redis()
    
    accounts = [account_id] if account_id else ["HAMPRO", "IBKR_PED"]
    result = {}
    
    for acct in accounts:
        try:
            # Map account to qebench key
            key_map = {"HAMPRO": "hamproqebench", "IBKR_PED": "ibpedqebench"}
            key_prefix = key_map.get(acct, acct.lower() + "qebench")
            
            raw = redis_client.get(f"psfalgo:{key_prefix}:summary")
            if raw:
                data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                result[acct] = data
            else:
                result[acct] = {"status": "no data"}
        except Exception as e:
            result[acct] = {"error": str(e)}
    
    return result


def _tool_compare_symbols(params: Dict) -> Dict:
    """Compare multiple symbols side by side."""
    symbols = params.get("symbols", [])[:5]  # Max 5
    fabric = _get_fabric()
    
    if not fabric or not fabric.is_ready():
        return {"error": "DataFabric not available"}
    
    comparisons = []
    for symbol in symbols:
        snap = fabric.get_fast_snapshot(symbol)
        if not snap:
            comparisons.append({"symbol": symbol, "error": "not found"})
            continue
        
        comparisons.append({
            "symbol": symbol,
            "group": snap.get('GROUP', ''),
            "last": round(float(snap.get('last', 0) or 0), 2),
            "GORT": round(float(snap.get('GORT', 0) or 0), 2),
            "bench_chg": round(float(snap.get('bench_chg', 0) or 0), 3),
            "daily_chg": round(float(snap.get('daily_chg', 0) or 0), 3),
            "ucuzluk": round(float(snap.get('Bid_buy_ucuzluk_skoru', 0) or 0), 3),
            "pahalilik": round(float(snap.get('Ask_sell_pahalilik_skoru', 0) or 0), 3),
            "SMA63chg": round(float(snap.get('SMA63chg', 0) or 0), 3),
            "spread": round(
                float(snap.get('ask', 0) or 0) - float(snap.get('bid', 0) or 0), 3
            ),
            "FINAL_THG": round(float(snap.get('FINAL_THG', 0) or 0), 1),
            "SHORT_FINAL": round(float(snap.get('SHORT_FINAL', 0) or 0), 1),
        })
    
    return {"comparison": comparisons}


def _tool_search_criteria(params: Dict) -> Dict:
    """Search symbols by criteria."""
    fabric = _get_fabric()
    
    if not fabric or not fabric.is_ready():
        return {"error": "DataFabric not available"}
    
    group_filter = params.get("group")
    gort_min = params.get("gort_min")
    gort_max = params.get("gort_max")
    min_ucuzluk = params.get("min_ucuzluk")
    min_pahalilik = params.get("min_pahalilik")
    min_spread = params.get("min_spread")
    sort_by = params.get("sort_by", "gort")
    limit = min(params.get("limit", 10), 30)
    
    all_symbols = fabric.get_all_static_symbols()
    matches = []
    
    for symbol in all_symbols:
        snap = fabric.get_fast_snapshot(symbol)
        if not snap or not snap.get('_has_live'):
            continue
        
        last = float(snap.get('last', 0) or 0)
        if last <= 0:
            continue
        
        group = snap.get('GROUP', '')
        gort = float(snap.get('GORT', 0) or 0)
        uc = float(snap.get('Bid_buy_ucuzluk_skoru', 0) or 0)
        ph = float(snap.get('Ask_sell_pahalilik_skoru', 0) or 0)
        spread = float(snap.get('ask', 0) or 0) - float(snap.get('bid', 0) or 0)
        bc = float(snap.get('bench_chg', 0) or 0)
        
        # Apply filters
        if group_filter and group != group_filter:
            continue
        if gort_min is not None and gort < gort_min:
            continue
        if gort_max is not None and gort > gort_max:
            continue
        if min_ucuzluk is not None and uc < min_ucuzluk:
            continue
        if min_pahalilik is not None and ph < min_pahalilik:
            continue
        if min_spread is not None and spread < min_spread:
            continue
        
        matches.append({
            "s": symbol,
            "g": group,
            "last": round(last, 2),
            "gort": round(gort, 2),
            "bc": round(bc, 3),
            "uc": round(uc, 3),
            "ph": round(ph, 3),
            "sp": round(spread, 3),
            "thg": round(float(snap.get('FINAL_THG', 0) or 0), 1),
        })
    
    # Sort
    sort_keys = {
        "gort": lambda x: x["gort"],
        "ucuzluk": lambda x: -x["uc"],
        "pahalilik": lambda x: -x["ph"],
        "bench_chg": lambda x: x["bc"],
        "spread": lambda x: -x["sp"],
    }
    sort_fn = sort_keys.get(sort_by, sort_keys["gort"])
    matches.sort(key=sort_fn)
    
    return {
        "total_matches": len(matches),
        "showing": min(limit, len(matches)),
        "filters": {k: v for k, v in params.items() if v is not None},
        "results": matches[:limit],
    }


def _tool_order_fill_analysis(params: Dict) -> Dict:
    """
    Detailed order execution + fill performance analysis.
    
    Provides:
    1. Open orders with truth tick context (distance, age, fill probability)
    2. Today's fills with unrealized PnL tracking
    3. Engine-level fill statistics
    """
    account_filter = params.get("account_id")
    redis_client = _get_redis()
    fabric = _get_fabric()
    
    result = {
        "open_orders_analysis": [],
        "fill_pff_analysis": [],
        "engine_stats": {},
        "summary": {},
    }
    
    now = time.time()
    
    # ── 1. OPEN ORDERS ANALYSIS ──
    # Get open orders
    accounts = [account_filter] if account_filter else ["HAMPRO", "IBKR_PED"]
    all_open_orders = []
    
    for acct in accounts:
        try:
            raw = redis_client.get(f"psfalgo:open_orders:{acct}")
            if raw:
                data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                orders = data if isinstance(data, list) else data.get('orders', [])
                for o in orders:
                    o['_account'] = acct
                all_open_orders.extend(orders)
        except Exception:
            pass
    
    for order in all_open_orders[:50]:  # Cap at 50
        sym = order.get('symbol', '')
        action = order.get('action', '')
        order_price = float(order.get('price', 0) or 0)
        tag = order.get('tag', order.get('engine', ''))
        acct = order.get('_account', '')
        created_ts = float(order.get('created_ts', order.get('ts', 0)) or 0)
        age_min = round((now - created_ts) / 60, 1) if created_ts > 0 else None
        
        # Detect engine from tag
        engine = 'UNKNOWN'
        tag_upper = (tag or '').upper()
        if 'NEWC' in tag_upper:
            engine = 'NEWC'
        elif 'KARBOTU' in tag_upper or 'KBOT' in tag_upper:
            engine = 'KARBOTU'
        elif 'PATADD' in tag_upper or 'PAT' in tag_upper:
            engine = 'PATADD'
        elif 'LT_TRIM' in tag_upper or 'LTTRIM' in tag_upper or 'LT_' in tag_upper:
            engine = 'LT_TRIM'
        elif 'ADDNEW' in tag_upper or 'ANP' in tag_upper:
            engine = 'ADDNEWPOS'
        elif 'REV' in tag_upper:
            engine = 'REV'
        elif 'MM' in tag_upper:
            engine = 'MM'
        
        # Get truth tick for this symbol
        tt_price = None
        bid = None
        ask = None
        spread = None
        try:
            tt_raw = redis_client.get(f"tt:ticks:{sym}")
            if tt_raw:
                ticks = json.loads(tt_raw.decode() if isinstance(tt_raw, bytes) else tt_raw)
                if ticks and isinstance(ticks, list):
                    tt_price = float(ticks[-1].get('price', 0))
        except Exception:
            pass
        
        # Get L1 for bid/ask
        if fabric and fabric.is_ready():
            try:
                snap = fabric.get_fast_snapshot(sym)
                if snap:
                    bid = float(snap.get('bid', 0) or 0)
                    ask = float(snap.get('ask', 0) or 0)
                    spread = round(ask - bid, 3) if bid > 0 and ask > 0 else None
            except Exception:
                pass
        
        # Calculate distance and fill probability
        distance_cents = None
        fill_status = 'UNKNOWN'
        
        if order_price > 0 and tt_price and tt_price > 0:
            if action.upper() == 'BUY':
                distance_cents = round((tt_price - order_price) * 100, 1)
                if distance_cents <= 2:
                    fill_status = 'LIKELY_FILL'
                elif distance_cents <= 8:
                    fill_status = 'WAITING'
                else:
                    fill_status = 'UNLIKELY'
            elif action.upper() in ('SELL', 'SHORT'):
                distance_cents = round((order_price - tt_price) * 100, 1)
                if distance_cents <= 2:
                    fill_status = 'LIKELY_FILL'
                elif distance_cents <= 8:
                    fill_status = 'WAITING'
                else:
                    fill_status = 'UNLIKELY'
        
        if age_min and age_min > 10:
            fill_status = 'STALE' if fill_status != 'LIKELY_FILL' else fill_status
        
        result["open_orders_analysis"].append({
            "symbol": sym,
            "account": acct,
            "action": action,
            "order_price": order_price,
            "tag": tag,
            "engine": engine,
            "age_min": age_min,
            "truth_tick_now": tt_price,
            "bid": bid,
            "ask": ask,
            "spread": spread,
            "distance_cents": distance_cents,
            "fill_status": fill_status,
        })
    
    # ── 2. FILL + TRUTH TICK ANALYSIS ──
    all_fills = []
    for acct in accounts:
        try:
            raw = redis_client.get(f"psfalgo:todays_fills:{acct}")
            if raw:
                data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                fill_list = data if isinstance(data, list) else data.get('fills', [])
                for f in fill_list:
                    f['_account'] = acct
                all_fills.extend(fill_list)
        except Exception:
            pass
    
    # Engine counters for stats
    engine_sent = {}   # from open orders
    engine_filled = {} # from fills
    engine_pnl = {}    # NEWC specific
    
    # Count open orders by engine
    for oa in result["open_orders_analysis"]:
        eng = oa["engine"]
        engine_sent[eng] = engine_sent.get(eng, 0) + 1
    
    for fill in all_fills[:100]:  # Cap at 100
        sym = fill.get('symbol', '')
        action = fill.get('action', '')
        fill_price = float(fill.get('price', 0) or 0)
        fill_time = fill.get('time', '')
        tag = fill.get('tag', '')
        acct = fill.get('_account', '')
        
        # Detect engine
        engine = 'UNKNOWN'
        tag_upper = (tag or '').upper()
        if 'NEWC' in tag_upper:
            engine = 'NEWC'
        elif 'KARBOTU' in tag_upper or 'KBOT' in tag_upper:
            engine = 'KARBOTU'
        elif 'PATADD' in tag_upper or 'PAT' in tag_upper:
            engine = 'PATADD'
        elif 'LT_TRIM' in tag_upper or 'LTTRIM' in tag_upper or 'LT_' in tag_upper:
            engine = 'LT_TRIM'
        elif 'ADDNEW' in tag_upper or 'ANP' in tag_upper:
            engine = 'ADDNEWPOS'
        elif 'REV' in tag_upper:
            engine = 'REV'
        elif 'MM' in tag_upper:
            engine = 'MM'
        
        engine_filled[engine] = engine_filled.get(engine, 0) + 1
        
        # Get current truth tick for unrealized PnL
        tt_now = None
        try:
            tt_raw = redis_client.get(f"tt:ticks:{sym}")
            if tt_raw:
                ticks = json.loads(tt_raw.decode() if isinstance(tt_raw, bytes) else tt_raw)
                if ticks and isinstance(ticks, list):
                    tt_now = float(ticks[-1].get('price', 0))
        except Exception:
            pass
        
        # Compute unrealized PnL
        unrealized_pnl_cents = None
        pnl_status = 'UNKNOWN'
        if fill_price > 0 and tt_now and tt_now > 0:
            if action.upper() == 'BUY':
                unrealized_pnl_cents = round((tt_now - fill_price) * 100, 1)
            elif action.upper() in ('SELL', 'SHORT'):
                unrealized_pnl_cents = round((fill_price - tt_now) * 100, 1)
            
            if unrealized_pnl_cents is not None:
                if unrealized_pnl_cents > 2:
                    pnl_status = 'IN_PROFIT'
                elif unrealized_pnl_cents >= -2:
                    pnl_status = 'BREAKEVEN'
                else:
                    pnl_status = 'IN_LOSS'
                
                # Track NEWC PnL
                if engine == 'NEWC':
                    if engine not in engine_pnl:
                        engine_pnl[engine] = []
                    engine_pnl[engine].append(unrealized_pnl_cents)
        
        result["fill_pff_analysis"].append({
            "symbol": sym,
            "account": acct,
            "action": action,
            "fill_price": fill_price,
            "fill_time": fill_time,
            "tag": tag,
            "engine": engine,
            "truth_tick_now": tt_now,
            "unrealized_pnl_cents": unrealized_pnl_cents,
            "pnl_status": pnl_status,
        })
    
    # ── 3. ENGINE STATS ──
    all_engines = set(list(engine_sent.keys()) + list(engine_filled.keys()))
    for eng in all_engines:
        sent = engine_sent.get(eng, 0)
        filled = engine_filled.get(eng, 0)
        total = sent + filled  # sent = still open, filled = completed
        stat = {
            "open": sent,
            "filled": filled,
            "total_today": total,
            "fill_rate": round(filled / total * 100, 1) if total > 0 else 0,
        }
        if eng in engine_pnl and engine_pnl[eng]:
            pnls = engine_pnl[eng]
            stat["avg_pnl_cents"] = round(sum(pnls) / len(pnls), 1)
            stat["wins"] = sum(1 for p in pnls if p > 2)
            stat["losses"] = sum(1 for p in pnls if p < -2)
            stat["win_rate"] = round(stat["wins"] / len(pnls) * 100, 1) if pnls else 0
        result["engine_stats"][eng] = stat
    
    # ── 4. SUMMARY ──
    open_analysis = result["open_orders_analysis"]
    stale = sum(1 for o in open_analysis if o.get("fill_status") == 'STALE')
    unlikely = sum(1 for o in open_analysis if o.get("fill_status") == 'UNLIKELY')
    in_profit = sum(1 for f in result["fill_pff_analysis"] if f.get("pnl_status") == 'IN_PROFIT')
    in_loss = sum(1 for f in result["fill_pff_analysis"] if f.get("pnl_status") == 'IN_LOSS')
    
    result["summary"] = {
        "total_open_orders": len(open_analysis),
        "stale_orders": stale,
        "unlikely_fills": unlikely,
        "likely_fills": sum(1 for o in open_analysis if o.get("fill_status") == 'LIKELY_FILL'),
        "total_fills_today": len(all_fills),
        "fills_in_profit": in_profit,
        "fills_in_loss": in_loss,
        "fills_breakeven": sum(1 for f in result["fill_pff_analysis"] if f.get("pnl_status") == 'BREAKEVEN'),
    }
    
    return result
