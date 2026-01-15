import React, { useState, useEffect } from 'react'
import './RejectedCandidates.css'

const RejectedCandidates = ({ isOpen, onClose }) => {
    const [rejections, setRejections] = useState([])
    const [loading, setLoading] = useState(false)
    const [autoRefresh, setAutoRefresh] = useState(true)

    const fetchRejections = async () => {
        try {
            setLoading(true)
            const res = await fetch('/api/psfalgo/rejected?limit=50')
            const data = await res.json()
            if (data.success) {
                setRejections(data.rejections || [])
            }
        } catch (err) {
            console.error("Error fetching rejections:", err)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        if (isOpen) {
            fetchRejections()
            const interval = setInterval(() => {
                if (autoRefresh) fetchRejections()
            }, 5000)
            return () => clearInterval(interval)
        }
    }, [isOpen, autoRefresh])

    if (!isOpen) return null

    return (
        <div className="rejected-overlay">
            <div className="rejected-panel">
                <div className="rejected-header">
                    <h3>🚫 Rejected Candidates (Shadow Visibility)</h3>
                    <div className="rejected-controls">
                        <label>
                            <input
                                type="checkbox"
                                checked={autoRefresh}
                                onChange={e => setAutoRefresh(e.target.checked)}
                            /> Auto-Refresh
                        </label>
                        <button onClick={fetchRejections}>Refresh</button>
                        <button className="close-btn" onClick={onClose}>×</button>
                    </div>
                </div>

                <div className="rejected-content">
                    {rejections.length === 0 ? (
                        <div className="no-data">No rejected candidates found log is empty.</div>
                    ) : (
                        <table>
                            <thead>
                                <tr>
                                    <th>Time</th>
                                    <th>Symbol</th>
                                    <th>Reason Code</th>
                                    <th>Details</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rejections.map((item, idx) => (
                                    <tr key={idx} className="rejected-row">
                                        <td>{new Date(item.timestamp).toLocaleTimeString()}</td>
                                        <td className="symbol-cell">{item.symbol}</td>
                                        <td><span className="reason-poo">{item.code}</span></td>
                                        <td className="details-cell">
                                            {item.details ? Object.entries(item.details).map(([k, v]) => (
                                                <span key={k} className="detail-tag">{k}: {Number(v).toFixed(2)}</span>
                                            )) : '-'}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            </div>
        </div>
    )
}

export default RejectedCandidates
