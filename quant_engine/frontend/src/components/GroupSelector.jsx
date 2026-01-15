import React, { useState, useRef, useEffect, useMemo } from 'react'
import './GroupSelector.css'

// Janall'dan birebir grup listesi
const PRIMARY_GROUPS = [
  'heldkuponlu', 'heldff', 'heldsolidbig', 'highmatur', 'heldflr', 'notheldtitrekhc',
  'rumoreddanger', 'helddeznff', 'heldgarabetaltiyedi', 'heldkuponlukreciliz',
  'heldkuponlukreorta', 'heldnff', 'heldotelremorta', 'heldtitrekhc',
  'notcefilliquid', 'notbesmaturlu', 'nottitrekhc', 'salakilliquid',
  'shitremhc', 'heldcilizyeniyedi', 'heldcommonsuz'
]

// Kuponlu groups that use CGRUP
const KUPONLU_GROUPS = ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']

// CGRUP values (for kuponlu groups)
const CGRUP_VALUES = ['C400', 'C425', 'C450', 'C475', 'C500', 'C525', 'C550', 'C575', 'C600']

function GroupSelector({ data = [] }) {
  const [isOpen, setIsOpen] = useState(false)
  const [expandedGroups, setExpandedGroups] = useState(new Set())
  const dropdownRef = useRef(null)

  // Calculate symbol count for each group/subgroup
  const groupCounts = useMemo(() => {
    const counts = {}
    
    PRIMARY_GROUPS.forEach(group => {
      if (KUPONLU_GROUPS.includes(group)) {
        // Kuponlu groups: count by CGRUP
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
        // Count symbols in kuponlu group that do NOT have a CGRUP
        const countNoCgrup = data.filter(item => {
          const itemGroup = (item.GROUP || item.group || item.file_group)?.toLowerCase()
          return itemGroup === group && (!item.CGRUP || item.CGRUP === '' || item.CGRUP === 'N/A')
        }).length
        if (countNoCgrup > 0) {
          counts[group]['NO_CGRUP'] = countNoCgrup
        }
      } else {
        // Other groups: count by primary group only
        const count = data.filter(item => {
          const itemGroup = (item.GROUP || item.group || item.file_group)?.toLowerCase()
          return itemGroup === group
        }).length
        // Show all groups even if count is 0 (data might not be loaded yet)
        counts[group] = count
      }
    })
    return counts
  }, [data])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  const toggleGroup = (groupName) => {
    setExpandedGroups(prev => {
      const newSet = new Set(prev)
      if (newSet.has(groupName)) {
        newSet.delete(groupName)
      } else {
        newSet.add(groupName)
      }
      return newSet
    })
  }

  const handleGroupSelect = (groupName, cgrupName = null) => {
    // Build URL with group filter
    const params = new URLSearchParams()
    params.set('group', groupName)
    if (cgrupName && cgrupName !== 'no_cgrup') {
      params.set('cgrup', cgrupName)
    }
    
    // Open in new tab
    const url = `${window.location.origin}${window.location.pathname}?${params.toString()}`
    window.open(url, '_blank')
    
    // Close dropdown
    setIsOpen(false)
  }

  return (
    <div className="group-selector" ref={dropdownRef} style={{ display: 'inline-block', position: 'relative' }}>
      <button 
        className="group-selector-button"
        onClick={() => setIsOpen(!isOpen)}
        style={{ 
          display: 'inline-block',
          visibility: 'visible',
          opacity: 1
        }}
      >
        📁 Groups
      </button>
      
      {isOpen && (
        <div className="group-dropdown">
          <div className="group-dropdown-header">
            <h3>Select Group</h3>
            <button 
              className="close-button"
              onClick={() => setIsOpen(false)}
            >
              ×
            </button>
          </div>
          
          <div className="group-dropdown-content">
            {PRIMARY_GROUPS.map(groupName => {
              const isKuponlu = KUPONLU_GROUPS.includes(groupName)
              const hasSubgroups = isKuponlu && Object.keys(groupCounts[groupName] || {}).length > 0
              const isExpanded = expandedGroups.has(groupName)
              const groupCount = isKuponlu 
                ? Object.values(groupCounts[groupName] || {}).reduce((sum, count) => sum + count, 0)
                : groupCounts[groupName] || 0

              // Show all groups, even if count is 0 (data might not be loaded yet)
              // This allows users to see all available groups regardless of current data

              return (
                <div key={groupName} className="group-dropdown-item">
                  <div 
                    className="group-dropdown-header-item"
                    onClick={() => isKuponlu ? toggleGroup(groupName) : handleGroupSelect(groupName)}
                  >
                    <span className="group-name">{groupName}</span>
                    <span className="group-count">({groupCount})</span>
                    {isKuponlu && (
                      <span className={`toggle-icon ${isExpanded ? 'expanded' : ''}`}>▼</span>
                    )}
                  </div>
                  {isKuponlu && isExpanded && hasSubgroups && (
                    <div className="cgrup-dropdown-list">
                      {CGRUP_VALUES.map(cgrupName => {
                        const cgrupCount = groupCounts[groupName]?.[cgrupName] || 0
                        if (cgrupCount === 0) return null
                        return (
                          <div 
                            key={cgrupName} 
                            className="cgrup-dropdown-item"
                            onClick={() => handleGroupSelect(groupName, cgrupName.toLowerCase())}
                          >
                            <span className="cgrup-name">{cgrupName}</span>
                            <span className="cgrup-count">({cgrupCount})</span>
                          </div>
                        )
                      })}
                      {groupCounts[groupName]?.['NO_CGRUP'] > 0 && (
                        <div 
                          className="cgrup-dropdown-item"
                          onClick={() => handleGroupSelect(groupName, 'no_cgrup')}
                        >
                          <span className="cgrup-name">No CGRUP</span>
                          <span className="cgrup-count">({groupCounts[groupName]['NO_CGRUP']})</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

export default GroupSelector

