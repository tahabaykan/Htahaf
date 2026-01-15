import React, { useState, useEffect, useMemo } from 'react'

const SnapBidAskModal = ({ isOpen, onClose }) => {
    const [searchTerm, setSearchTerm] = useState('')
    const [selectedSymbol, setSelectedSymbol] = useState(null)
    const [historyData, setHistoryData] = useState([])
    const [loading, setLoading] = useState(false)
    const [allSymbols, setAllSymbols] = useState([])

    // Load available symbols on mount (from static list or by fetching once)
    useEffect(() => {
        if (isOpen) {
            // Load symbols from backend
            fetch('/api/market-data/merged')
                .then(res => res.json())
                .then(data => {
                    if (data.success && data.data) {
                        setAllSymbols(data.data.map(item => item.PREF_IBKR || item.symbol).sort())
                    }
                })
                .catch(err => console.error("Error loading symbols", err))
        }
    }, [isOpen])

    // Load history when symbol selected
    useEffect(() => {
        if (selectedSymbol) {
            setLoading(true)
            fetch(`/api/market-data/snapshots/${selectedSymbol}/history`)
                .then(res => res.json())
                .then(data => {
                    if (data.success && data.data) {
                        setHistoryData(data.data)
                    } else {
                        setHistoryData([])
                    }
                })
                .catch(err => {
                    console.error("Error fetching history", err)
                    setHistoryData([])
                })
                .finally(() => setLoading(false))
        } else {
            setHistoryData([])
        }
    }, [selectedSymbol])

    // Filter symbols
    const filteredSymbols = useMemo(() => {
        if (!searchTerm) return allSymbols.slice(0, 50) // Show first 50 if empty
        const term = searchTerm.toLowerCase()
        return allSymbols.filter(s => s.toLowerCase().includes(term)).slice(0, 50)
    }, [allSymbols, searchTerm])

    if (!isOpen) return null

    return (
        <div style={{
            position: 'fixed',
            top: 0,
            left: 0,
            width: '100vw',
            height: '100vh',
            backgroundColor: 'rgba(0,0,0,0.85)',
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backdropFilter: 'blur(4px)'
        }}>
            <div style={{
                width: '900px',
                height: '600px',
                backgroundColor: '#111',
                border: '1px solid #333',
                borderRadius: '12px',
                display: 'flex',
                flexDirection: 'column',
                boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
                overflow: 'hidden',
                color: '#eee',
                fontFamily: 'Consolas, monospace'
            }}>
                {/* Header */}
                <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '16px',
                    borderBottom: '1px solid #333',
                    backgroundColor: '#0a0a0a'
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <span style={{ fontSize: '1.25rem' }}>📊</span>
                        <h2 style={{ fontSize: '1.25rem', fontWeight: 'bold', margin: 0, color: 'white' }}>SnapBidAsk Inspector</h2>
                        <span style={{
                            fontSize: '0.75rem',
                            backgroundColor: '#1e3a8a',
                            color: '#bfdbfe',
                            padding: '2px 8px',
                            borderRadius: '4px',
                            marginLeft: '8px'
                        }}>Live History</span>
                    </div>
                    <button
                        onClick={onClose}
                        style={{
                            background: 'none',
                            border: 'none',
                            color: '#9ca3af',
                            cursor: 'pointer',
                            fontSize: '1.5rem',
                            padding: '4px'
                        }}
                    >
                        ✕
                    </button>
                </div>

                <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
                    {/* Sidebar: Symbol Selection */}
                    <div style={{
                        width: '30%',
                        borderRight: '1px solid #333',
                        display: 'flex',
                        flexDirection: 'column',
                        backgroundColor: '#050505'
                    }}>
                        <div style={{ padding: '12px', borderBottom: '1px solid #333' }}>
                            <div style={{ position: 'relative' }}>
                                <span style={{
                                    position: 'absolute',
                                    left: '12px',
                                    top: '50%',
                                    transform: 'translateY(-50%)',
                                    color: '#6b7280'
                                }}>🔍</span>
                                <input
                                    type="text"
                                    placeholder="Search Symbol..."
                                    style={{
                                        width: '100%',
                                        backgroundColor: '#1a1a1a',
                                        color: 'white',
                                        padding: '8px 12px 8px 36px',
                                        borderRadius: '4px',
                                        border: '1px solid #333',
                                        fontSize: '0.875rem',
                                        outline: 'none'
                                    }}
                                    value={searchTerm}
                                    onChange={e => setSearchTerm(e.target.value)}
                                    autoFocus
                                />
                            </div>
                        </div>
                        <div style={{ flex: 1, overflowY: 'auto' }}>
                            {filteredSymbols.map(sym => (
                                <div
                                    key={sym}
                                    onClick={() => setSelectedSymbol(sym)}
                                    style={{
                                        padding: '8px 16px',
                                        cursor: 'pointer',
                                        fontSize: '0.875rem',
                                        fontWeight: '500',
                                        borderBottom: '1px solid #222',
                                        backgroundColor: selectedSymbol === sym ? 'rgba(30, 58, 138, 0.3)' : 'transparent',
                                        color: selectedSymbol === sym ? '#60a5fa' : '#d1d5db',
                                        borderLeft: selectedSymbol === sym ? '4px solid #3b82f6' : '4px solid transparent',
                                        transition: 'background-color 0.2s'
                                    }}
                                >
                                    {sym}
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Main Content: History Table */}
                    <div style={{
                        flex: 1,
                        display: 'flex',
                        flexDirection: 'column',
                        backgroundColor: '#0f0f0f'
                    }}>
                        {selectedSymbol ? (
                            <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                                <div style={{
                                    padding: '24px',
                                    borderBottom: '1px solid #333',
                                    backgroundColor: '#161616'
                                }}>
                                    <h1 style={{ fontSize: '1.875rem', fontWeight: 'bold', color: 'white', margin: '0 0 4px 0' }}>{selectedSymbol}</h1>
                                    <div style={{ color: '#9ca3af', fontSize: '0.875rem' }}>Last 4 Market Snapshots (5-min intervals)</div>
                                </div>

                                <div style={{ padding: '24px', flex: 1, overflowY: 'auto' }}>
                                    {loading ? (
                                        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', color: '#6b7280' }}>
                                            Loading snapshot history...
                                        </div>
                                    ) : historyData.length > 0 ? (
                                        <div style={{ borderRadius: '8px', border: '1px solid #333', overflow: 'hidden' }}>
                                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                                                <thead style={{ backgroundColor: '#222', color: '#9ca3af', textTransform: 'uppercase', fontSize: '0.75rem' }}>
                                                    <tr>
                                                        <th style={{ padding: '12px 24px', textAlign: 'left' }}>Time</th>
                                                        <th style={{ padding: '12px 24px', textAlign: 'right', color: '#4ade80' }}>Bid</th>
                                                        <th style={{ padding: '12px 24px', textAlign: 'right', color: '#f87171' }}>Ask</th>
                                                        <th style={{ padding: '12px 24px', textAlign: 'right', color: 'white' }}>Last</th>
                                                        <th style={{ padding: '12px 24px', textAlign: 'right', color: '#9ca3af' }}>Vol</th>
                                                    </tr>
                                                </thead>
                                                <tbody style={{ backgroundColor: '#111' }}>
                                                    {historyData.map((row, idx) => (
                                                        <tr key={idx} style={{ borderTop: '1px solid #222' }}>
                                                            <td style={{ padding: '16px 24px', color: '#d1d5db', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                                <span>🕒</span>
                                                                {row.timestamp}
                                                            </td>
                                                            <td style={{ padding: '16px 24px', textAlign: 'right', color: '#4ade80', fontWeight: 'bold' }}>
                                                                {row.bid?.toFixed(2) || '-'}
                                                            </td>
                                                            <td style={{ padding: '16px 24px', textAlign: 'right', color: '#f87171', fontWeight: 'bold' }}>
                                                                {row.ask?.toFixed(2) || '-'}
                                                            </td>
                                                            <td style={{ padding: '16px 24px', textAlign: 'right', color: 'white', fontWeight: 'bold' }}>
                                                                {row.last?.toFixed(2) || '-'}
                                                            </td>
                                                            <td style={{ padding: '16px 24px', textAlign: 'right', color: '#9ca3af' }}>
                                                                {row.volume?.toLocaleString() || '-'}
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    ) : (
                                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#6b7280' }}>
                                            <div style={{ fontSize: '2.25rem', marginBottom: '12px' }}>📊</div>
                                            <p>No snapshot history available yet.</p>
                                            <p style={{ fontSize: '0.75rem', marginTop: '4px' }}>Snapshots are processed every 5 minutes.</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#6b7280' }}>
                                <div style={{ fontSize: '3.75rem', marginBottom: '16px' }}>🔍</div>
                                <p style={{ fontSize: '1.125rem', fontWeight: '500' }}>Select a symbol to inspect</p>
                                <p style={{ fontSize: '0.875rem' }}>Search or click a symbol from the list</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    )
}

export default SnapBidAskModal
