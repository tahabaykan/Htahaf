import React from 'react'

const PositionsTable = ({ positions }) => {
  if (positions.length === 0) {
    return (
      <div className="p-8 text-center text-gray-500">
        Pozisyon bulunamadı
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
              Miktar
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Ortalama Maliyet
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Son Fiyat
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              P&L
            </th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {positions.map((position, index) => {
            const qty = position.qty || 0
            const avgCost = position.avg_cost || 0
            const lastPrice = position.last_price || position.prev_close || 0
            const pnl = (lastPrice - avgCost) * qty
            const pnlPercent = avgCost > 0 ? ((lastPrice - avgCost) / avgCost) * 100 : 0

            return (
              <tr key={index} className="hover:bg-gray-50">
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                  {position.symbol}
                </td>
                <td className={`px-6 py-4 whitespace-nowrap text-sm ${
                  qty > 0 ? 'text-green-600' : qty < 0 ? 'text-red-600' : 'text-gray-500'
                }`}>
                  {qty > 0 ? '+' : ''}{qty.toLocaleString()}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                  ${avgCost.toFixed(2)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                  ${lastPrice.toFixed(2)}
                </td>
                <td className={`px-6 py-4 whitespace-nowrap text-sm font-medium ${
                  pnl >= 0 ? 'text-green-600' : 'text-red-600'
                }`}>
                  ${pnl.toFixed(2)} ({pnlPercent.toFixed(2)}%)
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default PositionsTable









