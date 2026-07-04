import { useCallback, useEffect, useState } from 'react'

import api from '../api'

export function useRules(statusFilter) {
  const [rules, setRules] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [actionError, setActionError] = useState(null)

  const fetchRules = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = statusFilter ? { status_filter: statusFilter } : {}
      const response = await api.get('/api/v1/rules/', { params })
      setRules(response.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load rules')
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    fetchRules()
  }, [fetchRules])

  async function approveRule(ruleId) {
    setActionError(null)
    try {
      await api.post(`/api/v1/rules/${ruleId}/approve`)
      await fetchRules()
      return true
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to approve rule')
      return false
    }
  }

  async function rejectRule(ruleId) {
    setActionError(null)
    try {
      await api.post(`/api/v1/rules/${ruleId}/reject`)
      await fetchRules()
      return true
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to reject rule')
      return false
    }
  }

  return { rules, loading, error, actionError, refetch: fetchRules, approveRule, rejectRule }
}
