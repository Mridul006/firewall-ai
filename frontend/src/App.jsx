import { BrowserRouter as Router, Navigate, NavLink, Route, Routes } from 'react-router-dom'

import AlertBanner from './components/AlertBanner'
import { AuthProvider, useAuth } from './hooks/useAuth'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import Rules from './pages/Rules'
import Traffic from './pages/Traffic'

function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth()

  if (loading) {
    return <div className="p-6 text-sm text-gray-500">Loading…</div>
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return children
}

function navLinkClass({ isActive }) {
  return isActive
    ? 'text-blue-600 dark:text-blue-400'
    : 'text-gray-700 hover:text-blue-600 dark:text-gray-200'
}

function NavBar() {
  const { user, logout } = useAuth()

  return (
    <nav className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3 dark:border-gray-700 dark:bg-gray-800">
      <div className="flex gap-4 text-sm font-medium">
        <NavLink to="/" end className={navLinkClass}>
          Dashboard
        </NavLink>
        <NavLink to="/rules" className={navLinkClass}>
          Rules
        </NavLink>
        <NavLink to="/traffic" className={navLinkClass}>
          Traffic
        </NavLink>
      </div>
      <div className="flex items-center gap-3 text-sm text-gray-500">
        {user && <span>{user.email}</span>}
        <button type="button" onClick={logout} className="text-red-600 hover:text-red-800">
          Log out
        </button>
      </div>
    </nav>
  )
}

function Layout({ children }) {
  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-950">
      <NavBar />
      {/* Rendered here, not inside Dashboard, so the WebSocket connection
          persists across navigation instead of reconnecting (and missing
          alerts) every time the analyst leaves and returns to the Dashboard
          page. */}
      <AlertBanner />
      {children}
    </div>
  )
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout>
              <Dashboard />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/rules"
        element={
          <ProtectedRoute>
            <Layout>
              <Rules />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/traffic"
        element={
          <ProtectedRoute>
            <Layout>
              <Traffic />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <Router>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </Router>
  )
}
