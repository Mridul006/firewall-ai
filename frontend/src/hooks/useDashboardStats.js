import { useCallback, useEffect, useState } from 'react'

import api from '../api'

// Not in the originally requested hooks list, but coding_rules.md requires
// "custom hooks for all data fetching" — Dashboard.jsx needs this data, so it
// gets its own hook rather than fetching inline.
export function useDashboardStats() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchStats = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.get('/api/v1/dashboard/stats')
      setStats(response.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load dashboard stats')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchStats()
  }, [fetchStats])

  return { stats, loading, error, refetch: fetchStats }
}
