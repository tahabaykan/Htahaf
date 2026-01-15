import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import TruthTicksPanel from '../components/TruthTicksPanel'
import './TruthTicksPage.css'

const API_BASE = 'http://localhost:8000/api'

function TruthTicksPage() {
  const [jobId, setJobId] = useState(null)
  const [result, setResult] = useState(null)
  const [dominanceScores, setDominanceScores] = useState(null)
  const [selectedTimeframe, setSelectedTimeframe] = useState('TF_1D')  // Default: 1 day
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [refreshInterval, setRefreshInterval] = useState(null)

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
      const submitResponse = await fetch(`${API_BASE}/truth-ticks/submit-job`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          symbols: null  // Process all symbols
        })
      })
      
      if (!submitResponse.ok) {
        const errorData = await submitResponse.json()
        setError(errorData.detail || 'Failed to submit Truth Ticks job')
        setLoading(false)
        return
      }
      
      const submitData = await submitResponse.json()
      const newJobId = submitData.job_id
      setJobId(newJobId)
      
      // Step 2: Poll for results (worker may need time to bootstrap and process)
      const pollForResults = async (attempt = 1, maxAttempts = 20) => {
        try {
          // First, try to get all results from cache (most reliable - gets latest completed job)
          const allResultsResponse = await fetch(`${API_BASE}/truth-ticks/result/all`)
          if (allResultsResponse.ok) {
            const allResultsData = await allResultsResponse.json()
            if (allResultsData.success && allResultsData.data && Object.keys(allResultsData.data).length > 0) {
              setResult({
                job_id: allResultsData.job_id || newJobId,
                data: allResultsData.data,
                processed_count: allResultsData.count,
                updated_at: allResultsData.updated_at,
                message: allResultsData.message || 'Results from latest job cache'
              })
              
              // Fetch dominance scores for selected timeframe
              try {
                const dominanceResponse = await fetch(`${API_BASE}/truth-ticks/dominance-scores?timeframe=${selectedTimeframe}`)
                if (dominanceResponse.ok) {
                  const dominanceData = await dominanceResponse.json()
                  if (dominanceData.success && dominanceData.data) {
                    setDominanceScores(dominanceData.data)
                  }
                }
              } catch (e) {
                console.warn('Failed to fetch dominance scores:', e)
              }
              
              setLoading(false)
              return
            }
          }
          
          // Fallback: Try to get result by specific job_id
          const resultResponse = await fetch(`${API_BASE}/truth-ticks/result/${newJobId}`)
          if (resultResponse.ok) {
            const resultData = await resultResponse.json()
            if (resultData.success && resultData.result) {
              setResult(resultData.result)
              
              // Fetch dominance scores for selected timeframe
              try {
                const dominanceResponse = await fetch(`${API_BASE}/truth-ticks/dominance-scores?timeframe=${selectedTimeframe}`)
                if (dominanceResponse.ok) {
                  const dominanceData = await dominanceResponse.json()
                  if (dominanceData.success && dominanceData.data) {
                    setDominanceScores(dominanceData.data)
                  }
                }
              } catch (e) {
                console.warn('Failed to fetch dominance scores:', e)
              }
              
              setLoading(false)
              return
            }
          }
          // 404 is normal - job may still be processing, don't log as error
          
          // No results yet, wait and retry
          if (attempt < maxAttempts) {
            // Progressive delay: start with 3 seconds, increase to 5 seconds after 5 attempts
            const delay = attempt <= 5 ? 3000 : 5000
            setTimeout(() => pollForResults(attempt + 1, maxAttempts), delay)
          } else {
            setError('No results available after waiting. Worker may still be processing. Try refreshing in a moment.')
            setLoading(false)
          }
        } catch (e) {
          if (attempt >= maxAttempts) {
            setError(`Error fetching results: ${e.message}`)
            setLoading(false)
          } else {
            // Retry on error with delay
            setTimeout(() => pollForResults(attempt + 1, maxAttempts), 5000)
          }
        }
      }
      
      // Start polling after initial delay (worker needs time to bootstrap)
      setTimeout(() => pollForResults(), 20000)  // Wait 20 seconds initially for bootstrap
      
    } catch (e) {
      setError(`Error submitting job: ${e.message}`)
      setLoading(false)
    }
  }, [loading, selectedTimeframe])

  // Auto refresh
  useEffect(() => {
    if (autoRefresh && !refreshInterval) {
      const interval = setInterval(() => {
        fetchData()
      }, 60000)  // Refresh every 60 seconds
      setRefreshInterval(interval)
    } else if (!autoRefresh && refreshInterval) {
      clearInterval(refreshInterval)
      setRefreshInterval(null)
    }
    
    return () => {
      if (refreshInterval) {
        clearInterval(refreshInterval)
      }
    }
  }, [autoRefresh, fetchData, refreshInterval])

  return (
    <div className="truth-ticks-page">
      <div className="page-header">
        <h1>📊 Truth Ticks Analysis</h1>
        <Link to="/" className="back-link">← Back to Scanner</Link>
      </div>
      
      <div className="page-controls">
        <button
          onClick={fetchData}
          disabled={loading}
          className="btn btn-primary"
        >
          {loading ? 'Processing...' : 'Run Analysis'}
        </button>
        
        <Link
          to="/aura-mm"
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-secondary"
          style={{ textDecoration: 'none', display: 'inline-block' }}
          title="Open Aura Table MM Screener in new tab"
        >
          🎯 Aura Table MM
        </Link>
        
        <label className="timeframe-select-label">
          Timeframe:
          <select 
            value={selectedTimeframe}
            onChange={async (e) => {
              const newTimeframe = e.target.value
              setSelectedTimeframe(newTimeframe)
              // Refetch dominance scores when timeframe changes
              try {
                const dominanceResponse = await fetch(`${API_BASE}/truth-ticks/dominance-scores?timeframe=${newTimeframe}`)
                if (dominanceResponse.ok) {
                  const dominanceData = await dominanceResponse.json()
                  if (dominanceData.success && dominanceData.data) {
                    setDominanceScores(dominanceData.data)
                    console.log(`✅ Fetched ${Object.keys(dominanceData.data).length} dominance scores for ${newTimeframe}`)
                  } else {
                    console.warn(`⚠️ No dominance data for ${newTimeframe}`)
                    setDominanceScores({})
                  }
                }
              } catch (e) {
                console.error('Failed to fetch dominance scores:', e)
              }
            }}
            className="timeframe-select"
          >
            <option value="TF_4H">4 Hours</option>
            <option value="TF_1D">1 Day</option>
            <option value="TF_3D">3 Days</option>
            <option value="TF_5D">5 Days</option>
          </select>
        </label>
        
        <label className="auto-refresh-label">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />
          Auto Refresh (60s)
        </label>
      </div>
      
      {error && (
        <div className="error-message">
          ❌ {error}
        </div>
      )}
      
      {jobId && (
        <div className="job-info">
          Job ID: {jobId}
        </div>
      )}
      
      <TruthTicksPanel
        result={result}
        dominanceScores={dominanceScores}
        selectedTimeframe={selectedTimeframe}
        loading={loading}
      />
    </div>
  )
}

export default TruthTicksPage



