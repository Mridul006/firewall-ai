import { useCallback, useEffect, useState } from 'react'

import api from '../api'

export function useTraffic(onlyAnomalies = false) {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchTraffic = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const path = onlyAnomalies ? '/api/v1/traffic/anomalies' : '/api/v1/traffic/'
      const response = await api.get(path)
      setEvents(response.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load traffic data')
    } finally {
      setLoading(false)
    }
  }, [onlyAnomalies])

  useEffect(() => {
    fetchTraffic()
  }, [fetchTraffic])

  return { events, loading, error, refetch: fetchTraffic }
}
