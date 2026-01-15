import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import './AuraMMPage.css'

const API_BASE = 'http://localhost:8000/api'

function AuraMMPage() {
  const [mmScores, setMmScores] = useState({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [mode, setMode] = useState('MARKET_CLOSED')
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [refreshInterval, setRefreshInterval] = useState(null)
  const [sortBy, setSortBy] = useState('mm_score')
  const [sortDirection, setSortDirection] = useState('desc')
  const [searchFilter, setSearchFilter] = useState('')
  const [stats, setStats] = useState({ included: 0, excluded: 0, total: 0 })

  // Fetch MM scores
  const fetchMmScores = useCallback(async () => {
    if (loading) return
    
    setLoading(true)
    setError(null)
    
    try {
      const response = await fetch(`${API_BASE}/aura-mm/scores?mode=${mode}`)
      
      if (!response.ok) {
        const errorData = await response.json()
        setError(errorData.detail || 'Failed to fetch MM scores')
        setLoading(false)
        return
      }
      
      const data = await response.json()
      
      console.log('🔍 Aura MM API Response:', {
        success: data.success,
        count: data.count,
        mode: data.mode,
        dataKeys: data.data ? Object.keys(data.data).slice(0, 5) : [],
        firstSymbol: data.data ? Object.keys(data.data)[0] : null,
        firstSymbolData: data.data ? data.data[Object.keys(data.data)[0]] : null
      })
      
      if (data.success) {
        setMmScores(data.data || {})
        setStats({
          included: data.included_count || 0,
          excluded: data.excluded_count || 0,
          total: data.count || 0
        })
        if (Object.keys(data.data || {}).length === 0) {
          console.warn('⚠️ Aura MM: API returned success but data is empty')
        }
      } else {
        setError(data.message || 'Failed to fetch MM scores')
      }
    } catch (err) {
      setError(err.message || 'Network error')
    } finally {
      setLoading(false)
    }
  }, [mode, loading])

  // Auto refresh
  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(() => {
        fetchMmScores()
      }, 60000) // 60 seconds
      setRefreshInterval(interval)
      
      return () => clearInterval(interval)
    } else {
      if (refreshInterval) {
        clearInterval(refreshInterval)
        setRefreshInterval(null)
      }
    }
  }, [autoRefresh, fetchMmScores])

  // Initial load
  useEffect(() => {
    fetchMmScores()
  }, [mode])

  // Filter and sort data
  const filteredSymbols = Object.entries(mmScores).filter(([symbol]) => {
    if (!searchFilter) return true
    return symbol.toLowerCase().includes(searchFilter.toLowerCase())
  })
  
  const sortedSymbols = filteredSymbols.sort((a, b) => {
    const aValue = a[1]?.[sortBy] || 0
    const bValue = b[1]?.[sortBy] || 0
    
    if (sortDirection === 'asc') {
      return aValue - bValue
    } else {
      return bValue - aValue
    }
  })

  const handleSort = (column) => {
    if (sortBy === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(column)
      setSortDirection('desc')
    }
  }

  const formatCurrency = (value) => {
    if (value === null || value === undefined) return 'N/A'
    return `$${value.toFixed(2)}`
  }

  const formatPercent = (value) => {
    if (value === null || value === undefined) return 'N/A'
    return `${(value * 100).toFixed(1)}%`
  }

  const getScoreColor = (score) => {
    if (score >= 70) return '#10b981' // green
    if (score >= 50) return '#f59e0b' // yellow
    if (score >= 30) return '#ef4444' // red
    return '#6b7280' // gray
  }

  return (
    <div className="aura-mm-page">
      <div className="page-header">
        <h1>🎯 Aura Table MM</h1>
        <p>Market Making Screener & Scoring Engine</p>
      </div>

      <div className="controls">
        <div className="control-group">
          <label>
            <input
              type="text"
              placeholder="Search symbol..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              style={{
                padding: '6px 12px',
                border: '1px solid #d1d5db',
                borderRadius: '4px',
                fontSize: '14px',
                width: '200px',
                color: '#1f2937',
                backgroundColor: '#ffffff'
              }}
            />
          </label>
        </div>

        <div className="control-group">
          <label>
            Mode:
            <select value={mode} onChange={(e) => setMode(e.target.value)} style={{
              padding: '6px 12px',
              border: '1px solid #d1d5db',
              borderRadius: '4px',
              fontSize: '14px',
              color: '#1f2937',
              backgroundColor: '#ffffff'
            }}>
              <option value="MARKET_CLOSED">Tradeable MM</option>
              <option value="MARKET_CLOSED_BIAS">Bias / Watchlist</option>
              <option value="MARKET_LIVE">Market Live</option>
            </select>
          </label>
        </div>

        <div className="control-group">
          <label>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Auto Refresh (60s)
          </label>
        </div>

        <button onClick={fetchMmScores} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div className="error-message">
          ⚠️ {error}
        </div>
      )}

      <div className="stats-bar" style={{ color: '#1f2937' }}>
        <span>
          Showing {filteredSymbols.length} / {stats.total} symbols
          {mode === 'MARKET_CLOSED' || mode === 'MARKET_LIVE' ? ' (Tradeable MM only)' : ' (Bias / Watchlist)'}
        </span>
        {stats.excluded > 0 && (
          <span style={{ color: '#6b7280', fontSize: '0.875rem' }}>
            ({stats.included} included, {stats.excluded} excluded)
          </span>
        )}
        {searchFilter && <span>Filtered: {filteredSymbols.length} symbols</span>}
      </div>

      <div className="table-container">
        <table className="aura-mm-table">
          <thead>
            <tr>
              <th onClick={() => handleSort('symbol')}>
                Symbol {sortBy === 'symbol' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('mm_score')} className="sortable" title={mode === 'MARKET_CLOSED_BIAS' ? 'Structural bias score (Bias)' : 'Execution score (Tradeable)'}>
                MM Score {sortBy === 'mm_score' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th>Reason / Flags</th>
              <th onClick={() => handleSort('gap')} className="sortable">
                Gap {sortBy === 'gap' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('net_gap')} className="sortable">
                Net Gap {sortBy === 'net_gap' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('fast_cycles')} className="sortable">
                Fast Cycles {sortBy === 'fast_cycles' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('mm_value')} className="sortable">
                MM Value {sortBy === 'mm_value' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('balance')} className="sortable">
                Balance {sortBy === 'balance' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              {mode === 'MARKET_LIVE' && (
                <>
                  <th>Spread</th>
                  <th>Bid</th>
                  <th>Ask</th>
                </>
              )}
              <th>Size</th>
              {mode === 'MARKET_LIVE' ? (
                <>
              <th>Trade Quote (Buy)</th>
              <th>Trade Quote (Sell)</th>
                  <th>Expected Profit</th>
                </>
              ) : (
                <>
              <th>Anchor Zone 1 (Buy)</th>
              <th>Anchor Zone 2 (Sell)</th>
                  <th>Expected Profit</th>
                </>
              )}
              <th>Confidence</th>
              <th>AVG_ADV</th>
            </tr>
          </thead>
          <tbody>
            {sortedSymbols.map(([symbol, data]) => {
              const mmScore = data?.mm_score || 0
              const recommendations = data?.recommendations || {}
              const anchorDetails = recommendations.anchor_details || {}
              const buyAnchor = anchorDetails.buy_anchor
              const sellAnchor = anchorDetails.sell_anchor
              
              // Get ping-pong metrics
              const gap = data?.gap || 0
              const netGap = data?.net_gap || 0
              const fastCycles = data?.fast_cycles || 0
              const mmValue = data?.mm_value || 0
              const balance = data?.balance || 0
              const volAPct = data?.vol_A_pct || 0
              const volBPct = data?.vol_B_pct || 0
              const aLow = data?.a_low
              const bHigh = data?.b_high
              const lastAltTime = data?.last_fast_alt_time
              
              // Get expected profit for suggested size
              const suggestedSize = recommendations.suggested_size || 500
              const profitKey = `size_${suggestedSize}`
              const expectedProfitData = recommendations.expected_profit?.[profitKey]
              const expectedProfit = expectedProfitData?.net || expectedProfitData?.gross || 0
              const profitStatus = recommendations.expected_profit?.status
              
              // Get reasoning
              const reasoning = data?.mm_reasoning || {}
              const isIncluded = reasoning.included || false
              const exclusionReasons = reasoning.exclusion_reasons || []
              const inclusionReasons = reasoning.inclusion_reasons || []
              const reasoningMode = reasoning.mode || 'TRADEABLE_MM'
              
              // Format reasoning for display
              const formatReasoning = () => {
                if (isIncluded) {
                  if (inclusionReasons.length > 0) {
                    return (
                      <div style={{ fontSize: '0.75rem' }}>
                        <span style={{ color: '#10b981', fontWeight: 'bold' }}>
                          {reasoningMode === 'TRADEABLE_MM' ? 'Tradeable' : 'Bias'}: 
                        </span>
                        <span style={{ color: '#1f2937' }}>
                          {inclusionReasons.join(' + ')}
                        </span>
                      </div>
                    )
                  }
                  return <span style={{ color: '#10b981' }}>✓ Included</span>
                } else {
                  if (exclusionReasons.length > 0) {
                    return (
                      <div style={{ fontSize: '0.75rem' }}>
                        <span style={{ color: '#ef4444', fontWeight: 'bold' }}>Excluded: </span>
                        <span style={{ color: '#6b7280' }}>{exclusionReasons.join(', ')}</span>
                      </div>
                    )
                  }
                  return <span style={{ color: '#9ca3af' }}>Not included</span>
                }
              }
              
              return (
                <tr key={symbol}>
                  <td className="symbol-cell">{symbol}</td>
                  <td className="score-cell" style={{ color: getScoreColor(mmScore) }}>
                    {mmScore.toFixed(1)}
                  </td>
                  <td className="reasoning-cell" style={{ fontSize: '0.75rem', maxWidth: '200px' }}>
                    {formatReasoning()}
                  </td>
                  <td className="gap-cell">
                    {formatCurrency(gap)}
                  </td>
                  <td className="net-gap-cell">
                    {formatCurrency(netGap)}
                  </td>
                  <td className="cycles-cell">
                    {fastCycles}
                  </td>
                  <td className="mm-value-cell" style={{ color: mmValue >= 0.20 ? '#10b981' : mmValue >= 0.10 ? '#f59e0b' : '#6b7280' }}>
                    {formatCurrency(mmValue)}
                  </td>
                  <td className="balance-cell">
                    {formatPercent(balance)}
                  </td>
                  {mode === 'MARKET_LIVE' && (
                    <>
                      <td>{formatCurrency(data?.spread)}</td>
                      <td>{formatCurrency(data?.bid)}</td>
                      <td>{formatCurrency(data?.ask)}</td>
                    </>
                  )}
                  <td>{recommendations.suggested_size || 'N/A'}</td>
                  {mode === 'MARKET_LIVE' ? (
                    <>
                      <td>
                        {recommendations.tradeable_mm && recommendations.buy_price ? (
                          <div>
                            <div style={{ color: '#1f2937' }}>{formatCurrency(recommendations.buy_price)}</div>
                            {aLow && (
                              <div style={{ fontSize: '0.75rem', color: '#4b5563', marginTop: '2px' }}>
                                A: {formatCurrency(aLow)}
                              </div>
                            )}
                          </div>
                        ) : (
                          <span style={{ color: '#9ca3af', fontSize: '0.75rem' }}>
                            {recommendations.tradeable_reason || 'N/A'}
                          </span>
                        )}
                      </td>
                      <td>
                        {recommendations.tradeable_mm && recommendations.sell_price ? (
                          <div>
                            <div style={{ color: '#1f2937' }}>{formatCurrency(recommendations.sell_price)}</div>
                            {bHigh && (
                              <div style={{ fontSize: '0.75rem', color: '#4b5563', marginTop: '2px' }}>
                                B: {formatCurrency(bHigh)}
                              </div>
                            )}
                          </div>
                        ) : (
                          <span style={{ color: '#9ca3af', fontSize: '0.75rem' }}>
                            {recommendations.tradeable_reason || 'N/A'}
                          </span>
                        )}
                      </td>
                      <td className="profit-cell">
                        {profitStatus ? (
                          <span style={{ color: '#ef4444', fontSize: '0.75rem' }}>{profitStatus}</span>
                        ) : (
                          formatCurrency(expectedProfit)
                        )}
                      </td>
                    </>
                  ) : (
                    <>
                      <td>{aLow ? formatCurrency(aLow) : 'N/A'}</td>
                      <td>{bHigh ? formatCurrency(bHigh) : 'N/A'}</td>
                      <td className="profit-cell" style={{ color: profitStatus ? '#ef4444' : (expectedProfit > 0 ? '#10b981' : '#6b7280') }}>
                        {profitStatus ? (
                          <span style={{ fontSize: '0.75rem' }}>{profitStatus}</span>
                        ) : (
                          expectedProfit !== 0 ? formatCurrency(expectedProfit) : 'N/A'
                        )}
                      </td>
                    </>
                  )}
                  <td>
                    {volAPct > 0 || volBPct > 0 ? (
                      <div style={{ fontSize: '0.75rem' }}>
                        <div>A: {volAPct.toFixed(1)}%</div>
                        <div>B: {volBPct.toFixed(1)}%</div>
                      </div>
                    ) : 'N/A'}
                  </td>
                  <td style={{ fontSize: '0.75rem' }}>
                    {lastAltTime ? (
                      <span title={new Date(lastAltTime * 1000).toLocaleString()}>
                        {Math.round((Date.now() / 1000 - lastAltTime) / 60)}m ago
                      </span>
                    ) : 'N/A'}
                  </td>
                  <td>{formatPercent(recommendations.confidence)}</td>
                  <td>{data?.avg_adv ? Math.round(data.avg_adv).toLocaleString() : 'N/A'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {Object.keys(mmScores).length === 0 && !loading && (
        <div className="empty-state">
          <p>No MM scores available.</p>
          <p style={{ marginTop: '10px', fontSize: '0.9rem', color: '#6b7280' }}>
            ⚠️ Please run Truth Ticks Analysis first to collect tick data, then refresh this page.
          </p>
          <p style={{ marginTop: '5px', fontSize: '0.85rem', color: '#9ca3af' }}>
            Go to <Link to="/truth-ticks" style={{ color: '#3b82f6' }}>Truth Ticks</Link> page and click "Run Analysis".
          </p>
        </div>
      )}
    </div>
  )
}

export default AuraMMPage

