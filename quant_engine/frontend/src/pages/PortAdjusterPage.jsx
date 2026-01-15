import React, { useEffect, useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import './TradingPage.css'
import JFINModal from '../components/JFINModal'

const groupOrder = [
  'heldcilizyeniyedi', 'heldcommonsuz', 'helddeznff', 'heldff', 'heldflr',
  'heldgarabetaltiyedi', 'heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta',
  'heldnff', 'heldotelremorta', 'heldsolidbig', 'heldtitrekhc', 'highmatur',
  'notbesmaturlu', 'notcefilliquid', 'nottitrekhc', 'rumoreddanger', 'salakilliquid', 'shitremhc'
]

function PortAdjusterPage() {
  const [config, setConfig] = useState(null)
  const [snapshot, setSnapshot] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [recalcLoading, setRecalcLoading] = useState(false)
  const [presets, setPresets] = useState([])
  const [presetName, setPresetName] = useState('')
  const [csvImporting, setCsvImporting] = useState(false)
  const [jfinModalOpen, setJfinModalOpen] = useState(false)

  useEffect(() => {
    loadInitial()
  }, [])

  const loadInitial = async () => {
    try {
      setLoading(true)
      const [cfgRes, snapRes, presetRes] = await Promise.all([
        fetch('/api/psfalgo/port-adjuster/config'),
        fetch('/api/psfalgo/port-adjuster/snapshot'),
        fetch('/api/psfalgo/port-adjuster/presets/list')
      ])
      if (cfgRes.ok) {
        const cfg = await cfgRes.json()
        setConfig(cfg)
      }
      if (snapRes.ok) {
        const snap = await snapRes.json()
        setSnapshot(snap)
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
  }

  const longTotal = useMemo(() => config ? Object.values(config.long_groups || {}).reduce((a, b) => a + Number(b || 0), 0) : 0, [config])
  const shortTotal = useMemo(() => config ? Object.values(config.short_groups || {}).reduce((a, b) => a + Number(b || 0), 0) : 0, [config])
  const ltMmTotal = useMemo(() => config ? (Number(config.lt_ratio_pct || 0) + Number(config.mm_ratio_pct || 0)) : 0, [config])

  const isValidTotals = (longTotal >= 99 && longTotal <= 101) && (shortTotal >= 99 && shortTotal <= 101) && (ltMmTotal >= 99 && ltMmTotal <= 101)

  const updateCore = (key, value) => {
    setConfig(prev => ({ ...prev, [key]: value }))
  }

  const updateGroup = (side, group, value) => {
    setConfig(prev => {
      const target = side === 'long' ? { ...(prev.long_groups || {}) } : { ...(prev.short_groups || {}) }
      target[group] = Number(value)
      return {
        ...prev,
        [`${side}_groups`]: target
      }
    })
  }

  const handleSave = async () => {
    if (!config) return
    setSaving(true)
    try {
      const res = await fetch('/api/psfalgo/port-adjuster/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      })
      const result = await res.json()
      if (!res.ok || !result.success) throw new Error(result.detail || result.error || 'Save failed')
      setSnapshot(result.snapshot)
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleRecalc = async () => {
    setRecalcLoading(true)
    try {
      const res = await fetch('/api/psfalgo/port-adjuster/recalculate', { method: 'POST' })
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
    a.download = 'exposureadjuster.csv'
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

      {error && <div className="error-message">{error}</div>}

      <section className="card">
        <div className="card-header">
          <h3>Core Inputs</h3>
          <div className="card-actions">
            <button className="btn btn-secondary" onClick={handleRecalc} disabled={recalcLoading}>Recalculate</button>
            <button className="btn btn-primary" onClick={handleSave} disabled={!isValidTotals || saving}>{saving ? 'Saving...' : 'Save'}</button>
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
          <h3>CSV Import/Export</h3>
          <div className="card-actions">
            <input type="file" accept=".csv" onChange={e => handleImportCsv(e.target.files[0])} disabled={csvImporting} />
            <button className="btn btn-secondary" onClick={handleExportCsv}>Export CSV</button>
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

