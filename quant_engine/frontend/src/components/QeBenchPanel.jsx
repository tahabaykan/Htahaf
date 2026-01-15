import React, { useState, useEffect } from 'react'
import './QeBenchPanel.css'

/**
 * QeBench Panel - Benchmark Performance Tracking
 * 
 * Shows positions with outperformance vs DOS Group benchmark.
 */
const QeBenchPanel = ({ isOpen, onClose }) => {
    const [positions, setPositions] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

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
                                    <th>Symbol</th>
                                    <th>Qty</th>
                                    <th>Avg Cost</th>
                                    <th>Prev Close</th>
                                    <th>Daily Chg</th>
                                    <th>Last</th>
                                    <th>Bid</th>
                                    <th>Ask</th>
                                    <th>Spread</th>
                                    <th>Bench @Fill</th>
                                    <th>Bench Now</th>
                                    <th className="outperform-col">Outperform</th>
                                </tr>
                            </thead>
                            <tbody>
                                {positions.map((pos) => (
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
