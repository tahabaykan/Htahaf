import React, { useState, useMemo, useEffect, useCallback } from 'react'
import { useData } from '../contexts/DataContext'
import api from '../services/api'

// Memoized cell component for performance (500+ symbols)
const TableCell = React.memo(({ value, isMini450 }) => {
  return (
    <div className={`truncate ${isMini450 ? 'max-w-[80px]' : 'max-w-[120px]'}`} title={String(value)}>
      {String(value)}
    </div>
  )
})
TableCell.displayName = 'TableCell'

const StockTable = ({ stocks, selectedStocks = [], onSelectionChange, isMini450 = false }) => {
  const { marketData } = useData()
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' })
  const [currentPage, setCurrentPage] = useState(1)
  const [localSelection, setLocalSelection] = useState(new Set(selectedStocks))
  // Mini450 aktifse tüm hisseleri tek sayfada göster, değilse 15 hisse/sayfa
  const itemsPerPage = isMini450 ? stocks.length : 15

  // Sütun sırası - Phase 1: Static CSV + Live Market + Derived Scores
  // Optimized for 500+ symbols with frequent updates
  const allColumns = useMemo(() => {
    const columns = []
    
    // 1. Static CSV columns (from janalldata.csv)
    const staticColumns = [
      { key: 'PREF_IBKR', label: 'PREF_IBKR', type: 'static' },
      { key: 'prev_close', label: 'prev_close', type: 'static' },
      { key: 'CMON', label: 'CMON', type: 'static' },
      { key: 'CGRUP', label: 'CGRUP', type: 'static' },
      { key: 'FINAL_THG', label: 'FINAL_THG', type: 'static' },
      { key: 'SHORT_FINAL', label: 'SHORT_FINAL', type: 'static' },
      { key: 'AVG_ADV', label: 'AVG_ADV', type: 'static' },
      { key: 'SMI', label: 'SMI', type: 'static' },
      { key: 'SMA63_chg', label: 'SMA63_chg', type: 'static' },
      { key: 'SMA246_chg', label: 'SMA246_chg', type: 'static' }
    ]
    
    columns.push(...staticColumns)
    
    // 2. Live market columns (from Hammer Pro)
    const liveColumns = [
      { key: 'Bid', label: 'Bid', type: 'live' },
      { key: 'Ask', label: 'Ask', type: 'live' },
      { key: 'Last', label: 'Last', type: 'live' },
      { key: 'Volume', label: 'Volume', type: 'live' },
      { key: 'Spread', label: 'Spread', type: 'live' }
    ]
    
    columns.push(...liveColumns)
    
    // 3. Derived score columns (computed live)
    const scoreColumns = [
      { key: 'FrontBuyScore', label: 'FrontBuyScore', type: 'score' },
      { key: 'FinalFBScore', label: 'FinalFBScore', type: 'score' },
      { key: 'BidBuyScore', label: 'BidBuyScore', type: 'score' },
      { key: 'AskBuyScore', label: 'AskBuyScore', type: 'score' },
      { key: 'AskSellScore', label: 'AskSellScore', type: 'score' },
      { key: 'FrontSellScore', label: 'FrontSellScore', type: 'score' },
      { key: 'BidSellScore', label: 'BidSellScore', type: 'score' }
    ]
    
    columns.push(...scoreColumns)
    
    return columns
  }, [isMini450])

  // Seçim state'ini senkronize et
  useEffect(() => {
    setLocalSelection(new Set(selectedStocks))
  }, [selectedStocks])

  // Market data geldiğinde skorları güncelle (Tkinter'daki update_scores_with_market_data gibi)
  // NOT: Bu kısım DataContext'te yapılacak, burada sadece placeholder

  const sortedStocks = useMemo(() => {
    if (!sortConfig.key) return stocks

    return [...stocks].sort((a, b) => {
      let aVal = a[sortConfig.key]
      let bVal = b[sortConfig.key]

      // Sayısal değerleri parse et
      const aNum = parseFloat(aVal)
      const bNum = parseFloat(bVal)
      
      // Sayısal değerler varsa onları kullan
      if (!isNaN(aNum) && !isNaN(bNum)) {
        const comparison = aNum > bNum ? 1 : (aNum < bNum ? -1 : 0)
        return sortConfig.direction === 'asc' ? comparison : -comparison
      }
      
      // String karşılaştırma
      if (aVal === bVal) return 0
      const comparison = String(aVal) > String(bVal) ? 1 : -1
      return sortConfig.direction === 'asc' ? comparison : -comparison
    })
  }, [stocks, sortConfig])

  const paginatedStocks = useMemo(() => {
    // Mini450 aktifse tüm hisseleri göster, değilse sayfalama yap
    if (isMini450) {
      return sortedStocks
    }
    const startIndex = (currentPage - 1) * itemsPerPage
    return sortedStocks.slice(startIndex, startIndex + itemsPerPage)
  }, [sortedStocks, currentPage, itemsPerPage, isMini450])

  const totalPages = isMini450 ? 1 : Math.ceil(sortedStocks.length / itemsPerPage)

  const handleSort = useCallback((key) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc'
    }))
  }, [])

  const handleSelectStock = useCallback((symbol, checked) => {
    setLocalSelection(prev => {
      const newSelection = new Set(prev)
      if (checked) {
        newSelection.add(symbol)
      } else {
        newSelection.delete(symbol)
      }
      if (onSelectionChange) {
        onSelectionChange(Array.from(newSelection))
      }
      return newSelection
    })
  }, [onSelectionChange])

  const getMarketPrice = (symbol) => {
    const data = marketData[symbol]
    return data?.price || data?.last || '-'
  }

  // Memoized cell value getter for performance
  const getCellValue = useCallback((stock, columnKey) => {
    // Merged data structure: all fields are directly in stock object
    // Fallback to marketData for live updates if needed
    const symbol = stock.PREF_IBKR || stock['PREF IBKR'] || stock.Symbol || stock.symbol
    
    // Try stock data first (merged data)
    let value = stock[columnKey]
    
    // Fallback to marketData for live columns if stock doesn't have it
    if ((value === null || value === undefined || value === '') && marketData[symbol]) {
      if (columnKey === 'Bid') {
        value = marketData[symbol]?.bid
      } else if (columnKey === 'Ask') {
        value = marketData[symbol]?.ask
      } else if (columnKey === 'Last') {
        value = marketData[symbol]?.last || marketData[symbol]?.price
      } else if (columnKey === 'Volume') {
        value = marketData[symbol]?.volume
      }
    }
    
    // Format numeric values
    if (value !== null && value !== undefined && value !== '') {
      const numValue = parseFloat(value)
      if (!isNaN(numValue)) {
        // Round to 4 decimal places for scores and prices
        if (columnKey.includes('Score') || columnKey === 'Spread' || 
            columnKey === 'Bid' || columnKey === 'Ask' || columnKey === 'Last') {
          return numValue.toFixed(4)
        }
        // Round to 2 decimal places for other numeric values
        return numValue.toFixed(2)
      }
      return value
    }
    
    return '-'
  }, [marketData])

  if (stocks.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        Veri yok
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <div className={`text-sm text-gray-600 mb-2 ${isMini450 ? 'text-xs' : ''}`}>
        {isMini450 ? '🔍 Mini450 Görünümü - ' : ''}Toplam {stocks.length} hisse, {allColumns.length} sütun | Seçili: {localSelection.size}
      </div>
      <table className={`min-w-full divide-y divide-gray-200 ${isMini450 ? 'text-[10px]' : 'text-xs'}`}>
        <thead className="bg-gray-50 sticky top-0 z-10">
          <tr>
            {/* Seç checkbox sütunu */}
            <th className={`${isMini450 ? 'px-1 py-1 text-[10px]' : 'px-2 py-2 text-xs'} text-left font-medium text-gray-500 uppercase tracking-wider sticky left-0 bg-gray-50 z-20`}>
              <input
                type="checkbox"
                checked={paginatedStocks.length > 0 && paginatedStocks.every(s => {
                  const sym = s.PREF_IBKR || s['PREF IBKR'] || s.Symbol || s.symbol
                  return localSelection.has(sym)
                })}
                onChange={(e) => {
                  paginatedStocks.forEach(stock => {
                    const sym = stock.PREF_IBKR || stock['PREF IBKR'] || stock.Symbol || stock.symbol
                    handleSelectStock(sym, e.target.checked)
                  })
                }}
                className="rounded border-gray-300"
              />
            </th>
            {/* Tüm sütunlar */}
            {allColumns.map(col => (
              <th
                key={col.key}
                onClick={() => handleSort(col.key)}
                className={`${isMini450 ? 'px-1 py-1 text-[10px]' : 'px-2 py-2 text-xs'} text-left font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 whitespace-nowrap`}
              >
                <div className="flex items-center">
                  <span className="truncate max-w-[120px]" title={col.label}>
                    {col.label}
                  </span>
                  {sortConfig.key === col.key && (
                    <span className="ml-1">
                      {sortConfig.direction === 'asc' ? '↑' : '↓'}
                    </span>
                  )}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {paginatedStocks.map((stock, index) => {
            const symbol = stock.PREF_IBKR || stock['PREF IBKR'] || stock.Symbol || stock.symbol
            const isSelected = localSelection.has(symbol)
            
            return (
              <tr key={index} className={`hover:bg-gray-50 ${isSelected ? 'bg-blue-50' : ''}`}>
                {/* Seç checkbox */}
                <td className={`${isMini450 ? 'px-1 py-1' : 'px-2 py-2'} whitespace-nowrap sticky left-0 bg-white z-10`}>
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={(e) => handleSelectStock(symbol, e.target.checked)}
                    className={`rounded border-gray-300 ${isMini450 ? 'w-3 h-3' : ''}`}
                  />
                </td>
                {/* Tüm sütunlar */}
                {allColumns.map(col => (
                  <td
                    key={col.key}
                    className={`${isMini450 ? 'px-1 py-1 text-[10px]' : 'px-2 py-2 text-xs'} whitespace-nowrap text-gray-900`}
                  >
                    <TableCell value={getCellValue(stock, col.key)} isMini450={isMini450} />
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>

      {!isMini450 && totalPages > 1 && (
        <div className="bg-white px-4 py-3 flex items-center justify-between border-t border-gray-200">
          <div className="flex-1 flex justify-between sm:hidden">
            <button
              onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
              disabled={currentPage === 1}
              className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
            >
              Önceki
            </button>
            <button
              onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
              disabled={currentPage === totalPages}
              className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
            >
              Sonraki
            </button>
          </div>
          <div className="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
            <div>
              <p className="text-sm text-gray-700">
                Toplam <span className="font-medium">{sortedStocks.length}</span> hisse
              </p>
            </div>
            <div>
              <nav className="relative z-0 inline-flex rounded-md shadow-sm -space-x-px">
                <button
                  onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                  disabled={currentPage === 1}
                  className="px-2 py-2 border border-gray-300 rounded-l-md text-sm font-medium text-gray-500 bg-white hover:bg-gray-50 disabled:opacity-50"
                >
                  Önceki
                </button>
                <span className="px-4 py-2 border border-gray-300 text-sm font-medium text-gray-700 bg-white">
                  Sayfa {currentPage} / {totalPages}
                </span>
                <button
                  onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                  disabled={currentPage === totalPages}
                  className="px-2 py-2 border border-gray-300 rounded-r-md text-sm font-medium text-gray-500 bg-white hover:bg-gray-50 disabled:opacity-50"
                >
                  Sonraki
                </button>
              </nav>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default StockTable

