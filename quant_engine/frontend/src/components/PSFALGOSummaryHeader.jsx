import React, { useState, useEffect } from 'react'
import './PSFALGOSummaryHeader.css'

function PSFALGOSummaryHeader({ onRefresh }) {
  const [exposureMode, setExposureMode] = useState(null)
  const [realExposure, setRealExposure] = useState(null)
  const [shadowExposure, setShadowExposure] = useState(null)
  const [autocycleStatus, setAutocycleStatus] = useState(null)
  const [cycleStatus, setCycleStatus] = useState(null)
  const [loading, setLoading] = useState(true)

  // Fetch all summary data
  const fetchSummaryData = async () => {
    try {
      setLoading(true)

      // 1. Fetch Real State (Exposure & Mode) - The Source of Truth
      const stateResponse = await fetch('/api/psfalgo/state')
      const stateResult = await stateResponse.json()

      if (stateResult.success && stateResult.state) {
        if (stateResult.state.exposure) {
          // Map net_exposure to net_value for compatibility with existing UI logic, or use directly
          // Backend sends 'net_exposure', Frontend expects 'net_value' currently.
          // We will standardise to match what the UI expects (net_value) by mapping it.
          const exposureData = stateResult.state.exposure;
          setRealExposure({
            ...exposureData,
            net_value: exposureData.net_exposure // Standardize
          })

          if (exposureData.mode) {
            setExposureMode({ mode: exposureData.mode })
          }
        }
      }

      // 2. Fetch shadow exposure (keep existing logic)
      const shadowResponse = await fetch('/api/psfalgo/shadow/exposure')
      const shadowResult = await shadowResponse.json()
      if (shadowResult.success && shadowResult.exposure) {
        setShadowExposure(shadowResult.exposure)
      }

      // 3. Fetch AutoCycle status
      const autocycleResponse = await fetch('/api/psfalgo/cycle/autocycle/status')
      const autocycleResult = await autocycleResponse.json()
      if (autocycleResult.success && autocycleResult.status) {
        setAutocycleStatus(autocycleResult.status)
      }

      // 4. Fetch cycle status
      const cycleResponse = await fetch('/api/psfalgo/cycle/status')
      const cycleResult = await cycleResponse.json()
      if (cycleResult.success && cycleResult.status) {
        setCycleStatus(cycleResult.status)
      }
    } catch (error) {
      console.error('Error fetching PSFALGO summary:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSummaryData()
    // Refresh every 3 seconds
    const interval = setInterval(fetchSummaryData, 3000)
    return () => clearInterval(interval)
  }, [])

  // Refresh when onRefresh trigger changes
  useEffect(() => {
    if (onRefresh !== undefined && onRefresh !== null) {
      fetchSummaryData()
    }
  }, [onRefresh])

  // Calculate net exposure delta
  const netExposureDelta = shadowExposure && realExposure
    ? shadowExposure.net_value - (realExposure.net_value || 0)
    : null

  // Get exposure mode badge class
  const getExposureModeBadgeClass = (mode) => {
    if (!mode) return 'exposure-mode-unknown'
    const modeUpper = mode.toUpperCase()
    if (modeUpper === 'DEFENSIVE') return 'exposure-mode-defensive'
    if (modeUpper === 'TRANSITION') return 'exposure-mode-transition'
    if (modeUpper === 'OFFENSIVE') return 'exposure-mode-offensive'
    return 'exposure-mode-unknown'
  }

  // Get AutoCycle status badge class
  const getAutocycleBadgeClass = (status) => {
    if (!status || !status.running) return 'autocycle-stopped'
    if (status.blocked_reason === 'PENDING_APPROVAL') return 'autocycle-waiting'
    if (status.blocked_reason === 'EXECUTION_IN_PROGRESS') return 'autocycle-executing'
    return 'autocycle-running'
  }

  // Check if there's a pending approval
  const hasPendingApproval = cycleStatus?.current_cycle?.status === 'PENDING_APPROVAL'

  // Get last cycle result
  const lastCycle = cycleStatus?.current_cycle || cycleStatus?.last_cycle

  if (loading) {
    return (
      <div className="psfalgo-summary-header">
        <div className="summary-loading">Loading summary...</div>
      </div>
    )
  }

  return (
    <div className="psfalgo-summary-header">
      <div className="summary-row">
        {/* Exposure Mode */}
        <div className="summary-item">
          <span className="summary-label">Exposure Mode:</span>
          <span className={`summary-badge ${getExposureModeBadgeClass(exposureMode?.mode)}`}>
            {exposureMode?.mode || 'N/A'}
          </span>
        </div>

        {/* Current Exposure (Real) */}
        <div className="summary-item">
          <span className="summary-label">Real Exposure:</span>
          <span className="summary-value">
            {realExposure?.net_value !== undefined
              ? `$${realExposure.net_value.toFixed(2)}`
              : 'N/A'}
          </span>
        </div>

        {/* Shadow Exposure */}
        <div className="summary-item">
          <span className="summary-label">Shadow Exposure:</span>
          <span className="summary-value">
            {shadowExposure?.net_value !== undefined
              ? `$${shadowExposure.net_value.toFixed(2)}`
              : 'N/A'}
          </span>
        </div>

        {/* Net Exposure Delta */}
        <div className="summary-item">
          <span className="summary-label">Net Delta:</span>
          <span className={`summary-value ${netExposureDelta !== null && netExposureDelta !== 0 ? (netExposureDelta > 0 ? 'positive' : 'negative') : ''}`}>
            {netExposureDelta !== null
              ? `${netExposureDelta > 0 ? '+' : ''}$${netExposureDelta.toFixed(2)}`
              : 'N/A'}
          </span>
        </div>

        {/* AutoCycle Status */}
        <div className="summary-item">
          <span className="summary-label">AutoCycle:</span>
          <span className={`summary-badge ${getAutocycleBadgeClass(autocycleStatus)}`}>
            {autocycleStatus?.running
              ? (autocycleStatus.blocked_reason === 'PENDING_APPROVAL'
                ? '⏳ WAITING'
                : autocycleStatus.blocked_reason === 'EXECUTION_IN_PROGRESS'
                  ? '⚙️ EXECUTING'
                  : '▶️ RUNNING')
              : '⏸️ STOPPED'}
          </span>
        </div>

        {/* Pending Approval Badge */}
        {hasPendingApproval && (
          <div className="summary-item">
            <span className="summary-badge pending-approval-badge">
              ⚠️ PENDING APPROVAL
            </span>
          </div>
        )}
      </div>

      {/* Last Cycle Result */}
      {lastCycle && (
        <div className="summary-row cycle-result-row">
          <div className="summary-item">
            <span className="summary-label">Last Cycle:</span>
            <span className="summary-value-small">{lastCycle.cycle_id || 'N/A'}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Actions:</span>
            <span className="summary-value-small">{lastCycle.action_count || 0}</span>
          </div>
          {lastCycle.execution_results && (
            <>
              <div className="summary-item">
                <span className="summary-label">Executed:</span>
                <span className="summary-value-small positive">
                  {lastCycle.execution_results.executed_count || 0}
                </span>
              </div>
              <div className="summary-item">
                <span className="summary-label">Blocked:</span>
                <span className="summary-value-small negative">
                  {lastCycle.execution_results.blocked_count || 0}
                </span>
              </div>
              <div className="summary-item">
                <span className="summary-label">Skipped:</span>
                <span className="summary-value-small">
                  {lastCycle.execution_results.skipped_count || 0}
                </span>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

export default PSFALGOSummaryHeader

