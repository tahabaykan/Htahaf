import React, { useState, useEffect } from 'react'
import './PSFALGOSummaryHeader.css'

function PSFALGOSummaryHeader({ onRefresh }) {
  const [exposureMode, setExposureMode] = useState(null)
  const [realExposure, setRealExposure] = useState(null)
  const [shadowExposure, setShadowExposure] = useState(null)
  const [exposureMetrics, setExposureMetrics] = useState(null) // BEFDAY + intraday from /api/trading/exposure
  const [activeAccount, setActiveAccount] = useState(null) // Current trading account
  const [autocycleStatus, setAutocycleStatus] = useState(null)
  const [cycleStatus, setCycleStatus] = useState(null)
  const [freeExposure, setFreeExposure] = useState(null) // Free exposure from /api/xnl/free-exposure
  const [loading, setLoading] = useState(true)
  const [minmaxLoading, setMinmaxLoading] = useState({}) // { HAMPRO: true, IBKR_PED: true, ALL: true }
  const [minmaxResult, setMinmaxResult] = useState({}) // { HAMPRO: 'success'|'error', IBKR_PED: ... }

  // MinMax Area compute handler
  const handleMinMaxCompute = async (target) => {
    setMinmaxLoading(prev => ({ ...prev, [target]: true }))
    setMinmaxResult(prev => ({ ...prev, [target]: null }))
    try {
      const url = target === 'ALL'
        ? '/api/xnl/minmax-area/all'
        : `/api/xnl/minmax-area?account_id=${target}`
      const res = await fetch(url, { method: 'POST' })
      const result = await res.json()
      setMinmaxResult(prev => ({ ...prev, [target]: result.success ? 'success' : 'error' }))
      // Clear success badge after 4 seconds
      setTimeout(() => setMinmaxResult(prev => ({ ...prev, [target]: null })), 4000)
    } catch (err) {
      console.error('MinMax compute error:', err)
      setMinmaxResult(prev => ({ ...prev, [target]: 'error' }))
      setTimeout(() => setMinmaxResult(prev => ({ ...prev, [target]: null })), 4000)
    } finally {
      setMinmaxLoading(prev => ({ ...prev, [target]: false }))
    }
  }

  // Fetch all summary data
  const fetchSummaryData = async () => {
    try {
      setLoading(true)

      // 1. PRIMARY: Fetch from /api/trading/exposure (always works, even when RunallEngine is stopped)
      try {
        const expResponse = await fetch('/api/trading/exposure')
        const expResult = await expResponse.json()
        if (expResult.success && expResult.exposure) {
          // Set active account from this response
          setActiveAccount(expResult.trading_mode || null)

          // Use this as primary exposure data
          const exp = expResult.exposure
          setRealExposure({
            pot_total: exp.total_exposure || 0,
            pot_max: exp.max_pot_exp_pct ? (exp.total_exposure / (exp.current_exposure_pct / 100)) : 1000000,
            long_value: exp.long_exposure || 0,
            short_value: exp.short_exposure || 0,
            net_value: exp.net_exposure || 0,
            net_exposure: exp.net_exposure || 0,
            max_cur_exp_pct: exp.max_cur_exp_pct,
            max_pot_exp_pct: exp.max_pot_exp_pct,
            current_exposure_pct: exp.current_exposure_pct,
            potential_exposure_pct: exp.potential_exposure_pct,
            mode: null // Will be set from state if available
          })
          setExposureMetrics(exp)
        }
      } catch (_) {
        setExposureMetrics(null)
      }

      // 2. Fetch Real State (for mode and additional info)
      const stateResponse = await fetch('/api/psfalgo/state')
      const stateResult = await stateResponse.json()

      if (stateResult.success && stateResult.state) {
        if (stateResult.state.exposure?.mode) {
          setExposureMode({ mode: stateResult.state.exposure.mode })
          // Merge mode into realExposure
          setRealExposure(prev => prev ? { ...prev, mode: stateResult.state.exposure.mode } : prev)
        }
      }

      // 3. Fetch shadow exposure (keep existing logic)
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

      // 5. Fetch free exposure
      try {
        const freeExpRes = await fetch('/api/xnl/free-exposure')
        const freeExpResult = await freeExpRes.json()
        if (freeExpResult.success && freeExpResult.free_exposure) {
          setFreeExposure(freeExpResult.free_exposure)
        }
      } catch (_) {
        // Free exposure not critical
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

  // Get account badge class
  const getAccountBadgeClass = (account) => {
    if (!account) return 'account-unknown'
    const acc = account.toUpperCase()
    if (acc === 'HAMPRO') return 'account-hammer'
    if (acc === 'IBKR_PED') return 'account-ped'
    if (acc === 'IBKR_GUN') return 'account-gun'
    return 'account-unknown'
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
        {/* Active Account */}
        <div className="summary-item">
          <span className="summary-label">Account:</span>
          <span className={`summary-badge ${getAccountBadgeClass(activeAccount)}`}>
            {activeAccount === 'HAMPRO' ? '🔨 Hammer' :
              activeAccount === 'IBKR_PED' ? '📊 IBKR PED' :
                activeAccount === 'IBKR_GUN' ? '🔥 IBKR GUN' :
                  activeAccount || 'N/A'}
          </span>
        </div>

        {/* Exposure Mode */}
        <div className="summary-item">
          <span className="summary-label">Exposure Mode:</span>
          <span className={`summary-badge ${getExposureModeBadgeClass(exposureMode?.mode)}`}>
            {exposureMode?.mode || 'N/A'}
          </span>
        </div>

        {/* Current Exposure (Real) - pot_total; text black */}
        <div className="summary-item">
          <span className="summary-label">Real Exposure:</span>
          <span className="summary-value summary-value-exposure">
            {realExposure?.pot_total !== undefined
              ? `$${realExposure.pot_total.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
              : 'N/A'}
          </span>
        </div>

        {/* Max cur exp / Max pot exp (single source - Set & Check Rules / Port Adjuster) */}
        {((exposureMetrics && (exposureMetrics.max_cur_exp_pct != null || exposureMetrics.max_pot_exp_pct != null)) ||
          (realExposure && (realExposure.max_cur_exp_pct != null || realExposure.max_pot_exp_pct != null))) && (
            <>
              <div className="summary-item">
                <span className="summary-label">Max cur exp:</span>
                <span className="summary-value summary-value-exposure">
                  {(exposureMetrics?.max_cur_exp_pct ?? realExposure?.max_cur_exp_pct) != null
                    ? `${(exposureMetrics?.max_cur_exp_pct ?? realExposure?.max_cur_exp_pct)}%` : '—'}
                </span>
              </div>
              <div className="summary-item">
                <span className="summary-label">Max pot exp:</span>
                <span className="summary-value summary-value-exposure">
                  {(exposureMetrics?.max_pot_exp_pct ?? realExposure?.max_pot_exp_pct) != null
                    ? `${(exposureMetrics?.max_pot_exp_pct ?? realExposure?.max_pot_exp_pct)}%` : '—'}
                </span>
              </div>
            </>
          )}

        {/* Free Exposure (from FreeExposureEngine) */}
        {freeExposure && (
          <>
            <div className="summary-item summary-item-small">
              <span className="summary-label">Free Cur:</span>
              <span className="summary-value" style={{
                fontSize: '11px',
                color: freeExposure.blocked ? '#ef4444' : (freeExposure.free_cur_pct ?? 0) > 30 ? '#4ade80' : '#fbbf24'
              }}>
                {freeExposure.free_cur_pct?.toFixed(1) ?? '—'}%
              </span>
            </div>
            <div className="summary-item summary-item-small">
              <span className="summary-label">Free Pot:</span>
              <span className="summary-value" style={{
                fontSize: '11px',
                color: freeExposure.blocked ? '#ef4444' : (freeExposure.free_pot_pct ?? 0) > 30 ? '#4ade80' : '#fbbf24'
              }}>
                {freeExposure.free_pot_pct?.toFixed(1) ?? '—'}%
              </span>
            </div>
            <div className="summary-item summary-item-small">
              <span className="summary-label">Tier:</span>
              <span className="summary-value" style={{
                fontSize: '10px',
                padding: '1px 4px',
                borderRadius: '3px',
                backgroundColor: freeExposure.blocked ? 'rgba(239,68,68,0.2)' :
                  (freeExposure.effective_free_pct ?? 0) > 40 ? 'rgba(74,222,128,0.15)' : 'rgba(251,191,36,0.15)',
                color: freeExposure.blocked ? '#ef4444' :
                  (freeExposure.effective_free_pct ?? 0) > 40 ? '#4ade80' : '#fbbf24',
                fontWeight: 'bold'
              }}>
                {freeExposure.blocked ? '🚫 BLOCKED' : (freeExposure.tier_label || `ADV/${freeExposure.adv_divisor || '?'}`)}
              </span>
            </div>
          </>
        )}

        {/* Long Value (in $) */}
        <div className="summary-item">
          <span className="summary-label">Long:</span>
          <span className="summary-value positive">
            {realExposure?.long_value !== undefined
              ? `$${realExposure.long_value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
              : 'N/A'}
          </span>
        </div>

        {/* Short Value (in $) */}
        <div className="summary-item">
          <span className="summary-label">Short:</span>
          <span className="summary-value negative">
            {realExposure?.short_value !== undefined
              ? `$${realExposure.short_value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
              : 'N/A'}
          </span>
        </div>

        {/* Net Delta (Long - Short in dollars) */}
        <div className="summary-item">
          <span className="summary-label">Net Delta:</span>
          <span className={`summary-value ${realExposure?.long_value !== undefined && realExposure?.short_value !== undefined ? ((realExposure.long_value - realExposure.short_value) > 0 ? 'positive' : 'negative') : ''}`}>
            {realExposure?.long_value !== undefined && realExposure?.short_value !== undefined
              ? `${(realExposure.long_value - realExposure.short_value) > 0 ? '+' : ''}$${(realExposure.long_value - realExposure.short_value).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
              : 'N/A'}
          </span>
        </div>

        {/* BEFDAY + Intraday (compact) */}
        {exposureMetrics && (exposureMetrics.befday_long_exp != null || exposureMetrics.intraday_total_chg_exp != null) && (
          <>
            <div className="summary-item summary-item-small">
              <span className="summary-label">BEF L:</span>
              <span className="summary-value positive" style={{ fontSize: '11px' }}>
                ${exposureMetrics.befday_long_exp?.toFixed(0) ?? '—'}({exposureMetrics.befday_long_exp_pct?.toFixed(0) ?? '—'}%)
              </span>
            </div>
            <div className="summary-item summary-item-small">
              <span className="summary-label">BEF S:</span>
              <span className="summary-value negative" style={{ fontSize: '11px' }}>
                ${exposureMetrics.befday_short_exp?.toFixed(0) ?? '—'}({exposureMetrics.befday_short_exp_pct?.toFixed(0) ?? '—'}%)
              </span>
            </div>
            <div className="summary-item summary-item-small">
              <span className="summary-label">ΔL:</span>
              <span className={`summary-value ${(exposureMetrics.intraday_long_chg_exp ?? 0) >= 0 ? 'positive' : 'negative'}`} style={{ fontSize: '11px' }}>
                ${exposureMetrics.intraday_long_chg_exp?.toFixed(0) ?? '—'}({exposureMetrics.intraday_long_chg_exp_pct?.toFixed(0) ?? '—'}%)
              </span>
            </div>
            <div className="summary-item summary-item-small">
              <span className="summary-label">ΔS:</span>
              <span className={`summary-value ${(exposureMetrics.intraday_short_chg_exp ?? 0) >= 0 ? 'negative' : 'positive'}`} style={{ fontSize: '11px' }}>
                ${exposureMetrics.intraday_short_chg_exp?.toFixed(0) ?? '—'}({exposureMetrics.intraday_short_chg_exp_pct?.toFixed(0) ?? '—'}%)
              </span>
            </div>
            <div className="summary-item summary-item-small">
              <span className="summary-label">ΔTot:</span>
              <span className={`summary-value ${(exposureMetrics.intraday_total_chg_exp ?? 0) >= 0 ? 'positive' : 'negative'}`} style={{ fontSize: '11px' }}>
                ${exposureMetrics.intraday_total_chg_exp?.toFixed(0) ?? '—'}({exposureMetrics.intraday_total_chg_exp_pct?.toFixed(0) ?? '—'}%)
              </span>
            </div>
          </>
        )}

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

        {/* MinMax Area Buttons */}
        <div className="summary-item minmax-buttons-group">
          <span className="summary-label">MinMax:</span>
          <button
            className={`minmax-btn minmax-btn-ham ${minmaxResult.HAMPRO === 'success' ? 'minmax-success' : minmaxResult.HAMPRO === 'error' ? 'minmax-error' : ''}`}
            onClick={() => handleMinMaxCompute('HAMPRO')}
            disabled={minmaxLoading.HAMPRO}
            title="Compute MinMax Area for HAMPRO account"
          >
            {minmaxLoading.HAMPRO ? '⏳' : '🔨'} HAM
          </button>
          <button
            className={`minmax-btn minmax-btn-ped ${minmaxResult.IBKR_PED === 'success' ? 'minmax-success' : minmaxResult.IBKR_PED === 'error' ? 'minmax-error' : ''}`}
            onClick={() => handleMinMaxCompute('IBKR_PED')}
            disabled={minmaxLoading.IBKR_PED}
            title="Compute MinMax Area for IBKR PED account"
          >
            {minmaxLoading.IBKR_PED ? '⏳' : '📊'} PED
          </button>
          <button
            className={`minmax-btn minmax-btn-all ${minmaxResult.ALL === 'success' ? 'minmax-success' : minmaxResult.ALL === 'error' ? 'minmax-error' : ''}`}
            onClick={() => handleMinMaxCompute('ALL')}
            disabled={minmaxLoading.ALL}
            title="Compute MinMax Area for BOTH accounts (HAMPRO + IBKR_PED)"
          >
            {minmaxLoading.ALL ? '⏳' : '🔄'} Both
          </button>
        </div>
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

