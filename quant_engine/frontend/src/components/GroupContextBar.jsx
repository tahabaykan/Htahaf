import React, { useMemo } from 'react'
import './GroupContextBar.css'

// Benchmark formülleri (group_benchmark.yaml'den)
const BENCHMARK_FORMULAS = {
  'heldkuponlu': {
    'C400': { PFF: 0.36, TLT: 0.36, IEF: 0.08, IEI: 0.0 },
    'C425': { PFF: 0.368, TLT: 0.34, IEF: 0.092, IEI: 0.0 },
    'C450': { PFF: 0.38, TLT: 0.32, IEF: 0.10, IEI: 0.0 },
    'C475': { PFF: 0.40, TLT: 0.30, IEF: 0.12, IEI: 0.0 },
    'C500': { PFF: 0.32, TLT: 0.40, IEF: 0.08, IEI: 0.0 },
    'C525': { PFF: 0.30, TLT: 0.42, IEF: 0.10, IEI: 0.0 },
    'C550': { PFF: 0.28, TLT: 0.44, IEF: 0.12, IEI: 0.0 },
    'C575': { PFF: 0.26, TLT: 0.46, IEF: 0.14, IEI: 0.0 },
    'C600': { PFF: 0.24, TLT: 0.48, IEF: 0.16, IEI: 0.0 },
    'default': { PFF: 1.0 }
  },
  'heldkuponlukreciliz': {
    'default': { PFF: 1.0 } // CGRUP'a göre aynı formül kullanılır (heldkuponlu ile aynı)
  },
  'heldkuponlukreorta': {
    'default': { PFF: 1.0 } // CGRUP'a göre aynı formül kullanılır (heldkuponlu ile aynı)
  }
}

// Kuponlu gruplar
const KUPONLU_GROUPS = ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']

function GroupContextBar({ selectedGroup, selectedCgrup, data }) {
  const groupData = useMemo(() => {
    if (!selectedGroup) return null
    
    const filtered = data.filter(item => {
      const itemGroup = (item.GROUP || item.group || item.file_group)?.toLowerCase()
      if (itemGroup !== selectedGroup) return false
      
      if (KUPONLU_GROUPS.includes(selectedGroup)) {
        if (selectedCgrup) {
          return item.CGRUP?.toUpperCase() === selectedCgrup
        } else {
          return !item.CGRUP || item.CGRUP === '' || item.CGRUP === 'N/A'
        }
      }
      return true
    })
    
    return filtered
  }, [selectedGroup, selectedCgrup, data])

  const benchmarkFormula = useMemo(() => {
    if (!selectedGroup) return null
    
    if (KUPONLU_GROUPS.includes(selectedGroup)) {
      // Kuponlu gruplar için CGRUP'a göre formül
      const groupFormulas = BENCHMARK_FORMULAS[selectedGroup] || BENCHMARK_FORMULAS['heldkuponlu']
      if (selectedCgrup && groupFormulas[selectedCgrup]) {
        return groupFormulas[selectedCgrup]
      }
      return groupFormulas['default'] || { PFF: 1.0 }
    }
    
    // Diğer gruplar için default (şimdilik PFF, ileride config'den gelecek)
    return { PFF: 1.0 }
  }, [selectedGroup, selectedCgrup])

  const groupStats = useMemo(() => {
    if (!groupData || groupData.length === 0) return null
    
    const stats = {
      total: groupData.length,
      watch: groupData.filter(item => item.state === 'WATCH').length,
      candidate: groupData.filter(item => item.state === 'CANDIDATE').length,
      avgGrpanDev: null,
      avgRwvapDev: null,
      sellPressure: 0
    }
    
    // GRPAN ORT DEV ortalaması
    const grpanDevs = groupData
      .map(item => item.grpan_ort_dev)
      .filter(val => val !== null && val !== undefined && !isNaN(val))
    if (grpanDevs.length > 0) {
      stats.avgGrpanDev = grpanDevs.reduce((a, b) => a + b, 0) / grpanDevs.length
    }
    
    // RWVAP ORT DEV ortalaması
    const rwvapDevs = groupData
      .map(item => item.rwvap_ort_dev)
      .filter(val => val !== null && val !== undefined && !isNaN(val))
    if (rwvapDevs.length > 0) {
      stats.avgRwvapDev = rwvapDevs.reduce((a, b) => a + b, 0) / rwvapDevs.length
    }
    
    // SELL pressure (GRPAN ORT DEV < 0 olanların yüzdesi)
    if (grpanDevs.length > 0) {
      const negativeCount = grpanDevs.filter(d => d < 0).length
      stats.sellPressure = (negativeCount / grpanDevs.length) * 100
    }
    
    return stats
  }, [groupData])

  if (!selectedGroup) return null

  const getGroupDisplayName = (group) => {
    const displayNames = {
      'heldkuponlu': 'Held Kuponlu',
      'heldkuponlukreciliz': 'Held Kuponlu Kredi Düşük',
      'heldkuponlukreorta': 'Held Kuponlu Kredi Orta',
      'heldff': 'Held FF',
      'helddeznff': 'Held Dezenflasyon NFF',
      'heldnff': 'Held NFF',
      'heldflr': 'Held FLR',
      'heldgarabetaltiyedi': 'Held Garantili Altı Yedi',
      'heldotelremorta': 'Held Overnight Repo Orta',
      'heldsolidbig': 'Held Solid Big',
      'heldtitrekhc': 'Held Titrek HC',
      'heldbesmaturlu': 'Held Beş Maturiteli',
      'heldcilizyeniyedi': 'Held Ciliz Yeni Yedi',
      'heldcommonsuz': 'Held Common Siz',
      'highmatur': 'High Maturity',
      'notcefilliquid': 'Not Çok Filliquid',
      'notbesmaturlu': 'Not Beş Maturiteli',
      'nottitrekhc': 'Not Titrek HC',
      'salakilliquid': 'Salak Illiquid',
      'shitremhc': 'Shit Rem HC',
      'rumoreddanger': 'Rumored Danger'
    }
    return displayNames[group] || group
  }

  const formatBenchmarkFormula = (formula) => {
    const parts = []
    Object.entries(formula).forEach(([etf, coeff]) => {
      if (coeff !== 0) {
        parts.push(`${coeff.toFixed(3)}×${etf}`)
      }
    })
    return parts.join(' + ')
  }

  return (
    <div className="group-context-bar">
      <div className="context-section">
        <div className="context-label">GROUP:</div>
        <div className="context-value">
          {getGroupDisplayName(selectedGroup)}
          {selectedCgrup && <span className="cgrup-badge">{selectedCgrup}</span>}
        </div>
      </div>
      
      {benchmarkFormula && (
        <div className="context-section">
          <div className="context-label">Benchmark:</div>
          <div className="context-value formula">
            {formatBenchmarkFormula(benchmarkFormula)}
          </div>
        </div>
      )}
      
      {groupStats && (
        <>
          <div className="context-section">
            <div className="context-label">Count:</div>
            <div className="context-value">
              {groupStats.total} total
              {groupStats.watch > 0 && ` • ${groupStats.watch} WATCH`}
              {groupStats.candidate > 0 && ` • ${groupStats.candidate} CANDIDATE`}
            </div>
          </div>
          
          {groupStats.avgGrpanDev !== null && (
            <div className="context-section">
              <div className="context-label">Avg GOD:</div>
              <div className={`context-value ${groupStats.avgGrpanDev < 0 ? 'negative' : 'positive'}`}>
                {groupStats.avgGrpanDev > 0 ? '+' : ''}{groupStats.avgGrpanDev.toFixed(2)}
              </div>
            </div>
          )}
          
          {groupStats.avgRwvapDev !== null && (
            <div className="context-section">
              <div className="context-label">Avg ROD:</div>
              <div className={`context-value ${groupStats.avgRwvapDev < 0 ? 'negative' : 'positive'}`}>
                {groupStats.avgRwvapDev > 0 ? '+' : ''}{groupStats.avgRwvapDev.toFixed(2)}
              </div>
            </div>
          )}
          
          {groupStats.sellPressure > 0 && (
            <div className="context-section">
              <div className="context-label">Sell Pressure:</div>
              <div className="context-value">
                {groupStats.sellPressure.toFixed(1)}%
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default GroupContextBar

