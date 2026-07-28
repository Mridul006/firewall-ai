import { useState } from 'react'

const STATUS_STYLES = {
  PENDING: 'bg-yellow-100 text-yellow-800',
  SANDBOX_TESTING: 'bg-blue-100 text-blue-800',
  APPROVED_PENDING: 'bg-purple-100 text-purple-800',
  LIVE: 'bg-green-100 text-green-800',
  REJECTED: 'bg-red-100 text-red-800',
  REVOKED: 'bg-gray-200 text-gray-700',
}

export default function RuleCard({ rule, onApprove, onReject, onRevoke }) {
  const [actionLoading, setActionLoading] = useState(false)
  const [actionError, setActionError] = useState(null)

  async function handleApprove() {
    setActionLoading(true)
    setActionError(null)
    const ok = await onApprove(rule.id)
    if (!ok) setActionError('Failed to approve rule')
    setActionLoading(false)
  }

  async function handleReject() {
    setActionLoading(true)
    setActionError(null)
    const ok = await onReject(rule.id)
    if (!ok) setActionError('Failed to reject rule')
    setActionLoading(false)
  }

  async function handleRevoke() {
    if (!window.confirm('Revoke this live rule? It will stop being enforced.')) return
    setActionLoading(true)
    setActionError(null)
    const ok = await onRevoke(rule.id)
    if (!ok) setActionError('Failed to revoke rule')
    setActionLoading(false)
  }

  const fpRatePercent =
    typeof rule.fp_rate === 'number' ? `${(rule.fp_rate * 100).toFixed(2)}%` : '—'
  const confidencePercent =
    typeof rule.confidence === 'number' ? `${(rule.confidence * 100).toFixed(0)}%` : '—'
  const policyConflicts = rule.sandbox_result?.policy_conflicts || []

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <div className="flex items-start justify-between gap-2">
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
            STATUS_STYLES[rule.status] || 'bg-gray-100 text-gray-800'
          }`}
        >
          {rule.status}
        </span>
        <span className="text-xs text-gray-400">{rule.syntax}</span>
      </div>

      <pre className="mt-3 overflow-x-auto rounded-md bg-gray-900 p-3 text-xs text-gray-100">
        <code>{rule.command}</code>
      </pre>

      {rule.description && (
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">{rule.description}</p>
      )}

      <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
        <div>
          <dt className="text-gray-400">MITRE technique</dt>
          <dd className="font-medium text-gray-700 dark:text-gray-200">
            {rule.mitre_technique || '—'}
          </dd>
        </div>
        <div>
          <dt className="text-gray-400">Confidence</dt>
          <dd className="font-medium text-gray-700 dark:text-gray-200">{confidencePercent}</dd>
        </div>
        <div>
          <dt className="text-gray-400">FP rate (sandbox)</dt>
          <dd className="font-medium text-gray-700 dark:text-gray-200">{fpRatePercent}</dd>
        </div>
      </dl>

      {policyConflicts.length > 0 && (
        <div className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-2 dark:border-amber-700 dark:bg-amber-900/30">
          <p className="text-xs font-semibold text-amber-800 dark:text-amber-300">
            ⚠ {policyConflicts.length} policy conflict{policyConflicts.length > 1 ? 's' : ''} with LIVE rules — review before approving
          </p>
          <ul className="mt-1 list-inside list-disc text-xs text-amber-700 dark:text-amber-400">
            {policyConflicts.map((conflict, i) => (
              <li key={i}>{conflict.message}</li>
            ))}
          </ul>
        </div>
      )}

      {actionError && (
        <p className="mt-2 rounded-md bg-red-50 p-2 text-xs text-red-700">{actionError}</p>
      )}

      {rule.status === 'APPROVED_PENDING' && (
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={handleApprove}
            disabled={actionLoading}
            className="rounded-md bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            {actionLoading ? 'Working…' : 'Approve'}
          </button>
          <button
            type="button"
            onClick={handleReject}
            disabled={actionLoading}
            className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
          >
            {actionLoading ? 'Working…' : 'Reject'}
          </button>
        </div>
      )}

      {rule.status === 'LIVE' && (
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={handleRevoke}
            disabled={actionLoading}
            className="rounded-md bg-gray-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
          >
            {actionLoading ? 'Working…' : 'Revoke'}
          </button>
        </div>
      )}
    </div>
  )
}
