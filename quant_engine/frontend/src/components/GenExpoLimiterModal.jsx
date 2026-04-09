import React, { useState, useEffect, useCallback, useRef } from 'react'
import './GenExpoLimiterModal.css'

// Default per-tab settings for ADDNEWPOS
const defaultTabSettings = {
    jfin_pct: 50,
    gort_min: null,
    gort_max: null,
    tot_threshold: null,
    tot_direction: 'above',
    sma63chg_threshold: null,
    sma63chg_direction: 'below'
}

function normalizeTabFromApi(tab) {
    if (!tab || typeof tab !== 'object') return { ...defaultTabSettings }
    const pct = tab.jfin_pct
    const jfinPct = pct === 0 || pct === '0' ? 0 : [25, 50, 75, 100].includes(Number(pct)) ? Number(pct) : defaultTabSettings.jfin_pct
    return {
        ...defaultTabSettings,
        ...tab,
        jfin_pct: jfinPct,
        gort_min: tab.gort_min != null && tab.gort_min !== '' ? Number(tab.gort_min) : null,
        gort_max: tab.gort_max != null && tab.gort_max !== '' ? Number(tab.gort_max) : null,
        tot_threshold: tab.tot_threshold != null && tab.tot_threshold !== '' ? Number(tab.tot_threshold) : null,
        sma63chg_threshold: tab.sma63chg_threshold != null && tab.sma63chg_threshold !== '' ? Number(tab.sma63chg_threshold) : null
    }
}

function GenExpoLimiterModal({ isOpen, onClose }) {
    // ═══════════════════════════════════════════════════════════════════════════
    // STATE
    // ═══════════════════════════════════════════════════════════════════════════

    // Current account (from trading context)
    const [accountId, setAccountId] = useState('IBKR_PED')
    const [accountOptions] = useState(['IBKR_PED', 'HAMPRO', 'IBKR_GUN'])

    // Exposure Thresholds
    const [exposureSettings, setExposureSettings] = useState({
        max_cur_exp_pct: 92.0,
        max_pot_exp_pct: 100.0
    })

    // Current exposure status
    const [exposureStatus, setExposureStatus] = useState({
        current_exposure_pct: 0,
        potential_exposure_pct: 0,
        hard_risk: false
    })

    // ADDNEWPOS Global Settings
    const [globalSettings, setGlobalSettings] = useState({
        enabled: true,
        mode: 'both',
        long_ratio: 50.0,
        short_ratio: 50.0,
        active_tab: 'BB'
    })

    // ADDNEWPOS Per-Tab Settings
    const [tabSettings, setTabSettings] = useState({
        BB: { ...defaultTabSettings },
        FB: { ...defaultTabSettings },
        SAS: { ...defaultTabSettings },
        SFS: { ...defaultTabSettings }
    })

    // UI State
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [autoSaveStatus, setAutoSaveStatus] = useState(null) // 'saving' | 'saved' | 'error'
    const [activeSection, setActiveSection] = useState('exposure') // 'exposure' | 'addnewpos'
    const autoSaveTimer = useRef(null)

    // ADDNEWPOS active tab
    const activeTab = globalSettings.active_tab
    const currentTabSettings = tabSettings[activeTab] || defaultTabSettings
    const isShortPool = activeTab === 'SAS' || activeTab === 'SFS'
    const totLabel = isShortPool ? 'SFStot' : 'FBtot'

    // ═══════════════════════════════════════════════════════════════════════════
    // DATA FETCHING
    // ═══════════════════════════════════════════════════════════════════════════

    // Fetch current trading mode
    const fetchCurrentAccount = useCallback(async () => {
        try {
            const response = await fetch('/api/trading/mode')
            const result = await response.json()
            if (result.success && result.trading_mode) {
                // Map HAMMER_PRO to HAMPRO
                let mode = result.trading_mode
                if (mode === 'HAMMER_PRO') mode = 'HAMPRO'
                setAccountId(mode)
            }
        } catch (err) {
            console.error('Error fetching trading mode:', err)
        }
    }, [])

    // Fetch exposure thresholds for account
    const fetchExposureSettings = useCallback(async (account) => {
        try {
            const response = await fetch(`/api/psfalgo/exposure-limits?account_id=${account}`)
            const result = await response.json()
            if (result.success) {
                setExposureSettings({
                    max_cur_exp_pct: result.max_cur_exp_pct ?? 92.0,
                    max_pot_exp_pct: result.max_pot_exp_pct ?? 100.0
                })
            }
        } catch (err) {
            console.error('Error fetching exposure settings:', err)
        }
    }, [])

    // Fetch hard risk status
    const fetchHardRiskStatus = useCallback(async (account) => {
        try {
            const response = await fetch(`/api/psfalgo/hard-risk-status?account_id=${account}`)
            const result = await response.json()
            if (result.success) {
                setExposureStatus({
                    current_exposure_pct: result.current_exposure_pct ?? 0,
                    potential_exposure_pct: result.potential_exposure_pct ?? 0,
                    hard_risk: result.hard_risk ?? false
                })
            }
        } catch (err) {
            console.error('Error fetching hard risk status:', err)
        }
    }, [])

    // Fetch ADDNEWPOS settings for account
    const fetchAddnewposSettings = useCallback(async (account) => {
        try {
            const response = await fetch(`/api/xnl/addnewpos/settings?account_id=${account}`)
            const result = await response.json()
            if (result.success && result.settings) {
                const s = result.settings
                setGlobalSettings({
                    enabled: s.enabled ?? true,
                    mode: s.mode ?? 'both',
                    long_ratio: Number(s.long_ratio) || 50.0,
                    short_ratio: Number(s.short_ratio) || 50.0,
                    active_tab: s.active_tab ?? 'BB'
                })
                setTabSettings({
                    BB: normalizeTabFromApi(s.tab_bb),
                    FB: normalizeTabFromApi(s.tab_fb),
                    SAS: normalizeTabFromApi(s.tab_sas),
                    SFS: normalizeTabFromApi(s.tab_sfs)
                })
            }
        } catch (err) {
            console.error('Error fetching ADDNEWPOS settings:', err)
        }
    }, [])

    // Load all data for current account
    const loadAllData = useCallback(async (account) => {
        setLoading(true)
        setError(null)
        try {
            await Promise.all([
                fetchExposureSettings(account),
                fetchHardRiskStatus(account),
                fetchAddnewposSettings(account)
            ])
        } catch (err) {
            setError('Failed to load settings')
        } finally {
            setLoading(false)
        }
    }, [fetchExposureSettings, fetchHardRiskStatus, fetchAddnewposSettings])

    // Initial load
    useEffect(() => {
        if (isOpen) {
            fetchCurrentAccount().then(() => {
                // accountId will be set by fetchCurrentAccount, but we need to wait
            })
        }
    }, [isOpen, fetchCurrentAccount])

    // Load data when account changes
    useEffect(() => {
        if (isOpen && accountId) {
            loadAllData(accountId)
        }
    }, [isOpen, accountId, loadAllData])

    // ═══════════════════════════════════════════════════════════════════════════
    // HANDLERS
    // ═══════════════════════════════════════════════════════════════════════════

    // Account change
    const handleAccountChange = (newAccount) => {
        setAccountId(newAccount)
        // Data will be loaded by useEffect
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // AUTO-SAVE
    // ═══════════════════════════════════════════════════════════════════════════

    const doAutoSave = useCallback(async (expSettings, gSettings, tSettings, accId) => {
        try {
            setAutoSaveStatus('saving')

            // 1. Save exposure thresholds
            const expResponse = await fetch('/api/psfalgo/exposure-limits', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    account_id: accId,
                    max_cur_exp_pct: expSettings.max_cur_exp_pct,
                    max_pot_exp_pct: expSettings.max_pot_exp_pct
                })
            })
            const expResult = await expResponse.json()
            if (!expResult.success) throw new Error('Exposure save failed')

            // 2. Save ADDNEWPOS settings
            const addnewposPayload = {
                account_id: accId,
                enabled: gSettings.enabled,
                mode: gSettings.mode,
                long_ratio: gSettings.long_ratio,
                short_ratio: gSettings.short_ratio,
                active_tab: gSettings.active_tab,
                tab_bb: tSettings.BB,
                tab_fb: tSettings.FB,
                tab_sas: tSettings.SAS,
                tab_sfs: tSettings.SFS
            }
            const addnewposResponse = await fetch('/api/xnl/addnewpos/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(addnewposPayload)
            })
            const addnewposResult = await addnewposResponse.json()
            if (!addnewposResult.success) throw new Error('ADDNEWPOS save failed')

            setAutoSaveStatus('saved')
            setTimeout(() => setAutoSaveStatus(null), 1500)

            // Refresh hard risk status
            await fetchHardRiskStatus(accId)
        } catch (err) {
            console.error('Auto-save error:', err)
            setAutoSaveStatus('error')
            setTimeout(() => setAutoSaveStatus(null), 3000)
        }
    }, [fetchHardRiskStatus])

    const scheduleAutoSave = useCallback((expSettings, gSettings, tSettings, accId) => {
        if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
        autoSaveTimer.current = setTimeout(() => doAutoSave(expSettings, gSettings, tSettings, accId), 800)
    }, [doAutoSave])

    // Cleanup timer
    useEffect(() => {
        return () => { if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current) }
    }, [])

    // Update exposure setting + auto-save
    const updateExposure = (key, value) => {
        setExposureSettings(prev => {
            const updated = { ...prev, [key]: value }
            scheduleAutoSave(updated, globalSettings, tabSettings, accountId)
            return updated
        })
    }

    // Update ADDNEWPOS global setting + auto-save
    const updateGlobal = (key, value) => {
        setGlobalSettings(prev => {
            const updated = { ...prev, [key]: value }
            scheduleAutoSave(exposureSettings, updated, tabSettings, accountId)
            return updated
        })
    }

    // Update current ADDNEWPOS tab setting + auto-save
    const updateTab = (key, value) => {
        setTabSettings(prev => {
            const updated = {
                ...prev,
                [activeTab]: {
                    ...prev[activeTab],
                    [key]: value
                }
            }
            scheduleAutoSave(exposureSettings, globalSettings, updated, accountId)
            return updated
        })
    }

    // Handle ratio change
    const handleLongRatioChange = (value) => {
        const longRatio = Math.min(100, Math.max(0, parseFloat(value) || 0))
        const shortRatio = 100 - longRatio
        setGlobalSettings(prev => ({ ...prev, long_ratio: longRatio, short_ratio: shortRatio }))
    }

    // Change active tab + auto-save
    const changeTab = (tab) => {
        setGlobalSettings(prev => {
            const updated = { ...prev, active_tab: tab }
            scheduleAutoSave(exposureSettings, updated, tabSettings, accountId)
            return updated
        })
    }

    // Clear filters for current tab + auto-save
    const clearCurrentTabFilters = () => {
        setTabSettings(prev => {
            const updated = {
                ...prev,
                [activeTab]: {
                    ...prev[activeTab],
                    gort_min: null,
                    gort_max: null,
                    tot_threshold: null,
                    sma63chg_threshold: null
                }
            }
            scheduleAutoSave(exposureSettings, globalSettings, updated, accountId)
            return updated
        })
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // RENDER
    // ═══════════════════════════════════════════════════════════════════════════

    if (!isOpen) return null

    return (
        <div className="genexpo-modal-overlay" onClick={onClose}>
            <div className="genexpo-modal" onClick={(e) => e.stopPropagation()}>
                {/* Header */}
                <div className="genexpo-header">
                    <div className="genexpo-title">
                        <span className="genexpo-icon">🎚️</span>
                        <h2>GenExpo Limiter</h2>
                        <span className="genexpo-subtitle">Account-Aware Exposure & ADDNEWPOS Settings</span>
                    </div>
                    <button className="genexpo-close-btn" onClick={onClose}>✕</button>
                </div>

                {/* Account Selector */}
                <div className="genexpo-account-bar">
                    <span className="account-label">Active Account:</span>
                    <div className="account-buttons">
                        {accountOptions.map(acc => (
                            <button
                                key={acc}
                                className={`account-btn ${accountId === acc ? 'active' : ''}`}
                                onClick={() => handleAccountChange(acc)}
                            >
                                {acc === 'IBKR_PED' ? '📊 IBKR PED' :
                                    acc === 'HAMPRO' ? '🔨 Hammer' :
                                        '🔥 IBKR GUN'}
                            </button>
                        ))}
                    </div>

                    {/* Status indicators */}
                    <div className="status-indicators">
                        <span className={`status-badge ${exposureStatus.hard_risk ? 'danger' : 'safe'}`}>
                            {exposureStatus.hard_risk ? '🔴 HARD RISK' : '🟢 Normal'}
                        </span>
                        <span className="exposure-badge">
                            Cur: {exposureStatus.current_exposure_pct.toFixed(1)}% |
                            Pot: {exposureStatus.potential_exposure_pct.toFixed(1)}%
                        </span>
                    </div>
                </div>

                {/* Section Tabs */}
                <div className="genexpo-section-tabs">
                    <button
                        className={`section-tab ${activeSection === 'exposure' ? 'active' : ''}`}
                        onClick={() => setActiveSection('exposure')}
                    >
                        📊 Exposure Limits
                    </button>
                    <button
                        className={`section-tab ${activeSection === 'addnewpos' ? 'active' : ''}`}
                        onClick={() => setActiveSection('addnewpos')}
                    >
                        ➕ ADDNEWPOS Filters
                    </button>
                </div>

                {/* Content */}
                <div className="genexpo-content">
                    {loading ? (
                        <div className="genexpo-loading">Loading settings for {accountId}...</div>
                    ) : (
                        <>
                            {/* EXPOSURE SECTION */}
                            {activeSection === 'exposure' && (
                                <div className="section-content exposure-section">
                                    <div className="exposure-grid">
                                        {/* Max Current Exposure */}
                                        <div className="exposure-card">
                                            <label>Max Current Exposure %</label>
                                            <div className="exposure-input-group">
                                                <input
                                                    type="number"
                                                    value={exposureSettings.max_cur_exp_pct}
                                                    onChange={(e) => updateExposure('max_cur_exp_pct', parseFloat(e.target.value) || 0)}
                                                    min="0"
                                                    max="150"
                                                    step="1"
                                                />
                                                <span className="unit">%</span>
                                            </div>
                                            <div className="exposure-bar">
                                                <div
                                                    className="exposure-fill current"
                                                    style={{ width: `${Math.min(100, exposureStatus.current_exposure_pct)}%` }}
                                                />
                                                <div
                                                    className="exposure-limit-marker"
                                                    style={{ left: `${Math.min(100, exposureSettings.max_cur_exp_pct)}%` }}
                                                />
                                            </div>
                                            <span className="exposure-current-value">
                                                Current: {exposureStatus.current_exposure_pct.toFixed(1)}%
                                            </span>
                                        </div>

                                        {/* Max Potential Exposure */}
                                        <div className="exposure-card">
                                            <label>Max Potential Exposure %</label>
                                            <div className="exposure-input-group">
                                                <input
                                                    type="number"
                                                    value={exposureSettings.max_pot_exp_pct}
                                                    onChange={(e) => updateExposure('max_pot_exp_pct', parseFloat(e.target.value) || 0)}
                                                    min="0"
                                                    max="150"
                                                    step="1"
                                                />
                                                <span className="unit">%</span>
                                            </div>
                                            <div className="exposure-bar">
                                                <div
                                                    className="exposure-fill potential"
                                                    style={{ width: `${Math.min(100, exposureStatus.potential_exposure_pct)}%` }}
                                                />
                                                <div
                                                    className="exposure-limit-marker"
                                                    style={{ left: `${Math.min(100, exposureSettings.max_pot_exp_pct)}%` }}
                                                />
                                            </div>
                                            <span className="exposure-current-value">
                                                Potential: {exposureStatus.potential_exposure_pct.toFixed(1)}%
                                            </span>
                                        </div>
                                    </div>

                                    {/* Quick Presets */}
                                    <div className="exposure-presets">
                                        <span className="presets-label">Quick Presets:</span>
                                        <button onClick={() => { const u = { ...exposureSettings, max_cur_exp_pct: 85, max_pot_exp_pct: 95 }; setExposureSettings(u); scheduleAutoSave(u, globalSettings, tabSettings, accountId); }}>
                                            Conservative (85/95)
                                        </button>
                                        <button onClick={() => { const u = { ...exposureSettings, max_cur_exp_pct: 92, max_pot_exp_pct: 100 }; setExposureSettings(u); scheduleAutoSave(u, globalSettings, tabSettings, accountId); }}>
                                            Standard (92/100)
                                        </button>
                                        <button onClick={() => { const u = { ...exposureSettings, max_cur_exp_pct: 100, max_pot_exp_pct: 110 }; setExposureSettings(u); scheduleAutoSave(u, globalSettings, tabSettings, accountId); }}>
                                            Aggressive (100/110)
                                        </button>
                                    </div>

                                    {/* Hard Risk Explanation */}
                                    <div className="hard-risk-info">
                                        <strong>⚠️ Hard Risk Mode:</strong> When current ≥ max_cur OR potential ≥ max_pot,
                                        ADDNEWPOS/MM increase orders are blocked. Only position reductions allowed.
                                    </div>
                                </div>
                            )}

                            {/* ADDNEWPOS SECTION */}
                            {activeSection === 'addnewpos' && (
                                <div className="section-content addnewpos-section">
                                    {/* Global Settings Row */}
                                    <div className="addnewpos-global-row">
                                        <div className="global-label">GLOBAL:</div>

                                        {/* Mode */}
                                        <div className="setting-group mode-group">
                                            <label>Mode:</label>
                                            <div className="radio-group">
                                                <label className={globalSettings.mode === 'both' ? 'active' : ''}>
                                                    <input type="radio" value="both" checked={globalSettings.mode === 'both'}
                                                        onChange={(e) => updateGlobal('mode', e.target.value)} />
                                                    Both
                                                </label>
                                                <label className={globalSettings.mode === 'addlong_only' ? 'active' : ''}>
                                                    <input type="radio" value="addlong_only" checked={globalSettings.mode === 'addlong_only'}
                                                        onChange={(e) => updateGlobal('mode', e.target.value)} />
                                                    Long Only
                                                </label>
                                                <label className={globalSettings.mode === 'addshort_only' ? 'active' : ''}>
                                                    <input type="radio" value="addshort_only" checked={globalSettings.mode === 'addshort_only'}
                                                        onChange={(e) => updateGlobal('mode', e.target.value)} />
                                                    Short Only
                                                </label>
                                            </div>
                                        </div>

                                        {/* Enabled */}
                                        <div className="setting-group enabled-group">
                                            <label>
                                                <input type="checkbox" checked={globalSettings.enabled}
                                                    onChange={(e) => updateGlobal('enabled', e.target.checked)} />
                                                ENABLED
                                            </label>
                                        </div>

                                        <div className="v-divider" />

                                        {/* Long/Short Ratio */}
                                        <div className="setting-group ratio-group">
                                            <label>L/S Ratio:</label>
                                            <span className="ratio-label long">{globalSettings.long_ratio.toFixed(0)}%</span>
                                            <input type="range" min="0" max="100" value={globalSettings.long_ratio}
                                                onChange={(e) => handleLongRatioChange(e.target.value)} className="ratio-slider" />
                                            <span className="ratio-label short">{globalSettings.short_ratio.toFixed(0)}%</span>
                                        </div>
                                    </div>

                                    {/* Tab Selection */}
                                    <div className="addnewpos-tab-row">
                                        <span className="tab-section-label">Pool:</span>
                                        <div className="tab-buttons">
                                            <button className={`tab-btn bb ${activeTab === 'BB' ? 'active' : ''}`} onClick={() => changeTab('BB')}>BB</button>
                                            <button className={`tab-btn fb ${activeTab === 'FB' ? 'active' : ''}`} onClick={() => changeTab('FB')}>FB</button>
                                            <button className={`tab-btn sas ${activeTab === 'SAS' ? 'active' : ''}`} onClick={() => changeTab('SAS')}>SAS</button>
                                            <button className={`tab-btn sfs ${activeTab === 'SFS' ? 'active' : ''}`} onClick={() => changeTab('SFS')}>SFS</button>
                                        </div>
                                    </div>

                                    {/* Per-Tab Settings */}
                                    <div className="addnewpos-filter-row">
                                        <div className="tab-label">{activeTab}:</div>

                                        {/* JFIN */}
                                        <div className="setting-group jfin-group">
                                            <label>JFIN:</label>
                                            <div className="jfin-buttons">
                                                {[0, 25, 50, 75, 100].map(pct => (
                                                    <button key={pct} className={currentTabSettings.jfin_pct === pct ? 'active' : ''}
                                                        onClick={() => updateTab('jfin_pct', pct)}>
                                                        {pct}%
                                                    </button>
                                                ))}
                                            </div>
                                        </div>

                                        <div className="v-divider" />

                                        {/* GORT Range */}
                                        <div className="setting-group filter-inline">
                                            <label>GORT:</label>
                                            <input type="number" placeholder="Min" value={currentTabSettings.gort_min ?? ''}
                                                onChange={(e) => updateTab('gort_min', e.target.value ? parseFloat(e.target.value) : null)} step="0.01" />
                                            <span>—</span>
                                            <input type="number" placeholder="Max" value={currentTabSettings.gort_max ?? ''}
                                                onChange={(e) => updateTab('gort_max', e.target.value ? parseFloat(e.target.value) : null)} step="0.01" />
                                        </div>

                                        {/* Tot Filter */}
                                        <div className="setting-group filter-inline">
                                            <label>{totLabel}:</label>
                                            <input type="number" placeholder="Val" value={currentTabSettings.tot_threshold ?? ''}
                                                onChange={(e) => updateTab('tot_threshold', e.target.value ? parseFloat(e.target.value) : null)} step="0.01" />
                                            <div className="mini-radio">
                                                <label className={currentTabSettings.tot_direction === 'below' ? 'active' : ''}>
                                                    <input type="radio" value="below" checked={currentTabSettings.tot_direction === 'below'}
                                                        onChange={() => updateTab('tot_direction', 'below')} /> &lt;
                                                </label>
                                                <label className={currentTabSettings.tot_direction === 'above' ? 'active' : ''}>
                                                    <input type="radio" value="above" checked={currentTabSettings.tot_direction === 'above'}
                                                        onChange={() => updateTab('tot_direction', 'above')} /> &gt;
                                                </label>
                                            </div>
                                        </div>

                                        {/* SMA63 */}
                                        <div className="setting-group filter-inline">
                                            <label>SMA63:</label>
                                            <input type="number" placeholder="Val" value={currentTabSettings.sma63chg_threshold ?? ''}
                                                onChange={(e) => updateTab('sma63chg_threshold', e.target.value ? parseFloat(e.target.value) : null)} step="0.01" />
                                            <div className="mini-radio">
                                                <label className={currentTabSettings.sma63chg_direction === 'below' ? 'active' : ''}>
                                                    <input type="radio" value="below" checked={currentTabSettings.sma63chg_direction === 'below'}
                                                        onChange={() => updateTab('sma63chg_direction', 'below')} /> &lt;
                                                </label>
                                                <label className={currentTabSettings.sma63chg_direction === 'above' ? 'active' : ''}>
                                                    <input type="radio" value="above" checked={currentTabSettings.sma63chg_direction === 'above'}
                                                        onChange={() => updateTab('sma63chg_direction', 'above')} /> &gt;
                                                </label>
                                            </div>
                                        </div>

                                        <button className="clear-filters-btn" onClick={clearCurrentTabFilters} title={`Clear ${activeTab} filters`}>
                                            ✕ Clear
                                        </button>
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </div>

                {/* Footer */}
                <div className="genexpo-footer">
                    {error && <span className="error-msg">⚠️ {error}</span>}
                    {autoSaveStatus === 'saving' && <span className="autosave-indicator saving">⏳ Saving...</span>}
                    {autoSaveStatus === 'saved' && <span className="autosave-indicator saved">✓ Saved</span>}
                    {autoSaveStatus === 'error' && <span className="autosave-indicator error">⚠️ Save failed</span>}

                    <div className="footer-actions">
                        <button className="cancel-btn" onClick={onClose}>Close</button>
                    </div>
                </div>
            </div>
        </div>
    )
}

export default GenExpoLimiterModal
