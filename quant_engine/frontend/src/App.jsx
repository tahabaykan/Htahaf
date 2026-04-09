import React, { useState, useEffect, useCallback, useMemo } from 'react'
import ScannerTable from './components/ScannerTable'
import ControlBar from './components/ControlBar'
import StateReasonInspector from './components/StateReasonInspector'
import PSFALGOBulkActionPanel from './components/PSFALGOBulkActionPanel'
import ETFStrip from './components/ETFStrip'
import TradingAccountSelector from './components/TradingAccountSelector'
import AccountSidebar from './components/AccountSidebar'
import TradingPanelsOverlay from './components/TradingPanelsOverlay'
import GroupSelector from './components/GroupSelector'
import GroupContextBar from './components/GroupContextBar'
import RejectedCandidates from './components/RejectedCandidates'
import GemProposalsPanel from './components/GemProposalsPanel'
import GenobsPanel from './components/GenobsPanel'
import BenchmarkFillsPanel from './components/BenchmarkFillsPanel'
import SimulationPanel from './components/SimulationPanel'
import FakeOrdersList from './components/FakeOrdersList'
import KarbotuDiagnostic from './components/KarbotuDiagnostic'
import ExcludedListModal from './components/ExcludedListModal'
import PatternSuggestionsModal from './components/PatternSuggestionsModal'
import ExDivPlanPanel from './components/ExDivPlanPanel'
import AdminPanel from './pages/AdminPanel'
import './App.css'

function App() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [wsConnected, setWsConnected] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [filter, setFilter] = useState('')
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' })
  const [selectedRow, setSelectedRow] = useState(null)

  // Advanced filters
  const [stateFilter, setStateFilter] = useState(['IDLE', 'WATCH', 'CANDIDATE'])
  const [spreadMax, setSpreadMax] = useState('')
  const [avgAdvMin, setAvgAdvMin] = useState('')
  const [finalThgMin, setFinalThgMin] = useState('')
  const [shortFinalMin, setShortFinalMin] = useState('')

  // Focus Mode
  const [focusMode, setFocusMode] = useState(false)

  // Execution Mode
  const [executionMode, setExecutionMode] = useState('PREVIEW')
  const [executionModeInitialized, setExecutionModeInitialized] = useState(false)

  // Trading Account Mode
  const [tradingMode, setTradingMode] = useState('HAMMER_PRO')

  // Trading Panels Overlay
  const [overlayOpen, setOverlayOpen] = useState(false)
  const [overlayPanelType, setOverlayPanelType] = useState('positions')

  // Group Navigation
  const [selectedGroup, setSelectedGroup] = useState(null)
  const [selectedCgrup, setSelectedCgrup] = useState(null)

  // Rejected Candidates Panel & Excluded List
  const [showRejected, setShowRejected] = useState(false)
  const [showGemProposals, setShowGemProposals] = useState(false)
  const [showGenobs, setShowGenobs] = useState(false) // New Genobs Panel
  const [showBenchmarkFills, setShowBenchmarkFills] = useState(false)
  const [showSimulation, setShowSimulation] = useState(false) // Simulation Panel
  const [showKarbotuDebug, setShowKarbotuDebug] = useState(false) // KARBOTU Debug
  const [showExcludedList, setShowExcludedList] = useState(false) // Excluded List Modal
  const [showPatternSuggestions, setShowPatternSuggestions] = useState(false) // Pattern Suggestions Modal
  const [showExDivPlan, setShowExDivPlan] = useState(false) // Ex-Div 30 Day Plan
  const [showTSSScreen, setShowTSSScreen] = useState(false) // TSS - RTS Screen
  const [tssData, setTssData] = useState(null) // TSS v2 data
  const [showAdminPanel, setShowAdminPanel] = useState(false) // Admin Panel

  // Read group filter from URL parameters
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const groupParam = params.get('group')
    const cgrupParam = params.get('cgrup')

    if (groupParam) {
      setSelectedGroup(groupParam.toLowerCase())
      if (cgrupParam) {
        setSelectedCgrup(cgrupParam.toLowerCase())
      } else {
        setSelectedCgrup(null)
      }
    } else {
      setSelectedGroup(null)
      setSelectedCgrup(null)
    }
  }, [])

  // Auto BEFDAY capture: HammerPro 10 seconds after app loads
  useEffect(() => {
    const timer = setTimeout(async () => {
      try {
        const response = await fetch('/api/befday/capture/ham', { method: 'POST' })
        const result = await response.json()
        if (result.success) {
          if (result.already_captured) {
            console.log('📋 [BEFDAY] HammerPro already captured today')
          } else {
            console.log(`📋 [BEFDAY] HammerPro captured: ${result.position_count} positions`)
          }
        }
      } catch (err) {
        console.warn('[BEFDAY] Auto-capture failed:', err)
      }
    }, 10000) // 10 seconds after load

    return () => clearTimeout(timer)
  }, [])

  // Load execution mode on mount
  useEffect(() => {
    fetch('/api/market-data/execution/mode')
      .then(res => res.json())
      .then(data => {
        if (data.success && data.mode) {
          setExecutionMode(data.mode)
        }
        setExecutionModeInitialized(true)
      })
      .catch(err => {
        console.error('Error loading execution mode:', err)
        setExecutionModeInitialized(true)
      })
  }, [])

  // Save execution mode when changed by user (not on initial load)
  const handleExecutionModeChange = useCallback((newMode) => {
    setExecutionMode(newMode)
    if (executionModeInitialized) {
      fetch('/api/market-data/execution/mode', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ mode: newMode }),
      })
        .then(res => res.json())
        .then(data => {
          if (data.success) {
            console.log(`Execution mode set to: ${data.mode}`)
          }
        })
        .catch(err => console.error('Error setting execution mode:', err))
    }
  }, [executionModeInitialized])

  // Lifeless Mode (Cansız Veri)
  const [lifelessMode, setLifelessMode] = useState(false)

  // Poll Lifeless Mode status
  useEffect(() => {
    const checkStatus = async () => {
      try {
        const res = await fetch('/api/system/status')
        const data = await res.json()
        if (data.status === 'ok') {
          setLifelessMode(data.lifeless_mode)
        }
      } catch (err) {
        console.error('Error checking system status:', err)
      }
    }

    checkStatus() // check immediately
    const interval = setInterval(checkStatus, 5000) // check every 5s
    return () => clearInterval(interval)
  }, [])

  const toggleLifelessMode = async () => {
    try {
      const newMode = !lifelessMode
      const res = await fetch('/api/system/mode/lifeless', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: newMode })
      })
      const data = await res.json()
      if (data.status === 'success') {
        setLifelessMode(newMode)
        console.log(`💀 Lifeless Mode ${newMode ? 'ENABLED' : 'DISABLED'}`)
      } else {
        console.error('Failed to toggle Lifeless Mode:', data)
      }
    } catch (err) {
      console.error('Error toggling Lifeless Mode:', err)
    }
  }

  const handleShuffle = async () => {
    try {
      const res = await fetch('/api/system/mode/lifeless/shuffle', { method: 'POST' })
      const data = await res.json()
      if (data.status === 'success') {
        console.log(`🎲 Shuffled ${data.shuffled_count} symbols`)
      } else {
        console.error('Shuffle failed:', data)
      }
    } catch (err) {
      console.error('Error shuffling:', err)
    }
  }

  // WebSocket connection
  useEffect(() => {
    const ws = new WebSocket('ws://localhost:3000/ws')

    ws.onopen = () => {
      console.log('WebSocket connected')
      setWsConnected(true)
    }

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        if (message.type === 'market_data_update') {
          // Update data with new market data
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
        } else if (message.type === 'pong') {
          // Heartbeat response
        }
      } catch (err) {
        console.error('Error parsing WebSocket message:', err)
      }
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      setWsConnected(false)
    }

    ws.onclose = () => {
      console.log('WebSocket disconnected')
      setWsConnected(false)
    }

    // Send ping every 30 seconds
    const pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000)

    return () => {
      clearInterval(pingInterval)
      ws.close()
    }
  }, [])

  // Load CSV data
  const loadCsv = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch('/api/market-data/load-csv', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      })

      if (!response.ok) {
        // Check if backend is reachable
        if (response.status === 0 || response.status >= 500) {
          throw new Error(`Backend connection failed. Make sure backend is running on http://localhost:8000`)
        }
        const errorText = await response.text()
        throw new Error(`HTTP ${response.status}: ${errorText || 'Unknown error'}`)
      }

      const result = await response.json()

      if (result.success) {
        // After loading CSV, fetch merged data
        await fetchMergedData()
      } else {
        setError(result.message || result.detail || 'Failed to load CSV')
      }
    } catch (err) {
      console.error('CSV load error:', err)
      if (err.message.includes('Failed to fetch') || err.message.includes('NetworkError')) {
        setError(`Backend connection failed. Make sure backend is running on http://localhost:8000. Error: ${err.message}`)
      } else {
        setError(`Error loading CSV: ${err.message}`)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  // Fetch merged data
  // 🟢 FAST PATH - Fetch FAST data (L1 + CSV, no tick-by-tick)
  const fetchMergedData = useCallback(async () => {
    try {
      // Use /fast/all instead of /merged for instant L1 data
      const response = await fetch('/api/market-data/fast/all')

      if (!response.ok) {
        // Check if backend is reachable
        if (response.status === 0 || response.status >= 500) {
          throw new Error(`Backend connection failed. Make sure backend is running on http://localhost:8000`)
        }
        const errorText = await response.text()
        throw new Error(`HTTP ${response.status}: ${errorText || 'Unknown error'}`)
      }

      const result = await response.json()

      console.log('Fetched merged data:', result.success, 'count:', result.count, 'data length:', result.data?.length)

      if (result.success) {
        if (result.data && result.data.length > 0) {
          console.log('Setting data, first item:', result.data[0])
          try {
            setData(result.data)
            console.log('Data set successfully, length:', result.data.length)
            setError(null) // Clear any previous errors
          } catch (err) {
            console.error('Error setting data:', err)
            setError(`Error setting data: ${err.message}`)
          }
        } else {
          console.warn('No data in response, result:', result)
          setData([])
          if (!result.success) {
            setError(result.message || result.detail || 'No data available')
          }
        }
      } else {
        console.error('Failed to fetch merged data:', result)
        setError(result.message || result.detail || 'Failed to fetch merged data')
      }
    } catch (err) {
      console.error('Error fetching data:', err)
      if (err.message.includes('Failed to fetch') || err.message.includes('NetworkError')) {
        setError(`Backend connection failed. Make sure backend is running on http://localhost:8000. Error: ${err.message}`)
      } else {
        setError(`Error fetching data: ${err.message}`)
      }
    }
  }, [])

  // Auto refresh
  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(fetchMergedData, 2000)
      return () => clearInterval(interval)
    }
  }, [autoRefresh, fetchMergedData])

  // Calculate counters
  const counters = useMemo(() => {
    const total = data.length
    const watch = data.filter(item => item.state === 'WATCH').length
    const candidate = data.filter(item => item.state === 'CANDIDATE').length
    return { total, watch, candidate }
  }, [data])

  // Filter and sort data
  const filteredAndSortedData = useMemo(() => {
    let filtered = data

    console.log('Filtering data:', {
      total: data.length,
      focusMode,
      stateFilter,
      filter,
      spreadMax,
      avgAdvMin,
      finalThgMin,
      shortFinalMin
    })

    // Apply Focus Mode
    if (focusMode) {
      filtered = filtered.filter(item =>
        item.state === 'WATCH' || item.state === 'CANDIDATE'
      )
      console.log('After focus mode:', filtered.length)
    }

    // Apply state filter
    if (stateFilter.length > 0 && stateFilter.length < 3) {
      const before = filtered.length
      filtered = filtered.filter(item => stateFilter.includes(item.state))
      console.log('After state filter:', before, '->', filtered.length, 'stateFilter:', stateFilter)
    }

    // Apply group filter (PRIMARY GROUP + SECONDARY GROUP for kuponlu groups)
    if (selectedGroup) {
      const kuponluGroups = ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']
      filtered = filtered.filter(item => {
        const itemGroup = (item.GROUP || item.group || item.file_group)?.toLowerCase()
        if (itemGroup !== selectedGroup) return false

        // Kuponlu gruplar için CGRUP kontrolü
        if (kuponluGroups.includes(selectedGroup)) {
          if (selectedCgrup) {
            // Belirli CGRUP seçildiyse
            return item.CGRUP?.toUpperCase() === selectedCgrup
          } else {
            // CGRUP seçilmediyse, CGRUP'u olmayanları göster
            return !item.CGRUP || item.CGRUP === '' || item.CGRUP === 'N/A'
          }
        }
        // Diğer gruplar için CGRUP ignore edilir
        return true
      })
    }

    // Apply text filter
    if (filter) {
      const filterLower = filter.toLowerCase()
      filtered = filtered.filter(item =>
        item.PREF_IBKR?.toLowerCase().includes(filterLower) ||
        item.CMON?.toLowerCase().includes(filterLower) ||
        item.CGRUP?.toLowerCase().includes(filterLower)
      )
    }

    // Apply numeric filters
    if (spreadMax) {
      const max = parseFloat(spreadMax)
      if (!isNaN(max)) {
        filtered = filtered.filter(item => {
          // Spread is in cents (ask - bid), convert max from cents
          const spread = parseFloat(item.spread) || (item.ask && item.bid ? item.ask - item.bid : 0)
          return isNaN(spread) || spread <= max
        })
      }
    }

    if (avgAdvMin) {
      const min = parseFloat(avgAdvMin)
      if (!isNaN(min)) {
        filtered = filtered.filter(item => {
          const adv = parseFloat(item.AVG_ADV)
          return isNaN(adv) || adv >= min
        })
      }
    }

    if (finalThgMin) {
      const min = parseFloat(finalThgMin)
      if (!isNaN(min)) {
        filtered = filtered.filter(item => {
          const thg = parseFloat(item.FINAL_THG)
          return isNaN(thg) || thg >= min
        })
      }
    }

    if (shortFinalMin) {
      const min = parseFloat(shortFinalMin)
      if (!isNaN(min)) {
        filtered = filtered.filter(item => {
          const sf = parseFloat(item.SHORT_FINAL)
          return isNaN(sf) || sf >= min
        })
      }
    }

    // Apply sort
    if (focusMode) {
      // Focus Mode auto-sort: CANDIDATE first, then WATCH, then lowest spread (cents)
      filtered = [...filtered].sort((a, b) => {
        // State priority: CANDIDATE > WATCH
        const stateOrder = { 'CANDIDATE': 0, 'WATCH': 1 }
        const aState = stateOrder[a.state] ?? 2
        const bState = stateOrder[b.state] ?? 2

        if (aState !== bState) {
          return aState - bState
        }

        // Same state: sort by spread in cents (ascending)
        const aSpread = parseFloat(a.spread) || (a.ask && a.bid ? a.ask - a.bid : Infinity)
        const bSpread = parseFloat(b.spread) || (b.ask && b.bid ? b.ask - b.bid : Infinity)
        return aSpread - bSpread
      })
    } else if (sortConfig.key) {
      filtered = [...filtered].sort((a, b) => {
        const aVal = a[sortConfig.key]
        const bVal = b[sortConfig.key]
        const aNum = parseFloat(aVal)
        const bNum = parseFloat(bVal)

        if (!isNaN(aNum) && !isNaN(bNum)) {
          return sortConfig.direction === 'asc' ? aNum - bNum : bNum - aNum
        }

        const aStr = String(aVal || '')
        const bStr = String(bVal || '')
        return sortConfig.direction === 'asc'
          ? aStr.localeCompare(bStr)
          : bStr.localeCompare(aStr)
      })
    }

    return filtered
  }, [data, filter, sortConfig, focusMode, stateFilter, spreadMax, avgAdvMin, finalThgMin, shortFinalMin])

  const handleSort = useCallback((key) => {
    setSortConfig(prev => ({
      key,
      // Default to 'desc' (büyükten küçüğe), toggle if same column
      direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc'
    }))
  }, [])

  return (
    <div className="app">
      <header className="app-header">
        <h1>Quant Engine - Trading Scanner</h1>
        <div className="header-actions">
          <GroupSelector data={data} />
          <div className="status-indicators">
            <span className={`status-badge ${wsConnected ? 'connected' : 'disconnected'}`}>
              WS: {wsConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
        </div>
      </header>

      {/* Secondary Toolbar for Action Buttons (User Requested New Line) */}
      <div className="secondary-toolbar">
        <div className="toolbar-left">
          <button
            className={`status-badge ${showRejected ? 'active' : ''}`}
            onClick={() => setShowRejected(!showRejected)}
            style={{ cursor: 'pointer', background: showRejected ? '#552222' : '#333', color: '#ff9999' }}
          >
            🚫 Rejected
          </button>
          <button
            className={`status-badge ${showGemProposals ? 'active' : ''}`}
            onClick={() => setShowGemProposals(!showGemProposals)}
            style={{ cursor: 'pointer', background: showGemProposals ? '#225555' : '#333', color: '#00d4ff' }}
          >
            💎 Gems
          </button>
          <button
            className={`status-badge ${showGenobs ? 'active' : ''}`}
            onClick={() => setShowGenobs(!showGenobs)}
            style={{ cursor: 'pointer', background: showGenobs ? '#442255' : '#333', color: '#a4f' }}
          >
            🧬 Genobs
          </button>
          <button
            className={`status-badge ${showBenchmarkFills ? 'active' : ''}`}
            onClick={() => setShowBenchmarkFills(!showBenchmarkFills)}
            style={{ cursor: 'pointer', background: showBenchmarkFills ? '#4A5568' : '#333', color: '#63B3ED' }}
          >
            📊 QeBench
          </button>
          <button
            className={`status-badge ${showSimulation ? 'active' : ''}`}
            onClick={() => setShowSimulation(!showSimulation)}
            style={{ cursor: 'pointer', background: showSimulation ? '#f39c12' : '#333', color: '#f39c12' }}
          >
            🎭 Simulation
          </button>
          <button
            className={`status-badge ${showKarbotuDebug ? 'active' : ''}`}
            onClick={() => setShowKarbotuDebug(!showKarbotuDebug)}
            style={{ cursor: 'pointer', background: showKarbotuDebug ? '#e74c3c' : '#333', color: '#e74c3c' }}
          >
            🔍 KARBOTU Debug
          </button>
          <button
            className={`status-badge ${showExcludedList ? 'active' : ''}`}
            onClick={() => setShowExcludedList(!showExcludedList)}
            style={{ cursor: 'pointer', background: showExcludedList ? '#ef4444' : '#333', color: '#ef4444', borderColor: '#ef4444' }}
          >
            🚫 Excluded List
          </button>
          <button
            className={`status-badge ${showPatternSuggestions ? 'active' : ''}`}
            onClick={() => setShowPatternSuggestions(!showPatternSuggestions)}
            style={{ cursor: 'pointer', background: showPatternSuggestions ? '#7c3aed' : '#333', color: '#a78bfa', border: showPatternSuggestions ? '1px solid #a78bfa' : '1px solid #444' }}
          >
            🔮 Pattern Suggestions
          </button>
          <button
            className={`status-badge ${showExDivPlan ? 'active' : ''}`}
            onClick={() => setShowExDivPlan(!showExDivPlan)}
            style={{ cursor: 'pointer', background: showExDivPlan ? '#2b6cb0' : '#333', color: '#63b3ed', border: showExDivPlan ? '1px solid #63b3ed' : '1px solid #444' }}
          >
            📅 Ex-Div Plan
          </button>
          <button
            className={`status-badge ${showTSSScreen ? 'active' : ''}`}
            onClick={() => {
              setShowTSSScreen(!showTSSScreen)
              if (!showTSSScreen) {
                // Fetch TSS data when opening
                fetch('/tss-v2')
                  .then(r => r.json())
                  .then(d => { if (d.success) setTssData(d) })
                  .catch(console.error)
              }
            }}
            style={{ cursor: 'pointer', background: showTSSScreen ? '#1a7a3a' : '#333', color: '#4ade80', border: showTSSScreen ? '1px solid #4ade80' : '1px solid #444', fontWeight: 'bold' }}
          >
            📈 TSS - RTS Screen
          </button>
          <button
            className={`status-badge ${showAdminPanel ? 'active' : ''}`}
            onClick={() => setShowAdminPanel(!showAdminPanel)}
            style={{ cursor: 'pointer', background: showAdminPanel ? '#7f1d1d' : '#333', color: '#f87171', border: showAdminPanel ? '1px solid #ef4444' : '1px solid #444', fontWeight: 'bold' }}
          >
            🛡️ Admin Panel
          </button>

          {/* Lifeless Mode Controls - Moved here for visibility */}
          <div style={{ display: 'inline-flex', alignItems: 'center', marginLeft: '20px', borderLeft: '1px solid #444', paddingLeft: '20px' }}>
            <button
              className={`status-badge ${lifelessMode ? 'active-warning' : ''}`}
              onClick={toggleLifelessMode}
              style={{
                cursor: 'pointer',
                background: lifelessMode ? '#ff4444' : '#333',
                color: lifelessMode ? '#fff' : '#888',
                border: lifelessMode ? '1px solid #ff0000' : '1px solid #444',
                marginRight: '10px'
              }}
              title="Click to toggle Snapshot Playback Mode"
            >
              {lifelessMode ? '💀 CANSIZ VERİ (ACTIVE)' : '🟢 CANLI VERİ'}
            </button>
            {lifelessMode && (
              <button
                className="status-badge"
                onClick={handleShuffle}
                style={{
                  cursor: 'pointer',
                  background: '#ffaa00',
                  color: '#000',
                  border: '1px solid #ffaa00',
                  fontWeight: 'bold'
                }}
                title="Shuffle Data by +/- 0.05-0.15"
              >
                🎲 SİMÜLASYON (KARIŞTIR)
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Trading Account Selector */}
      <TradingAccountSelector onModeChange={setTradingMode} />

      {/* ETF Benchmark Strip */}
      <ETFStrip />

      {/* Quick Counters */}
      <div className="counters-bar">
        <div className="counter-item">
          <span className="counter-label">Total:</span>
          <span className="counter-value">{counters.total}</span>
        </div>
        <div className="counter-item">
          <span className="counter-label">WATCH:</span>
          <span className="counter-value">{counters.watch}</span>
        </div>
        <div className="counter-item">
          <span className="counter-label">CANDIDATE:</span>
          <span className="counter-value">{counters.candidate}</span>
        </div>
      </div>

      <ControlBar
        onLoadCsv={loadCsv}
        onRefresh={fetchMergedData}
        autoRefresh={autoRefresh}
        onAutoRefreshChange={setAutoRefresh}
        filter={filter}
        onFilterChange={setFilter}
        loading={loading}
        stateFilter={stateFilter}
        onStateFilterChange={setStateFilter}
        spreadMax={spreadMax}
        onSpreadMaxChange={setSpreadMax}
        avgAdvMin={avgAdvMin}
        onAvgAdvMinChange={setAvgAdvMin}
        finalThgMin={finalThgMin}
        onFinalThgMinChange={setFinalThgMin}
        shortFinalMin={shortFinalMin}
        onShortFinalMinChange={setShortFinalMin}
        focusMode={focusMode}
        onFocusModeChange={setFocusMode}
        executionMode={executionMode}
        onExecutionModeChange={handleExecutionModeChange}
      />

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      {/* Group Context Bar */}
      {selectedGroup && (
        <GroupContextBar
          selectedGroup={selectedGroup}
          selectedCgrup={selectedCgrup}
          data={data}
        />
      )}

      <div className="main-content">
        <div className="scanner-container">
          <div className={`scanner-wrapper ${selectedRow ? 'with-inspector' : ''}`}>
            <ScannerTable
              data={filteredAndSortedData}
              onSort={handleSort}
              sortConfig={sortConfig}
              onRowClick={setSelectedRow}
            />
          </div>

          <StateReasonInspector
            selectedRow={selectedRow}
            onClose={() => setSelectedRow(null)}
          />
        </div>

        {/* PSFALGO Bulk Action Panel */}
        <PSFALGOBulkActionPanel
          data={filteredAndSortedData}
          onOpenSimulation={() => setShowSimulation(true)}
          onOpenReport={() => setShowKarbotuDebug(true)}
        />

        {/* Mini Account Sidebar (fixed right, icons only) */}
        <AccountSidebar
          tradingMode={tradingMode}
          onOpenOverlay={(panelType) => {
            setOverlayPanelType(panelType)
            setOverlayOpen(true)
          }}
        />
      </div>

      {/* Trading Panels Overlay */}
      <TradingPanelsOverlay
        isOpen={overlayOpen}
        onClose={() => setOverlayOpen(false)}
        tradingMode={tradingMode}
        panelType={overlayPanelType}
      />


      <RejectedCandidates
        isOpen={showRejected}
        onClose={() => setShowRejected(false)}
      />

      <GemProposalsPanel
        isOpen={showGemProposals}
        onClose={() => setShowGemProposals(false)}
      />

      <GenobsPanel
        isOpen={showGenobs}
        onClose={() => setShowGenobs(false)}
      />

      {showBenchmarkFills && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          backgroundColor: '#1a202c',
          zIndex: 2000,
          overflow: 'auto',
          padding: '20px'
        }}>
          <button
            onClick={() => setShowBenchmarkFills(false)}
            style={{
              position: 'absolute',
              top: '20px',
              right: '20px',
              padding: '8px 16px',
              background: '#e53e3e',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontWeight: 'bold'
            }}
          >
            Close Monitor
          </button>
          <BenchmarkFillsPanel />
        </div>
      )}

      {showSimulation && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          backgroundColor: '#1a202c',
          zIndex: 2000,
          overflow: 'auto',
          padding: '20px'
        }}>
          <button
            onClick={() => setShowSimulation(false)}
            style={{
              position: 'absolute',
              top: '20px',
              right: '20px',
              padding: '8px 16px',
              background: '#e53e3e',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontWeight: 'bold'
            }}
          >
            Close
          </button>
          <SimulationPanel />
          <FakeOrdersList />
        </div>
      )}

      {showKarbotuDebug && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          backgroundColor: '#1a202c',
          zIndex: 2000,
          overflow: 'auto',
          padding: '20px'
        }}>
          <button
            onClick={() => setShowKarbotuDebug(false)}
            style={{
              position: 'absolute',
              top: '20px',
              right: '20px',
              padding: '8px 16px',
              background: '#e53e3e',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontWeight: 'bold'
            }}
          >
            Close
          </button>
          <KarbotuDiagnostic />
        </div>
      )}

      {/* Excluded List Modal */}
      <ExcludedListModal
        isOpen={showExcludedList}
        onClose={() => setShowExcludedList(false)}
      />

      {/* Pattern Suggestions Modal */}
      <PatternSuggestionsModal
        isOpen={showPatternSuggestions}
        onClose={() => setShowPatternSuggestions(false)}
      />

      {/* Ex-Div 30 Day Plan Panel */}
      <ExDivPlanPanel
        isOpen={showExDivPlan}
        onClose={() => setShowExDivPlan(false)}
      />

      {/* TSS - RTS Screen */}
      {showTSSScreen && (
        <div style={{
          position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
          backgroundColor: '#0d1117', zIndex: 2000, overflow: 'auto', padding: '20px',
          fontFamily: "'JetBrains Mono', 'Fira Code', monospace"
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <h2 style={{ color: '#4ade80', margin: 0 }}>📈 Truth Shift Score v2 — Real-Time Dashboard</h2>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button onClick={() => {
                fetch('/tss-v2').then(r => r.json()).then(d => { if (d.success) setTssData(d) }).catch(console.error)
              }} style={{ padding: '6px 12px', background: '#1a7a3a', color: '#fff', border: '1px solid #4ade80', borderRadius: '4px', cursor: 'pointer' }}>
                🔄 Refresh
              </button>
              <button onClick={() => setShowTSSScreen(false)} style={{
                padding: '6px 16px', background: '#e53e3e', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold'
              }}>Close</button>
            </div>
          </div>

          {!tssData ? (
            <div style={{ color: '#888', textAlign: 'center', padding: '60px' }}>
              <p>⏳ TSS v2 verisi bekleniyor...</p>
              <p style={{ fontSize: '12px' }}>Engine henüz hesaplama yapmamış olabilir veya truth tick verisi eksik.</p>
            </div>
          ) : (
            <div>
              {/* Market Overview */}
              {Object.entries(tssData.market_scores || {}).map(([wname, mkt]) => (
                <div key={wname} style={{ background: '#161b22', borderRadius: '8px', padding: '16px', marginBottom: '20px', border: '1px solid #30363d' }}>
                  <h3 style={{ color: '#c9d1d9', marginTop: 0 }}>
                    🌐 {wname} — Market TSS: <span style={{ color: mkt.tss >= 55 ? '#4ade80' : mkt.tss >= 45 ? '#fbbf24' : '#ef4444', fontSize: '24px' }}>{mkt.tss}</span>
                    <span style={{ color: '#8b949e', fontSize: '14px', marginLeft: '16px' }}>{mkt.symbol_count} symbols, {mkt.group_count} groups</span>
                  </h3>
                  {mkt.top_group && <div style={{ color: '#4ade80' }}>▲ Most Bullish: {mkt.top_group.name} = {mkt.top_group.tss}</div>}
                  {mkt.bottom_group && <div style={{ color: '#ef4444' }}>▼ Most Bearish: {mkt.bottom_group.name} = {mkt.bottom_group.tss}</div>}

                  {/* Group Rankings */}
                  {mkt.groups_ranked && (
                    <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '12px', fontSize: '13px' }}>
                      <thead>
                        <tr style={{ borderBottom: '1px solid #30363d' }}>
                          <th style={{ textAlign: 'left', padding: '6px', color: '#8b949e' }}>#</th>
                          <th style={{ textAlign: 'left', padding: '6px', color: '#8b949e' }}>Group</th>
                          <th style={{ textAlign: 'center', padding: '6px', color: '#8b949e' }}>TSS</th>
                          <th style={{ textAlign: 'left', padding: '6px', color: '#8b949e' }}>Signal</th>
                        </tr>
                      </thead>
                      <tbody>
                        {mkt.groups_ranked.map((g, i) => (
                          <tr key={g.name} style={{ borderBottom: '1px solid #21262d' }}>
                            <td style={{ padding: '4px 6px', color: '#8b949e' }}>{i + 1}</td>
                            <td style={{ padding: '4px 6px', color: '#c9d1d9' }}>{g.name}</td>
                            <td style={{ padding: '4px 6px', textAlign: 'center', fontWeight: 'bold', color: g.tss >= 55 ? '#4ade80' : g.tss >= 45 ? '#fbbf24' : '#ef4444' }}>{g.tss}</td>
                            <td style={{ padding: '4px 6px', color: g.tss >= 55 ? '#4ade80' : g.tss >= 45 ? '#fbbf24' : '#ef4444' }}>
                              {g.tss >= 70 ? '🟢🟢 STRONG BUY' : g.tss >= 55 ? '🟢 Bullish' : g.tss >= 45 ? '↔️ Neutral' : g.tss >= 30 ? '🔴 Bearish' : '🔴🔴 STRONG SELL'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              ))}

              {/* Top/Bottom Symbols */}
              {tssData.symbol_scores && Object.keys(tssData.symbol_scores).length > 0 && (() => {
                const allSyms = Object.entries(tssData.symbol_scores)
                  .filter(([, d]) => d.W_15M || d.W_1H || d.W_FULL_DAY)
                  .map(([sym, d]) => {
                    const w = d.W_15M || d.W_1H || d.W_FULL_DAY || {}
                    return { sym, tss: w.tss || 50, vol_dir: w.vol_dir, freq: w.freq_press, vwap: w.vwap_mom, rec: w.recency_factor }
                  })
                  .sort((a, b) => b.tss - a.tss)
                const n5 = Math.max(5, Math.ceil(allSyms.length * 0.05))
                return (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginTop: '16px' }}>
                    <div style={{ background: '#0a1f0a', borderRadius: '8px', padding: '16px', border: '1px solid #1a4a1a' }}>
                      <h4 style={{ color: '#4ade80', marginTop: 0 }}>▲ TOP {n5} (Most Bullish)</h4>
                      {allSyms.slice(0, n5).map((s, i) => (
                        <div key={s.sym} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0', color: '#4ade80', fontSize: '13px' }}>
                          <span>{i + 1}. {s.sym}</span>
                          <span style={{ fontWeight: 'bold' }}>{s.tss?.toFixed(1)} {s.rec < 1 ? `(rec=${s.rec})` : ''}</span>
                        </div>
                      ))}
                    </div>
                    <div style={{ background: '#1f0a0a', borderRadius: '8px', padding: '16px', border: '1px solid #4a1a1a' }}>
                      <h4 style={{ color: '#ef4444', marginTop: 0 }}>▼ BOTTOM {n5} (Most Bearish)</h4>
                      {allSyms.slice(-n5).reverse().map((s, i) => (
                        <div key={s.sym} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0', color: '#ef4444', fontSize: '13px' }}>
                          <span>{i + 1}. {s.sym}</span>
                          <span style={{ fontWeight: 'bold' }}>{s.tss?.toFixed(1)} {s.rec < 1 ? `(rec=${s.rec})` : ''}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )
              })()}
            </div>
          )}
        </div>
      )}

      {/* Admin Panel */}
      <AdminPanel
        isOpen={showAdminPanel}
        onClose={() => setShowAdminPanel(false)}
      />
    </div>
  )
}

export default App

