import TrafficChart from '../components/TrafficChart'
import { useTraffic } from '../hooks/useTraffic'

export default function Traffic() {
  const { events, loading, error } = useTraffic()
  const { events: anomalies, loading: anomaliesLoading, error: anomaliesError } = useTraffic(true)

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Traffic explorer</h1>

      <div className="mt-4 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">All traffic</h2>
        <TrafficChart events={events} loading={loading} error={error} />
      </div>

      <div className="mt-6 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
          Anomaly timeline
        </h2>
        <TrafficChart events={anomalies} loading={anomaliesLoading} error={anomaliesError} />
      </div>
    </div>
  )
}
