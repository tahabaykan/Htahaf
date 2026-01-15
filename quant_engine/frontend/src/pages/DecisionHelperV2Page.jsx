import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import DecisionHelperV2Panel from '../components/DecisionHelperV2Panel'
import './DecisionHelperV2Page.css'

const API_BASE = 'http://localhost:8000/api'

function DecisionHelperV2Page() {
  const [jobId, setJobId] = useState(null)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedWindow, setSelectedWindow] = useState('pan_30m')
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [refreshInterval, setRefreshInterval] = useState(null)

  // Available windows
  const windows = ['pan_10m', 'pan_30m', 'pan_1h', 'pan_3h', 'pan_1d']

  // Submit job and fetch results
  const fetchData = useCallback(async () => {
    // Prevent multiple simultaneous calls
    if (loading) {
      return
    }
    
    setLoading(true)
    setError(null)
    
    try {
      // Step 1: Submit job
      const submitResponse = await fetch(`${API_BASE}/decision-helper-v2/submit-job`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          symbols: null,  // Process all symbols
          windows: windows
        })
      })
      
      if (!submitResponse.ok) {
        const errorData = await submitResponse.json()
        setError(errorData.detail || 'Failed to submit DecisionHelperV2 job')
        setLoading(false)
        return
      }
      
      const submitData = await submitResponse.json()
      const newJobId = submitData.job_id
      setJobId(newJobId)
      
      // Step 2: Poll for results (worker may need time to bootstrap and process)
      // Worker writes results directly to Redis, so we poll for them
      const pollForResults = async (attempt = 1, maxAttempts = 12) => {
        try {
          // Get symbols list
          let symbols = []
          
          try {
            const symbolsResponse = await fetch(`${API_BASE}/market-data/merged`)
            if (symbolsResponse.ok) {
              const symbolsData = await symbolsResponse.json()
              if (symbolsData.success && symbolsData.data) {
                // Extract symbols from merged data
                // PREF_IBKR is the primary field, but also check symbol field
                symbols = symbolsData.data.map(r => {
                  // Try PREF_IBKR first (this is the symbol key in static store)
                  return r['PREF_IBKR'] || r['PREF IBKR'] || r.symbol || r['PREF_IBKR']
                }).filter(Boolean)
              }
            }
          } catch (e) {
            // If merged endpoint fails, try data-fabric endpoint
            try {
              const fabricResponse = await fetch(`${API_BASE}/data-fabric/symbols`)
              if (fabricResponse.ok) {
                const fabricData = await fabricResponse.json()
                if (fabricData.symbols) {
                  symbols = fabricData.symbols
                }
              }
            } catch (e2) {
              console.warn('Could not fetch symbols list:', e2)
            }
          }
          
          if (symbols.length === 0) {
            // No symbols yet, wait and retry
            if (attempt < maxAttempts) {
              setTimeout(() => pollForResults(attempt + 1, maxAttempts), 5000)
            } else {
              setError('Could not fetch symbols list. Worker may still be bootstrapping.')
              setLoading(false)
            }
            return
          }
          
          // Fetch results for each symbol and window
          const allResults = {}
          let fetchedCount = 0
          
          // Fetch all symbols (no limit) - worker already processed 439 symbols
          for (const symbol of symbols) {
            for (const window of windows) {
              try {
                const resultResponse = await fetch(`${API_BASE}/decision-helper-v2/result/${encodeURIComponent(symbol)}/${window}`)
                if (resultResponse.ok) {
                  const resultData = await resultResponse.json()
                  if (!allResults[symbol]) {
                    allResults[symbol] = {}
                  }
                  allResults[symbol][window] = resultData
                  fetchedCount++
                }
              } catch (e) {
                // Skip if result not available
              }
            }
          }
          
          // If we got some results, show them. Otherwise, retry if we haven't exceeded max attempts
          if (fetchedCount > 0 || attempt >= maxAttempts) {
            setResult({
              job_id: newJobId,
              data: allResults,
              fetched_count: fetchedCount,
              message: fetchedCount === 0 ? 'No results yet. Worker may still be processing. Try refreshing in a moment.' : null
            })
            setLoading(false)
          } else {
            // No results yet, wait and retry
            setTimeout(() => pollForResults(attempt + 1, maxAttempts), 5000)
          }
        } catch (e) {
          if (attempt >= maxAttempts) {
            setError(`Error fetching results: ${e.message}`)
            setLoading(false)
          } else {
            // Retry on error
            setTimeout(() => pollForResults(attempt + 1, maxAttempts), 5000)
          }
        }
      }
      
      // Start polling after initial delay (worker needs time to bootstrap)
      setTimeout(() => pollForResults(), 15000)  // Wait 15 seconds initially for bootstrap
      
    } catch (e) {
      setError(`Error submitting job: ${e.message}`)
      setLoading(false)
    }
  }, [windows, loading])

  // Auto-refresh logic
  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(() => {
        fetchData()
      }, 15 * 60 * 1000)  // 15 minutes
      setRefreshInterval(interval)
    } else {
      if (refreshInterval) {
        clearInterval(refreshInterval)
        setRefreshInterval(null)
      }
    }
    
    return () => {
      if (refreshInterval) {
        clearInterval(refreshInterval)
      }
    }
  }, [autoRefresh, fetchData])

  // Initial fetch - only once on mount
  useEffect(() => {
    // Only fetch if we don't have result yet
    if (!result && !loading) {
      fetchData()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])  // Empty dependency array - only run once on mount

  return (
    <div className="decision-helper-v2-page">
      <div className="page-header">
        <h1>Decision Helper V2 - Modal Price Flow</h1>
        <div className="header-actions">
          <button
            onClick={fetchData}
            disabled={loading}
            className="refresh-button"
          >
            {loading ? 'Loading...' : '🔄 Refresh'}
          </button>
          <label className="auto-refresh-toggle">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Auto-refresh (15 min)
          </label>
          <Link to="/" className="back-link">← Back to Scanner</Link>
        </div>
      </div>

      {error && (
        <div className="error-message">
          ❌ Error: {error}
        </div>
      )}

      {loading && !result && (
        <div className="loading-message">
          ⏳ Submitting job and waiting for results...
        </div>
      )}

      {result && (
        <div className="results-container">
          <div className="window-selector">
            <label>Window: </label>
            <select
              value={selectedWindow}
              onChange={(e) => setSelectedWindow(e.target.value)}
            >
              {windows.map(w => (
                <option key={w} value={w}>{w}</option>
              ))}
            </select>
          </div>
          
          <DecisionHelperV2Panel
            data={result.data}
            selectedWindow={selectedWindow}
          />
        </div>
      )}

      <div className="info-box">
        <h3>About Decision Helper V2</h3>
        <ul>
          <li><strong>Modal Price Flow:</strong> Uses GRPAN1 modal displacement instead of first/last trade</li>
          <li><strong>Illiquid-Safe:</strong> Designed for sparse trading environments</li>
          <li><strong>Real Flow Score (RFS):</strong> Composite score combining multiple factors</li>
          <li><strong>Windows:</strong> 10m, 30m, 1h, 3h, 1d</li>
        </ul>
      </div>
    </div>
  )
}

export default DecisionHelperV2Page


