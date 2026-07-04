import { createContext, createElement, useContext, useEffect, useState } from 'react'

import api, { TOKEN_STORAGE_KEY } from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_STORAGE_KEY))
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    function handleUnauthorized() {
      setUser(null)
      setToken(null)
    }
    window.addEventListener('auth:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('auth:unauthorized', handleUnauthorized)
  }, [])

  useEffect(() => {
    if (!token) {
      setLoading(false)
      return
    }

    let cancelled = false
    setLoading(true)
    api
      .get('/api/v1/auth/me')
      .then((response) => {
        if (!cancelled) setUser(response.data)
      })
      .catch(() => {
        if (!cancelled) {
          setUser(null)
          setToken(null)
          localStorage.removeItem(TOKEN_STORAGE_KEY)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [token])

  async function login(email, password) {
    setError(null)
    try {
      const response = await api.post('/api/v1/auth/login', { email, password })
      const accessToken = response.data.access_token
      localStorage.setItem(TOKEN_STORAGE_KEY, accessToken)
      setToken(accessToken)
      const meResponse = await api.get('/api/v1/auth/me')
      setUser(meResponse.data)
      return true
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed')
      return false
    }
  }

  function logout() {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
    setToken(null)
    setUser(null)
  }

  const value = {
    user,
    isAuthenticated: Boolean(token && user),
    loading,
    error,
    login,
    logout,
  }

  // createElement, not JSX: this file is a .js hook file per coding_rules.md's
  // "Hook files: useCamelCase.js" convention, and this project's build engine
  // (Vite 8 / rolldown) only parses JSX syntax in .jsx files.
  return createElement(AuthContext.Provider, { value }, children)
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
