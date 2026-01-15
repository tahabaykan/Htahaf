import React, { useState, useEffect, useRef } from 'react';
import './LogViewerPage.css';

const LogViewerPage = () => {
  const [logs, setLogs] = useState([]);
  const [filteredLogs, setFilteredLogs] = useState([]);
  const [statistics, setStatistics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Filters
  const [levelFilter, setLevelFilter] = useState('ALL');
  const [keywordFilter, setKeywordFilter] = useState('');
  const [moduleFilter, setModuleFilter] = useState('');
  
  // Pagination
  const [limit, setLimit] = useState(100);
  const [offset, setOffset] = useState(0);
  
  // Auto-refresh
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState(5); // seconds
  
  const wsRef = useRef(null);
  const logsEndRef = useRef(null);

  // Fetch logs from API
  const fetchLogs = async () => {
    try {
      const params = new URLSearchParams({
        limit: limit.toString(),
        offset: offset.toString(),
      });
      
      if (levelFilter !== 'ALL') params.append('level', levelFilter);
      if (keywordFilter) params.append('keyword', keywordFilter);
      if (moduleFilter) params.append('module', moduleFilter);
      
      const response = await fetch(`/api/logs?${params}`);
      const data = await response.json();
      
      if (data.success) {
        setLogs(data.logs);
        setFilteredLogs(data.logs);
        setError(null);
      } else {
        setError('Failed to fetch logs');
      }
    } catch (err) {
      setError(`Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Fetch statistics
  const fetchStatistics = async () => {
    try {
      const response = await fetch('/api/logs/statistics');
      const data = await response.json();
      if (data.success) {
        setStatistics(data.statistics);
      }
    } catch (err) {
      console.error('Error fetching statistics:', err);
    }
  };

  // WebSocket connection for real-time logs
  useEffect(() => {
    if (!autoRefresh) return;
    
    const ws = new WebSocket('ws://localhost:8000/api/logs/stream');
    wsRef.current = ws;
    
    ws.onopen = () => {
      console.log('✅ Log stream WebSocket connected');
    };
    
    ws.onmessage = (event) => {
      try {
        const logEntry = JSON.parse(event.data);
        setLogs(prev => {
          const newLogs = [logEntry, ...prev].slice(0, limit);
          return newLogs;
        });
      } catch (err) {
        console.error('Error parsing WebSocket message:', err);
      }
    };
    
    ws.onerror = (err) => {
      console.error('WebSocket error:', err);
    };
    
    ws.onclose = () => {
      console.log('📡 Log stream WebSocket disconnected');
    };
    
    return () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    };
  }, [autoRefresh, limit]);

  // Auto-refresh interval
  useEffect(() => {
    if (!autoRefresh) return;
    
    fetchLogs();
    fetchStatistics();
    
    const interval = setInterval(() => {
      fetchLogs();
      fetchStatistics();
    }, refreshInterval * 1000);
    
    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval, levelFilter, keywordFilter, moduleFilter, limit, offset]);

  // Scroll to bottom when new logs arrive
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  // Export logs
  const exportLogs = async (format) => {
    try {
      const params = new URLSearchParams({ format });
      if (levelFilter !== 'ALL') params.append('level', levelFilter);
      if (keywordFilter) params.append('keyword', keywordFilter);
      if (moduleFilter) params.append('module', moduleFilter);
      
      const response = await fetch(`/api/logs/export?${params}`);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `logs_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      alert(`Error exporting logs: ${err.message}`);
    }
  };

  // Clear logs
  const clearLogs = async () => {
    if (!window.confirm('Are you sure you want to clear all logs?')) return;
    
    try {
      const response = await fetch('/api/logs/clear', { method: 'DELETE' });
      const data = await response.json();
      if (data.success) {
        setLogs([]);
        setFilteredLogs([]);
        fetchStatistics();
      }
    } catch (err) {
      alert(`Error clearing logs: ${err.message}`);
    }
  };

  // Get log level color
  const getLevelColor = (level) => {
    switch (level) {
      case 'ERROR':
      case 'CRITICAL':
        return '#ff4444';
      case 'WARNING':
        return '#ffaa00';
      case 'INFO':
        return '#4488ff';
      case 'DEBUG':
        return '#888888';
      default:
        return '#000000';
    }
  };

  // Format timestamp
  const formatTimestamp = (timestamp) => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleString('tr-TR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        fractionalSecondDigits: 3
      });
    } catch {
      return timestamp;
    }
  };

  if (loading && logs.length === 0) {
    return <div className="log-viewer-loading">Loading logs...</div>;
  }

  return (
    <div className="log-viewer-page">
      <div className="log-viewer-header">
        <h1>📊 Log Viewer & Analyzer</h1>
        
        {/* Statistics */}
        {statistics && (
          <div className="log-statistics">
            <div className="stat-item">
              <span className="stat-label">Total Logs:</span>
              <span className="stat-value">{statistics.total_logs}</span>
            </div>
            <div className="stat-item error">
              <span className="stat-label">Errors:</span>
              <span className="stat-value">{statistics.errors}</span>
            </div>
            <div className="stat-item warning">
              <span className="stat-label">Warnings:</span>
              <span className="stat-value">{statistics.warnings}</span>
            </div>
            <div className="stat-item failed">
              <span className="stat-label">Failed:</span>
              <span className="stat-value">{statistics.failed}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Logs/sec:</span>
              <span className="stat-value">{statistics.logs_per_second?.toFixed(2) || '0.00'}</span>
            </div>
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="log-filters">
        <div className="filter-group">
          <label>Level:</label>
          <select value={levelFilter} onChange={(e) => setLevelFilter(e.target.value)}>
            <option value="ALL">All Levels</option>
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
            <option value="CRITICAL">CRITICAL</option>
          </select>
        </div>
        
        <div className="filter-group">
          <label>Keyword:</label>
          <input
            type="text"
            value={keywordFilter}
            onChange={(e) => setKeywordFilter(e.target.value)}
            placeholder="Search in messages..."
          />
        </div>
        
        <div className="filter-group">
          <label>Module:</label>
          <input
            type="text"
            value={moduleFilter}
            onChange={(e) => setModuleFilter(e.target.value)}
            placeholder="Filter by module..."
          />
        </div>
        
        <div className="filter-group">
          <label>Limit:</label>
          <input
            type="number"
            value={limit}
            onChange={(e) => setLimit(parseInt(e.target.value) || 100)}
            min="10"
            max="1000"
          />
        </div>
        
        <div className="filter-group">
          <label>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Auto-refresh
          </label>
        </div>
        
        {autoRefresh && (
          <div className="filter-group">
            <label>Interval (sec):</label>
            <input
              type="number"
              value={refreshInterval}
              onChange={(e) => setRefreshInterval(parseInt(e.target.value) || 5)}
              min="1"
              max="60"
            />
          </div>
        )}
        
        <div className="filter-actions">
          <button onClick={fetchLogs}>🔄 Refresh</button>
          <button onClick={() => exportLogs('json')}>📥 Export JSON</button>
          <button onClick={() => exportLogs('csv')}>📥 Export CSV</button>
          <button onClick={clearLogs} className="danger">🗑️ Clear</button>
        </div>
      </div>

      {/* Error message */}
      {error && <div className="log-error">{error}</div>}

      {/* Logs table */}
      <div className="log-table-container">
        <table className="log-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Level</th>
              <th>Module</th>
              <th>Function</th>
              <th>Line</th>
              <th>Message</th>
              <th>Keywords</th>
            </tr>
          </thead>
          <tbody>
            {filteredLogs.length === 0 ? (
              <tr>
                <td colSpan="7" className="no-logs">No logs found</td>
              </tr>
            ) : (
              filteredLogs.map((log, index) => (
                <tr key={index} className={`log-row log-level-${log.level.toLowerCase()}`}>
                  <td className="log-timestamp">{formatTimestamp(log.timestamp)}</td>
                  <td className="log-level" style={{ color: getLevelColor(log.level) }}>
                    {log.level}
                  </td>
                  <td className="log-module">{log.module}</td>
                  <td className="log-function">{log.function}</td>
                  <td className="log-line">{log.line}</td>
                  <td className="log-message">{log.message}</td>
                  <td className="log-keywords">
                    {log.keywords && log.keywords.length > 0 ? (
                      <div className="keyword-tags">
                        {log.keywords.slice(0, 3).map((kw, i) => (
                          <span key={i} className="keyword-tag">{kw}</span>
                        ))}
                      </div>
                    ) : (
                      '-'
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        <div ref={logsEndRef} />
      </div>
    </div>
  );
};

export default LogViewerPage;




