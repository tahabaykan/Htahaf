/**
 * Decision Helper Panel
 * 
 * Displays market state classification results from Decision Helper worker.
 */

import React, { useState, useEffect, useMemo } from 'react';
import './DecisionHelperPanel.css';

const API_BASE = 'http://localhost:8000/api';

const DecisionHelperPanel = ({ workerResult = null, loading = false, jobStatus = null, onRefresh = null }) => {
  const [selectedGroup, setSelectedGroup] = useState(null);
  const [selectedWindow, setSelectedWindow] = useState('15m');
  const [sortColumn, setSortColumn] = useState(null);
  const [sortDirection, setSortDirection] = useState('desc');
  
  // Extract groups from worker result
  const groups = useMemo(() => {
    if (!workerResult || !workerResult.groups) {
      return [];
    }
    return Object.keys(workerResult.groups);
  }, [workerResult]);
  
  // Get symbols for selected group
  const symbolsData = useMemo(() => {
    if (!selectedGroup || !workerResult || !workerResult.groups) {
      return [];
    }
    
    const groupData = workerResult.groups[selectedGroup];
    if (!groupData) {
      return [];
    }
    
    // Convert to array of {symbol, windows}
    return Object.entries(groupData).map(([symbol, windows]) => ({
      symbol,
      windows
    }));
  }, [selectedGroup, workerResult]);
  
  // Sort symbols
  const sortedSymbols = useMemo(() => {
    if (!sortColumn) {
      return symbolsData;
    }
    
    return [...symbolsData].sort((a, b) => {
      const aData = a.windows[selectedWindow];
      const bData = b.windows[selectedWindow];
      
      if (!aData || !bData) {
        return 0;
      }
      
      let aVal, bVal;
      
      switch (sortColumn) {
        case 'symbol':
          aVal = a.symbol;
          bVal = b.symbol;
          break;
        case 'state':
          aVal = aData.state || '';
          bVal = bData.state || '';
          break;
        case 'confidence':
          aVal = aData.confidence || 0;
          bVal = bData.confidence || 0;
          break;
        case 'price_displacement':
          aVal = aData.price_displacement || 0;
          bVal = bData.price_displacement || 0;
          break;
        case 'net_pressure':
          aVal = aData.net_pressure || 0;
          bVal = bData.net_pressure || 0;
          break;
        default:
          return 0;
      }
      
      if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
      return 0;
    });
  }, [symbolsData, sortColumn, sortDirection, selectedWindow]);
  
  const handleSort = (column) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('desc');
    }
  };
  
  const getStateColor = (state) => {
    switch (state) {
      case 'BUYER_DOMINANT':
        return '#28a745'; // Strong green - aggressive buyers
      case 'SELLER_DOMINANT':
        return '#dc3545'; // Strong red - aggressive sellers
      case 'BUYER_ABSORPTION':
        return '#90EE90'; // Light green - buyers absorbing sells (bullish)
      case 'SELLER_ABSORPTION':
        return '#FFA500'; // Orange - sellers absorbing buys (bearish)
      case 'BUYER_VACUUM':
        return '#87CEEB'; // Sky blue - fake strength, no real buyers
      case 'SELLER_VACUUM':
        return '#FFB6C1'; // Light pink - air pocket, no real sellers
      case 'NEUTRAL':
        return '#8b949e'; // Gray - unreadable tape
      // Legacy support
      case 'ABSORPTION':
        return '#4ECDC4'; // Teal (maps to BUYER_ABSORPTION)
      case 'VACUUM':
        return '#FFA500'; // Orange (maps to SELLER_VACUUM)
      default:
        return '#8b949e';
    }
  };
  
  return (
    <div className="decision-helper-panel">
      <div className="panel-header">
        <div className="header-left">
          <span className="path-badge">🔵 DECISION HELPER</span>
          <h3>Market State Analysis</h3>
        </div>
        <div className="header-right">
          <button 
            className="refresh-btn"
            onClick={onRefresh}
            disabled={loading}
          >
            {loading ? '...' : '🔄 Refresh'}
          </button>
        </div>
      </div>
      
      {loading && (
        <div className="loading-message">
          <p>Processing decision helper analysis...</p>
          <p className="hint">This may take a few moments</p>
        </div>
      )}
      
      {!loading && groups.length === 0 && (
        <div className="no-data-message">
          <p>No decision helper data available</p>
          <p className="hint">Click "Refresh" to start analysis</p>
        </div>
      )}
      
      {!loading && groups.length > 0 && (
        <>
          <div className="controls">
            <div className="control-group">
              <label>Group:</label>
              <select 
                value={selectedGroup || ''} 
                onChange={(e) => setSelectedGroup(e.target.value)}
                className="group-select"
              >
                <option value="">Select a group...</option>
                {groups.map(group => (
                  <option key={group} value={group}>{group}</option>
                ))}
              </select>
            </div>
            
            <div className="control-group">
              <label>Window:</label>
              <select 
                value={selectedWindow} 
                onChange={(e) => setSelectedWindow(e.target.value)}
                className="window-select"
              >
                <option value="5m">5m</option>
                <option value="15m">15m</option>
                <option value="30m">30m</option>
              </select>
            </div>
            
            <div className="info-text">
              {selectedGroup && sortedSymbols.length > 0 && (
                <span>{sortedSymbols.length} symbols in {selectedGroup}</span>
              )}
            </div>
          </div>
          
          {selectedGroup && sortedSymbols.length > 0 && (
            <div className="results-table-container">
              <table className="results-table">
                <thead>
                  <tr>
                    <th 
                      className={sortColumn === 'symbol' ? 'sortable active' : 'sortable'}
                      onClick={() => handleSort('symbol')}
                    >
                      Symbol {sortColumn === 'symbol' && (sortDirection === 'asc' ? '↑' : '↓')}
                    </th>
                    <th 
                      className={sortColumn === 'state' ? 'sortable active' : 'sortable'}
                      onClick={() => handleSort('state')}
                    >
                      State {sortColumn === 'state' && (sortDirection === 'asc' ? '↑' : '↓')}
                    </th>
                    <th 
                      className={sortColumn === 'confidence' ? 'sortable active' : 'sortable'}
                      onClick={() => handleSort('confidence')}
                    >
                      Confidence {sortColumn === 'confidence' && (sortDirection === 'asc' ? '↑' : '↓')}
                    </th>
                    <th 
                      className={sortColumn === 'price_displacement' ? 'sortable active' : 'sortable'}
                      onClick={() => handleSort('price_displacement')}
                    >
                      Displacement {sortColumn === 'price_displacement' && (sortDirection === 'asc' ? '↑' : '↓')}
                    </th>
                    <th>ADV Fraction</th>
                    <th 
                      className={sortColumn === 'net_pressure' ? 'sortable active' : 'sortable'}
                      onClick={() => handleSort('net_pressure')}
                    >
                      Net Pressure {sortColumn === 'net_pressure' && (sortDirection === 'asc' ? '↑' : '↓')}
                    </th>
                    <th>Efficiency</th>
                    <th>Trade Freq</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedSymbols.map(({ symbol, windows }) => {
                    const data = windows[selectedWindow];
                    if (!data) {
                      return (
                        <tr key={symbol}>
                          <td>{symbol}</td>
                          <td colSpan="7">No data for {selectedWindow}</td>
                        </tr>
                      );
                    }
                    
                    return (
                      <tr key={symbol}>
                        <td className="symbol">{symbol}</td>
                        <td 
                          style={{ 
                            backgroundColor: getStateColor(data.state),
                            color: '#000',
                            fontWeight: 'bold'
                          }}
                        >
                          {data.state}
                        </td>
                        <td>{(data.confidence * 100).toFixed(0)}%</td>
                        <td>{data.price_displacement?.toFixed(3) || '-'}</td>
                        <td>{(data.adv_fraction * 100).toFixed(1)}%</td>
                        <td>{data.net_pressure?.toFixed(3) || '-'}</td>
                        <td>{data.efficiency?.toFixed(2) || '-'}</td>
                        <td>{data.trade_frequency?.toFixed(1) || '-'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default DecisionHelperPanel;



