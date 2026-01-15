import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import DecisionHelperPanel from '../components/DecisionHelperPanel'
import './DecisionHelperPage.css'

const API_BASE = 'http://localhost:8000/api'

function DecisionHelperPage() {
  const [jobId, setJobId] = useState(null)
  const [jobStatus, setJobStatus] = useState(null)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Fetch decision helper data using worker (non-blocking)
  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    
    try {
      // Step 1: Start job
      const startResponse = await fetch(`${API_BASE}/decision-helper/compute`, {
        method: 'POST'
      })
      
      if (!startResponse.ok) {
        const errorData = await startResponse.json()
        setError(errorData.error || 'Failed to start decision helper job')
        setLoading(false)
        return
      }
      
      const startData = await startResponse.json()
      const newJobId = startData.job_id
      setJobId(newJobId)
      setJobStatus('queued')
      
      // Step 2: Poll for completion (simplified - worker writes directly to Redis)
      // For now, wait a bit then fetch results
      setTimeout(async () => {
        try {
          // Fetch results from Redis (worker writes them directly)
          // We'll need to get all groups and symbols
          const groupsResponse = await fetch(`${API_BASE}/market-data/merged`)
          const groupsData = await groupsResponse.json()
          
          if (groupsData.success && groupsData.data) {
            // Extract unique groups
            const groups = [...new Set(groupsData.data.map(r => r.GROUP).filter(Boolean))]
            
            // Fetch results for each group
            const allResults = {}
            for (const group of groups) {
              try {
                const groupResponse = await fetch(`${API_BASE}/decision-helper/results/${group}`)
                const groupData = await groupResponse.json()
                if (groupData.success && groupData.data) {
                  allResults[group] = groupData.data
                }
              } catch (err) {
                console.error(`Error fetching results for group ${group}:`, err)
              }
            }
            
            setResult({ groups: allResults })
            setJobStatus('completed')
          }
        } catch (err) {
          setError(`Error fetching results: ${err.message}`)
          setJobStatus('failed')
        } finally {
          setLoading(false)
        }
      }, 10000) // Wait 10 seconds for worker to process
      
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
    <div className="decision-helper-page">
      <div className="page-header">
        <Link to="/" className="back-link">← Back to Scanner</Link>
        <h1>🎯 Decision Helper</h1>
        <p className="page-description">
          Market state classification based on tick-by-tick analysis
        </p>
      </div>

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      <DecisionHelperPanel 
        workerResult={result}
        loading={loading}
        jobStatus={jobStatus}
        onRefresh={fetchData}
      />
    </div>
  )
}

export default DecisionHelperPage


