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
function LiveProposalsPanel({ wsConnected = false }) {
  const [proposals, setProposals] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('all') // all, PROPOSED, ACCEPTED, REJECTED
  const [autoScroll, setAutoScroll] = useState(true)
  const [lastUpdate, setLastUpdate] = useState(null)
  const listRef = useRef(null)

  // Fetch proposals from REST API (append-row flow - don't replace, merge)
  const fetchProposals = useCallback(async () => {
    try {
      const response = await fetch('/api/psfalgo/proposals/latest?limit=50')
      const result = await response.json()
      
      if (result.success && result.proposals) {
        // Append-row flow: Merge new proposals with existing ones
        setProposals(prevProposals => {
          const proposalMap = new Map(prevProposals.map(p => [p.proposal_id || `${p.cycle_id}_${p.symbol}_${p.side}`, p]))
          
          // Add/update new proposals
          result.proposals.forEach(proposal => {
            const key = proposal.proposal_id || `${proposal.cycle_id}_${proposal.symbol}_${proposal.side}`
            proposalMap.set(key, proposal)
          })
          
          // Convert back to array and sort by proposal_ts (newest first)
          const merged = Array.from(proposalMap.values())
          merged.sort((a, b) => {
            const tsA = new Date(a.proposal_ts || a.decision_ts || 0).getTime()
            const tsB = new Date(b.proposal_ts || b.decision_ts || 0).getTime()
            return tsB - tsA
          })
          
          return merged.slice(0, 100) // Keep last 100
        })
        
        setError(null)
        setLastUpdate(new Date())
        
        // Auto-scroll to top when new proposals arrive (newest at top)
        if (autoScroll && listRef.current) {
          setTimeout(() => {
            if (listRef.current) {
              listRef.current.scrollTop = 0
            }
          }, 100)
        }
      }
    } catch (err) {
      console.error('Error fetching proposals:', err)
      setError('Failed to load proposals')
    } finally {
      setLoading(false)
    }
  }, [autoScroll])

  // Initial fetch
  useEffect(() => {
    fetchProposals()
  }, [fetchProposals])

  // ALWAYS poll for updates - REST API is the primary source
  // Poll every 1 second for real-time feel
  useEffect(() => {
    const interval = setInterval(fetchProposals, 1000)
    return () => clearInterval(interval)
  }, [fetchProposals])

  // Also listen on BroadcastChannel for faster updates (if Scanner is broadcasting)
  useEffect(() => {
    const handleMessage = (event) => {
      try {
        const message = event.data
        if (message.type === 'proposals_update' && message.data) {
          setProposals(message.data)
          setLastUpdate(new Date())
        }
      } catch (err) {
        console.error('Error handling proposals update:', err)
      }
    }

    let bc = null
    try {
      bc = new BroadcastChannel('market-data')
      bc.onmessage = handleMessage
    } catch (err) {
      console.warn('BroadcastChannel not supported')
    }

    return () => {
      if (bc) bc.close()
    }
  }, [])

  // Accept proposal
  const handleAccept = async (proposalId) => {
    try {
      const response = await fetch(`/api/psfalgo/proposals/${proposalId}/accept`, {
        method: 'POST'
      })
      const result = await response.json()
      
      if (result.success) {
        fetchProposals() // Refresh
      } else {
        alert(result.error || 'Failed to accept proposal')
      }
    } catch (err) {
      console.error('Error accepting proposal:', err)
      alert('Failed to accept proposal')
    }
  }

  // Reject proposal
  const handleReject = async (proposalId) => {
    try {
      const response = await fetch(`/api/psfalgo/proposals/${proposalId}/reject`, {
        method: 'POST'
      })
      const result = await response.json()
      
      if (result.success) {
        fetchProposals() // Refresh
      } else {
        alert(result.error || 'Failed to reject proposal')
      }
    } catch (err) {
      console.error('Error rejecting proposal:', err)
      alert('Failed to reject proposal')
    }
  }

  // Filter proposals
  const filteredProposals = filter === 'all' 
    ? proposals 
    : proposals.filter(p => p.status === filter)

  // Get status badge class
  const getStatusClass = (status) => {
    switch (status) {
      case 'PROPOSED': return 'status-proposed'
      case 'ACCEPTED': return 'status-accepted'
      case 'REJECTED': return 'status-rejected'
      case 'EXPIRED': return 'status-expired'
      default: return ''
    }
  }

  // Get side badge class
  const getSideClass = (side) => {
    switch (side) {
      case 'BUY': return 'side-buy'
      case 'SELL': return 'side-sell'
      case 'COVER': return 'side-cover'
      case 'SHORT': return 'side-short'
      default: return ''
    }
  }

  // Format time
  const formatTime = (isoString) => {
    if (!isoString) return '-'
    const date = new Date(isoString)
    return date.toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit', 
      second: '2-digit' 
    })
  }

  if (loading) {
    return (
      <div className="live-proposals-panel">
        <div className="panel-header">
          <h3>📋 Live Order Proposals</h3>
        </div>
        <div className="panel-loading">Loading proposals...</div>
      </div>
    )
  }

  return (
    <div className="live-proposals-panel">
      <div className="panel-header">
        <h3>📋 Live Order Proposals</h3>
        <div className="panel-controls">
          <select 
            value={filter} 
            onChange={(e) => setFilter(e.target.value)}
            className="filter-select"
          >
            <option value="all">All ({proposals.length})</option>
            <option value="PROPOSED">Proposed ({proposals.filter(p => p.status === 'PROPOSED').length})</option>
            <option value="ACCEPTED">Accepted ({proposals.filter(p => p.status === 'ACCEPTED').length})</option>
            <option value="REJECTED">Rejected ({proposals.filter(p => p.status === 'REJECTED').length})</option>
          </select>
          <label className="auto-scroll-toggle">
            <input 
              type="checkbox" 
              checked={autoScroll} 
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            Auto-scroll
          </label>
          <button onClick={fetchProposals} className="refresh-btn">🔄</button>
        </div>
      </div>

      {error && (
        <div className="panel-error">{error}</div>
      )}

      <div ref={listRef} className="proposals-list" style={{ maxHeight: autoScroll ? '400px' : 'none', overflowY: 'auto' }}>
        {filteredProposals.length === 0 ? (
          <div className="no-proposals">
            <span className="no-proposals-icon">📭</span>
            <span>No proposals yet. Start RUNALL to generate order proposals.</span>
          </div>
        ) : (
          filteredProposals.map((proposal, index) => (
            <div 
              key={proposal.id || index} 
              className={`proposal-card ${getStatusClass(proposal.status)}`}
            >
              <div className="proposal-header">
                <span className="proposal-symbol">{proposal.symbol}</span>
                <span className={`proposal-side ${getSideClass(proposal.side)}`}>
                  {proposal.side}
                </span>
                <span className="proposal-engine">{proposal.engine}</span>
                <span className={`proposal-status ${getStatusClass(proposal.status)}`}>
                  {proposal.status}
                </span>
              </div>
              
              <div className="proposal-details">
                <div className="proposal-qty-price">
                  <span className="qty">{proposal.qty?.toLocaleString()} shares</span>
                  <span className="price">@ ${proposal.price?.toFixed(2)}</span>
                  <span className="order-type">{proposal.order_type}</span>
                </div>
                
                <div className="proposal-market">
                  <span>Bid: ${proposal.bid?.toFixed(2)}</span>
                  <span>Ask: ${proposal.ask?.toFixed(2)}</span>
                  <span>Spread: ${(proposal.spread || (proposal.ask - proposal.bid) || 0).toFixed(2)}</span>
                </div>
                
                <div className="proposal-reason">
                  <span className="reason-label">Reason:</span>
                  <span className="reason-text">{proposal.reason}</span>
                </div>
                
                {/* JFIN Details (if available) */}
                {proposal.metrics_used && (proposal.metrics_used.group || proposal.metrics_used.jfin_percentage) && (
                  <div className="proposal-jfin-details">
                    <span className="jfin-label">JFIN:</span>
                    {proposal.metrics_used.group && (
                      <span>Group: {proposal.metrics_used.group}</span>
                    )}
                    {proposal.metrics_used.cgrup && (
                      <span>CGRUP: {proposal.metrics_used.cgrup}</span>
                    )}
                    {proposal.metrics_used.final_bb_skor && (
                      <span>Final_BB: {proposal.metrics_used.final_bb_skor?.toFixed(2)}</span>
                    )}
                    {proposal.metrics_used.final_fb_skor && (
                      <span>Final_FB: {proposal.metrics_used.final_fb_skor?.toFixed(2)}</span>
                    )}
                    {proposal.metrics_used.calculated_lot && (
                      <span>Calc Lot: {proposal.metrics_used.calculated_lot?.toLocaleString()}</span>
                    )}
                    {proposal.metrics_used.addable_lot && (
                      <span>Addable: {proposal.metrics_used.addable_lot?.toLocaleString()}</span>
                    )}
                    {proposal.metrics_used.final_lot && (
                      <span>Final Lot: {proposal.metrics_used.final_lot?.toLocaleString()}</span>
                    )}
                    {proposal.metrics_used.maxalw && (
                      <span>MAXALW: {proposal.metrics_used.maxalw}</span>
                    )}
                    {proposal.metrics_used.befday_qty !== undefined && (
                      <span>BEFDAY: {proposal.metrics_used.befday_qty}</span>
                    )}
                    {proposal.metrics_used.jfin_percentage && (
                      <span>JFIN %: {proposal.metrics_used.jfin_percentage}%</span>
                    )}
                  </div>
                )}
                
                <div className="proposal-meta">
                  <span>Confidence: {(proposal.confidence * 100)?.toFixed(0)}%</span>
                  <span>Cycle: #{proposal.cycle_id}</span>
                  <span>Time: {formatTime(proposal.proposal_ts)}</span>
                </div>
              </div>

              {proposal.status === 'PROPOSED' && (
                <div className="proposal-actions">
                  <button 
                    className="accept-btn"
                    onClick={() => handleAccept(proposal.id)}
                  >
                    ✅ Accept
                  </button>
                  <button 
                    className="reject-btn"
                    onClick={() => handleReject(proposal.id)}
                  >
                    ❌ Reject
                  </button>
                </div>
              )}

              {proposal.human_action && (
                <div className="proposal-human-action">
                  <span className="human-action-badge">
                    {proposal.human_action === 'ACCEPTED' ? '✅' : '❌'} 
                    {proposal.human_action} at {formatTime(proposal.human_action_ts)}
                  </span>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <div className="panel-footer">
        <span className="proposal-count">
          Showing {filteredProposals.length} of {proposals.length} proposals
        </span>
        {lastUpdate && (
          <span className="last-update">
            Last update: {lastUpdate.toLocaleTimeString()}
          </span>
        )}
      </div>
    </div>
  )
}

export default LiveProposalsPanel

