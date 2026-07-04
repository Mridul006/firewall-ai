function StatCard({ label, value }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-gray-900 dark:text-gray-100">{value}</p>
    </div>
  )
}

export default function StatCards({ stats, loading, error }) {
  if (loading) {
    return <div className="text-sm text-gray-500">Loading stats…</div>
  }

  if (error) {
    return <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
  }

  if (!stats) {
    return null
  }

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <StatCard label="Total Rules" value={stats.total_rules} />
      <StatCard label="Pending" value={stats.pending_rules} />
      <StatCard label="Live" value={stats.live_rules} />
      <StatCard label="Anomalies Today" value={stats.anomalies_24h} />
    </div>
  )
}
