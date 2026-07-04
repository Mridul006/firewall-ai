import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

export default function TrafficChart({ events, loading, error }) {
  if (loading) {
    return <div className="text-sm text-gray-500">Loading traffic data…</div>
  }

  if (error) {
    return <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
  }

  if (!events || events.length === 0) {
    return <div className="text-sm text-gray-500">No traffic data available.</div>
  }

  const data = [...events]
    .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
    .map((event) => ({
      time: new Date(event.timestamp).toLocaleTimeString(),
      bytes: event.bytes,
      anomaly_score: event.anomaly_score,
    }))

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="time" tick={{ fontSize: 12 }} />
        <YAxis yAxisId="bytes" tick={{ fontSize: 12 }} />
        <YAxis yAxisId="score" orientation="right" domain={[0, 1]} tick={{ fontSize: 12 }} />
        <Tooltip />
        <Legend />
        <Line
          yAxisId="bytes"
          type="monotone"
          dataKey="bytes"
          stroke="#2563eb"
          dot={false}
          name="Bytes"
        />
        <Line
          yAxisId="score"
          type="monotone"
          dataKey="anomaly_score"
          stroke="#dc2626"
          dot={false}
          name="Anomaly score"
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
