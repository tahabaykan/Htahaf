import React, { useState, useEffect, useCallback } from 'react'
import './GreatestMMPage.css'

const API_BASE = 'http://localhost:8000/api'

function GreatestMMPage() {
    const [analyses, setAnalyses] = useState([])
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)
    const [sortBy, setSortBy] = useState('best_long_score')
    const [sortDirection, setSortDirection] = useState('desc')
    const [searchFilter, setSearchFilter] = useState('')
    const [showOnlyActionable, setShowOnlyActionable] = useState(true)
    const [stats, setStats] = useState({ total: 0, actionable: 0 })

    // Fetch analysis data
    const fetchAnalysis = useCallback(async () => {
        if (loading) return
        setLoading(true)
        setError(null)

        try {
            const response = await fetch(`${API_BASE}/greatest-mm/analysis`)
            if (!response.ok) {
                const errorData = await response.json()
                setError(errorData.detail || 'Failed to fetch analysis')
                setLoading(false)
                return
            }

            const data = await response.json()
            console.log('🎯 Greatest MM Response:', {
                success: data.success,
                symbol_count: data.symbol_count,
                actionable_count: data.actionable_count
            })

            if (data.success) {
                setAnalyses(data.analyses || [])
                setStats({
                    total: data.symbol_count || 0,
                    actionable: data.actionable_count || 0
                })
            } else {
                setError(data.error || 'Failed to fetch analysis')
            }
        } catch (err) {
            setError(err.message || 'Network error')
        } finally {
            setLoading(false)
        }
    }, [loading])

    useEffect(() => {
        fetchAnalysis()
    }, [])

    // Filter and sort
    const filteredAnalyses = analyses.filter(a => {
        if (searchFilter && !a.symbol.toLowerCase().includes(searchFilter.toLowerCase())) {
            return false
        }
        if (showOnlyActionable && !a.long_actionable && !a.short_actionable) {
            return false
        }
        return true
    })

    const sortedAnalyses = [...filteredAnalyses].sort((a, b) => {
        let aValue, bValue

        if (sortBy === 'symbol') {
            return sortDirection === 'asc'
                ? a.symbol.localeCompare(b.symbol)
                : b.symbol.localeCompare(a.symbol)
        } else if (sortBy === 'best_long_score') {
            aValue = a.best_long_score ?? -999
            bValue = b.best_long_score ?? -999
        } else if (sortBy === 'best_short_score') {
            aValue = a.best_short_score ?? -999
            bValue = b.best_short_score ?? -999
        } else if (sortBy === 'spread') {
            aValue = a.spread ?? 0
            bValue = b.spread ?? 0
        }

        return sortDirection === 'asc' ? aValue - bValue : bValue - aValue
    })

    const handleSort = (column) => {
        if (sortBy === column) {
            setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
        } else {
            setSortBy(column)
            setSortDirection('desc')
        }
    }

    const formatPrice = (value) => {
        if (value === null || value === undefined) return '-'
        return `$${value.toFixed(2)}`
    }

    const formatScore = (value) => {
        if (value === null || value === undefined) return '-'
        return value.toFixed(1)
    }

    const getScoreColor = (score) => {
        if (score === null || score === undefined) return '#6b7280'
        if (score >= 50) return '#10b981'
        if (score >= 30) return '#22c55e'
        if (score >= 0) return '#f59e0b'
        return '#ef4444'
    }

    const getScenarioLabel = (type) => {
        const labels = {
            'ORIGINAL': 'Org',
            'NEW_SON5': 'NewS5',
            'NEW_ENTRY': 'NewEnt',
            'BOTH_NEW': 'Both'
        }
        return labels[type] || type
    }

    return (
        <div className="greatest-mm-page">
            <div className="page-header">
                <h1>🎯 Greatest MM Quant</h1>
                <p>4-Scenario Market Making Score Analysis</p>
            </div>

            <div className="stats-banner">
                <span className="stat-item">📊 Total: {stats.total}</span>
                <span className="stat-item actionable">✅ Actionable: {stats.actionable}</span>
                <span className="stat-item">Threshold: 30+</span>
            </div>

            <div className="controls">
                <input
                    type="text"
                    placeholder="Search symbol..."
                    value={searchFilter}
                    onChange={(e) => setSearchFilter(e.target.value)}
                    className="search-input"
                />

                <label className="checkbox-label">
                    <input
                        type="checkbox"
                        checked={showOnlyActionable}
                        onChange={(e) => setShowOnlyActionable(e.target.checked)}
                    />
                    Show only actionable (30+)
                </label>

                <button onClick={fetchAnalysis} disabled={loading} className="refresh-btn">
                    {loading ? '⏳ Loading...' : '🔄 Refresh'}
                </button>
            </div>

            {error && (
                <div className="error-message">⚠️ {error}</div>
            )}

            <div className="table-container">
                <table className="mm-table">
                    <thead>
                        <tr>
                            <th onClick={() => handleSort('symbol')} className="sortable">
                                Symbol {sortBy === 'symbol' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </th>
                            <th>Bid</th>
                            <th>Ask</th>
                            <th onClick={() => handleSort('spread')} className="sortable">
                                Spread {sortBy === 'spread' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </th>
                            <th>Son5Tick</th>
                            <th>NewPrint</th>
                            <th onClick={() => handleSort('best_long_score')} className="sortable">
                                Best Long {sortBy === 'best_long_score' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </th>
                            <th>Long Entry</th>
                            <th onClick={() => handleSort('best_short_score')} className="sortable">
                                Best Short {sortBy === 'best_short_score' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </th>
                            <th>Short Entry</th>
                            <th>Scenarios</th>
                        </tr>
                    </thead>
                    <tbody>
                        {sortedAnalyses.map(a => (
                            <tr key={a.symbol} className={a.long_actionable || a.short_actionable ? 'actionable-row' : ''}>
                                <td className="symbol-cell">{a.symbol}</td>
                                <td>{formatPrice(a.bid)}</td>
                                <td>{formatPrice(a.ask)}</td>
                                <td>{a.spread ? `$${a.spread.toFixed(2)}` : '-'}</td>
                                <td style={{ color: '#a78bfa' }}>{formatPrice(a.son5_tick)}</td>
                                <td style={{ color: a.has_new_print ? '#22c55e' : '#6b7280' }}>
                                    {a.has_new_print ? formatPrice(a.new_print) : '-'}
                                </td>
                                <td style={{
                                    color: getScoreColor(a.best_long_score),
                                    fontWeight: a.long_actionable ? 'bold' : 'normal'
                                }}>
                                    {a.long_actionable && '✅ '}
                                    {formatScore(a.best_long_score)}
                                    {a.best_long_scenario && (
                                        <span className="scenario-tag">{getScenarioLabel(a.best_long_scenario)}</span>
                                    )}
                                </td>
                                <td style={{ color: a.long_actionable ? '#10b981' : '#6b7280' }}>
                                    {a.best_long_entry ? formatPrice(a.best_long_entry) : '-'}
                                </td>
                                <td style={{
                                    color: getScoreColor(a.best_short_score),
                                    fontWeight: a.short_actionable ? 'bold' : 'normal'
                                }}>
                                    {a.short_actionable && '✅ '}
                                    {formatScore(a.best_short_score)}
                                    {a.best_short_scenario && (
                                        <span className="scenario-tag">{getScenarioLabel(a.best_short_scenario)}</span>
                                    )}
                                </td>
                                <td style={{ color: a.short_actionable ? '#ef4444' : '#6b7280' }}>
                                    {a.best_short_entry ? formatPrice(a.best_short_entry) : '-'}
                                </td>
                                <td className="scenarios-cell">
                                    {a.scenarios && a.scenarios.map((s, i) => (
                                        <div key={i} className="scenario-mini">
                                            <span className="scenario-type">{getScenarioLabel(s.scenario_type)}</span>
                                            <span style={{ color: getScoreColor(s.mm_long) }}>L:{formatScore(s.mm_long)}</span>
                                            <span style={{ color: getScoreColor(s.mm_short) }}>S:{formatScore(s.mm_short)}</span>
                                        </div>
                                    ))}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {sortedAnalyses.length === 0 && !loading && (
                <div className="empty-state">
                    <p>No analysis data available.</p>
                    <p style={{ marginTop: '10px', fontSize: '0.9rem', color: '#6b7280' }}>
                        ⚠️ L1 data (bid/ask) required. Please ensure market is open.
                    </p>
                </div>
            )}
        </div>
    )
}

export default GreatestMMPage
