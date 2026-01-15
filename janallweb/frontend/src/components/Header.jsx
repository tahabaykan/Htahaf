import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useData } from '../contexts/DataContext'
import { useSocket } from '../contexts/SocketContext'
import ConnectionButton from './ConnectionButton'

const Header = () => {
  const location = useLocation()
  const { connectionStatus } = useData()
  const { connected } = useSocket()

  const isActive = (path) => {
    return location.pathname === path
  }

  return (
    <header className="bg-white shadow-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          <div className="flex items-center space-x-8">
            <h1 className="text-xl font-bold text-gray-900">JanAll Web</h1>
            
            <nav className="flex space-x-4">
              <Link
                to="/"
                className={`px-3 py-2 rounded-md text-sm font-medium ${
                  isActive('/')
                    ? 'bg-blue-500 text-white'
                    : 'text-gray-700 hover:bg-gray-100'
                }`}
              >
                Ana Sayfa
              </Link>
              <Link
                to="/positions"
                className={`px-3 py-2 rounded-md text-sm font-medium ${
                  isActive('/positions')
                    ? 'bg-blue-500 text-white'
                    : 'text-gray-700 hover:bg-gray-100'
                }`}
              >
                Pozisyonlar
              </Link>
              <Link
                to="/orders"
                className={`px-3 py-2 rounded-md text-sm font-medium ${
                  isActive('/orders')
                    ? 'bg-blue-500 text-white'
                    : 'text-gray-700 hover:bg-gray-100'
                }`}
              >
                Emirler
              </Link>
              <Link
                to="/algorithms"
                className={`px-3 py-2 rounded-md text-sm font-medium ${
                  isActive('/algorithms')
                    ? 'bg-blue-500 text-white'
                    : 'text-gray-700 hover:bg-gray-100'
                }`}
              >
                Algoritmalar
              </Link>
            </nav>
          </div>

          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <div
                className={`w-3 h-3 rounded-full ${
                  connected ? 'bg-green-500' : 'bg-red-500'
                }`}
                title={connected ? 'WebSocket Bağlı' : 'WebSocket Bağlı Değil'}
              />
              <span className="text-sm text-gray-600">WebSocket</span>
            </div>
            
            <div className="flex items-center space-x-2">
              <div
                className={`w-3 h-3 rounded-full ${
                  connectionStatus.hammer ? 'bg-green-500' : 'bg-red-500'
                }`}
                title={connectionStatus.hammer ? 'Hammer Bağlı' : 'Hammer Bağlı Değil'}
              />
              <span className="text-sm text-gray-600">Hammer</span>
            </div>

            <ConnectionButton />
          </div>
        </div>
      </div>
    </header>
  )
}

export default Header

