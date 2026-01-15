import React, { useMemo, useState, useEffect } from 'react'
import PSFALGOApproveModal from './PSFALGOApproveModal'
import './PSFALGOBulkActionPanel.css'

function PSFALGOBulkActionPanel({ data, onLedgerUpdate, onCycleUpdate }) {
  const [selectedSymbols, setSelectedSymbols] = useState(new Set())
  const [latestEntries, setLatestEntries] = useState([])
  const [showLatestEntries, setShowLatestEntries] = useState(false)
  const [cycleStatus, setCycleStatus] = useState(null)
  const [isRunningCycle, setIsRunningCycle] = useState(false)
  const [autocycleStatus, setAutocycleStatus] = useState(null)
  const [autocycleInterval, setAutocycleInterval] = useState(120)
  const [showApproveModal, setShowApproveModal] = useState(false)
  const [pendingCycleId, setPendingCycleId] = useState(null)
  
  // Filter and group data by action type
  const groupedData = useMemo(() => {
    if (!data || !Array.isArray(data)) {
      return {}
    }
    
    // Filter: only symbols where psfalgo_action_plan.action != 'HOLD'
    const filtered = data.filter(row => {
      const actionPlan = row.psfalgo_action_plan
      return actionPlan && actionPlan.action && actionPlan.action !== 'HOLD' && actionPlan.action !== 'BLOCKED'
    })
    
    // Group by action type
    const grouped = {}
    filtered.forEach(row => {
      const action = row.psfalgo_action_plan?.action || 'UNKNOWN'
      if (!grouped[action]) {
        grouped[action] = []
      }
      grouped[action].push(row)
    })
    
    return grouped
  }, [data])
  
  // Get all action types
  const actionTypes = Object.keys(groupedData).sort()
  
  // Toggle selection for a symbol
  const toggleSelection = (symbol) => {
    setSelectedSymbols(prev => {
      const newSet = new Set(prev)
      if (newSet.has(symbol)) {
        newSet.delete(symbol)
      } else {
        newSet.add(symbol)
      }
      return newSet
    })
  }
  
  // Toggle all in a group
  const toggleGroup = (actionType) => {
    const symbols = groupedData[actionType].map(row => row.PREF_IBKR)
    const allSelected = symbols.every(sym => selectedSymbols.has(sym))
    
    setSelectedSymbols(prev => {
      const newSet = new Set(prev)
      if (allSelected) {
        symbols.forEach(sym => newSet.delete(sym))
      } else {
        symbols.forEach(sym => newSet.add(sym))
      }
      return newSet
    })
  }
  
  // Toggle all
  const toggleAll = () => {
    const allSymbols = Object.values(groupedData).flat().map(row => row.PREF_IBKR)
    const allSelected = allSymbols.every(sym => selectedSymbols.has(sym))
    
    setSelectedSymbols(prev => {
      const newSet = new Set(prev)
      if (allSelected) {
        allSymbols.forEach(sym => newSet.delete(sym))
      } else {
        allSymbols.forEach(sym => newSet.add(sym))
      }
      return newSet
    })
  }
  
  // Fetch cycle status
  const fetchCycleStatus = async () => {
    try {
      const response = await fetch('/api/psfalgo/cycle/status')
      const result = await response.json()
      if (result.success && result.status) {
        const currentCycle = result.status.current_cycle
        const lastCycle = result.status.last_cycle
        setCycleStatus(currentCycle || lastCycle)
      }
    } catch (error) {
      console.error('Error fetching cycle status:', error)
    }
  }

  // Load cycle status on mount and periodically
  useEffect(() => {
    fetchCycleStatus()
    const interval = setInterval(fetchCycleStatus, 3000)
    return () => clearInterval(interval)
  }, [])

  // Handle RUNALL cycle
  const handleRunAll = async () => {
    setIsRunningCycle(true)
    try {
      const response = await fetch('/api/psfalgo/cycle/run', {
        method: 'POST',
      })
      const result = await response.json()
      if (result.success) {
        alert(`PSFALGO Cycle ${result.cycle_id} generated (${result.action_count} actions). Status: PENDING_APPROVAL`)
        // Refresh cycle status
        await fetchCycleStatus()
        if (onCycleUpdate) {
          onCycleUpdate()
        }
      } else {
        alert(`Error: ${result.error || 'Failed to run cycle'}`)
      }
    } catch (error) {
      console.error('Error running cycle:', error)
      alert(`Error running cycle: ${error.message}`)
    } finally {
      setIsRunningCycle(false)
    }
  }
  
  // Bulk approve (DRY-RUN ONLY - writes to ledger, no broker execution)
  const handleBulkApprove = async () => {
    const selectedRows = data.filter(row => selectedSymbols.has(row.PREF_IBKR))
    
    if (selectedRows.length === 0) {
      alert('No actions selected')
      return
    }
    
    // Prepare actions for ledger
    const actions = selectedRows.map(row => ({
      symbol: row.PREF_IBKR,
      psfalgo_action: row.psfalgo_action_plan?.action || 'UNKNOWN',
      size_percent: row.psfalgo_action_plan?.size_percent || 0.0,
      size_lot_estimate: row.psfalgo_action_plan?.size_lot_estimate || 0,
      exposure_mode: row.exposure_mode,
      guard_status: row.guard_status,
      action_reason: row.psfalgo_action_plan?.reason,
      position_snapshot: {
        befday_qty: row.befday_qty,
        current_qty: row.current_qty,
        potential_qty: row.potential_qty
      }
    }))
    
    try {
      const response = await fetch('/api/psfalgo/ledger/approve', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(actions),
      })
      
      const result = await response.json()
      
      if (result.success) {
        alert(`DRY-RUN: ${result.approved_count} actions approved and written to ledger. No broker execution.`)
        // Clear selection after approval
        setSelectedSymbols(new Set())
        // Refresh ledger entries
        const loadLatestEntries = async () => {
          try {
            const response = await fetch('/api/psfalgo/ledger?limit=10')
            const result = await response.json()
            if (result.success) {
              setLatestEntries(result.entries || [])
            }
          } catch (error) {
            console.error('Error loading ledger entries:', error)
          }
        }
        loadLatestEntries()
      } else {
        alert(`Error: ${result.message || 'Failed to approve actions'}`)
      }
    } catch (error) {
      console.error('Error approving actions:', error)
      alert(`Error approving actions: ${error.message}`)
    }
  }
  
  // Load AutoCycle status
  useEffect(() => {
    const loadAutocycleStatus = async () => {
      try {
        const response = await fetch('/api/psfalgo/cycle/autocycle/status')
        const result = await response.json()
        if (result.success && result.status) {
          setAutocycleStatus(result.status)
          if (result.status.interval_seconds) {
            setAutocycleInterval(result.status.interval_seconds)
          }
        }
      } catch (error) {
        console.error('Error loading AutoCycle status:', error)
      }
    }
    
    loadAutocycleStatus()
    // Refresh every 2 seconds
    const interval = setInterval(loadAutocycleStatus, 2000)
    return () => clearInterval(interval)
  }, [])
  
  // Handle approve cycle (called from modal)
  const handleApproveCycle = async (cycleId) => {
    try {
      const response = await fetch('/api/psfalgo/cycle/approve', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ cycle_id: cycleId }),
      })
      const result = await response.json()
      if (result.success) {
        alert(`PSFALGO Cycle ${result.cycle_id} approved. ${result.approved_count} actions written to ledger.`)
        // Hard refresh all PSFALGO data
        if (onLedgerUpdate) {
          onLedgerUpdate()
        }
        if (onCycleUpdate) {
          onCycleUpdate()
        }
        await fetchCycleStatus()
      } else {
        alert(`Error: ${result.error || 'Failed to approve cycle'}`)
      }
    } catch (error) {
      console.error('Error approving cycle:', error)
      alert(`Error approving cycle: ${error.message}`)
    }
  }

  // Handle reject cycle
  const handleRejectCycle = async (cycleId) => {
    try {
      const response = await fetch('/api/psfalgo/cycle/reject', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ cycle_id: cycleId }),
      })
      const result = await response.json()
      if (result.success) {
        alert(`PSFALGO Cycle ${result.cycle_id} rejected.`)
        // Hard refresh all PSFALGO data
        if (onCycleUpdate) {
          onCycleUpdate()
        }
        await fetchCycleStatus()
      } else {
        alert(`Error: ${result.error || 'Failed to reject cycle'}`)
      }
    } catch (error) {
      console.error('Error rejecting cycle:', error)
      alert(`Error rejecting cycle: ${error.message}`)
    }
  }

  // Handle AutoCycle toggle
  const handleAutocycleToggle = async () => {
    try {
      if (autocycleStatus?.running) {
        // Stop
        const response = await fetch('/api/psfalgo/cycle/autocycle/stop', {
          method: 'POST',
        })
        const result = await response.json()
        if (result.success) {
          alert('AutoCycle stopped')
          // Refresh status
          const statusResponse = await fetch('/api/psfalgo/cycle/autocycle/status')
          const statusResult = await statusResponse.json()
          if (statusResult.success && statusResult.status) {
            setAutocycleStatus(statusResult.status)
          }
        } else {
          alert(`Error: ${result.error || 'Failed to stop AutoCycle'}`)
        }
      } else {
        // Start
        if (autocycleInterval < 10) {
          alert('Interval must be at least 10 seconds')
          return
        }
        const response = await fetch('/api/psfalgo/cycle/autocycle/start', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ interval_seconds: autocycleInterval }),
        })
        const result = await response.json()
        if (result.success) {
          alert(`AutoCycle started (interval: ${autocycleInterval}s)`)
          // Refresh status
          const statusResponse = await fetch('/api/psfalgo/cycle/autocycle/status')
          const statusResult = await statusResponse.json()
          if (statusResult.success && statusResult.status) {
            setAutocycleStatus(statusResult.status)
          }
        } else {
          alert(`Error: ${result.error || 'Failed to start AutoCycle'}`)
        }
      }
    } catch (error) {
      console.error('Error toggling AutoCycle:', error)
      alert(`Error: ${error.message}`)
    }
  }
  
  // Get total count
  const totalCount = Object.values(groupedData).reduce((sum, rows) => sum + rows.length, 0)
  
  if (totalCount === 0) {
    return (
      <div className="psfalgo-bulk-panel">
        <div className="psfalgo-bulk-header">
          <h3>PSFALGO Bulk Actions</h3>
        </div>
        <div className="psfalgo-bulk-empty">
          No actions available (all symbols are HOLD or BLOCKED)
        </div>
      </div>
    )
  }
  
  return (
    <div className="psfalgo-bulk-panel">
      <div className="psfalgo-bulk-header">
        <h3>PSFALGO Bulk Actions</h3>
        <div className="psfalgo-bulk-actions">
          <button 
            className="psfalgo-runall-btn"
            onClick={handleRunAll}
            disabled={isRunningCycle}
            title="Run PSFALGO cycle (RUNALL) in SHADOW MODE"
          >
            {isRunningCycle ? 'Running...' : 'RUNALL (SHADOW)'}
          </button>
          <button 
            className="psfalgo-toggle-all-btn"
            onClick={toggleAll}
          >
            {Object.values(groupedData).flat().every(row => selectedSymbols.has(row.PREF_IBKR)) ? 'Deselect All' : 'Select All'}
          </button>
          <button 
            className="psfalgo-approve-btn"
            onClick={handleBulkApprove}
            disabled={selectedSymbols.size === 0}
          >
            Bulk Approve ({selectedSymbols.size})
          </button>
        </div>
      </div>
      
      {/* AutoCycle Control Section */}
      <div className="psfalgo-autocycle-control">
        <div className="psfalgo-autocycle-header">
          <h4>AutoCycle (SHADOW)</h4>
          <div className="psfalgo-autocycle-controls">
            <div className="psfalgo-autocycle-interval">
              <label>Interval (seconds):</label>
              <input
                type="number"
                min="10"
                value={autocycleInterval}
                onChange={(e) => setAutocycleInterval(parseInt(e.target.value) || 120)}
                disabled={autocycleStatus?.running}
                className="psfalgo-interval-input"
              />
            </div>
            <button
              className={`psfalgo-autocycle-toggle-btn ${autocycleStatus?.running ? 'running' : 'stopped'}`}
              onClick={handleAutocycleToggle}
            >
              {autocycleStatus?.running ? 'Stop AutoCycle' : 'Start AutoCycle'}
            </button>
          </div>
        </div>
        <div className="psfalgo-autocycle-status">
          <div className="autocycle-status-item">
            <span className="autocycle-label">Status:</span>
            <span className={`autocycle-value ${autocycleStatus?.running ? 'running' : 'stopped'}`}>
              {autocycleStatus?.running ? 'RUNNING' : 'STOPPED'}
            </span>
          </div>
          {autocycleStatus?.interval_seconds && (
            <div className="autocycle-status-item">
              <span className="autocycle-label">Interval:</span>
              <span className="autocycle-value">{autocycleStatus.interval_seconds}s</span>
            </div>
          )}
          {autocycleStatus?.last_run && (
            <div className="autocycle-status-item">
              <span className="autocycle-label">Last Run:</span>
              <span className="autocycle-value">
                {new Date(autocycleStatus.last_run).toLocaleString()}
              </span>
            </div>
          )}
          {autocycleStatus?.blocked_reason && autocycleStatus?.running && (
            <div className="autocycle-status-item blocked-reason">
              <span className="autocycle-label">Waiting:</span>
              <span className={`autocycle-value blocked-reason-${autocycleStatus.blocked_reason.toLowerCase().replace(/_/g, '-')}`}>
                {autocycleStatus.blocked_reason === 'PENDING_APPROVAL' && '⏳ PENDING_APPROVAL'}
                {autocycleStatus.blocked_reason === 'EXECUTION_IN_PROGRESS' && '⚙️ EXECUTION_IN_PROGRESS'}
                {autocycleStatus.blocked_reason === 'MANUAL_STOP' && '⏸️ MANUAL_STOP'}
                {!['PENDING_APPROVAL', 'EXECUTION_IN_PROGRESS', 'MANUAL_STOP'].includes(autocycleStatus.blocked_reason) && autocycleStatus.blocked_reason}
              </span>
            </div>
          )}
        </div>
      </div>
      
      {/* AutoCycle Control Section */}
      <div className="psfalgo-autocycle-control">
        <div className="psfalgo-autocycle-header">
          <h4>AutoCycle (SHADOW)</h4>
          <div className="psfalgo-autocycle-controls">
            <div className="psfalgo-autocycle-interval">
              <label>Interval (seconds):</label>
              <input
                type="number"
                min="10"
                value={autocycleInterval}
                onChange={(e) => setAutocycleInterval(parseInt(e.target.value) || 120)}
                disabled={autocycleStatus?.running}
                className="psfalgo-interval-input"
              />
            </div>
            <button
              className={`psfalgo-autocycle-toggle-btn ${autocycleStatus?.running ? 'running' : 'stopped'}`}
              onClick={handleAutocycleToggle}
            >
              {autocycleStatus?.running ? 'Stop AutoCycle' : 'Start AutoCycle'}
            </button>
          </div>
        </div>
        <div className="psfalgo-autocycle-status">
          <div className="autocycle-status-item">
            <span className="autocycle-label">Status:</span>
            <span className={`autocycle-value ${autocycleStatus?.running ? 'running' : 'stopped'}`}>
              {autocycleStatus?.running ? 'RUNNING' : 'STOPPED'}
            </span>
          </div>
          {autocycleStatus?.interval_seconds && (
            <div className="autocycle-status-item">
              <span className="autocycle-label">Interval:</span>
              <span className="autocycle-value">{autocycleStatus.interval_seconds}s</span>
            </div>
          )}
          {autocycleStatus?.last_run && (
            <div className="autocycle-status-item">
              <span className="autocycle-label">Last Run:</span>
              <span className="autocycle-value">
                {new Date(autocycleStatus.last_run).toLocaleString()}
              </span>
            </div>
          )}
          {autocycleStatus?.blocked_reason && autocycleStatus?.running && (
            <div className="autocycle-status-item blocked-reason">
              <span className="autocycle-label">Waiting:</span>
              <span className={`autocycle-value blocked-reason-${autocycleStatus.blocked_reason.toLowerCase().replace(/_/g, '-')}`}>
                {autocycleStatus.blocked_reason === 'PENDING_APPROVAL' && '⏳ PENDING_APPROVAL'}
                {autocycleStatus.blocked_reason === 'EXECUTION_IN_PROGRESS' && '⚙️ EXECUTION_IN_PROGRESS'}
                {autocycleStatus.blocked_reason === 'MANUAL_STOP' && '⏸️ MANUAL_STOP'}
                {!['PENDING_APPROVAL', 'EXECUTION_IN_PROGRESS', 'MANUAL_STOP'].includes(autocycleStatus.blocked_reason) && autocycleStatus.blocked_reason}
              </span>
            </div>
          )}
        </div>
      </div>
      
      {/* Cycle Status Section */}
      {cycleStatus && (
        <div className="psfalgo-cycle-status">
          <div className="psfalgo-cycle-header">
            <h4>Last Cycle: {cycleStatus.cycle_id || 'N/A'}</h4>
            <div className="psfalgo-cycle-actions">
              {cycleStatus.status === 'PENDING_APPROVAL' && (
                <>
                  <button
                    className="psfalgo-approve-cycle-btn"
                    onClick={() => {
                      setPendingCycleId(cycleStatus.cycle_id)
                      setShowApproveModal(true)
                    }}
                  >
                    Approve Cycle
                  </button>
                  <button
                    className="psfalgo-reject-cycle-btn"
                    onClick={() => handleRejectCycle(cycleStatus.cycle_id)}
                  >
                    Reject
                  </button>
                </>
              )}
            </div>
          </div>
          
          <div className="psfalgo-cycle-details">
            <div className="cycle-info">
              <div className="cycle-info-item">
                <span className="cycle-label">Status:</span>
                <span className={`cycle-value cycle-status-${cycleStatus.status?.toLowerCase()}`}>
                  {cycleStatus.status}
                </span>
              </div>
              <div className="cycle-info-item">
                <span className="cycle-label">Actions:</span>
                <span className="cycle-value">{cycleStatus.action_count || 0}</span>
              </div>
              <div className="cycle-info-item">
                <span className="cycle-label">Timestamp:</span>
                <span className="cycle-value">
                  {cycleStatus.cycle_timestamp ? new Date(cycleStatus.cycle_timestamp).toLocaleString() : 'N/A'}
                </span>
              </div>
            </div>
            
            {cycleStatus.exposure_before && (
              <div className="cycle-exposure">
                <h5>Exposure Before:</h5>
                <div className="exposure-stats">
                  <div className="stat-item">
                    <span className="stat-label">Total:</span>
                    <span className="stat-value">${cycleStatus.exposure_before.total_exposure?.toFixed(2) || '0.00'}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Long:</span>
                    <span className="stat-value positive">${cycleStatus.exposure_before.long_exposure?.toFixed(2) || '0.00'}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Short:</span>
                    <span className="stat-value negative">${cycleStatus.exposure_before.short_exposure?.toFixed(2) || '0.00'}</span>
                  </div>
                </div>
              </div>
            )}
            
            {cycleStatus.exposure_after && (
              <div className="cycle-exposure">
                <h5>Exposure After:</h5>
                <div className="exposure-stats">
                  <div className="stat-item">
                    <span className="stat-label">Total:</span>
                    <span className="stat-value">${cycleStatus.exposure_after.total_exposure?.toFixed(2) || '0.00'}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Long:</span>
                    <span className="stat-value positive">${cycleStatus.exposure_after.long_exposure?.toFixed(2) || '0.00'}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Short:</span>
                    <span className="stat-value negative">${cycleStatus.exposure_after.short_exposure?.toFixed(2) || '0.00'}</span>
                  </div>
                </div>
              </div>
            )}
            
            {/* PSFALGO Cycle Summary */}
            {cycleStatus.cycle_summary && (
              <div className="psfalgo-cycle-summary">
                <h5>Cycle Summary:</h5>
                <div className="summary-stats">
                  <div className="summary-stat-item">
                    <span className="summary-label">Total Actions:</span>
                    <span className="summary-value">{cycleStatus.cycle_summary.total_actions || 0}</span>
                  </div>
                  {cycleStatus.cycle_summary.blocked_count > 0 && (
                    <div className="summary-stat-item">
                      <span className="summary-label">Blocked:</span>
                      <span className="summary-value negative">{cycleStatus.cycle_summary.blocked_count}</span>
                    </div>
                  )}
                </div>
                
                {/* Action Counts by Type */}
                {cycleStatus.cycle_summary.action_counts && Object.keys(cycleStatus.cycle_summary.action_counts).length > 0 && (
                  <div className="action-counts-section">
                    <h6>Actions by Type:</h6>
                    <div className="action-counts-grid">
                      {Object.entries(cycleStatus.cycle_summary.action_counts).map(([actionType, count]) => (
                        <div key={actionType} className="action-count-item">
                          <span className="action-type">{actionType}:</span>
                          <span className="action-count">{count}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                {/* Top Block Reasons */}
                {cycleStatus.cycle_summary.top_block_reasons && cycleStatus.cycle_summary.top_block_reasons.length > 0 && (
                  <div className="block-reasons-section">
                    <h6>Top Block Reasons:</h6>
                    <ul className="block-reasons-list">
                      {cycleStatus.cycle_summary.top_block_reasons.map((item, idx) => (
                        <li key={idx} className="block-reason-item">
                          <span className="reason-text">{item.reason}</span>
                          <span className="reason-count">({item.count}x)</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {/* Exposure Change */}
                {cycleStatus.cycle_summary.exposure_change && (
                  <div className="exposure-change-section">
                    <h6>Exposure Change:</h6>
                    <div className="exposure-change-stats">
                      <div className="change-stat-item">
                        <span className="change-label">Total:</span>
                        <span className={`change-value ${cycleStatus.cycle_summary.exposure_change.total_change >= 0 ? 'positive' : 'negative'}`}>
                          ${cycleStatus.cycle_summary.exposure_change.total_change?.toFixed(2) || '0.00'}
                        </span>
                      </div>
                      <div className="change-stat-item">
                        <span className="change-label">Long:</span>
                        <span className={`change-value ${cycleStatus.cycle_summary.exposure_change.long_change >= 0 ? 'positive' : 'negative'}`}>
                          ${cycleStatus.cycle_summary.exposure_change.long_change?.toFixed(2) || '0.00'}
                        </span>
                      </div>
                      <div className="change-stat-item">
                        <span className="change-label">Short:</span>
                        <span className={`change-value ${cycleStatus.cycle_summary.exposure_change.short_change >= 0 ? 'positive' : 'negative'}`}>
                          ${cycleStatus.cycle_summary.exposure_change.short_change?.toFixed(2) || '0.00'}
                        </span>
                      </div>
                      <div className="change-stat-item">
                        <span className="change-label">Net Value:</span>
                        <span className={`change-value ${cycleStatus.cycle_summary.exposure_change.net_value_change >= 0 ? 'positive' : 'negative'}`}>
                          ${cycleStatus.cycle_summary.exposure_change.net_value_change?.toFixed(2) || '0.00'}
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
            
            {/* PSFALGO Execution Results */}
            {cycleStatus.execution_results && (
              <div className="psfalgo-exec-section">
                <h5>PSFALGO Execution:</h5>
                <div className="execution-stats">
                  <div className="stat-item">
                    <span className="stat-label">Simulated:</span>
                    <span className="stat-value">{cycleStatus.execution_results.simulated_count || 0}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Executed:</span>
                    <span className="stat-value positive">{cycleStatus.execution_results.executed_count || 0}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Blocked:</span>
                    <span className="stat-value negative">{cycleStatus.execution_results.blocked_count || 0}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Skipped:</span>
                    <span className="stat-value">{cycleStatus.execution_results.skipped_count || 0}</span>
                  </div>
                </div>
                {cycleStatus.execution_results.reason && (
                  <div className="execution-reason">
                    <span className="reason-label">Note:</span>
                    <span className="reason-text">{cycleStatus.execution_results.reason}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
      
      <div className="psfalgo-bulk-content">
        {actionTypes.map(actionType => {
          const rows = groupedData[actionType]
          const groupSelected = rows.every(row => selectedSymbols.has(row.PREF_IBKR))
          
          return (
            <div key={actionType} className="psfalgo-action-group">
              <div className="psfalgo-group-header">
                <input
                  type="checkbox"
                  checked={groupSelected}
                  onChange={() => toggleGroup(actionType)}
                  className="psfalgo-group-checkbox"
                />
                <h4 className="psfalgo-group-title">
                  {actionType} ({rows.length})
                </h4>
              </div>
              
              <div className="psfalgo-group-table">
                <div className="psfalgo-table-header">
                  <div className="psfalgo-col-checkbox"></div>
                  <div className="psfalgo-col-symbol">Symbol</div>
                  <div className="psfalgo-col-action">Action</div>
                  <div className="psfalgo-col-size-pct">Size %</div>
                  <div className="psfalgo-col-size-lot">Size (Lot)</div>
                  <div className="psfalgo-col-reason">Reason</div>
                </div>
                
                <div className="psfalgo-table-body">
                  {rows.map(row => {
                    const symbol = row.PREF_IBKR
                    const actionPlan = row.psfalgo_action_plan || {}
                    const isSelected = selectedSymbols.has(symbol)
                    
                    return (
                      <div 
                        key={symbol} 
                        className={`psfalgo-table-row ${isSelected ? 'selected' : ''}`}
                        onClick={() => toggleSelection(symbol)}
                      >
                        <div className="psfalgo-col-checkbox">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelection(symbol)}
                            onClick={(e) => e.stopPropagation()}
                            className="psfalgo-row-checkbox"
                          />
                        </div>
                        <div className="psfalgo-col-symbol">{symbol}</div>
                        <div className="psfalgo-col-action">{actionPlan.action || 'N/A'}</div>
                        <div className="psfalgo-col-size-pct">
                          {actionPlan.size_percent !== null && actionPlan.size_percent !== undefined 
                            ? `${actionPlan.size_percent.toFixed(2)}%` 
                            : 'N/A'}
                        </div>
                        <div className="psfalgo-col-size-lot">
                          {actionPlan.size_lot_estimate !== null && actionPlan.size_lot_estimate !== undefined 
                            ? actionPlan.size_lot_estimate 
                            : 'N/A'}
                        </div>
                        <div className="psfalgo-col-reason" title={actionPlan.reason || ''}>
                          {actionPlan.reason || 'N/A'}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          )
        })}
      </div>
      
      {/* Last Approved Actions Section */}
      {latestEntries.length > 0 && (
        <div className="psfalgo-latest-entries">
          <div className="psfalgo-latest-header">
            <h4>Last Approved Actions (DRY-RUN)</h4>
            <button
              className="psfalgo-toggle-entries-btn"
              onClick={() => setShowLatestEntries(!showLatestEntries)}
            >
              {showLatestEntries ? 'Hide' : 'Show'} ({latestEntries.length})
            </button>
          </div>
          
          {showLatestEntries && (
            <div className="psfalgo-latest-table">
              <div className="psfalgo-table-header">
                <div className="psfalgo-col-timestamp">Timestamp</div>
                <div className="psfalgo-col-symbol">Symbol</div>
                <div className="psfalgo-col-action">Action</div>
                <div className="psfalgo-col-size-pct">Size %</div>
                <div className="psfalgo-col-size-lot">Size (Lot)</div>
                <div className="psfalgo-col-reason">Reason</div>
              </div>
              
              <div className="psfalgo-table-body">
                {latestEntries.map((entry, idx) => (
                  <div key={idx} className="psfalgo-table-row">
                    <div className="psfalgo-col-timestamp">
                      {new Date(entry.timestamp).toLocaleString()}
                    </div>
                    <div className="psfalgo-col-symbol">{entry.symbol}</div>
                    <div className="psfalgo-col-action">{entry.psfalgo_action}</div>
                    <div className="psfalgo-col-size-pct">
                      {entry.size_percent?.toFixed(2)}%
                    </div>
                    <div className="psfalgo-col-size-lot">{entry.size_lot_estimate}</div>
                    <div className="psfalgo-col-reason" title={entry.action_reason || ''}>
                      {entry.action_reason || 'N/A'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      
      <div className="psfalgo-bulk-footer">
        Total: {totalCount} actions | Selected: {selectedSymbols.size}
      </div>

      {/* Approve Modal */}
      {showApproveModal && cycleStatus && (
        <PSFALGOApproveModal
          cycle={cycleStatus}
          onConfirm={async () => {
            await handleApproveCycle(pendingCycleId)
            setShowApproveModal(false)
            setPendingCycleId(null)
          }}
          onCancel={() => {
            setShowApproveModal(false)
            setPendingCycleId(null)
          }}
        />
      )}
    </div>
  )
}

export default PSFALGOBulkActionPanel

