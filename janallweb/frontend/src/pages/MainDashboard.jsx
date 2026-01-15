import React, { useState, useEffect } from 'react'
import { useData } from '../contexts/DataContext'
import StockTable from '../components/StockTable'
import CSVLoader from '../components/CSVLoader'
import TopControlBar from '../components/TopControlBar'
import OrderButtons from '../components/OrderButtons'
import LotManager from '../components/LotManager'
import ModeSelector from '../components/ModeSelector'
import SelectionControls from '../components/SelectionControls'
import GroupButtons from '../components/GroupButtons'
import toast from 'react-hot-toast'

const MainDashboard = () => {
  const { stocks, loadCSV, subscribeMarketData, fetchMergedMarketData } = useData()
  const [loading, setLoading] = useState(false)
  const [selectedStocks, setSelectedStocks] = useState([])
  const [lotSize, setLotSize] = useState(200)
  const [currentMode, setCurrentMode] = useState('HAMPRO')
  const [isMini450Active, setIsMini450Active] = useState(false)
  const [liveDataRunning, setLiveDataRunning] = useState(false)
  const [refreshInterval, setRefreshInterval] = useState(null)

  const handleLoadCSV = async (filename) => {
    setLoading(true)
    try {
      console.log('[MainDashboard] CSV yükleme başlatılıyor:', filename)
      const result = await loadCSV(filename)
      
      console.log('[MainDashboard] CSV yükleme sonucu:', result)
      
      // Result kontrolü
      if (!result) {
        console.error('[MainDashboard] Result undefined!')
        throw new Error('CSV yükleme sonucu alınamadı')
      }
      
      // Başarı mesajı
      const rowCount = result.row_count || (result.data ? result.data.length : 0)
      console.log('[MainDashboard] Row count:', rowCount)
      
      if (rowCount > 0) {
        toast.success(`${rowCount} hisse yüklendi`)
      } else {
        toast.success('CSV yüklendi (veri bulunamadı)')
      }
      
      // Market data'ya subscribe ol - Tkinter'daki gibi TÜM sembollere subscribe ol
      if (result.data && result.data.length > 0) {
        const symbols = result.data.map(stock => stock.PREF_IBKR || stock['PREF IBKR'] || stock.Symbol || stock.symbol).filter(Boolean)
        console.log('[MainDashboard] Market data subscribe:', symbols.length, 'sembol')
        subscribeMarketData(symbols) // TÜM sembollere subscribe ol (Tkinter'daki gibi)
      }
    } catch (error) {
      const errorMessage = error.message || 'Bilinmeyen hata'
      console.error('[MainDashboard] CSV yükleme hatası:', error)
      console.error('[MainDashboard] Error stack:', error.stack)
      toast.error('CSV yüklenemedi: ' + errorMessage)
    } finally {
      setLoading(false)
    }
  }

  const handleSelectAll = () => {
    const allSymbols = stocks.map(s => s.PREF_IBKR || s['PREF IBKR'] || s.Symbol || s.symbol).filter(Boolean)
    setSelectedStocks(allSymbols)
  }

  const handleDeselectAll = () => {
    setSelectedStocks([])
  }

  const handleLiveDataToggle = async (running) => {
    setLiveDataRunning(running)
    
    if (running) {
      // Start live data: load merged data and start periodic refresh
      try {
        setLoading(true)
        toast('Live data başlatılıyor...', { icon: 'ℹ️' })
        
        // Load merged data (static + live + scores)
        await fetchMergedMarketData()
        
        // Subscribe to market data updates via WebSocket
        if (stocks.length > 0) {
          const symbols = stocks.map(s => s.PREF_IBKR || s['PREF IBKR'] || s.Symbol || s.symbol).filter(Boolean)
          subscribeMarketData(symbols)
        }
        
        // Start periodic refresh (every 2 seconds for 500+ symbols)
        const interval = setInterval(async () => {
          try {
            await fetchMergedMarketData()
          } catch (error) {
            console.error('[MainDashboard] Periodic refresh error:', error)
          }
        }, 2000) // 2 seconds - optimized for 500+ symbols
        
        setRefreshInterval(interval)
        toast.success('Live data başlatıldı - Otomatik güncelleme aktif')
      } catch (error) {
        console.error('[MainDashboard] Live data start error:', error)
        toast.error('Live data başlatılamadı: ' + error.message)
        setLiveDataRunning(false)
      } finally {
        setLoading(false)
      }
    } else {
      // Stop live data
      if (refreshInterval) {
        clearInterval(refreshInterval)
        setRefreshInterval(null)
      }
      toast('Live data durduruldu', { icon: 'ℹ️' })
    }
  }
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (refreshInterval) {
        clearInterval(refreshInterval)
      }
    }
  }, [refreshInterval])

  const handleMini450Toggle = async (active) => {
    setIsMini450Active(active)
    
    if (active) {
      // Mini450 aktif olduğunda janalldata.csv'yi yükle
      try {
        toast('Mini450 görünümü aktif ediliyor...', { icon: 'ℹ️' })
        await handleLoadCSV('janalldata.csv')
        toast.success('Mini450 görünümü aktif - Tüm hisseler tek sayfada gösteriliyor')
        
        // Tüm hisseler için live data subscribe et
        if (stocks.length > 0) {
          const symbols = stocks.map(s => s.PREF_IBKR || s['PREF IBKR'] || s.Symbol || s.symbol).filter(Boolean)
          subscribeMarketData(symbols)
          toast.success(`${symbols.length} hisse için live data başlatıldı`)
        }
      } catch (error) {
        toast.error('Mini450 görünümü aktif edilemedi: ' + error.message)
        setIsMini450Active(false)
      }
    } else {
      toast('Normal görünüme dönüldü', { icon: 'ℹ️' })
    }
  }

  return (
    <div className="max-w-7xl mx-auto">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-900 mb-4">Ana Dashboard</h2>
        
        {/* Üst Kontrol Çubuğu */}
        <TopControlBar
          onLiveDataToggle={handleLiveDataToggle}
          onMini450Toggle={handleMini450Toggle}
          isMini450Active={isMini450Active}
        />

        {/* CSV Loader */}
        <div className="bg-white rounded-lg shadow p-4 mb-4">
          <CSVLoader onLoad={handleLoadCSV} loading={loading} />
        </div>

        {/* Grup Butonları */}
        <GroupButtons onLoadGroup={handleLoadCSV} />

        {/* Seçim Kontrolleri ve Mod Seçici */}
        <div className="bg-white rounded-lg shadow p-4 mb-4">
          <div className="flex items-center justify-between">
            <SelectionControls
              stocks={stocks}
              selectedStocks={selectedStocks}
              onSelectAll={handleSelectAll}
              onDeselectAll={handleDeselectAll}
            />
            <ModeSelector
              currentMode={currentMode}
              onModeChange={setCurrentMode}
            />
          </div>
        </div>

        {/* Lot Yönetimi */}
        <div className="bg-white rounded-lg shadow p-4 mb-4">
          <LotManager
            selectedStocks={selectedStocks}
            stocks={stocks}
            onLotChange={setLotSize}
          />
        </div>

        {/* Emir Butonları */}
        <div className="bg-white rounded-lg shadow p-4 mb-4">
          <OrderButtons
            selectedStocks={selectedStocks}
            lotSize={lotSize}
            currentMode={currentMode}
          />
        </div>
      </div>

      {stocks.length > 0 && (
        <div className="bg-white rounded-lg shadow">
          <StockTable 
            stocks={stocks} 
            selectedStocks={selectedStocks}
            onSelectionChange={setSelectedStocks}
            isMini450={isMini450Active}
          />
        </div>
      )}

      {stocks.length === 0 && (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <p className="text-gray-500">CSV dosyası yükleyerek başlayın</p>
        </div>
      )}
    </div>
  )
}

export default MainDashboard

