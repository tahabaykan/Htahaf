import React from 'react'
import LiveProposalsPanel from './LiveProposalsPanel'

/**
 * ReducemoreProposals - Defensive Reduction Proposals
 * 
 * Shows REDUCEMORE multiplier-based proposals (defensive/high-risk scenarios)
 */
function ReducemoreProposals({ wsConnected }) {
    return (
        <div className="reducemore-proposals">
            <div className="proposal-category-header">
                <h3>🔴 REDUCEMORE - Defensive Reductions</h3>
                <p className="category-description">
                    Aggressive defensive reductions in DEFANSIF/GECIS modes or high exposure scenarios
                </p>
            </div>
            <LiveProposalsPanel
                wsConnected={wsConnected}
                filterCategory="REDUCEMORE"
            />
        </div>
    )
}

export default ReducemoreProposals
