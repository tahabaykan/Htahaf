import React, { useState, useEffect, useCallback, useRef } from 'react'
import './AddnewposSettingsPanel.css'

// Default per-tab settings (used for Reset to Default)
const defaultTabSettings = {
  jfin_pct: 50,
  gort_min: null,
  gort_max: null,
  tot_threshold: null,
  tot_direction: 'above',
  sma63chg_threshold: null,
  sma63chg_direction: 'below'
}

const defaultGlobalSettings = {
  enabled: true,
  mode: 'both',
  long_ratio: 50.0,
  short_ratio: 50.0,
  active_tab: 'BB'
}

// Normalize tab object from API: merge with defaults and coerce jfin_pct to number (0,25,50,75,100)
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

function AddnewposSettingsPanel() {
  // Global settings (shared across all tabs)
  const [globalSettings, setGlobalSettings] = useState({ ...defaultGlobalSettings })

  // Per-tab settings
  const [tabSettings, setTabSettings] = useState({
    BB: { ...defaultTabSettings },
    FB: { ...defaultTabSettings },
    SAS: { ...defaultTabSettings },
    SFS: { ...defaultTabSettings }
  })

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [autoSaveStatus, setAutoSaveStatus] = useState(null) // 'saving', 'saved', 'error'
  const [collapsed, setCollapsed] = useState(false)
  const [csvFilename, setCsvFilename] = useState('')
  const [lastCsv, setLastCsv] = useState(null)
  const [csvSaving, setCsvSaving] = useState(false)
  const [csvLoading, setCsvLoading] = useState(false)
  const [accountId, setAccountId] = useState('HAMPRO')  // Current account

  // Auto-save debounce ref
  const autoSaveTimer = useRef(null)
  const pendingSave = useRef(false)

  // Current tab
  const activeTab = globalSettings.active_tab
  const currentTabSettings = tabSettings[activeTab] || defaultTabSettings

  // Is current tab a short pool?
  const isShortPool = activeTab === 'SAS' || activeTab === 'SFS'
  const totLabel = isShortPool ? 'SFStot' : 'FBtot'

  // ═══════════════════════════════════════════════════════════════
  // AUTO-SAVE: debounced save to backend on every change
  // ═══════════════════════════════════════════════════════════════
  const doAutoSave = useCallback(async (gSettings, tSettings, accId) => {
    try {
      setAutoSaveStatus('saving')
      const payload = {
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

      const response = await fetch('/api/xnl/addnewpos/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })

      const result = await response.json()
      if (result.success) {
        setAutoSaveStatus('saved')
        setTimeout(() => setAutoSaveStatus(null), 1500)
      } else {
        setAutoSaveStatus('error')
        setTimeout(() => setAutoSaveStatus(null), 3000)
      }
    } catch (err) {
      console.error('Auto-save failed:', err)
      setAutoSaveStatus('error')
      setTimeout(() => setAutoSaveStatus(null), 3000)
    }
  }, [])

  // Schedule auto-save (debounced 600ms)
  const scheduleAutoSave = useCallback((gSettings, tSettings, accId) => {
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
    pendingSave.current = true
    autoSaveTimer.current = setTimeout(() => {
      pendingSave.current = false
      doAutoSave(gSettings, tSettings, accId)
    }, 600)
  }, [doAutoSave])

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
    }
  }, [])

  // ═══════════════════════════════════════════════════════════════
  // FETCH SETTINGS (account-specific)
  // ═══════════════════════════════════════════════════════════════
  const fetchSettings = useCallback(async (accId) => {
    setError(null)
    try {
      const url = accId
        ? `/api/xnl/addnewpos/settings?account_id=${accId}`
        : '/api/xnl/addnewpos/settings'
      const response = await fetch(url)
      const result = await response.json()

      if (!response.ok) {
        setError(result.detail || result.message || 'Failed to load settings')
        return
      }
      if (result.success && result.settings) {
        const s = result.settings
        if (result.account_id) setAccountId(result.account_id)
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
      } else {
        setError(result.message || 'Settings format invalid')
      }
    } catch (err) {
      console.error('Error fetching ADDNEWPOS settings:', err)
      setError('Failed to load settings – ' + (err.message || 'network error'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchSettings(accountId)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const fetchLastCsv = useCallback(async () => {
    try {
      const r = await fetch('/api/xnl/addnewpos/settings/last-csv')
      const j = await r.json()
      if (j.success && j.filename) setLastCsv(j.filename)
      else setLastCsv(null)
    } catch (_) { setLastCsv(null) }
  }, [])

  useEffect(() => {
    if (!loading) fetchLastCsv()
  }, [loading, fetchLastCsv])

  // ═══════════════════════════════════════════════════════════════
  // ACCOUNT SWITCH
  // ═══════════════════════════════════════════════════════════════
  const switchAccount = (newAccId) => {
    setAccountId(newAccId)
    setLoading(true)
    fetchSettings(newAccId)
  }

  // ═══════════════════════════════════════════════════════════════
  // UPDATE HELPERS (auto-save on every change)
  // ═══════════════════════════════════════════════════════════════

  // Update global setting + auto-save
  const updateGlobal = (key, value) => {
    setGlobalSettings(prev => {
      const updated = { ...prev, [key]: value }
      scheduleAutoSave(updated, tabSettings, accountId)
      return updated
    })
  }

  // Update current tab setting + auto-save
  const updateTab = (key, value) => {
    setTabSettings(prev => {
      const updated = {
        ...prev,
        [activeTab]: {
          ...prev[activeTab],
          [key]: value
        }
      }
      scheduleAutoSave(globalSettings, updated, accountId)
      return updated
    })
  }

  // Handle ratio change + auto-save
  const handleLongRatioChange = (value) => {
    const longRatio = Math.min(100, Math.max(0, parseFloat(value) || 0))
    const shortRatio = 100 - longRatio
    setGlobalSettings(prev => {
      const updated = { ...prev, long_ratio: longRatio, short_ratio: shortRatio }
      scheduleAutoSave(updated, tabSettings, accountId)
      return updated
    })
  }

  // Change active tab + auto-save
  const changeTab = (tab) => {
    setGlobalSettings(prev => {
      const updated = { ...prev, active_tab: tab }
      scheduleAutoSave(updated, tabSettings, accountId)
      return updated
    })
  }

  // ═══════════════════════════════════════════════════════════════
  // RESET TO DEFAULT
  // ═══════════════════════════════════════════════════════════════
  const handleResetToDefault = () => {
    const newGlobal = { ...defaultGlobalSettings }
    const newTabs = {
      BB: { ...defaultTabSettings },
      FB: { ...defaultTabSettings },
      SAS: { ...defaultTabSettings },
      SFS: { ...defaultTabSettings }
    }
    setGlobalSettings(newGlobal)
    setTabSettings(newTabs)
    // Auto-save defaults immediately
    doAutoSave(newGlobal, newTabs, accountId)
  }

  // ═══════════════════════════════════════════════════════════════
  // CSV Save/Load (unchanged)
  // ═══════════════════════════════════════════════════════════════
  const handleSaveCsv = async () => {
    const name = (csvFilename || 'addnewpos').trim()
    if (!name) return
    setCsvSaving(true)
    setError(null)
    try {
      // Force save current state first
      await doAutoSave(globalSettings, tabSettings, accountId)

      // Now save to CSV
      const res = await fetch('/api/xnl/addnewpos/settings/save-csv', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: name })
      })
      const result = await res.json()
      if (!res.ok || !result.success) throw new Error(result.detail || 'Save CSV failed')
      setLastCsv(result.filename || name + (name.endsWith('.csv') ? '' : '.csv'))
      setAutoSaveStatus('saved')
      setTimeout(() => setAutoSaveStatus(null), 2000)
    } catch (err) {
      setError(err.message || 'Save CSV failed')
    } finally {
      setCsvSaving(false)
    }
  }

  const handleLoadCsv = async (file) => {
    if (!file) return
    setCsvLoading(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('upload_file', file)
      const res = await fetch('/api/xnl/addnewpos/settings/load-csv', { method: 'POST', body: form })
      const result = await res.json()
      if (!res.ok || !result.success) throw new Error(result.detail || 'Load CSV failed')
      if (result.settings) {
        const s = result.settings
        const newGlobal = { enabled: s.enabled ?? true, mode: s.mode ?? 'both', long_ratio: Number(s.long_ratio) || 50, short_ratio: Number(s.short_ratio) || 50, active_tab: s.active_tab ?? 'BB' }
        const newTabs = { BB: normalizeTabFromApi(s.tab_bb), FB: normalizeTabFromApi(s.tab_fb), SAS: normalizeTabFromApi(s.tab_sas), SFS: normalizeTabFromApi(s.tab_sfs) }
        setGlobalSettings(newGlobal)
        setTabSettings(newTabs)
        // Auto-save loaded CSV settings
        doAutoSave(newGlobal, newTabs, accountId)
      }
      setLastCsv(result.filename || file.name)
    } catch (err) {
      setError(err.message || 'Load CSV failed')
    } finally {
      setCsvLoading(false)
    }
  }

  const handleLoadLastCsv = async () => {
    setCsvLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/xnl/addnewpos/settings/load-last-csv', { method: 'POST' })
      const result = await res.json()
      if (!res.ok || !result.success) throw new Error(result.detail || 'Load last CSV failed')
      if (result.settings) {
        const s = result.settings
        const newGlobal = { enabled: s.enabled ?? true, mode: s.mode ?? 'both', long_ratio: Number(s.long_ratio) || 50, short_ratio: Number(s.short_ratio) || 50, active_tab: s.active_tab ?? 'BB' }
        const newTabs = { BB: normalizeTabFromApi(s.tab_bb), FB: normalizeTabFromApi(s.tab_fb), SAS: normalizeTabFromApi(s.tab_sas), SFS: normalizeTabFromApi(s.tab_sfs) }
        setGlobalSettings(newGlobal)
        setTabSettings(newTabs)
        // Auto-save loaded CSV settings
        doAutoSave(newGlobal, newTabs, accountId)
      }
    } catch (err) {
      setError(err.message || 'Load last failed')
    } finally {
      setCsvLoading(false)
    }
  }

  // Clear filters for current tab only + auto-save
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
      scheduleAutoSave(globalSettings, updated, accountId)
      return updated
    })
  }

  if (loading) {
    return (
      <div className="addnewpos-settings-panel loading">
        <div className="panel-header">
          <h3>📊 ADDNEWPOS Settings (XNL)</h3>
        </div>
        <div className="loading-spinner">Loading...</div>
      </div>
    )
  }

  return (
    <div className={`addnewpos-settings-panel ${collapsed ? 'collapsed' : ''}`}>
      <div className="panel-header" onClick={() => setCollapsed(!collapsed)}>
        <h3>
          <span className="collapse-icon">{collapsed ? '▶' : '▼'}</span>
          📊 ADDNEWPOS Settings
          <span className="account-badge">{accountId}</span>
        </h3>
        <div className="panel-actions">
          {!collapsed && (
            <>
              {/* Auto-save status indicator */}
              {autoSaveStatus === 'saving' && <span className="autosave-indicator saving">⏳ Saving...</span>}
              {autoSaveStatus === 'saved' && <span className="autosave-indicator saved">✓ Saved</span>}
              {autoSaveStatus === 'error' && <span className="autosave-indicator error">⚠️ Save failed</span>}

              {/* Reset to Default button */}
              <button className="reset-btn" onClick={(e) => { e.stopPropagation(); handleResetToDefault(); }} title="Reset all settings to default values">
                🔄 Reset Default
              </button>

              {error && <span className="error-msg">⚠️ {error}</span>}
            </>
          )}
        </div>
      </div>

      {!collapsed && (
        <div className="panel-content">
          {error && (
            <div className="panel-fetch-error" style={{ marginBottom: 8, padding: 8, background: 'rgba(116,42,42,0.3)', borderRadius: 4, color: '#fc8181', fontSize: 10 }}>
              {error}
              <button type="button" onClick={() => { setError(null); setLoading(true); fetchSettings(accountId); }} style={{ marginLeft: 8, padding: '2px 8px', cursor: 'pointer' }}>Retry</button>
            </div>
          )}

          {/* Row 0: Account Selector */}
          <div className="settings-row compact-row account-row">
            <div className="global-label">ACCOUNT:</div>
            <div className="setting-group">
              <div className="account-buttons">
                {['HAMPRO', 'IBKR_PED', 'IBKR_GUN'].map(acc => (
                  <button
                    key={acc}
                    className={`account-btn ${accountId === acc ? 'active' : ''}`}
                    onClick={() => switchAccount(acc)}
                  >
                    {acc}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Row 1: Global Settings - Mode + Enabled + Ratio */}
          <div className="settings-row compact-row">
            <div className="global-label">GLOBAL:</div>

            {/* Mode */}
            <div className="setting-group mode-group">
              <label>Mode:</label>
              <div className="radio-group">
                <label className={globalSettings.mode === 'both' ? 'active' : ''}>
                  <input type="radio" name="mode" value="both" checked={globalSettings.mode === 'both'} onChange={(e) => updateGlobal('mode', e.target.value)} />
                  Both
                </label>
                <label className={globalSettings.mode === 'addlong_only' ? 'active' : ''}>
                  <input type="radio" name="mode" value="addlong_only" checked={globalSettings.mode === 'addlong_only'} onChange={(e) => updateGlobal('mode', e.target.value)} />
                  Long Only
                </label>
                <label className={globalSettings.mode === 'addshort_only' ? 'active' : ''}>
                  <input type="radio" name="mode" value="addshort_only" checked={globalSettings.mode === 'addshort_only'} onChange={(e) => updateGlobal('mode', e.target.value)} />
                  Short Only
                </label>
              </div>
            </div>

            {/* Enabled */}
            <div className="setting-group enabled-group">
              <label>
                <input type="checkbox" checked={globalSettings.enabled} onChange={(e) => updateGlobal('enabled', e.target.checked)} />
                ENABLED
              </label>
            </div>

            <div className="v-divider" />

            {/* Long/Short Ratio */}
            <div className="setting-group ratio-group">
              <label>L/S Ratio:</label>
              <span className="ratio-label long">{globalSettings.long_ratio.toFixed(0)}%</span>
              <input type="range" min="0" max="100" value={globalSettings.long_ratio} onChange={(e) => handleLongRatioChange(e.target.value)} className="ratio-slider" />
              <span className="ratio-label short">{globalSettings.short_ratio.toFixed(0)}%</span>
            </div>

            {/* Tab Selection */}
            <div className="setting-group tab-group">
              <div className="tab-buttons">
                <button className={`tab-btn bb ${activeTab === 'BB' ? 'active' : ''}`} onClick={() => changeTab('BB')}>BB</button>
                <button className={`tab-btn fb ${activeTab === 'FB' ? 'active' : ''}`} onClick={() => changeTab('FB')}>FB</button>
                <button className={`tab-btn sas ${activeTab === 'SAS' ? 'active' : ''}`} onClick={() => changeTab('SAS')}>SAS</button>
                <button className={`tab-btn sfs ${activeTab === 'SFS' ? 'active' : ''}`} onClick={() => changeTab('SFS')}>SFS</button>
              </div>
            </div>
          </div>

          {/* Row 2: Per-Tab Settings - JFIN + Filters */}
          <div className="settings-row compact-row tab-settings-row">
            <div className="tab-label">{activeTab}:</div>

            {/* JFIN % - Per Tab (0% = skip this tab) */}
            <div className="setting-group jfin-group">
              <label>JFIN:</label>
              <div className="jfin-buttons">
                {[0, 25, 50, 75, 100].map(pct => (
                  <button key={pct} className={currentTabSettings.jfin_pct === pct ? 'active' : ''} onClick={() => updateTab('jfin_pct', pct)}>
                    {pct}%
                  </button>
                ))}
              </div>
            </div>

            <div className="v-divider" />

            {/* GORT Range - Per Tab */}
            <div className="setting-group filter-inline">
              <label>GORT:</label>
              <input type="number" placeholder="Min" value={currentTabSettings.gort_min ?? ''} onChange={(e) => updateTab('gort_min', e.target.value ? parseFloat(e.target.value) : null)} step="0.01" />
              <span>—</span>
              <input type="number" placeholder="Max" value={currentTabSettings.gort_max ?? ''} onChange={(e) => updateTab('gort_max', e.target.value ? parseFloat(e.target.value) : null)} step="0.01" />
            </div>

            {/* FBtot/SFStot Filter - Per Tab */}
            <div className="setting-group filter-inline">
              <label>{totLabel}:</label>
              <input
                type="number"
                placeholder="Val"
                value={currentTabSettings.tot_threshold ?? ''}
                onChange={(e) => updateTab('tot_threshold', e.target.value ? parseFloat(e.target.value) : null)}
                step="0.01"
              />
              <div className="mini-radio">
                <label className={currentTabSettings.tot_direction === 'below' ? 'active' : ''}>
                  <input type="radio" name="tot_dir" value="below" checked={currentTabSettings.tot_direction === 'below'}
                    onChange={() => updateTab('tot_direction', 'below')} />
                  &lt;
                </label>
                <label className={currentTabSettings.tot_direction === 'above' ? 'active' : ''}>
                  <input type="radio" name="tot_dir" value="above" checked={currentTabSettings.tot_direction === 'above'}
                    onChange={() => updateTab('tot_direction', 'above')} />
                  &gt;
                </label>
              </div>
            </div>

            {/* SMA63 chg - Per Tab */}
            <div className="setting-group filter-inline">
              <label>SMA63:</label>
              <input type="number" placeholder="Val" value={currentTabSettings.sma63chg_threshold ?? ''} onChange={(e) => updateTab('sma63chg_threshold', e.target.value ? parseFloat(e.target.value) : null)} step="0.01" />
              <div className="mini-radio">
                <label className={currentTabSettings.sma63chg_direction === 'below' ? 'active' : ''}>
                  <input type="radio" name="sma_dir" value="below" checked={currentTabSettings.sma63chg_direction === 'below'} onChange={() => updateTab('sma63chg_direction', 'below')} />
                  &lt;
                </label>
                <label className={currentTabSettings.sma63chg_direction === 'above' ? 'active' : ''}>
                  <input type="radio" name="sma_dir" value="above" checked={currentTabSettings.sma63chg_direction === 'above'} onChange={() => updateTab('sma63chg_direction', 'above')} />
                  &gt;
                </label>
              </div>
            </div>

            {/* Clear Filters for current tab */}
            <button className="clear-filters-btn" onClick={clearCurrentTabFilters} title={`Clear ${activeTab} filters`}>✕ Clear</button>
          </div>

          {/* CSV Save/Load — isim ile kaydet, son CSV default */}
          <div className="settings-row compact-row" style={{ marginTop: '10px', paddingTop: '10px', borderTop: '1px solid #333' }}>
            <div className="setting-group" style={{ flex: '0 0 auto' }}>
              <label>CSV:</label>
              <input type="text" placeholder="Dosya adı (örn. addnewpos_ocak)" value={csvFilename} onChange={e => setCsvFilename(e.target.value)} style={{ width: '160px', marginRight: '6px' }} />
              <button className="save-btn" onClick={handleSaveCsv} disabled={csvSaving} title="Kaydet ve varsayılan yap">{csvSaving ? '...' : '💾 Save CSV'}</button>
            </div>
            <div className="v-divider" />
            <div className="setting-group" style={{ flex: '0 0 auto' }}>
              <label className="btn btn-secondary" style={{ marginBottom: 0 }}>
                Dosyadan yükle
                <input type="file" accept=".csv" onChange={e => handleLoadCsv(e.target.files?.[0])} disabled={csvLoading} style={{ display: 'none' }} />
              </label>
            </div>
            {lastCsv && (
              <>
                <div className="v-divider" />
                <div className="setting-group" style={{ flex: '0 0 auto' }}>
                  <span style={{ color: '#888', marginRight: '8px' }}>Son: {lastCsv}</span>
                  <button className="btn btn-secondary" onClick={handleLoadLastCsv} disabled={csvLoading}>Load last</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default AddnewposSettingsPanel
