import React, { useState, useEffect, useMemo } from 'react'
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
  const [filteredData, setFilteredData] = useState({ BB: [], FB: [], SAS: [], SFS: [] })

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

  // Calculate exposure metrics for active tab
  const exposureMetrics = useMemo(() => {
    if (!jfinState) return null;
    
    // Get stocks for active tab (use filtered if available, otherwise use all)
    let activeStocks = [];
    if (activeTab === 'BB') {
      activeStocks = filteredData.BB?.length > 0 ? filteredData.BB : (jfinState.bb_stocks || []);
    } else if (activeTab === 'FB') {
      activeStocks = filteredData.FB?.length > 0 ? filteredData.FB : (jfinState.fb_stocks || []);
    } else if (activeTab === 'SAS') {
      activeStocks = filteredData.SAS?.length > 0 ? filteredData.SAS : (jfinState.sas_stocks || []);
    } else if (activeTab === 'SFS') {
      activeStocks = filteredData.SFS?.length > 0 ? filteredData.SFS : (jfinState.sfs_stocks || []);
    }
    
    // Calculate Est. Consumption = sum(final_lot) × 20
    const totalLots = activeStocks.reduce((sum, s) => sum + (s.final_lot || 0), 0);
    const estConsumption = totalLots * 20;
    
    // Get current and max exposure from account_state
    const accountState = jfinState.account_state;
    const currentExposure = accountState?.pot_total || accountState?.total_exposure || 0;
    const maxExposure = accountState?.limit_max_exposure || accountState?.pot_max || 0;
    
    // Calculate ratios
    const estToCurrent = currentExposure > 0 ? (estConsumption / currentExposure * 100) : 0;
    const estToMax = maxExposure > 0 ? (estConsumption / maxExposure * 100) : 0;
    
    return {
      totalLots,
      estConsumption,
      currentExposure,
      maxExposure,
      estToCurrent,
      estToMax
    };
  }, [jfinState, activeTab, filteredData]);

  // Handler for filtered data from tabs
  const handleFilteredDataChange = (tabId, data) => {
    setFilteredData(prev => ({ ...prev, [tabId]: data }));
  };

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
          
          {/* Exposure Estimation Panel */}
          {exposureMetrics && (
            <div className="jfin-exposure-panel">
              {/* Row 1: Total Lots & Est. Consumption */}
              <div className="jfin-exposure-row">
                <div className="jfin-exposure-item">
                  <span className="jfin-exposure-label">📦 Total Lots ({activeTab}):</span>
                  <span className="jfin-exposure-value highlight-blue">
                    {exposureMetrics.totalLots.toLocaleString()}
                  </span>
                </div>
                <div className="jfin-exposure-item">
                  <span className="jfin-exposure-label">💰 Est. Cons:</span>
                  <span className="jfin-exposure-value highlight">
                    ${exposureMetrics.estConsumption.toLocaleString()}
                  </span>
                  <span className="jfin-exposure-note">({exposureMetrics.totalLots.toLocaleString()} × $20)</span>
                </div>
              </div>
              
              {/* Row 2: Current & Max Exposure */}
              <div className="jfin-exposure-row">
                <div className="jfin-exposure-item">
                  <span className="jfin-exposure-label">📊 Current Exposure:</span>
                  <span className="jfin-exposure-value highlight-cyan">
                    ${exposureMetrics.currentExposure.toLocaleString()}
                  </span>
                </div>
                <div className="jfin-exposure-item">
                  <span className="jfin-exposure-label">🎯 Max Exposure:</span>
                  <span className="jfin-exposure-value highlight-orange">
                    ${exposureMetrics.maxExposure.toLocaleString()}
                  </span>
                </div>
              </div>
              
              {/* Row 3: Ratios */}
              {(exposureMetrics.currentExposure > 0 || exposureMetrics.maxExposure > 0) && (
                <div className="jfin-exposure-ratios">
                  <span className="jfin-ratio-item" title="Estimated Consumption / Current Exposure">
                    Est/Cur: <span className={`jfin-ratio-value ${exposureMetrics.estToCurrent > 25 ? 'warning' : ''}`}>
                      {exposureMetrics.estToCurrent.toFixed(1)}%
                    </span>
                  </span>
                  <span className="jfin-ratio-separator">|</span>
                  <span className="jfin-ratio-item" title="Estimated Consumption / Max Exposure">
                    Est/Max: <span className={`jfin-ratio-value ${exposureMetrics.estToMax > 15 ? 'warning' : ''}`}>
                      {exposureMetrics.estToMax.toFixed(1)}%
                    </span>
                  </span>
                  <span className="jfin-ratio-separator">|</span>
                  <span className="jfin-ratio-item" title="Current Exposure / Max Exposure">
                    Cur/Max: <span className={`jfin-ratio-value ${(exposureMetrics.currentExposure / exposureMetrics.maxExposure * 100) > 90 ? 'warning' : ''}`}>
                      {exposureMetrics.maxExposure > 0 ? (exposureMetrics.currentExposure / exposureMetrics.maxExposure * 100).toFixed(1) : 0}%
                    </span>
                  </span>
                </div>
              )}
            </div>
          )}
          
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
                <JFINTabBB 
                  stocks={jfinState?.bb_stocks || []} 
                  onFilteredDataChange={(data) => handleFilteredDataChange('BB', data)}
                />
              )}
              {activeTab === 'FB' && (
                <JFINTabFB 
                  stocks={jfinState?.fb_stocks || []} 
                  onFilteredDataChange={(data) => handleFilteredDataChange('FB', data)}
                />
              )}
              {activeTab === 'SAS' && (
                <JFINTabSAS 
                  stocks={jfinState?.sas_stocks || []} 
                  onFilteredDataChange={(data) => handleFilteredDataChange('SAS', data)}
                />
              )}
              {activeTab === 'SFS' && (
                <JFINTabSFS 
                  stocks={jfinState?.sfs_stocks || []} 
                  onFilteredDataChange={(data) => handleFilteredDataChange('SFS', data)}
                />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default JFINModal

