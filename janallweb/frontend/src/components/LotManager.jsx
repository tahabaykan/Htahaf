import React, { useState } from 'react'
import api from '../services/api'
import toast from 'react-hot-toast'

const LotManager = ({ selectedStocks, stocks, onLotChange }) => {
  const [lotSize, setLotSize] = useState(200)  // Default 200 lot
  const [settingLot, setSettingLot] = useState(false)

  const handleLotChange = (newLot) => {
    setLotSize(newLot)
    if (onLotChange) {
      onLotChange(newLot)
    }
  }

  const handlePercentageLot = async (percentage) => {
    if (selectedStocks.length === 0) {
      toast.error('Lütfen en az bir hisse seçin')
      return
    }

    try {
      setSettingLot(true)
      // Backend'den MAXALW değerlerini al ve % hesapla
      const response = await api.post('/orders/calculate-lot-percentage', {
        symbols: selectedStocks,
        percentage: percentage
      })

      if (response.data.success) {
        const calculatedLot = response.data.lot_size
        handleLotChange(calculatedLot)
        toast.success(`%${percentage} lot hesaplandı: ${calculatedLot}`)
      } else {
        toast.error('Lot hesaplanamadı: ' + (response.data.error || 'Bilinmeyen hata'))
      }
    } catch (error) {
      toast.error('Lot hatası: ' + error.message)
    } finally {
      setSettingLot(false)
    }
  }

  const handleAvgAdv = async () => {
    if (selectedStocks.length === 0) {
      toast.error('Lütfen en az bir hisse seçin')
      return
    }

    try {
      setSettingLot(true)
      const response = await api.post('/orders/calculate-lot-avg-adv', {
        symbols: selectedStocks
      })

      if (response.data.success) {
        const calculatedLot = response.data.lot_size
        handleLotChange(calculatedLot)
        toast.success(`Avg Adv lot hesaplandı: ${calculatedLot}`)
      } else {
        toast.error('Avg Adv hesaplanamadı: ' + (response.data.error || 'Bilinmeyen hata'))
      }
    } catch (error) {
      toast.error('Avg Adv hatası: ' + error.message)
    } finally {
      setSettingLot(false)
    }
  }

  return (
    <div className="flex items-center gap-2">
      <label className="text-sm font-medium text-gray-700">Lot:</label>
      <input
        type="number"
        value={lotSize}
        onChange={(e) => handleLotChange(parseInt(e.target.value) || 0)}
        className="w-20 px-2 py-1 border border-gray-300 rounded-md text-sm"
        min="1"
      />
      
      <button
        onClick={() => handlePercentageLot(25)}
        disabled={settingLot || selectedStocks.length === 0}
        className="px-3 py-1 bg-gray-500 text-white rounded-md hover:bg-gray-600 disabled:opacity-50 text-sm font-medium"
      >
        %25
      </button>
      <button
        onClick={() => handlePercentageLot(50)}
        disabled={settingLot || selectedStocks.length === 0}
        className="px-3 py-1 bg-gray-500 text-white rounded-md hover:bg-gray-600 disabled:opacity-50 text-sm font-medium"
      >
        %50
      </button>
      <button
        onClick={() => handlePercentageLot(75)}
        disabled={settingLot || selectedStocks.length === 0}
        className="px-3 py-1 bg-gray-500 text-white rounded-md hover:bg-gray-600 disabled:opacity-50 text-sm font-medium"
      >
        %75
      </button>
      <button
        onClick={() => handlePercentageLot(100)}
        disabled={settingLot || selectedStocks.length === 0}
        className="px-3 py-1 bg-gray-500 text-white rounded-md hover:bg-gray-600 disabled:opacity-50 text-sm font-medium"
      >
        %100
      </button>
      <button
        onClick={handleAvgAdv}
        disabled={settingLot || selectedStocks.length === 0}
        className="px-3 py-1 bg-gray-500 text-white rounded-md hover:bg-gray-600 disabled:opacity-50 text-sm font-medium"
      >
        Avg Adv
      </button>
    </div>
  )
}

export default LotManager









