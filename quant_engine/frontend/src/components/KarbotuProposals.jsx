import React from 'react'
import LiveProposalsPanel from './LiveProposalsPanel'

/**
 * KarbotuProposals - Profit-Taking Proposals
 * 
 * Shows KARBOTU signal-based proposals (FBtot > 1.3 for longs, SFStot > 1.3 for shorts)
 */
function KarbotuProposals({ wsConnected }) {
    return (
        <div className="karbotu-proposals">
            <div className="proposal-category-header">
                <h3>🟠 KARBOTU - Profit Taking</h3>
                <p className="category-description">
                    Profit-taking signals for expensive positions (FBtot/SFStot thresholds)
                </p>
            </div>
            <LiveProposalsPanel
                wsConnected={wsConnected}
                filterCategory="KARBOTU"
            />
        </div>
    )
}

export default KarbotuProposals
