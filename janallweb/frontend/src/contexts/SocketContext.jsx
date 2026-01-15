import React, { createContext, useContext, useEffect, useState } from 'react'
import { io } from 'socket.io-client'
import toast from 'react-hot-toast'

const SocketContext = createContext()

export const useSocket = () => {
  const context = useContext(SocketContext)
  if (!context) {
    throw new Error('useSocket must be used within SocketProvider')
  }
  return context
}

export const SocketProvider = ({ children }) => {
  const [socket, setSocket] = useState(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    // Socket.IO bağlantısı
    const newSocket = io('http://127.0.0.1:5000', {
      transports: ['websocket', 'polling']
    })

    newSocket.on('connect', () => {
      console.log('WebSocket bağlandı')
      setConnected(true)
      toast.success('WebSocket bağlantısı başarılı')
    })

    newSocket.on('disconnect', () => {
      console.log('WebSocket bağlantısı kesildi')
      setConnected(false)
      toast.error('WebSocket bağlantısı kesildi')
    })

    newSocket.on('error', (error) => {
      console.error('WebSocket hatası:', error)
      toast.error('WebSocket hatası: ' + error.message)
    })

    setSocket(newSocket)

    return () => {
      newSocket.close()
    }
  }, [])

  const value = {
    socket,
    connected
  }

  return (
    <SocketContext.Provider value={value}>
      {children}
    </SocketContext.Provider>
  )
}









