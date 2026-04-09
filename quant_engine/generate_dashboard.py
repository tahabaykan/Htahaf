#!/usr/bin/env python3
"""
QE Log Dashboard Generator v3
- Parses backend logs to determine HAMPRO vs IBKR_PED per cycle
- Parses [PROPOSAL] lines directly from logs
- Parses [HAMMER FILL] and [IBKR_FILL] lines
- Parses ERROR / WARNING lines
- Generates dashboard with HAMPRO/IBKR_PED sub-tabs in each engine section
"""
import re, os, glob, datetime

LOG_DIR = r"C:\StockTracker\quant_engine\data\logs\terminals"
OUTPUT  = r"C:\StockTracker\quant_engine\log_dashboard.html"
TODAY   = datetime.date.today().strftime("%Y%m%d")

RX_ANSI = re.compile(r'\x1b\[[0-9;]*m')

def load_backend_logs():
    """Load and clean all backend logs for today"""
    backend_logs = sorted(glob.glob(os.path.join(LOG_DIR, f"backend_{TODAY}_*.log")))
    all_content = []
    for logf in backend_logs:
        with open(logf, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        content = RX_ANSI.sub('', content)
        all_content.append((os.path.basename(logf), content))
    return all_content

def parse_cycle_account_map(logs):
    """Build cycle->account mapping from backend logs"""
    entries = []
    rx_cycle = re.compile(
        r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+ \| INFO.*'
        r'\[RUNALL\] Cycle (\d+) processing for Account: (\w+)'
    )
    for session, content in logs:
        for m in rx_cycle.finditer(content):
            entries.append({
                'session': session,
                'ts': m.group(1),
                'cycle': int(m.group(2)),
                'account': m.group(3)
            })
    return entries

def build_time_windows(cycle_entries):
    """Build time windows to assign proposals to accounts"""
    if not cycle_entries:
        return []
    sorted_entries = sorted(cycle_entries, key=lambda x: x['ts'])
    windows = []
    for i, entry in enumerate(sorted_entries):
        start = entry['ts']
        end = sorted_entries[i+1]['ts'] if i + 1 < len(sorted_entries) else "2099-12-31 23:59:59"
        windows.append((start, end, entry['account'], entry['cycle'], entry['session']))
    return windows

def get_account_for_time(windows, ts_str):
    """Assign account by timestamp"""
    for start, end, account, cycle, session in windows:
        if start <= ts_str < end:
            return account
    if windows and ts_str >= windows[-1][0]:
        return windows[-1][2]
    return "UNKNOWN"

def parse_proposals(logs):
    """Parse [PROPOSAL] Generated proposal lines from backend logs"""
    proposals = []
    # Pattern: [PROPOSAL] Generated proposal: SYMBOL ACTION QTY @ PRICE (engine=ENG, ..., cycle=N)
    # Use .*? (non-greedy) for the first wildcard, and , before cycle to be precise
    rx = re.compile(
        r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+.*?'
        r'\[PROPOSAL\] Generated proposal: (.+?) (BUY|SELL|SHORT|COVER) ([\d.]+) @ ([\d.]+) '
        r'\(engine=([\w_]+),.*?cycle=(\d+)\)'
    )
    for session, content in logs:
        for m in rx.finditer(content):
            proposals.append({
                'time': m.group(1),
                'symbol': m.group(2).strip(),
                'action': m.group(3),
                'qty': m.group(4),
                'price': m.group(5),
                'engine': m.group(6),
                'cycle': m.group(7),
                'session': session,
            })
    return proposals

def parse_fills(logs):
    """Parse [HAMMER FILL] and [IBKR_FILL] lines from backend logs"""
    fills = []
    
    # HAMMER FILL: [HAMMER FILL] Logged SYMBOL ACTION QTY @ PRICE (TAG)
    rx_hammer = re.compile(
        r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+.*?'
        r'\[HAMMER FILL\] Logged (.+?) (BUY|SELL) ([\d.]+) @ ([\d.]+) \(([^)]+)\)'
    )
    # IBKR_FILL: [IBKR_FILL] SYMBOL ACTION QTY@PRICE tag=TAG | METRICS: ...
    rx_ibkr = re.compile(
        r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+.*?'
        r'\[IBKR_FILL\][^A-Z]*(.+?) (BUY|SELL) ([\d.]+)@([\d.]+) tag=([^\s|]+)'
    )
    
    for session, content in logs:
        for m in rx_hammer.finditer(content):
            fills.append({
                'time': m.group(1),
                'symbol': m.group(2).strip(),
                'action': m.group(3),
                'qty': m.group(4),
                'price': m.group(5),
                'tag': m.group(6),
                'source': 'HAMPRO',
                'session': session,
            })
        for m in rx_ibkr.finditer(content):
            fills.append({
                'time': m.group(1),
                'symbol': m.group(2).strip(),
                'action': m.group(3),
                'qty': m.group(4),
                'price': m.group(5),
                'tag': m.group(6),
                'source': 'IBKR_PED',
                'session': session,
            })
    
    # Sort by time
    fills.sort(key=lambda x: x['time'])
    return fills

def parse_errors(logs):
    """Parse ERROR and WARNING lines from backend logs"""
    errors = []
    rx_loguru = re.compile(
        r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+ \| (ERROR|WARNING)\s+\| '
        r'([^:]+:[^:]+:\d+) \| (.+)'
    )
    
    for session, content in logs:
        for m in rx_loguru.finditer(content):
            errors.append({
                'time': m.group(1),
                'level': m.group(2),
                'source': m.group(3).strip(),
                'message': m.group(4).strip()[:200],
                'session': session,
            })
    
    errors.sort(key=lambda x: x['time'])
    return errors

def generate_html(proposals, fills, errors, cycle_entries, windows):
    """Generate the full HTML dashboard"""
    now = datetime.datetime.now().strftime("%H:%M:%S")
    
    # Assign account to each proposal
    for p in proposals:
        p['account'] = get_account_for_time(windows, p['time'])
    
    # Split by engine AND account
    def normalize_engine(eng):
        if 'ADDNEWPOS' in eng: return 'ADDNEWPOS_ENGINE'
        if 'PATADD' in eng: return 'PATADD_ENGINE'
        if eng in ('GREATEST_MM', 'MM_ENGINE', 'MM'): return 'GREATEST_MM'
        return eng
    
    engines_by_account = {}
    for ek in ['ADDNEWPOS_ENGINE', 'KARBOTU', 'LT_TRIM', 'GREATEST_MM', 'PATADD_ENGINE']:
        engines_by_account[ek] = {'HAMPRO': [], 'IBKR_PED': []}
    
    all_by_account = {'HAMPRO': [], 'IBKR_PED': []}
    
    for p in proposals:
        acc = p['account'] if p['account'] in ('HAMPRO', 'IBKR_PED') else 'HAMPRO'
        eng = normalize_engine(p['engine'])
        if eng in engines_by_account:
            engines_by_account[eng][acc].append(p)
        all_by_account[acc].append(p)
    
    total_h = len(all_by_account['HAMPRO'])
    total_i = len(all_by_account['IBKR_PED'])
    cycles_h = [e for e in cycle_entries if e['account'] == 'HAMPRO']
    cycles_i = [e for e in cycle_entries if e['account'] == 'IBKR_PED']
    
    # Fills split
    fills_h = [f for f in fills if f['source'] == 'HAMPRO']
    fills_i = [f for f in fills if f['source'] == 'IBKR_PED']
    
    # Errors split
    errors_only = [e for e in errors if e['level'] == 'ERROR']
    warns_only = [e for e in errors if e['level'] == 'WARNING']
    
    # Deduplicate errors for summary
    error_summary = {}
    for e in errors_only:
        key = e['message'][:80]
        if key not in error_summary:
            error_summary[key] = {'count': 0, 'first': e['time'], 'last': e['time'], 'msg': e['message'], 'source': e['source']}
        error_summary[key]['count'] += 1
        error_summary[key]['last'] = e['time']
    
    # Count per engine per account
    counts = {}
    for ek in engines_by_account:
        counts[ek] = {
            'h': len(engines_by_account[ek]['HAMPRO']),
            'i': len(engines_by_account[ek]['IBKR_PED']),
            'h_buy': sum(1 for p in engines_by_account[ek]['HAMPRO'] if p['action'] in ('BUY','COVER')),
            'h_sell': sum(1 for p in engines_by_account[ek]['HAMPRO'] if p['action'] in ('SELL','SHORT')),
            'i_buy': sum(1 for p in engines_by_account[ek]['IBKR_PED'] if p['action'] in ('BUY','COVER')),
            'i_sell': sum(1 for p in engines_by_account[ek]['IBKR_PED'] if p['action'] in ('SELL','SHORT')),
        }
    
    # -- HTML --
    H = []
    H.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QE Dashboard — {TODAY}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{--bg:#0a0e1a;--card:#111827;--card2:#1a2332;--bdr:#1e293b;--t1:#e2e8f0;--t2:#94a3b8;--t3:#64748b;
--blue:#3b82f6;--green:#10b981;--red:#ef4444;--amber:#f59e0b;--purple:#8b5cf6;--cyan:#06b6d4;--pink:#ec4899;
--hc:#10b981;--ic:#f59e0b}}
body{{font-family:'Inter',sans-serif;background:var(--bg);color:var(--t1);line-height:1.5}}
.hdr{{background:linear-gradient(180deg,#111827,#0a0e1a);border-bottom:1px solid var(--bdr);padding:14px 28px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;backdrop-filter:blur(12px)}}
.hdr h1{{font-size:18px;font-weight:700;background:linear-gradient(135deg,#667eea,#764ba2);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.hdr .meta{{font-size:12px;color:var(--t3);font-family:'JetBrains Mono',monospace}}
.tabs{{display:flex;gap:0;padding:0 28px;border-bottom:1px solid var(--bdr);background:var(--card);overflow-x:auto}}
.tab{{padding:10px 20px;cursor:pointer;font-size:13px;font-weight:500;color:var(--t3);border-bottom:2px solid transparent;transition:.2s;white-space:nowrap;user-select:none}}
.tab:hover{{color:var(--t1);background:rgba(59,130,246,.05)}}
.tab.active{{color:var(--blue);border-bottom-color:var(--blue);background:rgba(59,130,246,.08)}}
.pane{{display:none;padding:20px 28px}}.pane.active{{display:block}}
.sub-tabs{{display:flex;gap:0;margin-bottom:16px;border:1px solid var(--bdr);border-radius:10px;overflow:hidden;width:fit-content}}
.sub-tab{{padding:8px 20px;cursor:pointer;font-size:12px;font-weight:600;color:var(--t3);background:var(--card);transition:.2s;white-space:nowrap;user-select:none;border-right:1px solid var(--bdr);letter-spacing:.03em}}
.sub-tab:last-child{{border-right:none}}
.sub-tab:hover{{color:var(--t1);background:rgba(59,130,246,.05)}}
.sub-tab.act{{color:#fff}}
.sub-tab.act[data-a="H"]{{background:linear-gradient(135deg,#059669,#10b981)}}
.sub-tab.act[data-a="I"]{{background:linear-gradient(135deg,#d97706,#f59e0b)}}
.sub-tab .n{{display:inline-block;background:rgba(255,255,255,.15);padding:1px 6px;border-radius:6px;font-family:'JetBrains Mono',monospace;margin-left:4px;font-size:10px}}
.sc{{display:none}}.sc.act{{display:block}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:20px}}
.card{{background:var(--card);border:1px solid var(--bdr);border-radius:10px;padding:14px 16px;transition:.2s}}
.card:hover{{border-color:var(--blue);transform:translateY(-1px)}}
.card .lb{{font-size:11px;color:var(--t3);text-transform:uppercase;letter-spacing:.04em}}
.card .vl{{font-size:24px;font-weight:700;margin-top:2px;font-family:'JetBrains Mono',monospace}}
.card .sb{{font-size:11px;color:var(--t2);margin-top:2px}}
.g{{color:var(--green)}}.rd{{color:var(--red)}}.bl{{color:var(--blue)}}.am{{color:var(--amber)}}.pp{{color:var(--purple)}}.cy{{color:var(--cyan)}}.pk{{color:var(--pink)}}
.hc{{color:var(--hc)}}.ic{{color:var(--ic)}}
.sec{{background:var(--card);border:1px solid var(--bdr);border-radius:10px;margin-bottom:16px;overflow:hidden}}
.sec-hd{{padding:12px 16px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;justify-content:space-between}}
.sec-hd h3{{font-size:14px;font-weight:600;display:flex;align-items:center;gap:6px}}
.badge{{color:#fff;font-size:10px;font-weight:600;padding:2px 7px;border-radius:8px;font-family:'JetBrains Mono',monospace}}
.bh{{background:var(--hc)}}.bi{{background:var(--ic)}}.bb{{background:var(--blue)}}.br{{background:var(--red)}}.ba{{background:var(--amber)}}
.tscroll{{overflow-x:auto;max-height:600px;overflow-y:auto}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{background:rgba(30,41,59,.5);padding:8px 10px;text-align:left;font-weight:600;font-size:10px;text-transform:uppercase;letter-spacing:.04em;color:var(--t3);white-space:nowrap;position:sticky;top:0;cursor:pointer;z-index:2}}
td{{padding:6px 10px;border-top:1px solid rgba(30,41,59,.3);font-family:'JetBrains Mono',monospace;font-size:11px;white-space:nowrap}}
tr:hover{{background:var(--card2)}}
.rb{{background:linear-gradient(90deg,rgba(16,185,129,.07),transparent)}}
.rs{{background:linear-gradient(90deg,rgba(239,68,68,.07),transparent)}}
.eng{{display:inline-block;padding:2px 7px;border-radius:5px;font-size:10px;font-weight:600;font-family:'JetBrains Mono',monospace}}
.eng-K{{background:rgba(245,158,11,.12);color:var(--amber)}}
.eng-A{{background:rgba(59,130,246,.12);color:var(--blue)}}
.eng-L{{background:rgba(139,92,246,.12);color:var(--purple)}}
.eng-P{{background:rgba(6,182,212,.12);color:var(--cyan)}}
.eng-M{{background:rgba(236,72,153,.12);color:var(--pink)}}
.eng-R{{background:rgba(16,185,129,.12);color:var(--green)}}
.ai{{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:6px;font-size:11px;font-weight:600;font-family:'JetBrains Mono',monospace}}
.ai-h{{background:rgba(16,185,129,.1);color:var(--hc);border:1px solid rgba(16,185,129,.2)}}
.ai-i{{background:rgba(245,158,11,.1);color:var(--ic);border:1px solid rgba(245,158,11,.2)}}
.empty{{text-align:center;padding:30px;color:var(--t3);font-size:13px}}
.srch input{{width:100%;padding:8px 14px;background:var(--card);border:1px solid var(--bdr);border-radius:8px;color:var(--t1);font-size:13px;font-family:'JetBrains Mono',monospace;margin-bottom:12px}}
.srch input:focus{{outline:none;border-color:var(--blue)}}
.err-row{{background:linear-gradient(90deg,rgba(239,68,68,.06),transparent)}}
.warn-row{{background:linear-gradient(90deg,rgba(245,158,11,.06),transparent)}}
.lv-err{{color:var(--red);font-weight:600}}.lv-warn{{color:var(--amber);font-weight:600}}
.tag{{display:inline-block;padding:2px 7px;border-radius:5px;font-size:10px;font-weight:600;font-family:'JetBrains Mono',monospace}}
.tag-lt{{background:rgba(139,92,246,.12);color:var(--purple)}}
.tag-kb{{background:rgba(245,158,11,.12);color:var(--amber)}}
.tag-mm{{background:rgba(236,72,153,.12);color:var(--pink)}}
.tag-rev{{background:rgba(16,185,129,.12);color:var(--green)}}
.tag-oth{{background:rgba(59,130,246,.12);color:var(--blue)}}
.cnt-badge{{display:inline-block;background:rgba(239,68,68,.2);color:var(--red);padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700;font-family:'JetBrains Mono',monospace;min-width:28px;text-align:center}}
</style>
</head>
<body>
<div class="hdr">
  <h1>Quant Engine -- Log Dashboard</h1>
  <div class="meta">Generated: {now} | Date: {TODAY} | HAMPRO: {total_h} | IBKR: {total_i} | Total: {len(proposals)} | Fills: {len(fills)} | Errors: {len(errors_only)}</div>
</div>
<div class="tabs">
  <div class="tab active" onclick="sw('ov')">Overview</div>
  <div class="tab" onclick="sw('prop')">All ({len(proposals)})</div>
  <div class="tab" onclick="sw('fills')">Fills ({len(fills)})</div>
  <div class="tab" onclick="sw('errs')">Errors ({len(errors_only)})</div>
  <div class="tab" onclick="sw('warns')">Warnings ({len(warns_only)})</div>
  <div class="tab" onclick="sw('anp')">ADDNEWPOS ({counts['ADDNEWPOS_ENGINE']['h']+counts['ADDNEWPOS_ENGINE']['i']})</div>
  <div class="tab" onclick="sw('kb')">KARBOTU ({counts['KARBOTU']['h']+counts['KARBOTU']['i']})</div>
  <div class="tab" onclick="sw('lt')">LT_TRIM ({counts['LT_TRIM']['h']+counts['LT_TRIM']['i']})</div>
  <div class="tab" onclick="sw('mm')">MM ({counts['GREATEST_MM']['h']+counts['GREATEST_MM']['i']})</div>
  <div class="tab" onclick="sw('cyc')">Cycles ({len(cycle_entries)})</div>
</div>
""")
    
    # -- OVERVIEW --
    H.append(f"""
<div id="pane-ov" class="pane active">
<div class="grid">
  <div class="card"><div class="lb">Total Proposals</div><div class="vl bl">{len(proposals)}</div><div class="sb">H: {total_h} | I: {total_i}</div></div>
  <div class="card"><div class="lb">HAMPRO</div><div class="vl hc">{total_h}</div><div class="sb">{len(cycles_h)} cycles</div></div>
  <div class="card"><div class="lb">IBKR_PED</div><div class="vl ic">{total_i}</div><div class="sb">{len(cycles_i)} cycles</div></div>
  <div class="card"><div class="lb">Fills</div><div class="vl g">{len(fills)}</div><div class="sb">H:{len(fills_h)} I:{len(fills_i)}</div></div>
  <div class="card"><div class="lb">Errors</div><div class="vl rd">{len(errors_only)}</div><div class="sb">{len(error_summary)} unique</div></div>
  <div class="card"><div class="lb">ADDNEWPOS</div><div class="vl bl">{counts['ADDNEWPOS_ENGINE']['h']+counts['ADDNEWPOS_ENGINE']['i']}</div><div class="sb">H:{counts['ADDNEWPOS_ENGINE']['h']} I:{counts['ADDNEWPOS_ENGINE']['i']}</div></div>
  <div class="card"><div class="lb">KARBOTU</div><div class="vl am">{counts['KARBOTU']['h']+counts['KARBOTU']['i']}</div><div class="sb">H:{counts['KARBOTU']['h']} I:{counts['KARBOTU']['i']}</div></div>
  <div class="card"><div class="lb">LT_TRIM</div><div class="vl pp">{counts['LT_TRIM']['h']+counts['LT_TRIM']['i']}</div><div class="sb">H:{counts['LT_TRIM']['h']} I:{counts['LT_TRIM']['i']}</div></div>
  <div class="card"><div class="lb">MM</div><div class="vl cy">{counts['GREATEST_MM']['h']+counts['GREATEST_MM']['i']}</div><div class="sb">H:{counts['GREATEST_MM']['h']} I:{counts['GREATEST_MM']['i']}</div></div>
  <div class="card"><div class="lb">Cycles</div><div class="vl bl">{len(cycle_entries)}</div><div class="sb">H:{len(cycles_h)} I:{len(cycles_i)}</div></div>
</div>
<div class="sec"><div class="sec-hd"><h3>Breakdown by Engine & Account</h3></div><div class="tscroll"><table>
<thead><tr><th>Engine</th><th>H Buy</th><th>H Sell</th><th>H Total</th><th>I Buy</th><th>I Sell</th><th>I Total</th><th>Grand</th></tr></thead>
<tbody>""")
    
    for label, ek, ec in [('ADDNEWPOS','ADDNEWPOS_ENGINE','A'), ('KARBOTU','KARBOTU','K'),
                           ('LT_TRIM','LT_TRIM','L'), ('MM','GREATEST_MM','M')]:
        c = counts[ek]
        H.append(f"""<tr><td><span class='eng eng-{ec}'>{label}</span></td>
<td class='g'>{c['h_buy']}</td><td class='rd'>{c['h_sell']}</td><td>{c['h']}</td>
<td class='g'>{c['i_buy']}</td><td class='rd'>{c['i_sell']}</td><td>{c['i']}</td>
<td><b>{c['h']+c['i']}</b></td></tr>""")
    
    H.append("</tbody></table></div></div>")
    
    # -- Error summary in overview --
    if error_summary:
        H.append("""<div class="sec"><div class="sec-hd"><h3>Error Summary</h3></div><div class="tscroll"><table>
<thead><tr><th>Count</th><th>First</th><th>Last</th><th>Source</th><th>Message</th></tr></thead><tbody>""")
        for key in sorted(error_summary, key=lambda k: error_summary[k]['count'], reverse=True):
            es = error_summary[key]
            H.append(f"""<tr class="err-row"><td><span class="cnt-badge">{es['count']}</span></td>
<td>{es['first']}</td><td>{es['last']}</td><td style="font-size:10px">{_esc(es['source'][:40])}</td>
<td style="max-width:500px;overflow:hidden;text-overflow:ellipsis">{_esc(es['msg'][:120])}</td></tr>""")
        H.append("</tbody></table></div></div>")
    
    # -- Fills summary in overview --
    if fills:
        # Group fills by symbol
        fill_by_sym = {}
        for f in fills:
            sym = f['symbol']
            if sym not in fill_by_sym:
                fill_by_sym[sym] = {'buys': 0, 'sells': 0, 'buy_val': 0.0, 'sell_val': 0.0, 'tags': set(), 'source': set()}
            qty = float(f['qty'])
            price = float(f['price'])
            if f['action'] == 'BUY':
                fill_by_sym[sym]['buys'] += qty
                fill_by_sym[sym]['buy_val'] += qty * price
            else:
                fill_by_sym[sym]['sells'] += qty
                fill_by_sym[sym]['sell_val'] += qty * price
            fill_by_sym[sym]['tags'].add(f['tag'].split('_STEP_')[0])
            fill_by_sym[sym]['source'].add(f['source'])
        
        H.append("""<div class="sec"><div class="sec-hd"><h3>Fills Summary by Symbol</h3></div><div class="tscroll"><table>
<thead><tr><th>Symbol</th><th>Buy Qty</th><th>Buy $</th><th>Sell Qty</th><th>Sell $</th><th>Net Qty</th><th>Tags</th><th>Account</th></tr></thead><tbody>""")
        for sym in sorted(fill_by_sym, key=lambda s: fill_by_sym[s]['buys'] + fill_by_sym[s]['sells'], reverse=True):
            fs = fill_by_sym[sym]
            net = fs['buys'] - fs['sells']
            net_cls = 'g' if net > 0 else 'rd' if net < 0 else ''
            src_badge = ' '.join(f'<span class="badge {"bh" if s=="HAMPRO" else "bi"}">{s[:1]}</span>' for s in sorted(fs['source']))
            tag_str = ', '.join(sorted(fs['tags']))
            tag_cls = 'tag-lt' if 'LT' in tag_str else 'tag-kb' if 'KARB' in tag_str else 'tag-mm' if 'MM' in tag_str else 'tag-rev' if 'REV' in tag_str else 'tag-oth'
            H.append(f"""<tr><td><b>{_esc(sym)}</b></td>
<td class="g">{fs['buys']:g}</td><td class="g">${fs['buy_val']:,.0f}</td>
<td class="rd">{fs['sells']:g}</td><td class="rd">${fs['sell_val']:,.0f}</td>
<td class="{net_cls}">{net:+g}</td>
<td><span class="tag {tag_cls}">{_esc(tag_str[:40])}</span></td>
<td>{src_badge}</td></tr>""")
        H.append("</tbody></table></div></div>")
    
    H.append("</div>\n")
    
    # -- Helper for sub-tabs --
    def make_subtabs(pid, data_h, data_i, headers, row_fn, show_eng=False):
        s = []
        s.append(f"""
<div class="sub-tabs">
  <div class="sub-tab act" data-a="H" onclick="swS('{pid}','H')">HAMPRO <span class="n">{len(data_h)}</span></div>
  <div class="sub-tab" data-a="I" onclick="swS('{pid}','I')">IBKR_PED <span class="n">{len(data_i)}</span></div>
</div>""")
        for acct, items, active in [('H', data_h, ' act'), ('I', data_i, '')]:
            acct_label = 'HAMPRO' if acct == 'H' else 'IBKR_PED'
            bc = 'bh' if acct == 'H' else 'bi'
            aic = 'ai-h' if acct == 'H' else 'ai-i'
            tid = f"{pid}-{acct}-t"
            s.append(f"""
<div id="sc-{pid}-{acct}" class="sc{active}">
<div class="srch"><input placeholder="Search..." onkeyup="filt('{tid}',this.value)"></div>
<div class="sec"><div class="sec-hd"><h3><span class="ai {aic}">{acct_label}</span> <span class="badge {bc}">{len(items)}</span></h3></div>
<div class="tscroll"><table id="{tid}"><thead><tr>""")
            for h in headers:
                s.append(f"<th>{h}</th>")
            s.append("</tr></thead><tbody>")
            if not items:
                s.append(f'</tbody></table><div class="empty">No data for {acct_label}</div>')
            else:
                for p in items:
                    rc = 'rb' if p.get('action','') in ('BUY','COVER') else 'rs'
                    s.append(f'<tr class="{rc}">')
                    vals = row_fn(p)
                    for j, v in enumerate(vals):
                        if show_eng and headers[j] == 'Engine':
                            ec = 'K' if 'KARB' in v else 'A' if 'ADD' in v else 'L' if 'LT' in v else 'M' if 'MM' in v or 'GREAT' in v else 'P'
                            s.append(f'<td><span class="eng eng-{ec}">{_esc(v)}</span></td>')
                        elif headers[j] == 'Action':
                            cc = 'g' if v in ('BUY','COVER') else 'rd'
                            s.append(f'<td class="{cc}">{v}</td>')
                        elif headers[j] == 'Tag':
                            tc = 'tag-lt' if 'LT' in v else 'tag-kb' if 'KARB' in v else 'tag-mm' if 'MM' in v else 'tag-rev' if 'REV' in v else 'tag-oth'
                            s.append(f'<td><span class="tag {tc}">{_esc(v)}</span></td>')
                        else:
                            s.append(f'<td>{_esc(str(v))}</td>')
                    s.append('</tr>\n')
                s.append("</tbody></table>")
            s.append("</div></div></div>\n")
        return ''.join(s)
    
    # -- ALL PROPOSALS --
    H.append('<div id="pane-prop" class="pane">\n')
    H.append(make_subtabs('prop', all_by_account['HAMPRO'], all_by_account['IBKR_PED'],
        ['Time','Symbol','Action','Qty','Price','Engine','Cycle'],
        lambda p: [p['time'], p['symbol'], p['action'], p['qty'], p['price'], p['engine'], p.get('cycle','')],
        show_eng=True))
    H.append('</div>\n')
    
    # -- FILLS --
    H.append('<div id="pane-fills" class="pane">\n')
    H.append('<h2 style="font-size:16px;margin-bottom:12px">Fills</h2>\n')
    H.append(make_subtabs('fills', fills_h, fills_i,
        ['Time','Symbol','Action','Qty','Price','Tag'],
        lambda p: [p['time'], p['symbol'], p['action'], p['qty'], p['price'], p['tag']]))
    H.append('</div>\n')
    
    # -- ERRORS --
    H.append(f'<div id="pane-errs" class="pane">\n')
    H.append(f'<h2 style="font-size:16px;margin-bottom:12px">Errors ({len(errors_only)})</h2>\n')
    H.append("""<div class="srch"><input placeholder="Search errors..." onkeyup="filt('err-t',this.value)"></div>""")
    H.append("""<div class="sec"><div class="sec-hd"><h3>All Error Lines</h3></div><div class="tscroll"><table id="err-t">
<thead><tr><th>Time</th><th>Source</th><th>Message</th><th>Session</th></tr></thead><tbody>""")
    for e in errors_only:
        H.append(f'<tr class="err-row"><td>{e["time"]}</td><td style="font-size:10px">{_esc(e["source"][:50])}</td>')
        H.append(f'<td style="max-width:600px;overflow:hidden;text-overflow:ellipsis;white-space:normal">{_esc(e["message"])}</td>')
        H.append(f'<td style="font-size:10px">{e["session"]}</td></tr>\n')
    H.append("</tbody></table></div></div></div>\n")
    
    # -- WARNINGS --
    H.append(f'<div id="pane-warns" class="pane">\n')
    H.append(f'<h2 style="font-size:16px;margin-bottom:12px">Warnings ({len(warns_only)})</h2>\n')
    # Deduplicate warnings for summary view
    warn_summary = {}
    for w in warns_only:
        key = w['message'][:80]
        if key not in warn_summary:
            warn_summary[key] = {'count': 0, 'first': w['time'], 'last': w['time'], 'msg': w['message'], 'source': w['source']}
        warn_summary[key]['count'] += 1
        warn_summary[key]['last'] = w['time']
    
    H.append("""<div class="sec"><div class="sec-hd"><h3>Warning Summary (deduplicated)</h3></div><div class="tscroll"><table>
<thead><tr><th>Count</th><th>First</th><th>Last</th><th>Source</th><th>Message</th></tr></thead><tbody>""")
    for key in sorted(warn_summary, key=lambda k: warn_summary[k]['count'], reverse=True):
        ws = warn_summary[key]
        H.append(f'<tr class="warn-row"><td><span class="cnt-badge" style="background:rgba(245,158,11,.2);color:var(--amber)">{ws["count"]}</span></td>')
        H.append(f'<td>{ws["first"]}</td><td>{ws["last"]}</td>')
        H.append(f'<td style="font-size:10px">{_esc(ws["source"][:40])}</td>')
        H.append(f'<td style="max-width:500px;overflow:hidden;text-overflow:ellipsis;white-space:normal">{_esc(ws["msg"][:150])}</td></tr>\n')
    H.append("</tbody></table></div></div></div>\n")
    
    # -- ENGINE PANES --
    for pid, ek, label, icon in [
        ('anp','ADDNEWPOS_ENGINE','ADDNEWPOS',''),
        ('kb','KARBOTU','KARBOTU',''),
        ('lt','LT_TRIM','LT_TRIM',''),
        ('mm','GREATEST_MM','MM / Market Making',''),
    ]:
        H.append(f'<div id="pane-{pid}" class="pane"><h2 style="font-size:16px;margin-bottom:12px">{label}</h2>\n')
        H.append(make_subtabs(pid, engines_by_account[ek]['HAMPRO'], engines_by_account[ek]['IBKR_PED'],
            ['Time','Symbol','Action','Qty','Price','Cycle'],
            lambda p: [p['time'], p['symbol'], p['action'], p['qty'], p['price'], p.get('cycle','')]))
        H.append('</div>\n')
    
    # -- CYCLES --
    H.append('<div id="pane-cyc" class="pane">\n')
    H.append(f"""
<div class="sub-tabs">
  <div class="sub-tab act" data-a="H" onclick="swS('cyc','H')">HAMPRO <span class="n">{len(cycles_h)}</span></div>
  <div class="sub-tab" data-a="I" onclick="swS('cyc','I')">IBKR_PED <span class="n">{len(cycles_i)}</span></div>
</div>""")
    for acct, items, active in [('H', cycles_h, ' act'), ('I', cycles_i, '')]:
        acct_label = 'HAMPRO' if acct == 'H' else 'IBKR_PED'
        bc = 'bh' if acct == 'H' else 'bi'
        aic = 'ai-h' if acct == 'H' else 'ai-i'
        H.append(f"""
<div id="sc-cyc-{acct}" class="sc{active}">
<div class="sec"><div class="sec-hd"><h3><span class="ai {aic}">{acct_label}</span> Cycles <span class="badge {bc}">{len(items)}</span></h3></div>
<div class="tscroll"><table><thead><tr><th>Time</th><th>Cycle</th><th>Session</th></tr></thead><tbody>""")
        for e in items:
            H.append(f'<tr><td>{e["ts"]}</td><td>{e["cycle"]}</td><td>{e["session"]}</td></tr>\n')
        H.append("</tbody></table></div></div></div>\n")
    H.append('</div>\n')
    
    # -- JAVASCRIPT --
    H.append("""
<script>
function sw(id){
  document.querySelectorAll('.pane').forEach(e=>e.classList.remove('active'));
  document.querySelectorAll('.tabs .tab').forEach(e=>e.classList.remove('active'));
  document.getElementById('pane-'+id).classList.add('active');
  event.target.classList.add('active');
}
function swS(pid, a){
  const p=document.getElementById('pane-'+pid)||document.querySelector('.pane.active');
  if(!p)return;
  p.querySelectorAll('.sub-tab').forEach(e=>e.classList.remove('act'));
  p.querySelectorAll('.sc').forEach(e=>e.classList.remove('act'));
  p.querySelectorAll(`.sub-tab[data-a="${a}"]`).forEach(e=>e.classList.add('act'));
  const c=document.getElementById(`sc-${pid}-${a}`);
  if(c)c.classList.add('act');
}
function filt(tid,q){
  const t=document.getElementById(tid);if(!t)return;
  q=q.toLowerCase();
  t.querySelectorAll('tbody tr').forEach(r=>{r.style.display=r.textContent.toLowerCase().includes(q)?'':'none'});
}
document.querySelectorAll('th').forEach(th=>{
  th.addEventListener('click',function(){
    const t=this.closest('table'),tb=t.querySelector('tbody'),rs=Array.from(tb.querySelectorAll('tr'));
    const i=Array.from(this.parentNode.children).indexOf(this);
    const asc=this.dataset.asc!=='true';this.dataset.asc=asc;
    rs.sort((a,b)=>{
      let va=a.children[i]?.textContent||'',vb=b.children[i]?.textContent||'';
      let na=parseFloat(va),nb=parseFloat(vb);
      if(!isNaN(na)&&!isNaN(nb))return asc?na-nb:nb-na;
      return asc?va.localeCompare(vb):vb.localeCompare(va);
    });
    rs.forEach(r=>tb.appendChild(r));
  });
});
</script>
</body></html>
""")
    return ''.join(H)

def _esc(s):
    """HTML escape"""
    return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def main():
    print("Loading backend logs...")
    logs = load_backend_logs()
    print(f"  Found {len(logs)} backend log files")
    
    print("Parsing cycle-account mapping...")
    cycle_entries = parse_cycle_account_map(logs)
    print(f"  Found {len(cycle_entries)} cycle entries")
    for e in cycle_entries:
        print(f"    {e['session']}: Cycle {e['cycle']} -> {e['account']} @ {e['ts']}")
    
    windows = build_time_windows(cycle_entries)
    
    print("\nParsing proposals from logs...")
    proposals = parse_proposals(logs)
    print(f"  Found {len(proposals)} proposals")
    
    print("\nParsing fills from logs...")
    fills = parse_fills(logs)
    fills_h = sum(1 for f in fills if f['source'] == 'HAMPRO')
    fills_i = sum(1 for f in fills if f['source'] == 'IBKR_PED')
    print(f"  Found {len(fills)} fills (HAMPRO: {fills_h}, IBKR: {fills_i})")
    
    print("\nParsing errors/warnings from logs...")
    errors = parse_errors(logs)
    err_count = sum(1 for e in errors if e['level'] == 'ERROR')
    warn_count = sum(1 for e in errors if e['level'] == 'WARNING')
    print(f"  Found {err_count} errors, {warn_count} warnings")
    
    # Count proposals by account
    for p in proposals:
        p['account'] = get_account_for_time(windows, p['time'])
    h_count = sum(1 for p in proposals if p['account'] == 'HAMPRO')
    i_count = sum(1 for p in proposals if p['account'] == 'IBKR_PED')
    print(f"\n  Proposals: HAMPRO={h_count}, IBKR_PED={i_count}")
    
    # Reset account assignment (will be done again in generate_html)
    for p in proposals:
        del p['account']
    
    print("\nGenerating HTML dashboard...")
    html = generate_html(proposals, fills, errors, cycle_entries, windows)
    
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"\nDashboard written to: {OUTPUT}")
    print(f"   Size: {len(html):,} bytes")

if __name__ == '__main__':
    main()
