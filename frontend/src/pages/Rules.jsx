import { useState } from 'react'

import RuleList from '../components/RuleList'
import { useRules } from '../hooks/useRules'

const TABS = ['PENDING', 'APPROVED_PENDING', 'LIVE', 'REJECTED']

export default function Rules() {
  const [activeTab, setActiveTab] = useState(TABS[0])
  const { rules, loading, error, approveRule, rejectRule } = useRules(activeTab)

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Rules</h1>

      <div className="mt-4 flex gap-2 border-b border-gray-200 dark:border-gray-700">
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-2 text-sm font-medium ${
              activeTab === tab
                ? 'border-b-2 border-blue-600 text-blue-600'
                : 'text-gray-500 hover:text-gray-700 dark:text-gray-400'
            }`}
          >
            {tab.replace('_', ' ')}
          </button>
        ))}
      </div>

      <div className="mt-4">
        <RuleList
          rules={rules}
          loading={loading}
          error={error}
          onApprove={approveRule}
          onReject={rejectRule}
        />
      </div>
    </div>
  )
}
