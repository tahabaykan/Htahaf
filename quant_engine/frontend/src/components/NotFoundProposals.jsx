import React, { useState, useEffect, useCallback } from 'react'
import './NotFoundProposals.css'

/**
 * NotFoundProposals - Displays stocks with missing/zero critical metrics
 * 
 * These stocks are excluded from KARBOTU/ADDNEWPOS/REDUCEMORE proposals
 * because their Fbtot, SFStot, GORT, or SMA values are None or exactly 0.00
 */
function NotFoundProposals({ wsConnected = false }) {
    const [notFoundStocks, setNotFoundStocks] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [lastUpdated, setLastUpdated] = useState(null)

    const fetchNotFoundStocks = useCallback(async () => {
        try {
            setLoading(true)
            const response = await fetch('/api/psfalgo/not-found')
            const result = await response.json()

            if (result.success) {
                setNotFoundStocks(result.not_found || [])
                setLastUpdated(new Date().toLocaleTimeString())
                setError(null)
            } else {
                setError(result.error || 'Failed to fetch not found stocks')
            }
        } catch (err) {
            console.error('Error fetching not found stocks:', err)
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }, [])

    // Fetch on mount and every 30 seconds
    useEffect(() => {
        fetchNotFoundStocks()
        const interval = setInterval(fetchNotFoundStocks, 30000)
        return () => clearInterval(interval)
    }, [fetchNotFoundStocks])

    // Group by missing metric type for better visibility
    const groupedByMetric = notFoundStocks.reduce((acc, stock) => {
        const missingKey = (stock.missing_metrics || []).join(', ') || 'unknown'
        if (!acc[missingKey]) {
            acc[missingKey] = []
        }
        acc[missingKey].push(stock)
        return acc
    }, {})

    return (
        <div className="not-found-proposals">
            <div className="not-found-header">
                <div className="not-found-title">
                    <span className="not-found-icon">⚠️</span>
                    <h3>NOT FOUND ONES - Data Incomplete</h3>
                    <span className="not-found-count">{notFoundStocks.length} stocks</span>
                </div>
                <div className="not-found-actions">
                    {lastUpdated && (
                        <span className="last-updated">Last: {lastUpdated}</span>
                    )}
                    <button
                        className="refresh-btn"
                        onClick={fetchNotFoundStocks}
                        disabled={loading}
                    >
                        {loading ? '⏳' : '🔄'} Refresh
                    </button>
                </div>
            </div>

            <div className="not-found-info">
                <p>
                    Bu hisseler kritik metriklerden biri veya birkaçı
                    <strong> 0.00</strong> veya <strong>N/A</strong> olduğu için
                    tüm RUNALL motorlarından (KARBOTU, ADDNEWPOS, REDUCEMORE) hariç tutuldu.
                </p>
            </div>

            {error && (
                <div className="not-found-error">
                    ⚠️ Error: {error}
                </div>
            )}

            {loading && notFoundStocks.length === 0 ? (
                <div className="not-found-loading">
                    ⏳ Loading...
                </div>
            ) : notFoundStocks.length === 0 ? (
                <div className="not-found-empty">
                    ✅ All stocks have complete data. No missing metrics detected.
                </div>
            ) : (
                <div className="not-found-content">
                    {/* Summary Cards */}
                    <div className="metric-summary-cards">
                        {Object.entries(groupedByMetric).map(([metrics, stocks]) => (
                            <div key={metrics} className="metric-card">
                                <div className="metric-card-header">
                                    <span className="metric-name">{metrics}</span>
                                    <span className="metric-count">{stocks.length}</span>
                                </div>
                                <div className="metric-symbols">
                                    {stocks.slice(0, 10).map(s => (
                                        <span key={s.symbol} className="symbol-tag">
                                            {s.symbol}
                                        </span>
                                    ))}
                                    {stocks.length > 10 && (
                                        <span className="more-tag">+{stocks.length - 10} more</span>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* Full Table */}
                    <div className="not-found-table-container">
                        <table className="not-found-table">
                            <thead>
                                <tr>
                                    <th>Symbol</th>
                                    <th>Side</th>
                                    <th>Qty</th>
                                    <th>Missing Metrics</th>
                                    <th>Source</th>
                                    <th>Reason</th>
                                </tr>
                            </thead>
                            <tbody>
                                {notFoundStocks.map((stock, index) => (
                                    <tr key={`${stock.symbol}-${index}`}>
                                        <td className="symbol-cell">{stock.symbol}</td>
                                        <td className={`side-cell ${stock.side?.toLowerCase()}`}>
                                            {stock.side}
                                        </td>
                                        <td className="qty-cell">
                                            {stock.qty?.toLocaleString()}
                                        </td>
                                        <td className="missing-cell">
                                            {(stock.missing_metrics || []).map(m => (
                                                <span key={m} className="missing-tag">{m}</span>
                                            ))}
                                        </td>
                                        <td className="source-cell">
                                            {stock.source}
                                        </td>
                                        <td className="reason-cell">
                                            {stock.reason}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    )
}

export default NotFoundProposals
