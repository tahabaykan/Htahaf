import React, { useState, useEffect } from 'react'
import './JFINModal.css'
import JFINTabBB from './JFINTabBB'
import JFINTabFB from './JFINTabFB'
import JFINTabSAS from './JFINTabSAS'
import JFINTabSFS from './JFINTabSFS'

function JFINModal({ isOpen, onClose }) {
  const [activeTab, setActiveTab] = useState('BB')
  const [jfinState, setJfinState] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [percentage, setPercentage] = useState(50)

  useEffect(() => {
    if (isOpen) {
      loadJFINState()
      // Poll for updates every 2 seconds
      const interval = setInterval(loadJFINState, 2000)
      return () => clearInterval(interval)
    }
  }, [isOpen])

  const loadJFINState = async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await fetch('/api/psfalgo/jfin/state')
      const result = await response.json()
      
      if (result.success && result.state) {
        setJfinState(result.state)
        if (result.state.percentage) {
          setPercentage(result.state.percentage)
        }
        
        // Show helpful message if state is empty
        if (result.is_empty && result.message) {
          setError(result.message)
        } else if (result.is_empty && !result.runall_running) {
          setError('JFIN state is empty. Please start RUNALL to generate JFIN data.')
        } else {
          setError(null)
        }
      } else {
        setError(result.detail || result.error || 'Failed to load JFIN state')
      }
    } catch (err) {
      console.error('JFIN: Error loading state:', err)
      setError(err.message || 'Failed to load JFIN state')
    } finally {
      setLoading(false)
    }
  }

  const handleUpdatePercentage = async (newPercentage) => {
    try {
      setLoading(true)
      setError(null)
      const response = await fetch('/api/psfalgo/jfin/update-percentage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ percentage: newPercentage })
      })
      const result = await response.json()
      
      if (result.success) {
        setPercentage(newPercentage)
        await loadJFINState()
      } else {
        setError(result.detail || result.error || 'Failed to update percentage')
      }
    } catch (err) {
      console.error('JFIN: Error updating percentage:', err)
      setError(err.message || 'Failed to update percentage')
    } finally {
      setLoading(false)
    }
  }

  if (!isOpen) return null

  const tabs = [
    { id: 'BB', label: 'BB (Bid Buy)', count: jfinState?.bb_stocks?.length || 0 },
    { id: 'FB', label: 'FB (Front Buy)', count: jfinState?.fb_stocks?.length || 0 },
    { id: 'SAS', label: 'SAS (Ask Sell)', count: jfinState?.sas_stocks?.length || 0 },
    { id: 'SFS', label: 'SFS (Soft Front Sell)', count: jfinState?.sfs_stocks?.length || 0 }
  ]

  return (
    <div className="jfin-modal-overlay" onClick={onClose}>
      <div className="jfin-modal" onClick={(e) => e.stopPropagation()}>
        <div className="jfin-modal-header">
          <h2>JFIN - Final THG Lot Distributor</h2>
          <button className="jfin-modal-close" onClick={onClose}>×</button>
        </div>

        {error && (
          <div className="jfin-modal-error">
            ⚠️ {error}
          </div>
        )}

        <div className="jfin-modal-controls">
          <div className="jfin-percentage-controls">
            <label>JFIN Percentage:</label>
            <div className="jfin-percentage-buttons">
              {[25, 50, 75, 100].map(pct => (
                <button
                  key={pct}
                  className={`jfin-percentage-btn ${percentage === pct ? 'active' : ''}`}
                  onClick={() => handleUpdatePercentage(pct)}
                  disabled={loading}
                >
                  {pct}%
                </button>
              ))}
            </div>
            <span className="jfin-percentage-info">Current: {percentage}%</span>
          </div>
          <button className="jfin-refresh-btn" onClick={loadJFINState} disabled={loading}>
            {loading ? '⏳ Loading...' : '🔄 Refresh'}
          </button>
        </div>

        <div className="jfin-modal-tabs">
          {tabs.map(tab => (
            <button
              key={tab.id}
              className={`jfin-tab-btn ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label} ({tab.count})
            </button>
          ))}
        </div>

        <div className="jfin-modal-content">
          {loading && !jfinState ? (
            <div className="jfin-loading">Loading JFIN state...</div>
          ) : error && error.includes('empty') ? (
            <div className="jfin-empty-state">
              <div className="jfin-empty-icon">📊</div>
              <div className="jfin-empty-title">JFIN State is Empty</div>
              <div className="jfin-empty-message">
                {error}
              </div>
              <div className="jfin-empty-instructions">
                <p><strong>To populate JFIN data:</strong></p>
                <ol>
                  <li>Go to PSFALGO page</li>
                  <li>Click "▶️ Start RUNALL" button</li>
                  <li>Wait for RUNALL to complete a few cycles</li>
                  <li>ADDNEWPOS → JFIN transform will populate the data</li>
                </ol>
                <p className="jfin-empty-note">
                  JFIN state is automatically populated when RUNALL executes ADDNEWPOS cycle.
                </p>
              </div>
            </div>
          ) : (
            <>
              {activeTab === 'BB' && (
                <JFINTabBB stocks={jfinState?.bb_stocks || []} />
              )}
              {activeTab === 'FB' && (
                <JFINTabFB stocks={jfinState?.fb_stocks || []} />
              )}
              {activeTab === 'SAS' && (
                <JFINTabSAS stocks={jfinState?.sas_stocks || []} />
              )}
              {activeTab === 'SFS' && (
                <JFINTabSFS stocks={jfinState?.sfs_stocks || []} />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default JFINModal

