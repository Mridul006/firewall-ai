import RuleCard from './RuleCard'

export default function RuleList({ rules, loading, error, onApprove, onReject, onRevoke }) {
  if (loading) {
    return <div className="text-sm text-gray-500">Loading rules…</div>
  }

  if (error) {
    return <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
  }

  if (rules.length === 0) {
    return <div className="text-sm text-gray-500">No rules in this category.</div>
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {rules.map((rule) => (
        <RuleCard
          key={rule.id}
          rule={rule}
          onApprove={onApprove}
          onReject={onReject}
          onRevoke={onRevoke}
        />
      ))}
    </div>
  )
}
