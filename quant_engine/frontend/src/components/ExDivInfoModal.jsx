import React, { useState, useEffect, useCallback } from 'react';

/**
 * ExDivInfoModal — Bugün ex-dividend olan hisseleri ve 0.85*DIV_AMOUNT değerlerini gösterir.
 * Pattern Suggestions Modal ile aynı styling/konvansiyonu kullanır.
 */
function ExDivInfoModal({ isOpen, onClose }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const fetchData = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetch('/api/psfalgo/exdiv-today');
            if (!response.ok) {
                const errData = await response.json().catch(() => ({ detail: response.statusText }));
                throw new Error(errData.detail || `HTTP ${response.status}`);
            }
            const result = await response.json();
            if (result.success) {
                setData(result);
            } else {
                throw new Error(result.error || 'Failed to load ex-div info');
            }
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (isOpen) {
            fetchData();
        }
    }, [isOpen, fetchData]);

    if (!isOpen) return null;

    const stocks = data?.stocks || [];

    return (
        <div
            style={{
                position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
                background: 'rgba(0,0,0,0.65)', zIndex: 10000,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                backdropFilter: 'blur(4px)',
            }}
            onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
        >
            <div style={{
                background: '#0f1419', border: '1px solid #2a3a4a', borderRadius: '12px',
                width: '640px', maxHeight: '80vh', display: 'flex', flexDirection: 'column',
                boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
                fontFamily: "'Inter','Segoe UI',sans-serif",
            }}>
                {/* Header */}
                <div style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '16px 20px', borderBottom: '1px solid #1e2a3a',
                    background: 'linear-gradient(135deg, #0f1419, #162030)',
                    borderRadius: '12px 12px 0 0',
                }}>
                    <div>
                        <h2 style={{ margin: 0, fontSize: '16px', color: '#e2e8f0', letterSpacing: '0.3px' }}>
                            💰 Ex-Dividend Info Today
                        </h2>
                        {data && (
                            <div style={{ display: 'flex', gap: '8px', marginTop: '6px', flexWrap: 'wrap' }}>
                                <span style={{
                                    background: 'rgba(251,191,36,0.15)', border: '1px solid rgba(251,191,36,0.3)',
                                    borderRadius: '4px', padding: '2px 8px', fontSize: '11px', color: '#fbbf24'
                                }}>
                                    📅 {data.date_display || data.date}
                                </span>
                                <span style={{
                                    background: 'rgba(34,197,94,0.15)', border: '1px solid rgba(34,197,94,0.3)',
                                    borderRadius: '4px', padding: '2px 8px', fontSize: '11px', color: '#4ade80'
                                }}>
                                    🔢 {data.count} hisse
                                </span>
                                {data.source && (
                                    <span style={{
                                        background: 'rgba(96,165,250,0.1)', border: '1px solid rgba(96,165,250,0.2)',
                                        borderRadius: '4px', padding: '2px 8px', fontSize: '10px', color: '#60a5fa'
                                    }}>
                                        📦 {data.source}
                                    </span>
                                )}
                            </div>
                        )}
                    </div>
                    <button
                        onClick={onClose}
                        style={{
                            background: 'none', border: 'none', color: '#64748b',
                            fontSize: '22px', cursor: 'pointer', padding: '4px 8px',
                            borderRadius: '4px', lineHeight: 1,
                        }}
                        onMouseEnter={(e) => e.target.style.color = '#e2e8f0'}
                        onMouseLeave={(e) => e.target.style.color = '#64748b'}
                    >×</button>
                </div>

                {/* Body */}
                <div style={{ flex: 1, overflow: 'auto', padding: '12px 20px' }}>
                    {loading && (
                        <div style={{ textAlign: 'center', padding: '40px 0', color: '#94a3b8' }}>
                            <div style={{
                                width: '32px', height: '32px', border: '3px solid #1e293b',
                                borderTopColor: '#fbbf24', borderRadius: '50%',
                                animation: 'spin 0.8s linear infinite', margin: '0 auto 12px',
                            }} />
                            Ex-Div bilgileri yükleniyor...
                            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
                        </div>
                    )}

                    {error && (
                        <div style={{
                            background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)',
                            borderRadius: '6px', padding: '12px', color: '#f87171', fontSize: '12px'
                        }}>
                            ⚠️ {error}
                        </div>
                    )}

                    {!loading && data && stocks.length === 0 && (
                        <div style={{ textAlign: 'center', padding: '40px 0', color: '#64748b' }}>
                            <div style={{ fontSize: '36px', marginBottom: '8px' }}>📭</div>
                            <div style={{ fontSize: '13px' }}>Bugün ex-dividend tarihi olan hisse bulunamadı.</div>
                        </div>
                    )}

                    {!loading && data && stocks.length > 0 && (
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{
                                width: '100%', borderCollapse: 'collapse', fontSize: '12px',
                            }}>
                                <thead>
                                    <tr style={{ borderBottom: '2px solid #1e2a3a' }}>
                                        <th style={thStyle}>Symbol</th>
                                        <th style={thStyle}>DIV AMOUNT</th>
                                        <th style={{ ...thStyle, color: '#fbbf24' }}>0.85 × DIV</th>
                                        <th style={thStyle}>Ex-Div Date</th>
                                        <th style={thStyle}>Kaynak</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {stocks.map((stock) => (
                                        <tr key={stock.symbol} style={{
                                            borderBottom: '1px solid #1a2535',
                                            transition: 'background 0.15s',
                                        }}
                                            onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(251,191,36,0.05)'}
                                            onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                                        >
                                            <td style={{ ...tdStyle, fontWeight: 700, color: '#e2e8f0', letterSpacing: '0.5px' }}>
                                                {stock.symbol}
                                            </td>
                                            <td style={{ ...tdStyle, color: '#94a3b8', fontFamily: 'monospace' }}>
                                                ${stock.div_amount?.toFixed(4)}
                                            </td>
                                            <td style={{
                                                ...tdStyle, color: '#fbbf24', fontWeight: 700,
                                                fontFamily: 'monospace', fontSize: '13px',
                                            }}>
                                                ${stock.adjusted_div?.toFixed(4)}
                                            </td>
                                            <td style={{ ...tdStyle, color: '#64748b', fontSize: '11px' }}>
                                                {stock.ex_div_date}
                                            </td>
                                            <td style={{ ...tdStyle, color: '#475569', fontSize: '10px' }}>
                                                {stock.source_file}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>

                            {/* Toplam */}
                            <div style={{
                                marginTop: '12px', padding: '10px 0',
                                borderTop: '1px solid #1e2a3a', display: 'flex',
                                justifyContent: 'space-between', fontSize: '11px', color: '#94a3b8',
                            }}>
                                <span>Toplam: {stocks.length} hisse</span>
                                <span style={{ fontFamily: 'monospace', color: '#fbbf24' }}>
                                    Σ 0.85×DIV = ${stocks.reduce((s, st) => s + (st.adjusted_div || 0), 0).toFixed(4)}
                                </span>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div style={{
                    padding: '10px 20px', borderTop: '1px solid #1e2a3a',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    fontSize: '10px', color: '#475569',
                    borderRadius: '0 0 12px 12px',
                }}>
                    <span>
                        Kaynak: exdiv_info.py → exdiv_today.json (günlük pipeline)
                    </span>
                    <button
                        onClick={fetchData}
                        disabled={loading}
                        style={{
                            background: 'rgba(251,191,36,0.1)', border: '1px solid rgba(251,191,36,0.25)',
                            borderRadius: '4px', padding: '4px 10px', color: '#fbbf24',
                            fontSize: '11px', cursor: loading ? 'not-allowed' : 'pointer',
                            opacity: loading ? 0.5 : 1,
                        }}
                    >
                        🔄 Yenile
                    </button>
                </div>
            </div>
        </div>
    );
}

const thStyle = {
    textAlign: 'left', padding: '8px 10px', color: '#64748b',
    fontWeight: 600, fontSize: '11px', textTransform: 'uppercase',
    letterSpacing: '0.5px', whiteSpace: 'nowrap',
};

const tdStyle = {
    padding: '8px 10px', whiteSpace: 'nowrap',
};

export default ExDivInfoModal;
