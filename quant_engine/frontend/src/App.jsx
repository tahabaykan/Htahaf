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
  const [tradingMode, setTradingMode] = useState('HAMMER_TRADING')

  // Trading Panels Overlay
  const [overlayOpen, setOverlayOpen] = useState(false)
  const [overlayPanelType, setOverlayPanelType] = useState('positions')

  // Group Navigation
  const [selectedGroup, setSelectedGroup] = useState(null)
  const [selectedCgrup, setSelectedCgrup] = useState(null)

  // Rejected Candidates Panel
  const [showRejected, setShowRejected] = useState(false)

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
            <button
              className={`status-badge ${showRejected ? 'active' : ''}`}
              onClick={() => setShowRejected(!showRejected)}
              style={{ cursor: 'pointer', background: showRejected ? '#552222' : '#333', color: '#ff9999' }}
            >
              🚫 Rejected
            </button>
          </div>
        </div>
      </header>

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
        <PSFALGOBulkActionPanel data={filteredAndSortedData} />

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
    </div>
  )
}

export default App

