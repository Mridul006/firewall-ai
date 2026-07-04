import StatCards from '../components/StatCards'
import TrafficChart from '../components/TrafficChart'
import { useDashboardStats } from '../hooks/useDashboardStats'
import { useTraffic } from '../hooks/useTraffic'

export default function Dashboard() {
  const { stats, loading: statsLoading, error: statsError } = useDashboardStats()
  const { events, loading: trafficLoading, error: trafficError } = useTraffic()

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Dashboard</h1>

      <div className="mt-4">
        <StatCards stats={stats} loading={statsLoading} error={statsError} />
      </div>

      <div className="mt-6">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
          Traffic &amp; anomaly score
        </h2>
        <div className="mt-2 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
          <TrafficChart events={events} loading={trafficLoading} error={trafficError} />
        </div>
      </div>
    </div>
  )
}
