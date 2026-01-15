---
description: UI table columns must be sortable by clicking headers
---

# Sortable Table Columns Rule

All data tables in the Quant Engine frontend should follow this pattern for sortable columns:

## 1. State Setup
```javascript
const [sortBy, setSortBy] = useState('default_column')
const [sortDirection, setSortDirection] = useState('desc')
```

## 2. Sort Handler
```javascript
const handleSort = (column) => {
    if (sortBy === column) {
        setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
        setSortBy(column)
        setSortDirection('desc')
    }
}
```

## 3. Header Pattern (EVERY column should be sortable)
```jsx
<th onClick={() => handleSort('column_name')} className="sortable" title="Column description">
    Column Label {sortBy === 'column_name' && (sortDirection === 'asc' ? '↑' : '↓')}
</th>
```

## 4. Sorting Logic (handle null values)
```javascript
const sortedData = [...data].sort((a, b) => {
    let aValue = a.column ?? null
    let bValue = b.column ?? null
    
    // Handle null values - put nulls at end
    if (aValue === null && bValue === null) return 0
    if (aValue === null) return 1
    if (bValue === null) return -1
    
    return sortDirection === 'asc' ? aValue - bValue : bValue - aValue
})
```

## 5. CSS for sortable headers
```css
.sortable {
    cursor: pointer;
    user-select: none;
}
.sortable:hover {
    background-color: rgba(255, 255, 255, 0.1);
}
```

**IMPORTANT:** When adding new columns to any table, ALWAYS make them sortable following this pattern.
