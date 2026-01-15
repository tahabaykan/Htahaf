import React, { useState, useMemo } from 'react'
import './GroupSidebar.css'

// Janall'dan birebir grup listesi
const PRIMARY_GROUPS = [
  'heldkuponlu',
  'heldkuponlukreciliz',
  'heldkuponlukreorta',
  'heldff',
  'helddeznff',
  'heldnff',
  'heldflr',
  'heldgarabetaltiyedi',
  'heldotelremorta',
  'heldsolidbig',
  'heldtitrekhc',
  'heldbesmaturlu',
  'heldcilizyeniyedi',
  'heldcommonsuz',
  'highmatur',
  'notcefilliquid',
  'notbesmaturlu',
  'nottitrekhc',
  'salakilliquid',
  'shitremhc',
  'rumoreddanger'
]

// Kuponlu gruplar (CGRUP kullanır)
const KUPONLU_GROUPS = ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']

// CGRUP değerleri (kuponlu gruplar için)
const CGRUP_VALUES = ['C400', 'C425', 'C450', 'C475', 'C500', 'C525', 'C550', 'C575', 'C600']

function GroupSidebar({ data = [], selectedGroup, selectedCgrup, onGroupSelect, onCgrupSelect }) {
  const [expandedGroups, setExpandedGroups] = useState(new Set())
  
  // Eğer data yoksa veya boşsa, boş sidebar göster
  if (!data || data.length === 0) {
    return (
      <div className="group-sidebar">
        <div className="group-sidebar-header">
          <h3>📁 GROUPS</h3>
        </div>
        <div className="group-list" style={{ padding: '20px', textAlign: 'center', color: '#999' }}>
          <p>No data loaded</p>
          <p style={{ fontSize: '12px', marginTop: '8px' }}>Load CSV to see groups</p>
        </div>
      </div>
    )
  }

  // Her grup için symbol sayısını hesapla
  const groupCounts = useMemo(() => {
    const counts = {}
    
    PRIMARY_GROUPS.forEach(group => {
      if (KUPONLU_GROUPS.includes(group)) {
        // Kuponlu gruplar: CGRUP'a göre say
        counts[group] = {}
        CGRUP_VALUES.forEach(cgrup => {
          const count = data.filter(item => {
            const itemGroup = (item.GROUP || item.group || item.file_group)?.toLowerCase()
            const itemCgrup = item.CGRUP?.toUpperCase()
            return itemGroup === group && itemCgrup === cgrup
          }).length
          if (count > 0) {
            counts[group][cgrup] = count
          }
        })
        // CGRUP olmayanlar
        const countNoCgrup = data.filter(item => {
          const itemGroup = (item.GROUP || item.group || item.file_group)?.toLowerCase()
          return itemGroup === group && (!item.CGRUP || item.CGRUP === '' || item.CGRUP === 'N/A')
        }).length
        if (countNoCgrup > 0) {
          counts[group]['NO_CGRUP'] = countNoCgrup
        }
      } else {
        // Diğer gruplar: sadece grup bazlı say
        const count = data.filter(item => {
          const itemGroup = (item.GROUP || item.group || item.file_group)?.toLowerCase()
          return itemGroup === group
        }).length
        if (count > 0) {
          counts[group] = count
        }
      }
    })
    
    return counts
  }, [data])

  const toggleGroup = (group) => {
    const newExpanded = new Set(expandedGroups)
    if (newExpanded.has(group)) {
      newExpanded.delete(group)
    } else {
      newExpanded.add(group)
    }
    setExpandedGroups(newExpanded)
  }

  const handleGroupClick = (group, cgrup = null) => {
    if (KUPONLU_GROUPS.includes(group)) {
      // Kuponlu grup: önce expand et
      if (!expandedGroups.has(group)) {
        toggleGroup(group)
      }
      // CGRUP seçildiyse
      if (cgrup) {
        onGroupSelect(group)
        onCgrupSelect(cgrup)
      } else {
        // Sadece grup seçildi (CGRUP yok)
        onGroupSelect(group)
        onCgrupSelect(null)
      }
    } else {
      // Diğer gruplar: direkt seç
      onGroupSelect(group)
      onCgrupSelect(null)
    }
  }

  const getGroupDisplayName = (group) => {
    // Daha okunabilir isimler
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

  return (
    <div className="group-sidebar">
      <div className="group-sidebar-header">
        <h3>📁 GROUPS</h3>
        <button
          className="clear-filter-btn"
          onClick={() => {
            onGroupSelect(null)
            onCgrupSelect(null)
          }}
          disabled={!selectedGroup}
        >
          Clear Filter
        </button>
      </div>
      
      <div className="group-list">
        {PRIMARY_GROUPS.map(group => {
          const isKuponlu = KUPONLU_GROUPS.includes(group)
          const isExpanded = expandedGroups.has(group)
          const isSelected = selectedGroup === group
          const count = groupCounts[group]
          
          if (!count || (isKuponlu && Object.keys(count).length === 0) || (!isKuponlu && count === 0)) {
            return null // Grup boşsa göster
          }
          
          return (
            <div key={group} className="group-item">
              <div
                className={`group-header ${isSelected ? 'selected' : ''}`}
                onClick={() => {
                  if (isKuponlu) {
                    toggleGroup(group)
                  } else {
                    handleGroupClick(group)
                  }
                }}
              >
                <span className="group-name">{getGroupDisplayName(group)}</span>
                {isKuponlu && (
                  <span className="expand-icon">{isExpanded ? '▼' : '▶'}</span>
                )}
                {!isKuponlu && (
                  <span className="group-count">{typeof count === 'number' ? count : Object.values(count).reduce((a, b) => a + b, 0)}</span>
                )}
              </div>
              
              {isKuponlu && isExpanded && (
                <div className="cgrup-list">
                  {CGRUP_VALUES.map(cgrup => {
                    const cgrupCount = count[cgrup]
                    if (!cgrupCount) return null
                    
                    const isCgrupSelected = isSelected && selectedCgrup === cgrup
                    
                    return (
                      <div
                        key={cgrup}
                        className={`cgrup-item ${isCgrupSelected ? 'selected' : ''}`}
                        onClick={(e) => {
                          e.stopPropagation()
                          handleGroupClick(group, cgrup)
                        }}
                      >
                        <span className="cgrup-name">{cgrup}</span>
                        <span className="cgrup-count">{cgrupCount}</span>
                      </div>
                    )
                  })}
                  {count['NO_CGRUP'] && (
                    <div
                      className={`cgrup-item ${isSelected && !selectedCgrup ? 'selected' : ''}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        handleGroupClick(group, null)
                      }}
                    >
                      <span className="cgrup-name">(No CGRUP)</span>
                      <span className="cgrup-count">{count['NO_CGRUP']}</span>
                    </div>
                  )}
                </div>
              )}
              
              {!isKuponlu && isSelected && (
                <div className="group-indicator">✓</div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default GroupSidebar

