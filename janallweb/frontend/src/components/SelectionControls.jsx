import React from 'react'

const SelectionControls = ({ stocks, selectedStocks, onSelectAll, onDeselectAll }) => {
  const allSymbols = stocks.map(s => s.Symbol || s.symbol || s['PREF IBKR']).filter(Boolean)
  const allSelected = allSymbols.length > 0 && allSymbols.every(sym => selectedStocks.includes(sym))

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={onSelectAll}
        className="px-4 py-2 bg-gray-500 text-white rounded-md hover:bg-gray-600 text-sm font-medium"
      >
        Tümünü Seç
      </button>
      <button
        onClick={onDeselectAll}
        className="px-4 py-2 bg-gray-500 text-white rounded-md hover:bg-gray-600 text-sm font-medium"
      >
        Tümünü Kaldır
      </button>
      <span className="text-sm text-gray-600">
        Seçili: {selectedStocks.length} / {allSymbols.length}
      </span>
    </div>
  )
}

export default SelectionControls









