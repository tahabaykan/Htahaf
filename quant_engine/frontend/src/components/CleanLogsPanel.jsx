
import React, { useState, useEffect, useCallback } from 'react'
import './CleanLogsPanel.css'

function CleanLogsPanel({ tradingMode }) {
    const [logs, setLogs] = useState([])
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)

    // Filters
    const [correlationFilter, setCorrelationFilter] = useState('')
    const [componentFilter, setComponentFilter] = useState('ALL')
    const [severityFilter, setSeverityFilter] = useState('ALL')

    // Expanded details
    const [expandedLogId, setExpandedLogId] = useState(null)

    // Map frontend mode to backend account_id
    const getAccountId = useCallback((mode) => {
        switch (mode) {
            case 'HAMMER_PRO': return 'HAMPRO'
            case 'IBKR_PED': return 'IBKR_PED'
            case 'IBKR_GUN': return 'IBKR_GUN'
            default: return 'HAMPRO'
        }
    }, [])

    const accountId = getAccountId(tradingMode)

    const fetchLogs = useCallback(async () => {
        setLoading(true)
        setError(null)
        try {
            let url = `/api/psfalgo/${accountId}/cleanlogs?limit=200`
            if (correlationFilter) {
                url += `&correlation_id=${correlationFilter}`
            }

            const response = await fetch(url)
            const result = await response.json()

            if (result.success) {
                setLogs(result.logs || [])
            } else {
                setError(result.detail || 'Failed to fetch logs')
            }
        } catch (err) {
            console.error('Error fetching clean logs:', err)
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }, [accountId, correlationFilter])

    // Initial fetch and manual refresh
    useEffect(() => {
        fetchLogs()
    }, [fetchLogs])

    // Local filtering for things not processed by backend (if needed)
    // Backend handles correlation_id, we handle component/severity client-side for now
    const filteredLogs = logs.filter(log => {
        if (componentFilter !== 'ALL' && log.component !== componentFilter) return false
        if (severityFilter !== 'ALL' && log.severity !== severityFilter) return false
        return true
    })

    // Format Helpers
    const formatTime = (isoString) => {
        try {
            return new Date(isoString).toLocaleTimeString()
        } catch (e) {
            return isoString
        }
    }

    const getSeverityBadge = (severity) => {
        let color = '#ccc'
        if (severity === 'INFO') color = '#2196F3'
        if (severity === 'WARNING') color = '#FF9800'
        if (severity === 'CRITICAL') color = '#F44336'
        return <span className="severity-badge" style={{ backgroundColor: color }}>{severity}</span>
    }

    return (
        <div className="clean-logs-panel">
            <div className="logs-controls">
                <div className="control-group">
                    <label>Trace ID:</label>
                    <input
                        type="text"
                        placeholder="Search Correlation ID..."
                        value={correlationFilter}
                        onChange={(e) => setCorrelationFilter(e.target.value)}
                    />
                    {correlationFilter && (
                        <button className="clear-btn" onClick={() => setCorrelationFilter('')}>×</button>
                    )}
                </div>

                <div className="control-group">
                    <label>Component:</label>
                    <select value={componentFilter} onChange={(e) => setComponentFilter(e.target.value)}>
                        <option value="ALL">All Components</option>
                        <option value="DECISION">DECISION</option>
                        <option value="ORDER_CTRL">ORDER</option>
                        <option value="RUNALL">RUNALL</option>
                    </select>
                </div>

                <div className="control-group">
                    <label>Severity:</label>
                    <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}>
                        <option value="ALL">All Severities</option>
                        <option value="INFO">INFO</option>
                        <option value="WARNING">WARNING</option>
                        <option value="CRITICAL">CRITICAL</option>
                    </select>
                </div>

                <button className="refresh-btn" onClick={fetchLogs} disabled={loading}>
                    {loading ? '...' : 'Refresh'}
                </button>
            </div>

            <div className="logs-list">
                {error && <div className="error-banner">{error}</div>}

                {filteredLogs.length === 0 && !loading && (
                    <div className="empty-state">No relevant logs found.</div>
                )}

                <table className="logs-table">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Sev</th>
                            <th>Comp</th>
                            <th>Event</th>
                            <th>Symbol</th>
                            <th>Message</th>
                            <th>Trace</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filteredLogs.map((log, idx) => {
                            const uniqueKey = `${log.timestamp}-${idx}`
                            const isExpanded = expandedLogId === uniqueKey

                            return (
                                <React.Fragment key={uniqueKey}>
                                    <tr
                                        className={`log-row ${isExpanded ? 'active' : ''}`}
                                        onClick={() => setExpandedLogId(isExpanded ? null : uniqueKey)}
                                    >
                                        <td className="time-cell">{formatTime(log.timestamp)}</td>
                                        <td>{getSeverityBadge(log.severity)}</td>
                                        <td><span className="comp-tag">{log.component}</span></td>
                                        <td><span className="event-tag">{log.event}</span></td>
                                        <td>{log.symbol || '-'}</td>
                                        <td className="message-cell">{log.message}</td>
                                        <td>
                                            {log.correlation_id && (
                                                <span
                                                    className="trace-link"
                                                    onClick={(e) => {
                                                        e.stopPropagation()
                                                        setCorrelationFilter(log.correlation_id)
                                                    }}
                                                    title="Filter by this Trace ID"
                                                >
                                                    🔍 {log.correlation_id.substring(0, 8)}...
                                                </span>
                                            )}
                                        </td>
                                    </tr>
                                    {isExpanded && (
                                        <tr className="details-row">
                                            <td colSpan="7">
                                                <div className="log-details-json">
                                                    <pre>{JSON.stringify(log.details, null, 2)}</pre>
                                                    {log.correlation_id && (
                                                        <div className="trace-full-id">
                                                            Full Trace ID: {log.correlation_id}
                                                        </div>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    )}
                                </React.Fragment>
                            )
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    )
}

export default CleanLogsPanel
