import React, { useState } from 'react'
import api from '../services/api'
import toast from 'react-hot-toast'

const OrderButtons = ({ selectedStocks, lotSize, currentMode }) => {
  const [placingOrder, setPlacingOrder] = useState(false)

  const handlePlaceOrder = async (orderType) => {
    if (selectedStocks.length === 0) {
      toast.error('Lütfen en az bir hisse seçin')
      return
    }

    if (!lotSize || lotSize <= 0) {
      toast.error('Lütfen geçerli bir lot miktarı girin')
      return
    }

    try {
      setPlacingOrder(true)
      const response = await api.post('/orders/place-batch', {
        symbols: selectedStocks,
        order_type: orderType,
        lot_size: lotSize,
        mode: currentMode
      })

      if (response.data.success) {
        toast.success(`${selectedStocks.length} hisse için ${orderType} emri gönderildi`)
      } else {
        toast.error('Emir gönderilemedi: ' + (response.data.error || 'Bilinmeyen hata'))
      }
    } catch (error) {
      toast.error('Emir hatası: ' + error.message)
    } finally {
      setPlacingOrder(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        onClick={() => handlePlaceOrder('bid_buy')}
        disabled={placingOrder || selectedStocks.length === 0}
        className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:opacity-50 text-sm font-medium"
      >
        Bid Buy
      </button>
      <button
        onClick={() => handlePlaceOrder('front_buy')}
        disabled={placingOrder || selectedStocks.length === 0}
        className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:opacity-50 text-sm font-medium"
      >
        Front Buy
      </button>
      <button
        onClick={() => handlePlaceOrder('ask_buy')}
        disabled={placingOrder || selectedStocks.length === 0}
        className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:opacity-50 text-sm font-medium"
      >
        Ask Buy
      </button>
      <button
        onClick={() => handlePlaceOrder('ask_sell')}
        disabled={placingOrder || selectedStocks.length === 0}
        className="px-4 py-2 bg-red-500 text-white rounded-md hover:bg-red-600 disabled:opacity-50 text-sm font-medium"
      >
        Ask Sell
      </button>
      <button
        onClick={() => handlePlaceOrder('front_sell')}
        disabled={placingOrder || selectedStocks.length === 0}
        className="px-4 py-2 bg-red-500 text-white rounded-md hover:bg-red-600 disabled:opacity-50 text-sm font-medium"
      >
        Front Sell
      </button>
      <button
        onClick={() => handlePlaceOrder('soft_front_buy')}
        disabled={placingOrder || selectedStocks.length === 0}
        className="px-4 py-2 bg-purple-500 text-white rounded-md hover:bg-purple-600 disabled:opacity-50 text-sm font-medium"
      >
        SoftFront Buy
      </button>
      <button
        onClick={() => handlePlaceOrder('soft_front_sell')}
        disabled={placingOrder || selectedStocks.length === 0}
        className="px-4 py-2 bg-purple-500 text-white rounded-md hover:bg-purple-600 disabled:opacity-50 text-sm font-medium"
      >
        SoftFront Sell
      </button>
      <button
        onClick={() => handlePlaceOrder('bid_sell')}
        disabled={placingOrder || selectedStocks.length === 0}
        className="px-4 py-2 bg-red-500 text-white rounded-md hover:bg-red-600 disabled:opacity-50 text-sm font-medium"
      >
        Bid Sell
      </button>
    </div>
  )
}

export default OrderButtons

