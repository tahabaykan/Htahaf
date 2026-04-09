import React from 'react'
import LiveProposalsPanel from './LiveProposalsPanel'

/**
 * LTTrimProposals - LT Trim Execution Proposals
 * 
 * Reuses LiveProposalsPanel logic but filters to show only LT TRIM proposals
 */
function LTTrimProposals({ wsConnected }) {
    return (
        <div className="lt-trim-proposals">
            <div className="proposal-category-header">
                <h3>🔵 LT TRIM - Position Trim Execution</h3>
                <p className="category-description">
                    Systematic position trimming based on exposure limits and daily change quotas
                </p>
            </div>
            <LiveProposalsPanel
                wsConnected={wsConnected}
                filterCategory="LT_TRIM"
            />
        </div>
    )
}

export default LTTrimProposals
