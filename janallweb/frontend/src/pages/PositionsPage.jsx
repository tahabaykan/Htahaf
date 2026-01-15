import React from 'react'
import { useData } from '../contexts/DataContext'
import PositionsTable from '../components/PositionsTable'

const PositionsPage = () => {
  const { positions } = useData()

  return (
    <div className="max-w-7xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-4">Pozisyonlar</h2>
      
      <div className="bg-white rounded-lg shadow">
        <PositionsTable positions={positions} />
      </div>
    </div>
  )
}

export default PositionsPage









