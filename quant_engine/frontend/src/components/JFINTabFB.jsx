import React, { useState, useMemo } from 'react'
import './JFINTab.css'

function JFINTabFB({ stocks }) {
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' })

  const handleSort = (key) => {
    let direction = 'asc'
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc'
    }
    setSortConfig({ key, direction })
  }

  const sortedStocks = useMemo(() => {
    if (!sortConfig.key) return stocks

    return [...stocks].sort((a, b) => {
      const aVal = a[sortConfig.key]
      const bVal = b[sortConfig.key]

      if (aVal == null && bVal == null) return 0
      if (aVal == null) return 1
      if (bVal == null) return -1

      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortConfig.direction === 'asc' ? aVal - bVal : bVal - aVal
      }

      const aStr = String(aVal).toLowerCase()
      const bStr = String(bVal).toLowerCase()
      if (sortConfig.direction === 'asc') {
        return aStr.localeCompare(bStr)
      } else {
        return bStr.localeCompare(aStr)
      }
    })
  }, [stocks, sortConfig])

  if (!stocks || stocks.length === 0) {
    return (
      <div className="jfin-tab-empty">
        No FB (Front Buy) stocks selected
      </div>
    )
  }

  return (
    <div className="jfin-tab">
      <div className="jfin-tab-header">
        <h3>FB (Front Buy) - Long Positions</h3>
        <div className="jfin-tab-summary">
          <span>Total Stocks: {stocks.length}</span>
          <span>Total Lots: {stocks.reduce((sum, s) => sum + (s.final_lot || 0), 0).toLocaleString()}</span>
        </div>
      </div>

      <div className="jfin-table-container">
        <table className="jfin-table">
          <thead>
            <tr>
              <th onClick={() => handleSort('symbol')} className="sortable">
                Symbol {sortConfig.key === 'symbol' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}
              </th>
              <th onClick={() => handleSort('group')} className="sortable">
                Group {sortConfig.key === 'group' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}
              </th>
              <th onClick={() => handleSort('cgrup')} className="sortable">
                CGRUP {sortConfig.key === 'cgrup' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}
              </th>
              <th onClick={() => handleSort('final_fb_skor')} className="sortable">
                Final FB Skor {sortConfig.key === 'final_fb_skor' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}
              </th>
              <th onClick={() => handleSort('fbtot')} className="sortable">
                Fbtot {sortConfig.key === 'fbtot' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}
              </th>
              <th onClick={() => handleSort('gort')} className="sortable">
                GORT {sortConfig.key === 'gort' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}
              </th>
              <th onClick={() => handleSort('calculated_lot')} className="sortable">
                Calculated Lot {sortConfig.key === 'calculated_lot' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}
              </th>
              <th onClick={() => handleSort('addable_lot')} className="sortable">
                Addable Lot {sortConfig.key === 'addable_lot' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}
              </th>
              <th onClick={() => handleSort('final_lot')} className="sortable">
                Final Lot {sortConfig.key === 'final_lot' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}
              </th>
              <th onClick={() => handleSort('maxalw')} className="sortable">
                MAXALW {sortConfig.key === 'maxalw' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}
              </th>
              <th onClick={() => handleSort('current_position')} className="sortable">
                Current Pos {sortConfig.key === 'current_position' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}
              </th>
              <th onClick={() => handleSort('befday_qty')} className="sortable">
                BEFDAY {sortConfig.key === 'befday_qty' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}
              </th>
              <th onClick={() => handleSort('order_price')} className="sortable">
                Price {sortConfig.key === 'order_price' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}
              </th>
            </tr>
          </thead>
          <tbody>
            {sortedStocks.map((stock, idx) => (
              <tr key={stock.symbol || idx}>
                <td className="jfin-symbol">{stock.symbol}</td>
                <td>{stock.group || '-'}</td>
                <td>{stock.cgrup || '-'}</td>
                <td className="jfin-score">{stock.final_fb_skor?.toFixed(2) || '-'}</td>
                <td>{stock.fbtot?.toFixed(2) || '-'}</td>
                <td>{stock.gort?.toFixed(2) || '-'}</td>
                <td className="jfin-lot">{stock.calculated_lot?.toLocaleString() || '-'}</td>
                <td className="jfin-lot">{stock.addable_lot?.toLocaleString() || '-'}</td>
                <td className="jfin-lot-final jfin-long">{stock.final_lot?.toLocaleString() || '-'}</td>
                <td>{stock.maxalw || '-'}</td>
                <td className="jfin-long">{stock.current_position || 0}</td>
                <td className="jfin-long">{stock.befday_qty || 0}</td>
                <td className="jfin-price">${stock.order_price?.toFixed(2) || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default JFINTabFB
