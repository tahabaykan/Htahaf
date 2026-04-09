import React, { useState, useEffect, useMemo } from 'react'
import './GemProposalsPanel.css'

const GemProposalsPanel = () => {
    const [proposals, setProposals] = useState([])
    const [loading, setLoading] = useState(false)
    const [lastUpdate, setLastUpdate] = useState(null)
    
    // Exposure state
    const [realExposure, setRealExposure] = useState(null)
    const [estCurRatio, setEstCurRatio] = useState(44.0) // Default %44
    const [maxExposure, setMaxExposure] = useState(1200000) // Default $1.2M
    
    // Load MM settings on mount
    useEffect(() => {
        const loadMMSettings = async () => {
            try {
                const res = await fetch('/api/xnl/mm/settings')
                const data = await res.json()
                if (data.success && data.settings) {
                    if (data.settings.est_cur_ratio !== undefined) {
                        setEstCurRatio(data.settings.est_cur_ratio)
                    }
                }
            } catch (err) {
                console.error("Failed to load MM settings", err)
            }
        }
        loadMMSettings()
    }, [])
    
    // Save MM settings when Est/Cur ratio changes (debounced)
    useEffect(() => {
        const saveTimer = setTimeout(async () => {
            try {
                await fetch('/api/xnl/mm/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ est_cur_ratio: estCurRatio })
                })
            } catch (err) {
                console.error("Failed to save MM settings", err)
            }
        }, 1000) // Debounce 1 second
        
        return () => clearTimeout(saveTimer)
    }, [estCurRatio])
    
    // Selection state (separate for LONG and SHORT)
    const [selectedLongs, setSelectedLongs] = useState(new Set())
    const [selectedShorts, setSelectedShorts] = useState(new Set())

    // Fetch Standard Proposals from PSFALGO API
    const fetchProposals = async () => {
        setLoading(true)
        try {
            // Fetch latest 500 proposals to ensure we catch MM ones
            const res = await fetch(`/api/psfalgo/proposals/latest?limit=500&t=${Date.now()}`)
            const data = await res.json()
            if (data.success && data.proposals) {
                // Filter only GREATEST_MM engine proposals
                const mmProposals = data.proposals.filter(p => (p.engine || '').includes('MM'))
                setProposals(mmProposals)
                setLastUpdate(new Date())
            }
        } catch (err) {
            console.error("Failed to fetch MM proposals", err)
        } finally {
            setLoading(false)
        }
    }

    // Fetch real exposure
    const fetchRealExposure = async () => {
        try {
            const res = await fetch('/api/psfalgo/state')
            const data = await res.json()
            if (data.success && data.state?.exposure) {
                setRealExposure(data.state.exposure)
                // Use same source as ADDNEWPOS: limit_max_exposure or pot_max
                const maxExp = data.state.account_state?.limit_max_exposure || 
                              data.state.account_state?.pot_max || 
                              data.state.exposure.pot_max || 
                              1200000
                setMaxExposure(maxExp)
            }
        } catch (err) {
            console.error("Failed to fetch exposure", err)
        }
    }

    useEffect(() => {
        fetchProposals()
        fetchRealExposure()
        const interval = setInterval(() => {
            fetchProposals()
            fetchRealExposure()
        }, 65000)  // 65 sn: emir dongusu ile uyumlu
        return () => clearInterval(interval)
    }, [])

    // Split into Longs (BUY) and Shorts (SELL) - Apply Est/Cur ratio to limit count
    const { longs, shorts, exposureData } = useMemo(() => {
        const longMap = new Map()
        const shortMap = new Map()

        proposals.forEach(p => {
            // Parse metrics
            let metrics = p.metrics_used || p.metrics || {}
            if (typeof metrics === 'string') {
                try { metrics = JSON.parse(metrics) } catch (e) { }
            }
            p.parsedMetrics = metrics

            const side = (p.side || '').toUpperCase()
            const score = metrics.mm_score || 0

            // Filter: Score must be < 180
            if (score >= 180) return

            const isLong = side.includes('BUY')
            const isShort = side.includes('SELL')

            if (isLong) {
                if (!longMap.has(p.symbol) || (score > longMap.get(p.symbol).parsedMetrics.mm_score)) {
                    longMap.set(p.symbol, p)
                }
            } else if (isShort) {
                if (!shortMap.has(p.symbol) || (score > shortMap.get(p.symbol).parsedMetrics.mm_score)) {
                    shortMap.set(p.symbol, p)
                }
            }
        })

        let longs = Array.from(longMap.values())
        let shorts = Array.from(shortMap.values())

        // Sort by Score Descending
        longs.sort((a, b) => (b.parsedMetrics.mm_score || 0) - (a.parsedMetrics.mm_score || 0))
        shorts.sort((a, b) => (b.parsedMetrics.mm_score || 0) - (a.parsedMetrics.mm_score || 0))

        // Calculate default count (50 long + 50 short = 100 total)
        const defaultCount = 50
        const currentExp = realExposure?.pot_total || 1000000
        const estValue = currentExp * (estCurRatio / 100)
        
        // Calculate how many stocks we need (200 lot × avg_price × count = estValue)
        // For MM: lot is fixed 200, so we adjust count
        const avgPrice = 22 // Default estimate
        const lotPerStock = 200
        const valuePerStock = lotPerStock * avgPrice
        const targetCount = Math.floor(estValue / valuePerStock)
        
        // Limit to reasonable range (min 5, max 100)
        const finalCount = Math.max(5, Math.min(100, Math.floor(targetCount / 2))) // Divide by 2 for long+short
        
        // Apply Est/Cur ratio: if estCurRatio is 50% of default, take top 25 instead of 50
        const ratioMultiplier = estCurRatio / 44.0 // Default is 44%
        const adjustedCount = Math.max(5, Math.min(100, Math.floor(defaultCount * ratioMultiplier)))

        // Take top N stocks
        const finalLongs = longs.slice(0, adjustedCount)
        const finalShorts = shorts.slice(0, adjustedCount)

        // Calculate exposure metrics
        const totalLots = (finalLongs.length + finalShorts.length) * 200
        const estCons = totalLots * avgPrice
        const curExp = currentExp
        const maxExp = maxExposure
        const estToCur = curExp > 0 ? (estCons / curExp * 100) : 0
        const estToMax = maxExp > 0 ? (estCons / maxExp * 100) : 0
        const curToMax = maxExp > 0 ? (curExp / maxExp * 100) : 0

        return {
            longs: finalLongs,
            shorts: finalShorts,
            exposureData: {
                totalLots,
                estCons,
                curExp,
                maxExp,
                estToCur,
                estToMax,
                curToMax
            }
        }
    }, [proposals, estCurRatio, realExposure, maxExposure])

    // Selection handlers
    const toggleSelection = (proposalId, isLong) => {
        if (isLong) {
            setSelectedLongs(prev => {
                const newSet = new Set(prev)
                if (newSet.has(proposalId)) {
                    newSet.delete(proposalId)
                } else {
                    newSet.add(proposalId)
                }
                return newSet
            })
        } else {
            setSelectedShorts(prev => {
                const newSet = new Set(prev)
                if (newSet.has(proposalId)) {
                    newSet.delete(proposalId)
                } else {
                    newSet.add(proposalId)
                }
                return newSet
            })
        }
    }

    const selectAll = (data, isLong) => {
        const allIds = new Set(data.map(p => p.id || `${p.symbol}_${p.side}`))
        if (isLong) {
            setSelectedLongs(allIds)
        } else {
            setSelectedShorts(allIds)
        }
    }

    const deselectAll = (isLong) => {
        if (isLong) {
            setSelectedLongs(new Set())
        } else {
            setSelectedShorts(new Set())
        }
    }

    // Send orders handlers
    const handleSendBuyOrders = async () => {
        if (selectedLongs.size === 0) {
            alert('No orders selected')
            return
        }

        if (!confirm(`Send ${selectedLongs.size} BUY orders?`)) return

        try {
            // Get selected proposals
            const selectedProposals = longs.filter(p => {
                const id = p.id || `${p.symbol}_${p.side}`
                return selectedLongs.has(id)
            })

            // Accept and execute each proposal
            let successCount = 0
            let failCount = 0
            const errors = []

            for (const proposal of selectedProposals) {
                const proposalId = proposal.id
                if (!proposalId) {
                    failCount++
                    errors.push(`${proposal.symbol}: No proposal ID`)
                    continue
                }

                try {
                    const response = await fetch(`/api/psfalgo/proposals/${proposalId}/accept`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' }
                    })

                    const result = await response.json()
                    if (result.success) {
                        successCount++
                    } else {
                        failCount++
                        errors.push(`${proposal.symbol}: ${result.message || 'Unknown error'}`)
                    }
                } catch (err) {
                    failCount++
                    errors.push(`${proposal.symbol}: ${err.message}`)
                }
            }

            if (failCount === 0) {
                alert(`Successfully sent ${successCount} BUY orders`)
            } else {
                alert(`Sent ${successCount} orders, ${failCount} failed.\n\nErrors:\n${errors.slice(0, 5).join('\n')}${errors.length > 5 ? '\n...' : ''}`)
            }

            setSelectedLongs(new Set())
        } catch (err) {
            console.error('Error sending buy orders:', err)
            alert('Error sending orders: ' + err.message)
        }
    }

    const handleSendSellOrders = async () => {
        if (selectedShorts.size === 0) {
            alert('No orders selected')
            return
        }

        if (!confirm(`Send ${selectedShorts.size} SELL orders?`)) return

        try {
            // Get selected proposals
            const selectedProposals = shorts.filter(p => {
                const id = p.id || `${p.symbol}_${p.side}`
                return selectedShorts.has(id)
            })

            // Accept and execute each proposal
            let successCount = 0
            let failCount = 0
            const errors = []

            for (const proposal of selectedProposals) {
                const proposalId = proposal.id
                if (!proposalId) {
                    failCount++
                    errors.push(`${proposal.symbol}: No proposal ID`)
                    continue
                }

                try {
                    const response = await fetch(`/api/psfalgo/proposals/${proposalId}/accept`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' }
                    })

                    const result = await response.json()
                    if (result.success) {
                        successCount++
                    } else {
                        failCount++
                        errors.push(`${proposal.symbol}: ${result.message || 'Unknown error'}`)
                    }
                } catch (err) {
                    failCount++
                    errors.push(`${proposal.symbol}: ${err.message}`)
                }
            }

            if (failCount === 0) {
                alert(`Successfully sent ${successCount} SELL orders`)
            } else {
                alert(`Sent ${successCount} orders, ${failCount} failed.\n\nErrors:\n${errors.slice(0, 5).join('\n')}${errors.length > 5 ? '\n...' : ''}`)
            }

            setSelectedShorts(new Set())
        } catch (err) {
            console.error('Error sending sell orders:', err)
            alert('Error sending orders: ' + err.message)
        }
    }

    const ProposalTable = ({ data, title, type }) => {
        const isLong = type === 'long'
        const selectedSet = isLong ? selectedLongs : selectedShorts
        const selectedCount = selectedSet.size

        return (
            <div className={`mm-section ${type}`}>
                <div className={`mm-header ${type}`}>
                    <h3>{title} ({data.length})</h3>
                    <div className="mm-header-controls">
                        <button 
                            className="mm-control-btn"
                            onClick={() => selectAll(data, isLong)}
                            title="Select All"
                        >
                            Select All
                        </button>
                        <button 
                            className="mm-control-btn"
                            onClick={() => deselectAll(isLong)}
                            title="Deselect All"
                        >
                            Deselect
                        </button>
                        {isLong ? (
                            <button 
                                className="mm-send-btn mm-send-buy"
                                onClick={handleSendBuyOrders}
                                disabled={selectedCount === 0}
                                title="Send Buy Orders"
                            >
                                Send Buy Orders ({selectedCount})
                            </button>
                        ) : (
                            <button 
                                className="mm-send-btn mm-send-sell"
                                onClick={handleSendSellOrders}
                                disabled={selectedCount === 0}
                                title="Send Sell Orders"
                            >
                                Send Sell Orders ({selectedCount})
                            </button>
                        )}
                    </div>
                </div>
                <div className="mm-table-container">
                    <table className="mm-table">
                        <thead>
                            <tr>
                                <th style={{ width: '30px' }}>☐</th>
                                <th>Sym</th>
                                <th>Score</th>
                                <th>Price</th>
                                <th>Bid</th>
                                <th>Ask</th>
                                <th>Spread</th>
                                <th>Prev Close</th>
                                <th>Bench Chg</th>
                                <th>Scenario</th>
                                <th>Son5</th>
                                <th>NewP</th>
                            </tr>
                        </thead>
                        <tbody>
                            {data.length === 0 ? (
                                <tr>
                                    <td colSpan="12" className="empty-cell">No {title} Proposals</td>
                                </tr>
                            ) : (
                                data.map((p, idx) => {
                                    const proposalId = p.id || `${p.symbol}_${p.side}`
                                    const isSelected = selectedSet.has(proposalId)
                                    const bid = p.bid || p.parsedMetrics?.bid || 0
                                    const ask = p.ask || p.parsedMetrics?.ask || 0
                                    const spread = p.spread || (ask - bid) || 0
                                    const prevClose = p.prev_close || p.parsedMetrics?.prev_close || 0
                                    const benchChg = p.bench_chg || p.parsedMetrics?.benchmark_chg || p.parsedMetrics?.bench_chg || 0
                                    
                                    return (
                                        <tr 
                                            key={idx}
                                            className={isSelected ? 'mm-row-selected' : ''}
                                            onClick={() => toggleSelection(proposalId, isLong)}
                                            style={{ cursor: 'pointer' }}
                                        >
                                            <td onClick={(e) => e.stopPropagation()}>
                                                <input
                                                    type="checkbox"
                                                    checked={isSelected}
                                                    onChange={() => toggleSelection(proposalId, isLong)}
                                                    style={{ cursor: 'pointer' }}
                                                />
                                            </td>
                                            <td className="sym-cell">{p.symbol}</td>
                                            <td className="score-cell">{p.parsedMetrics.mm_score?.toFixed(1) || '-'}</td>
                                            <td className="price-cell">{p.price?.toFixed(2) || '-'}</td>
                                            <td className="bid-cell">{bid.toFixed(2)}</td>
                                            <td className="ask-cell">{ask.toFixed(2)}</td>
                                            <td className="spread-cell">{spread.toFixed(2)}</td>
                                            <td className="prev-close-cell">{prevClose.toFixed(2)}</td>
                                            <td className={`bench-chg-cell ${benchChg >= 0 ? 'positive' : 'negative'}`}>
                                                {benchChg >= 0 ? '+' : ''}{benchChg.toFixed(2)}
                                            </td>
                                            <td className="scenario-cell">{p.parsedMetrics.scenario || '-'}</td>
                                            <td className="son5-cell">{p.parsedMetrics.son5_tick?.toFixed(2) || '-'}</td>
                                            <td className="newp-cell" style={{ color: '#00d2ff' }}>
                                                {p.parsedMetrics.new_print ? p.parsedMetrics.new_print.toFixed(2) : '-'}
                                            </td>
                                        </tr>
                                    )
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        )
    }

    return (
        <div className="mm-panel-container">
            {/* Exposure Panel */}
            {exposureData && (
                <div className="mm-exposure-panel">
                    <div className="exposure-horizontal-row">
                        <div className="exposure-item">
                            <span className="exposure-icon">📦</span>
                            <span className="exposure-label">Tot. Lots (MM):</span>
                            <span className="exposure-value blue">{exposureData.totalLots.toLocaleString()}</span>
                        </div>
                        <span className="exp-sep">|</span>
                        <div className="exposure-item">
                            <span className="exposure-icon">💰</span>
                            <span className="exposure-label">Est. Cons:</span>
                            <span className="exposure-value cyan">${exposureData.estCons.toLocaleString()}</span>
                        </div>
                        <span className="exp-sep">|</span>
                        <div className="exposure-item">
                            <span className="exposure-icon">📊</span>
                            <span className="exposure-label">Cur Exp:</span>
                            <span className="exposure-value green">${exposureData.curExp.toLocaleString()}</span>
                        </div>
                        <span className="exp-sep">|</span>
                        <div className="exposure-item">
                            <span className="exposure-icon">🎯</span>
                            <span className="exposure-label">Max Exp:</span>
                            <span className="exposure-value orange">${exposureData.maxExp.toLocaleString()}</span>
                        </div>
                        <span className="exp-sep">|</span>
                        <div className="exposure-slider-group">
                            <label>Est/Cur:</label>
                            <input
                                type="range"
                                min="0"
                                max="100"
                                step="0.1"
                                value={estCurRatio}
                                onChange={(e) => setEstCurRatio(parseFloat(e.target.value))}
                                className="exposure-slider"
                            />
                            <span className="slider-value">{estCurRatio.toFixed(1)}%</span>
                        </div>
                        <span className="exp-sep">|</span>
                        <div className="exposure-ratios-inline">
                            <span className="ratio-item">
                                Est/Cur: <span className="ratio-value">{exposureData.estToCur.toFixed(1)}%</span>
                            </span>
                            <span className="ratio-item">
                                Est/Max: <span className="ratio-value">{exposureData.estToMax.toFixed(1)}%</span>
                            </span>
                            <span className="ratio-item">
                                Cur/Max: <span className="ratio-value">{exposureData.curToMax.toFixed(1)}%</span>
                            </span>
                        </div>
                    </div>
                </div>
            )}

            <div className="mm-split-view">
                {/* LONGS (LEFT) */}
                <ProposalTable data={longs} title="LONG (BUY)" type="long" />

                {/* SHORTS (RIGHT) */}
                <ProposalTable data={shorts} title="SHORT (SELL)" type="short" />
            </div>

            <div className="mm-footer">
                <span>Total MM Proposals: {proposals.length}</span>
                <span>Last Update: {lastUpdate ? lastUpdate.toLocaleTimeString() : 'Never'}</span>
                <span style={{ marginLeft: 'auto', fontSize: '11px', color: '#666' }}>* Range: 30-250 Score | Lot: 200 (fixed)</span>
            </div>
        </div>
    )
}

export default GemProposalsPanel
