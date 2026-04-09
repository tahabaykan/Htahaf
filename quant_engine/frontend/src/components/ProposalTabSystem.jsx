import React, { useState } from 'react'
import './ProposalTabSystem.css'
import LTTrimProposals from './LTTrimProposals'
import AddNewPosProposals from './AddNewPosProposals'
import KarbotuProposals from './KarbotuProposals'
import ReducemoreProposals from './ReducemoreProposals'
import NotFoundProposals from './NotFoundProposals'
import GemProposalsPanel from './GemProposalsPanel'

/**
 * ProposalTabSystem - 6-Tab Proposal Display
 * 
 * Tabs:
 * - LT TRIM: LT Trim execution proposals
 * - ADDNEWPOS: JFIN transformer intents (BB/FB/SAS/SFS pools)
 * - KARBOTU: Profit-taking proposals (signal-based)
 * - REDUCEMORE: Defensive reduction proposals (multiplier-based)
 * - GEM (MM): Market Making proposals (Greatest MM)
 * - NOT FOUND: Stocks with missing/zero critical metrics
 */
function ProposalTabSystem({ wsConnected = false }) {
    const [activeTab, setActiveTab] = useState('LT_TRIM')

    const tabs = [
        { id: 'LT_TRIM', label: '🔵 LT TRIM', description: 'Position Trim Execution' },
        { id: 'ADDNEWPOS', label: '🟢 ADDNEWPOS', description: 'New Position Additions (JFIN)' },
        { id: 'KARBOTU', label: '🟠 KARBOTU', description: 'Profit Taking' },
        { id: 'REDUCEMORE', label: '🔴 REDUCEMORE', description: 'Defensive Reductions' },
        { id: 'GEM_MM', label: '💎 MM', description: 'Market Making Proposals' },
        { id: 'NOT_FOUND', label: '⚠️ NOT FOUND', description: 'Stocks with Missing Data' }
    ]

    return (
        <div className="proposal-tab-system">
            {/* Tab Navigation */}
            <div className="proposal-tabs-header">
                <div className="proposal-tabs">
                    {tabs.map(tab => (
                        <button
                            key={tab.id}
                            className={`proposal-tab-btn ${activeTab === tab.id ? 'active' : ''}`}
                            onClick={() => setActiveTab(tab.id)}
                            title={tab.description}
                        >
                            {tab.label}
                        </button>
                    ))}
                </div>
                <div className="proposal-tabs-info">
                    <span className={`ws-status ${wsConnected ? 'connected' : 'disconnected'}`}>
                        {wsConnected ? '🟢 Live' : '🔴 Offline'}
                    </span>
                </div>
            </div>

            {/* Tab Content */}
            <div className="proposal-tab-content">
                {activeTab === 'LT_TRIM' && <LTTrimProposals wsConnected={wsConnected} />}
                {activeTab === 'ADDNEWPOS' && <AddNewPosProposals wsConnected={wsConnected} />}
                {activeTab === 'KARBOTU' && <KarbotuProposals wsConnected={wsConnected} />}
                {activeTab === 'REDUCEMORE' && <ReducemoreProposals wsConnected={wsConnected} />}
                {activeTab === 'GEM_MM' && <GemProposalsPanel />}
                {activeTab === 'NOT_FOUND' && <NotFoundProposals wsConnected={wsConnected} />}
            </div>
        </div>
    )
}

export default ProposalTabSystem

