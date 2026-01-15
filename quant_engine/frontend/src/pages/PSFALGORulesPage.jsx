import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import './PSFALGORulesPage.css'

function PSFALGORulesPage() {
  const [rules, setRules] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [presets, setPresets] = useState([])
  const [presetName, setPresetName] = useState('')
  const [presetDescription, setPresetDescription] = useState('')
  const [activeTab, setActiveTab] = useState('general')

  // Fetch rules on mount
  useEffect(() => {
    fetchRules()
    fetchPresets()
  }, [])

  const fetchRules = async () => {
    try {
      setLoading(true)
      const response = await fetch('/api/psfalgo/rules')
      const data = await response.json()
      
      if (data.success) {
        setRules(data.rules)
        setError(null)
      } else {
        setError('Failed to load rules')
      }
    } catch (err) {
      console.error('Error fetching rules:', err)
      setError('Error loading rules')
    } finally {
      setLoading(false)
    }
  }

  const fetchPresets = async () => {
    try {
      const response = await fetch('/api/psfalgo/rules/presets')
      const data = await response.json()
      
      if (data.success) {
        setPresets(data.presets || [])
      }
    } catch (err) {
      console.error('Error fetching presets:', err)
    }
  }

  const updateRule = (path, value) => {
    const keys = path.split('.')
    setRules(prev => {
      const newRules = JSON.parse(JSON.stringify(prev))
      let current = newRules
      
      for (let i = 0; i < keys.length - 1; i++) {
        if (!current[keys[i]]) {
          current[keys[i]] = {}
        }
        current = current[keys[i]]
      }
      
      // Handle number conversion
      const lastKey = keys[keys.length - 1]
      if (typeof current[lastKey] === 'number') {
        current[lastKey] = parseFloat(value) || 0
      } else if (typeof current[lastKey] === 'boolean') {
        current[lastKey] = value === 'true' || value === true
      } else {
        current[lastKey] = value
      }
      
      return newRules
    })
  }

  const saveRules = async () => {
    try {
      setSaving(true)
      setError(null)
      setSuccess(null)
      
      const response = await fetch('/api/psfalgo/rules', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(rules),
      })
      
      const data = await response.json()
      
      if (data.success) {
        setSuccess('Rules saved successfully!')
        setTimeout(() => setSuccess(null), 3000)
      } else {
        setError(data.error || 'Failed to save rules')
      }
    } catch (err) {
      console.error('Error saving rules:', err)
      setError('Error saving rules')
    } finally {
      setSaving(false)
    }
  }

  const resetToDefaults = async () => {
    if (!window.confirm('Are you sure you want to reset all rules to Janall defaults? This cannot be undone.')) {
      return
    }
    
    try {
      setSaving(true)
      setError(null)
      setSuccess(null)
      
      const response = await fetch('/api/psfalgo/rules/reset', {
        method: 'POST',
      })
      
      const data = await response.json()
      
      if (data.success) {
        setSuccess('Rules reset to defaults!')
        await fetchRules()
        setTimeout(() => setSuccess(null), 3000)
      } else {
        setError(data.error || 'Failed to reset rules')
      }
    } catch (err) {
      console.error('Error resetting rules:', err)
      setError('Error resetting rules')
    } finally {
      setSaving(false)
    }
  }

  const savePreset = async () => {
    if (!presetName.trim()) {
      setError('Please enter a preset name')
      return
    }
    
    try {
      setSaving(true)
      setError(null)
      setSuccess(null)
      
      const params = new URLSearchParams({
        preset_name: presetName,
      })
      if (presetDescription) {
        params.append('description', presetDescription)
      }
      
      const response = await fetch(`/api/psfalgo/rules/presets/save?${params.toString()}`, {
        method: 'POST',
      })
      
      const data = await response.json()
      
      if (data.success) {
        setSuccess(`Preset "${presetName}" saved!`)
        setPresetName('')
        setPresetDescription('')
        await fetchPresets()
        setTimeout(() => setSuccess(null), 3000)
      } else {
        setError(data.error || 'Failed to save preset')
      }
    } catch (err) {
      console.error('Error saving preset:', err)
      setError('Error saving preset')
    } finally {
      setSaving(false)
    }
  }

  const loadPreset = async (name) => {
    if (!window.confirm(`Load preset "${name}"? This will replace current rules.`)) {
      return
    }
    
    try {
      setSaving(true)
      setError(null)
      setSuccess(null)
      
      const response = await fetch(`/api/psfalgo/rules/presets/load?preset_name=${encodeURIComponent(name)}`, {
        method: 'POST',
      })
      
      const data = await response.json()
      
      if (data.success) {
        setSuccess(`Preset "${name}" loaded!`)
        await fetchRules()
        setTimeout(() => setSuccess(null), 3000)
      } else {
        setError(data.error || 'Failed to load preset')
      }
    } catch (err) {
      console.error('Error loading preset:', err)
      setError('Error loading preset')
    } finally {
      setSaving(false)
    }
  }

  const renderInput = (path, value, type = 'number', min = null, max = null, step = null) => {
    const inputProps = {
      type,
      value: value ?? '',
      onChange: (e) => updateRule(path, e.target.value),
      className: 'rule-input',
    }
    
    if (min !== null) inputProps.min = min
    if (max !== null) inputProps.max = max
    if (step !== null) inputProps.step = step
    
    return <input {...inputProps} />
  }

  const renderBoolean = (path, value) => {
    return (
      <label className="rule-checkbox">
        <input
          type="checkbox"
          checked={value || false}
          onChange={(e) => updateRule(path, e.target.checked)}
        />
        <span>{value ? 'Enabled' : 'Disabled'}</span>
      </label>
    )
  }

  const renderSelect = (path, value, options) => {
    return (
      <select
        value={value || options[0]?.value || ''}
        onChange={(e) => updateRule(path, e.target.value)}
        className="rule-input"
      >
        {options.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
    )
  }

  if (loading) {
    return (
      <div className="rules-page">
        <div className="rules-loading">Loading rules...</div>
      </div>
    )
  }

  if (!rules) {
    return (
      <div className="rules-page">
        <div className="rules-error">Failed to load rules</div>
      </div>
    )
  }

  const tabs = [
    { id: 'general', label: '🔄 General', icon: '⚙️' },
    { id: 'exposure', label: '📊 Exposure', icon: '📊' },
    { id: 'karbotu', label: '🔻 KARBOTU', icon: '🔻' },
    { id: 'reducemore', label: '⚡ REDUCEMORE', icon: '⚡' },
    { id: 'addnewpos', label: '🔺 ADDNEWPOS', icon: '🔺' },
    { id: 'jfin', label: '🎯 JFIN', icon: '🎯' },
    { id: 'lotdivider', label: '✂️ Lot Divider', icon: '✂️' },
    { id: 'controller', label: '🎮 Controller', icon: '🎮' },
    { id: 'guardrails', label: '🛡️ Guardrails', icon: '🛡️' },
    { id: 'befday', label: '📅 BEFDAY', icon: '📅' },
    { id: 'presets', label: '💾 Presets', icon: '💾' },
  ]

  return (
    <div className="rules-page">
      <header className="rules-header">
        <div className="rules-header-left">
          <Link to="/psfalgo" className="back-link">
            ← Back to PSFALGO
          </Link>
          <h1>⚙️ Set & Adjust Rules</h1>
          <span className="version-badge">Janall-Compatible v2.0</span>
        </div>
        <div className="rules-header-right">
          <button
            onClick={saveRules}
            disabled={saving}
            className="btn btn-primary"
          >
            {saving ? 'Saving...' : '💾 Save Rules'}
          </button>
          <button
            onClick={resetToDefaults}
            disabled={saving}
            className="btn btn-secondary"
          >
            🔄 Reset to Janall Defaults
          </button>
        </div>
      </header>

      {error && (
        <div className="alert alert-error">
          {error}
        </div>
      )}

      {success && (
        <div className="alert alert-success">
          {success}
        </div>
      )}

      {/* Tab Navigation */}
      <nav className="rules-tabs">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <div className="rules-content">
        {/* General / Cycle Rules */}
        {activeTab === 'general' && (
          <section className="rules-section">
            <h2>🔄 General / Cycle Rules</h2>
            <div className="rules-grid">
              <div className="rule-item">
                <label>Cycle Interval (seconds)</label>
                {renderInput('general.cycle.interval_seconds', rules.general?.cycle?.interval_seconds, 'number', 1, 3600, 1)}
                <span className="rule-description">Cycle interval: ~4 minutes (Janall: ~3-4 min)</span>
              </div>
              <div className="rule-item">
                <label>Order Wait Time (seconds)</label>
                {renderInput('general.cycle.order_wait_seconds', rules.general?.cycle?.order_wait_seconds, 'number', 0, 600, 1)}
                <span className="rule-description">Wait time after orders: 2 minutes (Janall: after(120000))</span>
              </div>
              <div className="rule-item">
                <label>Auto-Cancel After (seconds)</label>
                {renderInput('general.cycle.auto_cancel_after_seconds', rules.general?.cycle?.auto_cancel_after_seconds, 'number', 0, 600, 1)}
                <span className="rule-description">Auto-cancel orders after this time</span>
              </div>
              <div className="rule-item">
                <label>Lot Divider Enabled</label>
                {renderBoolean('general.cycle.lot_divider_enabled', rules.general?.cycle?.lot_divider_enabled)}
                <span className="rule-description">Split large orders into smaller chunks</span>
              </div>
              <div className="rule-item">
                <label>Controller ON Enabled</label>
                {renderBoolean('general.cycle.controller_on_enabled', rules.general?.cycle?.controller_on_enabled)}
                <span className="rule-description">Order lifecycle management</span>
              </div>
            </div>
            
            <h3>Intent Settings</h3>
            <div className="rules-grid">
              <div className="rule-item">
                <label>Intent TTL (seconds)</label>
                {renderInput('general.intent.ttl_seconds', rules.general?.intent?.ttl_seconds, 'number', 1, 600, 1)}
                <span className="rule-description">Intent time-to-live: 90 seconds</span>
              </div>
              <div className="rule-item">
                <label>Max Intents Per Cycle</label>
                {renderInput('general.intent.max_intents_per_cycle', rules.general?.intent?.max_intents_per_cycle, 'number', 1, 1000, 1)}
                <span className="rule-description">Maximum intents per cycle</span>
              </div>
              <div className="rule-item">
                <label>Auto-Expire Enabled</label>
                {renderBoolean('general.intent.auto_expire_enabled', rules.general?.intent?.auto_expire_enabled)}
                <span className="rule-description">Auto-expire intents after TTL</span>
              </div>
            </div>
          </section>
        )}

        {/* Exposure Rules */}
        {activeTab === 'exposure' && (
          <section className="rules-section">
            <h2>📊 Exposure Mode Rules</h2>
            <div className="rules-grid">
              <div className="rule-item">
                <label>Defensive Threshold (%)</label>
                {renderInput('exposure.defensive_threshold_percent', rules.exposure?.defensive_threshold_percent, 'number', 0, 100, 0.1)}
                <span className="rule-description">Janall: defensive_threshold = max_lot * 0.955</span>
              </div>
              <div className="rule-item">
                <label>Offensive Threshold (%)</label>
                {renderInput('exposure.offensive_threshold_percent', rules.exposure?.offensive_threshold_percent, 'number', 0, 100, 0.1)}
                <span className="rule-description">Janall: offensive_threshold = max_lot * 0.927</span>
              </div>
              <div className="rule-item">
                <label>Transition Mode</label>
                {renderSelect('exposure.transition_mode', rules.exposure?.transition_mode, [
                  { value: 'REDUCEMORE', label: 'REDUCEMORE' },
                  { value: 'KARBOTU', label: 'KARBOTU' }
                ])}
                <span className="rule-description">GEÇİŞ mode uses this engine</span>
              </div>
              <div className="rule-item">
                <label>Default Exposure Limit ($)</label>
                {renderInput('exposure.default_exposure_limit', rules.exposure?.default_exposure_limit, 'number', 0, 100000000, 1000)}
                <span className="rule-description">Default portfolio exposure limit</span>
              </div>
              <div className="rule-item">
                <label>Pot Exposure Limit</label>
                {renderInput('exposure.pot_expo_limit', rules.exposure?.pot_expo_limit, 'number', 0, 100000000, 1000)}
                <span className="rule-description">Pot exposure limit</span>
              </div>
            </div>
          </section>
        )}

        {/* KARBOTU Rules */}
        {activeTab === 'karbotu' && (
          <section className="rules-section">
            <h2>🔻 KARBOTU Rules - Take Profit (13 Steps)</h2>
            
            {/* GORT Filter LONGS */}
            <div className="rules-subsection">
              <h3>🟢 GORT Filter (LONGS)</h3>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Enabled</label>
                  {renderBoolean('karbotu.gort_filter_longs.enabled', rules.karbotu?.gort_filter_longs?.enabled)}
                </div>
                <div className="rule-item">
                  <label>GORT &gt;</label>
                  {renderInput('karbotu.gort_filter_longs.filters.gort_gt', rules.karbotu?.gort_filter_longs?.filters?.gort_gt, 'number', -10, 10, 0.1)}
                </div>
                <div className="rule-item">
                  <label>Ask Sell Pahalılık &gt;</label>
                  {renderInput('karbotu.gort_filter_longs.filters.ask_sell_pahalilik_gt', rules.karbotu?.gort_filter_longs?.filters?.ask_sell_pahalilik_gt, 'number', -1, 1, 0.01)}
                </div>
              </div>
            </div>

            {/* LONGS Steps 2-7 */}
            <div className="rules-subsection">
              <h3>🟢 LONGS Steps (2-7)</h3>
              <div className="steps-table">
                <table>
                  <thead>
                    <tr>
                      <th>Step</th>
                      <th>Enabled</th>
                      <th>Fbtot Range</th>
                      <th>Ask Sell Range</th>
                      <th>Lot %</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Step 2: Fbtot &lt; 1.10</td>
                      <td>{renderBoolean('karbotu.step_2.enabled', rules.karbotu?.step_2?.enabled)}</td>
                      <td>&lt; {renderInput('karbotu.step_2.filters.fbtot_lt', rules.karbotu?.step_2?.filters?.fbtot_lt, 'number', 0, 10, 0.01)}</td>
                      <td>&gt; {renderInput('karbotu.step_2.filters.ask_sell_pahalilik_gt', rules.karbotu?.step_2?.filters?.ask_sell_pahalilik_gt, 'number', -1, 1, 0.01)}</td>
                      <td>{renderInput('karbotu.step_2.lot_percentage', rules.karbotu?.step_2?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                    <tr>
                      <td>Step 3: Fbtot 1.11-1.45 Low</td>
                      <td>{renderBoolean('karbotu.step_3.enabled', rules.karbotu?.step_3?.enabled)}</td>
                      <td>{renderInput('karbotu.step_3.filters.fbtot_gte', rules.karbotu?.step_3?.filters?.fbtot_gte, 'number', 0, 10, 0.01)} - {renderInput('karbotu.step_3.filters.fbtot_lte', rules.karbotu?.step_3?.filters?.fbtot_lte, 'number', 0, 10, 0.01)}</td>
                      <td>{renderInput('karbotu.step_3.filters.ask_sell_pahalilik_gte', rules.karbotu?.step_3?.filters?.ask_sell_pahalilik_gte, 'number', -1, 1, 0.01)} - {renderInput('karbotu.step_3.filters.ask_sell_pahalilik_lte', rules.karbotu?.step_3?.filters?.ask_sell_pahalilik_lte, 'number', -1, 1, 0.01)}</td>
                      <td>{renderInput('karbotu.step_3.lot_percentage', rules.karbotu?.step_3?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                    <tr>
                      <td>Step 4: Fbtot 1.11-1.45 High</td>
                      <td>{renderBoolean('karbotu.step_4.enabled', rules.karbotu?.step_4?.enabled)}</td>
                      <td>{renderInput('karbotu.step_4.filters.fbtot_gte', rules.karbotu?.step_4?.filters?.fbtot_gte, 'number', 0, 10, 0.01)} - {renderInput('karbotu.step_4.filters.fbtot_lte', rules.karbotu?.step_4?.filters?.fbtot_lte, 'number', 0, 10, 0.01)}</td>
                      <td>&gt; {renderInput('karbotu.step_4.filters.ask_sell_pahalilik_gt', rules.karbotu?.step_4?.filters?.ask_sell_pahalilik_gt, 'number', -1, 1, 0.01)}</td>
                      <td>{renderInput('karbotu.step_4.lot_percentage', rules.karbotu?.step_4?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                    <tr>
                      <td>Step 5: Fbtot 1.46-1.85 Low</td>
                      <td>{renderBoolean('karbotu.step_5.enabled', rules.karbotu?.step_5?.enabled)}</td>
                      <td>{renderInput('karbotu.step_5.filters.fbtot_gte', rules.karbotu?.step_5?.filters?.fbtot_gte, 'number', 0, 10, 0.01)} - {renderInput('karbotu.step_5.filters.fbtot_lte', rules.karbotu?.step_5?.filters?.fbtot_lte, 'number', 0, 10, 0.01)}</td>
                      <td>{renderInput('karbotu.step_5.filters.ask_sell_pahalilik_gte', rules.karbotu?.step_5?.filters?.ask_sell_pahalilik_gte, 'number', -1, 1, 0.01)} - {renderInput('karbotu.step_5.filters.ask_sell_pahalilik_lte', rules.karbotu?.step_5?.filters?.ask_sell_pahalilik_lte, 'number', -1, 1, 0.01)}</td>
                      <td>{renderInput('karbotu.step_5.lot_percentage', rules.karbotu?.step_5?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                    <tr>
                      <td>Step 6: Fbtot 1.46-1.85 High</td>
                      <td>{renderBoolean('karbotu.step_6.enabled', rules.karbotu?.step_6?.enabled)}</td>
                      <td>{renderInput('karbotu.step_6.filters.fbtot_gte', rules.karbotu?.step_6?.filters?.fbtot_gte, 'number', 0, 10, 0.01)} - {renderInput('karbotu.step_6.filters.fbtot_lte', rules.karbotu?.step_6?.filters?.fbtot_lte, 'number', 0, 10, 0.01)}</td>
                      <td>&gt; {renderInput('karbotu.step_6.filters.ask_sell_pahalilik_gt', rules.karbotu?.step_6?.filters?.ask_sell_pahalilik_gt, 'number', -1, 1, 0.01)}</td>
                      <td>{renderInput('karbotu.step_6.lot_percentage', rules.karbotu?.step_6?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                    <tr>
                      <td>Step 7: Fbtot 1.86-2.10</td>
                      <td>{renderBoolean('karbotu.step_7.enabled', rules.karbotu?.step_7?.enabled)}</td>
                      <td>{renderInput('karbotu.step_7.filters.fbtot_gte', rules.karbotu?.step_7?.filters?.fbtot_gte, 'number', 0, 10, 0.01)} - {renderInput('karbotu.step_7.filters.fbtot_lte', rules.karbotu?.step_7?.filters?.fbtot_lte, 'number', 0, 10, 0.01)}</td>
                      <td>&gt; {renderInput('karbotu.step_7.filters.ask_sell_pahalilik_gt', rules.karbotu?.step_7?.filters?.ask_sell_pahalilik_gt, 'number', -1, 1, 0.01)}</td>
                      <td>{renderInput('karbotu.step_7.lot_percentage', rules.karbotu?.step_7?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* GORT Filter SHORTS */}
            <div className="rules-subsection">
              <h3>🔴 GORT Filter (SHORTS)</h3>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Enabled</label>
                  {renderBoolean('karbotu.gort_filter_shorts.enabled', rules.karbotu?.gort_filter_shorts?.enabled)}
                </div>
                <div className="rule-item">
                  <label>GORT &lt;</label>
                  {renderInput('karbotu.gort_filter_shorts.filters.gort_lt', rules.karbotu?.gort_filter_shorts?.filters?.gort_lt, 'number', -10, 10, 0.1)}
                </div>
                <div className="rule-item">
                  <label>Bid Buy Ucuzluk &lt;</label>
                  {renderInput('karbotu.gort_filter_shorts.filters.bid_buy_ucuzluk_lt', rules.karbotu?.gort_filter_shorts?.filters?.bid_buy_ucuzluk_lt, 'number', -1, 1, 0.01)}
                </div>
              </div>
            </div>

            {/* SHORTS Steps 9-13 */}
            <div className="rules-subsection">
              <h3>🔴 SHORTS Steps (9-13)</h3>
              <div className="steps-table">
                <table>
                  <thead>
                    <tr>
                      <th>Step</th>
                      <th>Enabled</th>
                      <th>SFStot Range</th>
                      <th>Bid Buy Range</th>
                      <th>Lot %</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Step 9: SFStot &gt; 1.70</td>
                      <td>{renderBoolean('karbotu.step_9.enabled', rules.karbotu?.step_9?.enabled)}</td>
                      <td>&gt; {renderInput('karbotu.step_9.filters.sfstot_gt', rules.karbotu?.step_9?.filters?.sfstot_gt, 'number', 0, 10, 0.01)}</td>
                      <td>&lt; {renderInput('karbotu.step_9.filters.bid_buy_ucuzluk_lt', rules.karbotu?.step_9?.filters?.bid_buy_ucuzluk_lt, 'number', -1, 1, 0.01)}</td>
                      <td>{renderInput('karbotu.step_9.lot_percentage', rules.karbotu?.step_9?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                    <tr>
                      <td>Step 10: SFStot 1.40-1.69 Low</td>
                      <td>{renderBoolean('karbotu.step_10.enabled', rules.karbotu?.step_10?.enabled)}</td>
                      <td>{renderInput('karbotu.step_10.filters.sfstot_gte', rules.karbotu?.step_10?.filters?.sfstot_gte, 'number', 0, 10, 0.01)} - {renderInput('karbotu.step_10.filters.sfstot_lte', rules.karbotu?.step_10?.filters?.sfstot_lte, 'number', 0, 10, 0.01)}</td>
                      <td>{renderInput('karbotu.step_10.filters.bid_buy_ucuzluk_gte', rules.karbotu?.step_10?.filters?.bid_buy_ucuzluk_gte, 'number', -1, 1, 0.01)} - {renderInput('karbotu.step_10.filters.bid_buy_ucuzluk_lte', rules.karbotu?.step_10?.filters?.bid_buy_ucuzluk_lte, 'number', -1, 1, 0.01)}</td>
                      <td>{renderInput('karbotu.step_10.lot_percentage', rules.karbotu?.step_10?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                    <tr>
                      <td>Step 11: SFStot 1.40-1.69 High</td>
                      <td>{renderBoolean('karbotu.step_11.enabled', rules.karbotu?.step_11?.enabled)}</td>
                      <td>{renderInput('karbotu.step_11.filters.sfstot_gte', rules.karbotu?.step_11?.filters?.sfstot_gte, 'number', 0, 10, 0.01)} - {renderInput('karbotu.step_11.filters.sfstot_lte', rules.karbotu?.step_11?.filters?.sfstot_lte, 'number', 0, 10, 0.01)}</td>
                      <td>&lt; {renderInput('karbotu.step_11.filters.bid_buy_ucuzluk_lt', rules.karbotu?.step_11?.filters?.bid_buy_ucuzluk_lt, 'number', -1, 1, 0.01)}</td>
                      <td>{renderInput('karbotu.step_11.lot_percentage', rules.karbotu?.step_11?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                    <tr>
                      <td>Step 12: SFStot 1.10-1.39 Low</td>
                      <td>{renderBoolean('karbotu.step_12.enabled', rules.karbotu?.step_12?.enabled)}</td>
                      <td>{renderInput('karbotu.step_12.filters.sfstot_gte', rules.karbotu?.step_12?.filters?.sfstot_gte, 'number', 0, 10, 0.01)} - {renderInput('karbotu.step_12.filters.sfstot_lte', rules.karbotu?.step_12?.filters?.sfstot_lte, 'number', 0, 10, 0.01)}</td>
                      <td>{renderInput('karbotu.step_12.filters.bid_buy_ucuzluk_gte', rules.karbotu?.step_12?.filters?.bid_buy_ucuzluk_gte, 'number', -1, 1, 0.01)} - {renderInput('karbotu.step_12.filters.bid_buy_ucuzluk_lte', rules.karbotu?.step_12?.filters?.bid_buy_ucuzluk_lte, 'number', -1, 1, 0.01)}</td>
                      <td>{renderInput('karbotu.step_12.lot_percentage', rules.karbotu?.step_12?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                    <tr>
                      <td>Step 13: SFStot 1.10-1.39 High</td>
                      <td>{renderBoolean('karbotu.step_13.enabled', rules.karbotu?.step_13?.enabled)}</td>
                      <td>{renderInput('karbotu.step_13.filters.sfstot_gte', rules.karbotu?.step_13?.filters?.sfstot_gte, 'number', 0, 10, 0.01)} - {renderInput('karbotu.step_13.filters.sfstot_lte', rules.karbotu?.step_13?.filters?.sfstot_lte, 'number', 0, 10, 0.01)}</td>
                      <td>&lt; {renderInput('karbotu.step_13.filters.bid_buy_ucuzluk_lt', rules.karbotu?.step_13?.filters?.bid_buy_ucuzluk_lt, 'number', -1, 1, 0.01)}</td>
                      <td>{renderInput('karbotu.step_13.lot_percentage', rules.karbotu?.step_13?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Settings */}
            <div className="rules-subsection">
              <h3>⚙️ KARBOTU Settings</h3>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Min Lot Size</label>
                  {renderInput('karbotu.settings.min_lot_size', rules.karbotu?.settings?.min_lot_size, 'number', 0, 10000, 1)}
                </div>
                <div className="rule-item">
                  <label>Cooldown (minutes)</label>
                  {renderInput('karbotu.settings.cooldown_minutes', rules.karbotu?.settings?.cooldown_minutes, 'number', 0, 60, 0.1)}
                </div>
                <div className="rule-item">
                  <label>Process LONGS First</label>
                  {renderBoolean('karbotu.settings.process_longs_first', rules.karbotu?.settings?.process_longs_first)}
                </div>
                <div className="rule-item">
                  <label>Exclude Fbtot=0</label>
                  {renderBoolean('karbotu.settings.exclude_fbtot_zero', rules.karbotu?.settings?.exclude_fbtot_zero)}
                </div>
                <div className="rule-item">
                  <label>Exclude SFStot=0</label>
                  {renderBoolean('karbotu.settings.exclude_sfstot_zero', rules.karbotu?.settings?.exclude_sfstot_zero)}
                </div>
              </div>
            </div>
          </section>
        )}

        {/* REDUCEMORE Rules */}
        {activeTab === 'reducemore' && (
          <section className="rules-section">
            <h2>⚡ REDUCEMORE Rules - Aggressive Mode</h2>
            <p className="section-description">Same steps as KARBOTU but with more aggressive lot percentages (25% → 50%, 50% → 75%)</p>
            
            <div className="rules-subsection">
              <h3>Eligibility</h3>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Exposure Ratio Threshold</label>
                  {renderInput('reducemore.eligibility.exposure_ratio_threshold', rules.reducemore?.eligibility?.exposure_ratio_threshold, 'number', 0, 1, 0.01)}
                  <span className="rule-description">Run if exposure_ratio &gt;= this value (0.8 = 80%)</span>
                </div>
                <div className="rule-item">
                  <label>Pot Total Multiplier</label>
                  {renderInput('reducemore.eligibility.pot_total_multiplier', rules.reducemore?.eligibility?.pot_total_multiplier, 'number', 0, 1, 0.01)}
                  <span className="rule-description">Run if pot_total &gt; this × pot_max</span>
                </div>
              </div>
            </div>

            {/* LONGS Steps */}
            <div className="rules-subsection">
              <h3>🟢 LONGS Steps (Aggressive)</h3>
              <div className="steps-table">
                <table>
                  <thead>
                    <tr>
                      <th>Step</th>
                      <th>Enabled</th>
                      <th>KARBOTU Lot %</th>
                      <th>REDUCEMORE Lot %</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Step 2: Fbtot &lt; 1.10</td>
                      <td>{renderBoolean('reducemore.step_2.enabled', rules.reducemore?.step_2?.enabled)}</td>
                      <td>50%</td>
                      <td>{renderInput('reducemore.step_2.lot_percentage', rules.reducemore?.step_2?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                    <tr>
                      <td>Step 3: Fbtot 1.11-1.45 Low</td>
                      <td>{renderBoolean('reducemore.step_3.enabled', rules.reducemore?.step_3?.enabled)}</td>
                      <td>25%</td>
                      <td>{renderInput('reducemore.step_3.lot_percentage', rules.reducemore?.step_3?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                    <tr>
                      <td>Step 4: Fbtot 1.11-1.45 High</td>
                      <td>{renderBoolean('reducemore.step_4.enabled', rules.reducemore?.step_4?.enabled)}</td>
                      <td>50%</td>
                      <td>{renderInput('reducemore.step_4.lot_percentage', rules.reducemore?.step_4?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                    <tr>
                      <td>Step 5: Fbtot 1.46-1.85 Low</td>
                      <td>{renderBoolean('reducemore.step_5.enabled', rules.reducemore?.step_5?.enabled)}</td>
                      <td>25%</td>
                      <td>{renderInput('reducemore.step_5.lot_percentage', rules.reducemore?.step_5?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                    <tr>
                      <td>Step 6: Fbtot 1.46-1.85 High</td>
                      <td>{renderBoolean('reducemore.step_6.enabled', rules.reducemore?.step_6?.enabled)}</td>
                      <td>50%</td>
                      <td>{renderInput('reducemore.step_6.lot_percentage', rules.reducemore?.step_6?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                    <tr>
                      <td>Step 7: Fbtot 1.86-2.10</td>
                      <td>{renderBoolean('reducemore.step_7.enabled', rules.reducemore?.step_7?.enabled)}</td>
                      <td>25%</td>
                      <td>{renderInput('reducemore.step_7.lot_percentage', rules.reducemore?.step_7?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* SHORTS Steps */}
            <div className="rules-subsection">
              <h3>🔴 SHORTS Steps (Aggressive)</h3>
              <div className="steps-table">
                <table>
                  <thead>
                    <tr>
                      <th>Step</th>
                      <th>Enabled</th>
                      <th>KARBOTU Lot %</th>
                      <th>REDUCEMORE Lot %</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Step 9: SFStot &gt; 1.70</td>
                      <td>{renderBoolean('reducemore.step_9.enabled', rules.reducemore?.step_9?.enabled)}</td>
                      <td>50%</td>
                      <td>{renderInput('reducemore.step_9.lot_percentage', rules.reducemore?.step_9?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                    <tr>
                      <td>Step 10: SFStot 1.40-1.69 Low</td>
                      <td>{renderBoolean('reducemore.step_10.enabled', rules.reducemore?.step_10?.enabled)}</td>
                      <td>25%</td>
                      <td>{renderInput('reducemore.step_10.lot_percentage', rules.reducemore?.step_10?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                    <tr>
                      <td>Step 11: SFStot 1.40-1.69 High</td>
                      <td>{renderBoolean('reducemore.step_11.enabled', rules.reducemore?.step_11?.enabled)}</td>
                      <td>50%</td>
                      <td>{renderInput('reducemore.step_11.lot_percentage', rules.reducemore?.step_11?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                    <tr>
                      <td>Step 12: SFStot 1.10-1.39 Low</td>
                      <td>{renderBoolean('reducemore.step_12.enabled', rules.reducemore?.step_12?.enabled)}</td>
                      <td>25%</td>
                      <td>{renderInput('reducemore.step_12.lot_percentage', rules.reducemore?.step_12?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                    <tr>
                      <td>Step 13: SFStot 1.10-1.39 High</td>
                      <td>{renderBoolean('reducemore.step_13.enabled', rules.reducemore?.step_13?.enabled)}</td>
                      <td>50%</td>
                      <td>{renderInput('reducemore.step_13.lot_percentage', rules.reducemore?.step_13?.lot_percentage, 'number', 0, 100, 1)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div className="rules-subsection">
              <h3>⚙️ Settings</h3>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Spread Tolerance (%)</label>
                  {renderInput('reducemore.settings.spread_tolerance_percent', rules.reducemore?.settings?.spread_tolerance_percent, 'number', 0, 1, 0.01)}
                  <span className="rule-description">Wider spread tolerance (less price perfection)</span>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* ADDNEWPOS Rules */}
        {activeTab === 'addnewpos' && (
          <section className="rules-section">
            <h2>🔺 ADDNEWPOS Rules - Add New Positions</h2>
            
            <div className="rules-subsection">
              <h3>Eligibility</h3>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Exposure Ratio Threshold</label>
                  {renderInput('addnewpos.eligibility.exposure_ratio_threshold', rules.addnewpos?.eligibility?.exposure_ratio_threshold, 'number', 0, 1, 0.01)}
                  <span className="rule-description">Run if exposure_ratio &lt; this value</span>
                </div>
                <div className="rule-item">
                  <label>Required Mode</label>
                  {renderSelect('addnewpos.eligibility.exposure_mode', rules.addnewpos?.eligibility?.exposure_mode, [
                    { value: 'OFANSIF', label: 'OFANSIF' },
                    { value: 'ANY', label: 'ANY' }
                  ])}
                </div>
              </div>
            </div>

            <div className="rules-subsection">
              <h3>🟢 AddLong Filters</h3>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>AddLong Enabled</label>
                  {renderBoolean('addnewpos.addlong.enabled', rules.addnewpos?.addlong?.enabled)}
                </div>
                <div className="rule-item">
                  <label>Bid Buy Ucuzluk &gt;</label>
                  {renderInput('addnewpos.addlong.filters.bid_buy_ucuzluk_gt', rules.addnewpos?.addlong?.filters?.bid_buy_ucuzluk_gt, 'number', 0, 1, 0.01)}
                </div>
                <div className="rule-item">
                  <label>Fbtot &gt;</label>
                  {renderInput('addnewpos.addlong.filters.fbtot_gt', rules.addnewpos?.addlong?.filters?.fbtot_gt, 'number', 0, 10, 0.01)}
                  <span className="rule-description">Expensive = good to buy</span>
                </div>
                <div className="rule-item">
                  <label>Spread &lt;</label>
                  {renderInput('addnewpos.addlong.filters.spread_lt', rules.addnewpos?.addlong?.filters?.spread_lt, 'number', 0, 1, 0.01)}
                </div>
                <div className="rule-item">
                  <label>AVG_ADV &gt;</label>
                  {renderInput('addnewpos.addlong.filters.avg_adv_gt', rules.addnewpos?.addlong?.filters?.avg_adv_gt, 'number', 0, 100000, 1)}
                </div>
              </div>
            </div>

            <div className="rules-subsection">
              <h3>🔴 AddShort Filters</h3>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>AddShort Enabled</label>
                  {renderBoolean('addnewpos.addshort.enabled', rules.addnewpos?.addshort?.enabled)}
                </div>
                <div className="rule-item">
                  <label>Ask Sell Pahalılık &gt;</label>
                  {renderInput('addnewpos.addshort.filters.ask_sell_pahalilik_gt', rules.addnewpos?.addshort?.filters?.ask_sell_pahalilik_gt, 'number', 0, 1, 0.01)}
                </div>
                <div className="rule-item">
                  <label>SFStot &gt;</label>
                  {renderInput('addnewpos.addshort.filters.sfstot_gt', rules.addnewpos?.addshort?.filters?.sfstot_gt, 'number', 0, 10, 0.01)}
                  <span className="rule-description">Cheap = good to short</span>
                </div>
                <div className="rule-item">
                  <label>Spread &lt;</label>
                  {renderInput('addnewpos.addshort.filters.spread_lt', rules.addnewpos?.addshort?.filters?.spread_lt, 'number', 0, 1, 0.01)}
                </div>
                <div className="rule-item">
                  <label>AVG_ADV &gt;</label>
                  {renderInput('addnewpos.addshort.filters.avg_adv_gt', rules.addnewpos?.addshort?.filters?.avg_adv_gt, 'number', 0, 100000, 1)}
                </div>
              </div>
            </div>

            <div className="rules-subsection">
              <h3>Portfolio Thresholds (Janall addnewpos_rules)</h3>
              <div className="rules-table">
                <table>
                  <thead>
                    <tr>
                      <th>Max Portfolio %</th>
                      <th>MAXALW Multiplier</th>
                      <th>Portfolio %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rules.addnewpos?.rules?.thresholds?.map((threshold, idx) => (
                      <tr key={idx}>
                        <td>
                          {renderInput(`addnewpos.rules.thresholds.${idx}.max_portfolio_percent`, threshold.max_portfolio_percent, 'number', 0, 100, 0.1)}
                        </td>
                        <td>
                          {renderInput(`addnewpos.rules.thresholds.${idx}.maxalw_multiplier`, threshold.maxalw_multiplier, 'number', 0, 1, 0.01)}
                        </td>
                        <td>
                          {renderInput(`addnewpos.rules.thresholds.${idx}.portfolio_percent`, threshold.portfolio_percent, 'number', 0, 10, 0.1)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Exposure Usage (%)</label>
                  {renderInput('addnewpos.rules.exposure_usage_percent', rules.addnewpos?.rules?.exposure_usage_percent, 'number', 0, 100, 0.1)}
                  <span className="rule-description">Use 60% of remaining exposure</span>
                </div>
              </div>
            </div>

            <div className="rules-subsection">
              <h3>⚙️ Settings</h3>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Mode</label>
                  {renderSelect('addnewpos.settings.mode', rules.addnewpos?.settings?.mode, [
                    { value: 'addlong_only', label: 'AddLong Only' },
                    { value: 'addshort_only', label: 'AddShort Only' },
                    { value: 'both', label: 'Both' }
                  ])}
                </div>
                <div className="rule-item">
                  <label>Max Lot Per Symbol</label>
                  {renderInput('addnewpos.settings.max_lot_per_symbol', rules.addnewpos?.settings?.max_lot_per_symbol, 'number', 0, 10000, 1)}
                </div>
                <div className="rule-item">
                  <label>Default Lot</label>
                  {renderInput('addnewpos.settings.default_lot', rules.addnewpos?.settings?.default_lot, 'number', 0, 10000, 1)}
                </div>
                <div className="rule-item">
                  <label>Min Lot Size</label>
                  {renderInput('addnewpos.settings.min_lot_size', rules.addnewpos?.settings?.min_lot_size, 'number', 0, 10000, 1)}
                </div>
                <div className="rule-item">
                  <label>Cooldown (minutes)</label>
                  {renderInput('addnewpos.settings.cooldown_minutes', rules.addnewpos?.settings?.cooldown_minutes, 'number', 0, 60, 0.1)}
                </div>
              </div>
            </div>
          </section>
        )}

        {/* Lot Divider */}
        {activeTab === 'lotdivider' && (
          <section className="rules-section">
            <h2>✂️ Lot Divider - Split Large Orders</h2>
            <p className="section-description">Splits large orders into smaller chunks to avoid market impact</p>
            
            <div className="rules-grid">
              <div className="rule-item">
                <label>Enabled</label>
                {renderBoolean('lot_divider.enabled', rules.lot_divider?.enabled)}
              </div>
              <div className="rule-item">
                <label>Max Lot Per Order</label>
                {renderInput('lot_divider.max_lot_per_order', rules.lot_divider?.max_lot_per_order, 'number', 100, 10000, 100)}
                <span className="rule-description">Maximum lot per single order</span>
              </div>
              <div className="rule-item">
                <label>Split Threshold</label>
                {renderInput('lot_divider.split_threshold', rules.lot_divider?.split_threshold, 'number', 100, 10000, 100)}
                <span className="rule-description">Split if lot &gt; this value</span>
              </div>
              <div className="rule-item">
                <label>Split Delay (ms)</label>
                {renderInput('lot_divider.split_delay_ms', rules.lot_divider?.split_delay_ms, 'number', 0, 5000, 100)}
                <span className="rule-description">Delay between split orders</span>
              </div>
            </div>
          </section>
        )}

        {/* Controller ON */}
        {activeTab === 'controller' && (
          <section className="rules-section">
            <h2>🎮 Controller ON - Order Lifecycle Management</h2>
            
            <div className="rules-subsection">
              <h3>Order Cancel Loop</h3>
              <p className="section-description">Cancel unfilled orders after timeout (Janall: 2 minutes)</p>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Enabled</label>
                  {renderBoolean('controller_on.order_cancel.enabled', rules.controller_on?.order_cancel?.enabled)}
                </div>
                <div className="rule-item">
                  <label>Check Interval (seconds)</label>
                  {renderInput('controller_on.order_cancel.check_interval_seconds', rules.controller_on?.order_cancel?.check_interval_seconds, 'number', 1, 300, 1)}
                </div>
                <div className="rule-item">
                  <label>Max Order Age (seconds)</label>
                  {renderInput('controller_on.order_cancel.max_order_age_seconds', rules.controller_on?.order_cancel?.max_order_age_seconds, 'number', 1, 600, 1)}
                  <span className="rule-description">Janall: 120 seconds (2 minutes)</span>
                </div>
                <div className="rule-item">
                  <label>Cancel Unfilled Orders</label>
                  {renderBoolean('controller_on.order_cancel.cancel_unfilled_orders', rules.controller_on?.order_cancel?.cancel_unfilled_orders)}
                </div>
              </div>
            </div>

            <div className="rules-subsection">
              <h3>Order Replace Loop</h3>
              <p className="section-description">Replace orders with better prices</p>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Enabled</label>
                  {renderBoolean('controller_on.order_replace.enabled', rules.controller_on?.order_replace?.enabled)}
                </div>
                <div className="rule-item">
                  <label>Check Interval (seconds)</label>
                  {renderInput('controller_on.order_replace.check_interval_seconds', rules.controller_on?.order_replace?.check_interval_seconds, 'number', 1, 300, 1)}
                </div>
                <div className="rule-item">
                  <label>Price Improvement Threshold ($)</label>
                  {renderInput('controller_on.order_replace.price_improvement_threshold', rules.controller_on?.order_replace?.price_improvement_threshold, 'number', 0, 1, 0.01)}
                </div>
                <div className="rule-item">
                  <label>Replace Partial Fills</label>
                  {renderBoolean('controller_on.order_replace.replace_partial_fills', rules.controller_on?.order_replace?.replace_partial_fills)}
                </div>
              </div>
            </div>
          </section>
        )}

        {/* Guardrails */}
        {activeTab === 'guardrails' && (
          <section className="rules-section">
            <h2>🛡️ Guardrails - Safety Checks</h2>
            
            <div className="rules-subsection">
              <h3>MAXALW (Company Exposure)</h3>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Company Limit Enabled</label>
                  {renderBoolean('guardrails.maxalw.company_limit_enabled', rules.guardrails?.maxalw?.company_limit_enabled)}
                </div>
                <div className="rule-item">
                  <label>Max Company Exposure (%)</label>
                  {renderInput('guardrails.maxalw.max_company_exposure_percent', rules.guardrails?.maxalw?.max_company_exposure_percent, 'number', 0, 1000, 0.1)}
                </div>
                <div className="rule-item">
                  <label>Check Before Order</label>
                  {renderBoolean('guardrails.maxalw.check_before_order', rules.guardrails?.maxalw?.check_before_order)}
                </div>
              </div>
            </div>

            <div className="rules-subsection">
              <h3>Daily Limits</h3>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Enabled</label>
                  {renderBoolean('guardrails.daily_limits.enabled', rules.guardrails?.daily_limits?.enabled)}
                </div>
                <div className="rule-item">
                  <label>Max Daily Lot Change</label>
                  {renderInput('guardrails.daily_limits.max_daily_lot_change', rules.guardrails?.daily_limits?.max_daily_lot_change, 'number', 0, 100000, 1)}
                </div>
                <div className="rule-item">
                  <label>Max Daily Lot Change Per Symbol</label>
                  {renderInput('guardrails.daily_limits.max_daily_lot_change_per_symbol', rules.guardrails?.daily_limits?.max_daily_lot_change_per_symbol, 'number', 0, 10000, 1)}
                </div>
                <div className="rule-item">
                  <label>Max Daily Orders</label>
                  {renderInput('guardrails.daily_limits.max_daily_orders', rules.guardrails?.daily_limits?.max_daily_orders, 'number', 0, 10000, 1)}
                </div>
              </div>
            </div>

            <div className="rules-subsection">
              <h3>Order Limits</h3>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Max Open Orders</label>
                  {renderInput('guardrails.order_limits.max_open_orders', rules.guardrails?.order_limits?.max_open_orders, 'number', 0, 1000, 1)}
                </div>
                <div className="rule-item">
                  <label>Max Open Orders Per Symbol</label>
                  {renderInput('guardrails.order_limits.max_open_orders_per_symbol', rules.guardrails?.order_limits?.max_open_orders_per_symbol, 'number', 0, 100, 1)}
                </div>
                <div className="rule-item">
                  <label>Max Order Value ($)</label>
                  {renderInput('guardrails.order_limits.max_order_value', rules.guardrails?.order_limits?.max_order_value, 'number', 0, 1000000, 1000)}
                </div>
              </div>
            </div>

            <div className="rules-subsection">
              <h3>Duplicate Prevention</h3>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Enabled</label>
                  {renderBoolean('guardrails.duplicate_prevention.enabled', rules.guardrails?.duplicate_prevention?.enabled)}
                </div>
                <div className="rule-item">
                  <label>Duplicate Intent Window (seconds)</label>
                  {renderInput('guardrails.duplicate_prevention.duplicate_intent_window_seconds', rules.guardrails?.duplicate_prevention?.duplicate_intent_window_seconds, 'number', 0, 3600, 1)}
                </div>
                <div className="rule-item">
                  <label>Same Symbol Cooldown (seconds)</label>
                  {renderInput('guardrails.duplicate_prevention.same_symbol_cooldown_seconds', rules.guardrails?.duplicate_prevention?.same_symbol_cooldown_seconds, 'number', 0, 3600, 1)}
                  <span className="rule-description">5 minutes cooldown per symbol</span>
                </div>
                <div className="rule-item">
                  <label>Check Pending Orders</label>
                  {renderBoolean('guardrails.duplicate_prevention.check_pending_orders', rules.guardrails?.duplicate_prevention?.check_pending_orders)}
                </div>
              </div>
            </div>

            <div className="rules-subsection">
              <h3>Position Limits</h3>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Enabled</label>
                  {renderBoolean('guardrails.position_limits.enabled', rules.guardrails?.position_limits?.enabled)}
                </div>
                <div className="rule-item">
                  <label>Max Position Per Symbol</label>
                  {renderInput('guardrails.position_limits.max_position_per_symbol', rules.guardrails?.position_limits?.max_position_per_symbol, 'number', 0, 100000, 100)}
                </div>
                <div className="rule-item">
                  <label>Max Total Positions</label>
                  {renderInput('guardrails.position_limits.max_total_positions', rules.guardrails?.position_limits?.max_total_positions, 'number', 0, 1000, 1)}
                </div>
                <div className="rule-item">
                  <label>Max Sector Exposure (%)</label>
                  {renderInput('guardrails.position_limits.max_sector_exposure_percent', rules.guardrails?.position_limits?.max_sector_exposure_percent, 'number', 0, 100, 0.1)}
                </div>
              </div>
            </div>
          </section>
        )}

        {/* JFIN - Deterministic Transformer */}
        {activeTab === 'jfin' && (
          <section className="rules-section">
            <h2>🎯 JFIN - Deterministic Transformer for ADDNEWPOS</h2>
            <div className="jfin-warning">
              ⚠️ JFIN output is <strong>INTENTIONS</strong>, NOT orders. Orders require user approval before execution.
              <br />
              📊 BB/FB/SAS/SFS pools are <strong>STRICTLY SEPARATE</strong> - same stock can appear in multiple pools.
            </div>
            
            <div className="rules-subsection">
              <h3>📊 TUMCSV Selection Parameters</h3>
              <p className="section-description">Controls how many stocks are selected from each group</p>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Selection Percent</label>
                  {renderSelect('jfin.tumcsv.selection_percent', rules.jfin?.tumcsv?.selection_percent, [
                    { value: 0.10, label: 'V10 - 10%' },
                    { value: 0.12, label: 'V15 - 12%' },
                    { value: 0.15, label: 'V20 - 15%' },
                  ])}
                  <span className="rule-description">Percentage of stocks to select from each group</span>
                </div>
                <div className="rule-item">
                  <label>Minimum Selection</label>
                  {renderInput('jfin.tumcsv.min_selection', rules.jfin?.tumcsv?.min_selection, 'number', 1, 20, 1)}
                  <span className="rule-description">Minimum stocks per group</span>
                </div>
                <div className="rule-item">
                  <label>HELDKUPONLU Pair Count</label>
                  {renderInput('jfin.tumcsv.heldkuponlu_pair_count', rules.jfin?.tumcsv?.heldkuponlu_pair_count, 'number', 1, 20, 1)}
                  <span className="rule-description">Special rule for HELDKUPONLU group</span>
                </div>
              </div>
              
              <div className="jfin-presets">
                <h4>Quick Presets</h4>
                <button 
                  className="btn btn-small"
                  onClick={() => {
                    updateRule('jfin.tumcsv.selection_percent', 0.10)
                    updateRule('jfin.tumcsv.min_selection', 2)
                    updateRule('jfin.tumcsv.heldkuponlu_pair_count', 8)
                  }}
                >
                  V10TUMCSV
                </button>
                <button 
                  className="btn btn-small"
                  onClick={() => {
                    updateRule('jfin.tumcsv.selection_percent', 0.12)
                    updateRule('jfin.tumcsv.min_selection', 2)
                    updateRule('jfin.tumcsv.heldkuponlu_pair_count', 10)
                  }}
                >
                  V15TUMCSV
                </button>
                <button 
                  className="btn btn-small"
                  onClick={() => {
                    updateRule('jfin.tumcsv.selection_percent', 0.15)
                    updateRule('jfin.tumcsv.min_selection', 3)
                    updateRule('jfin.tumcsv.heldkuponlu_pair_count', 12)
                  }}
                >
                  V20TUMCSV
                </button>
              </div>
            </div>

            <div className="rules-subsection">
              <h3>📈 Lot Distribution Parameters</h3>
              <p className="section-description">Alpha-weighted lot distribution to groups and stocks</p>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Alpha Coefficient</label>
                  {renderInput('jfin.lot_distribution.alpha', rules.jfin?.lot_distribution?.alpha, 'number', 0.5, 10, 0.5)}
                  <span className="rule-description">Higher alpha = more weight to higher scores</span>
                </div>
                <div className="rule-item">
                  <label>Total Long Rights</label>
                  {renderInput('jfin.lot_distribution.total_long_rights', rules.jfin?.lot_distribution?.total_long_rights, 'number', 0, 100000, 1000)}
                  <span className="rule-description">Total lot rights for LONG positions</span>
                </div>
                <div className="rule-item">
                  <label>Total Short Rights</label>
                  {renderInput('jfin.lot_distribution.total_short_rights', rules.jfin?.lot_distribution?.total_short_rights, 'number', 0, 100000, 1000)}
                  <span className="rule-description">Total lot rights for SHORT positions</span>
                </div>
                <div className="rule-item">
                  <label>Lot Rounding</label>
                  {renderInput('jfin.lot_distribution.lot_rounding', rules.jfin?.lot_distribution?.lot_rounding, 'number', 1, 500, 1)}
                  <span className="rule-description">Round lots to this value (e.g., 100)</span>
                </div>
              </div>
            </div>

            <div className="rules-subsection">
              <h3>🎯 JFIN Percentage</h3>
              <p className="section-description">What percentage of calculated lots to use for intents</p>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Default Percentage</label>
                  {renderSelect('jfin.percentage.default', rules.jfin?.percentage?.default, [
                    { value: 25, label: '25%' },
                    { value: 50, label: '50% (Default)' },
                    { value: 75, label: '75%' },
                    { value: 100, label: '100%' },
                  ])}
                  <span className="rule-description">Percentage of addable lot to use</span>
                </div>
              </div>
              <div className="jfin-percentage-buttons">
                <button 
                  className={`btn btn-percentage ${rules.jfin?.percentage?.default === 25 ? 'active' : ''}`}
                  onClick={() => updateRule('jfin.percentage.default', 25)}
                >
                  25%
                </button>
                <button 
                  className={`btn btn-percentage ${rules.jfin?.percentage?.default === 50 ? 'active' : ''}`}
                  onClick={() => updateRule('jfin.percentage.default', 50)}
                >
                  50%
                </button>
                <button 
                  className={`btn btn-percentage ${rules.jfin?.percentage?.default === 75 ? 'active' : ''}`}
                  onClick={() => updateRule('jfin.percentage.default', 75)}
                >
                  75%
                </button>
                <button 
                  className={`btn btn-percentage ${rules.jfin?.percentage?.default === 100 ? 'active' : ''}`}
                  onClick={() => updateRule('jfin.percentage.default', 100)}
                >
                  100%
                </button>
              </div>
            </div>

            <div className="rules-subsection">
              <h3>📊 Exposure Settings</h3>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Exposure Percent</label>
                  {renderInput('jfin.exposure.exposure_percent', rules.jfin?.exposure?.exposure_percent, 'number', 0, 100, 1)}
                  <span className="rule-description">Max exposure usage (default: 60%)</span>
                </div>
                <div className="rule-item">
                  <label>Apply to All Pools</label>
                  {renderBoolean('jfin.exposure.apply_to_all_pools', rules.jfin?.exposure?.apply_to_all_pools)}
                </div>
              </div>
            </div>

            <div className="rules-subsection">
              <h3>📦 Lot Controls</h3>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Minimum Lot Per Order</label>
                  {renderInput('jfin.lot_controls.min_lot_per_order', rules.jfin?.lot_controls?.min_lot_per_order, 'number', 100, 5000, 100)}
                  <span className="rule-description">Orders below this are filtered out</span>
                </div>
                <div className="rule-item">
                  <label>Maximum Lot Per Order</label>
                  {renderInput('jfin.lot_controls.max_lot_per_order', rules.jfin?.lot_controls?.max_lot_per_order, 'number', 100, 50000, 100)}
                  <span className="rule-description">Safety limit per order</span>
                </div>
              </div>
            </div>

            <div className="rules-subsection">
              <h3>🏊 Pool Configuration</h3>
              <p className="section-description">Configure each pool separately (BB/FB for LONG, SAS/SFS for SHORT)</p>
              
              <div className="jfin-pools">
                <div className="jfin-pool long">
                  <h4>📈 LONG Pools</h4>
                  <div className="pool-item">
                    <label>
                      <input
                        type="checkbox"
                        checked={rules.jfin?.pools?.bb_long?.enabled ?? true}
                        onChange={(e) => updateRule('jfin.pools.bb_long.enabled', e.target.checked)}
                      />
                      <span className="pool-name">BB_LONG</span>
                      <span className="pool-desc">Bid Buy - bid + (spread × 0.15)</span>
                    </label>
                  </div>
                  <div className="pool-item">
                    <label>
                      <input
                        type="checkbox"
                        checked={rules.jfin?.pools?.fb_long?.enabled ?? true}
                        onChange={(e) => updateRule('jfin.pools.fb_long.enabled', e.target.checked)}
                      />
                      <span className="pool-name">FB_LONG</span>
                      <span className="pool-desc">Front Buy - last + 0.01</span>
                    </label>
                  </div>
                </div>
                
                <div className="jfin-pool short">
                  <h4>📉 SHORT Pools</h4>
                  <div className="pool-item">
                    <label>
                      <input
                        type="checkbox"
                        checked={rules.jfin?.pools?.sas_short?.enabled ?? true}
                        onChange={(e) => updateRule('jfin.pools.sas_short.enabled', e.target.checked)}
                      />
                      <span className="pool-name">SAS_SHORT</span>
                      <span className="pool-desc">Ask Sell - ask - (spread × 0.15)</span>
                    </label>
                  </div>
                  <div className="pool-item">
                    <label>
                      <input
                        type="checkbox"
                        checked={rules.jfin?.pools?.sfs_short?.enabled ?? true}
                        onChange={(e) => updateRule('jfin.pools.sfs_short.enabled', e.target.checked)}
                      />
                      <span className="pool-name">SFS_SHORT</span>
                      <span className="pool-desc">Front Sell - last - 0.01</span>
                    </label>
                  </div>
                </div>
              </div>
            </div>

            <div className="rules-subsection">
              <h3>📋 Daily Limits (BEFDAY × 2)</h3>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Daily Limits Enabled</label>
                  {renderBoolean('jfin.daily_limits.enabled', rules.jfin?.daily_limits?.enabled)}
                </div>
                <div className="rule-item">
                  <label>BEFDAY Multiplier</label>
                  {renderInput('jfin.daily_limits.befday_multiplier', rules.jfin?.daily_limits?.befday_multiplier, 'number', 1, 10, 0.5)}
                  <span className="rule-description">Daily limit = BEFDAY × this value</span>
                </div>
              </div>
            </div>

            <div className="rules-subsection">
              <h3>🔐 Intent Settings</h3>
              <div className="rules-grid">
                <div className="rule-item">
                  <label>Require Approval</label>
                  {renderBoolean('jfin.intent.require_approval', rules.jfin?.intent?.require_approval)}
                  <span className="rule-description">⚠️ ALWAYS keep this ON for safety</span>
                </div>
                <div className="rule-item">
                  <label>Intent TTL (seconds)</label>
                  {renderInput('jfin.intent.ttl_seconds', rules.jfin?.intent?.ttl_seconds, 'number', 60, 3600, 60)}
                  <span className="rule-description">Intent expires after this time</span>
                </div>
              </div>
            </div>

            <div className="jfin-algorithm-info">
              <h3>📋 JFIN Algorithm Flow</h3>
              <ol>
                <li><strong>TUMCSV Selection:</strong> Select top X% stocks from each group by score</li>
                <li><strong>Lot Distribution:</strong> Alpha-weighted lot allocation to groups → stocks</li>
                <li><strong>Addable Lot Calculation:</strong> Clip to MAXALW, position, daily limit</li>
                <li><strong>Apply Percentage:</strong> 25% / 50% / 75% / 100% of addable lot</li>
                <li><strong>Calculate Prices:</strong> BB/FB/SAS/SFS price formulas</li>
                <li><strong>Generate Intentions:</strong> Create PENDING intents for approval</li>
              </ol>
            </div>
          </section>
        )}

        {/* BEFDAY Tracking */}
        {activeTab === 'befday' && (
          <section className="rules-section">
            <h2>📅 BEFDAY Tracking - Daily Position Snapshots</h2>
            <p className="section-description">
              Track positions at market open. Creates befham.csv (Hammer Pro), befibgun.csv (IBKR GUN), befibped.csv (IBKR PED)
            </p>
            
            <div className="rules-grid">
              <div className="rule-item">
                <label>BEFDAY Tracking Enabled</label>
                {renderBoolean('general.befday_tracking.enabled', rules.general?.befday_tracking?.enabled)}
              </div>
              <div className="rule-item">
                <label>Hammer Pro CSV File</label>
                <input
                  type="text"
                  value={rules.general?.befday_tracking?.csv_file || 'befham.csv'}
                  onChange={(e) => updateRule('general.befday_tracking.csv_file', e.target.value)}
                  className="rule-input"
                />
                <span className="rule-description">Auto-created when connected to Hammer Pro</span>
              </div>
              <div className="rule-item">
                <label>IBKR GUN CSV File</label>
                <input
                  type="text"
                  value={rules.general?.befday_tracking?.csv_file_ibkr_gun || 'befibgun.csv'}
                  onChange={(e) => updateRule('general.befday_tracking.csv_file_ibkr_gun', e.target.value)}
                  className="rule-input"
                />
                <span className="rule-description">Auto-created when IBKR GUN selected</span>
              </div>
              <div className="rule-item">
                <label>IBKR PED CSV File</label>
                <input
                  type="text"
                  value={rules.general?.befday_tracking?.csv_file_ibkr_ped || 'befibped.csv'}
                  onChange={(e) => updateRule('general.befday_tracking.csv_file_ibkr_ped', e.target.value)}
                  className="rule-input"
                />
                <span className="rule-description">Auto-created when IBKR PED selected</span>
              </div>
            </div>

            <div className="befday-info">
              <h3>📋 BEFDAY Logic</h3>
              <ul>
                <li>✅ Runs once per day between 00:00 - 16:30</li>
                <li>✅ Skips if today's CSV already exists</li>
                <li>✅ Saves all positions (LONGS + SHORTS with quantity)</li>
                <li>✅ Tracks position changes throughout the day</li>
              </ul>
            </div>
          </section>
        )}

        {/* Presets */}
        {activeTab === 'presets' && (
          <section className="rules-section">
            <h2>💾 Presets</h2>
            <div className="presets-section">
              <div className="presets-save">
                <h3>Save Current Rules as Preset</h3>
                <div className="presets-form">
                  <input
                    type="text"
                    placeholder="Preset name"
                    value={presetName}
                    onChange={(e) => setPresetName(e.target.value)}
                    className="rule-input"
                  />
                  <input
                    type="text"
                    placeholder="Description (optional)"
                    value={presetDescription}
                    onChange={(e) => setPresetDescription(e.target.value)}
                    className="rule-input"
                  />
                  <button
                    onClick={savePreset}
                    disabled={saving || !presetName.trim()}
                    className="btn btn-primary"
                  >
                    Save Preset
                  </button>
                </div>
              </div>
              <div className="presets-list">
                <h3>Load Preset</h3>
                {presets.length === 0 ? (
                  <p className="no-presets">No presets saved yet</p>
                ) : (
                  <div className="presets-grid">
                    {presets.map((preset, idx) => (
                      <div key={idx} className="preset-card">
                        <div className="preset-name">{preset.name}</div>
                        <div className="preset-description">{preset.description || 'No description'}</div>
                        <div className="preset-meta">
                          Saved: {new Date(preset.saved_at).toLocaleDateString()}
                        </div>
                        <button
                          onClick={() => loadPreset(preset.name)}
                          disabled={saving}
                          className="btn btn-small"
                        >
                          Load
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </section>
        )}
      </div>
    </div>
  )
}

export default PSFALGORulesPage
