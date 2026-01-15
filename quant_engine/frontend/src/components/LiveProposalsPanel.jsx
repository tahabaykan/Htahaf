import React, { useState, useEffect, useCallback, useRef } from 'react'
import './LiveProposalsPanel.css'

/**
 * Live Proposals Panel - Shows real-time order proposals from RUNALL
 * 
 * Displays proposals as they come in from the backend via REST API polling.
 * Each proposal shows: Symbol, Action, Qty, Price, Engine, Reason, Status
 * 
 * Uses aggressive polling (1 second) to ensure proposals are displayed in real-time.
 */
// Main Component
function LiveProposalsPanel({ wsConnected = false }) {
  const [proposals, setProposals] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('all') // all, PROPOSED, ACCEPTED, REJECTED
  const [autoScroll, setAutoScroll] = useState(true)
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

  // Fetch proposals logic (Keep existing logic)
  const fetchProposals = useCallback(async () => {
    // ... (Same fetching logic as before) ...
    try {
      const response = await fetch('/api/psfalgo/proposals/latest?limit=100') // Increased limit
      const result = await response.json()

      if (result.success && result.proposals) {
        setProposals(prevProposals => {
          // Dedup Logic
          const getDedupKey = (p) => {
            const priceStr = p.price ? p.price.toFixed(2) : '0.00';
            return `${p.symbol}_${p.side}_${p.qty}_${priceStr}`;
          };
          const proposalMap = new Map();
          prevProposals.forEach(p => proposalMap.set(getDedupKey(p), p));
          result.proposals.forEach(proposal => proposalMap.set(getDedupKey(proposal), proposal));

          const merged = Array.from(proposalMap.values())
          merged.sort((a, b) => {
            const tsA = new Date(a.proposal_ts || a.decision_ts || 0).getTime()
            const tsB = new Date(b.proposal_ts || b.decision_ts || 0).getTime()
            return tsB - tsA
          })
          return merged.slice(0, 150) // Keep last 150
        })
        setError(null)
        setLastUpdate(new Date())
      }
    } catch (err) {
      console.error('Error fetching proposals:', err)
      // setError('Failed to load proposals') // Suppress transient errors
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial fetch & Poll
  useEffect(() => {
    fetchProposals()
    const interval = setInterval(fetchProposals, 1000)
    return () => clearInterval(interval)
  }, [fetchProposals])

  // BroadcastChannel (Same as before)
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

  // Bulk Handlers (Same as before, abbreviated for space if valid)
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

  // --- CLASSIFICATION & FILTERING ---

  // Helper to determine Proposal "Side Category" (Long Strategy vs Short Strategy)
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
    if (engine === 'MM' || reason.includes('MM')) {
      // Assuming MM Long = Buy, MM Short = Sell
      if (side.includes('BUY') || side.includes('LONG')) return 'LONG_MM';
      return 'SHORT_MM';
    }

    // LT TRIM (Default)
    // Sells are for Long positions (Long Side)
    // Buys are for Short positions (Short Side)
    if (side.includes('SELL') || side.includes('SHORT')) return 'LONG_TRIM'; // Selling to trim Long
    if (side.includes('BUY') || side.includes('COVER')) return 'SHORT_TRIM'; // Buying to cover Short

    return 'UNKNOWN';
  }

  const getStageFromReason = (reason) => {
    const r = (reason || '').toUpperCase();
    if (r.includes('STAGE_1')) return 'STAGE_1';
    if (r.includes('STAGE_2')) return 'STAGE_2';
    if (r.includes('STAGE_3')) return 'STAGE_3';
    if (r.includes('STAGE_4')) return 'STAGE_4';
    if (r.includes('SMALL')) return 'SMALL';
    return 'OTHER';
  }

  // --- NEW: SMART SEARCH FILTERING ---
  const [searchQuery, setSearchQuery] = useState('')

  const parseSearchQuery = (query) => {
    if (!query) return null;
    const terms = query.toUpperCase().split(' ').filter(t => t.length > 0);
    return terms;
  }

  const matchesSearch = (p, terms) => {
    if (!terms || terms.length === 0) return true;

    const cat = getProposalCategory(p);
    const reason = (p.reason || '').toUpperCase();
    const engine = (p.engine || '').toUpperCase();
    const side = (p.side || '').toUpperCase();
    const symbol = (p.symbol || '').toUpperCase();

    // Check each term - ALL must match (AND logic)
    return terms.every(term => {
      // 1. SIDE FILTERS
      if (term === 'LONG') {
        return cat.startsWith('LONG_');
      }
      if (term === 'SHORT') {
        return cat.startsWith('SHORT_');
      }

      // 2. STAGE FILTERS
      if (term === 'STAGE') return true; // Just a keyword, wait for number
      if (['1', '2', '3', '4'].includes(term)) {
        return reason.includes(`STAGE_${term}`) || reason.includes(`STAGE${term}`) || reason.includes(`STAGE ${term}`);
      }
      if (term === 'SMALL') {
        return reason.includes('SMALL');
      }

      // 3. ENGINE FILTERS
      if (term === 'JFIN' || term === 'ADDNEWPOS') {
        return engine === 'ADDNEWPOS_ENGINE';
      }
      if (term === 'TRIM' || term === 'REDUCE') {
        return ['LT_TRIM', 'KARBOTU', 'REDUCEMORE'].includes(engine) || reason.includes('TRIM');
      }
      if (term === 'MM') {
        return engine === 'MM' || (p.book || '').toUpperCase() === 'MM';
      }

      // 4. SYMBOL SEARCH (General fallback)
      if (symbol.includes(term)) return true;

      // 5. Generic Includes check (allows searching for specific reason text)
      if (reason.includes(term)) return true;

      return false;
    });
  }

  // Filter Logic
  const filteredProposals = proposals.filter(p => {
    if (filter !== 'all' && p.status !== filter) return false

    const terms = parseSearchQuery(searchQuery);
    return matchesSearch(p, terms);
  })

  // Split into Columns
  const longSideProposals = [];
  const shortSideProposals = [];

  filteredProposals.forEach(p => {
    const cat = getProposalCategory(p);
    if (cat.startsWith('LONG_')) longSideProposals.push(p);
    else shortSideProposals.push(p);
  });

  // Status Badge Helper
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

  return (
    <div className="live-proposals-panel">
      <div className="panel-header" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '8px' }}>

        {/* ROW 1: Bulk Actions + Main Status Filter */}
        <div style={{ display: 'flex', width: '100%', justifyContent: 'space-between', alignItems: 'center' }}>
          <div className="bulk-actions-toolbar">
            <div style={{ display: 'flex', gap: '4px' }}>
              <button onClick={() => handleSelectAll(filteredProposals)} className="bulk-btn">Select All</button>
              <button onClick={handleDeselectAll} className="bulk-btn">Deselect</button>
            </div>
            <div className="bulk-separator" style={{ width: '1px', height: '16px', backgroundColor: '#555', margin: '0 4px' }}></div>
            <button onClick={handleBulkAccept} disabled={selectedIds.size === 0} className="bulk-btn accept-selected">✅ ({selectedIds.size})</button>
            <button onClick={handleBulkReject} disabled={selectedIds.size === 0} className="bulk-btn reject-selected">🗑️ ({selectedIds.size})</button>
          </div>

          <div style={{ display: 'flex', gap: '8px' }}>
            <select value={filter} onChange={(e) => setFilter(e.target.value)} className="filter-select">
              <option value="all">All Status</option>
              <option value="PROPOSED">Proposed</option>
              <option value="ACCEPTED">Accepted</option>
              <option value="REJECTED">Rejected</option>
            </select>
            <button onClick={fetchProposals} className="refresh-btn">🔄</button>
          </div>
        </div>

        {/* ROW 2: SEARCH INPUT (Replacing buttons) */}
        <div className="search-filter-container" style={{ width: '100%', display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span style={{ fontSize: '1.2em' }}>🔍</span>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search filter (e.g. 'long stage 3', 'short jfin', 'small', 'trim')"
            className="smart-search-input"
            style={{
              flex: 1,
              padding: '6px 10px',
              borderRadius: '4px',
              border: '1px solid #444',
              backgroundColor: '#222',
              color: '#fff',
              fontFamily: 'monospace',
              fontSize: '0.95em'
            }}
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              style={{
                background: 'none', border: 'none', color: '#888', cursor: 'pointer', fontSize: '1.2em'
              }}
            >
              ✖
            </button>
          )}
        </div>

      </div>

      {error && <div className="panel-error">{error}</div>}

      <div className="proposals-split-container">
        {/* LEFT COLUMN: LONG STRATEGIES */}
        <div className="proposals-column">
          <div className="column-header longs">LONG SIDE (JFIN/TRIM) ({longSideProposals.length})</div>
          {longSideProposals.length === 0 ? (
            <div className="no-proposals" style={{ padding: '20px', fontSize: '0.8em' }}>No Long Proposals</div>
          ) : (
            longSideProposals.map(p => (
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

        {/* RIGHT COLUMN: SHORT STRATEGIES */}
        <div className="proposals-column">
          <div className="column-header shorts">SHORT SIDE (JFIN/TRIM) ({shortSideProposals.length})</div>
          {shortSideProposals.length === 0 ? (
            <div className="no-proposals" style={{ padding: '20px', fontSize: '0.8em' }}>No Short Proposals</div>
          ) : (
            shortSideProposals.map(p => (
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

      <div className="panel-footer" style={{ fontSize: '0.8em', marginTop: '4px', textAlign: 'right', color: '#7f8c8d' }}>
        Updated: {lastUpdate ? lastUpdate.toLocaleTimeString() : '-'}
      </div>
    </div>
  )
}

export default LiveProposalsPanel

// Helper function to render proposal card (extracted to avoid duplication)
const ProposalCard = ({ proposal, isSelected, toggleSelection, getStatusClass, handleAccept, handleReject }) => {
  const sideUpper = (proposal.side || '').toUpperCase()
  const isSell = sideUpper.includes('SELL') || sideUpper.includes('SHORT')
  const isBuy = sideUpper.includes('BUY') || sideUpper.includes('COVER')

  let dynamicScoreLabel = '';
  let dynamicScoreValue = null;
  let dynamicScoreClass = '';

  if (isSell) {
    dynamicScoreLabel = 'Ask sell pahalilik';
    dynamicScoreValue = proposal.pahalilik_score;
    dynamicScoreClass = 'pahalilik';
  } else {
    dynamicScoreLabel = 'Bid buy ucuzluk';
    dynamicScoreValue = proposal.ucuzluk_score; // Default for buy
    dynamicScoreClass = 'ucuzluk';
  }

  return (
    <div
      className={`proposal-card ${getStatusClass(proposal.status)} ${isSelected ? 'selected-proposal' : ''}`}
      onClick={() => toggleSelection(proposal.id)}
      style={{
        borderLeft: isSelected ? '4px solid #00d2ff' : undefined,
        backgroundColor: isSelected ? 'rgba(0, 210, 255, 0.05)' : undefined,
        cursor: 'pointer',
        padding: '4px 6px',
        gap: '2px'
      }}
    >
      {/* LINE 1: CHECKBOX + SOJD 800 SELL @ 19.94 ... BID | ASK | SPREAD | LAST ... BUTTONS ... Pos: ... */}
      <div className="proposal-line-row primary" style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.95em' }}>
        {/* CHECKBOX */}
        {proposal.status === 'PROPOSED' && (
          <input
            type="checkbox"
            checked={isSelected}
            onChange={() => { }}
            onClick={(e) => { e.stopPropagation(); toggleSelection(proposal.id); }}
            style={{ cursor: 'pointer', transform: 'scale(1.2)', marginRight: '4px' }}
          />
        )}

        <span className="symbol" style={{ fontSize: '1.1em', fontWeight: '700' }}>{proposal.symbol}</span>

        <span style={{ fontWeight: '600' }}>{proposal.qty?.toLocaleString()}</span>
        <span className={isBuy ? 'side-buy' : 'side-sell'} style={{ fontWeight: 'bold' }}>{proposal.side}</span>
        <span>@</span>
        <span className={isBuy ? 'side-buy' : 'side-sell'} style={{ fontWeight: 'bold' }}>{proposal.price !== undefined ? proposal.price.toFixed(2) : '0.00'}</span>

        <span className="separator" style={{ opacity: 0.5 }}>|</span>
        <span style={{ fontSize: '0.9em' }}>Bid: {proposal.bid !== undefined && proposal.bid !== null ? proposal.bid.toFixed(2) : 'N/A'}</span>
        <span className="separator" style={{ opacity: 0.5 }}>|</span>
        <span style={{ fontSize: '0.9em' }}>Ask: {proposal.ask !== undefined && proposal.ask !== null ? proposal.ask.toFixed(2) : 'N/A'}</span>
        <span className="separator" style={{ opacity: 0.5 }}>|</span>
        <span style={{ fontSize: '0.9em' }}>Spr: {(proposal.spread || 0).toFixed(2)}</span>
        <span className="separator" style={{ opacity: 0.5 }}>|</span>
        <span style={{ fontSize: '0.9em' }}>Last: {proposal.last?.toFixed(2) || 'N/A'}</span>

        {/* COMPACT ACTION BUTTONS (between Last and Pos) */}
        {proposal.status === 'PROPOSED' ? (
          <div style={{ display: 'flex', gap: '3px', marginLeft: '6px' }}>
            <button
              className="mini-btn accept"
              onClick={(e) => { e.stopPropagation(); handleAccept(proposal.id); }}
              style={{
                padding: '2px 6px',
                fontSize: '9px',
                fontWeight: '600',
                minWidth: '50px'
              }}
            >
              ✓ ACC
            </button>
            <button
              className="mini-btn reject"
              onClick={(e) => { e.stopPropagation(); handleReject(proposal.id); }}
              style={{
                padding: '2px 6px',
                fontSize: '9px',
                fontWeight: '600',
                minWidth: '50px'
              }}
            >
              ✗ REJ
            </button>
          </div>
        ) : (
          <span className={`proposal-status ${getStatusClass(proposal.status)}`} style={{ fontSize: '9px', marginLeft: '6px' }}>
            {proposal.status}
          </span>
        )}

        {(proposal.current_qty !== undefined && proposal.current_qty !== null) && (
          <span style={{ marginLeft: 'auto', color: '#00d2ff', fontSize: '0.85em', fontWeight: '600', whiteSpace: 'nowrap' }}>
            (Pos: {proposal.current_qty} → {proposal.potential_qty !== undefined ? proposal.potential_qty : '?'})
          </span>
        )}
      </div>

      {/* LINE 2: Prev Close... daily chg... Bench chg... Score... */}
      <div className="proposal-line-row">
        <span>Prev Close :{proposal.prev_close?.toFixed(2) || 'N/A'}</span>
        <span className="separator"> | </span>
        <span>daily chg :</span>
        <span className={(proposal.daily_chg || 0) >= 0 ? 'val-pos' : 'val-neg'}>
          {proposal.daily_chg ? `${proposal.daily_chg >= 0 ? '+' : ''}${proposal.daily_chg.toFixed(2)}` : 'N/A'}
        </span>
        <span className="separator"> | </span>
        <span>Bench chg :</span>
        <span className={(proposal.bench_chg || 0) >= 0 ? 'val-pos' : 'val-neg'}>
          {proposal.bench_chg ? `${proposal.bench_chg >= 0 ? '+' : ''}${proposal.bench_chg.toFixed(2)}` : 'N/A'}
        </span>
        <span className="separator"> | </span>
        {dynamicScoreValue !== null && dynamicScoreValue !== undefined && (
          <>
            <span>{dynamicScoreLabel} : </span>
            <span className={`score-tag ${dynamicScoreClass}`}>
              {dynamicScoreValue > 0 ? '+' : ''}{dynamicScoreValue.toFixed(3)}
            </span>
          </>
        )}
      </div>

      {/* LINE 3: Just Reason (Buttons moved to Line 1) */}
      <div className="proposal-action-line" style={{ marginTop: '2px', paddingTop: '2px', gap: '4px' }}>
        <span className="mini-reason" title={proposal.reason}>
          R: {proposal.reason}
        </span>
      </div>
    </div>
  )
}
