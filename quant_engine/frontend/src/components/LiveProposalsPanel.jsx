import React, { useState, useEffect, useCallback } from 'react'
import './LiveProposalsPanel.css'

/**
 * Live Proposals Panel - Shows real-time order proposals from RUNALL
 * 
 * SIMPLIFIED: No inner tabs - filterCategory is passed from parent (LTTrimProposals, etc.)
 * Each parent component shows only its own engine's proposals
 */
function LiveProposalsPanel({ wsConnected = false, filterCategory = 'ALL' }) {
    const [proposals, setProposals] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [filter, setFilter] = useState('all') // all, PROPOSED, ACCEPTED, REJECTED
    const [lastUpdate, setLastUpdate] = useState(null)

    // NEW: Bulk Selection State
    const [selectedIds, setSelectedIds] = useState(new Set())

    // Toggle selection
    const toggleSelection = (id) => {
        setSelectedIds(prev => {
            const newSet = new Set(prev)
            if (newSet.has(id)) newSet.delete(id)
            else newSet.add(id)
            return newSet
        })
    }

    // Map filterCategory -> backend engine param. Engine-specific tabs fetch by engine
    // so they see proposals from all cycles (e.g. LT_TRIM from cycle 6 when current is 7).
    const engineParam = { LT_TRIM: 'LT_TRIM', KARBOTU: 'KARBOTU', REDUCEMORE: 'REDUCEMORE', ADDNEWPOS: 'ADDNEWPOS', JFIN: 'ADDNEWPOS', MM: 'GREATEST_MM', GEM_MM: 'GREATEST_MM' }[filterCategory]

    // Fetch proposals logic
    const fetchProposals = useCallback(async () => {
        try {
            const url = engineParam
                ? `/api/psfalgo/proposals?engine=${encodeURIComponent(engineParam)}&limit=150`
                : '/api/psfalgo/proposals/latest?limit=150'
            const response = await fetch(url)
            const result = await response.json()

            if (result.success && result.proposals) {
                if (engineParam) {
                    // Engine-specific: replace with full list (no cycle cut); avoids "current cycle only" hiding past-cycle proposals
                    const sorted = [...(result.proposals || [])].sort((a, b) => {
                        const tsA = new Date(a.proposal_ts || a.decision_ts || 0).getTime()
                        const tsB = new Date(b.proposal_ts || b.decision_ts || 0).getTime()
                        return tsB - tsA
                    })
                    setProposals(sorted.slice(0, 150))
                } else {
                    setProposals(prevProposals => {
                        const getDedupKey = (p) => {
                            const priceStr = p.price ? p.price.toFixed(2) : '0.00';
                            const engine = p.engine || 'UNKNOWN';
                            return `${p.symbol}_${p.side}_${p.qty}_${priceStr}_${engine}`;
                        };
                        const proposalMap = new Map();
                        (result.proposals || []).forEach(proposal => proposalMap.set(getDedupKey(proposal), proposal));
                        prevProposals.forEach(p => {
                            const key = getDedupKey(p);
                            if (!proposalMap.has(key)) proposalMap.set(key, p);
                        });
                        const merged = Array.from(proposalMap.values()).sort((a, b) => {
                            const tsA = new Date(a.proposal_ts || a.decision_ts || 0).getTime();
                            const tsB = new Date(b.proposal_ts || b.decision_ts || 0).getTime();
                            return tsB - tsA;
                        });
                        return merged.slice(0, 150);
                    })
                }
                setError(null)
                setLastUpdate(new Date())
            }
        } catch (err) {
            console.error('Error fetching proposals:', err)
        } finally {
            setLoading(false)
        }
    }, [engineParam])

    // Initial fetch & Poll
    useEffect(() => {
        fetchProposals()
        const interval = setInterval(fetchProposals, 65000)  // 65 sn: emir dongusu ile uyumlu
        return () => clearInterval(interval)
    }, [fetchProposals])

    // BroadcastChannel
    useEffect(() => {
        const handleMessage = (event) => {
            if (event.data?.type === 'proposals_update' && event.data.data) {
                setProposals(event.data.data)
                setLastUpdate(new Date())
            }
        }
        let bc;
        try {
            bc = new BroadcastChannel('market-data')
            bc.onmessage = handleMessage
        } catch (e) { }
        return () => bc && bc.close()
    }, [])

    // Action Handlers
    const handleAccept = async (id) => {
        await fetch(`/api/psfalgo/proposals/${id}/accept`, { method: 'POST' })
        fetchProposals()
    }
    const handleReject = async (id) => {
        await fetch(`/api/psfalgo/proposals/${id}/reject`, { method: 'POST' })
        fetchProposals()
    }

    // Bulk Handlers
    const handleSelectAll = (items) => {
        const ids = items.map(p => p.id)
        setSelectedIds(new Set(ids))
    }
    const handleDeselectAll = () => setSelectedIds(new Set())

    const handleBulkAccept = async () => {
        if (selectedIds.size === 0) return
        await Promise.all(Array.from(selectedIds).map(id => fetch(`/api/psfalgo/proposals/${id}/accept`, { method: 'POST' })))
        setSelectedIds(new Set())
        fetchProposals()
    }
    const handleBulkReject = async () => {
        if (selectedIds.size === 0) return
        await Promise.all(Array.from(selectedIds).map(id => fetch(`/api/psfalgo/proposals/${id}/reject`, { method: 'POST' })))
        setSelectedIds(new Set())
        fetchProposals()
    }

    // --- CLASSIFICATION ---
    const getProposalCategory = (p) => {
        const side = (p.side || '').toUpperCase()
        const engine = (p.engine || '').toUpperCase()
        const reason = (p.reason || '').toUpperCase()

        // JFIN (ADDNEWPOS)
        if (engine === 'ADDNEWPOS_ENGINE') {
            if (side.includes('BUY') || side.includes('LONG')) return 'LONG_JFIN';
            if (side.includes('SELL') || side.includes('SHORT')) return 'SHORT_JFIN';
        }

        // MM
        if (engine.includes('MM') || reason.includes('MM')) {
            if (side.includes('BUY') || side.includes('LONG')) return 'LONG_MM';
            return 'SHORT_MM';
        }

        // LT TRIM (Default)
        if (side.includes('SELL') || side.includes('SHORT')) return 'LONG_TRIM';
        if (side.includes('BUY') || side.includes('COVER')) return 'SHORT_TRIM';

        return 'UNKNOWN';
    }

    // --- SMART SEARCH ---
    const [searchQuery, setSearchQuery] = useState('')

    const matchesSearch = (p, query) => {
        if (!query) return true;
        const upperQuery = query.toUpperCase();
        const symbol = (p.symbol || '').toUpperCase();
        const reason = (p.reason || '').toUpperCase();
        return symbol.includes(upperQuery) || reason.includes(upperQuery);
    }

    // --- FILTER BY CATEGORY (from parent prop) ---
    const filteredProposals = proposals.filter(p => {
        // 1. Status Filter
        if (filter !== 'all' && p.status !== filter) return false

        // 2. Search Filter
        if (!matchesSearch(p, searchQuery)) return false;

        // 3. CATEGORY FILTER (from parent)
        const engine = (p.engine || '').toUpperCase();
        const reason = (p.reason || '').toUpperCase();
        const cat = getProposalCategory(p);

        if (filterCategory === 'ALL') return true;

        if (filterCategory === 'LT_TRIM') {
            // Fallback: Show RUNALL proposals here too (Core Execution Tab)
            return engine.includes('LT_TRIM') || engine === 'RUNALL';
        }
        if (filterCategory === 'KARBOTU') {
            return engine.includes('KARBOTU');
        }
        if (filterCategory === 'REDUCEMORE') {
            return engine.includes('REDUCEMORE');
        }
        if (filterCategory === 'ADDNEWPOS' || filterCategory === 'JFIN') {
            return engine.includes('ADDNEWPOS') || cat.includes('JFIN');
        }
        if (filterCategory === 'MM' || filterCategory === 'GEM_MM') {
            return engine.includes('MM') || reason.includes('MM');
        }
        return true;
    })

    // Split into Columns: Sell on Left, Buy on Right
    const sellSideProposals = [];
    const buySideProposals = [];

    filteredProposals.forEach(p => {
        const side = (p.side || '').toUpperCase();

        // Strict Buy/Sell Separation
        // SELL = SELL, SHORT
        // BUY = BUY, COVER, LONG, ADD
        const isBuy = side.includes('BUY') || side.includes('COVER') || side.includes('LONG') || side.includes('ADD');

        if (isBuy) {
            buySideProposals.push(p);
        } else {
            sellSideProposals.push(p);
        }
    });

    const getStatusClass = (status) => {
        switch (status) {
            case 'PROPOSED': return 'status-proposed'
            case 'ACCEPTED': return 'status-accepted'
            case 'REJECTED': return 'status-rejected'
            case 'EXPIRED': return 'status-expired'
            default: return ''
        }
    }

    if (loading && proposals.length === 0) {
        return <div className="live-proposals-panel"><div className="panel-loading">Loading proposals...</div></div>
    }

    // Açıklayıcı boş durum: LT TRIM / KARBOTU sekmelerinde öneri yoksa neden boş olduğunu göster
    const engineEmptyLabels = {
        LT_TRIM: 'Bu sekmede LT TRIM motorunun önerdiği emirler listelenir. Bu döngüde LT TRIM önerisi üretilmediyse liste boş olur (örn. tüm pozisyonlar toz seviyesinde ise).',
        KARBOTU: 'Bu sekmede KARBOTU motorunun önerdiği kâr alma emirleri listelenir. Bu döngüde KARBOTU önerisi üretilmediyse liste boş olur.',
    }
    const isEmptyEngineTab = (filterCategory === 'LT_TRIM' || filterCategory === 'KARBOTU') && filteredProposals.length === 0 && !loading

    return (
        <div className="live-proposals-panel">
            {/* DEBUGGER */}
            <div style={{ background: '#333', color: '#0f0', padding: '5px', fontSize: '12px' }}>
                DEBUG: Loaded: {proposals.length} | Loading: {loading.toString()} |
                Filter: {filterCategory} |
                Sells: {sellSideProposals.length} | Buys: {buySideProposals.length} |
                Sample Engine: {proposals[0]?.engine || 'None'} |
                Account: {proposals[0]?.account_id || 'N/A'}
            </div>
            {isEmptyEngineTab && (
                <div className="panel-empty-engine" style={{
                    margin: '12px 8px',
                    padding: '14px 16px',
                    background: 'rgba(80,80,120,0.25)',
                    border: '1px solid #555',
                    borderRadius: '8px',
                    color: '#c0c0ff',
                    fontSize: '0.9em',
                    lineHeight: 1.4
                }}>
                    <strong>Bu sekmede henüz öneri yok.</strong><br />
                    {engineEmptyLabels[filterCategory]}
                </div>
            )}
            {/* Header - No inner tabs anymore */}
            <div className="panel-header" style={{ flexDirection: 'row', alignItems: 'center', gap: '8px', paddingBottom: '4px', marginBottom: '4px', flexWrap: 'nowrap' }}>

                {/* Bulk Actions */}
                <div className="bulk-actions-toolbar" style={{ gap: '2px' }}>
                    <button onClick={() => handleSelectAll(filteredProposals)} className="bulk-btn" style={{ padding: '2px 6px', fontSize: '9px' }}>All</button>
                    <button onClick={handleDeselectAll} className="bulk-btn" style={{ padding: '2px 6px', fontSize: '9px' }}>None</button>
                    <div className="bulk-separator" style={{ width: '1px', height: '14px', backgroundColor: '#555', margin: '0 2px' }}></div>
                    <button onClick={handleBulkAccept} disabled={selectedIds.size === 0} className="bulk-btn accept-selected" style={{ padding: '2px 6px', fontSize: '9px' }}>✅{selectedIds.size}</button>
                    <button onClick={handleBulkReject} disabled={selectedIds.size === 0} className="bulk-btn reject-selected" style={{ padding: '2px 6px', fontSize: '9px' }}>🗑️{selectedIds.size}</button>
                </div>

                {/* SEARCH INPUT */}
                <div className="search-filter-container" style={{ flex: 1, display: 'flex', gap: '4px', alignItems: 'center', maxWidth: '200px' }}>
                    <span style={{ fontSize: '1em' }}>🔍</span>
                    <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Search..."
                        className="smart-search-input"
                        style={{
                            width: '100%',
                            padding: '2px 6px',
                            borderRadius: '3px',
                            border: '1px solid #444',
                            backgroundColor: '#222',
                            color: '#fff',
                            fontFamily: 'monospace',
                            fontSize: '0.9em',
                            height: '22px'
                        }}
                    />
                    {searchQuery && (
                        <button
                            onClick={() => setSearchQuery('')}
                            style={{ background: 'none', border: 'none', color: '#ccc', cursor: 'pointer', fontSize: '1em' }}
                        >✖</button>
                    )}
                </div>

                {/* Refresh & Filter */}
                <div style={{ display: 'flex', gap: '4px', marginLeft: 'auto' }}>
                    <select value={filter} onChange={(e) => setFilter(e.target.value)} className="filter-select" style={{ padding: '2px', fontSize: '9px', color: '#eee' }}>
                        <option value="all">All</option>
                        <option value="PROPOSED">Prop</option>
                        <option value="ACCEPTED">Acc</option>
                        <option value="REJECTED">Rej</option>
                    </select>
                    <button onClick={fetchProposals} className="refresh-btn" style={{ padding: '2px 6px' }}>🔄</button>
                </div>

            </div>

            {error && <div className="panel-error">{error}</div>}

            <div className="proposals-split-container" style={{ height: '650px' }}>
                {/* LEFT COLUMN: SELL ORDERS */}
                <div className="proposals-column">
                    <div className="column-header longs">SELL ORDERS ({sellSideProposals.length})</div>
                    {sellSideProposals.length === 0 ? (
                        <div className="no-proposals" style={{ padding: '20px', fontSize: '0.8em' }}>No Sell Proposals</div>
                    ) : (
                        sellSideProposals.map(p => (
                            <ProposalCard
                                key={p.id} proposal={p}
                                isSelected={selectedIds.has(p.id)}
                                toggleSelection={toggleSelection}
                                getStatusClass={getStatusClass}
                                handleAccept={handleAccept}
                                handleReject={handleReject}
                            />
                        ))
                    )}
                </div>

                {/* RIGHT COLUMN: BUY ORDERS */}
                <div className="proposals-column">
                    <div className="column-header shorts">BUY ORDERS ({buySideProposals.length})</div>
                    {buySideProposals.length === 0 ? (
                        <div className="no-proposals" style={{ padding: '20px', fontSize: '0.8em' }}>No Buy Proposals</div>
                    ) : (
                        buySideProposals.map(p => (
                            <ProposalCard
                                key={p.id} proposal={p}
                                isSelected={selectedIds.has(p.id)}
                                toggleSelection={toggleSelection}
                                getStatusClass={getStatusClass}
                                handleAccept={handleAccept}
                                handleReject={handleReject}
                            />
                        ))
                    )}
                </div>
            </div>
        </div>
    )
}

export default LiveProposalsPanel


// Helper function to render proposal card
const ProposalCard = ({ proposal, isSelected, toggleSelection, getStatusClass, handleAccept, handleReject }) => {
    const sideUpper = (proposal.side || '').toUpperCase()
    const isSell = sideUpper.includes('SELL') || sideUpper.includes('SHORT')
    const isBuy = sideUpper.includes('BUY') || sideUpper.includes('COVER')
    const currentQty = proposal.current_qty || 0

    // Dynamic Score Logic
    let dynamicScoreLabel = '';
    let dynamicScoreValue = null;
    let dynamicScoreClass = '';

    if (isSell) {
        dynamicScoreLabel = 'Ask ph:'; // User requested "Ask ph :"
        dynamicScoreValue = proposal.pahalilik_score;
        dynamicScoreClass = 'pahalilik';
    } else {
        dynamicScoreLabel = 'Bid uc:'; // User requested "Bid uc :"
        dynamicScoreValue = proposal.ucuzluk_score;
        dynamicScoreClass = 'ucuzluk';
    }

    // Purpose Tag Logic
    const getPurposeTag = () => {
        const engine = (proposal.engine || '').toUpperCase();
        const reason = (proposal.reason || '').toUpperCase();

        let enginePrefix = 'LT';
        if (engine === 'MM' || reason.includes('MM')) enginePrefix = 'MM';
        else if (engine === 'ADDNEWPOS_ENGINE') enginePrefix = 'JFIN';

        // Determine Direction (INC vs DEC)
        if (isBuy) {
            if (currentQty < 0) return `${enginePrefix}_SHORT_DEC`;
            return `${enginePrefix}_LONG_INC`;
        } else {
            if (currentQty > 0) return `${enginePrefix}_LONG_DEC`;
            return `${enginePrefix}_SHORT_INC`;
        }
    }

    const purposeTag = getPurposeTag();

    // Trim Percentage Logic
    let trimInfo = null;
    const isDecrease = purposeTag.includes('_DEC');
    if (isDecrease && currentQty !== 0 && proposal.qty > 0) {
        const pct = Math.round((proposal.qty / Math.abs(currentQty)) * 100);
        trimInfo = `%${pct}`;
    }

    // Daily Change Color Logic
    const dChg = proposal.daily_chg || 0;
    const dChgColor = dChg >= 0 ? '#2ecc71' : '#e74c3c'; // Green / Red

    return (
        <div
            className={`proposal-card ${getStatusClass(proposal.status)} ${isSelected ? 'selected-proposal' : ''}`}
            onClick={() => toggleSelection(proposal.id)}
            style={{
                borderLeft: isSelected ? '4px solid #00d2ff' : undefined,
                backgroundColor: isSelected ? 'rgba(0, 210, 255, 0.05)' : undefined,
                cursor: 'pointer',
                padding: '2px 4px',
                marginBottom: '2px',
                gap: '0px'
            }}
        >
            {/* LINE 1: CIM PRB | chg: +0.09 | 700 SELL @ 23.46 | Last: 23.34 | Bid:23.23 Ask:23.50 | Spr:0.27 */}
            <div className="proposal-line-row primary" style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.98em', height: '22px', color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden' }}>

                {/* CHECKBOX */}
                {proposal.status === 'PROPOSED' && (
                    <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => { }}
                        onClick={(e) => { e.stopPropagation(); toggleSelection(proposal.id); }}
                        style={{ cursor: 'pointer', transform: 'scale(1.1)', marginRight: '2px' }}
                    />
                )}

                {/* SYMBOL */}
                <span className="symbol" style={{ fontSize: '1.1em', fontWeight: '800', color: '#fff' }}>{proposal.symbol}</span>

                {/* DAILY CHANGE (Moved to top) */}
                <span style={{ fontSize: '0.9em', color: '#fff' }}>chg:</span>
                <span style={{ fontSize: '0.95em', fontWeight: '700', color: dChgColor }}>
                    {dChg > 0 ? '+' : ''}{(dChg || 0).toFixed(2)}
                </span>

                <span style={{ color: '#7f8c8d' }}>|</span>

                {/* QTY SIDE @ PRICE */}
                <div style={{ display: 'flex', gap: '4px', alignItems: 'baseline' }}>
                    <span style={{ fontWeight: '700', color: '#fff' }}>{proposal.qty?.toLocaleString()}</span>
                    {/* SIDE: GREEN/RED */}
                    <span className={isBuy ? 'side-buy' : 'side-sell'} style={{ fontWeight: '900', fontSize: '0.95em' }}>{proposal.side}</span>
                    <span style={{ color: '#fff', fontSize: '0.9em' }}>@</span>
                    {/* PRICE: WHITE */}
                    <span style={{ fontWeight: '800', color: '#fff' }}>{proposal.price != null ? Number(proposal.price).toFixed(2) : '0.00'}</span>
                </div>

                <span style={{ color: '#7f8c8d' }}>|</span>

                {/* LAST */}
                <span style={{ color: '#fff', fontSize: '0.9em' }}>Last:</span>
                <span style={{ color: '#fff', fontWeight: '600' }}>{proposal.last != null ? proposal.last.toFixed(2) : 'N/A'}</span>

                <span style={{ color: '#7f8c8d' }}>|</span>

                {/* BID / ASK */}
                <span style={{ color: '#fff', fontSize: '0.9em' }}>
                    Bid:{proposal.bid != null ? proposal.bid.toFixed(2) : 'N/A'} Ask:{proposal.ask != null ? proposal.ask.toFixed(2) : 'N/A'}
                </span>

                <span style={{ color: '#7f8c8d' }}>|</span>

                {/* SPREAD */}
                <span style={{ color: '#fff', fontSize: '0.9em' }}>Spr:{proposal.spread != null ? proposal.spread.toFixed(2) : 'N/A'}</span>


                {/* ACTION BUTTONS (Right-aligned) */}
                {proposal.status === 'PROPOSED' ? (
                    <div style={{ display: 'flex', gap: '2px', marginLeft: 'auto' }}>
                        <button
                            className="mini-btn accept"
                            onClick={(e) => { e.stopPropagation(); handleAccept(proposal.id); }}
                            style={{ padding: '1px 5px', fontSize: '9px', fontWeight: '700', minWidth: '40px', height: '18px' }}
                        >
                            ✓ ACC
                        </button>
                        <button
                            className="mini-btn reject"
                            onClick={(e) => { e.stopPropagation(); handleReject(proposal.id); }}
                            style={{ padding: '1px 5px', fontSize: '9px', fontWeight: '700', minWidth: '40px', height: '18px' }}
                        >
                            ✗ REJ
                        </button>
                    </div>
                ) : (
                    <span className={`proposal-status ${getStatusClass(proposal.status)}`} style={{ fontSize: '9px', marginLeft: 'auto' }}>
                        {proposal.status}
                    </span>
                )}

                {/* POS & TRIM (Pos: ...)%Trim */}
                {(proposal.current_qty !== undefined && proposal.current_qty !== null) && (
                    <div style={{ marginLeft: '6px', color: '#00d2ff', fontSize: '0.9em', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <span>(Pos: {proposal.current_qty}→{proposal.potential_qty !== undefined ? proposal.potential_qty : '?'})</span>
                        {/* Trim % (White text, right of Pos) */}
                        {trimInfo && <span style={{ color: '#fff', fontWeight: '800', backgroundColor: 'rgba(255, 255, 255, 0.1)', padding: '0 3px', borderRadius: '2px' }}>{trimInfo}</span>}
                    </div>
                )}
            </div>

            {/* LINE 2: [TAG] Reason | Prev:.. | B:.. | Ask ph: +Val */}
            <div className="proposal-line-row" style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.9em', marginTop: '1px', color: '#fff' }}>

                {/* PURPOSE TAG */}
                <span style={{ fontSize: '9px', backgroundColor: '#333', color: '#ccc', padding: '0px 3px', borderRadius: '2px', border: '1px solid #555', fontFamily: 'monospace' }}>
                    {purposeTag}
                </span>

                {/* REASON TAG (Moved Left) */}
                <span style={{
                    fontSize: '0.9em',
                    fontWeight: '600',
                    color: '#fff',
                    backgroundColor: 'rgba(255, 255, 255, 0.1)',
                    padding: '0 4px',
                    borderRadius: '3px',
                    maxWidth: '300px', // Increased width
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    flex: 1 // Take available space
                }} title={proposal.reason ? proposal.reason.replace('R:', '').trim() : ''}>
                    {proposal.reason ? proposal.reason.replace('R:', '').trim() : ''}
                </span>

                <span style={{ color: '#7f8c8d' }}>|</span>

                {/* Prev Close */}
                <span style={{ color: '#fff' }}>Prev:{proposal.prev_close != null ? proposal.prev_close.toFixed(2) : 'N/A'}</span>

                <span style={{ color: '#7f8c8d' }}>|</span>

                {/* Bench Change */}
                <span style={{ color: '#fff' }}>B:</span>
                <span className={(proposal.bench_chg || 0) >= 0 ? 'val-pos' : 'val-neg'}>
                    {proposal.bench_chg ? `${proposal.bench_chg >= 0 ? '+' : ''}${proposal.bench_chg.toFixed(2)}` : 'N/A'}
                </span>

                {/* PH / UC SCORE */}
                {dynamicScoreValue !== null && (
                    <>
                        <span style={{ color: '#7f8c8d' }}>|</span>
                        <span style={{ fontSize: '0.9em', color: '#fff' }}>{dynamicScoreLabel}</span>
                        <span className={`score-tag ${dynamicScoreClass}`} style={{ padding: '0 4px', fontSize: '0.95em', color: '#fff' }}>
                            {dynamicScoreValue > 0 ? '+' : ''}{dynamicScoreValue != null ? dynamicScoreValue.toFixed(3) : 'N/A'}
                        </span>
                    </>
                )}

                {/* EXTRA METRICS: Fbtot / SMA (From Metrics Used) */}
                {(() => {
                    const mused = proposal.metrics_used || {};
                    // Check for Fbtot/Sfstot
                    const fbtot = mused.fbtot !== undefined ? mused.fbtot : null;
                    const sfstot = mused.sfstot !== undefined ? mused.sfstot : null;
                    const sma63 = mused.sma63_chg !== undefined ? mused.sma63_chg : null;

                    const showFbtot = isBuy ? fbtot : sfstot; // Actually logic: Long = Fbtot? Wait.
                    // Karbotu: Long -> Sell Intent -> checks Fbtot/AskSell. 
                    // Proposal is SELL. So it is Short/Sell proposal.
                    // But usually "Fbtot" is associated with LONG positions getting expensive.
                    // Let's just show whatever is available.

                    const val = fbtot !== null ? fbtot : (sfstot !== null ? sfstot : null);
                    const label = fbtot !== null ? 'Fbtot:' : (sfstot !== null ? 'Sfstot:' : null);

                    return (
                        <>
                            {val !== null && (
                                <span style={{ marginLeft: '6px', fontSize: '0.9em', color: '#aaa', fontFamily: 'monospace' }}>
                                    {label}<span style={{ color: '#fff' }}>{val.toFixed(2)}</span>
                                </span>
                            )}
                            {sma63 !== null && (
                                <span style={{ marginLeft: '4px', fontSize: '0.9em', color: '#aaa', fontFamily: 'monospace' }}>
                                    SMA:<span style={{ color: sma63 >= 0 ? '#2ecc71' : '#e74c3c' }}>{sma63.toFixed(2)}</span>
                                </span>
                            )}
                        </>
                    )
                })()}

            </div>
        </div>
    )
}
