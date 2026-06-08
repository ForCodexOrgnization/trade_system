export function responseRows(data) {
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.results)) return data.results
  return []
}

export function responseCount(data, rows = responseRows(data)) {
  if (data && typeof data.count === 'number') return data.count
  return rows.length
}
