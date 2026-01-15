import React, { useState, useMemo } from 'react'
import TruthTicksInspector from './TruthTicksInspector'
import './TruthTicksPanel.css'

function TruthTicksPanel({ result, dominanceScores, selectedTimeframe, loading }) {
  const [sortBy, setSortBy] = useState('buyer_seller_score')  // Default sort by dominance score
  const [sortOrder, setSortOrder] = useState('desc')  // desc = descending
  const [filterFlag, setFilterFlag] = useState('all')  // all, insufficient, finra_dominant
  const [inspectorSymbol, setInspectorSymbol] = useState(null)
  const [searchFilter, setSearchFilter] = useState('')  // Search/filter text

  // Extract data from result and merge with dominance scores
  // Handle multi-timeframe structure: {symbol: {TF_4H: metrics, TF_1D: metrics, ...}}
  const data = useMemo(() => {
    if (!result || !result.data) {
      console.log('⚠️ TruthTicksPanel: No result or result.data')
      return []
    }
    
    const symbols = Object.keys(result.data)
    console.log(`🔍 TruthTicksPanel: Processing ${symbols.length} symbols, selectedTimeframe: ${selectedTimeframe}`)
    
    return symbols.map(symbol => {
      const symbolData = result.data[symbol]
      
      // Check if it's multi-timeframe structure
      let baseData = null
      if (symbolData && typeof symbolData === 'object' && !Array.isArray(symbolData)) {
        // Check if it has timeframe keys (multi-timeframe structure)
        if (selectedTimeframe && (symbolData[selectedTimeframe] || symbolData['TF_4H'] || symbolData['TF_1D'])) {
          // Multi-timeframe structure - get the selected timeframe
          if (symbolData[selectedTimeframe]) {
            baseData = {
              symbol,
              ...symbolData[selectedTimeframe]
            }
          } else {
            // Fallback to first available timeframe
            const availableTimeframe = symbolData['TF_1D'] || symbolData['TF_4H'] || symbolData['TF_3D'] || symbolData['TF_5D']
            if (availableTimeframe) {
              baseData = {
                symbol,
                ...availableTimeframe
              }
            }
          }
        } else {
          // Legacy single-timeframe structure
          baseData = {
            symbol,
            ...symbolData
          }
        }
      } else {
        // Legacy structure
        baseData = {
          symbol,
          ...symbolData
        }
      }
      
      if (!baseData) {
        return null
      }
      
      // Merge dominance score if available
      if (dominanceScores && dominanceScores[symbol]) {
        const dominanceData = dominanceScores[symbol]
        // Debug: Log first symbol for troubleshooting
        if (symbol === Object.keys(result.data)[0]) {
          console.log(`🔍 TruthTicksPanel: Merging dominance for ${symbol}`, {
            hasDominanceData: !!dominanceData,
            buyer_seller_score: dominanceData?.buyer_seller_score,
            buyer_seller_label: dominanceData?.buyer_seller_label,
            adv_percent: dominanceData?.adv_percent,
            timeframe_name: dominanceData?.timeframe_name,
            selectedTimeframe
          })
        }
        // Merge dominance data
        return {
          ...baseData,
          ...dominanceData
        }
      } else {
        // Debug: Log why merge didn't happen
        if (symbol === Object.keys(result.data)[0]) {
          console.log(`⚠️ TruthTicksPanel: No dominance data for ${symbol}`, {
            hasDominanceScores: !!dominanceScores,
            hasSymbolInDominanceScores: dominanceScores ? !!dominanceScores[symbol] : false
          })
        }
      }
      
      return baseData
    }).filter(item => item !== null)  // Filter out null items
  }, [result, dominanceScores, selectedTimeframe])

  // Filter data
  const filteredData = useMemo(() => {
    let filtered = [...data]
    
    // Apply flag filter
    if (filterFlag === 'insufficient') {
      filtered = filtered.filter(item => item.flags?.insufficient_truth_ticks)
    } else if (filterFlag === 'finra_dominant') {
      filtered = filtered.filter(item => item.flags?.finra_dominant)
    }
    
    // Apply search filter (search across all columns)
    if (searchFilter.trim()) {
      const searchLower = searchFilter.toLowerCase().trim()
      filtered = filtered.filter(item => {
        // Search in symbol
        if (item.symbol && item.symbol.toLowerCase().includes(searchLower)) {
          return true
        }
        
        // Search in buyer_seller_score
        if (item.buyer_seller_score !== undefined && item.buyer_seller_score !== null) {
          if (item.buyer_seller_score.toString().includes(searchLower)) {
            return true
          }
        }
        
        // Search in buyer_seller_label
        if (item.buyer_seller_label && item.buyer_seller_label.toLowerCase().includes(searchLower)) {
          return true
        }
        
        // Search in truth_tick_count
        const tickCount = item.truth_tick_count ?? item.truth_tick_count_100
        if (tickCount !== undefined && tickCount !== null && tickCount.toString().includes(searchLower)) {
          return true
        }
        
        // Search in truth_volume
        const volume = item.truth_volume ?? item.truth_volume_100
        if (volume !== undefined && volume !== null && volume.toString().includes(searchLower)) {
          return true
        }
        
        // Search in VWAP
        const vwap = item.truth_vwap ?? item.truth_vwap_100
        if (vwap !== undefined && vwap !== null && vwap.toString().includes(searchLower)) {
          return true
        }
        
        // Search in ADV%
        const advPercent = item.adv_percent ?? ((item.truth_adv_fraction_100 ?? item.adv_fraction_truth ?? 0) * 100)
        if (advPercent !== undefined && advPercent !== null && advPercent.toString().includes(searchLower)) {
          return true
        }
        
        // Search in Volav prices
        if (item.volav_levels && item.volav_levels.length > 0) {
          for (const volav of item.volav_levels) {
            if (volav.price && volav.price.toString().includes(searchLower)) {
              return true
            }
          }
        }
        
        // Search in volav1_start, volav1_end, displacement
        if (item.volav1_start && item.volav1_start.toString().includes(searchLower)) {
          return true
        }
        if (item.volav1_end && item.volav1_end.toString().includes(searchLower)) {
          return true
        }
        if (item.volav1_displacement && item.volav1_displacement.toString().includes(searchLower)) {
          return true
        }
        
        return false
      })
    }
    
    // Sort
    filtered.sort((a, b) => {
      let aVal = a[sortBy]
      let bVal = b[sortBy]
      
      // Handle null/undefined
      if (aVal == null) aVal = sortOrder === 'asc' ? Infinity : -Infinity
      if (bVal == null) bVal = sortOrder === 'asc' ? Infinity : -Infinity
      
      if (sortOrder === 'asc') {
        return aVal > bVal ? 1 : aVal < bVal ? -1 : 0
      } else {
        return aVal < bVal ? 1 : aVal > bVal ? -1 : 0
      }
    })
    
    return filtered
  }, [data, sortBy, sortOrder, filterFlag, searchFilter])

  const handleSort = (column) => {
    if (sortBy === column) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(column)
      setSortOrder('desc')
    }
  }

  const formatNumber = (val, decimals = 2) => {
    if (val == null || val === undefined) return 'N/A'
    return typeof val === 'number' ? val.toFixed(decimals) : val
  }

  const formatPercent = (val) => {
    if (val == null || val === undefined) return 'N/A'
    return typeof val === 'number' ? `${val.toFixed(1)}%` : val
  }

  const getDominanceClass = (score) => {
    if (score >= 80) return 'strong-buyer'
    if (score >= 60) return 'buyer'
    if (score >= 45) return 'neutral'
    if (score >= 25) return 'seller'
    return 'strong-seller'
  }
  
  const formatLabel = (label) => {
    if (!label) return 'N/A'
    // Convert underscored format to readable format
    return label.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
  }

  if (loading && !result) {
    return (
      <div className="truth-ticks-panel loading">
        <div className="loading-message">
          ⏳ Submitting job and waiting for results...
          <br />
          <small>Worker may need time to bootstrap ticks. This can take 15-30 seconds.</small>
        </div>
      </div>
    )
  }

  if (!result || filteredData.length === 0) {
    return (
      <div className="truth-ticks-panel empty">
        <div className="empty-message">
          {result?.message || 'No data available. Click "Run Analysis" to start.'}
        </div>
      </div>
    )
  }

  return (
    <div className="truth-ticks-panel">
      <div className="panel-header">
        <div className="stats">
          <span>
            Showing: {filteredData.length} / {data.length} symbols
            {searchFilter && ` (filtered by "${searchFilter}")`}
          </span>
          <span>Processed: {result.processed_count || 0}</span>
          {selectedTimeframe && (
            <span>Timeframe: {selectedTimeframe.replace('TF_', '')}</span>
          )}
        </div>
        
        <div className="controls">
          <label style={{ marginRight: '12px' }}>
            <input
              type="text"
              placeholder="Search symbol, score, volume, VWAP..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              style={{
                padding: '6px 12px',
                border: '1px solid #d1d5db',
                borderRadius: '4px',
                fontSize: '14px',
                width: '250px',
                color: '#1f2937',
                backgroundColor: '#ffffff'
              }}
            />
          </label>
          <label>
            Filter:
            <select value={filterFlag} onChange={(e) => setFilterFlag(e.target.value)}>
              <option value="all">All</option>
              <option value="insufficient">Insufficient Ticks</option>
              <option value="finra_dominant">FNRA Dominant</option>
            </select>
          </label>
        </div>
      </div>

      <div className="table-container">
        <table className="truth-ticks-table">
          <thead>
            <tr>
              <th onClick={() => handleSort('symbol')} className="sortable">
                Symbol {sortBy === 'symbol' && (sortOrder === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('buyer_seller_score')} className="sortable">
                Dominance {sortBy === 'buyer_seller_score' && (sortOrder === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('timeframe_seconds')} className="sortable">
                Timeframe {sortBy === 'timeframe_seconds' && (sortOrder === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('truth_tick_count_100')} className="sortable">
                Ticks {sortBy === 'truth_tick_count_100' && (sortOrder === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('truth_volume_100')} className="sortable">
                Volume {sortBy === 'truth_volume_100' && (sortOrder === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('truth_vwap_100')} className="sortable">
                VWAP {sortBy === 'truth_vwap_100' && (sortOrder === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('truth_adv_fraction_100')} className="sortable">
                ADV% {sortBy === 'truth_adv_fraction_100' && (sortOrder === 'asc' ? '↑' : '↓')}
              </th>
              <th>Volav1</th>
              <th>Volav2</th>
              <th>Volav3</th>
              <th>Volav4</th>
              <th onClick={() => handleSort('volav1_start')} className="sortable">
                Volav1 Start {sortBy === 'volav1_start' && (sortOrder === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('volav1_end')} className="sortable">
                Volav1 End {sortBy === 'volav1_end' && (sortOrder === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('volav1_displacement')} className="sortable">
                Displacement {sortBy === 'volav1_displacement' && (sortOrder === 'asc' ? '↑' : '↓')}
              </th>
              <th>Flags</th>
            </tr>
          </thead>
          <tbody>
            {filteredData.map((item, idx) => (
              <tr key={item.symbol} className={idx % 2 === 0 ? 'even' : 'odd'}>
                <td 
                  className="symbol clickable" 
                  onClick={() => setInspectorSymbol(item.symbol)}
                  title="Click to open Volav Inspector"
                >
                  {item.symbol}
                </td>
                <td>
                  {item.buyer_seller_score !== undefined && item.buyer_seller_score !== null ? (
                    <div className="dominance-score-cell">
                      <div className={`dominance-score dominance-${getDominanceClass(item.buyer_seller_score)}`}>
                        {item.buyer_seller_score}
                      </div>
                      <div className="dominance-label">{formatLabel(item.buyer_seller_label)}</div>
                    </div>
                  ) : (
                    <span className="no-dominance" title={`Debug: buyer_seller_score=${item.buyer_seller_score}, has dominanceScores=${!!dominanceScores}, has symbol=${!!dominanceScores?.[item.symbol]}`}>
                      N/A
                    </span>
                  )}
                </td>
                <td>
                  {item.timeframe ? (
                    <span title={`Likidite: ${item.timeframe_seconds < 86400 ? 'Yüksek' : item.timeframe_seconds < 259200 ? 'Orta' : 'Düşük'}`}>
                      {item.timeframe}
                    </span>
                  ) : 'N/A'}
                </td>
                <td>{item.truth_tick_count ?? item.truth_tick_count_100 ?? 'N/A'}</td>
                <td>{formatNumber(item.truth_volume ?? item.truth_volume_100, 0)}</td>
                <td>${formatNumber(item.truth_vwap ?? item.truth_vwap_100)}</td>
                <td>
                  {item.adv_percent !== undefined ? (
                    formatPercent(item.adv_percent)
                  ) : item.truth_adv_fraction_100 !== undefined ? (
                    formatPercent((item.truth_adv_fraction_100 || 0) * 100)
                  ) : item.adv_fraction_truth !== undefined ? (
                    formatPercent((item.adv_fraction_truth || 0) * 100)
                  ) : (
                    'N/A'
                  )}
                </td>
                <td>
                  {item.volav_levels && item.volav_levels[0] ? (
                    <span>${formatNumber(item.volav_levels[0].price)} ({formatPercent(item.volav_levels[0].pct_of_truth_volume)})</span>
                  ) : 'N/A'}
                </td>
                <td>
                  {item.volav_levels && item.volav_levels[1] ? (
                    <span>${formatNumber(item.volav_levels[1].price)} ({formatPercent(item.volav_levels[1].pct_of_truth_volume)})</span>
                  ) : 'N/A'}
                </td>
                <td>
                  {item.volav_levels && item.volav_levels[2] ? (
                    <span>${formatNumber(item.volav_levels[2].price)} ({formatPercent(item.volav_levels[2].pct_of_truth_volume)})</span>
                  ) : 'N/A'}
                </td>
                <td>
                  {item.volav_levels && item.volav_levels[3] ? (
                    <span>${formatNumber(item.volav_levels[3].price)} ({formatPercent(item.volav_levels[3].pct_of_truth_volume)})</span>
                  ) : 'N/A'}
                </td>
                <td>${formatNumber(item.volav1_start)}</td>
                <td>${formatNumber(item.volav1_end)}</td>
                <td className={item.volav1_displacement > 0 ? 'positive' : item.volav1_displacement < 0 ? 'negative' : ''}>
                  ${formatNumber(item.volav1_displacement)}
                </td>
                <td>
                  {item.flags?.insufficient_data && <span className="flag-badge insufficient" title="Less than 30 ticks in last 10 days">⚠️ Insufficient Data</span>}
                  {item.flags?.insufficient_truth_ticks && <span className="flag-badge insufficient">⚠️ Insufficient Ticks</span>}
                  {item.flags?.finra_dominant && <span className="flag-badge finra">🔴 FNRA</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {inspectorSymbol && (
        <TruthTicksInspector
          symbol={inspectorSymbol}
          onClose={() => setInspectorSymbol(null)}
        />
      )}
    </div>
  )
}

export default TruthTicksPanel

