import React, { useState, useEffect } from 'react'
import './QeBenchPanel.css'

/**
 * QeBench Panel - Benchmark Performance Tracking
 * 
 * Shows positions with outperformance vs DOS Group benchmark.
 * Supports sorting by columns.
 */
const QeBenchPanel = ({ isOpen, onClose }) => {
    const [positions, setPositions] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [sortConfig, setSortConfig] = useState({ key: 'symbol', direction: 'asc' })

    const fetchPositions = async () => {
        try {
            const response = await fetch('/api/qebench/positions')
            const data = await response.json()

            if (data.success) {
                setPositions(data.positions)
                setError(null)
            } else {
                setError('Failed to load positions')
            }
        } catch (err) {
            console.error('QeBench fetch error:', err)
            setError('Connection error')
        } finally {
            setLoading(false)
        }
    }

    const handleResetAll = async () => {
        if (!confirm('Reset all outperform values to 0? This will recalculate bench@fill for all positions.')) {
            return
        }

        try {
            const response = await fetch('/api/qebench/reset-all', { method: 'POST' })
            const data = await response.json()

            if (data.success) {
                alert(`✅ ${data.message}`)
                fetchPositions()
            } else {
                alert('❌ Reset failed')
            }
        } catch (err) {
            console.error('Reset error:', err)
            alert('❌ Connection error')
        }
    }

    useEffect(() => {
        if (isOpen) {
            fetchPositions()
            const interval = setInterval(fetchPositions, 2000) // 2sec polling
            return () => clearInterval(interval)
        }
    }, [isOpen])

    const handleSort = (key) => {
        let direction = 'asc'
        if (sortConfig.key === key && sortConfig.direction === 'asc') {
            direction = 'desc'
        }
        setSortConfig({ key, direction })
    }

    const sortedPositions = [...positions].sort((a, b) => {
        if (a[sortConfig.key] < b[sortConfig.key]) {
            return sortConfig.direction === 'asc' ? -1 : 1
        }
        if (a[sortConfig.key] > b[sortConfig.key]) {
            return sortConfig.direction === 'asc' ? 1 : -1
        }
        return 0
    })

    const SortIcon = ({ column }) => {
        if (sortConfig.key !== column) return <span className="sort-icon">⇅</span>
        return <span className="sort-icon">{sortConfig.direction === 'asc' ? '↑' : '↓'}</span>
    }

    if (!isOpen) return null

    return (
        <div className="qebench-overlay" onClick={onClose}>
            <div className="qebench-panel" onClick={(e) => e.stopPropagation()}>
                {/* Header */}
                <div className="qebench-header">
                    <h2>📊 QeBench - Benchmark Performance Tracker</h2>
                    <div className="header-actions">
                        <button onClick={handleResetAll} className="reset-all-btn">
                            🔄 Reset All
                        </button>
                        <button onClick={onClose} className="close-btn">✕</button>
                    </div>
                </div>

                {/* Content */}
                <div className="qebench-content">
                    {loading && <div className="loading">Loading positions...</div>}
                    {error && <div className="error">{error}</div>}

                    {!loading && !error && positions.length === 0 && (
                        <div className="empty-state">
                            No positions tracked yet. Positions will appear here after fills are recorded.
                        </div>
                    )}

                    {positions.length > 0 && (
                        <table className="qebench-table">
                            <thead>
                                <tr>
                                    <th onClick={() => handleSort('symbol')}>Symbol <SortIcon column="symbol" /></th>
                                    <th onClick={() => handleSort('qty')}>Qty <SortIcon column="qty" /></th>
                                    <th onClick={() => handleSort('avg_cost')}>Avg Cost <SortIcon column="avg_cost" /></th>
                                    <th onClick={() => handleSort('prev_close')}>Prev Close <SortIcon column="prev_close" /></th>
                                    <th onClick={() => handleSort('daily_chg')}>Daily Chg <SortIcon column="daily_chg" /></th>
                                    <th onClick={() => handleSort('current_price')}>Last <SortIcon column="current_price" /></th>
                                    <th onClick={() => handleSort('bid')}>Bid <SortIcon column="bid" /></th>
                                    <th onClick={() => handleSort('ask')}>Ask <SortIcon column="ask" /></th>
                                    <th onClick={() => handleSort('spread')}>Spread <SortIcon column="spread" /></th>
                                    <th onClick={() => handleSort('bench_at_fill')}>Bench @Fill <SortIcon column="bench_at_fill" /></th>
                                    <th onClick={() => handleSort('bench_now')}>Bench Now <SortIcon column="bench_now" /></th>
                                    <th className="outperform-col" onClick={() => handleSort('outperform_chg')}>
                                        Outperform <SortIcon column="outperform_chg" />
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {sortedPositions.map((pos) => (
                                    <tr key={pos.symbol}>
                                        <td className="symbol-cell">{pos.symbol}</td>
                                        <td>{pos.qty.toLocaleString()}</td>
                                        <td>${pos.avg_cost.toFixed(2)}</td>
                                        <td>${pos.prev_close.toFixed(2)}</td>
                                        <td className={pos.daily_chg >= 0 ? 'positive' : 'negative'}>
                                            {pos.daily_chg >= 0 ? '+' : ''}{pos.daily_chg.toFixed(2)}
                                        </td>
                                        <td>${pos.current_price.toFixed(2)}</td>
                                        <td>${pos.bid.toFixed(2)}</td>
                                        <td>${pos.ask.toFixed(2)}</td>
                                        <td>${pos.spread.toFixed(2)}</td>
                                        <td className="bench-fill">${pos.bench_at_fill.toFixed(2)}</td>
                                        <td className="bench-now">${pos.bench_now.toFixed(2)}</td>
                                        <td className={`outperform-cell ${pos.outperform_chg >= 0 ? 'positive' : 'negative'}`}>
                                            {pos.outperform_chg >= 0 ? '+' : ''}{pos.outperform_chg.toFixed(2)}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>

                {/* Footer */}
                <div className="qebench-footer">
                    <span>Auto-refresh: 2s | Positions: {positions.length}</span>
                </div>
            </div>
        </div>
    )
}

export default QeBenchPanel
