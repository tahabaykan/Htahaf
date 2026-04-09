"""
Flash Ex-Div Date Verifier
============================

Gemini Flash ile akıllı ex-div tarih tespiti.

MANTIK:
1. Bilinen anchor tarihinden 3'er aylık periyotlarla ileriye/geriye project et
2. Her beklenen pencere (±4 gün) için:
   a) Hedef hissenin günlük OHLCV verisini çıkar
   b) 5 adet random peer hissenin aynı günlerdeki verisini çıkar
   c) Flash'a gönder: "Bu hisse bu pencerede ex-div mi yaşadı?"
   d) Flash, cross-sectional karşılaştırma yaparak karar verir
3. Onaylanmış tarihler ile pattern analizi yap

AVANTAJLAR vs eski detector:
- Piyasa sell-off'larını (2025-04-07 gibi) doğru filtreler
- 3 aylık periyodisite kuralını sert uygular
- Her gap'i bağlamında değerlendirir (peer comparison)
- Güvenilir ex-div tarihi = güvenilir pattern analizi
"""

import os
import glob
import json
import asyncio
import random
import pandas as pd
import numpy as np
import warnings
from datetime import datetime
from typing import List, Dict, Optional, Tuple

warnings.filterwarnings('ignore')

from app.core.logger import logger

STOCKTRACKER_ROOT = r"C:\StockTracker"
UTALLDATA_DIR = os.path.join(STOCKTRACKER_ROOT, "UTALLDATA")

# All available stocks (cached)
_ALL_DFS: Dict[str, pd.DataFrame] = {}


def _load_stock_df(ticker: str) -> Optional[pd.DataFrame]:
    """UTALLDATA'dan bir hissenin DataFrame'ini yükle (cache ile)."""
    if ticker in _ALL_DFS:
        return _ALL_DFS[ticker]
    
    safe = ticker.replace(" ", "_")
    fpath = os.path.join(UTALLDATA_DIR, f"{safe}22exdata.csv")
    if not os.path.exists(fpath):
        return None
    
    try:
        df = pd.read_csv(fpath)
        df['Date'] = pd.to_datetime(df['Date'])
        _ALL_DFS[ticker] = df
        return df
    except Exception:
        return None


def _get_all_tickers() -> List[str]:
    """UTALLDATA'daki tüm hisse tickerları."""
    files = glob.glob(os.path.join(UTALLDATA_DIR, "*22exdata.csv"))
    tickers = []
    for fp in files:
        bn = os.path.basename(fp)
        tk = bn.replace("22exdata.csv", "").replace("_", " ").strip()
        if not tk.startswith("PFF"):
            tickers.append(tk)
    return sorted(tickers)


def _pick_random_peers(target: str, n: int = 5) -> List[str]:
    """Hedef hisse dışında n adet peer seç."""
    all_tickers = _get_all_tickers()
    candidates = [t for t in all_tickers if t != target]
    return random.sample(candidates, min(n, len(candidates)))


def _extract_window_data(df: pd.DataFrame, center_date: pd.Timestamp, 
                         window_days: int = 4) -> List[Dict]:
    """Merkez tarih etrafında ±window_days'lik veriyi çıkar."""
    start = center_date - pd.Timedelta(days=window_days + 2)  # Hafta sonu buffer
    end = center_date + pd.Timedelta(days=window_days + 2)
    
    window = df[(df['Date'] >= start) & (df['Date'] <= end)].copy()
    rows = []
    for idx in window.index:
        r = window.loc[idx]
        prev_close = df.loc[idx - 1, 'Close'] if idx > 0 and (idx - 1) in df.index else None
        
        gap_dollar = (r['Open'] - prev_close) if prev_close and prev_close > 0 else None
        gap_pct = (gap_dollar / prev_close * 100) if gap_dollar is not None and prev_close > 0 else None
        
        rows.append({
            'date': r['Date'].strftime('%Y-%m-%d'),
            'open': round(float(r['Open']), 2),
            'close': round(float(r['Close']), 2),
            'prev_close': round(float(prev_close), 2) if prev_close else None,
            'gap_dollar': round(float(gap_dollar), 3) if gap_dollar is not None else None,
            'gap_pct': round(float(gap_pct), 3) if gap_pct is not None else None,
            'volume': int(r.get('Volume', 0)) if pd.notna(r.get('Volume', 0)) else 0,
        })
    return rows


def build_quarterly_windows(anchor_date: str, data_start: pd.Timestamp,
                           data_end: pd.Timestamp) -> List[pd.Timestamp]:
    """Anchor'dan 3'er aylık beklenen ex-div tarihleri project et."""
    anchor = pd.to_datetime(anchor_date)
    windows = []
    
    # Geriye doğru
    q = 0
    while True:
        expected = anchor + pd.DateOffset(months=3 * q)
        if expected < data_start - pd.Timedelta(days=10):
            break
        if expected <= data_end + pd.Timedelta(days=10):
            windows.append(expected)
        q -= 1
        if q < -20:
            break
    
    # İleriye doğru  
    q = 1
    while True:
        expected = anchor + pd.DateOffset(months=3 * q)
        if expected > data_end + pd.Timedelta(days=10):
            break
        windows.append(expected)
        q += 1
        if q > 20:
            break
    
    return sorted(set(windows))


def build_verification_prompt(ticker: str, div_amount: float, 
                              anchor_date: str,
                              windows_data: List[Dict]) -> str:
    """Gemini Flash'a gönderilecek ex-div doğrulama promptu."""
    
    windows_text = []
    for w in windows_data:
        windows_text.append(f"\n  === PENCERE: Beklenen ~{w['expected_date']} ===")
        
        # Target stock
        windows_text.append(f"  {ticker} (HEDEF):")
        for d in w['target_data']:
            gap_str = f"Gap={d['gap_pct']:+.3f}% (${d['gap_dollar']:+.3f})" if d['gap_pct'] is not None else "Gap=N/A"
            windows_text.append(f"    {d['date']}  O={d['open']:.2f}  C={d['close']:.2f}  "
                              f"PC={d['prev_close'] or 'N/A'}  {gap_str}  Vol={d['volume']}")
        
        # Peers
        for peer_name, peer_data in w['peers'].items():
            windows_text.append(f"  {peer_name} (PEER):")
            for d in peer_data:
                gap_str = f"Gap={d['gap_pct']:+.3f}%" if d['gap_pct'] is not None else "Gap=N/A"
                windows_text.append(f"    {d['date']}  O={d['open']:.2f}  C={d['close']:.2f}  {gap_str}")
    
    windows_str = "\n".join(windows_text)
    
    prompt = f"""
═══════════════════════════════════════════════════════════════
EX-DIV TARİH DOĞRULAMA: {ticker}
═══════════════════════════════════════════════════════════════

BİLGİ:
- Ticker: {ticker}
- Çeyreklik temettü: ${div_amount:.4f}
- Beklenen gap-down: ~${-div_amount:.3f} (~{-div_amount/21*100:.1f}% @ $21 fiyat)
- Bilinen anchor ex-div: {anchor_date}
- Temettüler 3 ER AYLIK periyotlarla ödenir (±4 gün tolerans)

GÖREV:
Her pencere için, hedef hissenin o pencerede gerçekten ex-div yaşayıp yaşamadığını belirle.

KURALLAR:
1. Her 3 ayda bir MUTLAKA bir ex-div olmalıdır (preferred stocklar düzenli öder)
2. Ex-div günü: hisse açılışı önceki kapanıştan temettü tutarı kadar (~${div_amount:.2f}) düşer
3. CROSS-SECTIONAL KONTROL: Eğer O GÜN peer hisseler de benzer oranda düşmüşse → 
   PIYASA SELL-OFF, ex-div DEĞİL! (ör. 2025-04-07 tariff sell-off)
4. ÖNEMLI: Eğer pencerede hiçbir gün belirgin gap-down yoksa → 
   muhtemelen verinin eksik olduğu bir dönem veya anormal çeyrek. 
   En uygun günü yine de seç ama düşük güven ile.
5. Gap-down sadece hedef hissede (peer'larda değil) olmalı = yüksek güven ex-div

VERİ:
{windows_str}

═══════════════════════════════════════════════════════════════
CEVAP: MUTLAKA aşağıdaki JSON formatında ver.

```json
{{
  "ticker": "{ticker}",
  "verified_exdiv_dates": [
    {{
      "expected_date": "YYYY-MM-DD",
      "confirmed_date": "YYYY-MM-DD",
      "confidence": "HIGH/MEDIUM/LOW",
      "gap_pct": -1.5,
      "reasoning": "kısa açıklama"
    }}
  ],
  "notes": "genel not"
}}
```

Her pencere için bir entry olmalı. Eğer pencerede veri yoksa "confirmed_date": null yap.
"""
    return prompt


async def verify_exdiv_dates_with_flash(
    gemini_client,
    ticker: str,
    div_amount: float,
    anchor_date: str,
) -> Dict:
    """Bir hissenin tüm ex-div tarihlerini Flash ile doğrula."""
    
    df = _load_stock_df(ticker)
    if df is None:
        return {'ticker': ticker, 'error': 'No data file'}
    
    if len(df) < 50:
        return {'ticker': ticker, 'error': 'Insufficient data'}
    
    # Project quarterly windows
    data_start = df['Date'].iloc[0]
    data_end = df['Date'].iloc[-1]
    expected_dates = build_quarterly_windows(anchor_date, data_start, data_end)
    
    if not expected_dates:
        return {'ticker': ticker, 'error': 'No windows to check'}
    
    # Pick 5 random peers
    peers = _pick_random_peers(ticker, n=5)
    peer_dfs = {}
    for p in peers:
        pdf = _load_stock_df(p)
        if pdf is not None:
            peer_dfs[p] = pdf
    
    # Extract window data for each expected date
    windows_data = []
    for exp_date in expected_dates:
        target_data = _extract_window_data(df, exp_date, window_days=5)
        
        peer_windows = {}
        for p, pdf in peer_dfs.items():
            peer_windows[p] = _extract_window_data(pdf, exp_date, window_days=5)
        
        if target_data:  # Only include if we have data
            windows_data.append({
                'expected_date': exp_date.strftime('%Y-%m-%d'),
                'target_data': target_data,
                'peers': peer_windows,
            })
    
    if not windows_data:
        return {'ticker': ticker, 'error': 'No data in any window'}
    
    # Build prompt and call Flash
    prompt = build_verification_prompt(ticker, div_amount, anchor_date, windows_data)
    
    logger.info(f"[FLASH-EXDIV] Verifying {ticker}: {len(windows_data)} windows, "
                f"{len(peers)} peers, prompt ~{len(prompt)} chars")
    
    try:
        raw = await gemini_client.analyze(
            system_prompt=(
                "Sen bir preferred stock ex-dividend tarih doğrulama uzmanısın. "
                "Verilen fiyat verileri ve peer karşılaştırmalarından ex-div tarihlerini "
                "doğrula. 3 aylık periyodisite kuralını sıkı uygula. "
                "Piyasa geneli sell-off'ları ex-div ile karıştırma. "
                "Cevabını MUTLAKA JSON formatında ver."
            ),
            user_prompt=prompt,
            temperature=0.2,
        )
        
        # Parse response
        import re
        json_match = re.search(r'```json\s*(.*?)\s*```', raw, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group(1))
        else:
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
            else:
                result = {'error': 'Could not parse response', 'raw': raw[:500]}
        
        result['ticker'] = ticker
        result['div_amount'] = div_amount
        result['anchor_date'] = anchor_date
        result['n_windows'] = len(windows_data)
        result['peers_used'] = peers
        
        # Extract confirmed dates
        verified = result.get('verified_exdiv_dates', [])
        confirmed = [v['confirmed_date'] for v in verified 
                    if v.get('confirmed_date') and v.get('confidence') != 'NONE']
        result['confirmed_dates_list'] = confirmed
        result['n_confirmed'] = len(confirmed)
        
        logger.info(f"[FLASH-EXDIV] {ticker}: {len(confirmed)}/{len(windows_data)} dates confirmed")
        
        return result
        
    except Exception as e:
        logger.error(f"[FLASH-EXDIV] Error verifying {ticker}: {e}")
        return {'ticker': ticker, 'error': str(e)}


async def verify_all_stocks(
    gemini_client,
    div_info: Dict[str, Dict],
    tickers: List[str] = None,
    max_stocks: int = 0,
    delay_seconds: float = 4.0,
) -> Dict[str, Dict]:
    """Tüm hisselerin ex-div tarihlerini Flash ile doğrula."""
    
    if tickers is None:
        tickers = _get_all_tickers()
    
    # Filter to those with div info
    tickers = [t for t in tickers if t in div_info]
    
    if max_stocks > 0:
        tickers = tickers[:max_stocks]
    
    logger.info(f"[FLASH-EXDIV] Starting verification: {len(tickers)} stocks")
    
    results = {}
    ok = skip = err = 0
    
    for i, tk in enumerate(tickers):
        info = div_info[tk]
        anchor = info.get('exdiv_date', '')
        
        if not anchor or anchor == 'nan':
            # No anchor — try to find first ex-div via simple gap analysis
            logger.info(f"[FLASH-EXDIV] {tk}: No anchor date, will use heuristic")
            # Use the largest gap-down as anchor
            tdf = _load_stock_df(tk)
            if tdf is not None and len(tdf) > 50:
                tdf_gaps = (tdf['Open'] - tdf['Close'].shift(1)) / tdf['Close'].shift(1) * 100
                worst_idx = tdf_gaps.idxmin()
                if worst_idx is not None and tdf_gaps.iloc[worst_idx] < -0.3:
                    anchor = tdf.loc[worst_idx, 'Date'].strftime('%Y-%m-%d')
                    logger.info(f"[FLASH-EXDIV] {tk}: Heuristic anchor = {anchor}")
                else:
                    skip += 1
                    continue
            else:
                skip += 1
                continue
        
        try:
            result = await verify_exdiv_dates_with_flash(
                gemini_client, tk, info['div_amount'], anchor
            )
            results[tk] = result
            
            if 'error' in result:
                err += 1
            else:
                ok += 1
        except Exception as e:
            logger.error(f"[FLASH-EXDIV] Error {tk}: {e}")
            err += 1
        
        if (i + 1) % 5 == 0:
            logger.info(f"[FLASH-EXDIV] Progress: {i+1}/{len(tickers)} "
                       f"(ok={ok}, skip={skip}, err={err})")
        
        # Rate limit
        await asyncio.sleep(delay_seconds)
    
    logger.info(f"[FLASH-EXDIV] Verification complete: "
               f"{ok} verified, {skip} skipped, {err} errors")
    
    return results


# =====================================================================
# FALLBACK: Algorithmic verification (no Gemini needed)
# =====================================================================

def verify_exdiv_dates_algorithmic(
    ticker: str, 
    div_amount: float, 
    anchor_date: str,
    n_peers: int = 5
) -> Dict:
    """Flash olmadan, algorithmic cross-sectional verification."""
    df = _load_stock_df(ticker)
    if df is None or len(df) < 50:
        return {'ticker': ticker, 'error': 'No data'}
    
    data_start = df['Date'].iloc[0]
    data_end = df['Date'].iloc[-1]
    expected_dates = build_quarterly_windows(anchor_date, data_start, data_end)
    
    if not expected_dates:
        return {'ticker': ticker, 'error': 'No windows'}
    
    # Load peers
    peers = _pick_random_peers(ticker, n=n_peers)
    peer_dfs = {}
    for p in peers:
        pdf = _load_stock_df(p)
        if pdf is not None:
            peer_dfs[p] = pdf
    
    verified = []
    for exp_date in expected_dates:
        window_start = exp_date - pd.Timedelta(days=7)
        window_end = exp_date + pd.Timedelta(days=7)
        
        window = df[(df['Date'] >= window_start) & (df['Date'] <= window_end)]
        
        best_date = None
        best_score = -999
        
        for idx in window.index:
            if idx <= 0 or (idx - 1) not in df.index:
                continue
            
            prev_close = df.loc[idx - 1, 'Close']
            if prev_close <= 0 or np.isnan(prev_close):
                continue
            
            stock_gap = (df.loc[idx, 'Open'] - prev_close) / prev_close * 100
            date = df.loc[idx, 'Date']
            
            # Peer gaps on the same date
            peer_gaps = []
            for p, pdf in peer_dfs.items():
                prow = pdf[pdf['Date'] == date]
                if len(prow) > 0:
                    pidx = prow.index[0]
                    if pidx > 0 and (pidx - 1) in pdf.index:
                        ppc = pdf.loc[pidx - 1, 'Close']
                        if ppc > 0:
                            pgap = (prow.iloc[0]['Open'] - ppc) / ppc * 100
                            peer_gaps.append(pgap)
            
            peer_median = float(np.median(peer_gaps)) if peer_gaps else 0
            
            # Divergence: stock gapped down more than peers
            divergence = stock_gap - peer_median
            
            # Expected divergence = -div/price
            expected_div_pct = -div_amount / prev_close * 100
            
            # Score: how close is divergence to expected?
            if divergence < 0 and expected_div_pct < 0:
                ratio = divergence / expected_div_pct  # Should be ~1.0
                # Bonus for being close to 1.0, penalty for being far
                closeness = max(0, 1.0 - abs(ratio - 1.0))
                # Bonus for peers NOT gapping down (confirming stock-specific event)
                peer_stability = max(0, 1.0 + peer_median / 2)  # Higher if peers were flat/up
                
                score = closeness * 0.6 + peer_stability * 0.4
            else:
                score = 0
            
            if score > best_score:
                best_score = score
                best_date = {
                    'expected_date': exp_date.strftime('%Y-%m-%d'),
                    'confirmed_date': date.strftime('%Y-%m-%d'),
                    'confidence': 'HIGH' if best_score > 0.6 else 'MEDIUM' if best_score > 0.3 else 'LOW',
                    'score': round(score, 3),
                    'stock_gap_pct': round(stock_gap, 3),
                    'peer_median_gap_pct': round(peer_median, 3),
                    'divergence_pct': round(divergence, 3),
                }
        
        if best_date:
            verified.append(best_date)
    
    confirmed = [v['confirmed_date'] for v in verified if v['confidence'] in ('HIGH', 'MEDIUM')]
    
    return {
        'ticker': ticker,
        'div_amount': div_amount,
        'anchor_date': anchor_date,
        'verified_exdiv_dates': verified,
        'confirmed_dates_list': confirmed,
        'n_confirmed': len(confirmed),
        'n_windows': len(expected_dates),
        'peers_used': peers,
        'method': 'algorithmic'
    }
