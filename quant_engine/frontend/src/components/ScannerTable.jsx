import React, { useMemo, useRef, useEffect } from 'react'
import { FixedSizeList as List } from 'react-window'
import './ScannerTable.css'

// 🟢 FAST PATH COLUMNS - Main Scanner (L1 + CSV + Fast Scores)
// ❌ NO tick-by-tick columns here (GOD, ROD, GRPAN, RWVAP1D)
// Those are in Deeper Analysis page (SLOW PATH)
const COLUMNS = [
  { key: 'PREF_IBKR', label: 'PREF_IBKR', width: 120 },
  { key: 'state', label: 'state', width: 100 },
  { key: 'signal', label: 'Signal', width: 120 },
  { key: 'intent', label: 'intent', width: 100 },
  { key: 'plan', label: 'Plan', width: 80 },
  { key: 'queue', label: 'Queue', width: 100 },
  { key: 'gate', label: 'Gate', width: 100 },
  { key: 'action', label: 'Action', width: 100 },
  { key: 'execution', label: 'Execution', width: 100 },
  { key: 'CMON', label: 'CMON', width: 100 },
  { key: 'CGRUP', label: 'CGRUP', width: 100 },
  { key: 'GROUP', label: 'DOS GRUP', width: 120 },  // PRIMARY GROUP (file_group)
  { key: 'prev_close', label: 'prev_close', width: 100 },
  { key: 'bid', label: 'bid', width: 80 },
  { key: 'ask', label: 'ask', width: 80 },
  { key: 'last', label: 'last', width: 80 },
  { key: 'spread', label: 'SPREAD', width: 80 },  // Cent bazında (ask - bid)
  { key: 'volume', label: 'volume', width: 100 },
  { key: 'FINAL_THG', label: 'FINAL_THG', width: 100 },
  { key: 'SHORT_FINAL', label: 'SHORT_FINAL', width: 120 },
  { key: 'SMI', label: 'SMI', width: 80 },
  { key: 'SMA63chg', label: 'SMA63chg', width: 100 },
  { key: 'SMA246chg', label: 'SMA246chg', width: 110 },
  { key: 'AVG_ADV', label: 'AVG_ADV', width: 100 },
  { key: 'MAXALW', label: 'MAXALW', width: 100 },  // Static: AVG_ADV / 10
  { key: 'GORT', label: 'GORT', width: 90 },  // Group Relative Trend
  { key: 'Fbtot', label: 'Fbtot', width: 90 },  // Final Buy Total (Long)
  { key: 'SFStot', label: 'SFStot', width: 90 },  // Short Front Sell Total
  // 🟢 FAST PATH Pricing Overlay scores (calculated from L1 + CSV)
  { key: 'overlay_benchmark_type', label: 'Bench Type', width: 90 },
  { key: 'overlay_benchmark_chg', label: 'Bench Chg', width: 90 },
  { key: 'Bid_buy_ucuzluk_skoru', label: 'BB Ucuz', width: 90 },
  { key: 'Front_buy_ucuzluk_skoru', label: 'FB Ucuz', width: 90 },
  { key: 'Ask_buy_ucuzluk_skoru', label: 'AB Ucuz', width: 90 },
  { key: 'Ask_sell_pahalilik_skoru', label: 'AS Pahal', width: 90 },
  { key: 'Front_sell_pahalilik_skoru', label: 'FS Pahal', width: 90 },
  { key: 'Bid_sell_pahalilik_skoru', label: 'BS Pahal', width: 90 },
  { key: 'Final_BB_skor', label: 'Final BB', width: 90 },
  { key: 'Final_FB_skor', label: 'Final FB', width: 90 },
  { key: 'Final_AB_skor', label: 'Final AB', width: 90 },
  { key: 'Final_AS_skor', label: 'Final AS', width: 90 },
  { key: 'Final_FS_skor', label: 'Final FS', width: 90 },
  { key: 'Final_BS_skor', label: 'Final BS', width: 90 },
  { key: 'Final_SAS_skor', label: 'Final SAS', width: 90 },
  { key: 'Final_SFS_skor', label: 'Final SFS', width: 90 },
  { key: 'Final_SBS_skor', label: 'Final SBS', width: 90 },
  // 🔵 SLOW PATH columns REMOVED - see Deeper Analysis page
  // ❌ grpan_price (GRPAN $)
  // ❌ grpan_concentration_percent (GRPAN %)
  // ❌ rwvap_1d (RWVAP 1D)
  // ❌ grpan_ort_dev (GOD)
  // ❌ rwvap_ort_dev (ROD)
]

function formatValue(value, columnKey, row) {
  // Handle GROUP (DOS GRUP) column specially - heldkuponlu için CGRUP ekle
  if (columnKey === 'GROUP') {
    const group = value || row?.GROUP || row?.group || row?.file_group || '-'
    // heldkuponlu, heldkuponlukreciliz, heldkuponlukreorta için CGRUP ekle
    const kuponluGroups = ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']
    if (kuponluGroups.includes(group?.toLowerCase())) {
      const cgrup = row?.CGRUP || row?.cgrup
      if (cgrup) {
        return `${group}-${cgrup.toLowerCase()}`
      }
    }
    return group
  }
  
  // Handle signal column specially (must be before general object handling)
  if (columnKey === 'signal') {
    const signal = row?.signal
    if (!signal || typeof signal !== 'object' || Array.isArray(signal)) {
      return '-'
    }
    // Compact format: L:STRONG | X:WEAK | S:NONE | COV:MEDIUM
    const parts = []
    if (signal.long_entry && signal.long_entry !== 'NONE') {
      parts.push(`L:${signal.long_entry}`)
    }
    if (signal.long_exit && signal.long_exit !== 'NONE') {
      parts.push(`X:${signal.long_exit}`)
    }
    if (signal.short_entry && signal.short_entry !== 'NONE') {
      parts.push(`S:${signal.short_entry}`)
    }
    if (signal.short_cover && signal.short_cover !== 'NONE') {
      parts.push(`COV:${signal.short_cover}`)
    }
    if (parts.length === 0) {
      return 'NONE'
    }
    return parts.join(' | ')
  }
  
  // Handle intent column specially (must be before general object handling)
  if (columnKey === 'intent') {
    const intent = row?.intent
    if (!intent) {
      return '-'
    }
    return String(intent)
  }
  
  // Handle plan column specially
  if (columnKey === 'plan') {
    const orderPlan = row?.order_plan
    if (!orderPlan || !orderPlan.action || orderPlan.action === 'NONE') {
      return 'NONE'
    }
    return orderPlan.action
  }
  
  // Handle queue column specially
  if (columnKey === 'queue') {
    const queueStatus = row?.queue_status
    if (!queueStatus || !queueStatus.queue_status) {
      return '-'
    }
    return queueStatus.queue_status
  }
  
  // Handle gate column specially
  if (columnKey === 'gate') {
    const gateStatus = row?.gate_status
    if (!gateStatus || !gateStatus.gate_status) {
      return '-'
    }
    // Shorten status for display
    const status = gateStatus.gate_status
    if (status === 'AUTO_APPROVED') return 'AUTO'
    if (status === 'MANUAL_REVIEW') return 'REVIEW'
    if (status === 'BLOCKED') return 'BLOCK'
    return status
  }
  
  // Handle action column specially
  if (columnKey === 'action') {
    const userAction = row?.user_action
    if (!userAction) {
      return '-'
    }
    return userAction
  }
  
  // Handle execution column specially
  if (columnKey === 'execution') {
    const execStatus = row?.execution_status
    if (!execStatus) {
      return '-'
    }
    return execStatus
  }
  
  // Handle object values (must be before String conversion)
  // Note: signal and intent are already handled above
  if (value !== null && value !== undefined && typeof value === 'object') {
    // For nested objects that weren't handled above, return '-' to avoid [object Object]
    return '-'
  }
  
  if (value === null || value === undefined || value === '') return '-'
  
  // Try to parse as number
  const num = parseFloat(value)
  if (!isNaN(num) && isFinite(num)) {
    // Format spread in cents (ask - bid)
    if (columnKey === 'spread') {
      return '$' + num.toFixed(2)  // Cent bazında: $0.05, $0.10, etc.
    }
    // Format GRPAN price
    if (columnKey === 'grpan_price') {
      return '$' + num.toFixed(2)
    }
    // Format GRPAN concentration as percentage
    if (columnKey === 'grpan_concentration_percent') {
      return num.toFixed(2) + '%'
    }
    // Format RWVAP 1D
    if (columnKey === 'rwvap_1d') {
      // Get from rwvap_windows.rwvap_1d.rwvap
      const rwvap_1d = row?.rwvap_windows?.rwvap_1d?.rwvap
      if (rwvap_1d === null || rwvap_1d === undefined) {
        return '-'
      }
      return '$' + parseFloat(rwvap_1d).toFixed(2)
    }
    // Format GRPAN ORT DEV (GOD)
    if (columnKey === 'grpan_ort_dev') {
      const god = row?.grpan_ort_dev
      if (god === null || god === undefined || isNaN(god)) {
        return '-'
      }
      const num = parseFloat(god)
      const sign = num >= 0 ? '+' : ''
      return sign + num.toFixed(2)
    }
    // Format RWVAP ORT DEV (ROD)
    if (columnKey === 'rwvap_ort_dev') {
      const rod = row?.rwvap_ort_dev
      if (rod === null || rod === undefined || isNaN(rod)) {
        return '-'
      }
      const num = parseFloat(rod)
      const sign = num >= 0 ? '+' : ''
      return sign + num.toFixed(2)
    }
    // Format overlay benchmark type
    if (columnKey === 'overlay_benchmark_type') {
      const status = row?.overlay_status
      if (status === 'COLLECTING' || status === 'ERROR') {
        return status
      }
      const benchType = row?.overlay_benchmark_type
      return benchType || '-'
    }
    // Format overlay benchmark change
    if (columnKey === 'overlay_benchmark_chg') {
      const status = row?.overlay_status
      if (status === 'COLLECTING' || status === 'ERROR') {
        return status
      }
      const benchChg = row?.overlay_benchmark_chg
      if (benchChg === null || benchChg === undefined || isNaN(benchChg)) {
        return '-'
      }
      const num = parseFloat(benchChg)
      const sign = num >= 0 ? '+' : ''
      return sign + num.toFixed(4)
    }
    // Format overlay scores (ucuzluk/pahalılık skorları) - 2 decimals
    const overlayScoreKeys = [
      'Bid_buy_ucuzluk_skoru', 'Front_buy_ucuzluk_skoru', 'Ask_buy_ucuzluk_skoru',
      'Ask_sell_pahalilik_skoru', 'Front_sell_pahalilik_skoru', 'Bid_sell_pahalilik_skoru'
    ]
    if (overlayScoreKeys.includes(columnKey)) {
      const status = row?.overlay_status
      if (status === 'COLLECTING' || status === 'ERROR') {
        return status
      }
      const score = row?.[columnKey]
      if (score === null || score === undefined || isNaN(score)) {
        return '-'
      }
      const num = parseFloat(score)
      const sign = num >= 0 ? '+' : ''
      return sign + num.toFixed(2)
    }
    // Format final overlay scores - 2 decimals
    const finalScoreKeys = [
      'Final_BB_skor', 'Final_FB_skor', 'Final_AB_skor', 'Final_AS_skor', 'Final_FS_skor', 'Final_BS_skor',
      'Final_SAS_skor', 'Final_SFS_skor', 'Final_SBS_skor'
    ]
    if (finalScoreKeys.includes(columnKey)) {
      const status = row?.overlay_status
      if (status === 'COLLECTING' || status === 'ERROR') {
        return status
      }
      const score = row?.[columnKey]
      if (score === null || score === undefined || isNaN(score)) {
        return '-'
      }
      return parseFloat(score).toFixed(2)
    }
    // Format prices with 2 decimals
    if (['prev_close', 'bid', 'ask', 'last'].includes(columnKey)) {
      return num.toFixed(2)
    }
    // Format other numeric values with 2 decimals
    return num.toFixed(2)
  }
  
  // Return as string for non-numeric values
  return String(value)
}

function ScannerTable({ data, onSort, sortConfig, onRowClick }) {
  console.log('ScannerTable render:', { dataLength: data?.length, data: data?.slice(0, 2) })
  
  // ALL HOOKS MUST BE CALLED BEFORE ANY CONDITIONAL RETURNS
  const totalWidth = useMemo(() => 
    COLUMNS.reduce((sum, col) => sum + col.width, 0),
    []
  )
  
  const scrollRef = useRef(null)
  const headerRef = useRef(null)

  // Sync header scroll with body scroll using useEffect for better performance
  useEffect(() => {
    const scrollWrapper = scrollRef.current
    const header = headerRef.current
    
    if (!scrollWrapper || !header) return

    const handleScroll = () => {
      // Use requestAnimationFrame for smooth synchronization
      requestAnimationFrame(() => {
        if (header && scrollWrapper) {
          header.scrollLeft = scrollWrapper.scrollLeft
        }
      })
    }

    scrollWrapper.addEventListener('scroll', handleScroll, { passive: true })
    
    return () => {
      scrollWrapper.removeEventListener('scroll', handleScroll)
    }
  }, [])

  const Row = ({ index, style }) => {
    if (!data || !Array.isArray(data) || index >= data.length) {
      return null
    }
    
    const row = data[index]
    if (!row) return null

    try {
      return (
        <div 
          style={{ ...style, width: totalWidth, display: 'flex' }} 
          className="table-row"
          onClick={() => onRowClick && onRowClick(row)}
        >
          {COLUMNS.map(col => {
            // Get raw value from row using the exact column key
            const rawValue = row[col.key]
            // Format it using formatValue function
            const value = formatValue(rawValue, col.key, row)
            
            return (
              <div
                key={col.key}
                className={`table-cell ${(col.key === 'grpan_concentration_percent' || col.key === 'grpan_price') ? 'grpan-cell' : ''}`}
                style={{ width: col.width, flexShrink: 0, minWidth: col.width }}
                title={String(value)}
              >
                {String(value)}
              </div>
            )
          })}
        </div>
      )
    } catch (err) {
      console.error('Error rendering row:', err, row)
      return null
    }
  }

  // Check for empty data AFTER all hooks are called
  if (!data || !Array.isArray(data) || data.length === 0) {
    return (
      <div className="empty-state">
        <p>No data available. Click "Load CSV" to start.</p>
      </div>
    )
  }

  return (
    <div className="scanner-table-container">
      <div className="table-scroll-wrapper" ref={scrollRef}>
        <div 
          className="table-header" 
          ref={headerRef}
          style={{ width: totalWidth, minWidth: totalWidth }}
        >
          {COLUMNS.map(col => (
            <div
              key={col.key}
              className="table-header-cell"
              style={{ width: col.width, flexShrink: 0, minWidth: col.width }}
              onClick={() => onSort(col.key)}
            >
              {col.label}
              {sortConfig.key === col.key && (
                <span className="sort-indicator">
                  {sortConfig.direction === 'asc' ? ' ↑' : ' ↓'}
                </span>
              )}
            </div>
          ))}
        </div>
        
        <div className="table-body-wrapper" style={{ width: totalWidth, minWidth: totalWidth }}>
          <List
            height={600}
            itemCount={data.length}
            itemSize={35}
            width={totalWidth}
          >
            {Row}
          </List>
        </div>
      </div>
      
      <div className="table-footer">
        Showing {data.length} symbols
      </div>
    </div>
  )
}

export default ScannerTable

