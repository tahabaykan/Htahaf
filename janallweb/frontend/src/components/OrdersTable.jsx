import React from 'react'
import { useData } from '../contexts/DataContext'
import api from '../services/api'
import toast from 'react-hot-toast'

const OrdersTable = ({ orders }) => {
  const { fetchOrders } = useData()

  const handleCancel = async (orderId) => {
    if (!window.confirm('Emri iptal etmek istediğinize emin misiniz?')) {
      return
    }

    try {
      const response = await api.post('/orders/cancel', { order_id: orderId })
      if (response.data.success) {
        toast.success('Emir iptal edildi')
        fetchOrders()
      } else {
        toast.error(response.data.error || 'Emir iptal edilemedi')
      }
    } catch (error) {
      toast.error('Emir iptal hatası: ' + error.message)
    }
  }

  if (orders.length === 0) {
    return (
      <div className="p-8 text-center text-gray-500">
        Açık emir bulunamadı
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Sembol
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              İşlem
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Miktar
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Doldurulan
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Kalan
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Limit Fiyat
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Durum
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              İşlemler
            </th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {orders.map((order, index) => (
            <tr key={index} className="hover:bg-gray-50">
              <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                {order.symbol}
              </td>
              <td className={`px-6 py-4 whitespace-nowrap text-sm font-medium ${
                order.action === 'BUY' ? 'text-green-600' : 'text-red-600'
              }`}>
                {order.action}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                {order.qty.toLocaleString()}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                {order.filled_qty.toLocaleString()}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                {order.remaining_qty.toLocaleString()}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                ${order.limit_price.toFixed(2)}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm">
                <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                  order.status === 'Filled' ? 'bg-green-100 text-green-800' :
                  order.status === 'Cancelled' ? 'bg-red-100 text-red-800' :
                  'bg-yellow-100 text-yellow-800'
                }`}>
                  {order.status}
                </span>
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm">
                {order.status !== 'Filled' && order.status !== 'Cancelled' && (
                  <button
                    onClick={() => handleCancel(order.order_id)}
                    className="text-red-600 hover:text-red-900"
                  >
                    İptal
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default OrdersTable









