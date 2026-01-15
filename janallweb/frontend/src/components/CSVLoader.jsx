import React, { useState, useEffect } from 'react'
import api from '../services/api'
import toast from 'react-hot-toast'

const CSVLoader = ({ onLoad, loading }) => {
  const [csvFiles, setCsvFiles] = useState([])
  const [selectedFile, setSelectedFile] = useState('janalldata.csv')
  const [fetchingFiles, setFetchingFiles] = useState(false)

  useEffect(() => {
    fetchCSVFiles()
  }, [])

  const fetchCSVFiles = async () => {
    setFetchingFiles(true)
    try {
      const response = await api.get('/csv/list')
      if (response.data.success) {
        setCsvFiles(response.data.files || [])
      }
    } catch (error) {
      console.error('CSV dosyaları alınamadı:', error)
    } finally {
      setFetchingFiles(false)
    }
  }

  const handleLoad = () => {
    if (selectedFile) {
      onLoad(selectedFile)
    }
  }

  return (
    <div className="flex items-center space-x-4">
      <select
        value={selectedFile}
        onChange={(e) => setSelectedFile(e.target.value)}
        className="px-4 py-2 border border-gray-300 rounded-md"
        disabled={fetchingFiles || loading}
      >
        {csvFiles.length === 0 && (
          <option value="janalldata.csv">janalldata.csv</option>
        )}
        {csvFiles.map((file) => (
          <option key={file} value={file}>
            {file}
          </option>
        ))}
      </select>

      <button
        onClick={handleLoad}
        disabled={loading || fetchingFiles}
        className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:opacity-50"
      >
        {loading ? 'Yükleniyor...' : 'CSV Yükle'}
      </button>

      <button
        onClick={fetchCSVFiles}
        disabled={fetchingFiles}
        className="px-4 py-2 bg-gray-500 text-white rounded-md hover:bg-gray-600 disabled:opacity-50"
      >
        {fetchingFiles ? 'Yenileniyor...' : 'Yenile'}
      </button>
    </div>
  )
}

export default CSVLoader

