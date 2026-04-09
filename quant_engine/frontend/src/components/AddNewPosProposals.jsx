import React, { useState, useEffect, useCallback, useRef } from 'react'
import './AddNewPosProposals.css'
import JFINTabBB from './JFINTabBB'
import JFINTabFB from './JFINTabFB'
import JFINTabSAS from './JFINTabSAS'
import JFINTabSFS from './JFINTabSFS'
import OrderConfirmModal from './OrderConfirmModal'

// Default filter values
const DEFAULT_FILTERS = {
    fbtot_min: '',
    fbtot_max: '',
    sfstot_min: '',
    sfstot_max: '',
    gort_min: '',
    gort_max: '',
    sma63_min: '',
    sma63_max: '',
    sma246_min: '',
    sma246_max: '',
    // NEW: Ucuzluk/Pahalilik filters
    bid_buy_ucuzluk_min: '',
    bid_buy_ucuzluk_max: '',
    ask_sell_pahalilik_min: '',
    ask_sell_pahalilik_max: ''
}

const FILTER_STORAGE_KEY = 'addnewpos_filters'

/**
 * AddNewPosProposals - JFIN Intents Display for ADDNEWPOS Tab
 * 
 * Fetches JFIN state from `/api/psfalgo/jfin/state`
 * Displays 4 sub-tabs: BB | FB | SAS | SFS
 * Includes filter panel for Fbtot, SFStot, GORT, SMA with save/load
 */
function AddNewPosProposals({ wsConnected }) {
    const [activeSubTab, setActiveSubTab] = useState('BB')
    const [jfinState, setJfinState] = useState(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)
    const [percentage, setPercentage] = useState(50)
    const [realExposure, setRealExposure] = useState(null)  // Real exposure from /api/psfalgo/state
    const [estCurRatio, setEstCurRatio] = useState(28.8) // Default Est/Cur ratio for lot adjustment

    // Filter panel state
    const [showFilters, setShowFilters] = useState(false)
    const [filters, setFilters] = useState(DEFAULT_FILTERS)

    // Order confirmation modal state
    const [showConfirmModal, setShowConfirmModal] = useState(false)
    const [pendingOrders, setPendingOrders] = useState([])
    const [pendingPercentage, setPendingPercentage] = useState(50)
    const [confirmLoading, setConfirmLoading] = useState(false)
    const [filterAutoSaveStatus, setFilterAutoSaveStatus] = useState(null) // 'saving' | 'saved' | 'error'
    const filterSaveTimer = useRef(null)

    // Active filtered stocks (synced from child tabs)
    const [activeFilteredStocks, setActiveFilteredStocks] = useState([]) // Stocks currently visible in active tab

    // Load saved filters on mount
    useEffect(() => {
        try {
            const saved = localStorage.getItem(FILTER_STORAGE_KEY)
            if (saved) {
                const parsed = JSON.parse(saved)
                setFilters({ ...DEFAULT_FILTERS, ...parsed })
            }
        } catch (e) {
            console.error('Error loading saved filters:', e)
        }
    }, [])

    useEffect(() => {
        loadJFINState()
        loadRealExposure()
        // Poll for updates every 3 seconds
        const interval = setInterval(() => {
            loadJFINState()
            loadRealExposure()
        }, 3000)
        return () => clearInterval(interval)
    }, [])

    // Fetch real exposure from /api/psfalgo/state
    const loadRealExposure = async () => {
        try {
            const response = await fetch('/api/psfalgo/state')
            const result = await response.json()
            if (result.success && result.state?.exposure) {
                setRealExposure(result.state.exposure)
            }
        } catch (err) {
            console.error('[ADDNEWPOS] Error loading real exposure:', err)
        }
    }

    const loadJFINState = async () => {
        try {
            setLoading(true)
            setError(null)
            const response = await fetch('/api/psfalgo/jfin/state')
            const result = await response.json()

            if (result.success && result.state) {
                setJfinState(result.state)
                if (result.state.percentage) {
                    setPercentage(result.state.percentage)
                }
            } else if (result.is_empty) {
                setError(result.message || 'JFIN state is empty. Start RUNALL to generate data.')
            } else {
                setError(result.detail || result.error || 'Failed to load JFIN state')
            }
        } catch (err) {
            console.error('[ADDNEWPOS] Error loading state:', err)
            setError(err.message || 'Failed to load JFIN state')
        } finally {
            setLoading(false)
        }
    }

    // Open confirmation modal with orders preview
    const handleOpenConfirmModal = (newPercentage) => {
        // Use filtered stocks from the active tab if available, otherwise fallback to raw data
        let orders = []

        if (activeFilteredStocks && activeFilteredStocks.length > 0) {
            // Use stocks currently visible in the UI (filtered by child tab)
            orders = activeFilteredStocks
        } else {
            // Fallback: Get current tab's stocks based on activeSubTab (using parent filters which might be empty)
            if (activeSubTab === 'BB') {
                orders = applyFilters(jfinState?.bb_stocks, 'LONG') || []
            } else if (activeSubTab === 'FB') {
                orders = applyFilters(jfinState?.fb_stocks, 'LONG') || []
            } else if (activeSubTab === 'SAS') {
                orders = applyFilters(jfinState?.sas_stocks, 'SHORT') || []
            } else if (activeSubTab === 'SFS') {
                orders = applyFilters(jfinState?.sfs_stocks, 'SHORT') || []
            }
        }

        // Calculate final_lot at new percentage
        // CRITICAL FIX: Use addable_lot (which is maxalw constrained) instead of calculated_lot
        const ordersWithAdjustedLots = orders.map(o => ({
            ...o,
            final_lot: Math.floor((o.addable_lot || o.calculated_lot || 0) * (newPercentage / 100))
        })).filter(o => o.final_lot >= 200)

        setPendingOrders(ordersWithAdjustedLots)
        setPendingPercentage(newPercentage)
        setShowConfirmModal(true)
    }

    // Confirm and execute orders
    const handleConfirmOrders = async () => {
        try {
            setConfirmLoading(true)

            // First update the percentage
            const response = await fetch('/api/psfalgo/jfin/update-percentage', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ percentage: pendingPercentage })
            })
            const result = await response.json()

            if (result.success) {
                setPercentage(pendingPercentage)
                await loadJFINState()
                setShowConfirmModal(false)
                setPendingOrders([])
            } else {
                setError(result.detail || result.error || 'Failed to update percentage')
            }
        } catch (err) {
            console.error('[ADDNEWPOS] Error confirming orders:', err)
            setError(err.message || 'Failed to confirm orders')
        } finally {
            setConfirmLoading(false)
        }
    }

    const handleUpdatePercentage = async (newPercentage) => {
        // Open confirmation modal instead of directly updating
        handleOpenConfirmModal(newPercentage)
    }

    // Filter handlers - auto-save on change
    const doSaveFilters = useCallback(async (filtersToSave) => {
        try {
            setFilterAutoSaveStatus('saving')
            localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(filtersToSave))
            // Also save to backend
            await fetch('/api/psfalgo/addnewpos/filters', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(filtersToSave)
            })
            setFilterAutoSaveStatus('saved')
            setTimeout(() => setFilterAutoSaveStatus(null), 1500)
        } catch (e) {
            console.warn('Filter save failed:', e)
            setFilterAutoSaveStatus('error')
            setTimeout(() => setFilterAutoSaveStatus(null), 3000)
        }
    }, [])

    const scheduleFilterSave = useCallback((filtersToSave) => {
        if (filterSaveTimer.current) clearTimeout(filterSaveTimer.current)
        filterSaveTimer.current = setTimeout(() => doSaveFilters(filtersToSave), 500)
    }, [doSaveFilters])

    useEffect(() => {
        return () => { if (filterSaveTimer.current) clearTimeout(filterSaveTimer.current) }
    }, [])

    const handleFilterChange = (field, value) => {
        setFilters(prev => {
            const updated = { ...prev, [field]: value }
            scheduleFilterSave(updated)
            return updated
        })
    }



    const handleLoadFilters = useCallback(async () => {
        try {
            // Try backend first
            const response = await fetch('/api/psfalgo/addnewpos/filters')
            const result = await response.json()

            if (result.success && result.filters) {
                setFilters({ ...DEFAULT_FILTERS, ...result.filters })
            } else {
                // Fallback to localStorage
                const saved = localStorage.getItem(FILTER_STORAGE_KEY)
                if (saved) {
                    setFilters({ ...DEFAULT_FILTERS, ...JSON.parse(saved) })
                }
            }
        } catch (e) {
            // Fallback to localStorage
            const saved = localStorage.getItem(FILTER_STORAGE_KEY)
            if (saved) {
                setFilters({ ...DEFAULT_FILTERS, ...JSON.parse(saved) })
            }
        }
    }, [])

    const handleResetFilters = () => {
        setFilters(DEFAULT_FILTERS)
        doSaveFilters(DEFAULT_FILTERS)
    }

    // Apply filters to stocks - with tab-aware ucuzluk/pahalilik
    const applyFilters = useCallback((stocks, tabType = 'LONG') => {
        if (!stocks) return []

        return stocks.filter(stock => {
            // Fbtot filter
            if (filters.fbtot_min && stock.fbtot < parseFloat(filters.fbtot_min)) return false
            if (filters.fbtot_max && stock.fbtot > parseFloat(filters.fbtot_max)) return false

            // SFStot filter
            if (filters.sfstot_min && stock.sfstot < parseFloat(filters.sfstot_min)) return false
            if (filters.sfstot_max && stock.sfstot > parseFloat(filters.sfstot_max)) return false

            // GORT filter
            if (filters.gort_min && stock.gort < parseFloat(filters.gort_min)) return false
            if (filters.gort_max && stock.gort > parseFloat(filters.gort_max)) return false

            // SMA63 filter
            if (filters.sma63_min && stock.sma63_chg < parseFloat(filters.sma63_min)) return false
            if (filters.sma63_max && stock.sma63_chg > parseFloat(filters.sma63_max)) return false

            // SMA246 filter
            if (filters.sma246_min && stock.sma246_chg < parseFloat(filters.sma246_min)) return false
            if (filters.sma246_max && stock.sma246_chg > parseFloat(filters.sma246_max)) return false

            // Bid Buy Ucuzluk filter (for BB/FB Long tabs)
            if (tabType === 'LONG') {
                const ucuzluk = stock.bid_buy_ucuzluk ?? stock.ucuzluk_score ?? null
                if (ucuzluk !== null) {
                    if (filters.bid_buy_ucuzluk_min && ucuzluk < parseFloat(filters.bid_buy_ucuzluk_min)) return false
                    if (filters.bid_buy_ucuzluk_max && ucuzluk > parseFloat(filters.bid_buy_ucuzluk_max)) return false
                }
            }

            // Ask Sell Pahalilik filter (for SAS/SFS Short tabs)
            if (tabType === 'SHORT') {
                const pahalilik = stock.ask_sell_pahalilik ?? stock.pahalilik_score ?? null
                if (pahalilik !== null) {
                    if (filters.ask_sell_pahalilik_min && pahalilik < parseFloat(filters.ask_sell_pahalilik_min)) return false
                    if (filters.ask_sell_pahalilik_max && pahalilik > parseFloat(filters.ask_sell_pahalilik_max)) return false
                }
            }

            return true
        })
    }, [filters])

    // Memoize filtered stocks to prevent infinite loop on re-renders
    const filteredBB = React.useMemo(() => applyFilters(jfinState?.bb_stocks, 'LONG'), [jfinState?.bb_stocks, applyFilters])
    const filteredFB = React.useMemo(() => applyFilters(jfinState?.fb_stocks, 'LONG'), [jfinState?.fb_stocks, applyFilters])
    const filteredSAS = React.useMemo(() => applyFilters(jfinState?.sas_stocks, 'SHORT'), [jfinState?.sas_stocks, applyFilters])
    const filteredSFS = React.useMemo(() => applyFilters(jfinState?.sfs_stocks, 'SHORT'), [jfinState?.sfs_stocks, applyFilters])

    const subTabs = [
        { id: 'BB', label: 'BB (Bid Buy)', count: filteredBB?.length || 0 },
        { id: 'FB', label: 'FB (Front Buy)', count: filteredFB?.length || 0 },
        { id: 'SAS', label: 'SAS (Ask Sell)', count: filteredSAS?.length || 0 },
        { id: 'SFS', label: 'SFS (Front Sell)', count: filteredSFS?.length || 0 }
    ]

    // Check if any filter is active
    const hasActiveFilters = Object.values(filters).some(v => v !== '')

    return (
        <div className="addnewpos-proposals">
            <div className="addnewpos-header">
                <div className="header-left">
                    <h3>ADDNEWPOS - JFIN Transformer Intents</h3>
                </div>

                <div className="jfin-controls">
                    <button
                        className={`filter-toggle-btn ${showFilters ? 'active' : ''}`}
                        onClick={() => setShowFilters(!showFilters)}
                    >
                        🔍 Filters {hasActiveFilters && <span className="filter-active-badge">●</span>}
                    </button>
                    <div className="jfin-percentage-controls">
                        <label>JFIN %:</label>
                        <div className="jfin-percentage-buttons">
                            {[25, 50, 75, 100].map(pct => (
                                <button
                                    key={pct}
                                    className={`jfin-pct-btn ${percentage === pct ? 'active' : ''}`}
                                    onClick={() => handleUpdatePercentage(pct)}
                                    disabled={loading}
                                >
                                    {pct}%
                                </button>
                            ))}
                        </div>
                    </div>
                    <button className="jfin-refresh-btn" onClick={loadJFINState} disabled={loading}>
                        {loading ? '⏳' : '🔄'}
                    </button>
                </div>
            </div>

            {/* Filter Panel */}
            {showFilters && (
                <div className="addnewpos-filter-panel">
                    <div className="filter-panel-header">
                        <span>📊 Metric Filters</span>
                        <div className="filter-actions">
                            <button
                                className="filter-save-btn"
                                disabled
                                style={{ opacity: 0.7 }}
                            >
                                {filterAutoSaveStatus === 'saving' ? '⏳ Saving...' :
                                    filterAutoSaveStatus === 'saved' ? '✓ Saved' :
                                        filterAutoSaveStatus === 'error' ? '⚠️ Error' :
                                            '✓ Auto-save'}
                            </button>
                            <button
                                className="filter-load-btn"
                                onClick={handleLoadFilters}
                                title="Load saved filters"
                            >
                                📂 Load
                            </button>
                            <button
                                className="filter-reset-btn"
                                onClick={handleResetFilters}
                                title="Reset all filters"
                            >
                                🗑️ Reset
                            </button>
                        </div>
                    </div>

                    <div className="filter-grid">
                        {/* Fbtot Filter */}
                        <div className="filter-group">
                            <label className="filter-label">Fbtot</label>
                            <div className="filter-inputs">
                                <input
                                    type="number"
                                    placeholder="Min"
                                    value={filters.fbtot_min}
                                    onChange={e => handleFilterChange('fbtot_min', e.target.value)}
                                    step="0.01"
                                />
                                <span className="filter-separator">-</span>
                                <input
                                    type="number"
                                    placeholder="Max"
                                    value={filters.fbtot_max}
                                    onChange={e => handleFilterChange('fbtot_max', e.target.value)}
                                    step="0.01"
                                />
                            </div>
                        </div>

                        {/* SFStot Filter */}
                        <div className="filter-group">
                            <label className="filter-label">SFStot</label>
                            <div className="filter-inputs">
                                <input
                                    type="number"
                                    placeholder="Min"
                                    value={filters.sfstot_min}
                                    onChange={e => handleFilterChange('sfstot_min', e.target.value)}
                                    step="0.01"
                                />
                                <span className="filter-separator">-</span>
                                <input
                                    type="number"
                                    placeholder="Max"
                                    value={filters.sfstot_max}
                                    onChange={e => handleFilterChange('sfstot_max', e.target.value)}
                                    step="0.01"
                                />
                            </div>
                        </div>

                        {/* GORT Filter */}
                        <div className="filter-group">
                            <label className="filter-label">GORT</label>
                            <div className="filter-inputs">
                                <input
                                    type="number"
                                    placeholder="Min"
                                    value={filters.gort_min}
                                    onChange={e => handleFilterChange('gort_min', e.target.value)}
                                    step="0.01"
                                />
                                <span className="filter-separator">-</span>
                                <input
                                    type="number"
                                    placeholder="Max"
                                    value={filters.gort_max}
                                    onChange={e => handleFilterChange('gort_max', e.target.value)}
                                    step="0.01"
                                />
                            </div>
                        </div>

                        {/* SMA63 Filter */}
                        <div className="filter-group">
                            <label className="filter-label">SMA63 Chg</label>
                            <div className="filter-inputs">
                                <input
                                    type="number"
                                    placeholder="Min"
                                    value={filters.sma63_min}
                                    onChange={e => handleFilterChange('sma63_min', e.target.value)}
                                    step="0.01"
                                />
                                <span className="filter-separator">-</span>
                                <input
                                    type="number"
                                    placeholder="Max"
                                    value={filters.sma63_max}
                                    onChange={e => handleFilterChange('sma63_max', e.target.value)}
                                    step="0.01"
                                />
                            </div>
                        </div>

                        {/* SMA246 Filter */}
                        <div className="filter-group">
                            <label className="filter-label">SMA246 Chg</label>
                            <div className="filter-inputs">
                                <input
                                    type="number"
                                    placeholder="Min"
                                    value={filters.sma246_min}
                                    onChange={e => handleFilterChange('sma246_min', e.target.value)}
                                    step="0.01"
                                />
                                <span className="filter-separator">-</span>
                                <input
                                    type="number"
                                    placeholder="Max"
                                    value={filters.sma246_max}
                                    onChange={e => handleFilterChange('sma246_max', e.target.value)}
                                    step="0.01"
                                />
                            </div>
                        </div>

                        {/* Bid Buy Ucuzluk Filter (for BB/FB Long) */}
                        <div className="filter-group">
                            <label className="filter-label">Bid Buy Ucuzluk</label>
                            <div className="filter-inputs">
                                <input
                                    type="number"
                                    placeholder="Min"
                                    value={filters.bid_buy_ucuzluk_min}
                                    onChange={e => handleFilterChange('bid_buy_ucuzluk_min', e.target.value)}
                                    step="0.01"
                                />
                                <span className="filter-separator">-</span>
                                <input
                                    type="number"
                                    placeholder="Max"
                                    value={filters.bid_buy_ucuzluk_max}
                                    onChange={e => handleFilterChange('bid_buy_ucuzluk_max', e.target.value)}
                                    step="0.01"
                                />
                            </div>
                        </div>

                        {/* Ask Sell Pahalilik Filter (for SAS/SFS Short) */}
                        <div className="filter-group">
                            <label className="filter-label">Ask Sell Pahalilik</label>
                            <div className="filter-inputs">
                                <input
                                    type="number"
                                    placeholder="Min"
                                    value={filters.ask_sell_pahalilik_min}
                                    onChange={e => handleFilterChange('ask_sell_pahalilik_min', e.target.value)}
                                    step="0.01"
                                />
                                <span className="filter-separator">-</span>
                                <input
                                    type="number"
                                    placeholder="Max"
                                    value={filters.ask_sell_pahalilik_max}
                                    onChange={e => handleFilterChange('ask_sell_pahalilik_max', e.target.value)}
                                    step="0.01"
                                />
                            </div>
                        </div>
                    </div>

                    {hasActiveFilters && (
                        <div className="filter-summary">
                            Active filters: {Object.entries(filters)
                                .filter(([_, v]) => v !== '')
                                .map(([k, v]) => `${k.replace('_', ' ')}=${v}`)
                                .join(', ')
                            }
                        </div>
                    )}
                </div>
            )}

            {error && (
                <div className="addnewpos-error">
                    ⚠️ {error}
                </div>
            )}

            {/* Sub-Tabs for BB/FB/SAS/SFS */}
            <div className="jfin-sub-tabs">
                {subTabs.map(tab => (
                    <button
                        key={tab.id}
                        className={`jfin-sub-tab-btn ${activeSubTab === tab.id ? 'active' : ''}`}
                        onClick={() => setActiveSubTab(tab.id)}
                    >
                        {tab.label} <span className="count-badge">({tab.count})</span>
                    </button>
                ))}
            </div>

            {/* Exposure Panel - Per Tab - HORIZONTAL LAYOUT */}
            {jfinState && (
                <div className="jfin-exposure-info-panel horizontal">
                    {(() => {
                        // Get stocks for active tab
                        const stocks = activeFilteredStocks.length > 0 ? activeFilteredStocks : (
                            activeSubTab === 'BB' ? filteredBB :
                                activeSubTab === 'FB' ? filteredFB :
                                    activeSubTab === 'SAS' ? filteredSAS : filteredSFS
                        ) || [];

                        // Current & Max Exposure from REAL exposure endpoint
                        const currentExp = realExposure?.pot_total || 0;
                        const maxExp = jfinState.account_state?.limit_max_exposure || jfinState.account_state?.pot_max || 1200000;

                        // Calculate base total lots (without Est/Cur adjustment)
                        const baseTotalLots = stocks.reduce((sum, s) => {
                            const rawLot = s.addable_lot || s.calculated_lot || 0;
                            return sum + Math.floor(rawLot * (percentage / 100));
                        }, 0);

                        // Apply Est/Cur ratio adjustment to final lots
                        // For ADDNEWPOS: Keep stock count fixed, adjust lot sizes
                        const estValue = currentExp * (estCurRatio / 100);
                        const avgPrice = 20; // Default estimate
                        const baseEstCons = baseTotalLots * avgPrice;

                        // Calculate lot multiplier based on Est/Cur ratio
                        // If base Est/Cur is 28.8% and we want 50%, multiply lots by (50/28.8)
                        const baseEstToCur = currentExp > 0 ? (baseEstCons / currentExp * 100) : 0;
                        const lotMultiplier = baseEstToCur > 0 ? (estCurRatio / baseEstToCur) : 1;

                        // Apply multiplier to each stock's lot (min 200 lot rule)
                        const adjustedTotalLots = stocks.reduce((sum, s) => {
                            const rawLot = s.addable_lot || s.calculated_lot || 0;
                            const baseLot = Math.floor(rawLot * (percentage / 100));
                            const adjustedLot = Math.floor(baseLot * lotMultiplier);
                            // Apply min 200 lot rule: if adjusted lot < 200 and > 0, skip it
                            const finalLot = (adjustedLot < 200 && adjustedLot > 0) ? 0 : adjustedLot;
                            return sum + finalLot;
                        }, 0);

                        // Est. Consumption = Adjusted Total Lots × $20
                        const estCons = adjustedTotalLots * avgPrice;

                        // Ratios
                        const estToCur = currentExp > 0 ? (estCons / currentExp * 100) : 0;
                        const estToMax = maxExp > 0 ? (estCons / maxExp * 100) : 0;
                        const curToMax = maxExp > 0 ? (currentExp / maxExp * 100) : 0;

                        return (
                            <div className="exposure-horizontal-row">
                                <div className="exposure-item">
                                    <span className="exposure-icon">📦</span>
                                    <span className="exposure-label">Tot. Lots ({activeSubTab}):</span>
                                    <span className="exposure-value blue">{adjustedTotalLots.toLocaleString()}</span>
                                </div>
                                <span className="exp-sep">|</span>
                                <div className="exposure-item">
                                    <span className="exposure-icon">💰</span>
                                    <span className="exposure-label">Est. Cons:</span>
                                    <span className="exposure-value cyan">${estCons.toLocaleString()}</span>
                                </div>
                                <span className="exp-sep">|</span>
                                <div className="exposure-item">
                                    <span className="exposure-icon">📊</span>
                                    <span className="exposure-label">Cur Exp:</span>
                                    <span className="exposure-value green">${currentExp.toLocaleString()}</span>
                                </div>
                                <span className="exp-sep">|</span>
                                <div className="exposure-item">
                                    <span className="exposure-icon">🎯</span>
                                    <span className="exposure-label">Max Exp:</span>
                                    <span className="exposure-value orange">${maxExp.toLocaleString()}</span>
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
                                    <span className="ratio-item" title="Est/Current">
                                        Est/Cur: <span className={`ratio-value ${estToCur > 25 ? 'warning' : ''}`}>{estToCur.toFixed(1)}%</span>
                                    </span>
                                    <span className="ratio-item" title="Est/Max">
                                        Est/Max: <span className={`ratio-value ${estToMax > 15 ? 'warning' : ''}`}>{estToMax.toFixed(1)}%</span>
                                    </span>
                                    <span className="ratio-item" title="Cur/Max">
                                        Cur/Max: <span className={`ratio-value ${curToMax > 90 ? 'warning' : ''}`}>{curToMax.toFixed(1)}%</span>
                                    </span>
                                </div>
                            </div>
                        );
                    })()}
                </div>
            )}

            {/* Sub-Tab Content */}
            <div className="jfin-sub-tab-content">
                {loading && !jfinState ? (
                    <div className="jfin-loading">Loading JFIN state...</div>
                ) : error && error.includes('empty') ? (
                    <div className="jfin-empty-state">
                        <div className="jfin-empty-icon">📊</div>
                        <div className="jfin-empty-title">JFIN State Empty</div>
                        <div className="jfin-empty-message">{error}</div>
                        <div className="jfin-empty-instructions">
                            <p><strong>To populate JFIN data:</strong></p>
                            <ol>
                                <li>Start RUNALL engine</li>
                                <li>ADDNEWPOS cycle will run JFIN transformer</li>
                                <li>JFIN intents will populate here</li>
                            </ol>
                        </div>
                    </div>
                ) : (
                    <>
                        <>
                            {activeSubTab === 'BB' && (
                                <JFINTabBB
                                    stocks={filteredBB || []}
                                    onFilteredDataChange={setActiveFilteredStocks}
                                />
                            )}
                            {activeSubTab === 'FB' && (
                                <JFINTabFB
                                    stocks={filteredFB || []}
                                    onFilteredDataChange={setActiveFilteredStocks}
                                />
                            )}
                            {activeSubTab === 'SAS' && (
                                <JFINTabSAS
                                    stocks={filteredSAS || []}
                                    onFilteredDataChange={setActiveFilteredStocks}
                                />
                            )}
                            {activeSubTab === 'SFS' && (
                                <JFINTabSFS
                                    stocks={filteredSFS || []}
                                    onFilteredDataChange={setActiveFilteredStocks}
                                />
                            )}
                        </>
                    </>
                )}
            </div>

            {/* Order Confirmation Modal */}
            <OrderConfirmModal
                isOpen={showConfirmModal}
                onClose={() => { setShowConfirmModal(false); setPendingOrders([]) }}
                onConfirm={handleConfirmOrders}
                orders={pendingOrders}
                poolType={activeSubTab}
                percentage={pendingPercentage}
                loading={confirmLoading}
            />
        </div>
    )
}

export default AddNewPosProposals

