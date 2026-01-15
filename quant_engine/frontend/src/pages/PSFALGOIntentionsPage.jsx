import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import './PSFALGOIntentionsPage.css'

function PSFALGOIntentionsPage() {
  const [intents, setIntents] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedIntents, setSelectedIntents] = useState(new Set())
  const [filterStatus, setFilterStatus] = useState('PENDING')
  const [filterSymbol, setFilterSymbol] = useState('')
  const [ws, setWs] = useState(null)
  const [wsConnected, setWsConnected] = useState(false)

  // Fetch intents
  const fetchIntents = useCallback(async () => {
    try {
      setLoading(true)
      const params = new URLSearchParams()
      if (filterStatus) params.append('status', filterStatus)
      if (filterSymbol) params.append('symbol', filterSymbol)
      params.append('limit', '500')
      
      const response = await fetch(`/api/psfalgo/intents?${params.toString()}`)
      const data = await response.json()
      
      if (Array.isArray(data)) {
        setIntents(data)
      }
    } catch (err) {
      console.error('Error fetching intents:', err)
    } finally {
      setLoading(false)
    }
  }, [filterStatus, filterSymbol])

  // WebSocket connection for real-time updates
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws`
    const websocket = new WebSocket(wsUrl)
    
    websocket.onopen = () => {
      setWsConnected(true)
      console.log('✅ WebSocket connected (PSFALGO Intentions)')
    }
    
    websocket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        if (message.type === 'intent_update') {
          // Refresh intents when update received
          fetchIntents()
        }
      } catch (err) {
        console.error('Error parsing WebSocket message:', err)
      }
    }
    
    websocket.onerror = (error) => {
      console.error('WebSocket error:', error)
      setWsConnected(false)
    }
    
    websocket.onclose = () => {
      setWsConnected(false)
      console.log('WebSocket disconnected (PSFALGO Intentions)')
    }
    
    setWs(websocket)
    
    return () => {
      websocket.close()
    }
  }, [fetchIntents])

  // Initial fetch and periodic refresh
  useEffect(() => {
    fetchIntents()
    const interval = setInterval(fetchIntents, 2000) // Refresh every 2 seconds
    return () => clearInterval(interval)
  }, [fetchIntents])

  // Approve intent
  const approveIntent = async (intentId) => {
    try {
      const response = await fetch(`/api/psfalgo/intents/${intentId}/approve`, {
        method: 'POST'
      })
      const data = await response.json()
      
      if (data.success) {
        fetchIntents() // Refresh
        setSelectedIntents(new Set()) // Clear selection
      } else {
        alert(`Error: ${data.error || 'Failed to approve intent'}`)
      }
    } catch (err) {
      console.error('Error approving intent:', err)
      alert('Error approving intent')
    }
  }

  // Reject intent
  const rejectIntent = async (intentId, reason) => {
    try {
      const response = await fetch(`/api/psfalgo/intents/${intentId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: reason || 'Rejected by user' })
      })
      const data = await response.json()
      
      if (data.success) {
        fetchIntents() // Refresh
        setSelectedIntents(new Set()) // Clear selection
      } else {
        alert(`Error: ${data.error || 'Failed to reject intent'}`)
      }
    } catch (err) {
      console.error('Error rejecting intent:', err)
      alert('Error rejecting intent')
    }
  }

  // Bulk approve
  const bulkApprove = async () => {
    if (selectedIntents.size === 0) {
      alert('No intents selected')
      return
    }
    
    try {
      const response = await fetch('/api/psfalgo/intents/bulk-approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Array.from(selectedIntents))
      })
      const data = await response.json()
      
      if (data.success) {
        alert(`Approved ${data.approved} intents, ${data.failed} failed`)
        fetchIntents()
        setSelectedIntents(new Set())
      } else {
        alert(`Error: ${data.error || 'Failed to approve intents'}`)
      }
    } catch (err) {
      console.error('Error bulk approving intents:', err)
      alert('Error bulk approving intents')
    }
  }

  // Toggle selection
  const toggleSelection = (intentId) => {
    const newSelection = new Set(selectedIntents)
    if (newSelection.has(intentId)) {
      newSelection.delete(intentId)
    } else {
      newSelection.add(intentId)
    }
    setSelectedIntents(newSelection)
  }

  // Select all
  const selectAll = () => {
    const pendingIntents = intents.filter(i => i.status === 'PENDING')
    setSelectedIntents(new Set(pendingIntents.map(i => i.id)))
  }

  // Clear selection
  const clearSelection = () => {
    setSelectedIntents(new Set())
  }

  // Get status color
  const getStatusColor = (status) => {
    switch (status) {
      case 'PENDING': return '#ffa500' // Orange
      case 'APPROVED': return '#00ff00' // Green
      case 'REJECTED': return '#ff0000' // Red
      case 'SENT': return '#0080ff' // Blue
      case 'EXPIRED': return '#808080' // Gray
      case 'FAILED': return '#ff0000' // Red
      default: return '#ffffff'
    }
  }

  // Format timestamp
  const formatTimestamp = (ts) => {
    if (!ts) return '-'
    const date = new Date(ts)
    return date.toLocaleTimeString()
  }

  // Filter intents
  const filteredIntents = intents.filter(intent => {
    if (filterStatus && intent.status !== filterStatus) return false
    if (filterSymbol && !intent.symbol.toLowerCase().includes(filterSymbol.toLowerCase())) return false
    return true
  })

  return (
    <div className="psfalgo-intentions-page">
      <header className="psfalgo-intentions-header">
        <div className="psfalgo-intentions-header-left">
          <Link to="/scanner" className="psfalgo-link-button">
            ← Scanner
          </Link>
          <h1>🤖 PSFALGO Intentions</h1>
        </div>
        <div className="psfalgo-intentions-header-right">
          <span className={`status-badge ${wsConnected ? 'connected' : 'disconnected'}`}>
            {wsConnected ? '🟢 WS Connected' : '🔴 WS Disconnected'}
          </span>
          <button onClick={fetchIntents} disabled={loading}>
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </header>

      <div className="psfalgo-intentions-controls">
        <div className="filters">
          <label>
            Status:
            <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
              <option value="">All</option>
              <option value="PENDING">PENDING</option>
              <option value="APPROVED">APPROVED</option>
              <option value="REJECTED">REJECTED</option>
              <option value="SENT">SENT</option>
              <option value="EXPIRED">EXPIRED</option>
              <option value="FAILED">FAILED</option>
            </select>
          </label>
          <label>
            Symbol:
            <input
              type="text"
              value={filterSymbol}
              onChange={(e) => setFilterSymbol(e.target.value)}
              placeholder="Filter by symbol..."
            />
          </label>
        </div>
        <div className="bulk-actions">
          <button onClick={selectAll}>Select All</button>
          <button onClick={clearSelection}>Clear Selection</button>
          <button 
            onClick={bulkApprove} 
            disabled={selectedIntents.size === 0}
            className="approve-button"
          >
            Approve Selected ({selectedIntents.size})
          </button>
        </div>
      </div>

      <div className="psfalgo-intentions-table-container">
        <table className="psfalgo-intentions-table">
          <thead>
            <tr>
              <th style={{ width: 40 }}>☐</th>
              <th style={{ width: 100 }}>Symbol</th>
              <th style={{ width: 80 }}>Action</th>
              <th style={{ width: 60 }}>Qty</th>
              <th style={{ width: 80 }}>Price</th>
              <th style={{ width: 80 }}>Order Type</th>
              <th style={{ width: 100 }}>Status</th>
              <th style={{ width: 150 }}>Trigger Rule</th>
              <th style={{ width: 200 }}>Reason</th>
              <th style={{ width: 100 }}>Risk</th>
              <th style={{ width: 120 }}>Time</th>
              <th style={{ width: 150 }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredIntents.length === 0 ? (
              <tr>
                <td colSpan="12" style={{ textAlign: 'center', padding: '20px' }}>
                  {loading ? 'Loading...' : 'No intents found'}
                </td>
              </tr>
            ) : (
              filteredIntents.map(intent => (
                <tr key={intent.id} className={`intent-row status-${intent.status.toLowerCase()}`}>
                  <td>
                    {intent.status === 'PENDING' && (
                      <input
                        type="checkbox"
                        checked={selectedIntents.has(intent.id)}
                        onChange={() => toggleSelection(intent.id)}
                      />
                    )}
                  </td>
                  <td style={{ fontWeight: 'bold' }}>{intent.symbol}</td>
                  <td style={{ color: intent.action === 'BUY' ? '#00ff00' : '#ff0000' }}>
                    {intent.action}
                  </td>
                  <td>{intent.qty}</td>
                  <td>${intent.price?.toFixed(2) || '-'}</td>
                  <td>{intent.order_type}</td>
                  <td>
                    <span 
                      style={{ 
                        color: getStatusColor(intent.status),
                        fontWeight: 'bold'
                      }}
                    >
                      {intent.status}
                    </span>
                  </td>
                  <td style={{ fontSize: '12px' }}>{intent.trigger_rule}</td>
                  <td style={{ fontSize: '12px' }} title={intent.reason_text}>
                    {intent.reason_text?.substring(0, 50) || '-'}
                    {intent.reason_text?.length > 50 ? '...' : ''}
                  </td>
                  <td>
                    {intent.risk_passed ? (
                      <span style={{ color: '#00ff00' }}>✓ PASS</span>
                    ) : (
                      <span style={{ color: '#ff0000' }} title={intent.rejected_reason || 'Risk check failed'}>
                        ✗ FAIL
                      </span>
                    )}
                  </td>
                  <td style={{ fontSize: '12px' }}>{formatTimestamp(intent.timestamp)}</td>
                  <td>
                    {intent.status === 'PENDING' && (
                      <>
                        <button
                          onClick={() => approveIntent(intent.id)}
                          className="approve-button-small"
                          title="Approve and execute"
                        >
                          ✓
                        </button>
                        <button
                          onClick={() => rejectIntent(intent.id)}
                          className="reject-button-small"
                          title="Reject"
                        >
                          ✗
                        </button>
                      </>
                    )}
                    {intent.status === 'REJECTED' && intent.rejected_reason && (
                      <span style={{ fontSize: '10px', color: '#ff0000' }} title={intent.rejected_reason}>
                        {intent.rejected_reason.substring(0, 30)}...
                      </span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="psfalgo-intentions-summary">
        <div className="summary-item">
          <strong>Total:</strong> {intents.length} intents
        </div>
        <div className="summary-item">
          <strong>Pending:</strong> <span style={{ color: '#ffa500' }}>{intents.filter(i => i.status === 'PENDING').length}</span>
        </div>
        <div className="summary-item">
          <strong>Approved:</strong> <span style={{ color: '#00ff00' }}>{intents.filter(i => i.status === 'APPROVED').length}</span>
        </div>
        <div className="summary-item">
          <strong>Rejected:</strong> <span style={{ color: '#ff0000' }}>{intents.filter(i => i.status === 'REJECTED').length}</span>
        </div>
        <div className="summary-item">
          <strong>Sent:</strong> <span style={{ color: '#0080ff' }}>{intents.filter(i => i.status === 'SENT').length}</span>
        </div>
        <div className="summary-item">
          <strong>Expired:</strong> <span style={{ color: '#808080' }}>{intents.filter(i => i.status === 'EXPIRED').length}</span>
        </div>
      </div>
    </div>
  )
}

export default PSFALGOIntentionsPage





