import React, { useState, useEffect, useMemo } from 'react'
import ReactDOM from 'react-dom'

const GenobsPanel = ({ isOpen, onClose }) => {
    const [data, setData] = useState([])
    const [loading, setLoading] = useState(false)
    const [lastUpdated, setLastUpdated] = useState(null)

    // Sorting state
    const [sortBy, setSortBy] = useState('symbol')
    const [sortDirection, setSortDirection] = useState('asc')

    // Filter state (Generic)
    const [columnFilters, setColumnFilters] = useState({})

    // Global filters
    const [searchTerm, setSearchTerm] = useState('')
    const [selectedGroups, setSelectedGroups] = useState([])
    const [showGroupDropdown, setShowGroupDropdown] = useState(false)

    // Load filters from localStorage on mount
    useEffect(() => {
        const saved = localStorage.getItem('genobs_filters_v2')
        if (saved) {
            try {
                const parsed = JSON.parse(saved)
                setSelectedGroups(parsed.selectedGroups || [])
                setColumnFilters(parsed.columnFilters || {})
            } catch (e) { console.error("Filter load error", e) }
        }
    }, [])

    // Save filters on change
    const savePreset = () => {
        const filters = {
            selectedGroups,
            columnFilters
        }
        localStorage.setItem('genobs_filters_v2', JSON.stringify(filters))
        alert("Filters saved as preset!")
    }

    const handleFilterChange = (key, type, value) => {
        setColumnFilters(prev => {
            const current = prev[key] || {}
            // If value is empty, remove that key from obj
            const updated = { ...current, [type]: value }

            // Clean up empty objects
            if (!updated.min && !updated.max) {
                const newFilters = { ...prev }
                delete newFilters[key]
                return newFilters
            }

            return { ...prev, [key]: updated }
        })
    }

    const fetchData = async () => {
        setLoading(true)
        try {
            const res = await fetch(`http://localhost:8000/api/genobs/data?t=${Date.now()}`)
            const json = await res.json()
            if (json.success) {
                setData(json.data)
                setLastUpdated(new Date())
            }
        } catch (err) {
            console.error("Failed to fetch genobs data", err)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        if (isOpen) {
            fetchData()
            const interval = setInterval(fetchData, 3000) // 3 seconds refresh
            return () => clearInterval(interval)
        }
    }, [isOpen])

    // Unique groups for dropdown
    const uniqueGroups = useMemo(() => {
        const groups = [...new Set(data.map(p => p.group))].filter(Boolean).sort()
        return groups
    }, [data])

    // Toggle group
    const toggleGroup = (group) => {
        setSelectedGroups(prev =>
            prev.includes(group) ? prev.filter(g => g !== group) : [...prev, group]
        )
    }

    const handleSort = (column) => {
        if (sortBy === column) {
            setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
        } else {
            setSortBy(column)
            setSortDirection('desc')
        }
    }

    const renderSortIcon = (column) => {
        if (sortBy === column) return sortDirection === 'asc' ? ' ↑' : ' ↓'
        return ''
    }

    const filteredAndSortedData = useMemo(() => {
        let filtered = data

        // Search
        if (searchTerm.trim()) {
            const term = searchTerm.toLowerCase()
            filtered = filtered.filter(item =>
                (item.symbol || '').toLowerCase().includes(term) ||
                (item.group || '').toLowerCase().includes(term)
            )
        }

        // Groups
        if (selectedGroups.length > 0) {
            filtered = filtered.filter(item => selectedGroups.includes(item.group))
        }

        // Generic Column Filters
        // Iterate over keys in columnFilters
        Object.keys(columnFilters).forEach(key => {
            const { min = '', max = '' } = columnFilters[key]
            if (min !== '' || max !== '') {
                // Ensure we handle numeric conversion safely
                const minVal = min !== '' ? parseFloat(min) : -Infinity
                const maxVal = max !== '' ? parseFloat(max) : Infinity

                // If input is not a valid number (e.g. "-"), avoid filtering yet to prevent flashing empty
                if ((min !== '' && isNaN(minVal)) || (max !== '' && isNaN(maxVal))) {
                    return; // Skip this filter if invalid number
                }

                filtered = filtered.filter(item => {
                    const val = item[key]
                    if (val == null) return false // Filter out nulls if filter active
                    return val >= minVal && val <= maxVal
                })
            }
        })

        // Sort
        filtered.sort((a, b) => {
            let aVal = a[sortBy]
            let bVal = b[sortBy]

            // Null handling: Bottom
            if (aVal == null && bVal == null) return 0
            if (aVal == null) return 1
            if (bVal == null) return -1

            if (typeof aVal === 'string') {
                return sortDirection === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal)
            }
            return sortDirection === 'asc' ? aVal - bVal : bVal - aVal
        })

        return filtered
    }, [data, searchTerm, selectedGroups, columnFilters, sortBy, sortDirection])

    const exportToCSV = () => {
        if (!filteredAndSortedData.length) return

        const headers = Object.keys(filteredAndSortedData[0]).join(',')
        const rows = filteredAndSortedData.map(row =>
            Object.values(row).map(val => val == null ? '' : val).join(',')
        )
        const csv = [headers, ...rows].join('\n')

        const blob = new Blob([csv], { type: 'text/csv' })
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `genobs_export_${new Date().toISOString().slice(0, 10)}.csv`
        a.click()
    }

    // Helper to render filterable header
    const renderHeader = (key, label, width = '60px', highlight = false) => {
        const filter = columnFilters[key] || { min: '', max: '' }
        return (
            <th className={highlight ? 'highlight-header' : ''} style={{ minWidth: width }}>
                <div onClick={() => handleSort(key)} className="sortable-label">
                    {label}{renderSortIcon(key)}
                </div>
                <div className="filter-inputs">
                    <input
                        placeholder="Min"
                        value={filter.min || ''}
                        onChange={e => handleFilterChange(key, 'min', e.target.value)}
                        onClick={e => e.stopPropagation()}
                    />
                    <input
                        placeholder="Max"
                        value={filter.max || ''}
                        onChange={e => handleFilterChange(key, 'max', e.target.value)}
                        onClick={e => e.stopPropagation()}
                    />
                </div>
            </th>
        )
    }

    if (!isOpen) return null

    return (
        <div className="overlay-panel">
            {/* Header */}
            <div className="overlay-header">
                <h2>🧬 Genobs (General Observation - {filteredAndSortedData.length}/{data.length})</h2>
                <div style={{ display: 'flex', gap: '10px' }}>
                    <button onClick={savePreset} className="action-btn">💾 Save Filters</button>
                    <button onClick={exportToCSV} className="action-btn">📥 Export CSV</button>
                    <button onClick={onClose} className="close-btn">×</button>
                </div>
            </div>

            {/* Top Toolbar (Search & Groups only now) */}
            <div className="genobs-filter-bar">
                <input
                    className="filter-input"
                    placeholder="Search Symbol..."
                    value={searchTerm}
                    onChange={e => setSearchTerm(e.target.value)}
                />

                <div className="group-filter-wrapper">
                    <button className="filter-btn" onClick={() => setShowGroupDropdown(!showGroupDropdown)}>
                        Groups ({selectedGroups.length || 'All'}) ▼
                    </button>
                    {showGroupDropdown && (
                        <div className="group-dropdown">
                            <button onClick={() => setSelectedGroups([])}>Clear All</button>
                            {uniqueGroups.map(g => (
                                <div key={g} className="group-option" onClick={() => toggleGroup(g)}>
                                    <input type="checkbox" checked={selectedGroups.includes(g)} readOnly /> {g}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            <div className="genobs-content">
                <table className="genobs-table">
                    <thead>
                        <tr>
                            <th onClick={() => handleSort('symbol')} className="sortable" style={{ minWidth: '60px' }}>
                                Sym{renderSortIcon('symbol')}
                                <div style={{ height: '42px' }}></div> {/* Spacer for alignment */}
                            </th>
                            <th onClick={() => handleSort('group')} className="sortable" style={{ minWidth: '80px' }}>
                                Grp{renderSortIcon('group')}
                                <div style={{ height: '42px' }}></div>
                            </th>

                            {renderHeader('avg_adv', 'ADV', '70px')}

                            {/* Bid/Ask/Spread/1H Volav - Standard Columns (No Filter?) 
                                User: "bid,ask , 1h volavin sadece kendisi,haric,, bu 3 kolon disindaki her kolon bu sekildel filtrelenebilr olmali" 
                                So these 3 get NO filter inputs.
                            */}

                            <th onClick={() => handleSort('bid')} className="sortable" style={{ minWidth: '50px' }}>
                                Bid{renderSortIcon('bid')}
                                <div style={{ height: '42px' }}></div>
                            </th>
                            <th onClick={() => handleSort('ask')} className="sortable" style={{ minWidth: '50px' }}>
                                Ask{renderSortIcon('ask')}
                                <div style={{ height: '42px' }}></div>
                            </th>

                            {renderHeader('spread', 'Spr', '50px')}
                            {renderHeader('daily_chg', 'Chg', '50px')}
                            {renderHeader('ofi', 'OFI', '50px', true)}
                            {renderHeader('davg', 'Davg', '50px')}

                            {renderHeader('bid_buy', 'BidBuy', '60px')}
                            {renderHeader('ask_sell', 'AskSell', '60px')}

                            {/* Scores */}
                            {renderHeader('score_bid_volav', 'BB-Vol', '60px', true)}
                            {renderHeader('score_ask_volav', 'AS-Vol', '60px', true)}
                            {renderHeader('score_bid_truth', 'BB-Tru', '60px')}
                            {renderHeader('score_ask_truth', 'AS-Tru', '60px')}

                            {/* 1H Volav - No Filter */}
                            <th onClick={() => handleSort('volav_1h')} className="sortable" style={{ minWidth: '60px' }}>
                                1hVolav{renderSortIcon('volav_1h')}
                                <div style={{ height: '42px' }}></div>
                            </th>

                            {renderHeader('truth_price', 'Truth', '60px')}
                            {renderHeader('truth_minus_vol', 'Tru-Vol', '60px', true)}

                            {/* Metrics */}
                            {renderHeader('fbtot', 'FbTot', '50px')}
                            {renderHeader('sfstot', 'SfsTot', '50px')}
                            {renderHeader('final_thg', 'THG', '50px')}
                            {renderHeader('short_final', 'ShortF', '50px')}
                            {renderHeader('smi', 'SMI', '50px')}
                        </tr>
                    </thead>
                    <tbody>
                        {filteredAndSortedData.map(row => (
                            <tr key={row.symbol}>
                                <td className="font-bold">{row.symbol}</td>
                                <td className="tiny-text">{row.group}</td>
                                <td>{row.avg_adv}</td>

                                <td>{row.bid}</td>
                                <td>{row.ask}</td>
                                <td className={row.spread > 0.2 ? 'neg' : ''}>{row.spread}</td>

                                <td className={row.daily_chg >= 0 ? 'pos' : 'neg'}>{row.daily_chg}</td>
                                <td className={row.ofi > 0 ? 'pos-bold' : (row.ofi < 0 ? 'neg-bold' : 'neutral')}>{row.ofi}</td>

                                <td className="font-bold">{row.davg}</td>

                                <td className="highlight-cell">{row.bid_buy}</td>
                                <td className="highlight-cell">{row.ask_sell}</td>

                                {/* BB - Volav */}
                                <td className={row.score_bid_volav < 0 ? 'pos-bold' : ''}>
                                    {row.score_bid_volav != null ? row.score_bid_volav.toFixed(3) : '-'}
                                </td>
                                {/* AS - Volav */}
                                <td className={row.score_ask_volav > 0 ? 'neg-bold' : ''}>
                                    {row.score_ask_volav != null ? row.score_ask_volav.toFixed(3) : '-'}
                                </td>

                                {/* BB - Truth */}
                                <td className={row.score_bid_truth < 0 ? 'pos' : ''}>
                                    {row.score_bid_truth != null ? row.score_bid_truth.toFixed(3) : '-'}
                                </td>
                                {/* AS - Truth */}
                                <td className={row.score_ask_truth > 0 ? 'neg' : ''}>
                                    {row.score_ask_truth != null ? row.score_ask_truth.toFixed(3) : '-'}
                                </td>

                                <td>{row.volav_1h != null ? row.volav_1h : '-'}</td>
                                <td>{row.truth_price != null ? row.truth_price : '-'}</td>
                                <td className="font-bold">{row.truth_minus_vol != null ? row.truth_minus_vol.toFixed(3) : '-'}</td>

                                <td>{row.fbtot}</td>
                                <td>{row.sfstot}</td>
                                <td>{row.final_thg}</td>
                                <td>{row.short_final}</td>
                                <td>{row.smi}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <style>{`
                .overlay-panel {
                    position: fixed; top: 40px; left: 40px; right: 40px; bottom: 40px;
                    background: #121212; border: 1px solid #333; z-index: 2500;
                    display: flex; flex-direction: column; box-shadow: 0 0 25px rgba(0,0,0,0.8);
                }
                .overlay-header {
                    padding: 12px 20px; background: #1f1f1f; border-bottom: 1px solid #333;
                    display: flex; justify-content: space-between; align-items: center;
                }
                .overlay-header h2 { margin: 0; color: #a4f; }
                
                .genobs-filter-bar {
                    display: flex; gap: 10px; padding: 10px; background: #1a1a1a; border-bottom: 1px solid #333;
                    align-items: center;
                }
                .filter-input {
                    background: #2a2a2a; border: 1px solid #444; color: #fff; padding: 6px;
                    border-radius: 4px;
                }
                
                .filter-inputs {
                    display: flex; flex-direction: column; gap: 2px; margin-top: 4px;
                }
                .filter-inputs input {
                    width: 100%; box-sizing: border-box; font-size: 9px; padding: 2px;
                    background: #333; border: 1px solid #555; color: #fff; border-radius: 2px;
                }
                .sortable-label { cursor: pointer; display: flex; align-items: center; justify-content: space-between;}
                
                .filter-btn {
                    background: #333; color: #ccc; border: 1px solid #555; padding: 6px 12px; cursor: pointer;
                }
                .action-btn {
                    background: #333; color: #ccc; border: 1px solid #555; padding: 6px 12px; cursor: pointer; border-radius: 4px;
                }
                .close-btn { background: none; border: none; font-size: 20px; color: #888; cursor: pointer; }
                
                .group-filter-wrapper { position: relative; }
                .group-dropdown {
                    position: absolute; top: 100%; left: 0; background: #222; border: 1px solid #444;
                    max-height: 300px; overflow-y: auto; width: 200px; z-index: 100; padding: 5px;
                }
                .group-option { padding: 4px; cursor: pointer; color: #ddd; font-size: 12px; }
                .group-option:hover { background: #333; }
                
                .genobs-content { flex: 1; overflow: auto; background: #0e0e0e; }
                .genobs-table { width: 100%; border-collapse: collapse; color: #ccc; font-size: 11px; }
                .genobs-table th { 
                    position: sticky; top: 0; background: #1f1f1f; padding: 6px; text-align: left; 
                    border-bottom: 1px solid #444; color: #888; user-select: none; vertical-align: top;
                }
                .genobs-table td { padding: 4px 6px; border-bottom: 1px solid #222; }
                .genobs-table tr:hover { background: #1a1a1a; }
                
                .highlight-header { color: #fff; background: #2a2a2a; }
                .highlight-cell { background: #1a1a1a; font-weight: bold; }
                
                .pos { color: #0f0; }
                .neg { color: #f44; }
                .pos-bold { color: #0f0; font-weight: bold; }
                .neg-bold { color: #f44; font-weight: bold; }
                .neutral { color: #666; }
                
                .font-bold { font-weight: bold; color: #fff; }
                .tiny-text { font-size: 10px; color: #666; width: 80px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
            `}</style>
        </div>
    )
}

export default GenobsPanel
