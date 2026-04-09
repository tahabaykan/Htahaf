"""
Ex-Dividend Analysis API Routes
================================

Endpoints for triggering and viewing ex-div pattern analysis.
"""

from fastapi import APIRouter, Query
from typing import Optional, List
from app.core.logger import logger

router = APIRouter(prefix="/api/exdiv", tags=["Ex-Dividend Analysis"])


@router.post("/analyze")
async def start_analysis(
    api_key: Optional[str] = None,
    tickers: Optional[str] = Query(default=None, description="Comma-separated tickers, e.g. 'F PRB,DLR PRJ'"),
    max_stocks: int = Query(default=0, ge=0, description="Max stocks to analyze (0=all)"),
):
    """Ex-div pattern analizini başlat (Gemini Flash ile)."""
    from app.agent.exdiv_analyzer import start_exdiv_analysis
    
    ticker_list = None
    if tickers:
        ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
    
    try:
        analyzer = await start_exdiv_analysis(
            api_key=api_key or "",
            tickers=ticker_list,
            max_stocks=max_stocks,
        )
        summary = analyzer.get_summary()
        return {
            "status": "completed",
            "total_analyzed": len(summary),
            "summary": summary[:20],  # İlk 20
        }
    except Exception as e:
        logger.error(f"[EXDIV API] Analysis error: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/analyze-single")
async def analyze_single_stock(
    ticker: str = Query(..., description="Stock ticker, e.g. 'F PRB'"),
    api_key: Optional[str] = None,
):
    """Tek hisse için detaylı ex-div analizi."""
    from app.agent.exdiv_analyzer import get_exdiv_analyzer, ExDivFlashAnalyzer
    
    analyzer = get_exdiv_analyzer()
    if analyzer is None:
        analyzer = ExDivFlashAnalyzer(gemini_api_key=api_key or "")
        analyzer.load_data()
    
    try:
        result = await analyzer.analyze_single(ticker)
        if result is None:
            return {"status": "skipped", "ticker": ticker, 
                    "message": "No data or insufficient cycles"}
        
        # daily_stats çok büyük, sadece önemli günleri döndür
        important_days = [d for d in result['patterns']['daily_stats'] 
                         if abs(d['day']) <= 10 or d['day'] % 5 == 0]
        
        return {
            "status": "ok",
            "ticker": ticker,
            "div_amount": result['div_amount'],
            "yield_pct": round(result.get('yield_pct', 0), 1),
            "price_summary": result['price_summary'],
            "exdiv": {
                "n_cycles": result['exdiv']['n_cycles'],
                "quality": result['exdiv']['quality'],
                "avg_cycle": result['exdiv']['avg_cycle_len'],
                "dates": result['exdiv']['exdiv_dates'],
            },
            "pattern": {
                "strength": result['patterns']['pattern_strength'],
                "windows": result['patterns']['windows'],
                "signals": result['patterns']['signals'],
                "daily_important": important_days,
            },
            "prediction": result['prediction'],
            "flash_insight": result.get('flash_insight', {}),
        }
    except Exception as e:
        logger.error(f"[EXDIV API] Single analysis error: {e}")
        return {"status": "error", "ticker": ticker, "message": str(e)}


@router.get("/stocks")
async def list_available_stocks():
    """UTALLDATA'daki mevcut hisse listesi."""
    from app.agent.exdiv_analyzer import ExDivFlashAnalyzer
    
    analyzer = ExDivFlashAnalyzer()
    analyzer.load_data()
    
    stocks = analyzer.get_available_stocks()
    
    # Div bilgisi olan/olmayan ayrımı
    with_div = [t for t in stocks if t in analyzer.div_info]
    without_div = [t for t in stocks if t not in analyzer.div_info]
    
    return {
        "total": len(stocks),
        "with_div_info": len(with_div),
        "without_div_info": len(without_div),
        "missing_div_tickers": without_div,
        "all_tickers": stocks,
    }


@router.get("/results")
async def get_results(
    sort_by: str = Query(default="pattern_strength", 
                        description="Sort field: pattern_strength, yield_pct, next_exdiv_days, flash_score"),
    top_n: int = Query(default=50, ge=1, le=200),
):
    """Analiz sonuçlarının özeti."""
    from app.agent.exdiv_analyzer import get_exdiv_analyzer
    
    analyzer = get_exdiv_analyzer()
    if analyzer is None:
        return {"status": "not_started", "message": "Run /analyze first"}
    
    summary = analyzer.get_summary()
    
    # Sort
    reverse = True
    if sort_by == 'next_exdiv_days':
        reverse = False  # Yaklaşanlara göre sırala
    
    summary.sort(key=lambda x: x.get(sort_by, 0), reverse=reverse)
    
    return {
        "status": "ok",
        "total": len(summary),
        "sort_by": sort_by,
        "results": summary[:top_n],
    }


@router.get("/upcoming")
async def get_upcoming_exdivs(
    days_ahead: int = Query(default=30, ge=1, le=90),
):
    """Yaklaşan ex-div tarihleri."""
    from app.agent.exdiv_analyzer import get_exdiv_analyzer
    
    analyzer = get_exdiv_analyzer()
    if analyzer is None:
        return {"status": "not_started", "message": "Run /analyze first"}
    
    upcoming = []
    for tk, r in analyzer.results.items():
        pred = r.get('prediction', {})
        days = pred.get('days_away', 999)
        if 0 < days <= days_ahead:
            signals = r.get('patterns', {}).get('signals', [])
            flash = r.get('flash_insight', {})
            
            upcoming.append({
                'ticker': tk,
                'predicted_date': pred.get('predicted_date', ''),
                'days_away': days,
                'div_amount': r['div_amount'],
                'yield_pct': round(r.get('yield_pct', 0), 1),
                'pattern_strength': r['patterns']['pattern_strength'],
                'signals': [s['action'] for s in signals if s.get('significant')],
                'flash_strategy': flash.get('recommended_strategy', ''),
                'flash_score': flash.get('overall_score', 0),
            })
    
    upcoming.sort(key=lambda x: x['days_away'])
    
    return {
        "status": "ok",
        "days_ahead": days_ahead,
        "count": len(upcoming),
        "upcoming": upcoming,
    }


@router.get("/detail/{ticker}")
async def get_stock_detail(ticker: str):
    """Tek hissenin detaylı analiz sonucu (Redis'ten)."""
    import json
    try:
        from app.core.redis_client import get_redis_client
        rc = get_redis_client()
        sync_rc = getattr(rc, 'sync', rc)
        safe = ticker.replace(" ", "_")
        data = sync_rc.get(f"psfalgo:exdiv:analysis:{safe}")
        if data:
            if isinstance(data, bytes):
                data = data.decode()
            return {"status": "ok", "data": json.loads(data)}
    except Exception as e:
        logger.warning(f"[EXDIV API] Redis read error: {e}")
    
    # Fallback: in-memory
    from app.agent.exdiv_analyzer import get_exdiv_analyzer
    analyzer = get_exdiv_analyzer()
    if analyzer and ticker in analyzer.results:
        r = analyzer.results[ticker]
        return {
            "status": "ok",
            "data": {
                'ticker': ticker,
                'div_amount': r['div_amount'],
                'exdiv_quality': r['exdiv']['quality'],
                'n_cycles': r['exdiv']['n_cycles'],
                'pattern_strength': r['patterns']['pattern_strength'],
                'signals': r['patterns']['signals'],
                'prediction': r['prediction'],
                'flash_insight': r.get('flash_insight', {}),
            }
        }
    
    return {"status": "not_found", "ticker": ticker}


@router.get("/plan30")
async def get_30day_plan(
    long_pct: int = Query(default=50, ge=0, le=100),
    long_held_pct: int = Query(default=100, ge=1, le=100),
    short_held_pct: int = Query(default=100, ge=1, le=100),
):
    """
    Günlük dinamik ex-div trading planı.
    
    BUGÜNÜN tarihine göre:
    - Her hissenin döngüdeki konumunu hesaplar
    - top5_buy:  BUGÜN alım penceresi AÇIK olan en iyi 5 LONG
    - top5_sell: BUGÜN short penceresi AÇIK olan en iyi 5 SHORT
    - this_week: Bu hafta alım/satım penceresi açılacak hisseler
    - next_week: Gelecek hafta açılacaklar
    - calendar:  30 günlük tam aksiyon takvimi
    """
    import os
    import calendar
    import pandas as pd
    import numpy as np
    from datetime import datetime, timedelta

    BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    PIPELINE_DIR = os.path.join(BASE, "output", "exdiv_v5")
    STOCKTRACKER = os.path.dirname(BASE)  # c:\StockTracker

    sp = os.path.join(PIPELINE_DIR, "v5_summary.csv")

    if not os.path.exists(sp):
        return {"status": "no_data", "message": "Pipeline sonuclari yok. Once run_full_pipeline.py calistirin."}

    summary = pd.read_csv(sp)

    # ═══════════════════════════════════════════════════════════
    # BAZ EX-DIV TARİHLERİ: janalldata.csv (TEK DOĞRU KAYNAK)
    # Fallback: ekheld CSV'leri
    # ═══════════════════════════════════════════════════════════
    base_exdiv_map = {}  # ticker -> base datetime

    # 1) janalldata.csv'den yükle
    janall_path = os.path.join(STOCKTRACKER, "janalldata.csv")
    if os.path.exists(janall_path):
        jdf = pd.read_csv(janall_path)
        for _, row in jdf.iterrows():
            tk = str(row.get('PREF IBKR', '')).strip()
            exd = row.get('EX-DIV DATE', '')
            if tk and pd.notna(exd) and str(exd).strip():
                try:
                    dt = pd.to_datetime(str(exd).strip(), format='%m/%d/%Y')
                    base_exdiv_map[tk] = dt
                except Exception:
                    try:
                        dt = pd.to_datetime(str(exd).strip())
                        base_exdiv_map[tk] = dt
                    except Exception:
                        pass

    # 2) Fallback: ekheld CSV'leri (janalldata'da olmayan tickerlar icin)
    ekheld_files = [
        "ekheldkuponlu.csv", "ekheldff.csv", "ekheldnff.csv",
        "ekheldcommonsuz.csv", "ekheldflr.csv", "ekheldsolidbig.csv",
        "ekheldbesmaturlu.csv", "ekheldtitrekhc.csv",
    ]
    for ef in ekheld_files:
        fp = os.path.join(STOCKTRACKER, ef)
        if os.path.exists(fp):
            try:
                edf = pd.read_csv(fp)
                exdiv_col = 'EX-DIV DATE'
                if exdiv_col not in edf.columns:
                    for c in edf.columns:
                        if 'ex' in c.lower() and 'div' in c.lower():
                            exdiv_col = c
                            break
                if exdiv_col in edf.columns:
                    for _, row in edf.iterrows():
                        tk = str(row.get('PREF IBKR', '')).strip()
                        if tk and tk not in base_exdiv_map:
                            exd = row.get(exdiv_col, '')
                            if pd.notna(exd) and str(exd).strip():
                                try:
                                    dt = pd.to_datetime(str(exd).strip(), format='%m/%d/%Y')
                                    base_exdiv_map[tk] = dt
                                except Exception:
                                    try:
                                        dt = pd.to_datetime(str(exd).strip())
                                        base_exdiv_map[tk] = dt
                                    except Exception:
                                        pass
            except Exception:
                pass

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_str = today.strftime('%Y-%m-%d')
    end_dt = today + timedelta(days=30)
    short_pct = 100 - long_pct

    MAX_POS_PCT = 0.03
    max_long_n = int(long_pct / 100 / MAX_POS_PCT) if long_pct > 0 else 0
    max_short_n = int(short_pct / 100 / MAX_POS_PCT) if short_pct > 0 else 0

    DRIFT_TOLERANCE = 4  # baz gunden max kayma

    # ═══════════════════════════════════════════════════
    # NEXT EX-DIV HESAPLAMA
    # Mantik: BAZ tarihten 3,6,9,12... ay ekle
    # Her zaman BAZ gununen hesapla, ASLA kaydirilmaz
    # ═══════════════════════════════════════════════════

    def find_next_exdiv(ticker):
        """
        janalldata.csv'deki BAZ ex-div tarihinden 3'er ay ekleyerek
        bir sonraki ex-div'i bulur. Baz gun ASLA kaymaz.
        
        Ornek: BAZ = 11/29/2024 (gun=29)
        Projeksiyonlar: 02/28/2026, 05/29/2026, 08/29/2026...
        Pencere: gun ± 4 = 25-33 arasi beklenir
        """
        if ticker not in base_exdiv_map:
            return None, None, None

        base_dt = base_exdiv_map[ticker]
        base_day = base_dt.day
        base_month = base_dt.month
        base_year = base_dt.year

        # 3'er ay ekleyerek projekte et (bazdan, kayan tarihten degil)
        for n in range(1, 30):  # max 7.5 yil ileri
            target_month = base_month + 3 * n
            target_year = base_year + (target_month - 1) // 12
            target_month = ((target_month - 1) % 12) + 1

            # Baz gununu kullan, ayin max gununu asma
            max_d = calendar.monthrange(target_year, target_month)[1]
            actual_day = min(base_day, max_d)

            projected = pd.Timestamp(target_year, target_month, actual_day)

            # Pencere: baz_gun ± DRIFT_TOLERANCE
            # Bugunle karsilastir: pencere icerisindeyse veya gelecekteyse
            window_start = projected - timedelta(days=DRIFT_TOLERANCE)
            window_end = projected + timedelta(days=DRIFT_TOLERANCE)

            if window_end >= today:
                days_until = (projected - today).days
                return projected, days_until, base_day

        return None, None, None

    def biz_day_offset(base_dt, offset):
        """İş günü offset hesapla (negatif = geriye)."""
        dt = base_dt + timedelta(days=int(offset * 7 / 5))
        while dt.weekday() >= 5:
            dt += timedelta(days=1)
        return dt

    # ─── Tum hisselerin dongu bilgilerini topla ───
    stock_cycles = []
    for _, row in summary.iterrows():
        tk = row['ticker']

        next_exdiv, days_until, base_day = find_next_exdiv(tk)
        if next_exdiv is None or days_until is None:
            continue

        # Bugün bu hisse döngüde kaçıncı gün?
        # Negatif = ex-div'e X gün var, Pozitif = ex-div'den X gün geçti
        cycle_day = -days_until  # ör: days_until=5 → cycle_day=-5 (5 gün kala)

        stock_cycles.append({
            'ticker': tk,
            'row': row,
            'next_exdiv': next_exdiv,
            'days_until': days_until,
            'cycle_day': cycle_day,
        })

    # ═══════════════════════════════════════════════════
    # LONG SİNYALLER: Bugün döngüde entry penceresi açık mı?
    # ═══════════════════════════════════════════════════

    active_buys = []      # Bugün entry penceresi açık
    upcoming_buys = []    # Gelecek 30 gün içinde entry olacak

    for sc in stock_cycles:
        row = sc['row']
        tk = sc['ticker']
        next_exdiv = sc['next_exdiv']
        days_until = sc['days_until']

        if pd.isna(row.get('best_long_sharpe')) or row['best_long_sharpe'] < 0.3:
            continue
        if pd.isna(row.get('best_long_pval')) or row['best_long_pval'] > 0.15:
            continue

        entry_off = int(row['best_long_entry']) if pd.notna(row.get('best_long_entry')) else -5
        exit_off = int(row['best_long_exit']) if pd.notna(row.get('best_long_exit')) else 0

        # Entry ve exit tarihlerini hesapla
        entry_dt = biz_day_offset(next_exdiv, entry_off)
        exit_dt = biz_day_offset(next_exdiv, exit_off)
        if exit_dt <= entry_dt:
            exit_dt = entry_dt + timedelta(days=2)
            while exit_dt.weekday() >= 5:
                exit_dt += timedelta(days=1)

        holding_days = max(1, (exit_dt - entry_dt).days)

        # Score: Sharpe + winrate + return kombinasyonu
        score = (float(row.get('best_long_sharpe', 0)) * 0.4 +
                 float(row.get('best_long_win', 0)) * 10 * 0.3 +
                 float(row.get('best_long_ret', 0)) * 0.3)

        item = {
            'ticker': tk,
            'strategy': str(row.get('best_long_name', '')),
            'entry_date': entry_dt.strftime('%Y-%m-%d'),
            'exit_date': exit_dt.strftime('%Y-%m-%d'),
            'exdiv_date': next_exdiv.strftime('%Y-%m-%d'),
            'days_until_exdiv': int(days_until),
            'cycle_day': int(sc['cycle_day']),
            'entry_offset': entry_off,
            'exit_offset': exit_off,
            'holding_days': holding_days,
            'expected_return': round(float(row.get('best_long_ret', 0)), 3),
            'win_rate': round(float(row.get('best_long_win', 0)), 3),
            'sharpe': round(float(row.get('best_long_sharpe', 0)), 2),
            'p_value': round(float(row.get('best_long_pval', 1)), 4),
            'yield_pct': round(float(row.get('yield_pct', 0)), 1),
            'pattern_strength': round(float(row.get('pattern_strength', 0)), 1),
            'score': round(score, 3),
        }

        # BUGÜN entry penceresi açık mı?
        # Entry penceresi: entry_dt'den 1 iş günü öncesinden entry_dt+1'e kadar
        item['entry_offset_label'] = f"div{entry_off:+d}"
        item['exit_offset_label'] = f"div{exit_off:+d}"

        window_start = entry_dt - timedelta(days=1)
        window_end = entry_dt + timedelta(days=1)
        if window_start <= today <= window_end:
            item['signal'] = 'BUY_NOW'
            active_buys.append(item)
        elif entry_dt > today and entry_dt <= end_dt:
            days_to_entry = (entry_dt - today).days
            item['days_to_entry'] = days_to_entry
            upcoming_buys.append(item)

    active_buys.sort(key=lambda x: x['score'], reverse=True)
    upcoming_buys.sort(key=lambda x: (x.get('days_to_entry', 999), -x['score']))

    # ═══════════════════════════════════════════════════
    # SHORT SİNYALLER: Pipeline'ın best_short entry/exit offset'lerini kullan
    # ═══════════════════════════════════════════════════

    active_shorts = []    # Bugün short penceresi açık
    upcoming_shorts = []  # Gelecek 30 gün içinde short olacak

    for sc in stock_cycles:
        row = sc['row']
        tk = sc['ticker']
        next_exdiv = sc['next_exdiv']
        days_until = sc['days_until']

        if pd.isna(row.get('best_short_sharpe')) or row['best_short_sharpe'] < 0.3:
            continue

        # Short entry/exit: pipeline'dan oku, yoksa default (div+0, div+5)
        short_entry_off = int(row['best_short_entry']) if pd.notna(row.get('best_short_entry')) else 0
        short_exit_off = int(row['best_short_exit']) if pd.notna(row.get('best_short_exit')) else 5

        # Entry ve exit tarihlerini hesapla
        entry_dt = biz_day_offset(next_exdiv, short_entry_off)
        exit_dt = biz_day_offset(next_exdiv, short_exit_off)
        if exit_dt <= entry_dt:
            exit_dt = entry_dt + timedelta(days=2)
            while exit_dt.weekday() >= 5:
                exit_dt += timedelta(days=1)

        score = (float(row.get('best_short_sharpe', 0)) * 0.4 +
                 float(row.get('best_short_win', 0)) * 10 * 0.3 +
                 float(row.get('best_short_ret', 0)) * 0.3)

        item = {
            'ticker': tk,
            'strategy': str(row.get('best_short_name', 'WASHOUT')),
            'entry_date': entry_dt.strftime('%Y-%m-%d'),
            'exit_date': exit_dt.strftime('%Y-%m-%d'),
            'exdiv_date': next_exdiv.strftime('%Y-%m-%d'),
            'days_until_exdiv': int(days_until),
            'cycle_day': int(sc['cycle_day']),
            'entry_offset': short_entry_off,
            'exit_offset': short_exit_off,
            'entry_offset_label': f"div{short_entry_off:+d}",
            'exit_offset_label': f"div{short_exit_off:+d}",
            'holding_days': max(1, (exit_dt - entry_dt).days),
            'expected_return': round(float(row.get('best_short_ret', 0)), 3),
            'win_rate': round(float(row.get('best_short_win', 0)), 3) if pd.notna(row.get('best_short_win')) else 0,
            'sharpe': round(float(row.get('best_short_sharpe', 0)), 2),
            'p_value': round(float(row.get('best_short_pval', 1)), 4) if pd.notna(row.get('best_short_pval')) else 1.0,
            'yield_pct': round(float(row.get('yield_pct', 0)), 1),
            'pattern_strength': round(float(row.get('pattern_strength', 0)), 1),
            'score': round(score, 3),
        }

        # BUGÜN short penceresi açık mı?
        window_start = entry_dt - timedelta(days=1)
        window_end = entry_dt + timedelta(days=1)
        if window_start <= today <= window_end:
            item['signal'] = 'SHORT_NOW'
            active_shorts.append(item)
        elif entry_dt > today and entry_dt <= end_dt:
            days_to_entry = (entry_dt - today).days
            item['days_to_entry'] = days_to_entry
            upcoming_shorts.append(item)

    active_shorts.sort(key=lambda x: x['score'], reverse=True)
    upcoming_shorts.sort(key=lambda x: (x.get('days_to_entry', 999), -x['score']))

    # ═══════════════════════════════════════════════════
    # HAFTALIK GRUPLAMA
    # ═══════════════════════════════════════════════════

    week_end = today + timedelta(days=(4 - today.weekday()) % 7 + 1)  # Bu Cuma
    next_week_end = week_end + timedelta(days=7)

    this_week_buys = [b for b in upcoming_buys if b['entry_date'] <= week_end.strftime('%Y-%m-%d')]
    this_week_shorts = [s for s in upcoming_shorts if s['entry_date'] <= week_end.strftime('%Y-%m-%d')]
    next_week_buys = [b for b in upcoming_buys
                      if week_end.strftime('%Y-%m-%d') < b['entry_date'] <= next_week_end.strftime('%Y-%m-%d')]
    next_week_shorts = [s for s in upcoming_shorts
                        if week_end.strftime('%Y-%m-%d') < s['entry_date'] <= next_week_end.strftime('%Y-%m-%d')]

    # ═══════════════════════════════════════════════════
    # PORTFÖY SEÇİMİ + GÜNLÜK TAKVİM
    # ═══════════════════════════════════════════════════

    all_upcoming_longs = active_buys + upcoming_buys
    all_upcoming_shorts = active_shorts + upcoming_shorts
    all_upcoming_longs.sort(key=lambda x: x['score'], reverse=True)
    all_upcoming_shorts.sort(key=lambda x: x['score'], reverse=True)

    selected_longs = all_upcoming_longs[:max_long_n]
    selected_shorts = all_upcoming_shorts[:max_short_n]
    n_l_held = max(1, int(len(selected_longs) * long_held_pct / 100)) if selected_longs else 0
    n_s_held = max(1, int(len(selected_shorts) * short_held_pct / 100)) if selected_shorts else 0

    # Günlük aksiyon takvimi
    actions = []
    for t in selected_longs:
        actions.append({'date': t['entry_date'], 'action': 'BUY', 'ticker': t['ticker'],
                        'direction': 'LONG', 'strategy': t['strategy'],
                        'expected_return': t['expected_return'], 'sharpe': t['sharpe'],
                        'exdiv_date': t['exdiv_date']})
        actions.append({'date': t['exit_date'], 'action': 'SELL', 'ticker': t['ticker'],
                        'direction': 'LONG', 'strategy': t['strategy'],
                        'expected_return': t['expected_return'], 'sharpe': t['sharpe'],
                        'exdiv_date': t['exdiv_date']})
    for t in selected_shorts:
        actions.append({'date': t['entry_date'], 'action': 'SHORT', 'ticker': t['ticker'],
                        'direction': 'SHORT', 'strategy': t['strategy'],
                        'expected_return': t['expected_return'], 'sharpe': t['sharpe'],
                        'exdiv_date': t['exdiv_date']})
        actions.append({'date': t['exit_date'], 'action': 'COVER', 'ticker': t['ticker'],
                        'direction': 'SHORT', 'strategy': t['strategy'],
                        'expected_return': t['expected_return'], 'sharpe': t['sharpe'],
                        'exdiv_date': t['exdiv_date']})
    actions.sort(key=lambda x: (x['date'], x['action']))

    # Bugünün aksiyonları
    today_actions = [a for a in actions if a['date'] == today_str]

    return {
        "status": "ok",
        "today": today_str,
        "config": {
            "long_pct": long_pct, "short_pct": short_pct,
            "long_held_pct": long_held_pct, "short_held_pct": short_held_pct,
        },
        # ─── ANA: Bugün aktif sinyaller ───
        "top5_buy": active_buys[:5],
        "top5_sell": active_shorts[:5],
        "active_buy_count": len(active_buys),
        "active_short_count": len(active_shorts),
        # ─── Bu hafta & gelecek hafta ───
        "this_week_buys": this_week_buys[:10],
        "this_week_shorts": this_week_shorts[:10],
        "next_week_buys": next_week_buys[:10],
        "next_week_shorts": next_week_shorts[:10],
        # ─── 30 günlük tüm adaylar ───
        "all_longs": len(all_upcoming_longs),
        "all_shorts": len(all_upcoming_shorts),
        "selected_longs": selected_longs,
        "selected_shorts": selected_shorts,
        "held_long_count": n_l_held,
        "held_short_count": n_s_held,
        # ─── Günlük takvim ───
        "today_actions": today_actions,
        "daily_actions": actions,
    }


@router.get("/pattern-stats")
async def get_pattern_stats():
    """Quick stats without Gemini — sadece istatistiksel analiz."""
    from app.agent.exdiv_analyzer import ExDivFlashAnalyzer
    
    analyzer = ExDivFlashAnalyzer()
    analyzer.load_data()
    
    stocks = analyzer.get_available_stocks()
    
    results = []
    ok = skip = 0
    for tk in stocks:
        r = analyzer.analyze_single_sync(tk)
        if r:
            ok += 1
            signals = r['patterns']['signals']
            best_long = max((s['expected_return'] for s in signals 
                           if s['action'] in ('LONG', 'CAPTURE', 'RECOVERY', 'DIV_HOLD')), default=0)
            best_short = max((s['expected_return'] for s in signals 
                            if s['action'] in ('SHORT', 'WASHOUT')), default=0)
            
            results.append({
                'ticker': tk,
                'div_amount': r['div_amount'],
                'yield_pct': round(r.get('yield_pct', 0), 1),
                'n_cycles': r['exdiv']['n_cycles'],
                'quality': r['exdiv']['quality'],
                'pattern_strength': r['patterns']['pattern_strength'],
                'best_long': round(best_long, 2),
                'best_short': round(best_short, 2),
                'next_exdiv': r.get('prediction', {}).get('predicted_date', ''),
                'signals': [f"{s['action']}(ret={s['expected_return']:+.2f}%,p={s.get('p_value',1):.3f})" 
                           for s in signals if s.get('significant')],
            })
        else:
            skip += 1
    
    results.sort(key=lambda x: x['pattern_strength'], reverse=True)
    
    return {
        "status": "ok",
        "total_analyzed": ok,
        "skipped": skip,
        "top_patterns": results[:30],
        "all_results": results,
    }
