import React, { useState } from 'react'
import api from '../services/api'
import { useData } from '../contexts/DataContext'
import toast from 'react-hot-toast'

const PlaceOrderForm = () => {
  const { fetchOrders } = useData()
  const [formData, setFormData] = useState({
    symbol: '',
    side: 'BUY',
    quantity: '',
    price: '',
    order_type: 'LIMIT'
  })
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()

    if (!formData.symbol || !formData.quantity || !formData.price) {
      toast.error('Tüm alanları doldurun')
      return
    }

    setSubmitting(true)
    try {
      const response = await api.post('/orders/place', {
        symbol: formData.symbol,
        side: formData.side.toLowerCase(),
        quantity: parseFloat(formData.quantity),
        price: parseFloat(formData.price),
        order_type: formData.order_type
      })

      if (response.data.success) {
        toast.success('Emir gönderildi')
        setFormData({
          symbol: '',
          side: 'BUY',
          quantity: '',
          price: '',
          order_type: 'LIMIT'
        })
        fetchOrders()
      } else {
        toast.error(response.data.error || 'Emir gönderilemedi')
      }
    } catch (error) {
      toast.error('Emir gönderme hatası: ' + error.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold mb-4">Yeni Emir</h3>
      
      <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Sembol
          </label>
          <input
            type="text"
            value={formData.symbol}
            onChange={(e) => setFormData({ ...formData, symbol: e.target.value.toUpperCase() })}
            className="w-full px-3 py-2 border border-gray-300 rounded-md"
            placeholder="Örn: GS PRA"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            İşlem
          </label>
          <select
            value={formData.side}
            onChange={(e) => setFormData({ ...formData, side: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 rounded-md"
          >
            <option value="BUY">Al</option>
            <option value="SELL">Sat</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Miktar
          </label>
          <input
            type="number"
            value={formData.quantity}
            onChange={(e) => setFormData({ ...formData, quantity: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 rounded-md"
            placeholder="100"
            required
            min="1"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Fiyat
          </label>
          <input
            type="number"
            step="0.01"
            value={formData.price}
            onChange={(e) => setFormData({ ...formData, price: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 rounded-md"
            placeholder="25.50"
            required
            min="0"
          />
        </div>

        <div className="flex items-end">
          <button
            type="submit"
            disabled={submitting}
            className="w-full px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:opacity-50"
          >
            {submitting ? 'Gönderiliyor...' : 'Emir Gönder'}
          </button>
        </div>
      </form>
    </div>
  )
}

export default PlaceOrderForm









