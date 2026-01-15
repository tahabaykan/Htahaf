import React, { useState, useEffect } from 'react'
import './ETFStrip.css'

function ETFStrip() {
  const [etfData, setEtfData] = useState([])
  const [wsConnected, setWsConnected] = useState(false)

  // WebSocket connection for ETF updates
  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/ws/market-data')
    
    ws.onopen = () => {
      setWsConnected(true)
    }
    
    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        if (message.type === 'etf_update') {
          // Debug: Log first few ETF updates
          if (!window._etfMessageCount) window._etfMessageCount = 0
          window._etfMessageCount++
          if (window._etfMessageCount <= 3) {
            console.log(`📡 ETF WebSocket message #${window._etfMessageCount}:`, message.type, message.data?.length, 'ETFs')
            if (message.data && message.data.length > 0) {
              console.log('   First ETF update:', message.data[0])
            }
          }
          
          // Update ETF data
          setEtfData(prevData => {
            const dataMap = new Map(prevData.map(item => [item.symbol, item]))
            
            message.data.forEach(update => {
              if (update.symbol) {
                // Merge with existing data (if any)
                const existing = dataMap.get(update.symbol)
                if (existing) {
                  dataMap.set(update.symbol, { ...existing, ...update })
                } else {
                  dataMap.set(update.symbol, update)
                }
              }
            })
            
            return Array.from(dataMap.values())
          })
        }
      } catch (err) {
        console.error('Error parsing ETF WebSocket message:', err)
      }
    }
    
    ws.onerror = (error) => {
      console.error('ETF WebSocket error:', error)
      setWsConnected(false)
    }
    
    ws.onclose = () => {
      setWsConnected(false)
    }
    
    // Initial fetch from REST API and subscribe
    // CORRECT FLOW for Hammer push-based system:
    // 1. First subscribe (so Hammer starts pushing ETF L1/L2 data)
    // 2. Wait for cache to fill
    // 3. Then fetch snapshot (optional - WebSocket will handle updates)
    const initEtf = async () => {
      try {
        // Subscribe to ETFs FIRST (for real-time updates)
        const subscribeRes = await fetch('/api/market-data/subscribe-etf', {
          method: 'POST'
        })
        const subscribeResult = await subscribeRes.json()
        if (subscribeResult.success) {
          console.log(`ETF subscription: ${subscribeResult.subscribed}/${subscribeResult.total} subscribed`)
          
          // NOW wait for cache to fill (Hammer needs time to push first L1/L2 updates)
          // Then fetch snapshot (optional - only if cache has data)
          setTimeout(async () => {
            try {
              console.log('📸 Fetching ETF snapshot after subscription (cache should be filled now)...')
              const snapshotRes = await fetch('/api/market-data/snapshot/etf')
              const snapshotResult = await snapshotRes.json()
              
              if (snapshotResult.success && snapshotResult.data && snapshotResult.count > 0) {
                console.log(`📸 ETF Snapshot received: ${snapshotResult.count} ETFs`)
                setEtfData(snapshotResult.data)
              } else {
                console.log(`📸 ETF Snapshot empty (${snapshotResult.count} ETFs) - will wait for WebSocket updates`)
                // Fallback: try regular endpoint (might have prev_close at least)
                try {
                  const dataRes = await fetch('/api/market-data/etf')
                  const dataResult = await dataRes.json()
                  if (dataResult.success && dataResult.data && dataResult.data.length > 0) {
                    console.log(`📸 Fallback ETF endpoint: ${dataResult.data.length} ETFs`)
                    setEtfData(dataResult.data)
                  } else {
                    console.log('📸 Fallback ETF endpoint also empty - waiting for WebSocket updates')
                  }
                } catch (err) {
                  console.warn('⚠️ Fallback ETF endpoint failed:', err)
                }
              }
            } catch (err) {
              console.warn('⚠️ ETF snapshot fetch failed (non-critical, WebSocket will provide updates):', err)
              // Fallback to regular endpoint
              try {
                const dataRes = await fetch('/api/market-data/etf')
                const dataResult = await dataRes.json()
                if (dataResult.success && dataResult.data) {
                  setEtfData(dataResult.data)
                }
              } catch (fallbackErr) {
                console.error('Error fetching ETF data (fallback):', fallbackErr)
              }
            }
          }, 2000) // Wait 2 seconds for Hammer to push first L1/L2 updates to cache
        }
      } catch (err) {
        console.error('Error initializing ETF data:', err)
      }
    }
    
    initEtf()
    
    return () => {
      ws.close()
    }
  }, [])

  // Format number with 2 decimals
  const formatPrice = (value) => {
    if (value === null || value === undefined) return 'N/A'
    return parseFloat(value).toFixed(2)
  }

  // Format percentage with 2 decimals and sign
  const formatPercent = (value) => {
    if (value === null || value === undefined) return 'N/A'
    const num = parseFloat(value)
    return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`
  }

  // Format cents change with 2 decimals and sign
  const formatCents = (value) => {
    if (value === null || value === undefined) return 'N/A'
    const num = parseFloat(value)
    return `${num >= 0 ? '+' : ''}${num.toFixed(2)}`
  }

  // Get color class based on daily change
  const getChangeColor = (value) => {
    if (value === null || value === undefined) return ''
    const num = parseFloat(value)
    return num >= 0 ? 'positive' : 'negative'
  }

  // Sort ETFs by symbol (TLT, IEF, IEI, PFF, PGF, KRE, IWM, SPY)
  const etfOrder = ['TLT', 'IEF', 'IEI', 'PFF', 'PGF', 'KRE', 'IWM', 'SPY']
  const sortedEtfData = [...etfData].sort((a, b) => {
    const aIndex = etfOrder.indexOf(a.symbol)
    const bIndex = etfOrder.indexOf(b.symbol)
    if (aIndex === -1 && bIndex === -1) return 0
    if (aIndex === -1) return 1
    if (bIndex === -1) return -1
    return aIndex - bIndex
  })

  return (
    <div className="etf-strip">
      <div className="etf-strip-content">
        {sortedEtfData.length > 0 ? (
          sortedEtfData.map(etf => (
            <div key={etf.symbol} className="etf-item">
              <div className="etf-symbol">{etf.symbol}</div>
              <div className="etf-last">{formatPrice(etf.last)}</div>
              <div className={`etf-change-percent ${getChangeColor(etf.daily_change_percent)}`}>
                {formatPercent(etf.daily_change_percent)}
              </div>
              <div className={`etf-change-cents ${getChangeColor(etf.daily_change_cents)}`}>
                {formatCents(etf.daily_change_cents)}
              </div>
            </div>
          ))
        ) : (
          <div className="etf-placeholder">Loading ETF data...</div>
        )}
      </div>
    </div>
  )
}

export default ETFStrip

