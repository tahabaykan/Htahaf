
import React, { useState, useEffect } from 'react';

const BenchmarkFillsPanel = () => {
    const [fills, setFills] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [lastUpdated, setLastUpdated] = useState(null);

    const fetchFills = async () => {
        try {
            const response = await fetch('http://localhost:8000/api/benchmark/fills');
            const data = await response.json();

            if (data.success) {
                setFills(data.fills);
                setError(null);
                setLastUpdated(new Date());
            } else {
                setError(data.message || 'Failed to fetch fills');
            }
        } catch (err) {
            console.error(err);
            setError('Connection error');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchFills();
        const interval = setInterval(fetchFills, 5000); // Poll every 5s
        return () => clearInterval(interval);
    }, []);

    const formatTime = (isoString) => {
        if (!isoString) return '-';
        return new Date(isoString).toLocaleTimeString();
    };

    return (
        <div className="p-4 bg-gray-900 text-white min-h-screen">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-2xl font-bold text-blue-400">Benchmark Fills Monitor</h1>
                <div className="text-sm text-gray-400">
                    Last Updated: {lastUpdated ? lastUpdated.toLocaleTimeString() : '-'}
                    <button
                        onClick={fetchFills}
                        className="ml-4 px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-xs"
                    >
                        Refresh
                    </button>
                </div>
            </div>

            {error && (
                <div className="bg-red-900/50 border border-red-500 text-red-200 p-3 rounded mb-4">
                    {error}
                </div>
            )}

            <div className="overflow-x-auto">
                <table className="min-w-full bg-gray-800 rounded-lg overflow-hidden">
                    <thead className="bg-gray-700">
                        <tr>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">Time</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">Fill Time</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">Symbol</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">Side</th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-gray-300 uppercase tracking-wider">Qty</th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-gray-300 uppercase tracking-wider">Price</th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-blue-400 uppercase tracking-wider">Group Avg (Bench)</th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-gray-300 uppercase tracking-wider">Diff %</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">Source</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">Account</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-700">
                        {loading && fills.length === 0 ? (
                            <tr><td colSpan="10" className="px-4 py-8 text-center text-gray-500">Loading...</td></tr>
                        ) : fills.length === 0 ? (
                            <tr><td colSpan="10" className="px-4 py-8 text-center text-gray-500">No fills found today.</td></tr>
                        ) : (
                            fills.map((fill, idx) => (
                                <tr key={idx} className="hover:bg-gray-750">
                                    <td className="px-4 py-2 whitespace-nowrap text-xs text-gray-400">{formatTime(fill.timestamp)}</td>
                                    <td className="px-4 py-2 whitespace-nowrap text-xs text-gray-300">{formatTime(fill.fill_time)}</td>
                                    <td className="px-4 py-2 whitespace-nowrap text-sm font-bold text-yellow-400">{fill.symbol}</td>
                                    <td className={`px-4 py-2 whitespace-nowrap text-xs font-bold ${fill.action === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>
                                        {fill.action}
                                    </td>
                                    <td className="px-4 py-2 whitespace-nowrap text-xs text-right text-gray-300">{fill.qty}</td>
                                    <td className="px-4 py-2 whitespace-nowrap text-sm text-right font-mono text-white">{parseFloat(fill.price).toFixed(2)}</td>
                                    <td className="px-4 py-2 whitespace-nowrap text-sm text-right font-mono text-blue-300">
                                        {fill.bench_price ? parseFloat(fill.bench_price).toFixed(2) : '-'}
                                    </td>
                                    <td className={`px-4 py-2 whitespace-nowrap text-xs text-right font-bold ${parseFloat(fill.diff_pct) > 0 ? 'text-green-400' : parseFloat(fill.diff_pct) < 0 ? 'text-red-400' : 'text-gray-400'
                                        }`}>
                                        {fill.diff_pct ? `${fill.diff_pct}%` : '-'}
                                    </td>
                                    <td className="px-4 py-2 whitespace-nowrap text-xs text-gray-500 truncate max-w-[150px]" title={fill.bench_source}>
                                        {fill.bench_source}
                                    </td>
                                    <td className="px-4 py-2 whitespace-nowrap text-xs text-gray-400">{fill.account}</td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default BenchmarkFillsPanel;
