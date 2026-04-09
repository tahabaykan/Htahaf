import React, { useState, useMemo, useEffect } from 'react'
import JFINFilterControls from './JFINFilterControls'
import './JFINTab.css'

function JFINTabFB({ stocks, onFilteredDataChange }) {
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' })

  // Filter state
  const [filters, setFilters] = useState({
    gort_min: '',
    gort_max: '',
    fbtot_value: '',
    fbtot_type: 'below',
    sma63_value: '',
    sma63_type: 'below'
  })

  const [filteredStocks, setFilteredStocks] = useState(stocks)

  // Re-apply filters when stocks change (preserve filter values)
  useEffect(() => {
    const hasActiveFilter = filters.gort_min !== '' || filters.gort_max !== '' ||
      filters.fbtot_value !== '' || filters.sma63_value !== ''

    if (hasActiveFilter) {
      let filtered = [...stocks]
      if (filters.gort_min !== '') filtered = filtered.filter(s => (s.gort || 0) >= parseFloat(filters.gort_min))
      if (filters.gort_max !== '') filtered = filtered.filter(s => (s.gort || 0) <= parseFloat(filters.gort_max))
      if (filters.fbtot_value !== '') {
        const threshold = parseFloat(filters.fbtot_value)
        filtered = filtered.filter(s => filters.fbtot_type === 'below' ? (s.fbtot || 0) < threshold : (s.fbtot || 0) > threshold)
      }
      if (filters.sma63_value !== '') {
        const threshold = parseFloat(filters.sma63_value)
        filtered = filtered.filter(s => filters.sma63_type === 'below' ? (s.sma63_chg || 0) < threshold : (s.sma63_chg || 0) > threshold)
      }
      setFilteredStocks(filtered)
      if (onFilteredDataChange) onFilteredDataChange(filtered)
    } else {
      setFilteredStocks(stocks)
      if (onFilteredDataChange) onFilteredDataChange(stocks)
    }
  }, [stocks, filters, onFilteredDataChange])

  const applyFilters = () => {
    let filtered = [...stocks]

    if (filters.gort_min !== '') {
      const min = parseFloat(filters.gort_min)
      filtered = filtered.filter(s => (s.gort || 0) >= min)
    }
    if (filters.gort_max !== '') {
      const max = parseFloat(filters.gort_max)
      filtered = filtered.filter(s => (s.gort || 0) <= max)
    }

    if (filters.fbtot_value !== '') {
      const threshold = parseFloat(filters.fbtot_value)
      filtered = filtered.filter(s => {
        const fbtot = s.fbtot || 0
        return filters.fbtot_type === 'below' ? fbtot < threshold : fbtot > threshold
      })
    }

    if (filters.sma63_value !== '') {
      const threshold = parseFloat(filters.sma63_value)
      filtered = filtered.filter(s => {
        const sma63 = s.sma63_chg || 0
        return filters.sma63_type === 'below' ? sma63 < threshold : sma63 > threshold
      })
    }

    setFilteredStocks(filtered)
  }

  const clearFilters = () => {
    setFilters({
      gort_min: '',
      gort_max: '',
      fbtot_value: '',
      fbtot_type: 'below',
      sma63_value: '',  // Fixed: added colon
      sma63_type: 'below'
    })
    setFilteredStocks(stocks)
  }

  const handleSort = (key) => {
    let direction = 'asc'
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc'
    }
    setSortConfig({ key, direction })
  }

  const sortedStocks = useMemo(() => {
    if (!sortConfig.key) return filteredStocks
    return [...filteredStocks].sort((a, b) => {
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
      return sortConfig.direction === 'asc' ? aStr.localeCompare(bStr) : bStr.localeCompare(aStr)
    })
  }, [filteredStocks, sortConfig])

  if (!stocks || stocks.length === 0) {
    return <div className="jfin-tab-empty">No FB (Front Buy) stocks selected</div>
  }

  return (
    <div className="jfin-tab">
      <div className="jfin-tab-header">
        <h3>FB (Front Buy) - Long Positions</h3>
        <div className="jfin-tab-summary">
          <span>Total Stocks: {stocks.length}</span>
          <span>Filtered: {filteredStocks.length}</span>
          <span>Total Lots: {filteredStocks.reduce((sum, s) => sum + (s.final_lot || 0), 0).toLocaleString()}</span>
        </div>
      </div>

      <JFINFilterControls
        poolType="FB"
        filters={filters}
        onFilterChange={setFilters}
        onApplyFilters={applyFilters}
        onClearFilters={clearFilters}
      />

      <div className="jfin-table-container">
        <table className="jfin-table">
          <thead>
            <tr>
              <th onClick={() => handleSort('symbol')} className="sortable">Symbol {sortConfig.key === 'symbol' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}</th>
              <th onClick={() => handleSort('group')} className="sortable">Group {sortConfig.key === 'group' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}</th>
              <th onClick={() => handleSort('cgrup')} className="sortable">CGRUP {sortConfig.key === 'cgrup' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}</th>
              <th onClick={() => handleSort('final_fb_skor')} className="sortable">Final FB Skor {sortConfig.key === 'final_fb_skor' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}</th>
              <th onClick={() => handleSort('fbtot')} className="sortable">Fbtot {sortConfig.key === 'fbtot' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}</th>
              <th onClick={() => handleSort('gort')} className="sortable">GORT {sortConfig.key === 'gort' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}</th>
              <th onClick={() => handleSort('sma63_chg')} className="sortable">SMA63 chg {sortConfig.key === 'sma63_chg' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}</th>
              <th onClick={() => handleSort('calculated_lot')} className="sortable">Calculated Lot {sortConfig.key === 'calculated_lot' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}</th>
              <th onClick={() => handleSort('addable_lot')} className="sortable">Addable Lot {sortConfig.key === 'addable_lot' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}</th>
              <th onClick={() => handleSort('final_lot')} className="sortable">Final Lot {sortConfig.key === 'final_lot' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}</th>
              <th onClick={() => handleSort('maxalw')} className="sortable">MAXALW {sortConfig.key === 'maxalw' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}</th>
              <th onClick={() => handleSort('current_position')} className="sortable">Current Pos {sortConfig.key === 'current_position' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}</th>
              <th onClick={() => handleSort('befday_qty')} className="sortable">BEFDAY {sortConfig.key === 'befday_qty' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}</th>
              <th onClick={() => handleSort('order_price')} className="sortable">Price {sortConfig.key === 'order_price' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}</th>
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
                <td>{stock.sma63_chg?.toFixed(2) || '-'}</td>
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
