"""Test: Run a single Claude Haiku observer cycle with ENHANCED metrics."""
import os, sys, asyncio
sys.path.insert(0, os.path.dirname(__file__))
OUT_FILE = os.path.join(os.path.dirname(__file__), 'test_claude_result.txt')

os.environ['ANTHROPIC_API_KEY'] = 'sk-ant-' + 'api03-0VToNNEpSvOioLPr8PvVXvtxKNI3tPaX3nM6NvFDyJbMEhGljtnKveAjXfDXG2-PWX2Tqx-oe5ixGr8dV_fHeA-I-28IwAA'

from app.agent.trading_observer import TradingObserverAgent

async def test():
    agent = TradingObserverAgent(
        gemini_api_key=None,
        claude_api_key=os.environ['ANTHROPIC_API_KEY'],
        interval_seconds=600,
    )
    
    # Run single analysis
    await agent._observe_and_analyze()
    
    if agent.latest_insight:
        insight = agent.latest_insight
        lines = []
        lines.append("=" * 60)
        lines.append("CLAUDE HAIKU OBSERVER — ENHANCED METRICS TEST")
        lines.append("=" * 60)
        lines.append(f"Provider: {insight.get('provider')}")
        lines.append(f"Durum: {insight.get('durum')}")
        lines.append(f"Skor: {insight.get('skor')}")
        lines.append(f"Ozet: {insight.get('ozet', '')}")
        lines.append("")
        
        gozlemler = insight.get('gozlemler', [])
        lines.append(f"GOZLEMLER ({len(gozlemler)}):")
        for g in gozlemler:
            lines.append(f"  📊 {g}")
        lines.append("")
        
        anomaliler = insight.get('anomaliler', [])
        lines.append(f"ANOMALILER ({len(anomaliler)}):")
        for a in anomaliler:
            lines.append(f"  ⚠️ {a}")
        lines.append("")
        
        oneriler = insight.get('oneriler', [])
        lines.append(f"ONERILER ({len(oneriler)}):")
        for o in oneriler:
            lines.append(f"  💡 {o}")
        lines.append("")
        
        kritik = insight.get('kritik_uyari')
        if kritik:
            lines.append(f"🚨 KRITIK UYARI: {kritik}")
        
        lines.append(f"Duration: {insight.get('analysis_duration_ms')}ms")
        lines.append("=" * 60)
        
        result_text = '\n'.join(lines)
        with open(OUT_FILE, 'w', encoding='utf-8') as f:
            f.write(result_text)
        print(f"Saved to {OUT_FILE}")
        print(result_text)
    else:
        print("No insight produced")

asyncio.run(test())
