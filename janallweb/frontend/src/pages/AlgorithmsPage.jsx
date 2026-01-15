import React, { useState, useEffect } from 'react'
import { useData } from '../contexts/DataContext'
import api from '../services/api'
import toast from 'react-hot-toast'

const AlgorithmsPage = () => {
  const [algorithms, setAlgorithms] = useState([])
  const [selectedAlgorithm, setSelectedAlgorithm] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetchAlgorithms()
  }, [])

  const fetchAlgorithms = async () => {
    setLoading(true)
    try {
      const response = await api.get('/algorithms')
      if (response.data.success) {
        setAlgorithms(response.data.algorithms || [])
      }
    } catch (error) {
      toast.error('Algoritmalar yüklenemedi: ' + error.message)
    } finally {
      setLoading(false)
    }
  }

  const handleRunAlgorithm = async () => {
    if (!selectedAlgorithm) {
      toast.error('Algoritma seçin')
      return
    }

    setRunning(true)
    setResult(null)
    
    try {
      const response = await api.post('/algorithms/run', {
        algorithm_name: selectedAlgorithm,
        parameters: {}
      })

      if (response.data.success) {
        setResult(response.data.result)
        toast.success('Algoritma başarıyla çalıştırıldı')
      } else {
        toast.error(response.data.error || 'Algoritma çalıştırılamadı')
        setResult(response.data)
      }
    } catch (error) {
      toast.error('Algoritma çalıştırma hatası: ' + error.message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="max-w-7xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-4">Algoritmalar</h2>
      
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="flex items-center space-x-4 mb-4">
          <select
            value={selectedAlgorithm}
            onChange={(e) => setSelectedAlgorithm(e.target.value)}
            className="px-4 py-2 border border-gray-300 rounded-md flex-1"
            disabled={loading || running}
          >
            <option value="">Algoritma Seçin...</option>
            {algorithms.map((algo) => (
              <option key={algo} value={algo}>
                {algo}
              </option>
            ))}
          </select>

          <button
            onClick={handleRunAlgorithm}
            disabled={!selectedAlgorithm || running || loading}
            className="px-6 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:opacity-50"
          >
            {running ? 'Çalıştırılıyor...' : 'Çalıştır'}
          </button>

          <button
            onClick={fetchAlgorithms}
            disabled={loading}
            className="px-4 py-2 bg-gray-500 text-white rounded-md hover:bg-gray-600 disabled:opacity-50"
          >
            {loading ? 'Yükleniyor...' : 'Yenile'}
          </button>
        </div>

        {loading && (
          <p className="text-gray-500">Algoritmalar yükleniyor...</p>
        )}

        {!loading && algorithms.length === 0 && (
          <p className="text-gray-500">Algoritma bulunamadı</p>
        )}
      </div>

      {result && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold mb-4">Sonuç</h3>
          <pre className="bg-gray-100 p-4 rounded-md overflow-auto max-h-96">
            {JSON.stringify(result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

export default AlgorithmsPage









