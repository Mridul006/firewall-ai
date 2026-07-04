import axios from 'axios'

// This is a standalone Vite app served from the browser (not a sandboxed
// artifact environment), so the JWT is kept in localStorage for simplicity.
// Note this is vulnerable to XSS-based token theft; a production deployment
// should prefer an httpOnly cookie set by the backend instead.
export const TOKEN_STORAGE_KEY = 'firewall_ai_token'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_STORAGE_KEY)
      window.dispatchEvent(new Event('auth:unauthorized'))
    }
    return Promise.reject(error)
  },
)

export default api
