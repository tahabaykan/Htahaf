import React, { useMemo, useState } from 'react'
import './DecisionHelperV2Panel.css'

function DecisionHelperV2Panel({ data, selectedWindow }) {
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' })
  const [filter, setFilter] = useState('')

  // Process data for selected window
  const processedData = useMemo(() => {
    if (!data) return []

    const rows = []
    for (const [symbol, windows] of Object.entries(data)) {
      const windowData = windows[selectedWindow]
      // Include all results, even NO_SIGNAL_ILLIQUID (user wants to see all processed symbols)
      if (windowData) {
        rows.push({
          symbol,
          ...windowData
        })
      }
    }

    // Apply filter
    const filtered = filter
      ? rows.filter(r =>
        r.symbol.toLowerCase().includes(filter.toLowerCase()) ||
        (r.state && r.state.toLowerCase().includes(filter.toLowerCase()))
      )
      : rows

    // Apply sorting
    if (sortConfig.key) {
      filtered.sort((a, b) => {
        const aVal = a[sortConfig.key]
        const bVal = b[sortConfig.key]

        if (aVal === null || aVal === undefined) return 1
        if (bVal === null || bVal === undefined) return -1

        const comparison = aVal < bVal ? -1 : aVal > bVal ? 1 : 0
        return sortConfig.direction === 'asc' ? comparison : -comparison
      })
    }

    return filtered
  }, [data, selectedWindow, filter, sortConfig])

  const handleSort = (key) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc'
    }))
  }

  const getStateColor = (state) => {
    switch (state) {
      case 'BUYER_DOMINANT': return '#28a745'      // Strong green - aggressive buyers
      case 'SELLER_DOMINANT': return '#dc3545'     // Strong red - aggressive sellers
      case 'BUYER_ABSORPTION': return '#90EE90'    // Light green - buyers absorbing sells (bullish)
      case 'SELLER_ABSORPTION': return '#FFA500'   // Orange - sellers absorbing buys (bearish)
      case 'BUYER_VACUUM': return '#87CEEB'         // Sky blue - fake strength, no real buyers
      case 'SELLER_VACUUM': return '#FFB6C1'       // Light pink - air pocket, no real sellers
      case 'NEUTRAL': return '#E0E0E0'             // Gray - unreadable tape
      // Legacy support
      case 'ABSORPTION': return '#FFD700'          // Gold (maps to BUYER_ABSORPTION)
      case 'VACUUM': return '#FFA500'              // Orange (maps to SELLER_VACUUM)
      default: return '#FFFFFF'
    }
  }

  const formatNumber = (val, decimals = 4) => {
    if (val === null || val === undefined) return 'N/A'
    return typeof val === 'number' ? val.toFixed(decimals) : val
  }

  const formatPercent = (val) => {
    if (val === null || val === undefined) return 'N/A'
    return typeof val === 'number' ? `${(val * 100).toFixed(2)}%` : val
  }

  return (
    <div className="decision-helper-v2-panel">
      <div className="panel-controls">
        <input
          type="text"
          placeholder="Filter by symbol or state..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="filter-input"
        />
        <div className="stats">
          Showing {processedData.length} symbols
        </div>
      </div>

      <div className="table-container">
        <table className="decision-helper-v2-table">
          <thead>
            <tr>
              <th onClick={() => handleSort('symbol')} className="sortable">
                Symbol {sortConfig.key === 'symbol' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('state')} className="sortable">
                State {sortConfig.key === 'state' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('rfs')} className="sortable">
                RFS {sortConfig.key === 'rfs' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('modal_displacement')} className="sortable">
                Modal Disp {sortConfig.key === 'modal_displacement' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('grpan1_start')} className="sortable">
                G1 Start {sortConfig.key === 'grpan1_start' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('grpan1_end')} className="sortable">
                G1 End {sortConfig.key === 'grpan1_end' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('rwvap')} className="sortable">
                RWVAP {sortConfig.key === 'rwvap' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('rwvap_diff')} className="sortable">
                RWVAP Diff {sortConfig.key === 'rwvap_diff' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('adv_fraction')} className="sortable">
                ADV Frac {sortConfig.key === 'adv_fraction' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('flow_efficiency')} className="sortable">
                Flow Eff {sortConfig.key === 'flow_efficiency' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('srpan_score')} className="sortable">
                SRPAN {sortConfig.key === 'srpan_score' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </th>
              <th>V2 Bid</th>
              <th>V2 Ask</th>
              <th>V2 Age</th>
              <th>G1 Conf</th>
              <th>G2</th>
              <th>G2 Conf</th>
              <th>Spread</th>
            </tr>
          </thead>
          <tbody>
            {processedData.length === 0 ? (
              <tr>
                <td colSpan="15" className="no-data">
                  No data available for {selectedWindow}
                </td>
              </tr>
            ) : (
              processedData.map((row, idx) => (
                <tr key={row.symbol} className={idx % 2 === 0 ? 'even' : 'odd'}>
                  <td className="symbol-cell">{row.symbol}</td>
                  <td
                    className="state-cell"
                    style={{ backgroundColor: getStateColor(row.state) }}
                  >
                    {row.state}
                  </td>
                  <td className="number-cell">{formatNumber(row.rfs, 3)}</td>
                  <td className="number-cell">{formatNumber(row.modal_displacement)}</td>
                  <td className="number-cell">{formatNumber(row.grpan1_start)}</td>
                  <td className="number-cell">{formatNumber(row.grpan1_end)}</td>
                  <td className="number-cell">{formatNumber(row.rwvap)}</td>
                  <td className="number-cell">{formatNumber(row.rwvap_diff)}</td>
                  <td className="number-cell">{formatPercent(row.adv_fraction)}</td>
                  <td className="number-cell">{formatNumber(row.flow_efficiency, 2)}</td>
                  <td className="number-cell">{formatNumber(row.srpan_score, 1)}</td>
                  <td className="number-cell v2-cell">{row.v2_snapshot ? formatNumber(row.v2_snapshot.bid) : '-'}</td>
                  <td className="number-cell v2-cell">{row.v2_snapshot ? formatNumber(row.v2_snapshot.ask) : '-'}</td>
                  <td className="number-cell v2-cell">{row.v2_snapshot ? `${row.v2_snapshot.age}s` : '-'}</td>
                  <td className="number-cell">{formatPercent(row.grpan1_conf)}</td>
                  <td className="number-cell">{formatNumber(row.grpan2)}</td>
                  <td className="number-cell">{formatPercent(row.grpan2_conf)}</td>
                  <td className="number-cell">
                    {row.grpan2 && row.grpan1_end
                      ? formatNumber(Math.abs(row.grpan2 - row.grpan1_end))
                      : 'N/A'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default DecisionHelperV2Panel



