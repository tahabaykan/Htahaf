import React, { useState, useEffect, useMemo } from 'react'
import './TradingPanels.css'
import CleanLogsPanel from './CleanLogsPanel'

function TradingPanels({ tradingMode, initialTab = 'positions', onTabChange }) {
  const [activeTab, setActiveTab] = useState(initialTab)
  const [positions, setPositions] = useState([])
  const [shadowPositions, setShadowPositions] = useState([])
  const [shadowExposure, setShadowExposure] = useState(null)
  const [orders, setOrders] = useState([])
  const [filledOrders, setFilledOrders] = useState([])
  const [orderSubTab, setOrderSubTab] = useState('pending')
  const [filterText, setFilterText] = useState('')
  const [exposure, setExposure] = useState(null)
  const [loading, setLoading] = useState(false)

  // Bulk Selection State
  const [selectedOrders, setSelectedOrders] = useState(new Set())

  // Sorting State (for positions)
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'ascending' })

  // Orders Sorting State
  const [ordersSortConfig, setOrdersSortConfig] = useState({ key: null, direction: 'ascending' })

  // Pagination State for Orders
  const [ordersPage, setOrdersPage] = useState(1)
  const [ordersPerPage, setOrdersPerPage] = useState(25)

  useEffect(() => {
    // Update active tab when initialTab prop changes
    if (initialTab && initialTab !== activeTab) {
      setActiveTab(initialTab)
    }
  }, [initialTab])

  const handleTabChange = (tab) => {
    setActiveTab(tab)
    if (onTabChange) {
      onTabChange(tab)
    }
  }

  useEffect(() => {
    // Reload data when trading mode or active tab changes
    loadData()

    // Auto-refresh orders if tab is active
    let interval = null
    if (activeTab === 'orders') {
      interval = setInterval(loadData, 2000)
    }
    return () => { if (interval) clearInterval(interval) }
  }, [tradingMode, activeTab])

  const loadData = async () => {
    // Silent load for auto-refresh to avoid flickering if already loaded once?
    // For now simple load.
    if (!orders.length && activeTab === 'orders') setLoading(true)
    else if (activeTab !== 'orders') setLoading(true)

    try {
      // Convert frontend mode to backend account_id format
      const accountId = (tradingMode === 'HAMMER_PRO' || tradingMode === 'HAMMER_TRADING' || tradingMode === 'HAMPRO') ? 'HAMPRO' : tradingMode

      if (activeTab === 'positions') {
        const response = await fetch(`/api/trading/positions?_t=${Date.now()}&account_id=${accountId}`)
        const result = await response.json()
        if (result.success) {
          setPositions(result.positions || [])
        }
      } else if (activeTab === 'shadow-positions') {
        const response = await fetch(`/api/psfalgo/shadow/positions?_t=${Date.now()}`)
        const result = await response.json()
        if (result.success) {
          setShadowPositions(result.positions || [])
        }
        // Also load shadow exposure
        const exposureResponse = await fetch(`/api/psfalgo/shadow/exposure?_t=${Date.now()}`)
        const exposureResult = await exposureResponse.json()
        if (exposureResult.success) {
          setShadowExposure(exposureResult.summary || null)
        }
      } else if (activeTab === 'orders') {
        // Use Janall endpoint for Native visibility - pass mode so backend returns correct account's orders
        const modeParam = tradingMode || 'HAMMER_PRO'
        const response = await fetch(`/api/janall/orders?_t=${Date.now()}&mode=${modeParam}`)
        const result = await response.json()
        if (result) {
          // Janall routes return { open_orders: [], filled_orders: [] } usually
          const open = result.open_orders || result.orders || []
          const filled = result.filled_orders || []
          setOrders(open)
          setFilledOrders(filled)
        }
      } else if (activeTab === 'exposure') {
        const response = await fetch(`/api/trading/exposure?_t=${Date.now()}`)
        const result = await response.json()
        if (result.success) {
          setExposure(result.exposure || null)
        }
      }
    } catch (err) {
      console.error(`Error loading ${activeTab}:`, err)
    } finally {
      setLoading(false)
    }
  }

  // Selection Logic moved below with pagination support

  const handleBulkCancel = async () => {
    if (selectedOrders.size === 0) return
    if (!confirm(`Cancel ${selectedOrders.size} selected orders?`)) return
    try {
      const response = await fetch('/api/janall/cancel-orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order_ids: Array.from(selectedOrders) })
      })
      const result = await response.json()
      if (result.success) {
        setSelectedOrders(new Set())
        loadData()
        alert(result.message)
      } else {
        alert('Failed: ' + result.message)
      }
    } catch (err) {
      alert('Error cancelling: ' + err)
    }
  }

  const handleCancelAll = async () => {
    if (orders.length === 0) return
    if (!confirm('Hesaptaki TÜM açık emirleri iptal et? (reqGlobalCancel)')) return
    try {
      const response = await fetch('/api/janall/cancel-orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order_ids: [] })
      })
      const result = await response.json()
      if (result.success) {
        setSelectedOrders(new Set())
        loadData()
        alert(result.message)
      } else {
        alert('Failed: ' + (result.message || 'Tümünü iptal başarısız'))
      }
    } catch (err) {
      alert('Error: ' + err)
    }
  }

  // Sorting Logic
  const requestSort = (key) => {
    let direction = 'ascending'
    if (sortConfig.key === key && sortConfig.direction === 'ascending') {
      direction = 'descending'
    }
    setSortConfig({ key, direction })
  }

  const sortedPositions = useMemo(() => {
    let sortableItems = positions.filter(p => !filterText || p.symbol.toUpperCase().includes(filterText.toUpperCase()))
    if (sortConfig.key !== null) {
      sortableItems.sort((a, b) => {
        let aValue = a[sortConfig.key]
        let bValue = b[sortConfig.key]

        // Special handling for derived columns
        if (sortConfig.key === 'quantity' || sortConfig.key === 'display_qty') {
          aValue = a.display_qty !== undefined ? a.display_qty : a.qty
          bValue = b.display_qty !== undefined ? b.display_qty : b.qty
        } else if (sortConfig.key === 'befday_qty') {
          aValue = a.befday_qty || 0
          bValue = b.befday_qty || 0
        } else if (sortConfig.key === 'potential_qty') {
          aValue = a.potential_qty || 0
          bValue = b.potential_qty || 0
        }

        if (aValue < bValue) {
          return sortConfig.direction === 'ascending' ? -1 : 1
        }
        if (aValue > bValue) {
          return sortConfig.direction === 'ascending' ? 1 : -1
        }
        return 0
      })
    }
    return sortableItems
  }, [positions, sortConfig, filterText])

  const getSortIndicator = (key) => {
    if (sortConfig.key !== key) return ''
    return sortConfig.direction === 'ascending' ? ' ▲' : ' ▼'
  }

  // Orders Sorting Logic
  const requestOrdersSort = (key) => {
    let direction = 'ascending'
    if (ordersSortConfig.key === key && ordersSortConfig.direction === 'ascending') {
      direction = 'descending'
    }
    setOrdersSortConfig({ key, direction })
    setOrdersPage(1) // Reset to first page when sorting
  }

  const getOrdersSortIndicator = (key) => {
    if (ordersSortConfig.key !== key) return ''
    return ordersSortConfig.direction === 'ascending' ? ' ▲' : ' ▼'
  }

  // Sorted and Paginated Orders
  const { sortedOrders, paginatedOrders, totalPages } = useMemo(() => {
    let filtered = orders.filter(o => !filterText || (o.symbol || '').toUpperCase().includes(filterText.toUpperCase()))

    // Sort
    if (ordersSortConfig.key !== null) {
      filtered.sort((a, b) => {
        let aValue, bValue

        switch (ordersSortConfig.key) {
          case 'symbol':
            aValue = (a.symbol || '').toUpperCase()
            bValue = (b.symbol || '').toUpperCase()
            break
          case 'side':
            aValue = (a.action || a.side || '').toUpperCase()
            bValue = (b.action || b.side || '').toUpperCase()
            break
          case 'quantity':
            aValue = a.qty || a.quantity || 0
            bValue = b.qty || b.quantity || 0
            break
          case 'price':
            aValue = a.price || 0
            bValue = b.price || 0
            break
          case 'tag':
            aValue = (a.tag || '').toUpperCase()
            bValue = (b.tag || '').toUpperCase()
            break
          case 'status':
            aValue = (a.status || '').toUpperCase()
            bValue = (b.status || '').toUpperCase()
            break
          case 'time':
            aValue = a.timestamp || 0
            bValue = b.timestamp || 0
            break
          default:
            aValue = a[ordersSortConfig.key]
            bValue = b[ordersSortConfig.key]
        }

        if (aValue < bValue) return ordersSortConfig.direction === 'ascending' ? -1 : 1
        if (aValue > bValue) return ordersSortConfig.direction === 'ascending' ? 1 : -1
        return 0
      })
    }

    const total = Math.ceil(filtered.length / ordersPerPage)
    const start = (ordersPage - 1) * ordersPerPage
    const paginated = filtered.slice(start, start + ordersPerPage)

    return { sortedOrders: filtered, paginatedOrders: paginated, totalPages: total }
  }, [orders, ordersSortConfig, filterText, ordersPage, ordersPerPage])

  // Toggle select all (only visible/paginated orders)
  const toggleSelectAll = () => {
    if (selectedOrders.size === paginatedOrders.length) {
      setSelectedOrders(new Set())
    } else {
      const allIds = paginatedOrders.map((o, idx) => o.order_id || `temp-${idx}`)
      setSelectedOrders(new Set(allIds))
    }
  }

  const toggleSelect = (oid) => {
    const newSet = new Set(selectedOrders)
    if (newSet.has(oid)) {
      newSet.delete(oid)
    } else {
      newSet.add(oid)
    }
    setSelectedOrders(newSet)
  }

  return (
    <div className="trading-panels">
      <div className="panel-tabs">
        <button
          className={`tab-button ${activeTab === 'positions' ? 'active' : ''}`}
          onClick={() => handleTabChange('positions')}
        >
          Positions
        </button>
        <button
          className={`tab-button ${activeTab === 'shadow-positions' ? 'active' : ''}`}
          onClick={() => handleTabChange('shadow-positions')}
        >
          Shadow Positions <span className="simulated-badge">SIMULATED</span>
        </button>
        <button
          className={`tab-button ${activeTab === 'orders' ? 'active' : ''}`}
          onClick={() => handleTabChange('orders')}
        >
          Orders
        </button>
        <button
          className={`tab-button ${activeTab === 'exposure' ? 'active' : ''}`}
          onClick={() => handleTabChange('exposure')}
        >
          Exposure
        </button>
        <button
          className={`tab-button ${activeTab === 'cleanlogs' ? 'active' : ''}`}
          onClick={() => handleTabChange('cleanlogs')}
        >
          Clean Logs
        </button>
        <div className="tab-indicator" style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
          <div className="search-filter" style={{ position: 'relative' }}>
            <input
              type="text"
              placeholder="Search symbol..."
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              style={{
                padding: '6px 12px 6px 30px',
                borderRadius: '4px',
                border: '1px solid #444',
                background: '#1e293b',
                color: 'white',
                fontSize: '14px',
                width: '180px'
              }}
            />
            <span style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', opacity: 0.5 }}>🔍</span>
            {filterText && (
              <span
                onClick={() => setFilterText('')}
                style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', cursor: 'pointer', opacity: 0.7 }}
              >
                ✕
              </span>
            )}
          </div>
          <span className={`trading-mode-badge ${['HAMMER_TRADING', 'HAMMER_PRO', 'HAMPRO'].includes(tradingMode) ? 'hammer-badge' : ''}`}>
            {['HAMMER_TRADING', 'HAMMER_PRO', 'HAMPRO'].includes(tradingMode) ? 'Hammer Account' : tradingMode}
          </span>
        </div>
      </div>

      <div className="panel-content">
        {loading && activeTab !== 'orders' && ( // Don't show generic loading for orders refresh
          <div className="loading-message">Loading...</div>
        )}

        {!loading && activeTab === 'positions' && (
          <div className="positions-panel">
            {positions.length === 0 ? (
              <div className="empty-state">
                No positions in {tradingMode}
              </div>
            ) : (
              <table className="positions-table">
                <thead>
                  <tr>
                    <th onClick={() => requestSort('symbol')} className="sortable-header">
                      Symbol <span className="sort-icon">{getSortIndicator('symbol')}</span>
                    </th>
                    <th onClick={() => requestSort('befday_qty')} className="sortable-header">
                      Befday <span className="sort-icon">{getSortIndicator('befday_qty')}</span>
                    </th>
                    <th onClick={() => requestSort('display_qty')} className="sortable-header">
                      Current <span className="sort-icon">{getSortIndicator('display_qty')}</span>
                    </th>
                    <th onClick={() => requestSort('potential_qty')} className="sortable-header">
                      Potential <span className="sort-icon">{getSortIndicator('potential_qty')}</span>
                    </th>
                    <th onClick={() => requestSort('avg_price')} className="sortable-header">
                      Avg Price <span className="sort-icon">{getSortIndicator('avg_price')}</span>
                    </th>
                    <th onClick={() => requestSort('intraday_cost')} className="sortable-header">
                      Intra Cost <span className="sort-icon">{getSortIndicator('intraday_cost')}</span>
                    </th>
                    <th onClick={() => requestSort('intraday_pnl')} className="sortable-header">
                      Intra P&L <span className="sort-icon">{getSortIndicator('intraday_pnl')}</span>
                    </th>
                    <th onClick={() => requestSort('current_price')} className="sortable-header">
                      Current Price <span className="sort-icon">{getSortIndicator('current_price')}</span>
                    </th>
                    <th onClick={() => requestSort('unrealized_pnl')} className="sortable-header">
                      Unrealized P&L <span className="sort-icon">{getSortIndicator('unrealized_pnl')}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedPositions.map((pos, idx) => {
                    const isLong = (pos.display_qty || pos.qty) > 0
                    const isMixed = pos.display_bucket === 'MIXED'

                    return (
                      <tr key={idx}>
                        <td>
                          <div className="symbol-cell">
                            <span className="symbol-text">
                              {pos.symbol}
                            </span>
                            {/* Taxonomy Badge */}
                            {pos.full_taxonomy ? (
                              <span className={`taxonomy-badge ${pos.strategy_type?.toLowerCase() || 'lt'}`}>
                                {pos.full_taxonomy}
                              </span>
                            ) : (
                              <span className="taxonomy-badge lt">LT OV {isLong ? 'Long' : 'Short'}</span>
                            )}
                            {pos.group && <span className="group-badge">{pos.group}</span>}
                          </div>
                        </td>
                        <td className="quantity-befday" style={{ opacity: 0.8 }}>
                          {pos.befday_qty || 0}
                        </td>
                        <td>
                          <div className="qty-cell">
                            <span className={isLong ? 'quantity-long' : 'quantity-short'} style={{ fontWeight: 'bold' }}>
                              {pos.display_qty != null ? pos.display_qty : pos.qty}
                            </span>
                            {isMixed && (
                              <div className="split-details">
                                LT:{pos.lt_qty_raw} MM:{pos.mm_qty_raw}
                              </div>
                            )}
                          </div>
                        </td>
                        <td className="quantity-potential" style={{ fontWeight: 'bold' }}>
                          {pos.potential_qty != null ? pos.potential_qty : (pos.qty || 0)}
                        </td>
                        <td className={isLong ? 'quantity-long' : 'quantity-short'}>
                          ${pos.avg_price?.toFixed(2)}
                        </td>
                        <td>
                          {pos.intraday_cost ? `$${pos.intraday_cost.toFixed(2)}` : '-'}
                        </td>
                        <td className={pos.intraday_pnl >= 0 ? 'positive' : 'negative'}>
                          {pos.intraday_pnl ? `$${pos.intraday_pnl.toFixed(2)}` : '-'}
                        </td>
                        <td>
                          {pos.price_status === 'NO_PRICE' ? (
                            <span className="price-warning" title="Price Missing">⚠️ 0.00</span>
                          ) : (
                            <span>${pos.current_price ? pos.current_price.toFixed(2) : 'N/A'}</span>
                          )}
                        </td>
                        <td className={pos.unrealized_pnl >= 0 ? 'positive' : 'negative'}>
                          ${pos.unrealized_pnl ? pos.unrealized_pnl.toFixed(2) : 'N/A'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        )}

        {!loading && activeTab === 'shadow-positions' && (
          <div className="positions-panel">
            <div className="simulated-warning">
              <strong>⚠️ SIMULATED POSITIONS (DRY-RUN ONLY)</strong>
              <p>These positions are simulated based on PSFALGO execution ledger entries. No real broker execution has occurred.</p>
            </div>

            {shadowExposure && (
              <div className="shadow-exposure-summary">
                <h4>Exposure Summary</h4>
                <div className="exposure-stats">
                  <div className="stat-item">
                    <span className="stat-label">Total Exposure:</span>
                    <span className="stat-value">${shadowExposure.total_exposure?.toFixed(2) || '0.00'}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Long Exposure:</span>
                    <span className="stat-value positive">${shadowExposure.long_exposure?.toFixed(2) || '0.00'}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Short Exposure:</span>
                    <span className="stat-value negative">${shadowExposure.short_exposure?.toFixed(2) || '0.00'}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Net Exposure:</span>
                    <span className={`stat-value ${shadowExposure.net_exposure >= 0 ? 'positive' : 'negative'}`}>
                      ${shadowExposure.net_exposure?.toFixed(2) || '0.00'}
                    </span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Total Long Value:</span>
                    <span className="stat-value positive">${shadowExposure.total_long_value?.toFixed(2) || '0.00'}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Total Short Value:</span>
                    <span className="stat-value negative">${shadowExposure.total_short_value?.toFixed(2) || '0.00'}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Net Market Value:</span>
                    <span className={`stat-value ${shadowExposure.net_value >= 0 ? 'positive' : 'negative'}`}>
                      ${shadowExposure.net_value?.toFixed(2) || '0.00'}
                    </span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Long Positions:</span>
                    <span className="stat-value">{shadowExposure.long_count || shadowExposure.symbol_count_long || 0}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Short Positions:</span>
                    <span className="stat-value">{shadowExposure.short_count || shadowExposure.symbol_count_short || 0}</span>
                  </div>
                </div>
              </div>
            )}

            {shadowPositions.length === 0 ? (
              <div className="empty-state">
                No shadow positions (no approved actions in ledger)
              </div>
            ) : (
              <table className="positions-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Qty</th>
                    <th>Long Qty</th>
                    <th>Short Qty</th>
                    <th>Market Price</th>
                    <th>Avg Cost (Long)</th>
                    <th>Avg Cost (Short)</th>
                    <th>Market Value (Net)</th>
                    <th>Exposure</th>
                    <th>Entry Count</th>
                  </tr>
                </thead>
                <tbody>
                  {shadowPositions
                    .filter(p => !filterText || (p.symbol || '').toUpperCase().includes(filterText.toUpperCase()))
                    .map((pos, idx) => (
                      <tr key={idx}>
                        <td>{pos.symbol}</td>
                        <td className={pos.current_qty >= 0 ? 'quantity-long' : 'quantity-short'}>
                          {pos.current_qty > 0 ? '+' : ''}{pos.current_qty}
                        </td>
                        <td className="quantity-long">{pos.long_qty || 0}</td>
                        <td className="quantity-short">{pos.short_qty || 0}</td>
                        <td>${pos.market_price_used?.toFixed(4) || 'N/A'}</td>
                        <td className="quantity-long">${pos.avg_cost_long?.toFixed(4) || 'N/A'}</td>
                        <td className="quantity-short">${pos.avg_cost_short?.toFixed(4) || 'N/A'}</td>
                        <td className={pos.market_value_net >= 0 ? 'positive' : 'negative'}>
                          ${pos.market_value_net?.toFixed(2) || '0.00'}
                        </td>
                        <td>${pos.exposure?.toFixed(2) || '0.00'}</td>
                        <td>{pos.entry_count || 0}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* --- ORDERS PANEL WITH ACTIONS --- */}
        {activeTab === 'orders' && (
          <div className="orders-panel">
            <div className="orders-header-actions" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
              <div className="order-sub-tabs" style={{ display: 'flex', gap: '5px' }}>
                <button
                  className={`sub-tab-button ${orderSubTab === 'pending' ? 'active' : ''}`}
                  onClick={() => setOrderSubTab('pending')}
                  style={{
                    padding: '6px 15px',
                    borderRadius: '4px',
                    border: '1px solid #444',
                    background: orderSubTab === 'pending' ? '#2563eb' : '#1e293b',
                    color: 'white',
                    cursor: 'pointer',
                    fontWeight: 'bold'
                  }}
                >
                  Pending ({orders.length})
                </button>
                <button
                  className={`sub-tab-button ${orderSubTab === 'filled' ? 'active' : ''}`}
                  onClick={() => setOrderSubTab('filled')}
                  style={{
                    padding: '6px 15px',
                    borderRadius: '4px',
                    border: '1px solid #444',
                    background: orderSubTab === 'filled' ? '#2563eb' : '#1e293b',
                    color: 'white',
                    cursor: 'pointer',
                    fontWeight: 'bold'
                  }}
                >
                  Filled ({filledOrders.length})
                </button>
              </div>

              {orderSubTab === 'pending' && orders.length > 0 && (
                <button
                  className="cancel-button"
                  onClick={handleCancelAll}
                  style={{
                    backgroundColor: '#b91c1c',
                    color: 'white',
                    border: 'none',
                    padding: '6px 16px',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    fontWeight: 'bold',
                    boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
                    marginRight: '8px'
                  }}
                >
                  Tümünü iptal ({orders.length})
                </button>
              )}
              {orderSubTab === 'pending' && selectedOrders.size > 0 && (
                <button
                  className="cancel-button"
                  onClick={handleBulkCancel}
                  style={{
                    backgroundColor: '#ef4444',
                    color: 'white',
                    border: 'none',
                    padding: '6px 16px',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    fontWeight: 'bold',
                    boxShadow: '0 2px 4px rgba(0,0,0,0.2)'
                  }}
                >
                  Seçileni iptal ({selectedOrders.size})
                </button>
              )}
            </div>

            {orderSubTab === 'pending' ? (
              orders.length === 0 ? (
                <div className="empty-state">No pending orders in {tradingMode}</div>
              ) : (
                <>
                  <table className="orders-table">
                    <thead>
                      <tr>
                        <th style={{ width: '40px', textAlign: 'center' }}>
                          <input
                            type="checkbox"
                            checked={paginatedOrders.length > 0 && selectedOrders.size === paginatedOrders.length}
                            onChange={toggleSelectAll}
                            style={{ cursor: 'pointer', transform: 'scale(1.2)' }}
                          />
                        </th>
                        <th onClick={() => requestOrdersSort('tag')} style={{ cursor: 'pointer' }}>
                          Tag{getOrdersSortIndicator('tag')}
                        </th>
                        <th onClick={() => requestOrdersSort('symbol')} style={{ cursor: 'pointer' }}>
                          Symbol{getOrdersSortIndicator('symbol')}
                        </th>
                        <th onClick={() => requestOrdersSort('side')} style={{ cursor: 'pointer' }}>
                          Side{getOrdersSortIndicator('side')}
                        </th>
                        <th onClick={() => requestOrdersSort('quantity')} style={{ cursor: 'pointer' }}>
                          Quantity{getOrdersSortIndicator('quantity')}
                        </th>
                        <th onClick={() => requestOrdersSort('price')} style={{ cursor: 'pointer' }}>
                          Price{getOrdersSortIndicator('price')}
                        </th>
                        <th onClick={() => requestOrdersSort('status')} style={{ cursor: 'pointer' }}>
                          Status{getOrdersSortIndicator('status')}
                        </th>
                        <th onClick={() => requestOrdersSort('time')} style={{ cursor: 'pointer' }}>
                          Time{getOrdersSortIndicator('time')}
                        </th>
                        <th>ID</th>
                      </tr>
                    </thead>
                    <tbody>
                      {paginatedOrders.map((order, idx) => {
                        const oid = order.order_id || `temp-${idx}`
                        const isBuy = (order.action || order.side || '').toUpperCase() === 'BUY'
                        return (
                          <tr key={oid} className={selectedOrders.has(oid) ? 'selected-row' : ''}>
                            <td style={{ textAlign: 'center' }}>
                              <input
                                type="checkbox"
                                checked={selectedOrders.has(oid)}
                                onChange={() => toggleSelect(oid)}
                              />
                            </td>
                            <td>
                              <span className={`order-tag tag-${(order.tag || 'unknown').toLowerCase().replace(/_/g, '-')}`}>
                                {order.tag || 'N/A'}
                              </span>
                              {order.client_id_label != null && (
                                <span title={order.cancelable_by_this_session ? 'Bu oturumdan iptal edilebilir' : 'Başka oturum; sadece Tümünü iptal ile kapanır'}>
                                  <span style={{ fontSize: '0.75em', marginLeft: 6, color: '#64748b' }}>{order.client_id_label}</span>
                                  {order.cancelable_by_this_session != null && (
                                    <span style={{
                                      marginLeft: 4,
                                      padding: '1px 6px',
                                      borderRadius: 4,
                                      fontSize: '0.7em',
                                      backgroundColor: order.cancelable_by_this_session ? '#dcfce7' : '#fed7aa',
                                      color: order.cancelable_by_this_session ? '#166534' : '#9a3412'
                                    }}>
                                      {order.cancelable_by_this_session ? 'Bu oturum' : 'Başka oturum'}
                                    </span>
                                  )}
                                </span>
                              )}
                            </td>
                            <td><strong>{order.symbol}</strong></td>
                            <td style={{ color: isBuy ? '#22c55e' : '#ef4444', fontWeight: 'bold' }}>
                              {order.action || order.side}
                            </td>
                            <td>{(order.filled_qty || 0)} / {(order.qty || order.quantity || 0)}</td>
                            <td>{order.price ? `$${order.price.toFixed(2)}` : order.order_type}</td>
                            <td><span className={`status-badge ${(order.status || '').toLowerCase()}`}>{order.status}</span></td>
                            <td style={{ fontSize: '0.85em', color: '#666' }}>
                              {order.timestamp ? new Date(order.timestamp * 1000).toLocaleTimeString() : (order.time || '-')}
                            </td>
                            <td style={{ fontSize: '0.8em', color: '#888' }}>{oid}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>

                  {/* Pagination Controls */}
                  {totalPages > 1 && (
                    <div className="pagination-controls" style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginTop: '12px',
                      padding: '10px 0',
                      borderTop: '1px solid #333'
                    }}>
                      <div style={{ color: '#888', fontSize: '0.9em' }}>
                        Showing {((ordersPage - 1) * ordersPerPage) + 1} - {Math.min(ordersPage * ordersPerPage, sortedOrders.length)} of {sortedOrders.length} orders
                      </div>
                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <select
                          value={ordersPerPage}
                          onChange={(e) => { setOrdersPerPage(Number(e.target.value)); setOrdersPage(1) }}
                          style={{
                            padding: '4px 8px',
                            borderRadius: '4px',
                            border: '1px solid #444',
                            background: '#1e293b',
                            color: 'white',
                            cursor: 'pointer'
                          }}
                        >
                          <option value={10}>10 / page</option>
                          <option value={25}>25 / page</option>
                          <option value={50}>50 / page</option>
                          <option value={100}>100 / page</option>
                        </select>
                        <button
                          onClick={() => setOrdersPage(1)}
                          disabled={ordersPage === 1}
                          style={{
                            padding: '4px 10px',
                            borderRadius: '4px',
                            border: '1px solid #444',
                            background: ordersPage === 1 ? '#333' : '#2563eb',
                            color: 'white',
                            cursor: ordersPage === 1 ? 'not-allowed' : 'pointer'
                          }}
                        >«</button>
                        <button
                          onClick={() => setOrdersPage(p => Math.max(1, p - 1))}
                          disabled={ordersPage === 1}
                          style={{
                            padding: '4px 10px',
                            borderRadius: '4px',
                            border: '1px solid #444',
                            background: ordersPage === 1 ? '#333' : '#2563eb',
                            color: 'white',
                            cursor: ordersPage === 1 ? 'not-allowed' : 'pointer'
                          }}
                        >‹ Prev</button>
                        <span style={{ color: '#ccc', padding: '0 8px' }}>
                          Page {ordersPage} of {totalPages}
                        </span>
                        <button
                          onClick={() => setOrdersPage(p => Math.min(totalPages, p + 1))}
                          disabled={ordersPage === totalPages}
                          style={{
                            padding: '4px 10px',
                            borderRadius: '4px',
                            border: '1px solid #444',
                            background: ordersPage === totalPages ? '#333' : '#2563eb',
                            color: 'white',
                            cursor: ordersPage === totalPages ? 'not-allowed' : 'pointer'
                          }}
                        >Next ›</button>
                        <button
                          onClick={() => setOrdersPage(totalPages)}
                          disabled={ordersPage === totalPages}
                          style={{
                            padding: '4px 10px',
                            borderRadius: '4px',
                            border: '1px solid #444',
                            background: ordersPage === totalPages ? '#333' : '#2563eb',
                            color: 'white',
                            cursor: ordersPage === totalPages ? 'not-allowed' : 'pointer'
                          }}
                        >»</button>
                      </div>
                    </div>
                  )}
                </>
              )
            ) : (
              filledOrders.length === 0 ? (
                <div className="empty-state">No filled orders today in {tradingMode}</div>
              ) : (
                <table className="orders-table filled-table">
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Side</th>
                      <th>Quantity</th>
                      <th>Fill Price</th>
                      <th>Tag</th>
                      <th>Time</th>
                      <th>ID</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filledOrders
                      .filter(o => !filterText || (o.symbol || '').toUpperCase().includes(filterText.toUpperCase()))
                      .map((order, idx) => {
                        const oid = order.order_id || `fill-${idx}`
                        const isBuy = (order.action || order.side || '').toUpperCase() === 'BUY'
                        return (
                          <tr key={oid}>
                            <td><strong>{order.symbol}</strong></td>
                            <td style={{ color: isBuy ? '#22c55e' : '#ef4444', fontWeight: 'bold' }}>
                              {order.action || order.side}
                            </td>
                            <td>{order.qty || order.quantity}</td>
                            <td>${(order.avg_fill_price || order.price || 0.0).toFixed(2)}</td>
                            <td>
                              <span className={`order-tag tag-${(order.tag || 'unknown').toLowerCase().replace(/_/g, '-')}`}>
                                {order.tag || 'N/A'}
                              </span>
                            </td>
                            <td style={{ fontSize: '0.85em', color: '#666' }}>
                              {order.timestamp ? new Date(order.timestamp * 1000).toLocaleTimeString() : (order.time || '-')}
                            </td>
                            <td style={{ fontSize: '0.8em', color: '#888' }}>{oid}</td>
                          </tr>
                        )
                      })}
                  </tbody>
                </table>
              )
            )}
          </div>
        )}

        {!loading && activeTab === 'exposure' && (
          <div className="exposure-panel">
            {exposure ? (
              <div className="exposure-metrics">
                <div className="metric-item">
                  <span className="metric-label">Total Exposure:</span>
                  <span className="metric-value">${exposure.total_exposure?.toFixed(2)}</span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Long Exposure:</span>
                  <span className="metric-value positive">${exposure.long_exposure?.toFixed(2)}</span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Short Exposure:</span>
                  <span className="metric-value negative">${exposure.short_exposure?.toFixed(2)}</span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Net Exposure:</span>
                  <span className={`metric-value ${exposure.net_exposure >= 0 ? 'positive' : 'negative'}`}>
                    ${exposure.net_exposure?.toFixed(2)}
                  </span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Position Count:</span>
                  <span className="metric-value">{exposure.position_count}</span>
                </div>
                {(exposure.befday_long_exp != null || exposure.intraday_total_chg_exp != null) && (
                  <>
                    <div className="metric-item exposure-befday-divider" style={{ gridColumn: '1 / -1', borderTop: '1px solid #333', marginTop: '6px', paddingTop: '6px' }}>
                      <span className="metric-label" style={{ fontSize: '11px' }}>BEFDAY / Intraday</span>
                    </div>
                    <div className="metric-item">
                      <span className="metric-label">BEFDAY Long:</span>
                      <span className="metric-value positive">${exposure.befday_long_exp?.toFixed(0) ?? '—'} ({exposure.befday_long_exp_pct?.toFixed(1) ?? '—'}%)</span>
                    </div>
                    <div className="metric-item">
                      <span className="metric-label">BEFDAY Short:</span>
                      <span className="metric-value negative">${exposure.befday_short_exp?.toFixed(0) ?? '—'} ({exposure.befday_short_exp_pct?.toFixed(1) ?? '—'}%)</span>
                    </div>
                    <div className="metric-item">
                      <span className="metric-label">Intra Long Chg:</span>
                      <span className={`metric-value ${(exposure.intraday_long_chg_exp ?? 0) >= 0 ? 'positive' : 'negative'}`}>${exposure.intraday_long_chg_exp?.toFixed(0) ?? '—'} ({exposure.intraday_long_chg_exp_pct?.toFixed(1) ?? '—'}%)</span>
                    </div>
                    <div className="metric-item">
                      <span className="metric-label">Intra Short Chg:</span>
                      <span className={`metric-value ${(exposure.intraday_short_chg_exp ?? 0) >= 0 ? 'negative' : 'positive'}`}>${exposure.intraday_short_chg_exp?.toFixed(0) ?? '—'} ({exposure.intraday_short_chg_exp_pct?.toFixed(1) ?? '—'}%)</span>
                    </div>
                    <div className="metric-item">
                      <span className="metric-label">Intra Total Chg:</span>
                      <span className={`metric-value ${(exposure.intraday_total_chg_exp ?? 0) >= 0 ? 'positive' : 'negative'}`}>${exposure.intraday_total_chg_exp?.toFixed(0) ?? '—'} ({exposure.intraday_total_chg_exp_pct?.toFixed(1) ?? '—'}%)</span>
                    </div>
                  </>
                )}
              </div>
            ) : (
              <div className="empty-state">
                No exposure data for {tradingMode}
              </div>
            )}
          </div>
        )}

        {activeTab === 'cleanlogs' && (
          <CleanLogsPanel tradingMode={tradingMode} />
        )}
      </div>
    </div>
  )
}

export default TradingPanels
