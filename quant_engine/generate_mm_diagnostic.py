"""
MM Diagnostic Dashboard Generator
Parses backend logs and produces a self-contained HTML dashboard.
"""
import re, json, glob, os
from collections import defaultdict

ANSI = re.compile(r'\x1b\[[0-9;]*m')
LOG_DIR = r"C:\StockTracker\quant_engine\data\logs\terminals"
OUT_HTML = r"C:\StockTracker\quant_engine\mm_diagnostic.html"

def find_latest_backend_log():
    logs = sorted(glob.glob(os.path.join(LOG_DIR, "backend_*.log")), key=os.path.getmtime, reverse=True)
    return logs[0] if logs else None

def parse_mm_order(line):
    m = re.search(r'\[MM_ORDER\]\s+(BUY|SELL)\s+(\S+(?:\s+\S+)?)\s+(\d+)lot\s+@\$(\S+)\s+\|\s+Score=(\S+)\s+Sc=(\S+)\s+Bid=\$(\S+)\s+Ask=\$(\S+)\s+Son5=(\S+)\s+(.*)', line)
    if not m:
        return None
    rest = m.group(10)
    volav_match = re.search(r'Volav_(\S+)=\$(\S+)', rest)
    volav_window = volav_match.group(1) if volav_match else None
    volav_val = volav_match.group(2) if volav_match else None
    metrics = {}
    for key in ['fbtot', 'sfstot', 'gort', 'ucuz', 'pah']:
        km = re.search(rf'{key}=(\S+)', rest)
        if km:
            val = km.group(1)
            metrics[key] = None if val == 'None' else float(val)
    return {
        'action': m.group(1), 'symbol': m.group(2), 'qty': int(m.group(3)),
        'price': float(m.group(4)), 'score': float(m.group(5)),
        'scenario': m.group(6), 'bid': float(m.group(7)), 'ask': float(m.group(8)),
        'son5': float(m.group(9)) if m.group(9) != 'None' else None,
        'volav_window': volav_window,
        'volav': float(volav_val) if volav_val else None,
        **metrics
    }

def parse_fill(line):
    m = re.search(r'\[FILL\]\s+(?:\[HIST\]\s+)?(\S+(?:\s+\S+)?)\s+(BUY|SELL|SHORT|COVER)\s+(\S+)\s+@\s+\$(\S+)\s+\|\s+Tag:\s+(\S+)\s+\|\s+Type:\s+(\S+)', line)
    if not m:
        return None
    ts_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
    return {
        'ts': ts_match.group(1) if ts_match else '',
        'symbol': m.group(1), 'action': m.group(2), 'qty': float(m.group(3)),
        'price': float(m.group(4)), 'tag': m.group(5), 'type': m.group(6),
        'account': 'IBKR_PED' if '[HIST]' in line else 'HAMPRO',
    }

def parse_rev(line):
    sent = re.search(r'REV sent via IBKR:\s+(BUY|SELL)\s+(\S+)\s+(\S+(?:\s+\S+)?)\s+@\s+\$(\S+)', line)
    if sent:
        ts_m = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
        return {'ts': ts_m.group(1) if ts_m else '', 'action': sent.group(1),
                'qty': float(sent.group(2)), 'symbol': sent.group(3),
                'price': float(sent.group(4)), 'status': 'SENT'}
    failed = re.search(r'REV IBKR send failed for (\S+(?:\s+\S+)?):\s+(.*)', line)
    if failed:
        ts_m = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
        return {'ts': ts_m.group(1) if ts_m else '', 'symbol': failed.group(1).rstrip(':'),
                'reason': failed.group(2), 'status': 'FAILED'}
    return None

def parse_frontlama(line):
    m = re.search(r'\[FRONTED\]\s+(\S+(?:\s+\S+)?)\s+(BUY|SELL)\s+(\d+)\s+\|\s+Price:\s+\$(\S+)\s+.+?\$(\S+)\s+\(sacrifice:\s+\$(\S+)\)\s+\|\s+Tag:\s+(\S+)', line)
    if not m:
        return None
    ts_m = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
    return {
        'ts': ts_m.group(1) if ts_m else '', 'symbol': m.group(1),
        'action': m.group(2), 'qty': int(m.group(3)),
        'base_price': float(m.group(4)), 'fronted_price': float(m.group(5)),
        'sacrifice': float(m.group(6)), 'tag': m.group(7),
    }

HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MM Diagnostic Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#0f1117;--surface:#1a1d27;--surface2:#22263a;--border:#2d3148;--text:#e4e6f0;--text-dim:#8b8fa5;--accent:#6366f1;--green:#22c55e;--red:#ef4444;--orange:#f59e0b;--cyan:#06b6d4;--pink:#ec4899}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
.header{background:linear-gradient(135deg,#1e1b4b 0%,#312e81 50%,#1e1b4b 100%);padding:20px 32px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}
.header h1{font-size:1.5rem;font-weight:700}.header h1 span{color:var(--accent)}
.header .meta{font-size:.85rem;color:var(--text-dim)}
.tabs{display:flex;gap:2px;background:var(--surface);padding:4px;border-bottom:1px solid var(--border)}
.tab{padding:10px 24px;cursor:pointer;border-radius:6px;font-size:.9rem;font-weight:500;color:var(--text-dim);transition:all .2s}
.tab:hover{background:var(--surface2);color:var(--text)}.tab.active{background:var(--accent);color:#fff}
.content{padding:24px 32px}.section{margin-bottom:32px}
.section-title{font-size:1.1rem;font-weight:600;margin-bottom:12px;display:flex;align-items:center;gap:8px}
.badge{font-size:.75rem;padding:2px 8px;border-radius:10px;font-weight:600}
.badge-green{background:rgba(34,197,94,.15);color:var(--green)}.badge-red{background:rgba(239,68,68,.15);color:var(--red)}
.badge-orange{background:rgba(245,158,11,.15);color:var(--orange)}.badge-cyan{background:rgba(6,182,212,.15);color:var(--cyan)}
.badge-pink{background:rgba(236,72,153,.15);color:var(--pink)}
table{width:100%;border-collapse:collapse;background:var(--surface);border-radius:8px;overflow:hidden}
th{text-align:left;padding:10px 14px;font-size:.78rem;text-transform:uppercase;letter-spacing:.05em;color:var(--text-dim);background:var(--surface2);border-bottom:1px solid var(--border);white-space:nowrap}
td{padding:8px 14px;font-size:.85rem;border-bottom:1px solid var(--border);white-space:nowrap}
tr:hover{background:rgba(99,102,241,.06)}
.score-low{color:var(--orange);font-weight:600}.score-med{color:var(--text);font-weight:500}.score-high{color:var(--green);font-weight:600}
.action-buy{color:var(--green);font-weight:600}.action-sell{color:var(--red);font-weight:600}
.scenario-tag{display:inline-block;padding:2px 6px;border-radius:4px;font-size:.75rem;font-weight:600}
.sc-ORIGINAL{background:rgba(99,102,241,.15);color:#818cf8}.sc-NEW_SON5{background:rgba(6,182,212,.15);color:var(--cyan)}
.sc-VOLAV_ANCHOR{background:rgba(236,72,153,.15);color:var(--pink)}.sc-BOTH_NEW{background:rgba(245,158,11,.15);color:var(--orange)}
.sc-NEW_ENTRY{background:rgba(34,197,94,.15);color:var(--green)}
.rev-yes{color:var(--green)}.rev-no{color:var(--red);font-weight:600}
.stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:24px}
.stat-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px}
.stat-card .label{font-size:.78rem;color:var(--text-dim);margin-bottom:4px}.stat-card .value{font-size:1.6rem;font-weight:700}
.panel{display:none}.panel.active{display:block}
.spread-col{color:var(--text-dim)}.fill-row-warn{background:rgba(239,68,68,.08)!important}
.front-sacrifice{color:var(--orange);font-weight:600}
</style>
</head>
<body>
<div class="header">
    <h1>🔧 <span>MM Diagnostic</span> Dashboard</h1>
    <div class="meta" id="headerMeta"></div>
</div>
<div class="tabs">
    <div class="tab active" onclick="showPanel('mm',this)">📊 MM Low Scores</div>
    <div class="tab" onclick="showPanel('fills',this)">💰 Fills & REV Tracking</div>
    <div class="tab" onclick="showPanel('frontlama',this)">🔄 Frontlama</div>
    <div class="tab" onclick="showPanel('rev',this)">📤 REV Orders</div>
</div>
<div class="content">
    <div class="panel active" id="panel-mm">
        <div class="stat-grid" id="mmStats"></div>
        <div class="section">
            <div class="section-title">🟢 Bottom 15 BUY (LONG) — Lowest MM Scores <span class="badge badge-green" id="buyCount"></span></div>
            <table><thead><tr><th>#</th><th>Symbol</th><th>Qty</th><th>Price</th><th>MM Score</th><th>Scenario</th><th>Son5</th><th>Volav</th><th>Bid</th><th>Ask</th><th>Spread</th><th>FBtot</th><th>SFStot</th><th>GORT</th></tr></thead><tbody id="buyTable"></tbody></table>
        </div>
        <div class="section">
            <div class="section-title">🔴 Bottom 15 SELL (SHORT) — Lowest MM Scores <span class="badge badge-red" id="sellCount"></span></div>
            <table><thead><tr><th>#</th><th>Symbol</th><th>Qty</th><th>Price</th><th>MM Score</th><th>Scenario</th><th>Son5</th><th>Volav</th><th>Bid</th><th>Ask</th><th>Spread</th><th>FBtot</th><th>SFStot</th><th>GORT</th></tr></thead><tbody id="sellTable"></tbody></table>
        </div>
    </div>
    <div class="panel" id="panel-fills">
        <div class="stat-grid" id="fillStats"></div>
        <div class="section">
            <div class="section-title">💰 Fills ≥200 Lot — REV Order Tracking <span class="badge badge-orange" id="fillCount"></span></div>
            <p style="color:var(--text-dim);font-size:.85rem;margin-bottom:12px">🔴 Red rows = 200+ lot filled but NO REV order sent</p>
            <table><thead><tr><th>Symbol</th><th>Total Qty</th><th>Fill Count</th><th>Tags</th><th>Account</th><th>REV Sent?</th><th>REV Match</th></tr></thead><tbody id="fillTable"></tbody></table>
        </div>
    </div>
    <div class="panel" id="panel-frontlama">
        <div class="section">
            <div class="section-title">🔄 Frontlama Orders <span class="badge badge-cyan" id="frontCount"></span></div>
            <table><thead><tr><th>Time</th><th>Symbol</th><th>Action</th><th>Qty</th><th>Base Price</th><th>Fronted Price</th><th>Sacrifice</th><th>Tag</th></tr></thead><tbody id="frontTable"></tbody></table>
        </div>
    </div>
    <div class="panel" id="panel-rev">
        <div class="section">
            <div class="section-title">📤 REV Orders <span class="badge badge-pink" id="revCount"></span></div>
            <table><thead><tr><th>Time</th><th>Symbol</th><th>Action</th><th>Qty</th><th>Price</th><th>Status</th><th>Reason</th></tr></thead><tbody id="revTable"></tbody></table>
        </div>
    </div>
</div>
<script>
const DATA = __DATA_PLACEHOLDER__;

function showPanel(n,el){document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.getElementById('panel-'+n).classList.add('active');el.classList.add('active')}
function sC(s){return s<40?'score-low':s<70?'score-med':'score-high'}
function fmt(v,d=2){return v===null||v===undefined?'<span style="color:var(--text-dim)">N/A</span>':Number(v).toFixed(d)}

function renderMM(o,i){
    const sp=(o.ask-o.bid).toFixed(2);
    const vl=o.volav?`${o.volav_window}=$${o.volav.toFixed(2)}`:'<span style="color:var(--text-dim)">—</span>';
    return`<tr><td>${i+1}</td><td><strong>${o.symbol}</strong></td><td>${o.qty}</td><td>$${o.price.toFixed(2)}</td><td class="${sC(o.score)}">${o.score.toFixed(1)}</td><td><span class="scenario-tag sc-${o.scenario}">${o.scenario}</span></td><td>${o.son5!==null?'$'+o.son5.toFixed(2):'N/A'}</td><td>${vl}</td><td>$${o.bid.toFixed(2)}</td><td>$${o.ask.toFixed(2)}</td><td class="spread-col">$${sp}</td><td>${fmt(o.fbtot)}</td><td>${fmt(o.sfstot)}</td><td>${fmt(o.gort)}</td></tr>`
}
function renderFill(f){
    const w=f.has_200_plus&&!f.rev_sent?'fill-row-warn':'';
    const ri=f.rev_sent?'<span class="rev-yes">✅ Yes</span>':'<span class="rev-no">❌ No</span>';
    const rs=f.rev_symbol_match&&f.rev_symbol_match.length?f.rev_symbol_match.join(', '):'—';
    return`<tr class="${w}"><td><strong>${f.symbol}</strong></td><td>${f.total_qty}</td><td>${f.fill_count}</td><td>${f.tags.map(t=>`<span class="badge ${t.includes('MM_')?'badge-pink':t.includes('KARBOTU')?'badge-orange':'badge-cyan'}">${t}</span>`).join(' ')}</td><td>${f.accounts.join(', ')}</td><td>${ri}</td><td>${rs}</td></tr>`
}
function renderFront(f){
    return`<tr><td>${(f.ts||'').split(' ')[1]||f.ts}</td><td><strong>${f.symbol}</strong></td><td class="${f.action==='BUY'?'action-buy':'action-sell'}">${f.action}</td><td>${f.qty}</td><td>$${f.base_price.toFixed(2)}</td><td>$${f.fronted_price.toFixed(2)}</td><td class="front-sacrifice">$${f.sacrifice.toFixed(2)}</td><td><span class="badge ${f.tag.includes('MM_')?'badge-pink':f.tag.includes('KARBOTU')?'badge-orange':'badge-cyan'}">${f.tag}</span></td></tr>`
}
function renderRev(r){
    const si=r.status==='SENT'?'<span class="rev-yes">✅ SENT</span>':'<span class="rev-no">❌ FAILED</span>';
    return`<tr><td>${(r.ts||'').split(' ')[1]||r.ts}</td><td><strong>${r.symbol}</strong></td><td class="${r.action==='BUY'?'action-buy':r.action==='SELL'?'action-sell':''}">${r.action||'—'}</td><td>${r.qty||'—'}</td><td>${r.price?'$'+r.price.toFixed(2):'—'}</td><td>${si}</td><td style="color:var(--text-dim)">${r.reason||'—'}</td></tr>`
}

const d=DATA;
document.getElementById('headerMeta').textContent=`Log: ${d.log_file} | Last Cycle: ${d.last_cycle} | ${d.total_mm_orders} MM orders`;
document.getElementById('mmStats').innerHTML=`
<div class="stat-card"><div class="label">Total MM Orders</div><div class="value">${d.total_mm_orders}</div></div>
<div class="stat-card"><div class="label">BUY (LONG)</div><div class="value" style="color:var(--green)">${d.total_mm_buys}</div></div>
<div class="stat-card"><div class="label">SELL (SHORT)</div><div class="value" style="color:var(--red)">${d.total_mm_sells}</div></div>
<div class="stat-card"><div class="label">Min BUY Score</div><div class="value" style="color:var(--orange)">${d.bottom_15_buys.length?d.bottom_15_buys[0].score.toFixed(1):'N/A'}</div></div>
<div class="stat-card"><div class="label">Min SELL Score</div><div class="value" style="color:var(--orange)">${d.bottom_15_sells.length?d.bottom_15_sells[0].score.toFixed(1):'N/A'}</div></div>`;
document.getElementById('buyCount').textContent=d.bottom_15_buys.length+' shown';
document.getElementById('buyTable').innerHTML=d.bottom_15_buys.map(renderMM).join('');
document.getElementById('sellCount').textContent=d.bottom_15_sells.length+' shown';
document.getElementById('sellTable').innerHTML=d.bottom_15_sells.map(renderMM).join('');
const noRev=d.fills_200_plus.filter(f=>!f.rev_sent).length;
document.getElementById('fillStats').innerHTML=`
<div class="stat-card"><div class="label">Fills ≥200 lot</div><div class="value">${d.fills_200_plus.length}</div></div>
<div class="stat-card"><div class="label">With REV ✅</div><div class="value" style="color:var(--green)">${d.fills_200_plus.length-noRev}</div></div>
<div class="stat-card"><div class="label">Missing REV ❌</div><div class="value" style="color:var(--red)">${noRev}</div></div>
<div class="stat-card"><div class="label">Frontlama Orders</div><div class="value">${d.frontlama_orders.length}</div></div>`;
document.getElementById('fillCount').textContent=d.fills_200_plus.length+' symbols';
document.getElementById('fillTable').innerHTML=d.fills_200_plus.map(renderFill).join('');
document.getElementById('frontCount').textContent=d.frontlama_orders.length+' orders';
document.getElementById('frontTable').innerHTML=d.frontlama_orders.map(renderFront).join('');
document.getElementById('revCount').textContent=d.rev_orders.length+' total';
document.getElementById('revTable').innerHTML=d.rev_orders.map(renderRev).join('');
</script>
</body>
</html>'''

def main():
    log_path = find_latest_backend_log()
    if not log_path:
        print("No backend log found!")
        return
    print(f"Parsing: {os.path.basename(log_path)}")
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = ANSI.sub('', f.read())
    lines = content.split('\n')

    mm_orders, fills_raw, revs, frontlamas = [], [], [], []
    for line in lines:
        if '[MM_ORDER]' in line:
            p = parse_mm_order(line)
            if p:
                ts_m = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                p['ts'] = ts_m.group(1) if ts_m else ''
                mm_orders.append(p)
        if '[FILL]' in line and 'Tag:' in line:
            p = parse_fill(line)
            if p: fills_raw.append(p)
        if 'REV' in line and ('REV sent' in line or 'REV IBKR send failed' in line):
            p = parse_rev(line)
            if p: revs.append(p)
        if '[FRONTED]' in line:
            p = parse_frontlama(line)
            if p: frontlamas.append(p)

    # Group MM by minute, get last cycle
    mm_by_min = defaultdict(list)
    for o in mm_orders:
        mm_by_min[o['ts'][:16]].append(o)
    last_key = sorted(mm_by_min.keys())[-1] if mm_by_min else ''
    last_mm = mm_by_min.get(last_key, [])

    buys = sorted([o for o in last_mm if o['action']=='BUY'], key=lambda x: x['score'])
    sells = sorted([o for o in last_mm if o['action']=='SELL'], key=lambda x: x['score'])

    # Group fills by symbol
    fill_summary = defaultdict(lambda: {'total_qty':0,'fills':[],'tags':set(),'accounts':set()})
    for f in fills_raw:
        s = f['symbol']
        fill_summary[s]['total_qty'] += f['qty']
        fill_summary[s]['fills'].append(f)
        fill_summary[s]['tags'].add(f['tag'])
        fill_summary[s]['accounts'].add(f['account'])

    rev_symbols = {r.get('symbol','') for r in revs}
    fills_grouped = []
    for sym, data in sorted(fill_summary.items(), key=lambda x: -x[1]['total_qty']):
        fg = {
            'symbol': sym, 'total_qty': data['total_qty'], 'fill_count': len(data['fills']),
            'tags': list(data['tags']), 'accounts': list(data['accounts']),
            'has_200_plus': data['total_qty'] >= 200,
        }
        if fg['has_200_plus']:
            variants = {sym}
            if '-' in sym:
                parts = sym.split('-', 1)
                variants.add(f"{parts[0]} PR{parts[1]}")
            fg['rev_sent'] = bool(variants & rev_symbols)
            fg['rev_symbol_match'] = list(variants & rev_symbols)
            fills_grouped.append(fg)

    output = {
        'log_file': os.path.basename(log_path), 'last_cycle': last_key,
        'total_mm_orders': len(last_mm), 'total_mm_buys': len(buys), 'total_mm_sells': len(sells),
        'bottom_15_buys': buys[:15], 'bottom_15_sells': sells[:15],
        'fills_200_plus': fills_grouped, 'total_fills': len(fills_raw),
        'rev_orders': revs, 'rev_symbols': list(rev_symbols), 'frontlama_orders': frontlamas,
    }

    # Embed data into HTML
    json_str = json.dumps(output, default=str)
    html = HTML_TEMPLATE.replace('__DATA_PLACEHOLDER__', json_str)
    with open(OUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Dashboard: {OUT_HTML}")
    print(f"  MM (last cycle {last_key}): {len(last_mm)} ({len(buys)} BUY, {len(sells)} SELL)")
    print(f"  Min BUY score: {buys[0]['score']:.1f}" if buys else "  No BUY")
    print(f"  Min SELL score: {sells[0]['score']:.1f}" if sells else "  No SELL")
    print(f"  Fills ≥200: {len(fills_grouped)}")
    norev = len([f for f in fills_grouped if not f['rev_sent']])
    print(f"  Missing REV: {norev}")
    print(f"  REV orders: {len(revs)}, Frontlama: {len(frontlamas)}")

if __name__ == '__main__':
    main()
