import React, { useState, useEffect, useCallback } from 'react'
import './AdminPanel.css'

const STATUS_COLORS = {
  fresh: '#10b981',
  ok: '#10b981',
  healthy: '#10b981',
  running: '#10b981',
  stale: '#f59e0b',
  warning: '#f59e0b',
  dead: '#ef4444',
  critical: '#ef4444',
  error: '#ef4444',
  missing: '#6b7280',
  no_data: '#6b7280',
  empty: '#6b7280',
  STOPPED: '#ef4444',
  RUNNING: '#10b981',
}

const STATUS_ICONS = {
  fresh: '🟢',
  ok: '🟢',
  healthy: '🟢',
  running: '🟢',
  stale: '🟡',
  warning: '🟡',
  dead: '🔴',
  critical: '🔴',
  error: '🔴',
  missing: '⚫',
  no_data: '⚫',
  empty: '⚫',
  STOPPED: '🔴',
  RUNNING: '🟢',
}

function StatusBadge({ status }) {
  const color = STATUS_COLORS[status] || '#6b7280'
  const icon = STATUS_ICONS[status] || '⚪'
  return (
    <span className="admin-status-badge" style={{ color, borderColor: color }}>
      {icon} {(status || 'unknown').toUpperCase()}
    </span>
  )
}

function DataCard({ title, icon, status, children }) {
  const borderColor = STATUS_COLORS[status] || '#374151'
  return (
    <div className="admin-data-card" style={{ borderLeftColor: borderColor }}>
      <div className="admin-card-header">
        <span className="admin-card-icon">{icon}</span>
        <span className="admin-card-title">{title}</span>
        <StatusBadge status={status} />
      </div>
      <div className="admin-card-body">
        {children}
      </div>
    </div>
  )
}

function MetricRow({ label, value, highlight }) {
  return (
    <div className="admin-metric-row">
      <span className="admin-metric-label">{label}</span>
      <span className={`admin-metric-value ${highlight || ''}`}>{value ?? 'N/A'}</span>
    </div>
  )
}

function SampleTable({ samples, columns }) {
  if (!samples || samples.length === 0) return null
  return (
    <table className="admin-sample-table">
      <thead>
        <tr>
          {columns.map(col => <th key={col.key}>{col.label}</th>)}
        </tr>
      </thead>
      <tbody>
        {samples.map((s, i) => (
          <tr key={i}>
            {columns.map(col => (
              <td key={col.key} style={col.key === 'status' ? { color: STATUS_COLORS[s[col.key]] } : {}}>
                {col.key === 'status' ? <StatusBadge status={s[col.key]} /> : (
                  col.format ? col.format(s[col.key]) : (s[col.key] ?? '-')
                )}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function AdminPanel({ isOpen, onClose }) {
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [lastUpdate, setLastUpdate] = useState(null)

  const fetchHealth = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/admin/health')
      const data = await res.json()
      if (data.success) {
        setHealth(data.health)
        setLastUpdate(new Date().toLocaleTimeString())
      } else {
        setError(data.error || 'Failed to fetch health data')
      }
    } catch (err) {
      setError(`Connection error: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (isOpen) {
      fetchHealth()
    }
  }, [isOpen, fetchHealth])

  useEffect(() => {
    if (autoRefresh && isOpen) {
      const interval = setInterval(fetchHealth, 10000)
      return () => clearInterval(interval)
    }
  }, [autoRefresh, isOpen, fetchHealth])

  if (!isOpen) return null

  const h = health || {}
  const overall = h.overall || {}

  return (
    <div className="admin-overlay">
      <div className="admin-panel">
        {/* Header */}
        <div className="admin-header">
          <div className="admin-header-left">
            <h2>🛡️ System Admin Panel</h2>
            <StatusBadge status={overall.status} />
            {lastUpdate && <span className="admin-last-update">Updated: {lastUpdate}</span>}
          </div>
          <div className="admin-header-right">
            <a
              href="/static/ops-dashboard.html"
              target="_blank"
              rel="noopener noreferrer"
              className="admin-ops-link"
            >
              📊 Ops Dashboard
            </a>
            <label className="admin-auto-refresh">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
              Auto (10s)
            </label>
            <button className="admin-refresh-btn" onClick={fetchHealth} disabled={loading}>
              {loading ? '⏳' : '🔄'} Refresh
            </button>
            <button className="admin-close-btn" onClick={onClose}>✕</button>
          </div>
        </div>

        {/* Issues Banner */}
        {overall.issues && overall.issues.length > 0 && (
          <div className="admin-issues-banner">
            <span className="admin-issues-icon">⚠️ ISSUES:</span>
            {overall.issues.map((issue, i) => (
              <span key={i} className="admin-issue-tag">{issue}</span>
            ))}
          </div>
        )}

        {error && <div className="admin-error">{error}</div>}

        {/* Main Grid */}
        <div className="admin-grid">

          {/* ═══ ROW 1: Infrastructure ═══ */}

          {/* Hammer Connection */}
          <DataCard title="Hammer Pro Connection" icon="🔌" status={h.hammer_connection?.status}>
            <MetricRow label="Connected" value={h.hammer_connection?.connected ? 'Yes ✅' : 'No ❌'} />
            <MetricRow label="L1 Updates Received" value={h.hammer_connection?.l1_updates_received?.toLocaleString()} />
            <MetricRow label="Last L1 Update" value={h.hammer_connection?.last_l1_age} />
          </DataCard>

          {/* Redis */}
          <DataCard title="Redis" icon="🗄️" status={h.redis?.status}>
            <MetricRow label="Connected" value={h.redis?.connected ? 'Yes ✅' : 'No ❌'} />
            <MetricRow label="Total Keys" value={h.redis?.total_keys?.toLocaleString()} />
            <MetricRow label="Memory" value={h.redis?.used_memory_human} />
          </DataCard>

          {/* Dual Process */}
          <DataCard title="Dual Process" icon="🔄" status={h.dual_process?.status}>
            <MetricRow label="State" value={h.dual_process?.state} highlight={h.dual_process?.state === 'RUNNING' ? 'green' : 'red'} />
            <MetricRow label="Active Account" value={h.dual_process?.current_account || 'None'} />
            <MetricRow label="Loop Count" value={h.dual_process?.loop_count} />
            <MetricRow label="XNL Running" value={h.dual_process?.xnl_running === '1' ? 'Yes 🟢' : 'No 🔴'} />
            <MetricRow label="XNL Account" value={h.dual_process?.xnl_running_account || '-'} />
            {h.dual_process?.started_at && (
              <MetricRow label="Started" value={h.dual_process.started_at} />
            )}
            {h.dual_process?.accounts && (
              <MetricRow label="Accounts" value={h.dual_process.accounts.join(' ↔ ')} />
            )}
          </DataCard>

          {/* ═══ ROW 2: Market Data Pipelines ═══ */}

          {/* Truth Ticks */}
          <DataCard title="Truth Ticks Pipeline" icon="📊" status={h.truth_ticks?.status}>
            <MetricRow label="Total Symbols" value={h.truth_ticks?.total_symbols} />
            <div className="admin-freshness-bar">
              <span style={{ color: '#10b981' }}>🟢 {h.truth_ticks?.fresh || 0}</span>
              <span style={{ color: '#f59e0b' }}>🟡 {h.truth_ticks?.stale || 0}</span>
              <span style={{ color: '#ef4444' }}>🔴 {h.truth_ticks?.dead || 0}</span>
            </div>
            <MetricRow label="Total Ticks" value={h.truth_ticks?.total_ticks?.toLocaleString()} />
            <MetricRow label="Newest Tick" value={h.truth_ticks?.newest_tick_age} />
            <MetricRow label="Oldest Tick" value={h.truth_ticks?.oldest_tick_age} />
            <SampleTable
              samples={h.truth_ticks?.samples}
              columns={[
                { key: 'symbol', label: 'Symbol' },
                { key: 'ticks', label: 'Ticks' },
                { key: 'last_tick_age', label: 'Age' },
                { key: 'status', label: 'Status' },
              ]}
            />
          </DataCard>

          {/* L1 Market Data */}
          <DataCard title="L1 Market Data (bid/ask)" icon="💹" status={h.l1_market_data?.status}>
            <MetricRow label="Total Symbols" value={h.l1_market_data?.total_symbols} />
            <MetricRow label="With Valid Bid/Ask" value={h.l1_market_data?.with_bid_ask} />
            <SampleTable
              samples={h.l1_market_data?.samples}
              columns={[
                { key: 'symbol', label: 'Symbol' },
                { key: 'bid', label: 'Bid', format: v => v ? `$${Number(v).toFixed(2)}` : '-' },
                { key: 'ask', label: 'Ask', format: v => v ? `$${Number(v).toFixed(2)}` : '-' },
                { key: 'ttl', label: 'TTL' },
                { key: 'status', label: 'Status' },
              ]}
            />
          </DataCard>

          {/* TSS v2 */}
          <DataCard title="TSS v2 Scores" icon="📈" status={h.tss_v2?.status}>
            <MetricRow label="Total Symbols" value={h.tss_v2?.total_symbols} />
            <MetricRow label="Newest Score" value={h.tss_v2?.newest_age} />
            <SampleTable
              samples={h.tss_v2?.samples}
              columns={[
                { key: 'symbol', label: 'Symbol' },
                { key: 'score', label: 'Score' },
                { key: 'recency', label: 'Recency' },
                { key: 'age', label: 'Age' },
              ]}
            />
          </DataCard>

          {/* ═══ ROW 3: Per-Account Data ═══ */}

          {/* BEFDAY */}
          <DataCard title="BEFDAY (Daily Snapshot)" icon="📋" status={
            h.befday?.hampro?.status === 'fresh' && h.befday?.ibkr_ped?.status === 'fresh' ? 'fresh' :
            h.befday?.hampro?.status === 'fresh' || h.befday?.ibkr_ped?.status === 'fresh' ? 'stale' : 'missing'
          }>
            <div className="admin-account-section">
              <h4>HAMPRO</h4>
              <MetricRow label="Positions" value={h.befday?.hampro?.position_count} />
              <MetricRow label="Date" value={h.befday?.hampro?.date} />
              <StatusBadge status={h.befday?.hampro?.status} />
            </div>
            <div className="admin-account-section">
              <h4>IBKR_PED</h4>
              <MetricRow label="Positions" value={h.befday?.ibkr_ped?.position_count} />
              <MetricRow label="Date" value={h.befday?.ibkr_ped?.date} />
              <StatusBadge status={h.befday?.ibkr_ped?.status} />
            </div>
          </DataCard>

          {/* Current Positions */}
          <DataCard title="Current Positions" icon="📦" status={
            h.positions?.hampro?.status === 'fresh' ? 'fresh' :
            h.positions?.hampro?.status === 'stale' ? 'stale' : 'missing'
          }>
            <div className="admin-account-section">
              <h4>HAMPRO</h4>
              <MetricRow label="Count" value={h.positions?.hampro?.count} />
              <MetricRow label="Age" value={h.positions?.hampro?.age} />
              <StatusBadge status={h.positions?.hampro?.status} />
            </div>
            <div className="admin-account-section">
              <h4>IBKR_PED</h4>
              <MetricRow label="Count" value={h.positions?.ibkr_ped?.count} />
              <MetricRow label="Age" value={h.positions?.ibkr_ped?.age} />
              <StatusBadge status={h.positions?.ibkr_ped?.status} />
            </div>
          </DataCard>

          {/* Active Orders */}
          <DataCard title="Active Orders" icon="📝" status={
            (h.orders?.hampro?.count > 0 || h.orders?.ibkr_ped?.count > 0) ? 'ok' : 'empty'
          }>
            <div className="admin-account-section">
              <h4>HAMPRO</h4>
              <MetricRow label="Open Orders" value={h.orders?.hampro?.count ?? 0} />
              <StatusBadge status={h.orders?.hampro?.status} />
            </div>
            <div className="admin-account-section">
              <h4>IBKR_PED</h4>
              <MetricRow label="Open Orders" value={h.orders?.ibkr_ped?.count ?? 0} />
              <StatusBadge status={h.orders?.ibkr_ped?.status} />
            </div>
          </DataCard>

          {/* ═══ ROW 4: MinMax + REV ═══ */}

          {/* MinMax */}
          <DataCard title="MinMax Bands" icon="📐" status={
            h.minmax?.hampro?.status === 'fresh' ? 'fresh' :
            h.minmax?.hampro?.status === 'stale' ? 'stale' : 'missing'
          }>
            <div className="admin-account-section">
              <h4>HAMPRO</h4>
              <MetricRow label="Symbols" value={h.minmax?.hampro?.count} />
              <MetricRow label="Computed Date" value={h.minmax?.hampro?.computed_date} />
              <MetricRow label="Age" value={h.minmax?.hampro?.age} />
              <StatusBadge status={h.minmax?.hampro?.status} />
            </div>
            <div className="admin-account-section">
              <h4>IBKR_PED</h4>
              <MetricRow label="Symbols" value={h.minmax?.ibkr_ped?.count} />
              <MetricRow label="Computed Date" value={h.minmax?.ibkr_ped?.computed_date} />
              <MetricRow label="Age" value={h.minmax?.ibkr_ped?.age} />
              <StatusBadge status={h.minmax?.ibkr_ped?.status} />
            </div>
          </DataCard>

          {/* REV Queue */}
          <DataCard title="REV Order Queue" icon="⚡" status={
            (h.rev_queue?.hampro?.queue_length > 0 || h.rev_queue?.ibkr_ped?.queue_length > 0) ? 'warning' : 'ok'
          }>
            <div className="admin-account-section">
              <h4>HAMPRO</h4>
              <MetricRow label="Pending" value={h.rev_queue?.hampro?.queue_length ?? 0}
                highlight={h.rev_queue?.hampro?.queue_length > 0 ? 'amber' : ''} />
              {h.rev_queue?.hampro?.preview?.map((p, i) => (
                <div key={i} className="admin-rev-preview">
                  <span style={{ color: p.action === 'BUY' ? '#10b981' : '#ef4444', fontWeight: 700 }}>
                    {p.action}
                  </span>
                  {' '}{p.qty} {p.symbol}
                </div>
              ))}
            </div>
            <div className="admin-account-section">
              <h4>IBKR_PED</h4>
              <MetricRow label="Pending" value={h.rev_queue?.ibkr_ped?.queue_length ?? 0}
                highlight={h.rev_queue?.ibkr_ped?.queue_length > 0 ? 'amber' : ''} />
              {h.rev_queue?.ibkr_ped?.preview?.map((p, i) => (
                <div key={i} className="admin-rev-preview">
                  <span style={{ color: p.action === 'BUY' ? '#10b981' : '#ef4444', fontWeight: 700 }}>
                    {p.action}
                  </span>
                  {' '}{p.qty} {p.symbol}
                </div>
              ))}
            </div>
          </DataCard>

          {/* Excluded List */}
          <DataCard title="Excluded Symbols" icon="🚫" status={h.excluded_list?.status}>
            <MetricRow label="Count" value={h.excluded_list?.count} />
            {h.excluded_list?.symbols && h.excluded_list.symbols.length > 0 && (
              <div className="admin-excluded-list">
                {h.excluded_list.symbols.map((sym, i) => (
                  <span key={i} className="admin-excluded-tag">{sym}</span>
                ))}
              </div>
            )}
          </DataCard>

        </div>

        {/* Footer */}
        <div className="admin-footer">
          <span>Server Time: {overall.checked_at || '-'}</span>
          <span>•</span>
          <span>Overall: <StatusBadge status={overall.status} /></span>
        </div>
      </div>
    </div>
  )
}
