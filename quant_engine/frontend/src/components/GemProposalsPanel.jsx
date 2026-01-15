import React, { useState, useEffect, useMemo } from 'react'
import ReactDOM from 'react-dom'

const GemProposalsPanel = ({ isOpen, onClose }) => {
    const [proposals, setProposals] = useState([])
    const [loading, setLoading] = useState(false)

    // Inspector State
    const [selectedSymbol, setSelectedSymbol] = useState(null)
    const [inspectorData, setInspectorData] = useState(null)
    const [inspectLoading, setInspectLoading] = useState(false)

    // Sorting state
    const [sortBy, setSortBy] = useState('divergence')
    const [sortDirection, setSortDirection] = useState('desc')

    // Filter state
    const [searchTerm, setSearchTerm] = useState('')
    const [selectedGroups, setSelectedGroups] = useState([])
    const [showGroupDropdown, setShowGroupDropdown] = useState(false)

    const fetchProposals = async () => {
        setLoading(true)
        try {
            const res = await fetch(`http://localhost:8000/api/gem-proposals/?t=${Date.now()}`)
            const data = await res.json()
            if (data.success) {
                setProposals(data.data)
            }
        } catch (err) {
            console.error("Failed to fetch proposals", err)
        } finally {
            setLoading(false)
        }
    }

    const fetchInspectorData = async (symbol) => {
        setInspectLoading(true)
        setInspectorData(null)
        try {
            const res = await fetch(`http://localhost:8000/api/gem-proposals/inspect/${symbol}?t=${Date.now()}`)
            const data = await res.json()
            if (data.success) {
                setInspectorData(data.data)
            }
        } catch (err) {
            console.error("Failed to fetch inspection", err)
        } finally {
            setInspectLoading(false)
        }
    }

    const handleRowClick = (symbol) => {
        setSelectedSymbol(symbol)
        fetchInspectorData(symbol)
    }

    const closeInspector = () => {
        setSelectedSymbol(null)
        setInspectorData(null)
    }

    useEffect(() => {
        if (isOpen) {
            fetchProposals()
            const interval = setInterval(fetchProposals, 5000)
            return () => clearInterval(interval)
        }
    }, [isOpen])

    // Get unique groups for filter dropdown
    const uniqueGroups = useMemo(() => {
        const groups = [...new Set(proposals.map(p => p.group))].filter(Boolean).sort()
        return groups
    }, [proposals])

    // Sort handler
    const handleSort = (column) => {
        if (sortBy === column) {
            setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
        } else {
            setSortBy(column)
            setSortDirection('desc')
        }
    }

    // Toggle group selection
    const toggleGroup = (group) => {
        setSelectedGroups(prev =>
            prev.includes(group)
                ? prev.filter(g => g !== group)
                : [...prev, group]
        )
    }

    const selectAllGroups = () => setSelectedGroups([...uniqueGroups])
    const clearAllGroups = () => setSelectedGroups([])

    // Filter and sort proposals
    const filteredAndSortedProposals = useMemo(() => {
        let filtered = proposals

        // Filter by search term (group name)
        if (searchTerm.trim()) {
            const term = searchTerm.toLowerCase()
            filtered = filtered.filter(p =>
                p.group?.toLowerCase().includes(term) ||
                p.symbol?.toLowerCase().includes(term)
            )
        }

        // Filter by selected groups
        if (selectedGroups.length > 0) {
            filtered = filtered.filter(p => selectedGroups.includes(p.group))
        }

        // Sort
        const sorted = [...filtered].sort((a, b) => {
            let aValue, bValue

            switch (sortBy) {
                case 'symbol':
                    aValue = a.symbol ?? ''
                    bValue = b.symbol ?? ''
                    break
                case 'group':
                    aValue = a.group ?? ''
                    bValue = b.group ?? ''
                    break
                case 'price':
                    aValue = parseFloat(a.price) || null
                    bValue = parseFloat(b.price) || null
                    break
                case 'rr':
                    aValue = a.rr ?? null
                    bValue = b.rr ?? null
                    break
                case 'divergence':
                    aValue = (a.divergence !== null && a.divergence !== undefined) ? a.divergence : null
                    bValue = (b.divergence !== null && b.divergence !== undefined) ? b.divergence : null
                    break
                case 'action':
                    aValue = a.action ?? ''
                    bValue = b.action ?? ''
                    break
                case 'qty':
                    aValue = a.qty ?? null
                    bValue = b.qty ?? null
                    break
                case 'reason':
                    aValue = a.reason ?? ''
                    bValue = b.reason ?? ''
                    break
                case 'has_truth':
                    aValue = a.has_truth_tick ? 1 : 0
                    bValue = b.has_truth_tick ? 1 : 0
                    break
                case 'prev_close':
                    aValue = parseFloat(a.prev_close) || null
                    bValue = parseFloat(b.prev_close) || null
                    break
                case 'grp_avg_prev':
                    aValue = parseFloat(a.grp_avg_prev) || null
                    bValue = parseFloat(b.grp_avg_prev) || null
                    break
                case 'div_1h':
                    aValue = a.div_1h ?? null
                    bValue = b.div_1h ?? null
                    break
                case 'div_4h':
                    aValue = a.div_4h ?? null
                    bValue = b.div_4h ?? null
                    break
                case 'div_1d':
                    aValue = a.div_1d ?? null
                    bValue = b.div_1d ?? null
                    break
                case 'div_2d':
                    aValue = a.div_2d ?? null
                    bValue = b.div_2d ?? null
                    break
                case 'davg':
                    aValue = a.davg ?? null
                    bValue = b.davg ?? null
                    break
                case 'fbtot':
                    aValue = a.fbtot ?? null
                    bValue = b.fbtot ?? null
                    break
                case 'sfstot':
                    aValue = a.sfstot ?? null
                    bValue = b.sfstot ?? null
                    break
                default:
                    return 0
            }

            // Handle null values - ALWAYS AT BOTTOM
            if (aValue === null && bValue === null) return 0
            if (aValue === null) return 1
            if (bValue === null) return -1

            if (typeof aValue === 'string' && typeof bValue === 'string') {
                return sortDirection === 'asc'
                    ? aValue.localeCompare(bValue)
                    : bValue.localeCompare(aValue)
            }

            return sortDirection === 'asc' ? aValue - bValue : bValue - aValue
        })

        return sorted
    }, [proposals, searchTerm, selectedGroups, sortBy, sortDirection])

    if (!isOpen) return null

    const renderSortIcon = (column) => {
        if (sortBy === column) {
            return sortDirection === 'asc' ? ' ↑' : ' ↓'
        }
        return ''
    }

    return (
        <div className="overlay-panel">
            <div className="overlay-header">
                <h2>💎 Gem Proposals ({filteredAndSortedProposals.length}/{proposals.length})</h2>
                <button onClick={onClose} className="close-btn">×</button>
            </div>

            {/* Filter Controls */}
            <div className="gem-filters">
                <div className="filter-row">
                    <input
                        type="text"
                        placeholder="🔍 Search by Symbol or Group..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="search-input"
                    />

                    <div className="group-filter">
                        <button
                            className="group-filter-btn"
                            onClick={() => setShowGroupDropdown(!showGroupDropdown)}
                        >
                            📁 Groups ({selectedGroups.length || 'All'}) ▼
                        </button>

                        {showGroupDropdown && (
                            <div className="group-dropdown">
                                <div className="group-dropdown-actions">
                                    <button onClick={selectAllGroups}>Select All</button>
                                    <button onClick={clearAllGroups}>Clear All</button>
                                </div>
                                <div className="group-list">
                                    {uniqueGroups.map(group => (
                                        <label key={group} className="group-item">
                                            <input
                                                type="checkbox"
                                                checked={selectedGroups.includes(group)}
                                                onChange={() => toggleGroup(group)}
                                            />
                                            <span>{group}</span>
                                        </label>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            <div className="gem-content">
                {loading && proposals.length === 0 ? (
                    <div className="loading">Loading Gems...</div>
                ) : proposals.length === 0 ? (
                    <div style={{ padding: '20px', color: '#888' }}>
                        No proposals found. (Backend API returned 0 items)
                    </div>
                ) : filteredAndSortedProposals.length === 0 ? (
                    <div style={{ padding: '20px', color: '#888' }}>
                        No proposals match your filter criteria.
                    </div>
                ) : (
                    <table className="gem-table">
                        <thead>
                            <tr>
                                <th onClick={() => handleSort('symbol')} className="sortable">Sym{renderSortIcon('symbol')}</th>
                                <th onClick={() => handleSort('group')} className="sortable">Grp{renderSortIcon('group')}</th>
                                <th onClick={() => handleSort('price')} className="sortable">Px{renderSortIcon('price')}</th>
                                <th onClick={() => handleSort('rr')} className="sortable">RelRet{renderSortIcon('rr')}</th>
                                <th onClick={() => handleSort('davg')} className="sortable highlight-header">Davg{renderSortIcon('davg')}</th>
                                <th onClick={() => handleSort('divergence')} className="sortable">D.Now{renderSortIcon('divergence')}</th>
                                <th onClick={() => handleSort('div_1h')} className="sortable">1H{renderSortIcon('div_1h')}</th>
                                <th onClick={() => handleSort('div_4h')} className="sortable">4H{renderSortIcon('div_4h')}</th>
                                <th onClick={() => handleSort('div_1d')} className="sortable">1D{renderSortIcon('div_1d')}</th>
                                <th onClick={() => handleSort('div_2d')} className="sortable">2D{renderSortIcon('div_2d')}</th>
                                <th onClick={() => handleSort('fbtot')} className="sortable">FbTot{renderSortIcon('fbtot')}</th>
                                <th onClick={() => handleSort('sfstot')} className="sortable">SfsTot{renderSortIcon('sfstot')}</th>
                                <th onClick={() => handleSort('action')} className="sortable">Act{renderSortIcon('action')}</th>
                                <th onClick={() => handleSort('has_truth')} className="sortable">T{renderSortIcon('has_truth')}</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredAndSortedProposals.map((p, idx) => (
                                <tr
                                    key={idx}
                                    className={p.is_fake_print ? "fake-print-row clickable-row" : "clickable-row"}
                                    onClick={() => handleRowClick(p.symbol)}
                                    title="Click to view full inspection details"
                                >
                                    <td>{p.symbol}</td>
                                    <td className="tiny-text">{p.group}</td>
                                    <td>{p.price}</td>
                                    <td className={p.rr >= 0 ? 'positive-cents' : 'negative-cents'}>{p.rr >= 0 ? '+' : ''}{p.rr.toFixed(2)}</td>
                                    <td className={p.davg != null ? (p.davg >= 0 ? 'positive-cents highlight-cell' : 'negative-cents highlight-cell') : 'na-cell highlight-cell'}>
                                        {p.davg != null ? (p.davg >= 0 ? '+' : '') + p.davg.toFixed(2) : '-'}
                                    </td>
                                    <td className={p.divergence >= 0 ? 'positive-cents' : 'negative-cents'}>{p.divergence >= 0 ? '+' : ''}{p.divergence.toFixed(2)}</td>
                                    <td className={p.div_1h != null ? (p.div_1h >= 0 ? 'positive-cents' : 'negative-cents') : 'na-cell'}>{p.div_1h != null ? p.div_1h.toFixed(2) : '-'}</td>
                                    <td className={p.div_4h != null ? (p.div_4h >= 0 ? 'positive-cents' : 'negative-cents') : 'na-cell'}>{p.div_4h != null ? p.div_4h.toFixed(2) : '-'}</td>
                                    <td className={p.div_1d != null ? (p.div_1d >= 0 ? 'positive-cents' : 'negative-cents') : 'na-cell'}>{p.div_1d != null ? p.div_1d.toFixed(2) : '-'}</td>
                                    <td className={p.div_2d != null ? (p.div_2d >= 0 ? 'positive-cents' : 'negative-cents') : 'na-cell'}>{p.div_2d != null ? p.div_2d.toFixed(2) : '-'}</td>

                                    <td className="metric-cell">{p.fbtot != null ? p.fbtot.toFixed(2) : '-'}</td>
                                    <td className="metric-cell">{p.sfstot != null ? p.sfstot.toFixed(2) : '-'}</td>

                                    <td className={`action-${p.action.toLowerCase()}`}>{p.action}</td>
                                    <td className={p.has_truth_tick ? 'truth-yes' : 'truth-no'}>{p.has_truth_tick ? '✓' : ''}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {/* INSPECTOR MODAL */}
            {selectedSymbol && (
                <div className="inspector-overlay" onClick={closeInspector}>
                    <div className="inspector-modal" onClick={e => e.stopPropagation()}>
                        <div className="inspector-header">
                            <h3>🔍 Gem Inspector: {selectedSymbol}</h3>
                            <button onClick={closeInspector}>✕</button>
                        </div>
                        <div className="inspector-body">
                            {inspectLoading ? (
                                <div className="loading">Loading details...</div>
                            ) : !inspectorData ? (
                                <div className="error">No detailed data available yet. Please wait for next engine cycle.</div>
                            ) : (
                                <>
                                    <div className="inspector-section">
                                        <h4>Current Truth Status <span className="group-badge">{inspectorData.group}</span></h4>
                                        <div className="metrics-grid">
                                            <div className="metric-box">
                                                <label>Effective Price</label>
                                                <div className="value">{inspectorData.current?.price?.toFixed(2)}</div>
                                            </div>
                                            <div className="metric-box">
                                                <label>Davg</label>
                                                <div className={`value ${inspectorData.current?.davg >= 0 ? 'pos' : 'neg'}`}>
                                                    {inspectorData.current?.davg != null ? inspectorData.current?.davg.toFixed(2) : '-'}
                                                </div>
                                            </div>
                                            <div className="metric-box">
                                                <label>Truth Size</label>
                                                <div className="value">{inspectorData.current?.size}</div>
                                            </div>
                                            <div className="metric-box">
                                                <label>Change (vs PrevCl)</label>
                                                <div className={`value ${inspectorData.current?.change >= 0 ? 'pos' : 'neg'}`}>
                                                    {inspectorData.current?.change?.toFixed(2)}
                                                </div>
                                            </div>
                                        </div>
                                        <div className="metrics-grid" style={{ marginTop: '10px' }}>
                                            <div className="metric-box">
                                                <label>Fbtot</label>
                                                <div className="value">{inspectorData.current?.fbtot != null ? inspectorData.current?.fbtot.toFixed(2) : '-'}</div>
                                            </div>
                                            <div className="metric-box">
                                                <label>Sfstot</label>
                                                <div className="value">{inspectorData.current?.sfstot != null ? inspectorData.current?.sfstot.toFixed(2) : '-'}</div>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="inspector-section">
                                        <h4>Timeframe Divergence Breakdown</h4>
                                        <table className="inspector-table">
                                            <thead>
                                                <tr>
                                                    <th>TF</th>
                                                    <th>Hist. Volav Price</th>
                                                    <th>Stock Change</th>
                                                    <th>Group Avg Change</th>
                                                    <th>Divergence (Stock - Grp)</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {['1h', '4h', '1d', '2d'].map(tf => {
                                                    const d = inspectorData.timeframes?.[tf];
                                                    if (!d) return null;
                                                    return (
                                                        <tr key={tf}>
                                                            <td className="tf-label">{tf.toUpperCase()}</td>
                                                            <td>{d.hist_price ? d.hist_price.toFixed(2) : '-'}</td>
                                                            <td className={d.change_cents >= 0 ? 'pos' : 'neg'}>
                                                                {d.change_cents != null ? d.change_cents.toFixed(2) : '-'}
                                                            </td>
                                                            <td className={d.group_avg_change >= 0 ? 'pos' : 'neg'}>
                                                                {d.group_avg_change != null ? d.group_avg_change.toFixed(2) : '-'}
                                                            </td>
                                                            <td className={d.divergence >= 0 ? 'pos-bold' : 'neg-bold'}>
                                                                {d.divergence != null ? d.divergence.toFixed(2) : '-'}
                                                            </td>
                                                        </tr>
                                                    )
                                                })}
                                            </tbody>
                                        </table>
                                        <p className="inspector-note">
                                            * <b>Divergence Formula:</b> (Current Truth - Hist Volav) - (Group Avg Change)
                                        </p>
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                </div>
            )}

            <style>{`
        .overlay-panel {
          position: fixed; top: 50px; left: 50px; right: 50px; bottom: 50px;
          background: #1e1e1e; border: 1px solid #444; z-index: 1000;
          display: flex; flex-direction: column; box-shadow: 0 0 20px rgba(0,0,0,0.5);
        }
        .overlay-header {
            padding: 10px 15px; background: #252525; border-bottom: 1px solid #333;
            display: flex; justify-content: space-between; align-items: center;
        }
        .overlay-header h2 { margin: 0; color: #00d4ff; font-size: 18px; }
        .close-btn { background: none; border: none; color: #fff; font-size: 24px; cursor: pointer; }
        
        /* Filter Styles */
        .gem-filters {
            padding: 8px 15px; background: #252525; border-bottom: 1px solid #333;
        }
        .filter-row {
            display: flex; gap: 8px; align-items: center;
        }
        .search-input {
            flex: 1; padding: 6px 10px; background: #1a1a1a; border: 1px solid #444;
            border-radius: 4px; color: #fff; font-size: 13px;
        }
        .search-input:focus {
            outline: none; border-color: #00d4ff;
        }
        .search-input::placeholder {
            color: #666;
        }
        .group-filter {
            position: relative;
        }
        .group-filter-btn {
            padding: 6px 12px; background: #333; border: 1px solid #555;
            border-radius: 4px; color: #fff; cursor: pointer; font-size: 13px;
        }
        .group-filter-btn:hover {
            background: #444;
        }
        .group-dropdown {
            position: absolute; top: 100%; right: 0; margin-top: 4px;
            background: #2a2a2a; border: 1px solid #444; border-radius: 4px;
            min-width: 220px; max-height: 300px; overflow-y: auto; z-index: 100;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4);
        }
        .group-dropdown-actions {
            display: flex; gap: 8px; padding: 8px; border-bottom: 1px solid #444;
        }
        .group-dropdown-actions button {
            flex: 1; padding: 6px 8px; background: #444; border: none;
            border-radius: 3px; color: #fff; cursor: pointer; font-size: 12px;
        }
        .group-dropdown-actions button:hover {
            background: #555;
        }
        .group-list {
            max-height: 240px; overflow-y: auto;
        }
        .group-item {
            display: flex; align-items: center; gap: 8px; padding: 8px 12px;
            cursor: pointer; color: #ddd;
        }
        .group-item:hover {
            background: #333;
        }
        .group-item input[type="checkbox"] {
            accent-color: #00d4ff;
        }
        
        .gem-content { padding: 0; overflow: auto; flex: 1; }
        .gem-table { width: 100%; border-collapse: collapse; color: #ddd; font-size: 12px; }
        .gem-table th, .gem-table td { padding: 4px 6px; text-align: left; border-bottom: 1px solid #333; }
        .gem-table th { color: #888; position: sticky; top: 0; background: #1e1e1e; font-weight: 600; white-space: nowrap; }
        
        /* Sortable Headers */
        .gem-table th.sortable {
            cursor: pointer; user-select: none; transition: background 0.2s;
        }
        .gem-table th.sortable:hover {
            background: rgba(0, 212, 255, 0.1); color: #00d4ff;
        }
        
        .highlight-header { color: #fff !important; background: #2a2a2a !important; }
        .highlight-cell { background: #252525; font-weight: bold; }

        .action-sell { color: #ff4444; font-weight: bold; }
        .action-buy { color: #00ff88; font-weight: bold; }
        .action-watch { color: #ffaa00; font-weight: bold; }
        .fake-print-row { opacity: 0.5; }
        .truth-yes { color: #00ff88; font-weight: bold; text-align: center; }
        .truth-no { color: #666; text-align: center; }
        .positive-cents { color: #00ff88; }
        .negative-cents { color: #ff4444; }
        .na-cell { color: #555; text-align: center; }
        .tiny-text { font-size: 10px; color: #888; white-space: nowrap; overflow: hidden; max-width: 80px; text-overflow: ellipsis; }
        .metric-cell { color: #ccc; }

        .clickable-row { cursor: pointer; transition: background 0.1s; }
        .clickable-row:hover { background: #2a2a2a; }

        /* INSPECTOR MODAL STYLES */
        .inspector-overlay {
            position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.7); z-index: 2000;
            display: flex; justify-content: center; align-items: center;
            backdrop-filter: blur(2px);
        }
        .inspector-modal {
            background: #1e1e1e; width: 600px; max-width: 90%; max-height: 90vh;
            border: 1px solid #555; box-shadow: 0 0 30px rgba(0,0,0,0.8);
            border-radius: 8px; display: flex; flex-direction: column; overflow: hidden;
        }
        .inspector-header {
            padding: 15px; background: #252525; border-bottom: 1px solid #444;
            display: flex; justify-content: space-between; align-items: center;
        }
        .inspector-header h3 { margin: 0; color: #fff; }
        .inspector-header button {
            background: none; border: none; color: #888; font-size: 20px; cursor: pointer;
        }
        .inspector-header button:hover { color: #fff; }
        
        .inspector-body { padding: 20px; overflow-y: auto; }
        .inspector-section { margin-bottom: 25px; }
        .inspector-section h4 { color: #888; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 15px; }
        
        .group-badge {
            background: #333; padding: 2px 6px; border-radius: 4px; color: #aaa; font-size: 12px; margin-left: 8px;
        }
        
        .metrics-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
        .metric-box { background: #252525; padding: 10px; border-radius: 4px; text-align: center; }
        .metric-box label { display: block; color: #666; font-size: 10px; margin-bottom: 4px; text-transform: uppercase; }
        .metric-box .value { font-size: 16px; font-weight: bold; color: #fff; }
        .source-tag { font-size: 10px !important; color: #00d4ff !important; word-break: break-all; }
        
        .inspector-table { width: 100%; border-collapse: collapse; font-size: 13px; }
        .inspector-table th { text-align: left; padding: 8px; border-bottom: 1px solid #444; color: #666; }
        .inspector-table td { padding: 8px; border-bottom: 1px solid #333; color: #ddd; }
        .tf-label { font-weight: bold; color: #00d4ff !important; }
        
        .pos { color: #00ff88; }
        .neg { color: #ff4444; }
        .pos-bold { color: #00ff88; font-weight: bold; font-size: 14px; }
        .neg-bold { color: #ff4444; font-weight: bold; font-size: 14px; }
        
        .inspector-note { font-size: 11px; color: #666; margin-top: 10px; font-style: italic; }
        
      `}</style>
        </div>
    )
}

export default GemProposalsPanel
