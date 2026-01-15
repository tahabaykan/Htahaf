"""
Proposal Explainer - "Why This Trade?" Panel

Generates human-readable explanations for proposals.
Explains which metrics passed thresholds, which are borderline, etc.

Key Principles:
- Human-readable text
- Metric-based explanations
- Threshold analysis
- Decision logic'e dokunmaz
"""

from typing import Dict, Any, Optional, List

from app.core.logger import logger
from app.psfalgo.proposal_models import OrderProposal
from app.psfalgo.market_snapshot_store import get_market_snapshot_store


class ProposalExplainer:
    """
    Proposal Explainer - generates "Why This Trade?" explanations.
    
    Responsibilities:
    - Generate human-readable explanations
    - Analyze which metrics passed thresholds
    - Identify borderline metrics
    - Explain befday/today effects
    - Explain SMA direction
    
    Does NOT:
    - Make trading decisions
    - Execute orders
    - Modify decision engines
    """
    
    def __init__(self):
        """Initialize Proposal Explainer"""
        logger.info("ProposalExplainer initialized")
    
    def explain_proposal(self, proposal: OrderProposal) -> Dict[str, Any]:
        """
        Generate "Why This Trade?" explanation for proposal.
        
        Args:
            proposal: OrderProposal to explain
            
        Returns:
            Explanation dict with human-readable text and analysis
        """
        # Get market snapshot for additional context
        snapshot_store = get_market_snapshot_store()
        snapshot = None
        if snapshot_store:
            snapshot = snapshot_store.get_current_snapshot(proposal.symbol)
        
        # Extract metrics
        metrics_used = proposal.metrics_used or {}
        fbtot = metrics_used.get('fbtot') or (snapshot.fbtot if snapshot else None)
        gort = metrics_used.get('gort') or (snapshot.gort if snapshot else None)
        sma63_chg = metrics_used.get('sma63_chg') or (snapshot.sma63_chg if snapshot else None)
        sma246_chg = metrics_used.get('sma246_chg') or (snapshot.sma246_chg if snapshot else None)
        ask_sell_pahalilik = metrics_used.get('ask_sell_pahalilik')
        bid_buy_ucuzluk = metrics_used.get('bid_buy_ucuzluk')
        
        # Build explanation
        explanation_parts = []
        threshold_analysis = []
        borderline_metrics = []
        
        # Engine-specific explanations
        if proposal.engine == 'KARBOTU':
            explanation_parts.append("Bu trade önerildi çünkü:")
            
            # FBTOT analysis
            if fbtot is not None:
                if fbtot < 1.10:
                    explanation_parts.append(f"- FBTOT = {fbtot:.2f} (< 1.10) ✅")
                    threshold_analysis.append({
                        'metric': 'FBTOT',
                        'value': fbtot,
                        'threshold': 1.10,
                        'passed': True,
                        'reason': 'FBTOT < 1.10 indicates stock is relatively cheap'
                    })
                else:
                    borderline_metrics.append({
                        'metric': 'FBTOT',
                        'value': fbtot,
                        'threshold': 1.10,
                        'status': 'BORDERLINE'
                    })
            
            # GORT analysis
            if gort is not None:
                if gort > -1.0:
                    explanation_parts.append(f"- GORT = {gort:.2f} (> -1.0) ✅")
                    threshold_analysis.append({
                        'metric': 'GORT',
                        'value': gort,
                        'threshold': -1.0,
                        'passed': True,
                        'reason': 'GORT > -1 indicates positive group-relative value'
                    })
                else:
                    borderline_metrics.append({
                        'metric': 'GORT',
                        'value': gort,
                        'threshold': -1.0,
                        'status': 'BORDERLINE'
                    })
            
            # Ask Sell Pahalılık analysis
            if ask_sell_pahalilik is not None:
                if ask_sell_pahalilik > -0.10:
                    explanation_parts.append(f"- Ask Sell Pahalılık = {ask_sell_pahalilik:.2f} (> -0.10) ✅")
                    threshold_analysis.append({
                        'metric': 'Ask Sell Pahalılık',
                        'value': ask_sell_pahalilik,
                        'threshold': -0.10,
                        'passed': True,
                        'reason': 'Ask Sell Pahalılık > -0.10 indicates good selling opportunity'
                    })
                else:
                    borderline_metrics.append({
                        'metric': 'Ask Sell Pahalılık',
                        'value': ask_sell_pahalilik,
                        'threshold': -0.10,
                        'status': 'BORDERLINE'
                    })
        
        elif proposal.engine == 'ADDNEWPOS':
            explanation_parts.append("Bu trade önerildi çünkü:")
            
            # Bid Buy Ucuzluk analysis
            if bid_buy_ucuzluk is not None:
                if bid_buy_ucuzluk > 0.06:
                    explanation_parts.append(f"- Bid Buy Ucuzluk = {bid_buy_ucuzluk:.2f} (> 0.06) ✅")
                    threshold_analysis.append({
                        'metric': 'Bid Buy Ucuzluk',
                        'value': bid_buy_ucuzluk,
                        'threshold': 0.06,
                        'passed': True,
                        'reason': 'Bid Buy Ucuzluk > 0.06 indicates good buying opportunity'
                    })
            
            # FBTOT analysis (for buying)
            if fbtot is not None:
                if fbtot > 1.10:
                    explanation_parts.append(f"- FBTOT = {fbtot:.2f} (> 1.10) ✅")
                    threshold_analysis.append({
                        'metric': 'FBTOT',
                        'value': fbtot,
                        'threshold': 1.10,
                        'passed': True,
                        'reason': 'FBTOT > 1.10 indicates stock is relatively expensive (good for buying)'
                    })
        
        # SMA analysis
        if sma63_chg is not None:
            if sma63_chg > 0:
                explanation_parts.append(f"- SMA63 = +{sma63_chg:.2f} (pozitif trend) ✅")
            elif sma63_chg < 0:
                explanation_parts.append(f"- SMA63 = {sma63_chg:.2f} (negatif trend) ⚠️")
            else:
                explanation_parts.append(f"- SMA63 = {sma63_chg:.2f} (nötr)")
        
        if sma246_chg is not None:
            if sma246_chg > 0:
                explanation_parts.append(f"- SMA246 = +{sma246_chg:.2f} (uzun vadeli pozitif) ✅")
            elif sma246_chg < 0:
                explanation_parts.append(f"- SMA246 = {sma246_chg:.2f} (uzun vadeli negatif) ⚠️")
        
        # Spread analysis
        if proposal.spread_percent is not None:
            if proposal.spread_percent < 0.20:
                explanation_parts.append(f"- Spread = {proposal.spread_percent:.2f}% (kabul edilebilir) ✅")
            else:
                explanation_parts.append(f"- Spread = {proposal.spread_percent:.2f}% (yüksek) ⚠️")
        
        # Befday / Today analysis
        if snapshot:
            if snapshot.befday_qty != 0:
                explanation_parts.append(
                    f"- Önceki gün pozisyon: {snapshot.befday_qty:.0f} lot "
                    f"(bugün değişim: {snapshot.today_qty_chg:+.0f} lot)"
                )
        
        # Confidence analysis
        if proposal.confidence > 0.7:
            explanation_parts.append(f"- Güven skoru: {proposal.confidence:.0%} (yüksek) ✅")
        elif proposal.confidence > 0.5:
            explanation_parts.append(f"- Güven skoru: {proposal.confidence:.0%} (orta)")
        else:
            explanation_parts.append(f"- Güven skoru: {proposal.confidence:.0%} (düşük) ⚠️")
        
        # Warnings
        if hasattr(proposal, 'warnings') and proposal.warnings:
            explanation_parts.append(f"\n⚠️ Uyarılar: {', '.join(proposal.warnings)}")
        
        # Combine explanation
        explanation_text = "\n".join(explanation_parts)
        
        return {
            'explanation_text': explanation_text,
            'threshold_analysis': threshold_analysis,
            'borderline_metrics': borderline_metrics,
            'confidence': proposal.confidence,
            'warnings': proposal.warnings if hasattr(proposal, 'warnings') else []
        }


# Global instance
_proposal_explainer: Optional[ProposalExplainer] = None


def get_proposal_explainer() -> Optional[ProposalExplainer]:
    """Get global ProposalExplainer instance"""
    return _proposal_explainer


def initialize_proposal_explainer():
    """Initialize global ProposalExplainer instance"""
    global _proposal_explainer
    _proposal_explainer = ProposalExplainer()
    logger.info("ProposalExplainer initialized")






