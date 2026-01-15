import React, { useState } from 'react'
import { useData } from '../contexts/DataContext'
import toast from 'react-hot-toast'

const ConnectionButton = () => {
  const { connectionStatus, connectHammer, fetchConnectionStatus } = useData()
  const [connecting, setConnecting] = useState(false)
  const [showDialog, setShowDialog] = useState(false)
  const [formData, setFormData] = useState({
    host: '127.0.0.1',
    port: 16400,
    password: ''
  })

  const handleConnect = async () => {
    if (!formData.password) {
      toast.error('Şifre gerekli')
      return
    }

    setConnecting(true)
    try {
      const result = await connectHammer(
        formData.host,
        formData.port,
        formData.password
      )
      
      if (result.success) {
        toast.success('Hammer Pro bağlantısı başarılı')
        setShowDialog(false)
        await fetchConnectionStatus()
      } else {
        toast.error(result.error || 'Bağlantı başarısız')
      }
    } catch (error) {
      toast.error('Bağlantı hatası: ' + error.message)
    } finally {
      setConnecting(false)
    }
  }

  return (
    <>
      <button
        onClick={() => setShowDialog(true)}
        className={`px-4 py-2 rounded-md text-sm font-medium ${
          connectionStatus.hammer
            ? 'bg-green-500 text-white hover:bg-green-600'
            : 'bg-gray-500 text-white hover:bg-gray-600'
        }`}
      >
        {connectionStatus.hammer ? 'Bağlı' : 'Bağlan'}
      </button>

      {showDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-96">
            <h2 className="text-xl font-bold mb-4">Hammer Pro Bağlantısı</h2>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Host
                </label>
                <input
                  type="text"
                  value={formData.host}
                  onChange={(e) => setFormData({ ...formData, host: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Port
                </label>
                <input
                  type="number"
                  value={formData.port}
                  onChange={(e) => setFormData({ ...formData, port: parseInt(e.target.value) })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Şifre
                </label>
                <input
                  type="password"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                  placeholder="Hammer Pro API şifresi"
                />
              </div>
            </div>

            <div className="flex justify-end space-x-2 mt-6">
              <button
                onClick={() => setShowDialog(false)}
                className="px-4 py-2 text-gray-700 bg-gray-200 rounded-md hover:bg-gray-300"
              >
                İptal
              </button>
              <button
                onClick={handleConnect}
                disabled={connecting}
                className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:opacity-50"
              >
                {connecting ? 'Bağlanıyor...' : 'Bağlan'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default ConnectionButton









