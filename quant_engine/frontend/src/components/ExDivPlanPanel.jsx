import React, { useState, useEffect } from 'react'

/**
 * ExDiv 30-Day Plan Panel
 * 
 * Her açıldığında GÜNCEL tarih ile çalışır:
 * - TOP 5 BUY: Bugün alım penceresi AÇIK olan en iyi 5 LONG
 * - TOP 5 SHORT: Bugün short penceresi AÇIK olan en iyi 5 SHORT
 * - Bu Hafta / Gelecek Hafta: Yaklaşan fırsatlar
 * - 30 günlük aksiyon takvimi
 */
const ExDivPlanPanel = ({ isOpen, onClose }) => {
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)
    const [longPct, setLongPct] = useState(50)
    const [longHeldPct, setLongHeldPct] = useState(100)
    const [shortHeldPct, setShortHeldPct] = useState(100)
    const [activeTab, setActiveTab] = useState('today') // today | week | calendar

    const fetchPlan = async () => {
        setLoading(true)
        setError(null)
        try {
            const res = await fetch(
                `/api/exdiv/plan30?long_pct=${longPct}&long_held_pct=${longHeldPct}&short_held_pct=${shortHeldPct}`
            )
            const json = await res.json()
            if (json.status === 'ok') {
                setData(json)
            } else {
                setError(json.message || 'Veri yok')
            }
        } catch (e) {
            setError(e.message)
        }
        setLoading(false)
    }

    // Her açılışta güncel veriyi çek
    useEffect(() => {
        if (isOpen) {
            fetchPlan()
        }
    }, [isOpen])

    if (!isOpen) return null

    const shortPct = 100 - longPct

    return (
        <div style={overlayStyle}>
            <div style={modalStyle}>
                {/* HEADER */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                    <div>
                        <h2 style={{ color: '#e2e8f0', margin: 0, fontSize: '20px' }}>
                            📅 Ex-Div Trading Planı
                        </h2>
                        {data && (
                            <span style={{ color: '#718096', fontSize: '12px' }}>
                                Tarih: {data.today} · {data.all_longs} long · {data.all_shorts} short aday
                            </span>
                        )}
                    </div>
                    <button onClick={onClose} style={closeBtnStyle}>✕ Kapat</button>
                </div>

                {/* CONFIG BAR */}
                <div style={configBarStyle}>
                    <ConfigInput label="Long %" value={longPct} onChange={v => setLongPct(v)} min={0} max={100} color="#48bb78" />
                    <span style={{ color: '#4a5568', fontSize: '12px', alignSelf: 'center' }}>/ Short {shortPct}%</span>
                    <ConfigInput label="L-Held" value={longHeldPct} onChange={v => setLongHeldPct(v)} min={1} max={100} color="#68d391" suffix="%" />
                    <ConfigInput label="S-Held" value={shortHeldPct} onChange={v => setShortHeldPct(v)} min={1} max={100} color="#feb2b2" suffix="%" />
                    <button onClick={fetchPlan} disabled={loading} style={{
                        ...updateBtnStyle,
                        background: loading ? '#4a5568' : '#4299e1',
                        cursor: loading ? 'wait' : 'pointer',
                    }}>
                        {loading ? '⏳...' : '🔄 Güncelle'}
                    </button>
                </div>

                {error && <div style={errorStyle}>{error}</div>}

                {data && (
                    <>
                        {/* ═══ BUGÜNÜN AKTİF SİNYALLERİ ═══ */}
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '16px' }}>

                            {/* TOP 5 BEST BUY — BUGÜN */}
                            <div style={buyBoxStyle}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                                    <h3 style={{ color: '#48bb78', margin: 0, fontSize: '15px' }}>
                                        🟢 TOP 5 BEST BUY
                                    </h3>
                                    <span style={badgeStyle(data.active_buy_count > 0 ? '#276749' : '#4a5568')}>
                                        {data.active_buy_count > 0 ? `🔥 ${data.active_buy_count} aktif` : 'Bugün sinyal yok'}
                                    </span>
                                </div>
                                {data.top5_buy?.length > 0 ? (
                                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                        <thead>
                                            <tr style={{ borderBottom: '1px solid #276749' }}>
                                                <th style={thStyle}>Ticker</th>
                                                <th style={thStyle}>Strateji</th>
                                                <th style={thStyle}>Entry</th>
                                                <th style={thStyle}>ExDiv</th>
                                                <th style={thStyle}>Ret%</th>
                                                <th style={thStyle}>Win%</th>
                                                <th style={thStyle}>Sharpe</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {data.top5_buy.map((t, i) => (
                                                <tr key={i} style={{ borderBottom: '1px solid #1a202c', background: t.signal === 'BUY_NOW' ? '#1c3a1c' : 'transparent' }}>
                                                    <td style={{ ...tdStyle, color: '#48bb78', fontWeight: 'bold' }}>
                                                        {t.signal === 'BUY_NOW' && '⚡'}{t.ticker}
                                                    </td>
                                                    <td style={{ ...tdStyle, color: '#a0aec0', fontSize: '10px' }}>{t.strategy}</td>
                                                    <td style={{ ...tdStyle, color: '#e2e8f0' }}>{t.entry_date?.slice(5)}</td>
                                                    <td style={{ ...tdStyle, color: '#718096', fontSize: '10px' }}>{t.exdiv_date?.slice(5)}</td>
                                                    <td style={{ ...tdStyle, color: '#48bb78', fontWeight: 'bold' }}>+{t.expected_return?.toFixed(2)}%</td>
                                                    <td style={tdStyle}>{t.win_rate ? (t.win_rate * 100).toFixed(0) + '%' : '-'}</td>
                                                    <td style={{ ...tdStyle, color: t.sharpe > 5 ? '#ffd700' : '#e2e8f0', fontWeight: 'bold' }}>{t.sharpe?.toFixed(1)}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                ) : (
                                    <div style={{ color: '#718096', textAlign: 'center', padding: '20px', fontSize: '13px' }}>
                                        Bugün long entry penceresi açık hisse yok.
                                        <br />Bu hafta {(data.this_week_buys?.length || 0)} fırsat var →
                                    </div>
                                )}
                            </div>

                            {/* TOP 5 BEST SHORT — BUGÜN */}
                            <div style={shortBoxStyle}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                                    <h3 style={{ color: '#fc8181', margin: 0, fontSize: '15px' }}>
                                        🔴 TOP 5 BEST SHORT
                                    </h3>
                                    <span style={badgeStyle(data.active_short_count > 0 ? '#9b2c2c' : '#4a5568')}>
                                        {data.active_short_count > 0 ? `🔥 ${data.active_short_count} aktif` : 'Bugün sinyal yok'}
                                    </span>
                                </div>
                                {data.top5_sell?.length > 0 ? (
                                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                        <thead>
                                            <tr style={{ borderBottom: '1px solid #9b2c2c' }}>
                                                <th style={thStyle}>Ticker</th>
                                                <th style={thStyle}>Strateji</th>
                                                <th style={thStyle}>Entry</th>
                                                <th style={thStyle}>ExDiv</th>
                                                <th style={thStyle}>Ret%</th>
                                                <th style={thStyle}>Sharpe</th>
                                                <th style={thStyle}>Yield</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {data.top5_sell.map((t, i) => (
                                                <tr key={i} style={{ borderBottom: '1px solid #1a202c', background: t.signal === 'SHORT_NOW' ? '#3a1c1c' : 'transparent' }}>
                                                    <td style={{ ...tdStyle, color: '#fc8181', fontWeight: 'bold' }}>
                                                        {t.signal === 'SHORT_NOW' && '⚡'}{t.ticker}
                                                    </td>
                                                    <td style={{ ...tdStyle, color: '#a0aec0', fontSize: '10px' }}>{t.strategy}</td>
                                                    <td style={{ ...tdStyle, color: '#e2e8f0' }}>{t.entry_date?.slice(5)}</td>
                                                    <td style={{ ...tdStyle, color: '#718096', fontSize: '10px' }}>{t.exdiv_date?.slice(5)}</td>
                                                    <td style={{ ...tdStyle, color: '#fc8181', fontWeight: 'bold' }}>+{t.expected_return?.toFixed(2)}%</td>
                                                    <td style={{ ...tdStyle, color: t.sharpe > 1.5 ? '#ffd700' : '#e2e8f0', fontWeight: 'bold' }}>{t.sharpe?.toFixed(1)}</td>
                                                    <td style={tdStyle}>{t.yield_pct?.toFixed(1)}%</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                ) : (
                                    <div style={{ color: '#718096', textAlign: 'center', padding: '20px', fontSize: '13px' }}>
                                        Bugün short entry penceresi açık hisse yok.
                                        <br />Bu hafta {(data.this_week_shorts?.length || 0)} fırsat var →
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* ═══ BUGÜNÜN AKSİYONLARI ═══ */}
                        {data.today_actions?.length > 0 && (
                            <div style={{ background: '#2d3748', borderRadius: '10px', padding: '12px 16px', marginBottom: '14px', border: '1px solid #4a5568' }}>
                                <h4 style={{ color: '#ffd700', margin: '0 0 8px 0', fontSize: '14px' }}>
                                    ⚡ BUGÜN YAPILACAKLAR ({data.today})
                                </h4>
                                {data.today_actions.map((a, i) => {
                                    const emoji = a.action === 'BUY' ? '🟢' : a.action === 'SHORT' ? '🔴' : a.action === 'SELL' ? '📤' : '📥'
                                    const color = a.action === 'BUY' ? '#48bb78' : a.action === 'SHORT' ? '#fc8181' : '#a0aec0'
                                    return (
                                        <div key={i} style={{ display: 'flex', gap: '10px', alignItems: 'center', padding: '3px 0', fontSize: '13px' }}>
                                            <span>{emoji}</span>
                                            <span style={{ color, fontWeight: 'bold', minWidth: '55px' }}>{a.action}</span>
                                            <span style={{ color: '#e2e8f0', fontWeight: 'bold', minWidth: '100px' }}>{a.ticker}</span>
                                            <span style={{ color: '#718096', fontSize: '11px' }}>[{a.strategy}]</span>
                                            <span style={{ color: '#48bb78', marginLeft: 'auto' }}>ret={a.expected_return > 0 ? '+' : ''}{a.expected_return?.toFixed(2)}%</span>
                                        </div>
                                    )
                                })}
                            </div>
                        )}

                        {/* ═══ TAB NAVIGATION ═══ */}
                        <div style={{ display: 'flex', gap: '4px', marginBottom: '12px' }}>
                            {[
                                { id: 'week', label: '📆 Bu Hafta / Gelecek Hafta' },
                                { id: 'portfolio', label: '📊 Portföy' },
                                { id: 'calendar', label: '📋 30 Gün Takvim' },
                            ].map(tab => (
                                <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                                    style={{
                                        padding: '6px 14px', borderRadius: '6px', border: 'none', cursor: 'pointer',
                                        fontSize: '12px', fontWeight: 'bold',
                                        background: activeTab === tab.id ? '#4299e1' : '#2d3748',
                                        color: activeTab === tab.id ? '#fff' : '#a0aec0',
                                    }}
                                >{tab.label}</button>
                            ))}
                        </div>

                        {/* ═══ TAB: BU HAFTA / GELECEK HAFTA ═══ */}
                        {activeTab === 'week' && (
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
                                {/* Bu Hafta */}
                                <div>
                                    <h4 style={{ color: '#63b3ed', margin: '0 0 8px 0', fontSize: '14px' }}>📆 Bu Hafta</h4>
                                    <WeekList buys={data.this_week_buys} shorts={data.this_week_shorts} />
                                </div>
                                {/* Gelecek Hafta */}
                                <div>
                                    <h4 style={{ color: '#a78bfa', margin: '0 0 8px 0', fontSize: '14px' }}>📆 Gelecek Hafta</h4>
                                    <WeekList buys={data.next_week_buys} shorts={data.next_week_shorts} />
                                </div>
                            </div>
                        )}

                        {/* ═══ TAB: PORTFÖY ═══ */}
                        {activeTab === 'portfolio' && (
                            <>
                                {/* Stats Row */}
                                <div style={{ display: 'flex', gap: '10px', marginBottom: '14px', flexWrap: 'wrap' }}>
                                    <StatBox label="Long Seçilen" value={data.selected_longs?.length || 0} color="#48bb78" />
                                    <StatBox label="Short Seçilen" value={data.selected_shorts?.length || 0} color="#fc8181" />
                                    <StatBox label="Long Held" value={data.held_long_count || 0} color="#68d391" />
                                    <StatBox label="Short Held" value={data.held_short_count || 0} color="#feb2b2" />
                                </div>

                                {/* Selected Longs */}
                                <details open style={{ marginBottom: '14px' }}>
                                    <summary style={{ color: '#48bb78', cursor: 'pointer', fontSize: '14px', fontWeight: 'bold' }}>
                                        📗 Long Pozisyonlar ({data.selected_longs?.length || 0})
                                    </summary>
                                    <div style={{ overflowX: 'auto', marginTop: '6px' }}>
                                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                            <thead>
                                                <tr style={{ borderBottom: '1px solid #2d3748' }}>
                                                    {['#', 'Ticker', 'Strateji', 'Entry', 'Exit', 'ExDiv', 'D', 'Ret%', 'Win', 'Shrp', 'Yld'].map(h =>
                                                        <th key={h} style={thStyle}>{h}</th>
                                                    )}
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {(data.selected_longs || []).map((t, i) => (
                                                    <tr key={i} style={{
                                                        borderBottom: '1px solid #1a202c',
                                                        background: i < (data.held_long_count || 0) ? '#1c2a1c' : 'transparent',
                                                    }}>
                                                        <td style={tdStyle}>{i + 1}</td>
                                                        <td style={{ ...tdStyle, color: '#48bb78', fontWeight: 'bold' }}>
                                                            {t.signal === 'BUY_NOW' && '⚡'}{t.ticker}
                                                        </td>
                                                        <td style={{ ...tdStyle, fontSize: '10px', color: '#a0aec0' }}>{t.strategy}</td>
                                                        <td style={{ ...tdStyle, color: '#e2e8f0' }}>{t.entry_date}</td>
                                                        <td style={{ ...tdStyle, color: '#e2e8f0' }}>{t.exit_date}</td>
                                                        <td style={{ ...tdStyle, color: '#718096' }}>{t.exdiv_date}</td>
                                                        <td style={tdStyle}>{t.holding_days}d</td>
                                                        <td style={{ ...tdStyle, color: '#48bb78', fontWeight: 'bold' }}>+{t.expected_return?.toFixed(2)}%</td>
                                                        <td style={tdStyle}>{t.win_rate ? (t.win_rate * 100).toFixed(0) + '%' : '-'}</td>
                                                        <td style={{ ...tdStyle, color: t.sharpe > 5 ? '#ffd700' : '#e2e8f0' }}>{t.sharpe?.toFixed(1)}</td>
                                                        <td style={tdStyle}>{t.yield_pct?.toFixed(1)}%</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </details>

                                {/* Selected Shorts */}
                                <details style={{ marginBottom: '14px' }}>
                                    <summary style={{ color: '#fc8181', cursor: 'pointer', fontSize: '14px', fontWeight: 'bold' }}>
                                        📕 Short Pozisyonlar ({data.selected_shorts?.length || 0})
                                    </summary>
                                    <div style={{ overflowX: 'auto', marginTop: '6px' }}>
                                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                            <thead>
                                                <tr style={{ borderBottom: '1px solid #2d3748' }}>
                                                    {['#', 'Ticker', 'Strateji', 'Entry', 'Cover', 'ExDiv', 'D', 'Ret%', 'Shrp', 'Yld'].map(h =>
                                                        <th key={h} style={thStyle}>{h}</th>
                                                    )}
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {(data.selected_shorts || []).map((t, i) => (
                                                    <tr key={i} style={{
                                                        borderBottom: '1px solid #1a202c',
                                                        background: i < (data.held_short_count || 0) ? '#2a1c1c' : 'transparent',
                                                    }}>
                                                        <td style={tdStyle}>{i + 1}</td>
                                                        <td style={{ ...tdStyle, color: '#fc8181', fontWeight: 'bold' }}>
                                                            {t.signal === 'SHORT_NOW' && '⚡'}{t.ticker}
                                                        </td>
                                                        <td style={{ ...tdStyle, fontSize: '10px', color: '#a0aec0' }}>{t.strategy}</td>
                                                        <td style={{ ...tdStyle, color: '#e2e8f0' }}>{t.entry_date}</td>
                                                        <td style={{ ...tdStyle, color: '#e2e8f0' }}>{t.exit_date}</td>
                                                        <td style={{ ...tdStyle, color: '#718096' }}>{t.exdiv_date}</td>
                                                        <td style={tdStyle}>{t.holding_days}d</td>
                                                        <td style={{ ...tdStyle, color: '#fc8181', fontWeight: 'bold' }}>+{t.expected_return?.toFixed(2)}%</td>
                                                        <td style={{ ...tdStyle, color: t.sharpe > 1.5 ? '#ffd700' : '#e2e8f0' }}>{t.sharpe?.toFixed(1)}</td>
                                                        <td style={tdStyle}>{t.yield_pct?.toFixed(1)}%</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </details>
                            </>
                        )}

                        {/* ═══ TAB: GÜNLÜK TAKVİM ═══ */}
                        {activeTab === 'calendar' && (
                            <div style={{ maxHeight: '450px', overflow: 'auto' }}>
                                {(() => {
                                    const grouped = {}
                                        ; (data.daily_actions || []).forEach(a => {
                                            if (!grouped[a.date]) grouped[a.date] = []
                                            grouped[a.date].push(a)
                                        })
                                    return Object.entries(grouped).map(([date, acts]) => {
                                        const isToday = date === data.today
                                        return (
                                            <div key={date} style={{ marginBottom: '10px' }}>
                                                <div style={{
                                                    color: isToday ? '#ffd700' : '#a0aec0', fontSize: '13px', fontWeight: 'bold',
                                                    borderBottom: `1px solid ${isToday ? '#ffd700' : '#2d3748'}`, paddingBottom: '3px', marginBottom: '4px',
                                                }}>
                                                    {isToday ? '⚡ ' : '📌 '}{date} ({new Date(date + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'short' })})
                                                    {isToday && ' — BUGÜN'}
                                                </div>
                                                {acts.map((a, i) => {
                                                    const emoji = a.action === 'BUY' ? '🟢' : a.action === 'SHORT' ? '🔴' : a.action === 'SELL' ? '📤' : '📥'
                                                    const color = a.action === 'BUY' ? '#48bb78' : a.action === 'SHORT' ? '#fc8181' : '#a0aec0'
                                                    return (
                                                        <div key={i} style={{ display: 'flex', gap: '8px', alignItems: 'center', padding: '2px 8px', fontSize: '12px' }}>
                                                            <span>{emoji}</span>
                                                            <span style={{ color, fontWeight: 'bold', minWidth: '50px' }}>{a.action}</span>
                                                            <span style={{ color: '#e2e8f0', minWidth: '95px', fontWeight: 'bold' }}>{a.ticker}</span>
                                                            <span style={{ color: '#718096', fontSize: '10px' }}>[{a.strategy}]</span>
                                                            <span style={{ color: '#48bb78', marginLeft: 'auto', fontSize: '11px' }}>
                                                                ret={a.expected_return > 0 ? '+' : ''}{a.expected_return?.toFixed(2)}%
                                                            </span>
                                                            <span style={{ color: '#a0aec0', fontSize: '11px' }}>shrp={a.sharpe?.toFixed(1)}</span>
                                                        </div>
                                                    )
                                                })}
                                            </div>
                                        )
                                    })
                                })()}
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    )
}

// ═══ SUB-COMPONENTS ═══

const WeekList = ({ buys, shorts }) => (
    <div>
        {buys?.length > 0 && (
            <div style={{ marginBottom: '8px' }}>
                <div style={{ color: '#48bb78', fontSize: '12px', fontWeight: 'bold', marginBottom: '4px' }}>Long Fırsatlar:</div>
                {buys.map((t, i) => (
                    <div key={i} style={{ display: 'flex', gap: '6px', fontSize: '12px', padding: '2px 0', alignItems: 'center' }}>
                        <span style={{ color: '#48bb78', fontWeight: 'bold', minWidth: '80px' }}>{t.ticker}</span>
                        <span style={{ color: '#718096', fontSize: '10px', minWidth: '60px' }}>{t.entry_date?.slice(5)}</span>
                        <span style={{ color: '#48bb78' }}>+{t.expected_return?.toFixed(2)}%</span>
                        <span style={{ color: '#a0aec0', fontSize: '10px' }}>shrp={t.sharpe?.toFixed(1)}</span>
                        {t.days_to_entry != null && (
                            <span style={{ color: '#ffd700', fontSize: '10px', marginLeft: 'auto' }}>{t.days_to_entry}d</span>
                        )}
                    </div>
                ))}
            </div>
        )}
        {shorts?.length > 0 && (
            <div>
                <div style={{ color: '#fc8181', fontSize: '12px', fontWeight: 'bold', marginBottom: '4px' }}>Short Fırsatlar:</div>
                {shorts.map((t, i) => (
                    <div key={i} style={{ display: 'flex', gap: '6px', fontSize: '12px', padding: '2px 0', alignItems: 'center' }}>
                        <span style={{ color: '#fc8181', fontWeight: 'bold', minWidth: '80px' }}>{t.ticker}</span>
                        <span style={{ color: '#718096', fontSize: '10px', minWidth: '60px' }}>{t.entry_date?.slice(5)}</span>
                        <span style={{ color: '#fc8181' }}>+{t.expected_return?.toFixed(2)}%</span>
                        <span style={{ color: '#a0aec0', fontSize: '10px' }}>shrp={t.sharpe?.toFixed(1)}</span>
                        {t.days_to_entry != null && (
                            <span style={{ color: '#ffd700', fontSize: '10px', marginLeft: 'auto' }}>{t.days_to_entry}d</span>
                        )}
                    </div>
                ))}
            </div>
        )}
        {(!buys?.length && !shorts?.length) && (
            <div style={{ color: '#4a5568', fontSize: '12px', textAlign: 'center', padding: '12px' }}>Bu dönem sinyal yok</div>
        )}
    </div>
)

const ConfigInput = ({ label, value, onChange, min, max, color, suffix }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        <label style={{ color: '#a0aec0', fontSize: '12px' }}>{label}:</label>
        <input type="number" min={min} max={max} value={value}
            onChange={e => onChange(Math.max(min, Math.min(max, parseInt(e.target.value) || min)))}
            style={{
                width: '50px', background: '#1a1f2e', border: '1px solid #4a5568', borderRadius: '5px',
                color, padding: '3px 6px', fontSize: '13px', textAlign: 'center'
            }}
        />
        {suffix && <span style={{ color: '#718096', fontSize: '11px' }}>{suffix}</span>}
    </div>
)

const StatBox = ({ label, value, color }) => (
    <div style={{
        background: '#2d3748', borderRadius: '8px', padding: '6px 14px',
        display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: '70px',
    }}>
        <span style={{ color: '#718096', fontSize: '10px' }}>{label}</span>
        <span style={{ color, fontSize: '18px', fontWeight: 'bold' }}>{value}</span>
    </div>
)

// ═══ STYLES ═══

const overlayStyle = {
    position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
    backgroundColor: 'rgba(0,0,0,0.85)', zIndex: 3000,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
}

const modalStyle = {
    background: '#1a1f2e', borderRadius: '14px', width: '94%', maxWidth: '1200px',
    maxHeight: '92vh', overflow: 'auto', padding: '20px',
    border: '1px solid #2d3748', boxShadow: '0 25px 50px -12px rgba(0,0,0,0.5)',
}

const closeBtnStyle = {
    background: '#e53e3e', color: '#fff', border: 'none', borderRadius: '6px',
    padding: '5px 14px', cursor: 'pointer', fontWeight: 'bold', fontSize: '13px',
}

const configBarStyle = {
    display: 'flex', gap: '14px', alignItems: 'center', marginBottom: '16px',
    background: '#2d3748', padding: '10px 14px', borderRadius: '8px', flexWrap: 'wrap',
}

const updateBtnStyle = {
    color: '#fff', border: 'none', borderRadius: '6px',
    padding: '5px 16px', fontWeight: 'bold', fontSize: '12px',
}

const errorStyle = {
    background: '#742a2a', color: '#fed7d7', padding: '10px', borderRadius: '8px', marginBottom: '14px', fontSize: '13px',
}

const buyBoxStyle = {
    background: '#1c2a1c', borderRadius: '10px', padding: '14px', border: '1px solid #276749',
}

const shortBoxStyle = {
    background: '#2a1c1c', borderRadius: '10px', padding: '14px', border: '1px solid #9b2c2c',
}

const badgeStyle = (bg) => ({
    background: bg, padding: '2px 8px', borderRadius: '10px', fontSize: '10px', color: '#e2e8f0',
})

const thStyle = { textAlign: 'left', padding: '5px 6px', color: '#a0aec0', fontSize: '10px', fontWeight: '600', whiteSpace: 'nowrap' }
const tdStyle = { padding: '4px 6px', color: '#e2e8f0', fontSize: '12px', whiteSpace: 'nowrap' }

export default ExDivPlanPanel
