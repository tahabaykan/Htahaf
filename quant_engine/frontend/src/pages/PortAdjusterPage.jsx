import React, { useEffect, useState, useMemo, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import './TradingPage.css'
import JFINModal from '../components/JFINModal'

const groupOrder = [
  'heldcilizyeniyedi', 'heldcommonsuz', 'helddeznff', 'heldff', 'heldflr',
  'heldgarabetaltiyedi', 'heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta',
  'heldnff', 'heldotelremorta', 'heldsolidbig', 'heldtitrekhc', 'highmatur',
  'notbesmaturlu', 'notcefilliquid', 'nottitrekhc', 'rumoreddanger', 'salakilliquid', 'shitremhc'
]

const ACCOUNT_OPTIONS = ['IBKR_PED', 'HAMPRO', 'IBKR_GUN']

function PortAdjusterPage() {
  const [accountId, setAccountId] = useState('IBKR_PED')
  const [config, setConfig] = useState(null)
  const [snapshot, setSnapshot] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [autoSaveStatus, setAutoSaveStatus] = useState(null)
  const autoSaveTimer = useRef(null)
  const [recalcLoading, setRecalcLoading] = useState(false)
  const [presets, setPresets] = useState([])
  const [presetName, setPresetName] = useState('')
  const [csvImporting, setCsvImporting] = useState(false)
  const [csvFilename, setCsvFilename] = useState('')
  const [lastCsv, setLastCsv] = useState(null)
  const [jfinModalOpen, setJfinModalOpen] = useState(false)

  const loadInitial = useCallback(async (acc) => {
    const targetAcc = acc || accountId
    try {
      setLoading(true)
      // Use V2 endpoints with account parameter
      const [cfgRes, presetRes] = await Promise.all([
        fetch(`/api/psfalgo/port-adjuster-v2/config?account_id=${targetAcc}`),
        fetch('/api/psfalgo/port-adjuster/presets/list')
      ])
      if (cfgRes.ok) {
        const result = await cfgRes.json()
        if (result.success && result.config) {
          setConfig(result.config)
        }
      }
      // Get snapshot separately
      const snapRes = await fetch(`/api/psfalgo/port-adjuster-v2/snapshot?account_id=${targetAcc}`)
      if (snapRes.ok) {
        const snapResult = await snapRes.json()
        if (snapResult.success && snapResult.snapshot) {
          setSnapshot(snapResult.snapshot)
        }
      }
      if (presetRes.ok) {
        const pres = await presetRes.json()
        setPresets(pres.presets || [])
      }
      setError(null)
    } catch (e) {
      console.error(e)
      setError('Failed to load Port Adjuster data')
    } finally {
      setLoading(false)
    }
  }, [accountId])

  useEffect(() => {
    loadInitial()
  }, [])

  // Reload when account changes
  const handleAccountChange = (newAcc) => {
    setAccountId(newAcc)
    loadInitial(newAcc)
  }

  const longTotal = useMemo(() => config ? Object.values(config.long_groups || {}).reduce((a, b) => a + Number(b || 0), 0) : 0, [config])
  const shortTotal = useMemo(() => config ? Object.values(config.short_groups || {}).reduce((a, b) => a + Number(b || 0), 0) : 0, [config])
  const ltMmTotal = useMemo(() => config ? (Number(config.lt_ratio_pct || 0) + Number(config.mm_ratio_pct || 0)) : 0, [config])

  const isValidTotals = (longTotal >= 99 && longTotal <= 101) && (shortTotal >= 99 && shortTotal <= 101) && (ltMmTotal >= 99 && ltMmTotal <= 101)

  // Auto-save config (debounced 1000ms)
  const doAutoSave = useCallback(async (configToSave, accId) => {
    if (!configToSave) return
    try {
      setAutoSaveStatus('saving')
      const res = await fetch(`/api/psfalgo/port-adjuster-v2/config?account_id=${accId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(configToSave)
      })
      const result = await res.json()
      if (!res.ok || !result.success) throw new Error(result.detail || 'Save failed')
      setSnapshot(result.snapshot)
      setAutoSaveStatus('saved')
      setTimeout(() => setAutoSaveStatus(null), 1500)
      setError(null)
    } catch (e) {
      setAutoSaveStatus('error')
      setTimeout(() => setAutoSaveStatus(null), 3000)
    }
  }, [])

  const scheduleAutoSave = useCallback((configToSave, accId) => {
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
    autoSaveTimer.current = setTimeout(() => doAutoSave(configToSave, accId), 1000)
  }, [doAutoSave])

  useEffect(() => {
    return () => { if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current) }
  }, [])

  const updateCore = (key, value) => {
    setConfig(prev => {
      const updated = { ...prev, [key]: value }
      scheduleAutoSave(updated, accountId)
      return updated
    })
  }

  const updateGroup = (side, group, value) => {
    setConfig(prev => {
      const target = side === 'long' ? { ...(prev.long_groups || {}) } : { ...(prev.short_groups || {}) }
      target[group] = Number(value)
      const updated = {
        ...prev,
        [`${side}_groups`]: target
      }
      scheduleAutoSave(updated, accountId)
      return updated
    })
  }



  const handleRecalc = async () => {
    setRecalcLoading(true)
    try {
      const res = await fetch(`/api/psfalgo/port-adjuster-v2/recalculate?account_id=${accountId}`, { method: 'POST' })
      const result = await res.json()
      if (!res.ok || !result.success) throw new Error(result.detail || result.error || 'Recalculate failed')
      setSnapshot(result.snapshot)
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setRecalcLoading(false)
    }
  }

  const handlePresetSave = async () => {
    if (!presetName || !config) return
    try {
      const res = await fetch(`/api/psfalgo/port-adjuster/presets/save?name=${encodeURIComponent(presetName)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      })
      const result = await res.json()
      if (!res.ok || !result.success) throw new Error(result.detail || result.error || 'Preset save failed')
      await loadPresets()
    } catch (e) {
      setError(e.message)
    }
  }

  const loadPresets = async () => {
    const res = await fetch('/api/psfalgo/port-adjuster/presets/list')
    if (res.ok) {
      const result = await res.json()
      setPresets(result.presets || [])
    }
  }

  const handlePresetLoad = async (name) => {
    try {
      const res = await fetch(`/api/psfalgo/port-adjuster/presets/load?name=${encodeURIComponent(name)}`, { method: 'POST' })
      const result = await res.json()
      if (!res.ok || !result.success) throw new Error(result.detail || result.error || 'Preset load failed')
      if (result.snapshot && result.snapshot.config) {
        setConfig(result.snapshot.config)
      }
      setSnapshot(result.snapshot)
      setError(null)
    } catch (e) {
      setError(e.message)
    }
  }

  const handleImportCsv = async (file) => {
    if (!file) return
    setCsvImporting(true)
    try {
      const form = new FormData()
      form.append('upload_file', file)
      const res = await fetch('/api/psfalgo/port-adjuster/import-csv', { method: 'POST', body: form })
      const result = await res.json()
      if (!res.ok || !result.success) throw new Error(result.detail || result.error || 'Import failed')
      setConfig(result.config)
      setSnapshot(result.snapshot)
      if (result.filename) setLastCsv(result.filename)
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setCsvImporting(false)
    }
  }

  const handleSaveCsv = async () => {
    const name = (csvFilename || 'exposureadjuster').trim()
    if (!name) return
    setCsvImporting(true)
    try {
      const res = await fetch('/api/psfalgo/port-adjuster/save-csv', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: name })
      })
      const result = await res.json()
      if (!res.ok || !result.success) throw new Error(result.detail || result.error || 'Save CSV failed')
      setLastCsv(result.filename || name + (name.endsWith('.csv') ? '' : '.csv'))
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setCsvImporting(false)
    }
  }

  const handleLoadLastCsv = async () => {
    setCsvImporting(true)
    try {
      const res = await fetch('/api/psfalgo/port-adjuster/load-last-csv', { method: 'POST' })
      const result = await res.json()
      if (!res.ok || !result.success) throw new Error(result.detail || result.error || 'Load last failed')
      setConfig(result.config)
      setSnapshot(result.snapshot)
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setCsvImporting(false)
    }
  }

  const handleExportCsv = async () => {
    const res = await fetch('/api/psfalgo/port-adjuster/export-csv')
    if (!res.ok) return
    const blob = await res.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = lastCsv || 'exposureadjuster.csv'
    a.click()
    window.URL.revokeObjectURL(url)
  }

  if (loading) return <div className="trading-page"><h2>Loading Port Adjuster...</h2></div>
  if (!config) return <div className="trading-page"><h2>Config not available</h2></div>

  return (
    <div className="trading-page">
      <header className="app-header">
        <h1>Port Adjuster</h1>
        <div className="header-actions">
          <Link to="/scanner" className="btn btn-secondary">← Back to Scanner</Link>
        </div>
      </header>

      {/* Account Selector */}
      <section className="card" style={{
        background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
        marginBottom: '20px',
        padding: '15px 20px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px', flexWrap: 'wrap' }}>
          <span style={{ color: '#9ca3af', fontWeight: '500' }}>Active Account:</span>
          <div style={{ display: 'flex', gap: '8px' }}>
            {ACCOUNT_OPTIONS.map(acc => (
              <button
                key={acc}
                onClick={() => handleAccountChange(acc)}
                style={{
                  padding: '8px 16px',
                  borderRadius: '8px',
                  border: 'none',
                  cursor: 'pointer',
                  fontWeight: '600',
                  fontSize: '14px',
                  transition: 'all 0.2s ease',
                  background: accountId === acc
                    ? 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)'
                    : 'rgba(75, 85, 99, 0.5)',
                  color: accountId === acc ? 'white' : '#9ca3af',
                  boxShadow: accountId === acc ? '0 4px 15px rgba(99, 102, 241, 0.4)' : 'none'
                }}
              >
                {acc === 'IBKR_PED' ? '📊 IBKR PED' :
                  acc === 'HAMPRO' ? '🔨 Hammer' :
                    '🔥 IBKR GUN'}
              </button>
            ))}
          </div>
          <span style={{
            marginLeft: 'auto',
            color: '#60a5fa',
            fontSize: '12px',
            background: 'rgba(96, 165, 250, 0.1)',
            padding: '4px 10px',
            borderRadius: '4px'
          }}>
            💾 Settings auto-sync with GenExpo Limiter
          </span>
        </div>
      </section>

      {error && <div className="error-message">{error}</div>}

      <section className="card">
        <div className="card-header">
          <h3>Core Inputs</h3>
          <div className="card-actions">
            <button className="btn btn-secondary" onClick={handleRecalc} disabled={recalcLoading}>Recalculate</button>
            {autoSaveStatus === 'saving' && <span style={{ color: '#fbbf24', fontSize: '12px', padding: '4px 10px' }}>⏳ Saving...</span>}
            {autoSaveStatus === 'saved' && <span style={{ color: '#34d399', fontSize: '12px', padding: '4px 10px' }}>✓ Saved</span>}
            {autoSaveStatus === 'error' && <span style={{ color: '#f87171', fontSize: '12px', padding: '4px 10px' }}>⚠️ Save failed</span>}
          </div>
        </div>
        <div className="card-body grid-4">
          <div className="form-group">
            <label>Total Exposure (USD)</label>
            <input type="number" value={config.total_exposure_usd} onChange={e => updateCore('total_exposure_usd', Number(e.target.value))} />
          </div>
          <div className="form-group">
            <label>Avg Pref Price</label>
            <input type="number" value={config.avg_pref_price} step="0.01" onChange={e => updateCore('avg_pref_price', Number(e.target.value))} />
          </div>
        </div>
      </section>

      <section className="card" style={{ background: 'linear-gradient(135deg, #1e3a5f 0%, #0f2942 100%)' }}>
        <div className="card-header">
          <h3 style={{ color: '#fff' }}>📊 LT / MM Split</h3>
        </div>
        <div className="card-body" style={{ color: '#e5e7eb' }}>
          <div className="grid-4" style={{ marginBottom: '20px' }}>
            <div className="form-group">
              <label style={{ color: '#93c5fd' }}>LT Ratio %</label>
              <input
                type="number"
                value={config.lt_ratio_pct || 70}
                min="0" max="100"
                onChange={e => {
                  const ltVal = Number(e.target.value) || 0
                  updateCore('lt_ratio_pct', ltVal)
                  updateCore('mm_ratio_pct', 100 - ltVal)
                }}
              />
            </div>
            <div className="form-group">
              <label style={{ color: '#fbbf24' }}>MM Ratio %</label>
              <input
                type="number"
                value={config.mm_ratio_pct || 30}
                min="0" max="100"
                onChange={e => {
                  const mmVal = Number(e.target.value) || 0
                  updateCore('mm_ratio_pct', mmVal)
                  updateCore('lt_ratio_pct', 100 - mmVal)
                }}
              />
            </div>
            <div className="form-group">
              <label style={{ color: '#93c5fd' }}>LT Potential Multiplier</label>
              <input
                type="number"
                value={config.lt_potential_multiplier || 1.5}
                min="1" max="5" step="0.1"
                onChange={e => updateCore('lt_potential_multiplier', Number(e.target.value))}
              />
            </div>
            <div className="form-group">
              <label style={{ color: '#fbbf24' }}>MM Potential Multiplier</label>
              <input
                type="number"
                value={config.mm_potential_multiplier || 2.0}
                min="1" max="5" step="0.1"
                onChange={e => updateCore('mm_potential_multiplier', Number(e.target.value))}
              />
            </div>
          </div>

          {/* LT Long/Short Ratio within LT */}
          <div className="grid-4" style={{ marginBottom: '20px', paddingTop: '15px', borderTop: '1px solid #374151' }}>
            <div className="form-group">
              <label style={{ color: '#10b981' }}>LT Long Ratio %</label>
              <input type="number" value={config.long_ratio_pct} onChange={e => updateCore('long_ratio_pct', Number(e.target.value))} />
            </div>
            <div className="form-group">
              <label style={{ color: '#ef4444' }}>LT Short Ratio %</label>
              <input type="number" value={config.short_ratio_pct} onChange={e => updateCore('short_ratio_pct', Number(e.target.value))} />
            </div>
          </div>

          {/* Calculated Values Display */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '15px', background: 'rgba(0,0,0,0.2)', padding: '15px', borderRadius: '8px' }}>
            <div>
              <div style={{ fontSize: '11px', color: '#9ca3af' }}>LT Base Exposure</div>
              <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#93c5fd' }}>
                ${(snapshot?.lt_exposure_usd || 0).toLocaleString()}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '11px', color: '#9ca3af' }}>LT Max Potential</div>
              <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#60a5fa' }}>
                ${(snapshot?.lt_max_potential_usd || 0).toLocaleString()}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '11px', color: '#9ca3af' }}>MM Base Exposure</div>
              <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#fbbf24' }}>
                ${(snapshot?.mm_exposure_usd || 0).toLocaleString()}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '11px', color: '#9ca3af' }}>MM Max Potential</div>
              <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#f59e0b' }}>
                ${(snapshot?.mm_max_potential_usd || 0).toLocaleString()}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="card">
        <div className="card-header">
          <h3>Presets</h3>
          <div className="card-actions">
            <select value="" onChange={e => { if (e.target.value) handlePresetLoad(e.target.value) }}>
              <option value="">Select preset</option>
              {presets.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
            <input type="text" placeholder="Preset name" value={presetName} onChange={e => setPresetName(e.target.value)} />
            <button className="btn btn-secondary" onClick={handlePresetSave} disabled={!presetName}>Save as preset</button>
          </div>
        </div>
      </section>

      <div className="card two-column">
        <div>
          <div className="card-header">
            <h3>Long Groups</h3>
            <div className="pill">Sum: {longTotal.toFixed(1)}%</div>
          </div>
          <div className="table-scroll">
            <table className="simple-table">
              <thead>
                <tr>
                  <th>Group</th>
                  <th>%</th>
                  <th>Max Lot</th>
                  <th>Max Value (USD)</th>
                </tr>
              </thead>
              <tbody>
                {groupOrder.map(g => (
                  <tr key={g}>
                    <td>{g}</td>
                    <td>
                      <input
                        type="number"
                        value={(config.long_groups && config.long_groups[g]) ?? 0}
                        onChange={e => updateGroup('long', g, e.target.value)}
                      />
                    </td>
                    <td>{snapshot?.long_allocations?.[g]?.max_lot?.toFixed(0) || '-'}</td>
                    <td>{snapshot?.long_allocations?.[g]?.max_value_usd?.toFixed(0) || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!(longTotal >= 99 && longTotal <= 101) && <div className="warning-text">Long total should be 99-101%</div>}
        </div>

        <div>
          <div className="card-header">
            <h3>Short Groups</h3>
            <div className="pill">Sum: {shortTotal.toFixed(1)}%</div>
          </div>
          <div className="table-scroll">
            <table className="simple-table">
              <thead>
                <tr>
                  <th>Group</th>
                  <th>%</th>
                  <th>Max Lot</th>
                  <th>Max Value (USD)</th>
                </tr>
              </thead>
              <tbody>
                {groupOrder.map(g => (
                  <tr key={g}>
                    <td>{g}</td>
                    <td>
                      <input
                        type="number"
                        value={(config.short_groups && config.short_groups[g]) ?? 0}
                        onChange={e => updateGroup('short', g, e.target.value)}
                      />
                    </td>
                    <td>{snapshot?.short_allocations?.[g]?.max_lot?.toFixed(0) || '-'}</td>
                    <td>{snapshot?.short_allocations?.[g]?.max_value_usd?.toFixed(0) || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!(shortTotal >= 99 && shortTotal <= 101) && <div className="warning-text">Short total should be 99-101%</div>}
        </div>
      </div>

      <section className="card">
        <div className="card-header">
          <h3>CSV Save/Load (isim ile; son kullanılan varsayılan)</h3>
          <div className="card-actions" style={{ flexWrap: 'wrap', gap: '8px' }}>
            <input type="text" placeholder="Dosya adı (örn. exposure_ocak)" value={csvFilename} onChange={e => setCsvFilename(e.target.value)} style={{ width: '180px' }} />
            <button className="btn btn-primary" onClick={handleSaveCsv} disabled={csvImporting || !(csvFilename || '').trim()}>
              {csvImporting ? '...' : 'Save CSV'}
            </button>
            <span style={{ margin: '0 4px' }}>|</span>
            <label className="btn btn-secondary" style={{ marginBottom: 0 }}>
              Dosyadan yükle
              <input type="file" accept=".csv" onChange={e => handleImportCsv(e.target.files?.[0])} disabled={csvImporting} style={{ display: 'none' }} />
            </label>
            <button className="btn btn-secondary" onClick={handleExportCsv} disabled={csvImporting}>Export CSV</button>
            {lastCsv && (
              <>
                <span style={{ color: '#888', marginLeft: '8px' }}>Son: {lastCsv}</span>
                <button className="btn btn-secondary" onClick={handleLoadLastCsv} disabled={csvImporting}>Load last</button>
              </>
            )}
          </div>
        </div>
      </section>

      <section className="card">
        <div className="card-header">
          <h3>JFIN Window</h3>
          <div className="card-actions">
            <button className="btn btn-primary" onClick={() => setJfinModalOpen(true)}>
              📊 Open JFIN Window
            </button>
          </div>
        </div>
        <div className="card-body">
          <p style={{ color: '#999', fontSize: '13px' }}>
            Open JFIN (Final THG Lot Distributor) window to view and manage BB, FB, SAS, SFS pools.
          </p>
        </div>
      </section>

      <JFINModal isOpen={jfinModalOpen} onClose={() => setJfinModalOpen(false)} />

      <section className="card">
        <div className="card-header">
          <h3>Snapshot Summary</h3>
        </div>
        <div className="card-body grid-4">
          <div>
            <div className="summary-label">Total Lot</div>
            <div className="summary-value">{snapshot?.total_lot?.toFixed(0) || '-'}</div>
          </div>
          <div>
            <div className="summary-label">Long Lot</div>
            <div className="summary-value">{snapshot?.long_lot?.toFixed(0) || '-'}</div>
          </div>
          <div>
            <div className="summary-label">Short Lot</div>
            <div className="summary-value">{snapshot?.short_lot?.toFixed(0) || '-'}</div>
          </div>
          <div>
            <div className="summary-label">Last Saved</div>
            <div className="summary-value">{snapshot?.last_saved_at ? new Date(snapshot.last_saved_at).toLocaleString() : '-'}</div>
            <div className="summary-sub">{snapshot?.config_source || 'n/a'}</div>
          </div>
        </div>
      </section>
    </div>
  )
}

export default PortAdjusterPage

