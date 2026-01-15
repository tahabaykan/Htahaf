import React, { createContext, useContext, useState, useEffect } from 'react'
import { useSocket } from './SocketContext'
import api from '../services/api'

const DataContext = createContext()

export const useData = () => {
  const context = useContext(DataContext)
  if (!context) {
    throw new Error('useData must be used within DataProvider')
  }
  return context
}

export const DataProvider = ({ children }) => {
  const { socket } = useSocket()
  const [stocks, setStocks] = useState([])
  const [positions, setPositions] = useState([])
  const [orders, setOrders] = useState([])
  const [marketData, setMarketData] = useState({})
  const [connectionStatus, setConnectionStatus] = useState({
    hammer: false,
    ibkr: false
  })

  // WebSocket event listeners
  useEffect(() => {
    if (!socket) return

    socket.on('market_data_update', async (data) => {
      // Market data geldiğinde güncelle
      setMarketData(prev => ({
        ...prev,
        [data.symbol]: data.data
      }))
      
      // Skorları yeniden hesapla (Tkinter'daki gibi)
      // Periyodik güncelleme için debounce kullan
      if (stocks.length > 0) {
        // Her market data güncellemesinde skorları güncellemek yerine
        // periyodik olarak güncelle (performans için)
        // Bu kısım StockTable'da useEffect ile yapılacak
      }
    })

    socket.on('positions_update', (data) => {
      setPositions(data.positions || [])
    })

    socket.on('order_update', (data) => {
      // Emir güncellemesi geldiğinde listeyi yenile
      fetchOrders()
    })

    socket.on('fill_update', (data) => {
      // Fill geldiğinde pozisyonları yenile
      fetchPositions()
    })

    return () => {
      socket.off('market_data_update')
      socket.off('positions_update')
      socket.off('order_update')
      socket.off('fill_update')
    }
  }, [socket])

  // İlk yükleme
  useEffect(() => {
    fetchConnectionStatus()
    fetchPositions()
    fetchOrders()
  }, [])

  const fetchConnectionStatus = async () => {
    try {
      const response = await api.get('/connection/status')
      setConnectionStatus(response.data.status)
    } catch (error) {
      console.error('Bağlantı durumu alınamadı:', error)
    }
  }

  const fetchPositions = async () => {
    try {
      const response = await api.get('/positions')
      setPositions(response.data.positions || [])
    } catch (error) {
      console.error('Pozisyonlar alınamadı:', error)
    }
  }

  const fetchOrders = async () => {
    try {
      const response = await api.get('/orders')
      setOrders(response.data.orders || [])
    } catch (error) {
      console.error('Emirler alınamadı:', error)
    }
  }

  const loadCSV = async (filename) => {
    try {
      console.log(`[Frontend] CSV yükleme isteği: ${filename}`)
      const response = await api.post('/csv/load', { filename })
      
      console.log('[Frontend] API Response:', response.data)
      
      if (response.data.success) {
        setStocks(response.data.data || [])
        console.log(`[Frontend] CSV yüklendi: ${response.data.row_count} satır`)
        return response.data
      } else {
        // API'den success: false geldi
        const errorMessage = response.data.error || 'CSV yüklenemedi'
        console.error('[Frontend] API hatası:', errorMessage)
        throw new Error(errorMessage)
      }
    } catch (error) {
      console.error('[Frontend] CSV yükleme hatası:', error)
      
      // Error response'u parse et
      if (error.response && error.response.data) {
        const errorMessage = error.response.data.error || error.message || 'CSV yüklenemedi'
        console.error('[Frontend] Hata detayı:', errorMessage)
        throw new Error(errorMessage)
      }
      
      // Network hatası veya diğer hatalar
      if (error.message) {
        throw new Error(error.message)
      }
      
      throw new Error('CSV yüklenirken bilinmeyen bir hata oluştu')
    }
  }

  const connectHammer = async (host, port, password) => {
    try {
      const response = await api.post('/connection/hammer/connect', {
        host,
        port,
        password
      })
      if (response.data.success) {
        await fetchConnectionStatus()
      }
      return response.data
    } catch (error) {
      console.error('Hammer bağlantısı başarısız:', error)
      throw error
    }
  }

  const disconnectHammer = async () => {
    try {
      const response = await api.post('/connection/hammer/disconnect')
      if (response.data.success) {
        await fetchConnectionStatus()
      }
      return response.data
    } catch (error) {
      console.error('Hammer disconnect hatası:', error)
      throw error
    }
  }

  const subscribeMarketData = (symbols) => {
    if (socket && socket.connected) {
      socket.emit('subscribe_market_data', { symbols })
      console.log(`[DataContext] ${symbols.length} sembol için market data subscribe edildi`)
    }
  }

  const fetchMergedMarketData = async () => {
    /**
     * Fetch merged data: static CSV + live market data + derived scores
     * This is the main function for the market scanner table.
     */
    try {
      const response = await api.get('/market-data/merged')
      if (response.data.success) {
        setStocks(response.data.data || [])
        console.log(`[DataContext] Merged data loaded: ${response.data.count} symbols`)
        return response.data
      } else {
        throw new Error(response.data.error || 'Failed to fetch merged data')
      }
    } catch (error) {
      console.error('[DataContext] Merged data fetch error:', error)
      throw error
    }
  }

  // Periyodik olarak skorları güncelle (Tkinter'daki update_scores_with_market_data gibi)
  useEffect(() => {
    if (stocks.length === 0) return
    
    let isMounted = true
    
    // Periyodik olarak skorları güncelle (Tkinter'da 1-3 saniyede bir)
    const updateInterval = 2000 // 2 saniyede bir güncelle (performans için)
    
    const updateScores = async () => {
      if (!isMounted) return
      
      try {
        // Backend'de batch olarak skorları güncelle
        const response = await api.post('/scores/update-batch', { stocks })
        
        if (isMounted && response.data.success && response.data.stocks) {
          // Güncellenmiş stocks'u set et
          setStocks(response.data.stocks)
          console.log(`[DataContext] Skorlar güncellendi: ${response.data.stocks.length} hisse`)
        }
      } catch (error) {
        console.error('[DataContext] Skor güncelleme hatası:', error)
      }
    }
    
    // İlk güncellemeyi hemen yap
    updateScores()
    
    // Sonra periyodik olarak güncelle
    const intervalId = setInterval(updateScores, updateInterval)
    
    return () => {
      isMounted = false
      clearInterval(intervalId)
    }
  }, [stocks.length]) // Sadece stocks sayısı değiştiğinde yeniden başlat

  const value = {
    stocks,
    positions,
    orders,
    marketData,
    connectionStatus,
    setStocks,
    setPositions,
    setOrders,
    fetchPositions,
    fetchOrders,
    loadCSV,
    connectHammer,
    disconnectHammer,
    subscribeMarketData,
    fetchConnectionStatus,
    fetchMergedMarketData
  }

  return (
    <DataContext.Provider value={value}>
      {children}
    </DataContext.Provider>
  )
}

