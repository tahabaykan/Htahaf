import React, { useState } from 'react'
import api from '../services/api'
import toast from 'react-hot-toast'

const ModeSelector = ({ currentMode, onModeChange }) => {
  const [changing, setChanging] = useState(false)

  const handleModeChange = async (mode) => {
    try {
      setChanging(true)
      const response = await api.post('/mode/set', { mode })
      if (response.data.success) {
        if (onModeChange) {
          onModeChange(mode)
        }
        toast.success(`Mod değiştirildi: ${mode}`)
      } else {
        toast.error('Mod değiştirilemedi: ' + (response.data.error || 'Bilinmeyen hata'))
      }
    } catch (error) {
      toast.error('Mod hatası: ' + error.message)
    } finally {
      setChanging(false)
    }
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => handleModeChange('HAMPRO')}
        disabled={changing}
        className={`px-4 py-2 rounded-md text-sm font-medium ${
          currentMode === 'HAMPRO'
            ? 'bg-blue-600 text-white'
            : 'bg-gray-300 text-gray-700 hover:bg-gray-400'
        } disabled:opacity-50`}
      >
        HAMPRO MOD
      </button>
      <button
        onClick={() => handleModeChange('IBKR_GUN')}
        disabled={changing}
        className={`px-4 py-2 rounded-md text-sm font-medium ${
          currentMode === 'IBKR_GUN'
            ? 'bg-blue-600 text-white'
            : 'bg-gray-300 text-gray-700 hover:bg-gray-400'
        } disabled:opacity-50`}
      >
        IBKR GUN MOD
      </button>
      <button
        onClick={() => handleModeChange('IBKR_PED')}
        disabled={changing}
        className={`px-4 py-2 rounded-md text-sm font-medium ${
          currentMode === 'IBKR_PED'
            ? 'bg-blue-600 text-white'
            : 'bg-gray-300 text-gray-700 hover:bg-gray-400'
        } disabled:opacity-50`}
      >
        IBKR PED MOD
      </button>
    </div>
  )
}

export default ModeSelector

