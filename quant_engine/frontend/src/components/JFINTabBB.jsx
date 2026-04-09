import React, { useState, useMemo, useEffect } from 'react'
import JFINFilterControls from './JFINFilterControls'
import './JFINTab.css'

function JFINTabBB({ stocks, onFilteredDataChange }) {
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
    // Check if any filter is active
    const hasActiveFilter = filters.gort_min !== '' || filters.gort_max !== '' ||
      filters.fbtot_value !== '' || filters.sma63_value !== ''

    let currentFiltered = stocks;
    if (hasActiveFilter) {
      // Re-apply current filters to new stocks
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

      currentFiltered = filtered;
      setFilteredStocks(filtered)
    } else {
      currentFiltered = stocks;
      setFilteredStocks(stocks)
    }

    // Notify parent
    if (onFilteredDataChange) {
      onFilteredDataChange(currentFiltered)
    }
  }, [stocks, filters, onFilteredDataChange])

  const applyFilters = () => {
    let filtered = [...stocks]

    // GORT range filter
    if (filters.gort_min !== '') {
      const min = parseFloat(filters.gort_min)
      filtered = filtered.filter(s => (s.gort || 0) >= min)
    }
    if (filters.gort_max !== '') {
      const max = parseFloat(filters.gort_max)
      filtered = filtered.filter(s => (s.gort || 0) <= max)
    }

    // FBtot filter
    if (filters.fbtot_value !== '') {
      const threshold = parseFloat(filters.fbtot_value)
      filtered = filtered.filter(s => {
        const fbtot = s.fbtot || 0
        if (filters.fbtot_type === 'below') {
          return fbtot < threshold
        } else {
          return fbtot > threshold
        }
      })
    }

    // SMA63 chg filter
    if (filters.sma63_value !== '') {
      const threshold = parseFloat(filters.sma63_value)
      filtered = filtered.filter(s => {
        const sma63 = s.sma63_chg || 0
        if (filters.sma63_type === 'below') {
          return sma63 < threshold
        } else {
          return sma63 > threshold
        }
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
      sma63_value: '',
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

      // Handle null/undefined
      if (aVal == null && bVal == null) return 0
      if (aVal == null) return 1
      if (bVal == null) return -1

      // Numeric comparison
      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortConfig.direction === 'asc' ? aVal - bVal : bVal - aVal
      }

      // String comparison
      const aStr = String(aVal).toLowerCase()
      const bStr = String(bVal).toLowerCase()
      if (sortConfig.direction === 'asc') {
        return aStr.localeCompare(bStr)
      } else {
        return bStr.localeCompare(aStr)
      }
    })
  }, [filteredStocks, sortConfig])

  if (!stocks || stocks.length === 0) {
    return (
      <div className="jfin-tab-empty">
        No BB (Bid Buy) stocks selected
      </div>
    )
  }

  return (
    <div className="jfin-tab">
      <div className="jfin-tab-header">
        <h3>BB (Bid Buy) - Long Positions</h3>
        <div className="jfin-tab-summary">
          <span>Total Stocks: {stocks.length}</span>
          <span>Filtered: {filteredStocks.length}</span>
          <span>Total Lots: {filteredStocks.reduce((sum, s) => sum + (s.final_lot || 0), 0).toLocaleString()}</span>
        </div>
      </div>

      {/* Filter Controls */}
      <JFINFilterControls
        poolType="BB"
        filters={filters}
        onFilterChange={setFilters}
        onApplyFilters={applyFilters}
        onClearFilters={clearFilters}
      />

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
              <th onClick={() => handleSort('final_bb_skor')} className="sortable">
                Final BB Skor {sortConfig.key === 'final_bb_skor' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}
              </th>
              <th onClick={() => handleSort('fbtot')} className="sortable">
                Fbtot {sortConfig.key === 'fbtot' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}
              </th>
              <th onClick={() => handleSort('gort')} className="sortable">
                GORT {sortConfig.key === 'gort' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}
              </th>
              <th onClick={() => handleSort('sma63_chg')} className="sortable">
                SMA63 chg {sortConfig.key === 'sma63_chg' && (sortConfig.direction === 'asc' ? ' ↑' : ' ↓')}
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
                <td className="jfin-score">{stock.final_bb_skor?.toFixed(2) || '-'}</td>
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

export default JFINTabBB


