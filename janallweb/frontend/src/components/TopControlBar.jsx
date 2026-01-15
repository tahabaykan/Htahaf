import React, { useState, useEffect } from 'react'
import { useData } from '../contexts/DataContext'
import api from '../services/api'
import toast from 'react-hot-toast'

const TopControlBar = ({ onLiveDataToggle, onMini450Toggle, isMini450Active }) => {
  const { connectionStatus, connectHammer, disconnectHammer, fetchConnectionStatus } = useData()
  const [connecting, setConnecting] = useState(false)
  const [liveDataRunning, setLiveDataRunning] = useState(false)

  // Connection status'u periyodik olarak güncelle
  useEffect(() => {
    const interval = setInterval(() => {
      fetchConnectionStatus()
    }, 5000) // 5 saniyede bir güncelle

    return () => clearInterval(interval)
  }, [fetchConnectionStatus])

  const handleConnectHammer = async () => {
    if (connectionStatus.hammer) {
      // Bağlantıyı kes
      try {
        setConnecting(true)
        const result = await disconnectHammer()
        if (result.success) {
          toast.success('Hammer Pro bağlantısı kesildi')
        } else {
          toast.error('Bağlantı kesilemedi: ' + (result.error || 'Bilinmeyen hata'))
        }
      } catch (error) {
        toast.error('Bağlantı kesilemedi: ' + error.message)
      } finally {
        setConnecting(false)
      }
    } else {
      // Bağlan
      try {
        setConnecting(true)
        const result = await connectHammer('127.0.0.1', 16400, 'Nl201090.')
        if (result.success) {
          toast.success('Hammer Pro\'ya bağlanıldı')
        } else {
          toast.error('Bağlantı başarısız: ' + (result.error || 'Bilinmeyen hata'))
        }
      } catch (error) {
        toast.error('Bağlantı hatası: ' + error.message)
      } finally {
        setConnecting(false)
      }
    }
  }

  const handleToggleLiveData = async () => {
    try {
      setLiveDataRunning(!liveDataRunning)
      if (onLiveDataToggle) {
        onLiveDataToggle(!liveDataRunning)
      }
      toast.success(liveDataRunning ? 'Live Data durduruldu' : 'Live Data başlatıldı')
    } catch (error) {
      toast.error('Live Data hatası: ' + error.message)
      setLiveDataRunning(false)
    }
  }


  const handleMini450 = () => {
    if (onMini450Toggle) {
      onMini450Toggle(!isMini450Active)
    }
  }

  return (
    <div className="bg-white rounded-lg shadow p-4 mb-4">
      <div className="flex flex-wrap items-center gap-2">
        {/* Sol taraf - Bağlantı butonları */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleConnectHammer}
            disabled={connecting}
            className={`px-4 py-2 rounded-md text-sm font-medium ${
              connectionStatus.hammer
                ? 'bg-red-500 text-white hover:bg-red-600'
                : 'bg-green-500 text-white hover:bg-green-600'
            } disabled:opacity-50`}
          >
            {connecting
              ? 'Bağlanıyor...'
              : connectionStatus.hammer
              ? "Bağlantıyı Kes"
              : "Hammer Pro'ya Bağlan"}
          </button>

          <button
            onClick={handleToggleLiveData}
            disabled={!connectionStatus.hammer}
            className={`px-4 py-2 rounded-md text-sm font-medium ${
              liveDataRunning
                ? 'bg-yellow-500 text-white hover:bg-yellow-600'
                : 'bg-blue-500 text-white hover:bg-blue-600'
            } disabled:opacity-50`}
          >
            {liveDataRunning ? 'Live Data Durdur' : 'Live Data Başlat'}
          </button>

          <button
            onClick={handleMini450}
            className={`px-4 py-2 rounded-md text-sm font-medium ${
              isMini450Active
                ? 'bg-purple-500 text-white hover:bg-purple-600'
                : 'bg-gray-500 text-white hover:bg-gray-600'
            }`}
          >
            {isMini450Active ? 'Normal Görünüm' : 'Mini450'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default TopControlBar

