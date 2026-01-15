import React, { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import ScannerTable from '../components/ScannerTable'
import ControlBar from '../components/ControlBar'
import StateReasonInspector from '../components/StateReasonInspector'
import ETFStrip from '../components/ETFStrip'
import TradingAccountSelector from '../components/TradingAccountSelector'
import AccountSidebar from '../components/AccountSidebar'
import TradingPanelsOverlay from '../components/TradingPanelsOverlay'
import GroupSelector from '../components/GroupSelector'
import GroupContextBar from '../components/GroupContextBar'
import TickerAlertPanel from '../components/TickerAlertPanel'
import '../App.css'

function ScannerPage() {
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
  const [dosGrupFilter, setDosGrupFilter] = useState('')
  const [bidBuyUcuzlukMax, setBidBuyUcuzlukMax] = useState('')
  const [askSellPahalilikMin, setAskSellPahalilikMin] = useState('')
  const [finalBBMin, setFinalBBMin] = useState('')
  const [finalSASMax, setFinalSASMax] = useState('')
  const [finalFBMin, setFinalFBMin] = useState('')
  const [finalSFSMax, setFinalSFSMax] = useState('')
  const [gortMin, setGortMin] = useState('')
  const [gortMax, setGortMax] = useState('')
  const [fbtotMin, setFbtotMin] = useState('')
  const [sfstotMax, setSfstotMax] = useState('')
  
  // Presets
  const [presets, setPresets] = useState([])
  const [presetName, setPresetName] = useState('')
  
  // Load presets from backend on mount
  useEffect(() => {
    const loadPresets = async () => {
      try {
        const response = await fetch('/api/scanner-filters/presets/list')
        const data = await response.json()
        if (data.success) {
          setPresets(data.presets || [])
        }
      } catch (err) {
        console.error('Error loading presets:', err)
        // Fallback to localStorage
        const savedPresets = localStorage.getItem('scanner_filter_presets')
        if (savedPresets) {
          try {
            const parsed = JSON.parse(savedPresets)
            setPresets(Object.keys(parsed))
          } catch (e) {
            console.error('Error parsing localStorage presets:', e)
          }
        }
      }
    }
    loadPresets()
  }, [])
  
  // Load saved filters from localStorage on mount
  useEffect(() => {
    const savedFilters = localStorage.getItem('scanner_filters')
    if (savedFilters) {
      try {
        const filters = JSON.parse(savedFilters)
        if (filters.spreadMax !== undefined) setSpreadMax(filters.spreadMax || '')
        if (filters.avgAdvMin !== undefined) setAvgAdvMin(filters.avgAdvMin || '')
        if (filters.finalThgMin !== undefined) setFinalThgMin(filters.finalThgMin || '')
        if (filters.shortFinalMin !== undefined) setShortFinalMin(filters.shortFinalMin || '')
        if (filters.dosGrupFilter !== undefined) setDosGrupFilter(filters.dosGrupFilter || '')
        if (filters.bidBuyUcuzlukMax !== undefined) setBidBuyUcuzlukMax(filters.bidBuyUcuzlukMax || '')
        if (filters.askSellPahalilikMin !== undefined) setAskSellPahalilikMin(filters.askSellPahalilikMin || '')
        if (filters.finalBBMin !== undefined) setFinalBBMin(filters.finalBBMin || '')
        if (filters.finalSASMax !== undefined) setFinalSASMax(filters.finalSASMax || '')
        if (filters.finalFBMin !== undefined) setFinalFBMin(filters.finalFBMin || '')
        if (filters.finalSFSMax !== undefined) setFinalSFSMax(filters.finalSFSMax || '')
        if (filters.gortMin !== undefined) setGortMin(filters.gortMin || '')
        if (filters.gortMax !== undefined) setGortMax(filters.gortMax || '')
        if (filters.fbtotMin !== undefined) setFbtotMin(filters.fbtotMin || '')
        if (filters.sfstotMax !== undefined) setSfstotMax(filters.sfstotMax || '')
        if (filters.stateFilter) setStateFilter(filters.stateFilter)
        if (filters.filter) setFilter(filters.filter || '')
      } catch (e) {
        console.error('Error loading saved filters:', e)
      }
    }
  }, [])
  
  // Save filters to localStorage whenever they change
  useEffect(() => {
    const filters = {
      spreadMax,
      avgAdvMin,
      finalThgMin,
      shortFinalMin,
      dosGrupFilter,
      bidBuyUcuzlukMax,
      askSellPahalilikMin,
      finalBBMin,
      finalSASMax,
      finalFBMin,
      finalSFSMax,
      gortMin,
      gortMax,
      fbtotMin,
      sfstotMax,
      stateFilter,
      filter
    }
    localStorage.setItem('scanner_filters', JSON.stringify(filters))
  }, [spreadMax, avgAdvMin, finalThgMin, shortFinalMin, dosGrupFilter, bidBuyUcuzlukMax, askSellPahalilikMin, finalBBMin, finalSASMax, finalFBMin, finalSFSMax, gortMin, gortMax, fbtotMin, sfstotMax, stateFilter, filter])
  
  // Preset handlers
  const handlePresetSave = async () => {
    if (!presetName.trim()) {
      alert('Please enter a preset name')
      return
    }
    
    try {
      const filters = {
        spreadMax,
        avgAdvMin,
        finalThgMin,
        shortFinalMin,
        dosGrupFilter,
        bidBuyUcuzlukMax,
        askSellPahalilikMin,
        finalBBMin,
        finalSASMax,
        finalFBMin,
        finalSFSMax,
        gortMin,
        gortMax,
        fbtotMin,
        sfstotMax,
        stateFilter,
        filter
      }
      
      const response = await fetch(`/api/scanner-filters/presets/save?name=${encodeURIComponent(presetName)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filter_state: filters })
      })
      
      const data = await response.json()
      if (data.success) {
        alert(`Preset "${presetName}" saved successfully!`)
        setPresetName('')
        // Reload presets list
        const listResponse = await fetch('/api/scanner-filters/presets/list')
        const listData = await listResponse.json()
        if (listData.success) {
          setPresets(listData.presets || [])
        }
        // Also save to localStorage as backup
        const savedPresets = JSON.parse(localStorage.getItem('scanner_filter_presets') || '{}')
        savedPresets[presetName] = filters
        localStorage.setItem('scanner_filter_presets', JSON.stringify(savedPresets))
      } else {
        alert(`Error: ${data.detail || 'Failed to save preset'}`)
      }
    } catch (err) {
      console.error('Error saving preset:', err)
      // Fallback to localStorage
      const savedPresets = JSON.parse(localStorage.getItem('scanner_filter_presets') || '{}')
      savedPresets[presetName] = filters
      localStorage.setItem('scanner_filter_presets', JSON.stringify(savedPresets))
      alert(`Preset "${presetName}" saved to localStorage (backend unavailable)`)
      setPresetName('')
      setPresets(Object.keys(savedPresets))
    }
  }
  
  const handlePresetLoad = async (presetNameToLoad) => {
    if (!presetNameToLoad) return
    
    try {
      const response = await fetch(`/api/scanner-filters/presets/load?name=${encodeURIComponent(presetNameToLoad)}`)
      const data = await response.json()
      
      if (data.success && data.filterState) {
        const filters = data.filterState
        if (filters.spreadMax !== undefined) setSpreadMax(filters.spreadMax || '')
        if (filters.avgAdvMin !== undefined) setAvgAdvMin(filters.avgAdvMin || '')
        if (filters.finalThgMin !== undefined) setFinalThgMin(filters.finalThgMin || '')
        if (filters.shortFinalMin !== undefined) setShortFinalMin(filters.shortFinalMin || '')
        if (filters.dosGrupFilter !== undefined) setDosGrupFilter(filters.dosGrupFilter || '')
        if (filters.bidBuyUcuzlukMax !== undefined) setBidBuyUcuzlukMax(filters.bidBuyUcuzlukMax || '')
        if (filters.askSellPahalilikMin !== undefined) setAskSellPahalilikMin(filters.askSellPahalilikMin || '')
        if (filters.finalBBMin !== undefined) setFinalBBMin(filters.finalBBMin || '')
        if (filters.finalSASMax !== undefined) setFinalSASMax(filters.finalSASMax || '')
        if (filters.finalFBMin !== undefined) setFinalFBMin(filters.finalFBMin || '')
        if (filters.finalSFSMax !== undefined) setFinalSFSMax(filters.finalSFSMax || '')
        if (filters.gortMin !== undefined) setGortMin(filters.gortMin || '')
        if (filters.gortMax !== undefined) setGortMax(filters.gortMax || '')
        if (filters.fbtotMin !== undefined) setFbtotMin(filters.fbtotMin || '')
        if (filters.sfstotMax !== undefined) setSfstotMax(filters.sfstotMax || '')
        if (filters.stateFilter) setStateFilter(filters.stateFilter)
        if (filters.filter !== undefined) setFilter(filters.filter || '')
        alert(`Preset "${presetNameToLoad}" loaded successfully!`)
      } else {
        alert(`Error: ${data.detail || 'Failed to load preset'}`)
      }
    } catch (err) {
      console.error('Error loading preset:', err)
      // Fallback to localStorage
      const savedPresets = JSON.parse(localStorage.getItem('scanner_filter_presets') || '{}')
      if (savedPresets[presetNameToLoad]) {
        const filters = savedPresets[presetNameToLoad]
        // Apply filters same as above
        if (filters.spreadMax !== undefined) setSpreadMax(filters.spreadMax || '')
        if (filters.avgAdvMin !== undefined) setAvgAdvMin(filters.avgAdvMin || '')
        if (filters.finalThgMin !== undefined) setFinalThgMin(filters.finalThgMin || '')
        if (filters.shortFinalMin !== undefined) setShortFinalMin(filters.shortFinalMin || '')
        if (filters.dosGrupFilter !== undefined) setDosGrupFilter(filters.dosGrupFilter || '')
        if (filters.bidBuyUcuzlukMax !== undefined) setBidBuyUcuzlukMax(filters.bidBuyUcuzlukMax || '')
        if (filters.askSellPahalilikMin !== undefined) setAskSellPahalilikMin(filters.askSellPahalilikMin || '')
        if (filters.finalBBMin !== undefined) setFinalBBMin(filters.finalBBMin || '')
        if (filters.finalSASMax !== undefined) setFinalSASMax(filters.finalSASMax || '')
        if (filters.finalFBMin !== undefined) setFinalFBMin(filters.finalFBMin || '')
        if (filters.finalSFSMax !== undefined) setFinalSFSMax(filters.finalSFSMax || '')
        if (filters.gortMin !== undefined) setGortMin(filters.gortMin || '')
        if (filters.gortMax !== undefined) setGortMax(filters.gortMax || '')
        if (filters.fbtotMin !== undefined) setFbtotMin(filters.fbtotMin || '')
        if (filters.sfstotMax !== undefined) setSfstotMax(filters.sfstotMax || '')
        if (filters.stateFilter) setStateFilter(filters.stateFilter)
        if (filters.filter !== undefined) setFilter(filters.filter || '')
        alert(`Preset "${presetNameToLoad}" loaded from localStorage`)
      } else {
        alert(`Preset "${presetNameToLoad}" not found`)
      }
    }
  }
  
  // Clear all filters handler
  const handleClearAllFilters = () => {
    setFilter('')
    setStateFilter(['IDLE', 'WATCH', 'CANDIDATE'])
    setSpreadMax('')
    setAvgAdvMin('')
    setFinalThgMin('')
    setShortFinalMin('')
    setDosGrupFilter('')
    setBidBuyUcuzlukMax('')
    setAskSellPahalilikMin('')
    setFinalBBMin('')
    setFinalSASMax('')
    setFinalFBMin('')
    setFinalSFSMax('')
    setGortMin('')
    setGortMax('')
    setFbtotMin('')
    setSfstotMax('')
  }
  
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
  
  // Ticker Alert Panel
  const [showTickerAlerts, setShowTickerAlerts] = useState(false)
  const [tickerAlertSessionId, setTickerAlertSessionId] = useState(null)
  
  // Create tab session on mount (for ticker alert tracking)
  useEffect(() => {
    const sessionId = `tab_${Date.now()}`
    setTickerAlertSessionId(sessionId)
    
    // Create session on backend
    fetch(`/api/ticker-alerts/session/create?session_id=${sessionId}`, {
      method: 'POST'
    }).catch(err => {
      console.error('Error creating ticker alert session:', err)
    })
    
    return () => {
      // Cleanup: reset session on unmount (optional)
    }
  }, [])

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

  // WebSocket connection (ONLY Scanner page opens WebSocket)
  // Other pages use BroadcastChannel to receive data from Scanner
  useEffect(() => {
    // Initialize BroadcastChannel for publishing market data
    let broadcastChannel = null
    try {
      broadcastChannel = new BroadcastChannel('market-data')
      console.log('✅ BroadcastChannel initialized (Scanner - Publisher)')
    } catch (err) {
      console.warn('BroadcastChannel not supported:', err)
    }
    
    const ws = new WebSocket('ws://localhost:8000/ws/market-data')
    
    ws.onopen = async () => {
      console.log('✅ WebSocket connected (Scanner - Main Connection)')
      setWsConnected(true)
      
      // EVENT-DRIVEN FLOW (restored old model):
      // 1. Subscribe to preferred stocks (L1 only)
      // 2. Each L1Update triggers immediate WebSocket send (event-driven)
      // 3. UI fills as data arrives (no snapshot needed, no batch waiting)
      // 4. WebSocket updates arrive one-by-one as Hammer pushes them
      
      // Subscribe to all preferred stocks (L1 only)
      // Wait a bit for Hammer connection to be ready
      setTimeout(() => {
        console.log('📊 Attempting to subscribe to preferred stocks...')
        fetch('/api/market-data/subscribe-preferred', {
          method: 'POST'
        })
          .then(res => res.json())
          .then(result => {
            if (result.success) {
              console.log(`✅ Subscribed to ${result.subscribed}/${result.total} preferred stocks (L1 only)`)
              console.log('📡 Preferred stocks will update immediately as L1Updates arrive (event-driven)')
            } else {
              console.warn(`⚠️ Preferred subscription failed: ${result.message}`)
              // Retry after 2 seconds if Hammer not ready
              if (result.message && result.message.includes('not available')) {
                setTimeout(() => {
                  console.log('📊 Retrying preferred subscription...')
                  fetch('/api/market-data/subscribe-preferred', {
                    method: 'POST'
                  })
                    .then(res => res.json())
                    .then(retryResult => {
                      if (retryResult.success) {
                        console.log(`✅ Retry successful: Subscribed to ${retryResult.subscribed}/${retryResult.total} preferred stocks`)
                      } else {
                        console.warn(`⚠️ Retry failed: ${retryResult.message}`)
                      }
                    })
                    .catch(err => {
                      console.error('Error in retry subscribing to preferred stocks:', err)
                    })
                }, 2000)
              }
            }
          })
          .catch(err => {
            console.error('Error subscribing to preferred stocks:', err)
          })
      }, 1000) // Wait 1 second for Hammer connection to be ready
    }
    
    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        if (message.type === 'market_data_update') {
          // Debug: Log first few WebSocket messages
          if (!window._wsMessageCount) window._wsMessageCount = 0
          window._wsMessageCount++
          if (window._wsMessageCount <= 3) {
            console.log(`📡 WebSocket message #${window._wsMessageCount}:`, message.type, message.data?.length, 'updates')
            if (message.data && message.data.length > 0) {
              console.log('   First update:', message.data[0])
            }
          }
          
          // Update local data
          setData(prevData => {
            const dataMap = new Map(prevData.map(item => [item.PREF_IBKR, item]))
            
            // Update with new data
            let updatedCount = 0
            message.data.forEach(update => {
              const key = update.PREF_IBKR || update.symbol
              if (key) {
                const existing = dataMap.get(key)
                if (existing) {
                  // Calculate spread if not provided (fallback: ask - bid)
                  if (update.spread === null || update.spread === undefined) {
                    const bid = update.bid !== null && update.bid !== undefined ? update.bid : existing.bid
                    const ask = update.ask !== null && update.ask !== undefined ? update.ask : existing.ask
                    if (bid !== null && bid !== undefined && ask !== null && ask !== undefined) {
                      update.spread = ask - bid
                    }
                  }
                  
                  const merged = { ...existing, ...update }
                  dataMap.set(key, merged)
                  updatedCount++
                  
                  // Debug: Log first few merges
                  if (window._wsMessageCount <= 3 && message.data.indexOf(update) === 0) {
                    console.log(`   ✅ Merged ${key}:`, {
                      existing_bid: existing?.bid,
                      update_bid: update.bid,
                      merged_bid: merged.bid,
                      existing_ask: existing?.ask,
                      update_ask: update.ask,
                      merged_ask: merged.ask,
                      spread: merged.spread,
                      GORT: merged.GORT,
                      Fbtot: merged.Fbtot
                    })
                  }
                } else {
                  // Symbol not in initial data - calculate spread if needed
                  if (update.spread === null || update.spread === undefined) {
                    const bid = update.bid
                    const ask = update.ask
                    if (bid !== null && bid !== undefined && ask !== null && ask !== undefined) {
                      update.spread = ask - bid
                    }
                  }
                  
                  dataMap.set(key, update)
                  if (window._wsMessageCount <= 3 && message.data.indexOf(update) === 0) {
                    console.log(`   ⚠️ Symbol ${key} not in initial data, adding:`, update)
                  }
                }
              }
            })
            
            if (window._wsMessageCount <= 3) {
              console.log(`   Updated ${updatedCount}/${message.data.length} symbols in dataMap`)
            }
            
            return Array.from(dataMap.values())
          })
          
          // Publish to BroadcastChannel for other tabs
          if (broadcastChannel) {
            try {
              broadcastChannel.postMessage({
                type: 'market_data_update',
                data: message.data,
                timestamp: Date.now()
              })
            } catch (err) {
              console.warn('Error posting to BroadcastChannel:', err)
            }
          }
        } else if (message.type === 'pong') {
          // Heartbeat response
        } else if (message.type === 'ticker_alert') {
          // Also broadcast ticker alerts
          if (broadcastChannel) {
            try {
              broadcastChannel.postMessage(message)
            } catch (err) {
              console.warn('Error posting ticker alert to BroadcastChannel:', err)
            }
          }
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
      if (broadcastChannel) {
        broadcastChannel.close()
      }
    }
  }, [])

  // Fetch merged data (defined first to avoid hoisting issues)
  const fetchMergedData = useCallback(async () => {
    try {
      const response = await fetch('/api/market-data/merged')
      const result = await response.json()
      
      console.log('Fetched merged data:', result.success, 'count:', result.count, 'data length:', result.data?.length)
      
      if (result.success) {
        if (result.data && result.data.length > 0) {
          console.log('Setting data, first item:', result.data[0])
          try {
            setData(result.data)
            console.log('Data set successfully, length:', result.data.length)
          } catch (err) {
            console.error('Error setting data:', err)
            setError(`Error setting data: ${err.message}`)
          }
        } else {
          console.warn('No data in response, result:', result)
          setData([])
        }
      } else {
        console.error('Failed to fetch merged data:', result)
        setError('Failed to fetch merged data')
      }
    } catch (err) {
      console.error('Error fetching data:', err)
      setError(`Error fetching data: ${err.message}`)
    }
  }, [])

  // Load initial data on mount (BEFORE CSV load, so we have data structure ready)
  useEffect(() => {
    // Fetch initial merged data immediately on mount
    fetchMergedData()
  }, [fetchMergedData])

  // Load CSV data (defined after fetchMergedData)
  const loadCsv = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch('/api/market-data/load-csv', {
        method: 'POST'
      })
      
      // Check if response is OK
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`HTTP ${response.status}: ${errorText || 'Unknown error'}`)
      }
      
      // Check if response has content
      const contentType = response.headers.get('content-type')
      if (!contentType || !contentType.includes('application/json')) {
        const text = await response.text()
        throw new Error(`Expected JSON but got: ${contentType || 'no content-type'}. Response: ${text.substring(0, 100)}`)
      }
      
      const result = await response.json()
      
      if (result.success) {
        // After loading CSV, fetch merged data
        // Note: fetchMergedData is defined above, so we can call it directly
        await fetchMergedData()
      } else {
        setError(result.message || result.detail || 'Failed to load CSV')
      }
    } catch (err) {
      console.error('CSV loading error:', err)
      setError(`Error loading CSV: ${err.message}`)
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // fetchMergedData is stable (no dependencies), so we don't need it in deps

  // Auto refresh (FALLBACK MODE: only if WebSocket is disconnected)
  // Note: CSV data (prev_close, static scores) is NOT refreshed - it's loaded once at backend startup
  // WebSocket provides real-time updates, so auto refresh is only needed as fallback
  useEffect(() => {
    // Only enable auto refresh if WebSocket is disconnected (fallback mode)
    if (autoRefresh && !wsConnected) {
      const interval = setInterval(fetchMergedData, 2000)
      return () => clearInterval(interval)
    }
  }, [autoRefresh, wsConnected, fetchMergedData])

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
          const spread = parseFloat(item.spread_percent)
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
          const short = parseFloat(item.SHORT_FINAL)
          return isNaN(short) || short >= min
        })
      }
    }
    
    // Apply DOS GRUP filter
    if (dosGrupFilter) {
      const filterLower = dosGrupFilter.toLowerCase()
      filtered = filtered.filter(item => {
        const dosGrup = item.DOS_GRUP || item.CGRUP || ''
        return dosGrup.toLowerCase().includes(filterLower)
      })
    }
    
    // Apply bid buy ucuzluk filter
    if (bidBuyUcuzlukMax) {
      const max = parseFloat(bidBuyUcuzlukMax)
      if (!isNaN(max)) {
        filtered = filtered.filter(item => {
          const ucuzluk = parseFloat(item.bid_buy_ucuzluk)
          return isNaN(ucuzluk) || ucuzluk <= max
        })
      }
    }
    
    // Apply ask sell pahalilik filter
    if (askSellPahalilikMin) {
      const min = parseFloat(askSellPahalilikMin)
      if (!isNaN(min)) {
        filtered = filtered.filter(item => {
          const pahalilik = parseFloat(item.ask_sell_pahalilik)
          return isNaN(pahalilik) || pahalilik >= min
        })
      }
    }
    
    // Apply final BB min filter
    if (finalBBMin) {
      const min = parseFloat(finalBBMin)
      if (!isNaN(min)) {
        filtered = filtered.filter(item => {
          const bb = parseFloat(item.Final_BB_skor || item.final_bb)
          return isNaN(bb) || bb >= min
        })
      }
    }
    
    // Apply final SAS max filter
    if (finalSASMax) {
      const max = parseFloat(finalSASMax)
      if (!isNaN(max)) {
        filtered = filtered.filter(item => {
          const sas = parseFloat(item.Final_SAS_skor || item.final_sas)
          return isNaN(sas) || sas <= max
        })
      }
    }
    
    // Apply final FB min filter
    if (finalFBMin) {
      const min = parseFloat(finalFBMin)
      if (!isNaN(min)) {
        filtered = filtered.filter(item => {
          const fb = parseFloat(item.Final_FB_skor || item.final_fb)
          return isNaN(fb) || fb >= min
        })
      }
    }
    
    // Apply final SFS max filter
    if (finalSFSMax) {
      const max = parseFloat(finalSFSMax)
      if (!isNaN(max)) {
        filtered = filtered.filter(item => {
          const sfs = parseFloat(item.Final_SFS_skor || item.final_sfs)
          return isNaN(sfs) || sfs <= max
        })
      }
    }
    
    // Apply GORT min/max filter
    if (gortMin) {
      const min = parseFloat(gortMin)
      if (!isNaN(min)) {
        filtered = filtered.filter(item => {
          const gort = parseFloat(item.GORT)
          return isNaN(gort) || gort >= min
        })
      }
    }
    
    if (gortMax) {
      const max = parseFloat(gortMax)
      if (!isNaN(max)) {
        filtered = filtered.filter(item => {
          const gort = parseFloat(item.GORT)
          return isNaN(gort) || gort <= max
        })
      }
    }
    
    // Apply Fbtot min filter
    if (fbtotMin) {
      const min = parseFloat(fbtotMin)
      if (!isNaN(min)) {
        filtered = filtered.filter(item => {
          const fbtot = parseFloat(item.Fbtot)
          return isNaN(fbtot) || fbtot >= min
        })
      }
    }
    
    // Apply SFStot max filter
    if (sfstotMax) {
      const max = parseFloat(sfstotMax)
      if (!isNaN(max)) {
        filtered = filtered.filter(item => {
          const sfstot = parseFloat(item.SFStot)
          return isNaN(sfstot) || sfstot <= max
        })
      }
    }
    
    
    // Apply sort
    if (focusMode) {
      // Focus Mode auto-sort: CANDIDATE first, then WATCH, then lowest spread_percent
      filtered = [...filtered].sort((a, b) => {
        // State priority: CANDIDATE > WATCH
        const stateOrder = { 'CANDIDATE': 0, 'WATCH': 1 }
        const aState = stateOrder[a.state] ?? 2
        const bState = stateOrder[b.state] ?? 2
        
        if (aState !== bState) {
          return aState - bState
        }
        
        // Same state: sort by spread_percent (ascending)
        const aSpread = parseFloat(a.spread_percent) || Infinity
        const bSpread = parseFloat(b.spread_percent) || Infinity
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
    
    // Apply group filter (PRIMARY GROUP + SECONDARY GROUP for kuponlu groups)
    if (selectedGroup) {
      const kuponluGroups = ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']
      filtered = filtered.filter(item => {
        const itemGroup = (item.GROUP || item.group || item.file_group)?.toLowerCase()
        if (itemGroup !== selectedGroup) return false
        
        // Kuponlu gruplar için CGRUP kontrolü
        if (kuponluGroups.includes(selectedGroup)) {
          const itemCgrup = item.CGRUP?.toLowerCase()
          if (selectedCgrup === 'no_cgrup') {
            return !itemCgrup || itemCgrup === '' || itemCgrup === 'n/a'
          }
          return itemCgrup === selectedCgrup
        }
        return true
      })
    }
    
    return filtered
  }, [data, filter, sortConfig, focusMode, stateFilter, spreadMax, avgAdvMin, finalThgMin, shortFinalMin, selectedGroup, selectedCgrup])

  const handleSort = useCallback((key) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc'
    }))
  }, [])

  return (
    <div className="app">
      <header className="app-header">
        <h1>Quant Engine - Trading Scanner</h1>
        <div className="header-actions">
          <GroupSelector data={data} />
          <Link 
            to="/port-adjuster" 
            className="psfalgo-link-button"
            title="Open Port Adjuster"
          >
            📐 Port Adjuster
          </Link>
          <Link
            to="/ticker-alerts"
            target="_blank"
            rel="noopener noreferrer"
            className="psfalgo-link-button"
            title="Open Ticker Alerts (Daily High/Low) in new tab"
          >
            🔔 Ticker Alerts
          </Link>
          <Link
            to="/decision-helper"
            target="_blank"
            rel="noopener noreferrer"
            className="psfalgo-link-button"
            title="Open Decision Helper (Market State Analysis) in new tab"
          >
            🎯 Decision Helper
          </Link>
          <Link
            to="/decision-helper-v2"
            target="_blank"
            rel="noopener noreferrer"
            className="psfalgo-link-button"
            title="Open Decision Helper V2 (Modal Price Flow) in new tab"
          >
            🎯 Decision Helper V2
          </Link>
          <Link
            to="/psfalgo-intentions"
            target="_blank"
            rel="noopener noreferrer"
            className="psfalgo-link-button"
            title="Open PSFALGO Intentions (Pending Orders) in new tab"
          >
            🤖 Intentions
          </Link>
          <Link 
            to="/deeper-analysis" 
            target="_blank"
            rel="noopener noreferrer"
            className="psfalgo-link-button"
            title="Open Deeper Analysis (Tick-by-tick) in new tab"
          >
            📊 Deeper Analysis
          </Link>
          <Link
            to="/truth-ticks"
            target="_blank"
            rel="noopener noreferrer"
            className="psfalgo-link-button"
            title="Open Truth Ticks Analysis (Volume-weighted truth prints) in new tab"
          >
            🔍 Truth Ticks
          </Link>
          <Link
            to="/aura-mm"
            target="_blank"
            rel="noopener noreferrer"
            className="psfalgo-link-button"
            title="Open Aura MM Screener (Market Making) in new tab"
          >
            🎯 Aura MM
          </Link>
          <div className="status-indicators">
            <Link 
              to="/psfalgo" 
              target="_blank" 
              rel="noopener noreferrer"
              className="psfalgo-link-button"
              title="Open PSFALGO Position Management in new tab"
            >
              🤖 PSFALGO
            </Link>
            <span className={`status-badge ${wsConnected ? 'connected' : 'disconnected'}`}>
              WS: {wsConnected ? 'Connected' : 'Disconnected'}
            </span>
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
        dosGrupFilter={dosGrupFilter}
        onDosGrupFilterChange={setDosGrupFilter}
        bidBuyUcuzlukMax={bidBuyUcuzlukMax}
        onBidBuyUcuzlukMaxChange={setBidBuyUcuzlukMax}
        askSellPahalilikMin={askSellPahalilikMin}
        onAskSellPahalilikMinChange={setAskSellPahalilikMin}
        finalBBMin={finalBBMin}
        onFinalBBMinChange={setFinalBBMin}
        finalSASMax={finalSASMax}
        onFinalSASMaxChange={setFinalSASMax}
        finalFBMin={finalFBMin}
        onFinalFBMinChange={setFinalFBMin}
        finalSFSMax={finalSFSMax}
        onFinalSFSMaxChange={setFinalSFSMax}
        gortMin={gortMin}
        onGortMinChange={setGortMin}
        gortMax={gortMax}
        onGortMaxChange={setGortMax}
        fbtotMin={fbtotMin}
        onFbtotMinChange={setFbtotMin}
        sfstotMax={sfstotMax}
        onSfstotMaxChange={setSfstotMax}
        presets={presets}
        presetName={presetName}
        onPresetNameChange={setPresetName}
        onPresetSave={handlePresetSave}
        onPresetLoad={handlePresetLoad}
        onPresetsLoad={() => {}}
        onClearAllFilters={handleClearAllFilters}
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
      
      {/* Ticker Alert Panel */}
      {showTickerAlerts && (
        <TickerAlertPanel
          sessionId={tickerAlertSessionId}
          onClose={() => setShowTickerAlerts(false)}
        />
      )}
    </div>
  )
}

export default ScannerPage

