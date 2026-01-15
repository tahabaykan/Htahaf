import React from 'react'
import { useData } from '../contexts/DataContext'
import OrdersTable from '../components/OrdersTable'
import PlaceOrderForm from '../components/PlaceOrderForm'

const OrdersPage = () => {
  const { orders } = useData()

  return (
    <div className="max-w-7xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-4">Emirler</h2>
      
      <div className="mb-6">
        <PlaceOrderForm />
      </div>

      <div className="bg-white rounded-lg shadow">
        <OrdersTable orders={orders} />
      </div>
    </div>
  )
}

export default OrdersPage









