import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import PSFALGOBulkActionPanel from '../components/PSFALGOBulkActionPanel'
import PSFALGOSummaryHeader from '../components/PSFALGOSummaryHeader'
import TradingPanelsOverlay from '../components/TradingPanelsOverlay'
import ProposalTabSystem from '../components/ProposalTabSystem'
import LiveDataStatusBar from '../components/LiveDataStatusBar'
import TakeProfitLongsTab from '../components/TakeProfitLongsTab'
import TakeProfitShortsTab from '../components/TakeProfitShortsTab'
import EngineStatusPanel from '../components/EngineStatusPanel'
import SimulationPanel from '../components/SimulationPanel'
import KarbotuDiagnostic from '../components/KarbotuDiagnostic'
import AddnewposSettingsPanel from '../components/AddnewposSettingsPanel'
import GenExpoLimiterModal from '../components/GenExpoLimiterModal'
import RevOrdersModal from '../components/RevOrdersModal'
import './PSFALGOPage.css'

function PSFALGOPage() {
  const [data, setData] = useState([])
  const [bcConnected, setBcConnected] = useState(false)
  const [pollingActive, setPollingActive] = useState(false)
  const [tradingMode, setTradingMode] = useState('HAMMER_PRO')
  const [overlayOpen, setOverlayOpen] = useState(false)
  const [overlayPanelType, setOverlayPanelType] = useState('positions')
  const [summaryRefreshTrigger, setSummaryRefreshTrigger] = useState(0)
  const [activeTab, setActiveTab] = useState('positions')

  // Simulation & Report State
  const [showSimulation, setShowSimulation] = useState(false)
  const [showReport, setShowReport] = useState(false)
  const [showGenExpo, setShowGenExpo] = useState(false)
  const [showRevOrders, setShowRevOrders] = useState(false)

  // RUNALL Engine State
  const [runallState, setRunallState] = useState({
    global_state: 'IDLE',
    cycle_state: 'INIT',
    loop_count: 0,
    loop_running: false,
    dry_run_mode: true,
    last_error: null
  })
  const [runallLoading, setRunallLoading] = useState(false)
  const [runallError, setRunallError] = useState(null)

  // XNL Engine State
  const [xnlState, setXnlState] = useState({
    state: 'STOPPED',
    started_at: null,
    stopped_at: null,
    total_orders_sent: 0,
    total_orders_cancelled: 0,
    total_front_cycles: 0,
    total_refresh_cycles: 0,
    last_error: null,
    cycle_states: {}
  })
  const [xnlLoading, setXnlLoading] = useState(false)
  const [xnlError, setXnlError] = useState(null)
  const [cancelLoading, setCancelLoading] = useState(null) // 'incr'|'decr'|'sells'|'buys'|'lt'|'mm'|'tum' or null
  const [revExcluded, setRevExcluded] = useState(() => {
    try { return localStorage.getItem('rev_excluded') === 'true' } catch { return false }
  })    // when true, REV-tagged orders are excluded from cancel

  // Dual Process: alternate XNL between two accounts (longest front cycle 3.5 min per account)
  const [dualProcessState, setDualProcessState] = useState({
    state: 'STOPPED',
    account_a: 'IBKR_PED',
    account_b: 'HAMPRO',
    current_account: null,
    loop_count: 0,
    last_error: null
  })
  const [dualProcessLoading, setDualProcessLoading] = useState(false)
  const [ibkrAccount, setIbkrAccount] = useState(() => localStorage.getItem('dual_process_ibkr_account') || 'IBKR_PED')

  // HEAVY Mode: Account-aware settings (each account has separate settings)
  const HEAVY_ACCOUNTS = ['HAMPRO', 'IBKR_PED', 'IBKR_MAIN']
  const defaultHeavySettings = {
    heavy_long_dec: false,
    heavy_short_dec: false,
    heavy_lot_pct: 30,
    heavy_long_threshold: 0.02,
    heavy_short_threshold: -0.02
  }
  const [heavySettingsAll, setHeavySettingsAll] = useState({
    HAMPRO: { ...defaultHeavySettings },
    IBKR_PED: { ...defaultHeavySettings },
    IBKR_MAIN: { ...defaultHeavySettings }
  })

  // Fetch HEAVY settings for all accounts
  const fetchHeavySettings = useCallback(async () => {
    try {
      const res = await fetch('/api/xnl/heavy-settings')
      if (res.ok) {
        const data = await res.json()
        if (data.all_accounts) {
          setHeavySettingsAll(prev => ({
            ...prev,
            ...data.all_accounts
          }))
        }
      }
    } catch (err) {
      console.error('Failed to fetch HEAVY settings:', err)
    }
  }, [])

  // Update HEAVY settings for a specific account
  const updateAccountHeavySettings = useCallback(async (accountId, updates) => {
    try {
      // Optimistic update
      setHeavySettingsAll(prev => ({
        ...prev,
        [accountId]: { ...prev[accountId], ...updates }
      }))

      const res = await fetch(`/api/xnl/heavy-settings/${accountId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates)
      })
      if (res.ok) {
        const data = await res.json()
        if (data.settings) {
          setHeavySettingsAll(prev => ({
            ...prev,
            [accountId]: data.settings
          }))
        }
        console.log(`✅ HEAVY settings updated for ${accountId}:`, updates)
      }
    } catch (err) {
      console.error(`Failed to update HEAVY settings for ${accountId}:`, err)
    }
  }, [])

  // Legacy: for backward compat, also expose simple fetchHeavyModes
  const fetchHeavyModes = fetchHeavySettings

  // MM Lot Mode Settings (fixed vs adv_adjust)
  const [mmLotSettings, setMmLotSettings] = useState({
    lot_mode: 'fixed',
    lot_per_stock: 200
  })

  // Fetch MM lot settings
  const fetchMmLotSettings = useCallback(async () => {
    try {
      const res = await fetch('/api/xnl/mm/settings')
      if (res.ok) {
        const data = await res.json()
        if (data.settings) {
          setMmLotSettings({
            lot_mode: data.settings.lot_mode || 'fixed',
            lot_per_stock: data.settings.lot_per_stock || 200
          })
        }
      }
    } catch (err) {
      console.error('Failed to fetch MM lot settings:', err)
    }
  }, [])

  // Update MM lot settings
  const updateMmLotSettings = useCallback(async (updates) => {
    try {
      // Optimistic update
      setMmLotSettings(prev => ({ ...prev, ...updates }))

      const res = await fetch('/api/xnl/mm/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates)
      })
      if (res.ok) {
        const data = await res.json()
        if (data.settings) {
          setMmLotSettings({
            lot_mode: data.settings.lot_mode || 'fixed',
            lot_per_stock: data.settings.lot_per_stock || 200
          })
        }
        console.log('✅ MM lot settings updated:', updates)
      }
    } catch (err) {
      console.error('Failed to update MM lot settings:', err)
    }
  }, [])

  // L/S Ratio Settings (per increase engine)
  const [lsRatios, setLsRatios] = useState({
    MM_ENGINE: { long_pct: 50, short_pct: 50 },
    PATADD_ENGINE: { long_pct: 50, short_pct: 50 },
    ADDNEWPOS_ENGINE: { long_pct: 50, short_pct: 50 },
  })

  const fetchLsRatios = useCallback(async () => {
    try {
      const res = await fetch('/api/psfalgo/ls-ratio')
      if (res.ok) {
        const data = await res.json()
        if (data.ratios) setLsRatios(data.ratios)
      }
    } catch (err) {
      console.error('Failed to fetch L/S ratios:', err)
    }
  }, [])

  const updateLsRatio = useCallback(async (engineName, longPct) => {
    const clamped = Math.max(0, Math.min(100, parseInt(longPct) || 50))
    // Optimistic update
    setLsRatios(prev => ({
      ...prev,
      [engineName]: { long_pct: clamped, short_pct: 100 - clamped }
    }))
    try {
      const res = await fetch('/api/psfalgo/ls-ratio', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ engine: engineName, long_pct: clamped })
      })
      if (res.ok) {
        const data = await res.json()
        if (data.ratios) setLsRatios(data.ratios)
        console.log(`✅ L/S ratio updated: ${engineName} L=${clamped}% S=${100 - clamped}%`)
      }
    } catch (err) {
      console.error(`Failed to update L/S ratio for ${engineName}:`, err)
    }
  }, [])

  // Baseline Reset: notification state + handler
  const [resetNotification, setResetNotification] = useState(null)

  const handleBaselineReset = useCallback(async (category = null) => {
    const label = category || 'ALL'
    if (!window.confirm(`Reset ${label} settings to baseline defaults?`)) return
    try {
      const url = category
        ? `/api/psfalgo/settings/reset-to-baseline?category=${category}`
        : '/api/psfalgo/settings/reset-to-baseline'
      const res = await fetch(url, { method: 'POST' })
      const data = await res.json()

      if (data.success) {
        // Build readable diff report
        let report = data.message + '\n'
        if (data.changes && data.changes.length > 0) {
          report += '\n📋 Changes:\n'
          data.changes.forEach(c => {
            const from = typeof c.from === 'object' ? JSON.stringify(c.from) : String(c.from)
            const to = typeof c.to === 'object' ? JSON.stringify(c.to) : String(c.to)
            report += `  • [${c.category}] ${c.account || ''} ${c.field}: ${from} → ${to}\n`
          })
        }
        setResetNotification({ type: 'success', message: report, count: data.total_changes })

        // Refresh all setting states
        fetchHeavySettings()
        fetchMmLotSettings()
        fetchLsRatios()
        // Refresh runall state to pick up active_engines
        try {
          const stateRes = await fetch('/api/psfalgo/state')
          const stateData = await stateRes.json()
          if (stateData.active_engines) {
            setRunallState(prev => ({ ...prev, active_engines: stateData.active_engines }))
          }
        } catch (_) { }

        // Auto-dismiss after 8 seconds
        setTimeout(() => setResetNotification(null), 8000)
      } else {
        setResetNotification({ type: 'error', message: data.message || 'Reset failed', count: 0 })
        setTimeout(() => setResetNotification(null), 5000)
      }
    } catch (err) {
      setResetNotification({ type: 'error', message: `Reset error: ${err.message}`, count: 0 })
      setTimeout(() => setResetNotification(null), 5000)
    }
  }, [fetchHeavySettings, fetchMmLotSettings, fetchLsRatios])

  // Use BroadcastChannel to receive data from Scanner page (NO WebSocket)
  useEffect(() => {
    let broadcastChannel = null
    let pollingInterval = null

    try {
      broadcastChannel = new BroadcastChannel('market-data')
      setBcConnected(true)
      console.log('✅ PSFALGO: BroadcastChannel connected (Subscriber)')

      broadcastChannel.onmessage = (event) => {
        try {
          const message = event.data
          if (message.type === 'market_data_update') {
            // Update data with new market data from Scanner
            setData(prevData => {
              const dataMap = new Map(prevData.map(item => [item.PREF_IBKR, item]))

              // Update with new data
              message.data.forEach(update => {
                const key = update.PREF_IBKR || update.symbol
                if (key) {
                  dataMap.set(key, { ...dataMap.get(key), ...update })
                }
              })

              return Array.from(dataMap.values())
            })
          }
        } catch (err) {
          console.error('PSFALGO: Error parsing BroadcastChannel message:', err)
        }
      }

      broadcastChannel.onerror = (error) => {
        console.error('PSFALGO: BroadcastChannel error:', error)
        setBcConnected(false)
      }
    } catch (err) {
      console.warn('PSFALGO: BroadcastChannel not supported, falling back to REST polling:', err)
      setBcConnected(false)

      // Fallback: REST polling every 2 seconds
      setPollingActive(true)
      pollingInterval = setInterval(() => {
        fetchMergedData()
      }, 2000)
    }

    return () => {
      if (broadcastChannel) {
        broadcastChannel.close()
      }
      if (pollingInterval) {
        clearInterval(pollingInterval)
      }
    }
  }, [])

  // Fetch HEAVY modes + MM lot settings on mount
  useEffect(() => {
    fetchHeavyModes()
    fetchMmLotSettings()
    fetchLsRatios()
  }, [fetchHeavyModes, fetchMmLotSettings, fetchLsRatios])

  // 🟢 FAST PATH - Fetch FAST data (L1 + CSV, no tick-by-tick)
  const fetchMergedData = useCallback(async () => {
    try {
      // Use /fast/all instead of /merged for instant L1 data
      const response = await fetch('/api/market-data/fast/all')
      const result = await response.json()

      if (result.success && result.data && result.data.length > 0) {
        setData(result.data)
      }
    } catch (err) {
      console.error('PSFALGO: Error fetching data:', err)
    }
  }, [])

  // Hard refresh all PSFALGO data
  const refetchAllPSFALGO = useCallback(async () => {
    try {
      // 🟢 FAST PATH - Fetch FAST data
      const mergedResponse = await fetch('/api/market-data/fast/all')
      const mergedResult = await mergedResponse.json()
      if (mergedResult.success && mergedResult.data && mergedResult.data.length > 0) {
        setData(mergedResult.data)
      }

      // Trigger summary header refresh
      setSummaryRefreshTrigger(prev => prev + 1)
    } catch (err) {
      console.error('PSFALGO: Error refetching data:', err)
    }
  }, [])

  // Load data on mount
  useEffect(() => {
    fetchMergedData()
    // Refresh every 5 seconds
    const interval = setInterval(fetchMergedData, 5000)
    return () => clearInterval(interval)
  }, [fetchMergedData])

  // Fetch RUNALL state
  const fetchRunallState = useCallback(async () => {
    try {
      const response = await fetch('/api/psfalgo/state')
      const result = await response.json()

      if (result.success && result.state) {
        setRunallState(result.state)
        setRunallError(null)
      }
    } catch (err) {
      console.error('PSFALGO: Error fetching RUNALL state:', err)
      // Don't set error for network issues - RUNALL might not be initialized yet
    }
  }, [])

  // Poll RUNALL state
  useEffect(() => {
    fetchRunallState()
    const interval = setInterval(fetchRunallState, 4000) // Every 4 seconds
    return () => clearInterval(interval)
  }, [fetchRunallState])

  // Start RUNALL
  const handleStartRunall = async () => {
    setRunallLoading(true)
    setRunallError(null)
    try {
      const response = await fetch('/api/psfalgo/start', { method: 'POST' })
      const result = await response.json()

      if (result.success) {
        await fetchRunallState()
        setSummaryRefreshTrigger(prev => prev + 1)
      } else {
        setRunallError(result.detail || result.error || 'Failed to start RUNALL')
      }
    } catch (err) {
      console.error('PSFALGO: Error starting RUNALL:', err)
      setRunallError(err.message || 'Failed to start RUNALL')
    } finally {
      setRunallLoading(false)
    }
  }

  // Stop RUNALL
  const handleStopRunall = async () => {
    setRunallLoading(true)
    setRunallError(null)
    try {
      const response = await fetch('/api/psfalgo/stop', { method: 'POST' })
      const result = await response.json()

      if (result.success) {
        await fetchRunallState()
      } else {
        setRunallError(result.detail || result.error || 'Failed to stop RUNALL')
      }
    } catch (err) {
      console.error('PSFALGO: Error stopping RUNALL:', err)
      setRunallError(err.message || 'Failed to stop RUNALL')
    } finally {
      setRunallLoading(false)
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // XNL ENGINE FUNCTIONS
  // ═══════════════════════════════════════════════════════════════════════════

  // Fetch XNL state
  const fetchXnlState = useCallback(async () => {
    try {
      const response = await fetch('/api/xnl/state')
      const result = await response.json()
      if (result.state) {
        setXnlState(result)
      }
    } catch (err) {
      console.error('PSFALGO: Error fetching XNL state:', err)
    }
  }, [])

  // Poll XNL state
  useEffect(() => {
    fetchXnlState()
    const interval = setInterval(fetchXnlState, 3000)
    return () => clearInterval(interval)
  }, [fetchXnlState])

  // Dual Process: fetch state
  const fetchDualProcessState = useCallback(async () => {
    try {
      const response = await fetch('/api/xnl/dual-process/state')
      const data = await response.json()
      if (data && typeof data.state !== 'undefined') {
        setDualProcessState(prev => ({
          ...prev,
          state: data.state || 'STOPPED',
          account_a: data.account_a || prev.account_a,
          account_b: data.account_b || prev.account_b,
          current_account: data.current_account ?? null,
          loop_count: data.loop_count ?? 0,
          last_error: data.last_error ?? null
        }))
      }
    } catch (err) {
      console.error('PSFALGO: Error fetching Dual Process state:', err)
    }
  }, [])
  useEffect(() => {
    fetchDualProcessState()
    const interval = setInterval(fetchDualProcessState, 3000)
    return () => clearInterval(interval)
  }, [fetchDualProcessState])

  // Start XNL Engine
  const handleStartXnl = async () => {
    setXnlLoading(true)
    setXnlError(null)
    try {
      const response = await fetch('/api/xnl/start', { method: 'POST' })
      const result = await response.json()

      if (result.success) {
        await fetchXnlState()
        setSummaryRefreshTrigger(prev => prev + 1)
      } else {
        setXnlError(result.message || 'Failed to start XNL Engine')
      }
    } catch (err) {
      console.error('PSFALGO: Error starting XNL:', err)
      setXnlError(err.message || 'Failed to start XNL Engine')
    } finally {
      setXnlLoading(false)
    }
  }

  // Stop XNL Engine
  const handleStopXnl = async () => {
    setXnlLoading(true)
    setXnlError(null)
    try {
      const response = await fetch('/api/xnl/stop', { method: 'POST' })
      const result = await response.json()

      if (result.success) {
        await fetchXnlState()
      } else {
        setXnlError(result.message || 'Failed to stop XNL Engine')
      }
    } catch (err) {
      console.error('PSFALGO: Error stopping XNL:', err)
      setXnlError(err.message || 'Failed to stop XNL Engine')
    } finally {
      setXnlLoading(false)
    }
  }

  // Cancel by filter (incr, decr, sells, buys, lt, mm, tum) + rev_excluded
  const handleCancelByFilter = async (filterType) => {
    setCancelLoading(filterType)
    try {
      const response = await fetch('/api/xnl/cancel/filter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filter: filterType, rev_excluded: revExcluded })
      })
      const result = await response.json()
      if (result.success) {
        setXnlError(null)
        if (result.cancelled != null && result.cancelled > 0) {
          setSummaryRefreshTrigger((t) => t + 1)
        }
      } else if (result.cancelled === 0 && result.failed > 0) {
        setXnlError(result.message || `Failed to cancel (${filterType})`)
      }
      await fetchXnlState()
    } catch (err) {
      console.error('PSFALGO: Error cancelling by filter:', err)
      setXnlError(err.message)
    } finally {
      setCancelLoading(null)
    }
  }

  // Dual Process: start (IBKR_PED ↔ HAMPRO, 3.5 min front cycle per account)
  const handleStartDualProcess = async () => {
    setDualProcessLoading(true)
    setXnlError(null)
    try {
      const response = await fetch('/api/xnl/dual-process/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_a: ibkrAccount, account_b: 'HAMPRO' })
      })
      const result = await response.json()
      if (result.success) {
        setXnlError(null)
        await fetchDualProcessState()
      } else {
        setXnlError(result.message || 'Dual Process start failed')
      }
    } catch (err) {
      console.error('PSFALGO: Dual Process start error:', err)
      setXnlError(err.message || 'Dual Process start failed')
    } finally {
      setDualProcessLoading(false)
    }
  }
  const handleStopDualProcess = async () => {
    setDualProcessLoading(true)
    try {
      const response = await fetch('/api/xnl/dual-process/stop', { method: 'POST' })
      const result = await response.json()
      if (result.success) await fetchDualProcessState()
    } catch (err) {
      console.error('PSFALGO: Dual Process stop error:', err)
    } finally {
      setDualProcessLoading(false)
    }
  }

  // MinMax Area: compute and save minmaxarea.csv for all PREF IBKR symbols
  const [minmaxLoading, setMinmaxLoading] = useState(false)
  const handleMinMaxArea = async () => {
    setMinmaxLoading(true)
    setXnlError(null)
    try {
      const response = await fetch('/api/xnl/minmax-area', { method: 'POST' })
      const result = await response.json()
      if (result.success) {
        setXnlError(null)
        const msg = result.message || `MinMax Area: ${result.data?.row_count ?? 0} symbols → minmaxarea.csv`
        alert(msg)
      } else {
        setXnlError(result.message || 'MinMax Area failed')
      }
    } catch (err) {
      console.error('PSFALGO: MinMax Area error:', err)
      setXnlError(err.message || 'MinMax Area failed')
    } finally {
      setMinmaxLoading(false)
    }
  }

  // Get XNL state badge class
  const getXnlStateBadgeClass = () => {
    switch (xnlState.state) {
      case 'RUNNING':
        return 'running'
      case 'STARTING':
        return 'waiting'
      case 'STOPPING':
        return 'waiting'
      case 'STOPPED':
      default:
        return 'idle'
    }
  }

  // Get state badge color
  const getStateBadgeClass = () => {
    switch (runallState.global_state) {
      case 'RUNNING':
        return 'running'
      case 'WAITING':
        return 'waiting'
      case 'ERROR':
        return 'error'
      case 'BLOCKED':
        return 'blocked'
      default:
        return 'idle'
    }
  }

  // Toggle Engine Logic (Mutual Exclusivity)
  const toggleEngine = async (engineName, isChecked) => {
    // Default set if null/undefined
    let currentEngines = runallState.active_engines || ['LT_TRIM', 'KARBOTU', 'PATADD_ENGINE', 'ADDNEWPOS_ENGINE', 'MM_ENGINE'];
    let newEngines = [...currentEngines];

    if (isChecked) {
      if (!newEngines.includes(engineName)) newEngines.push(engineName);

      // Mutual Exclusivity: KARBOTU vs REDUCEMORE
      if (engineName === 'KARBOTU') {
        newEngines = newEngines.filter(e => e !== 'REDUCEMORE');
      } else if (engineName === 'REDUCEMORE') {
        newEngines = newEngines.filter(e => e !== 'KARBOTU');
      }
    } else {
      // Allow deselecting any engine
      newEngines = newEngines.filter(e => e !== engineName);
    }

    // Update Local State Optimistically
    setRunallState(prev => ({ ...prev, active_engines: newEngines }));

    // Send to Backend
    try {
      await fetch('/api/psfalgo/set-active-engines', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newEngines)
      });
      // Do NOT await fetchRunallState immediately to prevent race condition flickering.
      // The optimistic update is enough, the polling will eventually sync it.
    } catch (err) {
      console.error("Failed to set active engines:", err);
      // Revert on error if needed, but for now simple logging
    }
  }

  return (
    <div className="psfalgo-page">
      <header className="psfalgo-header">
        <div className="psfalgo-header-left">
          <Link to="/" className="back-to-scanner-link">
            ← Scanner
          </Link>
          <h1>🤖 PSFALGO - Position Management</h1>
          <Link to="/psfalgo-rules" className="rules-button">
            ⚙️ Set & Check Rules
          </Link>
        </div>
        <div className="psfalgo-header-right">
          <span className={`status-badge ${bcConnected ? 'connected' : 'disconnected'}`}>
            {bcConnected ? '🟢 BC Connected' : pollingActive ? '🔄 Polling' : '🔴 Disconnected'}
          </span>
          <button
            onClick={() => handleBaselineReset(null)}
            title="Reset ALL settings to baseline defaults"
            style={{
              background: 'rgba(251,191,36,0.15)', border: '1px solid rgba(251,191,36,0.3)',
              borderRadius: '3px', color: '#fbbf24', fontSize: '8px', padding: '2px 6px',
              cursor: 'pointer', marginLeft: '6px'
            }}
          >🔄 RESET ALL</button>
        </div>
      </header>

      {/* Reset Notification Toast */}
      {resetNotification && (
        <div style={{
          position: 'fixed', top: '12px', right: '12px', zIndex: 9999,
          background: resetNotification.type === 'success' ? 'rgba(16,24,39,0.97)' : 'rgba(127,29,29,0.97)',
          border: `1px solid ${resetNotification.type === 'success' ? '#22c55e' : '#ef4444'}`,
          borderRadius: '8px', padding: '12px 16px', maxWidth: '420px', minWidth: '280px',
          boxShadow: '0 8px 32px rgba(0,0,0,0.5)', backdropFilter: 'blur(8px)',
          fontFamily: 'monospace', fontSize: '11px', color: '#e2e8f0', lineHeight: '1.5'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '4px' }}>
            <span style={{ fontWeight: 'bold', color: resetNotification.type === 'success' ? '#4ade80' : '#f87171', fontSize: '12px' }}>
              {resetNotification.type === 'success' ? '✅ Baseline Reset' : '❌ Reset Error'}
            </span>
            <button onClick={() => setResetNotification(null)} style={{
              background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: '14px', padding: '0 0 0 8px'
            }}>×</button>
          </div>
          <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: '#cbd5e1', fontSize: '10px' }}>
            {resetNotification.message}
          </pre>
          {resetNotification.count > 0 && (
            <div style={{ marginTop: '6px', fontSize: '9px', color: '#94a3b8', borderTop: '1px solid #334155', paddingTop: '4px' }}>
              {resetNotification.count} setting{resetNotification.count !== 1 ? 's' : ''} restored to baseline
            </div>
          )}
        </div>
      )}

      {/* Live Data Status Bar - Shows live_data vs algo_ready */}
      <LiveDataStatusBar />

      {/* RUNALL Control Panel */}
      <div className="runall-control-panel">
        <div className="runall-status">
          <span className={`runall-state-badge ${getStateBadgeClass()}`}>
            {runallState.global_state === 'RUNNING' ? '🟢' :
              runallState.global_state === 'WAITING' ? '🟡' :
                runallState.global_state === 'ERROR' ? '🔴' :
                  runallState.global_state === 'BLOCKED' ? '🟠' : '⚪'}
            {' '}{runallState.global_state}
          </span>
          {runallState.loop_running && (
            <span className="runall-cycle-info">
              Cycle #{runallState.loop_count} | {runallState.cycle_state}
            </span>
          )}
          {runallState.dry_run_mode && (
            <span className="runall-dry-run-badge">DRY-RUN</span>
          )}
        </div>

        <div className="runall-engine-controls" style={{ display: 'flex', gap: '6px', alignItems: 'center', margin: '0 8px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '2px', cursor: 'pointer', color: '#e0e0e0', fontSize: '9px' }}>
            <input type="checkbox" checked={runallState.active_engines?.includes('LT_TRIM') ?? true} onChange={(e) => toggleEngine('LT_TRIM', e.target.checked)} style={{ width: '10px', height: '10px' }} />
            LT_TRIM
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '2px', cursor: 'pointer', color: '#e0e0e0', fontSize: '9px' }}>
            <input type="checkbox" checked={runallState.active_engines?.includes('KARBOTU') ?? true} onChange={(e) => toggleEngine('KARBOTU', e.target.checked)} style={{ width: '10px', height: '10px' }} />
            KARBOTU
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '2px', cursor: 'pointer', color: '#e0e0e0', fontSize: '9px' }}>
            <input type="checkbox" checked={runallState.active_engines?.includes('REDUCEMORE') ?? false} onChange={(e) => toggleEngine('REDUCEMORE', e.target.checked)} style={{ width: '10px', height: '10px' }} />
            REDUCEMORE
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '2px', cursor: 'pointer', color: '#c4b5fd', fontSize: '9px' }}>
            <input type="checkbox" checked={runallState.active_engines?.includes('PATADD_ENGINE') ?? true} onChange={(e) => toggleEngine('PATADD_ENGINE', e.target.checked)} style={{ width: '10px', height: '10px' }} />
            PATADD
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '2px', cursor: 'pointer', color: '#e0e0e0', fontSize: '9px' }}>
            <input type="checkbox" checked={runallState.active_engines?.includes('ADDNEWPOS_ENGINE') ?? true} onChange={(e) => toggleEngine('ADDNEWPOS_ENGINE', e.target.checked)} style={{ width: '10px', height: '10px' }} />
            ADDNEWPOS
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '2px', cursor: 'pointer', color: '#e0e0e0', fontSize: '9px' }}>
            <input type="checkbox" checked={runallState.active_engines?.includes('MM_ENGINE') ?? true} onChange={(e) => toggleEngine('MM_ENGINE', e.target.checked)} style={{ width: '10px', height: '10px' }} />
            MM_ENG
          </label>
          <button
            onClick={() => handleBaselineReset('active_engines')}
            style={{
              background: 'rgba(160,174,192,0.15)', border: '1px solid rgba(160,174,192,0.3)',
              borderRadius: '3px', color: '#a0aec0', fontSize: '7px', padding: '1px 4px',
              cursor: 'pointer', marginLeft: '2px'
            }}
          >↺</button>
        </div>

        {/* HEAVY Mode Controls - Account-Aware (3 accounts) */}
        <div className="heavy-mode-controls" style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
          margin: '0 8px',
          padding: '4px 6px',
          background: 'rgba(255, 69, 58, 0.10)',
          borderRadius: '4px',
          border: '1px solid rgba(255, 69, 58, 0.25)',
          minWidth: '320px'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: '#ff453a', fontSize: '9px', fontWeight: 'bold' }}>🔥 HEAVY MODE (Account-Specific)</span>
            <button
              onClick={() => handleBaselineReset('heavy')}
              style={{
                background: 'rgba(255,69,58,0.15)', border: '1px solid rgba(255,69,58,0.3)',
                borderRadius: '3px', color: '#ff453a', fontSize: '7px', padding: '1px 4px',
                cursor: 'pointer'
              }}
            >↺ Reset</button>
          </div>

          {HEAVY_ACCOUNTS.map(accId => {
            const settings = heavySettingsAll[accId] || {}
            const shortLabel = accId === 'HAMPRO' ? 'HAM' : accId === 'IBKR_PED' ? 'PED' : 'MAIN'
            const isActive = settings.heavy_long_dec || settings.heavy_short_dec

            return (
              <div key={accId} style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '2px 4px',
                background: isActive ? 'rgba(255, 159, 10, 0.15)' : 'transparent',
                borderRadius: '3px',
                borderLeft: isActive ? '2px solid #ff9f0a' : '2px solid transparent'
              }}>
                {/* Account Label */}
                <span style={{
                  color: isActive ? '#ff9f0a' : '#888',
                  fontSize: '8px',
                  fontWeight: 'bold',
                  width: '32px'
                }}>{shortLabel}</span>

                {/* LONGDEC checkbox */}
                <label style={{ display: 'flex', alignItems: 'center', gap: '2px', cursor: 'pointer', color: settings.heavy_long_dec ? '#4ade80' : '#666', fontSize: '8px' }}>
                  <input
                    type="checkbox"
                    checked={settings.heavy_long_dec ?? false}
                    onChange={(e) => updateAccountHeavySettings(accId, { heavy_long_dec: e.target.checked })}
                    style={{ width: '9px', height: '9px' }}
                  />
                  L
                </label>

                {/* SHORTDEC checkbox */}
                <label style={{ display: 'flex', alignItems: 'center', gap: '2px', cursor: 'pointer', color: settings.heavy_short_dec ? '#f87171' : '#666', fontSize: '8px' }}>
                  <input
                    type="checkbox"
                    checked={settings.heavy_short_dec ?? false}
                    onChange={(e) => updateAccountHeavySettings(accId, { heavy_short_dec: e.target.checked })}
                    style={{ width: '9px', height: '9px' }}
                  />
                  S
                </label>

                {/* Separator */}
                <span style={{ color: '#444', fontSize: '8px' }}>|</span>

                {/* Lot % */}
                <label style={{ display: 'flex', alignItems: 'center', gap: '1px', color: '#777', fontSize: '8px' }}>
                  %
                  <input
                    type="number"
                    min="1" max="100"
                    value={settings.heavy_lot_pct ?? 30}
                    onChange={(e) => {
                      const val = Math.max(1, Math.min(100, parseInt(e.target.value) || 30))
                      setHeavySettingsAll(prev => ({
                        ...prev,
                        [accId]: { ...prev[accId], heavy_lot_pct: val }
                      }))
                    }}
                    onBlur={() => updateAccountHeavySettings(accId, { heavy_lot_pct: settings.heavy_lot_pct })}
                    onKeyDown={(e) => e.key === 'Enter' && updateAccountHeavySettings(accId, { heavy_lot_pct: settings.heavy_lot_pct })}
                    style={{
                      width: '28px',
                      padding: '1px 2px',
                      fontSize: '8px',
                      background: '#1a1a1a',
                      border: '1px solid #333',
                      borderRadius: '2px',
                      color: '#ddd',
                      textAlign: 'center'
                    }}
                  />
                </label>

                {/* Long Threshold */}
                <label style={{ display: 'flex', alignItems: 'center', gap: '1px', color: '#4ade80', fontSize: '8px' }}>
                  L≥
                  <input
                    type="number"
                    step="0.01"
                    value={settings.heavy_long_threshold ?? 0.02}
                    onChange={(e) => {
                      const val = parseFloat(e.target.value) || 0.02
                      setHeavySettingsAll(prev => ({
                        ...prev,
                        [accId]: { ...prev[accId], heavy_long_threshold: val }
                      }))
                    }}
                    onBlur={() => updateAccountHeavySettings(accId, { heavy_long_threshold: settings.heavy_long_threshold })}
                    onKeyDown={(e) => e.key === 'Enter' && updateAccountHeavySettings(accId, { heavy_long_threshold: settings.heavy_long_threshold })}
                    style={{
                      width: '38px',
                      padding: '1px 2px',
                      fontSize: '8px',
                      background: '#1a1a1a',
                      border: '1px solid #333',
                      borderRadius: '2px',
                      color: '#4ade80',
                      textAlign: 'center'
                    }}
                  />
                </label>

                {/* Short Threshold */}
                <label style={{ display: 'flex', alignItems: 'center', gap: '1px', color: '#f87171', fontSize: '8px' }}>
                  S≤
                  <input
                    type="number"
                    step="0.01"
                    value={settings.heavy_short_threshold ?? -0.02}
                    onChange={(e) => {
                      const val = parseFloat(e.target.value) || -0.02
                      setHeavySettingsAll(prev => ({
                        ...prev,
                        [accId]: { ...prev[accId], heavy_short_threshold: val }
                      }))
                    }}
                    onBlur={() => updateAccountHeavySettings(accId, { heavy_short_threshold: settings.heavy_short_threshold })}
                    onKeyDown={(e) => e.key === 'Enter' && updateAccountHeavySettings(accId, { heavy_short_threshold: settings.heavy_short_threshold })}
                    style={{
                      width: '42px',
                      padding: '1px 2px',
                      fontSize: '8px',
                      background: '#1a1a1a',
                      border: '1px solid #333',
                      borderRadius: '2px',
                      color: '#f87171',
                      textAlign: 'center'
                    }}
                  />
                </label>
              </div>
            )
          })}
        </div>

        {/* MM Lot Mode Controls */}
        <div className="mm-lot-mode-controls" style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '3px',
          margin: '0 8px',
          padding: '4px 6px',
          background: 'rgba(14, 165, 233, 0.10)',
          borderRadius: '4px',
          border: '1px solid rgba(14, 165, 233, 0.25)',
          minWidth: '180px'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: '#0ea5e9', fontSize: '9px', fontWeight: 'bold' }}>📊 MM LOT MODE</span>
            <button
              onClick={() => handleBaselineReset('mm_settings')}
              style={{
                background: 'rgba(14,165,233,0.15)', border: '1px solid rgba(14,165,233,0.3)',
                borderRadius: '3px', color: '#0ea5e9', fontSize: '7px', padding: '1px 4px',
                cursor: 'pointer'
              }}
            >↺ Reset</button>
          </div>

          {/* Fixed Lot Radio */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <label style={{
              display: 'flex', alignItems: 'center', gap: '3px', cursor: 'pointer',
              color: mmLotSettings.lot_mode === 'fixed' ? '#4ade80' : '#666', fontSize: '9px',
              fontWeight: mmLotSettings.lot_mode === 'fixed' ? 'bold' : 'normal'
            }}>
              <input
                type="radio"
                name="mm-lot-mode"
                value="fixed"
                checked={mmLotSettings.lot_mode === 'fixed'}
                onChange={() => updateMmLotSettings({ lot_mode: 'fixed' })}
                style={{ width: '9px', height: '9px', accentColor: '#4ade80' }}
              />
              Fixed Lot
            </label>
            <input
              type="number"
              min="100"
              max="5000"
              step="100"
              value={mmLotSettings.lot_per_stock}
              onChange={(e) => {
                const val = Math.max(100, parseInt(e.target.value) || 200)
                setMmLotSettings(prev => ({ ...prev, lot_per_stock: val }))
              }}
              onBlur={() => updateMmLotSettings({ lot_per_stock: mmLotSettings.lot_per_stock })}
              onKeyDown={(e) => e.key === 'Enter' && updateMmLotSettings({ lot_per_stock: mmLotSettings.lot_per_stock })}
              disabled={mmLotSettings.lot_mode !== 'fixed'}
              style={{
                width: '42px',
                padding: '1px 3px',
                fontSize: '9px',
                background: mmLotSettings.lot_mode === 'fixed' ? '#1a1a1a' : '#111',
                border: '1px solid ' + (mmLotSettings.lot_mode === 'fixed' ? '#444' : '#222'),
                borderRadius: '2px',
                color: mmLotSettings.lot_mode === 'fixed' ? '#4ade80' : '#555',
                textAlign: 'center',
                opacity: mmLotSettings.lot_mode === 'fixed' ? 1 : 0.5
              }}
            />
          </div>

          {/* AVG ADV Adjuster Radio */}
          <label style={{
            display: 'flex', alignItems: 'center', gap: '3px', cursor: 'pointer',
            color: mmLotSettings.lot_mode === 'adv_adjust' ? '#fbbf24' : '#666', fontSize: '9px',
            fontWeight: mmLotSettings.lot_mode === 'adv_adjust' ? 'bold' : 'normal'
          }}>
            <input
              type="radio"
              name="mm-lot-mode"
              value="adv_adjust"
              checked={mmLotSettings.lot_mode === 'adv_adjust'}
              onChange={() => updateMmLotSettings({ lot_mode: 'adv_adjust' })}
              style={{ width: '9px', height: '9px', accentColor: '#fbbf24' }}
            />
            AVG ADV Adjuster
            <span style={{
              fontSize: '7px',
              color: '#888',
              marginLeft: '2px'
            }}>(Free Exp Tiers)</span>
          </label>
        </div>

        {/* INCREASE L/S SETTINGS — Per-Engine Long/Short Allocation */}
        <div className="ls-ratio-controls" style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '3px',
          margin: '0 8px',
          padding: '4px 6px',
          background: 'rgba(168, 85, 247, 0.10)',
          borderRadius: '4px',
          border: '1px solid rgba(168, 85, 247, 0.25)',
          minWidth: '200px'
        }}>
          <span style={{ color: '#a855f7', fontSize: '9px', fontWeight: 'bold' }}>⚖️ INCREASE L/S SETTINGS</span>
          {[
            { key: 'MM_ENGINE', label: 'MM' },
            { key: 'PATADD_ENGINE', label: 'PATADD' },
            { key: 'ADDNEWPOS_ENGINE', label: 'ADDNP' },
          ].map(({ key, label }) => {
            const ratio = lsRatios[key] || { long_pct: 50, short_pct: 50 }
            return (
              <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <span style={{ color: '#a0aec0', fontSize: '8px', fontWeight: 'bold', width: '38px' }}>{label}</span>
                <label style={{ display: 'flex', alignItems: 'center', gap: '1px', color: '#4ade80', fontSize: '8px' }}>
                  L
                  <input
                    type="number"
                    min="0" max="100" step="5"
                    value={ratio.long_pct}
                    onChange={(e) => {
                      const val = Math.max(0, Math.min(100, parseInt(e.target.value) || 50))
                      setLsRatios(prev => ({
                        ...prev,
                        [key]: { long_pct: val, short_pct: 100 - val }
                      }))
                    }}
                    onBlur={() => updateLsRatio(key, ratio.long_pct)}
                    onKeyDown={(e) => e.key === 'Enter' && updateLsRatio(key, ratio.long_pct)}
                    style={{
                      width: '30px', padding: '1px 2px', fontSize: '8px',
                      background: '#1a1a1a', border: '1px solid #333',
                      borderRadius: '2px', color: '#4ade80', textAlign: 'center'
                    }}
                  />
                </label>
                <span style={{ color: '#555', fontSize: '8px' }}>/</span>
                <label style={{ display: 'flex', alignItems: 'center', gap: '1px', color: '#f87171', fontSize: '8px' }}>
                  S
                  <span style={{
                    display: 'inline-block', width: '24px', textAlign: 'center',
                    fontSize: '8px', color: '#f87171', fontWeight: 'bold'
                  }}>{ratio.short_pct}</span>
                </label>
                {/* Visual bar */}
                <div style={{
                  flex: 1, height: '4px', borderRadius: '2px',
                  background: '#1a1a1a', overflow: 'hidden', minWidth: '40px'
                }}>
                  <div style={{
                    width: `${ratio.long_pct}%`, height: '100%',
                    background: ratio.long_pct === 50
                      ? 'linear-gradient(90deg, #4ade80, #fbbf24)'
                      : ratio.long_pct > 50
                        ? 'linear-gradient(90deg, #4ade80, #22c55e)'
                        : 'linear-gradient(90deg, #f87171, #ef4444)',
                    borderRadius: '2px', transition: 'width 0.2s ease'
                  }} />
                </div>
              </div>
            )
          })}
        </div>

        <div className="runall-controls">
          {!runallState.loop_running ? (
            <button
              className="runall-start-btn"
              onClick={handleStartRunall}
              disabled={runallLoading}
            >
              {runallLoading ? '⏳ Starting...' : '▶️ Start RUNALL'}
            </button>
          ) : (
            <button
              className="runall-stop-btn"
              onClick={handleStopRunall}
              disabled={runallLoading}
            >
              {runallLoading ? '⏳ Stopping...' : '⏹️ Stop RUNALL'}
            </button>
          )}

          {/* XNL Engine Toggle Button */}
          <div className="xnl-divider" style={{ width: '1px', height: '16px', backgroundColor: '#4a5568', margin: '0 4px' }} />

          {xnlState.state !== 'RUNNING' && xnlState.state !== 'STARTING' ? (
            <button className="xnl-start-btn" onClick={handleStartXnl} disabled={xnlLoading}
              style={{ background: 'linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)', color: 'white', border: 'none', padding: '3px 8px', borderRadius: '3px', cursor: 'pointer', fontWeight: 'bold', fontSize: '10px', display: 'flex', alignItems: 'center', gap: '2px' }}
              title="Start XNL Engine">
              {xnlLoading ? '⏳' : '🚀'} XNL
            </button>
          ) : (
            <button className="xnl-stop-btn" onClick={handleStopXnl} disabled={false}
              style={{ background: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)', color: 'white', border: 'none', padding: '3px 8px', borderRadius: '3px', cursor: 'pointer', fontWeight: 'bold', fontSize: '10px', display: 'flex', alignItems: 'center', gap: '2px' }}
              title="Stop XNL Engine (always clickable when running)">
              {xnlLoading ? '⏳' : '⏹️'} XNL
            </button>
          )}

          {/* MinMax Area: compute todays min/max qty per symbol → minmaxarea.csv */}
          <button
            type="button"
            className="xnl-start-btn"
            onClick={handleMinMaxArea}
            disabled={minmaxLoading}
            title="Compute MinMax Area for all PREF IBKR symbols and save to minmaxarea.csv"
            style={{ marginLeft: '4px' }}
          >
            {minmaxLoading ? '⏳' : '📐'} MinMax Area
          </button>
          {/* Dual Process: alternate XNL between selected IBKR account and HAMPRO */}
          <div className="xnl-divider" style={{ width: '1px', height: '16px', backgroundColor: '#4a5568', margin: '0 4px' }} />
          {/* IBKR Account Selector for Dual Process */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '3px', marginRight: '4px', padding: '2px 5px', background: 'rgba(124, 58, 237, 0.12)', borderRadius: '4px', border: '1px solid rgba(124, 58, 237, 0.25)' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '2px', cursor: dualProcessState.state === 'RUNNING' ? 'not-allowed' : 'pointer', color: ibkrAccount === 'IBKR_PED' ? '#a78bfa' : '#666', fontSize: '8px', fontWeight: ibkrAccount === 'IBKR_PED' ? 'bold' : 'normal' }}>
              <input
                type="radio"
                name="ibkr-account-psfalgo"
                value="IBKR_PED"
                checked={ibkrAccount === 'IBKR_PED'}
                onChange={() => { setIbkrAccount('IBKR_PED'); localStorage.setItem('dual_process_ibkr_account', 'IBKR_PED') }}
                disabled={dualProcessState.state === 'RUNNING'}
                style={{ width: '9px', height: '9px', accentColor: '#7c3aed' }}
              />
              PED
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '2px', cursor: dualProcessState.state === 'RUNNING' ? 'not-allowed' : 'pointer', color: ibkrAccount === 'IBKR_GUN' ? '#a78bfa' : '#666', fontSize: '8px', fontWeight: ibkrAccount === 'IBKR_GUN' ? 'bold' : 'normal' }}>
              <input
                type="radio"
                name="ibkr-account-psfalgo"
                value="IBKR_GUN"
                checked={ibkrAccount === 'IBKR_GUN'}
                onChange={() => { setIbkrAccount('IBKR_GUN'); localStorage.setItem('dual_process_ibkr_account', 'IBKR_GUN') }}
                disabled={dualProcessState.state === 'RUNNING'}
                style={{ width: '9px', height: '9px', accentColor: '#7c3aed' }}
              />
              GUN
            </label>
          </div>
          {(dualProcessState.state !== 'RUNNING' && dualProcessState.state !== 'STOPPING') ? (
            <button
              type="button"
              className="xnl-start-btn"
              onClick={handleStartDualProcess}
              disabled={dualProcessLoading}
              title={`Start Dual Process: XNL alternates between ${ibkrAccount} and HAMPRO (3.5 min per account)`}
              style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #5b21b6 100%)', color: 'white' }}
            >
              {dualProcessLoading ? '⏳' : '🔄'} Dual Process
            </button>
          ) : (
            <button
              type="button"
              className="xnl-stop-btn"
              onClick={handleStopDualProcess}
              disabled={dualProcessLoading}
              title="Stop Dual Process (will halt after current step)"
              style={{ background: 'linear-gradient(135deg, #dc2626 0%, #b91c1c 100%)', color: 'white' }}
            >
              {dualProcessLoading ? '⏳' : '⏹️'} Dual Process
            </button>
          )}
          {dualProcessState.state === 'RUNNING' && (
            <span className="xnl-state-badge" style={{ fontSize: '8px', color: '#a0aec0', marginLeft: '4px' }}>
              {dualProcessState.current_account || '—'} | #{dualProcessState.loop_count}
            </span>
          )}
          {/* XNL State Badge */}
          <span className={`xnl-state-badge ${getXnlStateBadgeClass()}`}
            style={{
              padding: '2px 5px', borderRadius: '3px', fontSize: '8px', fontWeight: '600', textTransform: 'uppercase',
              backgroundColor: xnlState.state === 'RUNNING' ? '#22543d' : xnlState.state === 'STOPPING' ? '#744210' : '#2d3748',
              color: xnlState.state === 'RUNNING' ? '#68d391' : xnlState.state === 'STOPPING' ? '#f6e05e' : '#a0aec0'
            }}>
            {xnlState.state === 'RUNNING' ? '🟢' : xnlState.state === 'STOPPING' ? '⏳' : '⚪'} {xnlState.state}
          </span>

          {/* Cancel by filter: c incr, c decr, c sells, c buys, c lt, c mm, c TUM + rev excluded checkbox */}
          <div className="cancel-divider" style={{ width: '1px', height: '16px', backgroundColor: '#4a5568', margin: '0 4px' }} />
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '9px', color: '#a0aec0', marginRight: '6px' }}>
            <input type="checkbox" checked={revExcluded} onChange={(e) => { setRevExcluded(e.target.checked); localStorage.setItem('rev_excluded', String(e.target.checked)) }} />
            rev excluded
          </label>
          {['incr', 'decr', 'sells', 'buys', 'lt', 'mm', 'tum'].map((f) => (
            <button key={f} className={`cancel-filter-btn cancel-${f}`} onClick={() => handleCancelByFilter(f)} disabled={cancelLoading !== null}
              style={{ background: f === 'tum' ? 'linear-gradient(135deg, #dc2626 0%, #b91c1c 100%)' : '#4a5568', color: 'white', border: 'none', padding: '3px 6px', borderRadius: '3px', cursor: 'pointer', fontWeight: 'bold', fontSize: '9px' }}
              title={f === 'tum' ? 'Cancel ALL orders' : f === 'incr' ? 'Cancel increase-tag orders' : f === 'decr' ? 'Cancel decrease-tag orders' : f === 'sells' ? 'Cancel all SELL' : f === 'buys' ? 'Cancel all BUY' : f === 'lt' ? 'Cancel LT-tag orders' : 'Cancel MM-tag orders'}>
              {cancelLoading === f ? '⏳' : 'c'} {f === 'tum' ? 'TUM' : f}
            </button>
          ))}

          <div className="link-divider" style={{ width: '1px', height: '16px', backgroundColor: '#4a5568', margin: '0 4px' }} />

          <Link to="/psfalgo-intentions" className="intentions-link-btn">
            📋 View Intentions
          </Link>

          {/* New Diagnostic Buttons */}
          <Link
            to="/port-adjuster"
            className="psfalgo-link-button"
            style={{ backgroundColor: '#20c997', color: 'white', border: 'none', padding: '3px 8px', borderRadius: '3px', cursor: 'pointer', fontWeight: 'bold', fontSize: '9px', textDecoration: 'none', display: 'inline-block' }}
            title="Open Port Adjuster"
          >
            📐 Port Adjuster
          </Link>
          <button className="genexpo-btn" onClick={() => setShowGenExpo(true)}
            style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #5b21b6 100%)', color: 'white', border: 'none', padding: '3px 8px', borderRadius: '3px', cursor: 'pointer', fontWeight: 'bold', fontSize: '9px' }}
            title="GenExpo Limiter - Account-Aware Exposure & ADDNEWPOS Settings">
            🎚️ GenExpo Limiter
          </button>
          <button className="simulation-btn" onClick={() => setShowSimulation(true)}
            style={{ backgroundColor: '#fd7e14', color: 'white', border: 'none', padding: '3px 8px', borderRadius: '3px', cursor: 'pointer', fontWeight: 'bold', fontSize: '9px' }}
            title="Open 10 Min Later Simulation">
            🎭 Sim
          </button>
          <button className="report-btn" onClick={() => setShowReport(true)}
            style={{ backgroundColor: '#6f42c1', color: 'white', border: 'none', padding: '3px 8px', borderRadius: '3px', cursor: 'pointer', fontWeight: 'bold', fontSize: '9px' }}
            title="Open Universal Decision Compass">
            🧭 Report
          </button>
          <button className="rev-orders-btn" onClick={() => setShowRevOrders(true)}
            style={{ background: 'linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)', color: 'white', border: 'none', padding: '3px 8px', borderRadius: '3px', cursor: 'pointer', fontWeight: 'bold', fontSize: '9px' }}
            title="View Active REV Orders">
            🔄 REV Orders
          </button>
        </div>

        {runallError && (
          <div className="runall-error">
            ⚠️ {runallError}
          </div>
        )}

        {xnlError && (
          <div className="xnl-error" style={{ color: '#fc8181', fontSize: '9px', marginTop: '2px', padding: '2px 6px', backgroundColor: '#742a2a', borderRadius: '3px' }}>
            ⚠️ XNL: {xnlError}
          </div>
        )}

        {runallState.last_error && (
          <div className="runall-last-error">
            Last Error: {runallState.last_error}
          </div>
        )}
      </div>

      {/* Summary Header */}
      <PSFALGOSummaryHeader onRefresh={summaryRefreshTrigger} />

      {/* Engine Diagnostic Panel */}
      <EngineStatusPanel />

      {/* ADDNEWPOS Settings Panel (XNL Engine) */}
      <AddnewposSettingsPanel />

      {/* Proposal Tab System - 4 Tabs: LT TRIM | ADDNEWPOS | KARBOTU | REDUCEMORE */}
      <ProposalTabSystem wsConnected={bcConnected} />

      {/* Tab Navigation */}
      <div className="psfalgo-tabs">
        <button
          className={`psfalgo-tab-btn ${activeTab === 'positions' ? 'active' : ''}`}
          onClick={() => setActiveTab('positions')}
        >
          Positions
        </button>
        <button
          className={`psfalgo-tab-btn ${activeTab === 'longs' ? 'active' : ''}`}
          onClick={() => setActiveTab('longs')}
        >
          Take Profit Longs
        </button>
        <button
          className={`psfalgo-tab-btn ${activeTab === 'shorts' ? 'active' : ''}`}
          onClick={() => setActiveTab('shorts')}
        >
          Take Profit Shorts
        </button>
      </div>

      <div className="psfalgo-content">
        {activeTab === 'positions' && (
          <PSFALGOBulkActionPanel
            data={data}
            onLedgerUpdate={refetchAllPSFALGO}
            onCycleUpdate={refetchAllPSFALGO}
          />
        )}
        {activeTab === 'longs' && <TakeProfitLongsTab />}
        {activeTab === 'shorts' && <TakeProfitShortsTab />}
      </div>

      <TradingPanelsOverlay
        isOpen={overlayOpen}
        onClose={() => setOverlayOpen(false)}
        tradingMode={tradingMode}
        panelType={overlayPanelType}
      />

      {/* Simulation Panel Modal */}
      {
        showSimulation && (
          <div style={{
            position: 'fixed',
            top: '10%',
            left: '20%',
            width: '60%',
            maxHeight: '80%',
            overflowY: 'auto',
            backgroundColor: '#1b263b',
            zIndex: 2000,
            boxShadow: '0 0 20px rgba(0,0,0,0.6)',
            borderRadius: '12px',
            padding: '10px',
            border: '1px solid #444'
          }}>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '10px' }}>
              <button
                onClick={() => setShowSimulation(false)}
                style={{ background: 'none', border: 'none', color: '#fff', fontSize: '1.2rem', cursor: 'pointer' }}
              >
                ❌ Close
              </button>
            </div>
            <SimulationPanel />
          </div>
        )
      }

      {/* Universal Report Modal */}
      {
        showReport && (
          <div style={{
            position: 'fixed',
            top: '5%',
            left: '5%',
            width: '90%',
            height: '90%',
            backgroundColor: '#1e1e1e',
            zIndex: 2000,
            boxShadow: '0 0 20px rgba(0,0,0,0.5)',
            borderRadius: '8px',
            display: 'flex',
            flexDirection: 'column'
          }}>
            <div style={{ padding: '10px', textAlign: 'right', borderBottom: '1px solid #333' }}>
              <button
                onClick={() => setShowReport(false)}
                style={{ background: 'none', border: 'none', color: '#fff', fontSize: '1.2rem', cursor: 'pointer' }}
              >
                ❌ Close
              </button>
            </div>
            <div style={{ flex: 1, overflow: 'hidden' }}>
              <KarbotuDiagnostic />
            </div>
          </div>
        )
      }

      {/* GenExpo Limiter Modal */}
      <GenExpoLimiterModal isOpen={showGenExpo} onClose={() => setShowGenExpo(false)} />

      {/* REV Orders Modal */}
      <RevOrdersModal isOpen={showRevOrders} onClose={() => setShowRevOrders(false)} />
    </div >
  )
}

export default PSFALGOPage

