import React, { useState, useEffect, useCallback } from 'react'
import './SidehitPressPage.css'

const API_BASE = 'http://localhost:8000/api'

function SidehitPressPage() {
    const [analyses, setAnalyses] = useState([])
    const [groups, setGroups] = useState([])
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)
    const [sortBy, setSortBy] = useState('rel_drift')
    const [sortDirection, setSortDirection] = useState('desc')
    const [searchFilter, setSearchFilter] = useState('')
    const [groupFilter, setGroupFilter] = useState('')
    const [stats, setStats] = useState({ symbols: 0, groups: 0 })

    // Best Odds From Side mode
    const [bestOddsMode, setBestOddsMode] = useState(false)
    const [bestOddsData, setBestOddsData] = useState([])
    const [bestOddsLoading, setBestOddsLoading] = useState(false)

    // Fetch analysis data
    const fetchAnalysis = useCallback(async () => {
        if (loading) return

        setLoading(true)
        setError(null)

        try {
            const params = new URLSearchParams()
            if (groupFilter) params.append('group', groupFilter)
            // No limit - fetch all symbols

            const response = await fetch(`${API_BASE}/sidehit/analysis?${params}`)

            if (!response.ok) {
                const errorData = await response.json()
                setError(errorData.detail || 'Failed to fetch analysis')
                setLoading(false)
                return
            }

            const data = await response.json()

            console.log('🔍 Sidehit Press API Response:', {
                success: data.success,
                symbol_count: data.symbol_count,
                group_count: data.group_count,
                mode: data.mode
            })

            if (data.success) {
                setAnalyses(data.symbols || [])
                setGroups(data.groups || [])
                setStats({
                    symbols: data.symbol_count || 0,
                    groups: data.group_count || 0
                })
            } else {
                setError(data.error || 'Failed to fetch analysis')
            }
        } catch (err) {
            setError(err.message || 'Network error')
        } finally {
            setLoading(false)
        }
    }, [loading, groupFilter])

    // Fetch Best Odds From Side data
    const fetchBestOdds = useCallback(async () => {
        setBestOddsLoading(true)
        setError(null)

        try {
            const params = new URLSearchParams()
            if (groupFilter) params.append('group', groupFilter)

            const response = await fetch(`${API_BASE}/sidehit/best-odds?${params}`)

            if (!response.ok) {
                const errorData = await response.json()
                setError(errorData.detail || 'Failed to fetch best odds')
                setBestOddsLoading(false)
                return
            }

            const data = await response.json()

            console.log('🎯 Best Odds API Response:', {
                success: data.success,
                symbol_count: data.symbol_count,
                symbols_with_l1: data.symbols_with_l1
            })

            if (data.success) {
                setBestOddsData(data.results || [])
            } else {
                setError(data.error || 'Failed to fetch best odds')
            }
        } catch (err) {
            setError(err.message || 'Network error')
        } finally {
            setBestOddsLoading(false)
        }
    }, [groupFilter])

    // Toggle Best Odds mode
    const handleBestOddsToggle = () => {
        const newMode = !bestOddsMode
        setBestOddsMode(newMode)
        if (newMode) {
            fetchBestOdds()
        }
    }

    // Initial load
    useEffect(() => {
        fetchAnalysis()
    }, [])

    // Get unique group IDs for filter
    const uniqueGroups = [...new Set(groups.map(g => g.group_id))].sort()

    // Filter and sort data
    const filteredAnalyses = analyses.filter((a) => {
        if (searchFilter && !a.symbol.toLowerCase().includes(searchFilter.toLowerCase())) {
            return false
        }
        if (groupFilter && a.group?.group_id !== groupFilter) {
            return false
        }
        return true
    })

    const sortedAnalyses = [...filteredAnalyses].sort((a, b) => {
        let aValue, bValue

        // String sorting
        if (sortBy === 'symbol') {
            aValue = a.symbol || ''
            bValue = b.symbol || ''
            return sortDirection === 'asc'
                ? aValue.localeCompare(bValue)
                : bValue.localeCompare(aValue)
        } else if (sortBy === 'group') {
            aValue = a.group?.group_id || ''
            bValue = b.group?.group_id || ''
            return sortDirection === 'asc'
                ? aValue.localeCompare(bValue)
                : bValue.localeCompare(aValue)
        }

        // Numeric sorting - all other columns
        if (sortBy === 'rel_drift') {
            aValue = a.group?.rel_drift_15_60 ?? null
            bValue = b.group?.rel_drift_15_60 ?? null
        } else if (sortBy === 'drift_15_60') {
            aValue = a.drift?.drift_15_60 ?? null
            bValue = b.drift?.drift_15_60 ?? null
        } else if (sortBy === 'drift_60_240') {
            aValue = a.drift?.drift_60_240 ?? null
            bValue = b.drift?.drift_60_240 ?? null
        } else if (sortBy === 'drift_240_1d') {
            aValue = a.drift?.drift_240_1d ?? null
            bValue = b.drift?.drift_240_1d ?? null
        } else if (sortBy === 'last5_tick') {
            aValue = a.last5_tick_avg ?? null
            bValue = b.last5_tick_avg ?? null
        } else if (sortBy === 'last5_vs_15m') {
            aValue = a.last5_vs_15m ?? null
            bValue = b.last5_vs_15m ?? null
        } else if (sortBy === 'last5_vs_1h') {
            aValue = a.last5_vs_1h ?? null
            bValue = b.last5_vs_1h ?? null
        } else if (sortBy === 'volav_15m') {
            aValue = a.volav_15m?.volav_price ?? null
            bValue = b.volav_15m?.volav_price ?? null
        } else if (sortBy === 'volav_1h') {
            aValue = a.volav_1h?.volav_price ?? null
            bValue = b.volav_1h?.volav_price ?? null
        } else if (sortBy === 'volav_4h') {
            aValue = a.volav_4h?.volav_price ?? null
            bValue = b.volav_4h?.volav_price ?? null
        } else if (sortBy === 'volav_1d') {
            aValue = a.volav_1d?.volav_price ?? null
            bValue = b.volav_1d?.volav_price ?? null
        } else if (sortBy === 'tick_count') {
            aValue = a.debug_metrics?.tick_count_1h ?? 0
            bValue = b.debug_metrics?.tick_count_1h ?? 0
        } else {
            // Default: no sorting
            return 0
        }

        // Handle null values - put nulls at the end
        if (aValue === null && bValue === null) return 0
        if (aValue === null) return 1
        if (bValue === null) return -1

        if (sortDirection === 'asc') {
            return aValue - bValue
        } else {
            return bValue - aValue
        }
    })

    const handleSort = (column) => {
        if (sortBy === column) {
            setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
        } else {
            setSortBy(column)
            setSortDirection('desc')
        }
    }

    // Format drift as decimal (e.g., +0.05 or -0.03)
    const formatDrift = (value) => {
        if (value === null || value === undefined) return '-'
        const sign = value >= 0 ? '+' : ''
        return `${sign}${value.toFixed(4)}`
    }

    // Format relative drift (same format)
    const formatRelDrift = (value) => {
        if (value === null || value === undefined) return '-'
        const sign = value > 0 ? '+' : ''
        return `${sign}${value.toFixed(4)}`
    }

    const getDriftColor = (value) => {
        if (value === null || value === undefined) return '#6b7280'
        if (value > 0.03) return '#10b981' // strong up
        if (value > 0) return '#22c55e' // up
        if (value < -0.03) return '#ef4444' // strong down
        if (value < 0) return '#f87171' // down
        return '#6b7280' // neutral
    }

    const getStatusBadge = (status) => {
        if (!status) return null

        const colors = {
            'OVERPERFORM_GROUP': { bg: '#dcfce7', text: '#166534' },
            'UNDERPERFORM_GROUP': { bg: '#fee2e2', text: '#991b1b' },
            'IN_LINE_WITH_GROUP': { bg: '#f3f4f6', text: '#374151' },
            'INSUFFICIENT_DATA': { bg: '#fef3c7', text: '#92400e' }
        }

        const color = colors[status] || colors['INSUFFICIENT_DATA']
        const label = status.replace(/_/g, ' ').replace('GROUP', '')

        return (
            <span
                className="status-badge"
                style={{
                    backgroundColor: color.bg,
                    color: color.text,
                    padding: '2px 6px',
                    borderRadius: '4px',
                    fontSize: '0.7rem',
                    fontWeight: '600'
                }}
            >
                {label}
            </span>
        )
    }

    const formatVolav = (volav) => {
        if (!volav || !volav.volav_price) return '-'
        return `$${volav.volav_price.toFixed(2)}`
    }

    return (
        <div className="sidehit-press-page">
            <div className="page-header">
                <h1>📊 Sidehit Press</h1>
                <p>MM Flow Scanner - VOLAV Drift & Group Analysis</p>
            </div>

            <div className="mode-banner">
                <span className="mode-tag">ANALYSIS MODE</span>
                <span className="mode-desc">Weekend/Market Closed - No L1 Required</span>
            </div>

            <div className="controls">
                <div className="control-group">
                    <input
                        type="text"
                        placeholder="Search symbol..."
                        value={searchFilter}
                        onChange={(e) => setSearchFilter(e.target.value)}
                        className="search-input"
                    />
                </div>

                <div className="control-group">
                    <label>
                        Group:
                        <select
                            value={groupFilter}
                            onChange={(e) => setGroupFilter(e.target.value)}
                            className="group-select"
                        >
                            <option value="">All Groups</option>
                            {uniqueGroups.map(g => (
                                <option key={g} value={g}>{g}</option>
                            ))}
                        </select>
                    </label>
                </div>

                <button onClick={fetchAnalysis} disabled={loading} className="refresh-btn">
                    {loading ? 'Loading...' : '🔄 Refresh'}
                </button>

                <button
                    onClick={handleBestOddsToggle}
                    disabled={bestOddsLoading}
                    className={`best-odds-btn ${bestOddsMode ? 'active' : ''}`}
                    style={{
                        marginLeft: '10px',
                        padding: '8px 16px',
                        backgroundColor: bestOddsMode ? '#10b981' : '#3b82f6',
                        color: 'white',
                        border: 'none',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        fontWeight: '600'
                    }}
                >
                    {bestOddsLoading ? '⏳ Loading...' : bestOddsMode ? '✅ Best Odds Active' : '🎯 Best Odds From Side'}
                </button>
            </div>

            {error && (
                <div className="error-message">
                    ⚠️ {error}
                </div>
            )}

            <div className="stats-bar">
                <span>
                    📈 {filteredAnalyses.length} / {stats.symbols} symbols |
                    📁 {stats.groups} groups
                </span>
            </div>

            {/* Group Summary Section */}
            {groups.length > 0 && !groupFilter && (
                <div className="groups-section">
                    <h3>Group Summary</h3>
                    <div className="groups-grid">
                        {groups.slice(0, 12).map(g => (
                            <div
                                key={g.group_id}
                                className="group-card"
                                onClick={() => setGroupFilter(g.group_id)}
                            >
                                <div className="group-name">{g.group_id}</div>
                                <div className="group-stats">
                                    <span className="stat-count">{g.symbol_count} symbols</span>
                                    {g.median_drift_15_60 !== null && (
                                        <span
                                            className="stat-drift"
                                            style={{ color: getDriftColor(g.median_drift_15_60) }}
                                        >
                                            Drift: {formatDrift(g.median_drift_15_60)}
                                        </span>
                                    )}
                                </div>
                                <div className="group-performance">
                                    {g.overperform_symbols?.length > 0 && (
                                        <span className="perf-over">↑{g.overperform_symbols.length}</span>
                                    )}
                                    {g.underperform_symbols?.length > 0 && (
                                        <span className="perf-under">↓{g.underperform_symbols.length}</span>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            <div className="table-container">
                <table className="sidehit-table">
                    <thead>
                        <tr>
                            <th onClick={() => handleSort('symbol')} className="sortable">
                                Symbol {sortBy === 'symbol' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </th>
                            <th onClick={() => handleSort('group')} className="sortable">
                                Group {sortBy === 'group' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </th>
                            <th onClick={() => handleSort('rel_drift')} className="sortable" title="Symbol drift vs Group median">
                                vs Group {sortBy === 'rel_drift' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </th>
                            <th>Status</th>
                            <th onClick={() => handleSort('drift_15_60')} className="sortable" title="15min vs 1hour drift">
                                15m→1h {sortBy === 'drift_15_60' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </th>
                            <th onClick={() => handleSort('drift_60_240')} className="sortable" title="1hour vs 4hour drift">
                                1h→4h {sortBy === 'drift_60_240' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </th>
                            <th onClick={() => handleSort('drift_240_1d')} className="sortable" title="4hour vs 1day drift">
                                4h→1d {sortBy === 'drift_240_1d' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </th>
                            <th onClick={() => handleSort('last5_tick')} className="sortable" title="Last 5 truth ticks average/mode price">
                                Son5Tick {sortBy === 'last5_tick' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </th>
                            <th onClick={() => handleSort('last5_vs_15m')} className="sortable" title="Last 5 ticks - 15m VOLAV">
                                Son5-15m {sortBy === 'last5_vs_15m' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </th>
                            <th onClick={() => handleSort('last5_vs_1h')} className="sortable" title="Last 5 ticks - 1h VOLAV">
                                Son5-1h {sortBy === 'last5_vs_1h' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </th>
                            <th onClick={() => handleSort('volav_15m')} className="sortable">
                                VOLAV 15m {sortBy === 'volav_15m' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </th>
                            <th onClick={() => handleSort('volav_1h')} className="sortable">
                                VOLAV 1h {sortBy === 'volav_1h' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </th>
                            <th onClick={() => handleSort('volav_4h')} className="sortable">
                                VOLAV 4h {sortBy === 'volav_4h' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </th>
                            <th onClick={() => handleSort('volav_1d')} className="sortable">
                                VOLAV 1d {sortBy === 'volav_1d' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </th>
                            <th onClick={() => handleSort('tick_count')} className="sortable">
                                Ticks {sortBy === 'tick_count' && (sortDirection === 'asc' ? '↑' : '↓')}
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        {/* Group by group_id and render group average row before each group's symbols */}
                        {(() => {
                            // Group analyses by group_id
                            const groupedData = {}
                            sortedAnalyses.forEach(a => {
                                const gid = a.group?.group_id || 'OTHER'
                                if (!groupedData[gid]) groupedData[gid] = []
                                groupedData[gid].push(a)
                            })

                            // Get group summaries as a map
                            const groupSummaryMap = {}
                            groups.forEach(g => {
                                groupSummaryMap[g.group_id] = g
                            })

                            return Object.entries(groupedData).map(([groupId, groupSymbols]) => {
                                const groupSummary = groupSummaryMap[groupId]
                                return (
                                    <React.Fragment key={groupId}>
                                        {/* Group Average Row */}
                                        <tr className="group-avg-row" style={{ backgroundColor: '#1f2937', fontWeight: 'bold' }}>
                                            <td style={{ color: '#f59e0b' }}>📊 {groupId} ORT</td>
                                            <td style={{ color: '#9ca3af' }}>{groupSummary?.symbol_count || groupSymbols.length} hisse</td>
                                            <td>-</td>
                                            <td>-</td>
                                            <td style={{ color: getDriftColor(groupSummary?.median_drift_15_60) }}>
                                                {formatDrift(groupSummary?.median_drift_15_60)}
                                            </td>
                                            <td style={{ color: getDriftColor(groupSummary?.median_drift_60_240) }}>
                                                {formatDrift(groupSummary?.median_drift_60_240)}
                                            </td>
                                            <td style={{ color: getDriftColor(groupSummary?.median_drift_240_1d) }}>
                                                {formatDrift(groupSummary?.median_drift_240_1d)}
                                            </td>
                                            <td style={{ color: '#60a5fa' }}>
                                                {groupSummary?.avg_last5_tick?.toFixed(2) || '-'}
                                            </td>
                                            <td style={{ color: getDriftColor(groupSummary?.avg_last5_vs_15m) }}>
                                                {formatDrift(groupSummary?.avg_last5_vs_15m)}
                                            </td>
                                            <td style={{ color: getDriftColor(groupSummary?.avg_last5_vs_1h) }}>
                                                {formatDrift(groupSummary?.avg_last5_vs_1h)}
                                            </td>
                                            <td style={{ color: '#60a5fa' }}>{groupSummary?.avg_volav_15m?.toFixed(2) || '-'}</td>
                                            <td style={{ color: '#60a5fa' }}>{groupSummary?.avg_volav_1h?.toFixed(2) || '-'}</td>
                                            <td style={{ color: '#60a5fa' }}>{groupSummary?.avg_volav_4h?.toFixed(2) || '-'}</td>
                                            <td style={{ color: '#60a5fa' }}>{groupSummary?.avg_volav_1d?.toFixed(2) || '-'}</td>
                                            <td>-</td>
                                        </tr>

                                        {/* Symbol Rows */}
                                        {groupSymbols.map((a) => {
                                            const relDrift = a.group?.rel_drift_15_60
                                            const drift15_60 = a.drift?.drift_15_60
                                            const drift60_240 = a.drift?.drift_60_240
                                            const drift240_1d = a.drift?.drift_240_1d
                                            const status = a.group?.status_15_60

                                            return (
                                                <tr key={a.symbol}>
                                                    <td className="symbol-cell">{a.symbol}</td>
                                                    <td className="group-cell">{a.group?.group_id || '-'}</td>
                                                    <td
                                                        className="drift-cell"
                                                        style={{ color: getDriftColor(relDrift), fontWeight: 'bold' }}
                                                        title={`vs Group: ${relDrift ? relDrift.toFixed(4) : '-'}`}
                                                    >
                                                        {formatRelDrift(relDrift)}
                                                    </td>
                                                    <td className="status-cell">
                                                        {getStatusBadge(status)}
                                                    </td>
                                                    <td
                                                        className="drift-cell"
                                                        style={{ color: getDriftColor(drift15_60) }}
                                                    >
                                                        {formatDrift(drift15_60)}
                                                    </td>
                                                    <td
                                                        className="drift-cell"
                                                        style={{ color: getDriftColor(drift60_240) }}
                                                    >
                                                        {formatDrift(drift60_240)}
                                                    </td>
                                                    <td
                                                        className="drift-cell"
                                                        style={{ color: getDriftColor(drift240_1d) }}
                                                    >
                                                        {formatDrift(drift240_1d)}
                                                    </td>
                                                    <td className="volav-cell" style={{ color: '#60a5fa' }}>
                                                        {a.last5_tick_avg?.toFixed(2) || '-'}
                                                    </td>
                                                    <td
                                                        className="drift-cell"
                                                        style={{ color: getDriftColor(a.last5_vs_15m) }}
                                                    >
                                                        {formatDrift(a.last5_vs_15m)}
                                                    </td>
                                                    <td
                                                        className="drift-cell"
                                                        style={{ color: getDriftColor(a.last5_vs_1h) }}
                                                    >
                                                        {formatDrift(a.last5_vs_1h)}
                                                    </td>
                                                    <td className="volav-cell">{formatVolav(a.volav_15m)}</td>
                                                    <td className="volav-cell">{formatVolav(a.volav_1h)}</td>
                                                    <td className="volav-cell">{formatVolav(a.volav_4h)}</td>
                                                    <td className="volav-cell">{formatVolav(a.volav_1d)}</td>
                                                    <td className="tick-cell">
                                                        {a.debug_metrics?.tick_count_1h || 0}
                                                    </td>
                                                </tr>
                                            )
                                        })}
                                    </React.Fragment>
                                )
                            })
                        })()}
                    </tbody>
                </table>
            </div>

            {analyses.length === 0 && !loading && !bestOddsMode && (
                <div className="empty-state">
                    <p>No analysis data available.</p>
                    <p style={{ marginTop: '10px', fontSize: '0.9rem', color: '#6b7280' }}>
                        ⚠️ Please ensure Truth Ticks data is collected during market hours.
                    </p>
                </div>
            )}

            {/* Best Odds From Side Table */}
            {bestOddsMode && (
                <div className="table-container" style={{ marginTop: '20px' }}>
                    <h3 style={{ color: '#10b981', marginBottom: '10px' }}>
                        🎯 Best Odds From Side - Son5Tick vs Bid/Ask Distance
                    </h3>
                    <table className="sidehit-table">
                        <thead>
                            <tr>
                                <th onClick={() => handleSort('symbol')} className="sortable">
                                    Symbol {sortBy === 'symbol' && (sortDirection === 'asc' ? '↑' : '↓')}
                                </th>
                                <th onClick={() => handleSort('group')} className="sortable">
                                    Group {sortBy === 'group' && (sortDirection === 'asc' ? '↑' : '↓')}
                                </th>
                                <th>Bid</th>
                                <th>Ask</th>
                                <th onClick={() => handleSort('last5_tick')} className="sortable">
                                    Son5Tick {sortBy === 'last5_tick' && (sortDirection === 'asc' ? '↑' : '↓')}
                                </th>
                                <th onClick={() => handleSort('odd_bid_distance')} className="sortable" title="Son5Tick - Bid (positive = good for selling)">
                                    oddBidDist {sortBy === 'odd_bid_distance' && (sortDirection === 'asc' ? '↑' : '↓')}
                                </th>
                                <th onClick={() => handleSort('odd_ask_distance')} className="sortable" title="Ask - Son5Tick (positive = good for buying)">
                                    oddAskDist {sortBy === 'odd_ask_distance' && (sortDirection === 'asc' ? '↑' : '↓')}
                                </th>
                                <th>VOLAV 15m</th>
                                <th>VOLAV 1h</th>
                                <th onClick={() => handleSort('last5_vs_15m')} className="sortable">
                                    Son5-15m {sortBy === 'last5_vs_15m' && (sortDirection === 'asc' ? '↑' : '↓')}
                                </th>
                                <th onClick={() => handleSort('last5_vs_1h')} className="sortable">
                                    Son5-1h {sortBy === 'last5_vs_1h' && (sortDirection === 'asc' ? '↑' : '↓')}
                                </th>
                                <th>Ticks</th>
                            </tr>
                        </thead>
                        <tbody>
                            {(() => {
                                // Sort best odds data
                                const sortedBestOdds = [...bestOddsData].sort((a, b) => {
                                    let aValue, bValue

                                    if (sortBy === 'symbol') {
                                        return sortDirection === 'asc'
                                            ? (a.symbol || '').localeCompare(b.symbol || '')
                                            : (b.symbol || '').localeCompare(a.symbol || '')
                                    } else if (sortBy === 'group') {
                                        return sortDirection === 'asc'
                                            ? (a.group_id || '').localeCompare(b.group_id || '')
                                            : (b.group_id || '').localeCompare(a.group_id || '')
                                    } else if (sortBy === 'odd_bid_distance') {
                                        aValue = a.odd_bid_distance ?? null
                                        bValue = b.odd_bid_distance ?? null
                                    } else if (sortBy === 'odd_ask_distance') {
                                        aValue = a.odd_ask_distance ?? null
                                        bValue = b.odd_ask_distance ?? null
                                    } else if (sortBy === 'last5_tick') {
                                        aValue = a.last5_tick_avg ?? null
                                        bValue = b.last5_tick_avg ?? null
                                    } else if (sortBy === 'last5_vs_15m') {
                                        aValue = a.last5_vs_15m ?? null
                                        bValue = b.last5_vs_15m ?? null
                                    } else if (sortBy === 'last5_vs_1h') {
                                        aValue = a.last5_vs_1h ?? null
                                        bValue = b.last5_vs_1h ?? null
                                    } else {
                                        return 0
                                    }

                                    if (aValue === null && bValue === null) return 0
                                    if (aValue === null) return 1
                                    if (bValue === null) return -1

                                    return sortDirection === 'asc' ? aValue - bValue : bValue - aValue
                                })

                                // Filter by group and search
                                const filteredBestOdds = sortedBestOdds.filter(item => {
                                    if (searchFilter && !item.symbol.toLowerCase().includes(searchFilter.toLowerCase())) {
                                        return false
                                    }
                                    if (groupFilter && item.group_id !== groupFilter) {
                                        return false
                                    }
                                    return true
                                })

                                // Group data by group_id
                                const groupedData = {}
                                filteredBestOdds.forEach(item => {
                                    const gid = item.group_id || 'OTHER'
                                    if (!groupedData[gid]) groupedData[gid] = []
                                    groupedData[gid].push(item)
                                })

                                return Object.entries(groupedData).map(([groupId, items]) => (
                                    <React.Fragment key={groupId}>
                                        {/* Group Header Row */}
                                        <tr style={{ backgroundColor: '#1f2937', fontWeight: 'bold' }}>
                                            <td colSpan="12" style={{ color: '#f59e0b', padding: '8px' }}>
                                                📊 {groupId} ({items.length} hisse)
                                            </td>
                                        </tr>

                                        {/* Symbol Rows */}
                                        {items.map(item => (
                                            <tr key={item.symbol}>
                                                <td className="symbol-cell">{item.symbol}</td>
                                                <td>{item.group_id}</td>
                                                <td style={{ color: '#60a5fa' }}>
                                                    {item.bid ? `$${item.bid.toFixed(2)}` : '-'}
                                                </td>
                                                <td style={{ color: '#60a5fa' }}>
                                                    {item.ask ? `$${item.ask.toFixed(2)}` : '-'}
                                                </td>
                                                <td style={{ color: '#a78bfa' }}>
                                                    {item.last5_tick_avg ? `$${item.last5_tick_avg.toFixed(2)}` : '-'}
                                                </td>
                                                <td style={{
                                                    color: item.odd_bid_distance > 0 ? '#10b981' : item.odd_bid_distance < 0 ? '#f87171' : '#6b7280',
                                                    fontWeight: 'bold'
                                                }}>
                                                    {item.odd_bid_distance !== null ? formatDrift(item.odd_bid_distance) : '-'}
                                                </td>
                                                <td style={{
                                                    color: item.odd_ask_distance > 0 ? '#10b981' : item.odd_ask_distance < 0 ? '#f87171' : '#6b7280',
                                                    fontWeight: 'bold'
                                                }}>
                                                    {item.odd_ask_distance !== null ? formatDrift(item.odd_ask_distance) : '-'}
                                                </td>
                                                <td>{item.volav_15m ? `$${item.volav_15m.toFixed(2)}` : '-'}</td>
                                                <td>{item.volav_1h ? `$${item.volav_1h.toFixed(2)}` : '-'}</td>
                                                <td style={{ color: getDriftColor(item.last5_vs_15m) }}>
                                                    {formatDrift(item.last5_vs_15m)}
                                                </td>
                                                <td style={{ color: getDriftColor(item.last5_vs_1h) }}>
                                                    {formatDrift(item.last5_vs_1h)}
                                                </td>
                                                <td>{item.tick_count || 0}</td>
                                            </tr>
                                        ))}
                                    </React.Fragment>
                                ))
                            })()}
                        </tbody>
                    </table>

                    {bestOddsData.length === 0 && !bestOddsLoading && (
                        <div className="empty-state">
                            <p>No Best Odds data available.</p>
                            <p style={{ marginTop: '10px', fontSize: '0.9rem', color: '#6b7280' }}>
                                ⚠️ L1 data (bid/ask) required. Please ensure market is open.
                            </p>
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}

export default SidehitPressPage
