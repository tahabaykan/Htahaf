import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import DeeperAnalysisPanel from '../components/DeeperAnalysisPanel'
import './DeeperAnalysisPage.css'

const API_BASE = 'http://localhost:8000/api'

function DeeperAnalysisPage() {
  const [selectedSymbol, setSelectedSymbol] = useState(null)
  const [jobId, setJobId] = useState(null)
  const [jobStatus, setJobStatus] = useState(null)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Fetch deeper analysis data using worker (non-blocking)
  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    
    try {
      // Step 1: Start job
      const startResponse = await fetch(`${API_BASE}/deeper-analysis/compute`, {
        method: 'POST'
      })
      
      if (!startResponse.ok) {
        // Fallback to old endpoint if worker not available
        const fallbackResponse = await fetch(`${API_BASE}/market-data/deep-analysis/all`)
        const fallbackData = await fallbackResponse.json()
        setResult(fallbackData)
        setLoading(false)
        return
      }
      
      const startData = await startResponse.json()
      const newJobId = startData.job_id
      setJobId(newJobId)
      
      // Step 2: Poll for status
      const maxAttempts = 120 // 2 minutes max
      let attempts = 0
      
      const pollInterval = setInterval(async () => {
        attempts++
        
        try {
          const statusResponse = await fetch(`${API_BASE}/deeper-analysis/status/${newJobId}`)
          const statusData = await statusResponse.json()
          
          setJobStatus(statusData.status)
          
          if (statusData.status === 'completed') {
            clearInterval(pollInterval)
            
            // Step 3: Get result
            const resultResponse = await fetch(`${API_BASE}/deeper-analysis/result/${newJobId}`)
            const resultData = await resultResponse.json()
            
            if (resultData.success) {
              // resultData already contains {success, job_id, data, ...}
              // Pass the entire resultData to panel
              setResult(resultData)
            } else {
              setError(resultData.error || 'Failed to get result')
            }
            setLoading(false)
          } else if (statusData.status === 'failed') {
            clearInterval(pollInterval)
            setError(statusData.error || 'Job failed')
            setLoading(false)
          } else if (attempts >= maxAttempts) {
            clearInterval(pollInterval)
            setError('Timeout waiting for job completion')
            setLoading(false)
          }
        } catch (err) {
          clearInterval(pollInterval)
          setError(`Error checking status: ${err.message}`)
          setLoading(false)
        }
      }, 1000) // Poll every second
      
    } catch (err) {
      setError(`Error starting job: ${err.message}`)
      setLoading(false)
    }
  }, [])

  // Auto-refresh when enabled (15 minutes = 900000 ms)
  useEffect(() => {
    // Initial fetch
    fetchData()
    
    // Refresh every 15 minutes (900000 ms)
    const interval = setInterval(() => {
      fetchData()
    }, 900000)
    
    return () => clearInterval(interval)
  }, [fetchData])

  return (
    <div className="deeper-analysis-page">
      <div className="page-header">
        <div className="header-left">
          <h1>Deeper Analysis</h1>
          <p className="subtitle">Tick-by-tick analysis (GOD, ROD, GRPAN)</p>
        </div>
        <div className="header-right">
          <Link to="/scanner" className="btn btn-secondary">
            ← Back to Scanner
          </Link>
          <button 
            onClick={fetchData} 
            disabled={loading}
            className="btn btn-primary"
          >
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>

      {jobStatus && (
        <div className="job-status">
          <span className={`status-badge ${jobStatus}`}>
            {jobStatus === 'queued' && '⏳ Queued'}
            {jobStatus === 'processing' && '🔄 Processing...'}
            {jobStatus === 'completed' && '✅ Completed'}
            {jobStatus === 'failed' && '❌ Failed'}
          </span>
          {jobId && <span className="job-id">Job ID: {jobId}</span>}
        </div>
      )}

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      <div className="analysis-content">
        <DeeperAnalysisPanel 
          selectedSymbol={selectedSymbol}
          workerResult={result}
        />
      </div>
    </div>
  )
}

export default DeeperAnalysisPage
