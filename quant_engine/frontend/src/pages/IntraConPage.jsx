import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import './TradingPage.css'

function IntraConPage() {
    const [status, setStatus] = useState(null)
    const [symbols, setSymbols] = useState([])
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)
    const [selectedMode, setSelectedMode] = useState('hampro')
    const [sortConfig, setSortConfig] = useState({ key: 'todays_qty_chg', direction: 'desc' })

    useEffect(() => {
        fetchStatus()
    }, [])

    useEffect(() => {
        if (status?.modes?.[selectedMode]?.initialized) {
            fetchSymbols()
        }
    }, [selectedMode, status])

    const fetchStatus = async () => {
        try {
            const res = await fetch('/api/intracon/status')
            const data = await res.json()
            setStatus(data)
        } catch (err) {
            setError('Failed to fetch IntraCon status')
        }
    }

    const fetchSymbols = async () => {
        setLoading(true)
        try {
            const res = await fetch(`/api/intracon/symbols/${selectedMode}`)
            const data = await res.json()
            if (data.success) {
                setSymbols(data.symbols || [])
            }
        } catch (err) {
            setError('Failed to fetch symbols')
        } finally {
            setLoading(false)
        }
    }

    const handleInitialize = async () => {
        setLoading(true)
        try {
            const res = await fetch(`/api/intracon/initialize/${selectedMode}`, { method: 'POST' })
            const data = await res.json()
            if (data.success) {
                await fetchStatus()
                await fetchSymbols()
            } else {
                setError(data.detail || 'Initialize failed')
            }
        } catch (err) {
            setError('Initialize failed')
        } finally {
            setLoading(false)
        }
    }

    const handleSort = (key) => {
        setSortConfig(prev => ({
            key,
            direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc'
        }))
    }

    const sortedSymbols = [...symbols].sort((a, b) => {
        const aVal = a[sortConfig.key] ?? 0
        const bVal = b[sortConfig.key] ?? 0
        const mult = sortConfig.direction === 'desc' ? -1 : 1
        if (typeof aVal === 'string') return mult * aVal.localeCompare(bVal)
        return mult * (aVal - bVal)
    })

    const getQtyChgColor = (chg) => {
        if (chg > 0) return '#22c55e'
        if (chg < 0) return '#ef4444'
        return '#6b7280'
    }

    const getRemainingColor = (remaining, limit) => {
        if (limit === 0) return '#6b7280'
        const pct = remaining / limit
        if (pct <= 0) return '#ef4444'
        if (pct < 0.3) return '#f59e0b'
        return '#22c55e'
    }

    return (
        <div className="trading-page">
            <header className="app-header">
                <h1>📊 IntraCon - Intraday Controller</h1>
                <div className="header-actions">
                    <Link to="/scanner" className="btn btn-secondary">← Back to Scanner</Link>
                </div>
            </header>

            {error && <div className="error-message">{error}</div>}

            <section className="card" style={{ background: 'linear-gradient(135deg, #1e3a5f 0%, #0f2942 100%)' }}>
                <div className="card-header">
                    <h3 style={{ color: '#fff' }}>Mode Selection & Initialize</h3>
                    <div className="card-actions">
                        <select
                            value={selectedMode}
                            onChange={e => setSelectedMode(e.target.value)}
                            style={{ padding: '8px', borderRadius: '4px' }}
                        >
                            <option value="hampro">Hammer Pro</option>
                            <option value="ibkr_ped">IBKR Ped</option>
                            <option value="ibkr_gun">IBKR Gun</option>
                        </select>
                        <button
                            className="btn btn-primary"
                            onClick={handleInitialize}
                            disabled={loading}
                        >
                            {loading ? '...' : '🔄 Initialize'}
                        </button>
                    </div>
                </div>
                <div className="card-body" style={{ color: '#e5e7eb' }}>
                    {status?.modes ? (
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '15px' }}>
                            {Object.entries(status.modes).map(([mode, info]) => (
                                <div
                                    key={mode}
                                    style={{
                                        background: mode === selectedMode ? 'rgba(59, 130, 246, 0.3)' : 'rgba(0,0,0,0.2)',
                                        padding: '15px',
                                        borderRadius: '8px',
                                        cursor: 'pointer',
                                        border: mode === selectedMode ? '2px solid #3b82f6' : '2px solid transparent'
                                    }}
                                    onClick={() => setSelectedMode(mode)}
                                >
                                    <div style={{ fontWeight: 'bold', marginBottom: '8px' }}>
                                        {mode === 'hampro' ? '🔨 Hammer Pro' : mode === 'ibkr_ped' ? '📈 IBKR Ped' : '📊 IBKR Gun'}
                                    </div>
                                    {info.initialized ? (
                                        <>
                                            <div style={{ color: '#22c55e' }}>✅ Initialized</div>
                                            <div style={{ fontSize: '12px', color: '#9ca3af' }}>
                                                {info.symbol_count} symbols | {info.total_portfolio_lots?.toLocaleString()} lots
                                            </div>
                                        </>
                                    ) : (
                                        <div style={{ color: '#f59e0b' }}>⚠️ Not initialized</div>
                                    )}
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div style={{ textAlign: 'center', color: '#9ca3af' }}>Loading status...</div>
                    )}
                </div>
            </section>

            <section className="card">
                <div className="card-header">
                    <h3>Position Intraday Status</h3>
                    <div className="card-actions">
                        <span style={{ color: '#6b7280', fontSize: '13px' }}>
                            {symbols.length} symbols | Click headers to sort
                        </span>
                    </div>
                </div>
                <div className="table-scroll" style={{ maxHeight: '600px', overflowX: 'auto' }}>
                    <table className="simple-table">
                        <thead>
                            <tr>
                                <th onClick={() => handleSort('symbol')} style={{ cursor: 'pointer' }}>Symbol</th>
                                <th onClick={() => handleSort('befday_qty')} style={{ cursor: 'pointer' }}>BefDay</th>
                                <th onClick={() => handleSort('current_qty')} style={{ cursor: 'pointer' }}>Current</th>
                                <th onClick={() => handleSort('potential_qty')} style={{ cursor: 'pointer' }}>Pot. Pos</th>
                                <th onClick={() => handleSort('todays_qty_chg')} style={{ cursor: 'pointer' }}>Chg</th>
                                <th onClick={() => handleSort('portfolio_pct')} style={{ cursor: 'pointer' }}>Port %</th>
                                <th onClick={() => handleSort('potential_pct')} style={{ cursor: 'pointer' }}>Pot %</th>
                                <th onClick={() => handleSort('maxalw')} style={{ cursor: 'pointer' }}>MAXALW</th>
                                <th onClick={() => handleSort('maxalw_headroom')} style={{ cursor: 'pointer' }}>Headroom</th>
                                <th onClick={() => handleSort('todays_add_limit')} style={{ cursor: 'pointer' }}>Daily Limit</th>
                                <th onClick={() => handleSort('todays_add_remaining')} style={{ cursor: 'pointer' }}>Remaining</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                <tr><td colSpan={11} style={{ textAlign: 'center' }}>Loading...</td></tr>
                            ) : sortedSymbols.length === 0 ? (
                                <tr><td colSpan={11} style={{ textAlign: 'center', color: '#6b7280' }}>No data. Click Initialize.</td></tr>
                            ) : sortedSymbols.map(s => (
                                <tr key={s.symbol} style={{
                                    background: s.maxalw_exceeded ? 'rgba(239, 68, 68, 0.15)' :
                                        s.potential_exceeds_maxalw ? 'rgba(245, 158, 11, 0.15)' : 'inherit'
                                }}>
                                    <td style={{ fontWeight: 'bold' }}>
                                        {s.symbol}
                                        {s.maxalw_exceeded && <span style={{ color: '#ef4444', marginLeft: '4px' }}>⛔</span>}
                                        {s.potential_exceeds_maxalw && !s.maxalw_exceeded && <span style={{ color: '#f59e0b', marginLeft: '4px' }}>⚠️</span>}
                                    </td>
                                    <td>{s.befday_qty?.toLocaleString()}</td>
                                    <td>{s.current_qty?.toLocaleString()}</td>
                                    <td style={{
                                        color: s.potential_exceeds_maxalw ? '#f59e0b' : '#6b7280',
                                        fontWeight: s.potential_qty !== s.current_qty ? 'bold' : 'normal'
                                    }}>
                                        {s.potential_qty?.toLocaleString()}
                                        {(s.pending_buy_qty > 0 || s.pending_sell_qty > 0) && (
                                            <span style={{ fontSize: '10px', marginLeft: '3px' }}>
                                                {s.pending_buy_qty > 0 && <span style={{ color: '#22c55e' }}>+{s.pending_buy_qty}</span>}
                                                {s.pending_sell_qty > 0 && <span style={{ color: '#ef4444' }}>-{s.pending_sell_qty}</span>}
                                            </span>
                                        )}
                                    </td>
                                    <td style={{ color: getQtyChgColor(s.todays_qty_chg), fontWeight: 'bold' }}>
                                        {s.todays_qty_chg > 0 ? '+' : ''}{s.todays_qty_chg?.toLocaleString()}
                                    </td>
                                    <td>{s.portfolio_pct?.toFixed(1)}%</td>
                                    <td style={{ color: s.potential_pct > s.portfolio_pct ? '#f59e0b' : '#6b7280' }}>
                                        {s.potential_pct?.toFixed(1)}%
                                    </td>
                                    <td style={{ color: s.maxalw_exceeded ? '#ef4444' : '#6b7280' }}>
                                        {s.maxalw?.toLocaleString() || '-'}
                                    </td>
                                    <td style={{
                                        color: s.maxalw_headroom <= 0 ? '#ef4444' :
                                            s.maxalw_headroom < 500 ? '#f59e0b' : '#22c55e',
                                        fontWeight: 'bold'
                                    }}>
                                        {s.maxalw ? s.maxalw_headroom?.toLocaleString() : '-'}
                                    </td>
                                    <td>{s.todays_add_limit?.toLocaleString()}</td>
                                    <td style={{ color: getRemainingColor(s.todays_add_remaining, s.todays_add_limit), fontWeight: 'bold' }}>
                                        {s.todays_add_remaining?.toLocaleString()}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </section>

            <section className="card">
                <div className="card-header">
                    <h3>Portfolio Rules</h3>
                </div>
                <div className="card-body">
                    <table className="simple-table" style={{ maxWidth: '600px' }}>
                        <thead>
                            <tr>
                                <th>Portfolio %</th>
                                <th>MAXALW Multiplier</th>
                                <th>Description</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr><td>&lt; 1%</td><td>× 0.50</td><td>Yeni pozisyon</td></tr>
                            <tr><td>1-3%</td><td>× 0.40</td><td>Küçük pozisyon</td></tr>
                            <tr><td>3-5%</td><td>× 0.30</td><td>Orta pozisyon</td></tr>
                            <tr><td>5-7%</td><td>× 0.20</td><td>Büyük pozisyon</td></tr>
                            <tr><td>7-10%</td><td>× 0.10</td><td>Çok büyük pozisyon</td></tr>
                            <tr style={{ background: 'rgba(239, 68, 68, 0.1)' }}><td>&gt;= 10%</td><td>× 0.05</td><td>Maksimum doluluk</td></tr>
                        </tbody>
                    </table>
                    <p style={{ marginTop: '15px', color: '#6b7280', fontSize: '13px' }}>
                        • Minimum emir lot'u: 200<br />
                        • Tüm emirler 100'lük yuvarlama ile
                    </p>
                </div>
            </section>
        </div>
    )
}

export default IntraConPage
